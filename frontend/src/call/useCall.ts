import { useCallback, useEffect, useRef, useState } from 'react';
import { unlockAudio, openMic } from '../audio/mic';
import { Vad } from '../audio/vad';
import { Stt } from '../audio/stt';

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) || '';

export type CallState = 'idle' | 'connecting' | 'listening' | 'thinking' | 'speaking' | 'reconnecting';

export type Emotion = 'calm' | 'happy' | 'angry' | 'offended' | 'sad' | 'flirty' | 'ashamed';

export interface TranscriptItem {
  id: string;
  speaker: 'user' | 'tutor';
  text: string;
  timestamp: Date;
  seq?: number;
}

export interface Playing {
  seq: number;
  text: string;
  startedAt: number;
  durationMs: number;
}

type ChunkState = 'queued' | 'playing' | 'ended';

function computePlayedCount(states: Map<number, ChunkState>): number {
  let count = 0;
  while (states.get(count + 1) === 'ended') count++;
  return count;
}

interface TurnEventData {
  emotion?: string;
  delta?: string;
  seq?: number;
  mime?: string;
  b64?: string;
  text?: string;
  code?: string;
}

interface CallStartResponse {
  call_id: string;
  deepgram_token: string;
  deepgram_auth?: 'bearer' | 'token';
  deepgram_expires_in: number | null;
}

/** setTimeout wrapped as a cancelable promise; the timer id is tracked in timersRef so a caller can clear it. */
function wait(ms: number, timersRef: { current: Set<number> }): Promise<void> {
  return new Promise((resolve) => {
    const id = window.setTimeout(() => {
      timersRef.current.delete(id);
      resolve();
    }, ms);
    timersRef.current.add(id);
  });
}

export function useCall() {
  const [callState, setCallState] = useState<CallState>('idle');
  const [audioLevel, setAudioLevel] = useState<number>(0);
  const [transcripts, setTranscripts] = useState<TranscriptItem[]>([]);
  const [currentCaption, setCurrentCaption] = useState<string>('');
  const [emotion, setEmotion] = useState<Emotion>('calm');
  const [muted, setMuted] = useState<boolean>(false);
  const [micError, setMicError] = useState<boolean>(false);
  const [playing, setPlaying] = useState<Playing | null>(null);

  const callStateRef = useRef<CallState>('idle');
  const callIdRef = useRef<string>('local');

  const abortRef = useRef<AbortController | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const micRef = useRef<{ stream: MediaStream; stop(): void } | null>(null);
  const sttRef = useRef<Stt | null>(null);
  const vadRef = useRef<Vad | null>(null);
  const animFrameRef = useRef<number | null>(null);

  const emotionRef = useRef<string>('calm');
  const mutedRef = useRef<boolean>(false);
  const playingRef = useRef<AudioBufferSourceNode[]>([]);
  const nextStartTimeRef = useRef<number>(0);
  const streamDoneRef = useRef<boolean>(false);
  const turnStartedRef = useRef<boolean>(false);
  const queueChainRef = useRef<Promise<void>>(Promise.resolve());

  const chunkStateRef = useRef<Map<number, ChunkState>>(new Map());
  const chunkTimeoutRef = useRef<Map<number, number>>(new Map());
  const chunkDurationRef = useRef<Map<number, number>>(new Map());
  const turnTutorIdsRef = useRef<Map<number, string>>(new Map());
  const playedCountRef = useRef<number>(0);
  const pendingSpokenUptoRef = useRef<number | null>(null);

  const endingRef = useRef<boolean>(false);
  const reconnectTimersRef = useRef<Set<number>>(new Set());
  const reconnectingSttRef = useRef<boolean>(false);
  const reconnectSttRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    callStateRef.current = callState;
  }, [callState]);

  const updateAudioLevel = useCallback(function tick(): void {
    if (!analyserRef.current) return;
    const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount);
    analyserRef.current.getByteTimeDomainData(dataArray);
    let sumSquares = 0;
    for (let i = 0; i < dataArray.length; i++) {
      const v = (dataArray[i] - 128) / 128;
      sumSquares += v * v;
    }
    const rms = Math.sqrt(sumSquares / dataArray.length);
    setAudioLevel(Math.min(1, rms * 4));
    animFrameRef.current = requestAnimationFrame(tick);
  }, []);

  const finishSpeaking = useCallback(() => {
    setCallState('listening');
    setPlaying(null);
    vadRef.current?.setCharlieSpeaking(false);
    if (!mutedRef.current) {
      vadRef.current?.start();
      sttRef.current?.unmute();
    }
  }, []);

  const decodeAndSchedule = useCallback(
    async (b64: string, text: string, seq: number) => {
      const ctx = ctxRef.current;
      if (!ctx) return;

      const binary = atob(b64);
      const len = binary.length;
      const bytes = new Uint8Array(len);
      for (let i = 0; i < len; i++) bytes[i] = binary.charCodeAt(i);

      let buffer: AudioBuffer;
      try {
        buffer = await ctx.decodeAudioData(bytes.buffer.slice(0));
      } catch (err) {
        console.error('decodeAudioData failed:', err);
        return;
      }

      const src = ctx.createBufferSource();
      src.buffer = buffer;
      src.connect(ctx.destination);
      if (analyserRef.current) src.connect(analyserRef.current);

      if (!turnStartedRef.current) {
        turnStartedRef.current = true;
        setCallState('speaking');
        vadRef.current?.setCharlieSpeaking(true);
        vadRef.current?.muteFor(200);
        sttRef.current?.mute();
      }

      const startAt = Math.max(ctx.currentTime, nextStartTimeRef.current);
      src.start(startAt);
      nextStartTimeRef.current = startAt + buffer.duration;
      playingRef.current.push(src);
      chunkStateRef.current.set(seq, 'queued');
      chunkDurationRef.current.set(seq, buffer.duration * 1000);

      const delayMs = Math.max(0, (startAt - ctx.currentTime) * 1000);
      const timeoutId = window.setTimeout(() => {
        chunkStateRef.current.set(seq, 'playing');
        const id = Math.random().toString();
        turnTutorIdsRef.current.set(seq, id);
        setTranscripts((prev) => [...prev, { id, speaker: 'tutor', text, timestamp: new Date(), seq }]);
        const durationMs = chunkDurationRef.current.get(seq) ?? buffer.duration * 1000;
        setPlaying({ seq, text, startedAt: performance.now(), durationMs });
      }, delayMs);
      chunkTimeoutRef.current.set(seq, timeoutId);

      src.onended = () => {
        chunkStateRef.current.set(seq, 'ended');
        chunkTimeoutRef.current.delete(seq);
        playingRef.current = playingRef.current.filter((s) => s !== src);
        playedCountRef.current = computePlayedCount(chunkStateRef.current);
        if (playingRef.current.length === 0 && streamDoneRef.current) {
          finishSpeaking();
        }
      };
    },
    [finishSpeaking],
  );

  const enqueueAudio = useCallback(
    (b64: string, text: string, seq: number) => {
      queueChainRef.current = queueChainRef.current.then(() => decodeAndSchedule(b64, text, seq));
    },
    [decodeAndSchedule],
  );

  /** Retries doFetch up to 3 times (1500ms apart) while in 'reconnecting' state. Returns the response on
   * success (ok, or a non-5xx failure that the caller should handle normally), or null after 3 failures / abort. */
  const retryFetch = useCallback(async (doFetch: () => Promise<Response>): Promise<Response | null> => {
    setCallState('reconnecting');
    for (let i = 0; i < 3; i++) {
      await wait(1500, reconnectTimersRef);
      if (endingRef.current) return null;
      try {
        const res = await doFetch();
        if (res.ok || res.status < 500) return res;
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') return null;
      }
    }
    return null;
  }, []);

  const sendTurn = useCallback(
    async (text: string) => {
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      setCallState('thinking');
      streamDoneRef.current = false;
      turnStartedRef.current = false;
      chunkStateRef.current.clear();
      chunkTimeoutRef.current.clear();
      chunkDurationRef.current.clear();
      turnTutorIdsRef.current.clear();
      playedCountRef.current = 0;

      const spokenUpto = pendingSpokenUptoRef.current;
      pendingSpokenUptoRef.current = null;

      const doFetch = () =>
        fetch(`${API_BASE}/api/turn`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            text,
            call_id: callIdRef.current,
            ...(spokenUpto !== null ? { spoken_upto: spokenUpto } : {}),
          }),
          signal: ctrl.signal,
        });

      let res: Response;
      try {
        res = await doFetch();
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') return;
        const retried = await retryFetch(doFetch);
        if (!retried) {
          if (endingRef.current) return;
          setCurrentCaption('Нет связи с сервером');
          setCallState('listening');
          return;
        }
        res = retried;
        setCallState('thinking');
      }

      if (!res.ok && res.status >= 500) {
        const retried = await retryFetch(doFetch);
        if (!retried) {
          if (endingRef.current) return;
          setCurrentCaption('Нет связи с сервером');
          setCallState('listening');
          return;
        }
        res = retried;
        setCallState('thinking');
      }

      if (!res.ok || !res.body) {
        setCurrentCaption('Ошибка');
        setCallState('listening');
        return;
      }

      try {
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = '';
        let charlieText = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const blocks = buf.split('\n\n');
          buf = blocks.pop() ?? '';
          for (const block of blocks) {
            let event = 'message';
            let dataStr = '';
            for (const line of block.split('\n')) {
              if (line.startsWith('event: ')) event = line.slice(7).trim();
              else if (line.startsWith('data: ')) dataStr += line.slice(6);
            }
            if (!dataStr) continue;
            const data = JSON.parse(dataStr) as TurnEventData;

            if (event === 'emotion') {
              const nextEmotion = (data.emotion ?? 'calm') as Emotion;
              emotionRef.current = nextEmotion;
              setEmotion(nextEmotion);
              console.log('[emotion]', data.emotion);
            } else if (event === 'text') {
              charlieText += data.delta ?? '';
            } else if (event === 'audio') {
              enqueueAudio(data.b64 ?? '', data.text ?? '', data.seq ?? 0);
            } else if (event === 'fallback') {
              console.warn('fallback');
            } else if (event === 'done') {
              queueChainRef.current = queueChainRef.current.then(() => {
                streamDoneRef.current = true;
                if (playingRef.current.length === 0) {
                  if (turnStartedRef.current) {
                    finishSpeaking();
                  } else {
                    setCallState('listening');
                  }
                }
              });
            } else if (event === 'error') {
              setCurrentCaption('Ошибка');
              setCallState('listening');
            }
          }
        }
        void charlieText;
      } catch (err) {
        if (err instanceof Error && err.name !== 'AbortError') {
          console.error('turn error:', err);
          setCurrentCaption('Ошибка');
          setCallState('listening');
        }
      }
    },
    [enqueueAudio, finishSpeaking, retryFetch],
  );

  const interruptTutor = useCallback(() => {
    pendingSpokenUptoRef.current = playedCountRef.current;

    const removeIds = new Set<string>();
    for (const [seq, state] of chunkStateRef.current) {
      if (state === 'ended') continue;
      const timeoutId = chunkTimeoutRef.current.get(seq);
      if (timeoutId !== undefined) window.clearTimeout(timeoutId);
      const id = turnTutorIdsRef.current.get(seq);
      if (id) removeIds.add(id);
    }
    if (removeIds.size > 0) {
      setTranscripts((prev) => prev.filter((item) => !removeIds.has(item.id)));
    }

    abortRef.current?.abort();
    for (const src of playingRef.current) {
      try {
        src.stop();
      } catch {
        // already stopped
      }
    }
    playingRef.current = [];
    nextStartTimeRef.current = 0;
    streamDoneRef.current = false;
    setPlaying(null);
    finishSpeaking();
  }, [finishSpeaking]);

  const onSpeechStart = useCallback(() => {
    if (callStateRef.current === 'speaking') {
      interruptTutor();
    }
  }, [interruptTutor]);

  const onSpeechEnd = useCallback(() => {
    const stt = sttRef.current;
    if (!stt) return;
    void (async () => {
      const text = await stt.finalize();
      if (!text.trim()) return;
      setTranscripts((prev) => [
        ...prev,
        { id: Math.random().toString(), speaker: 'user', text, timestamp: new Date() },
      ]);
      setCurrentCaption('');
      sendTurn(text);
    })();
  }, [sendTurn]);

  const onInterim = useCallback((text: string) => {
    setCurrentCaption(text);
  }, []);

  /** Called when the STT socket closes unexpectedly, or the browser comes back online while disconnected.
   * Re-fetches a Deepgram token (keeping the same call_id) and reconnects Stt, up to 5 attempts 2s apart. */
  const handleSttClose = useCallback(() => {
    if (endingRef.current) return;
    if (callStateRef.current === 'idle') return;
    reconnectSttRef.current?.();
  }, []);

  const reconnectStt = useCallback(async () => {
    if (endingRef.current) return;
    if (reconnectingSttRef.current) return;
    if (sttRef.current?.connected) return;

    reconnectingSttRef.current = true;
    const wasSpeaking = callStateRef.current === 'speaking';
    setCallState('reconnecting');

    let success = false;
    for (let attempt = 0; attempt < 5 && !endingRef.current; attempt++) {
      if (attempt > 0) {
        await wait(2000, reconnectTimersRef);
        if (endingRef.current) break;
      }
      try {
        const res = await fetch(`${API_BASE}/api/call/start`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ call_id: callIdRef.current }),
        });
        if (!res.ok) throw new Error(`call/start failed: ${res.status}`);
        const data = (await res.json()) as CallStartResponse;
        const ctx = ctxRef.current;
        const mic = micRef.current;
        if (!ctx || !mic) throw new Error('call ended during reconnect');

        const stt = await Stt.connect(
          mic.stream,
          ctx,
          data.deepgram_token,
          {
            onInterim,
            onFinal: () => {},
            onError: (err: Error) => console.error('[stt error]', err),
            onClose: handleSttClose,
          },
          data.deepgram_auth ?? 'bearer',
        );
        sttRef.current = stt;
        if (mutedRef.current) {
          stt.mute();
        } else {
          stt.unmute();
        }
        success = true;
        break;
      } catch (err) {
        console.error('stt reconnect attempt failed:', err);
      }
    }

    reconnectingSttRef.current = false;
    if (endingRef.current) return;

    if (success) {
      setCallState(wasSpeaking ? 'speaking' : 'listening');
    } else {
      setCurrentCaption('Нет связи');
      setCallState('listening');
    }
  }, [onInterim, handleSttClose]);

  useEffect(() => {
    reconnectSttRef.current = () => {
      void reconnectStt();
    };
  }, [reconnectStt]);

  const handleOffline = useCallback(() => {
    if (endingRef.current) return;
    if (callStateRef.current === 'idle') return;
    setCallState('reconnecting');
  }, []);

  const handleOnline = useCallback(() => {
    if (endingRef.current) return;
    if (callStateRef.current === 'idle') return;
    if (!sttRef.current?.connected) {
      void reconnectStt();
    }
  }, [reconnectStt]);

  const startCall = useCallback(
    async (_scenarioId?: string) => {
      endingRef.current = false;
      setCallState('connecting');
      setTranscripts([]);
      setCurrentCaption('');
      setMicError(false);
      setPlaying(null);
      streamDoneRef.current = false;
      turnStartedRef.current = false;
      nextStartTimeRef.current = 0;
      playingRef.current = [];

      const ctx = await unlockAudio();
      ctxRef.current = ctx;

      let mic;
      try {
        mic = await openMic();
      } catch (err) {
        console.error('mic access failed:', err);
        setCurrentCaption('Нет доступа к микрофону');
        setMicError(true);
        setCallState('idle');
        return;
      }
      micRef.current = mic;

      let call_id: string;
      let token: string;
      let auth: 'bearer' | 'token';
      try {
        const res = await fetch(`${API_BASE}/api/call/start`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({}),
        });
        if (!res.ok) throw new Error(`call/start failed: ${res.status}`);
        const data = (await res.json()) as CallStartResponse;
        call_id = data.call_id;
        token = data.deepgram_token;
        auth = data.deepgram_auth ?? 'bearer';
      } catch (err) {
        console.error('call/start failed:', err);
        setCurrentCaption('Сервер недоступен');
        setCallState('idle');
        return;
      }
      callIdRef.current = call_id;

      const stt = await Stt.connect(
        mic.stream,
        ctx,
        token,
        {
          onInterim,
          onFinal: (_text: string) => {},
          onError: (err: Error) => console.error('[stt error]', err),
          onClose: handleSttClose,
        },
        auth,
      );
      sttRef.current = stt;

      const vad = await Vad.create(mic.stream, { onSpeechStart, onSpeechEnd });
      vadRef.current = vad;
      vad.start();

      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      analyserRef.current = analyser;
      const source = ctx.createMediaStreamSource(mic.stream);
      source.connect(analyser);
      updateAudioLevel();

      window.addEventListener('offline', handleOffline);
      window.addEventListener('online', handleOnline);

      setCallState('listening');
      sendTurn('');
    },
    [onInterim, onSpeechStart, onSpeechEnd, updateAudioLevel, sendTurn, handleSttClose, handleOffline, handleOnline],
  );

  const endCall = useCallback(() => {
    endingRef.current = true;
    for (const id of reconnectTimersRef.current) window.clearTimeout(id);
    reconnectTimersRef.current.clear();
    reconnectingSttRef.current = false;

    window.removeEventListener('offline', handleOffline);
    window.removeEventListener('online', handleOnline);

    abortRef.current?.abort();
    for (const src of playingRef.current) {
      try {
        src.stop();
      } catch {
        // already stopped
      }
    }
    playingRef.current = [];
    vadRef.current?.destroy();
    vadRef.current = null;
    sttRef.current?.close();
    sttRef.current = null;
    micRef.current?.stop();
    micRef.current = null;
    if (animFrameRef.current !== null) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    setCallState('idle');
    setAudioLevel(0);
    setPlaying(null);
    emotionRef.current = 'calm';
    setEmotion('calm');
    mutedRef.current = false;
    setMuted(false);
  }, [handleOffline, handleOnline]);

  const toggleMute = useCallback(() => {
    setMuted((prev) => {
      const next = !prev;
      mutedRef.current = next;
      if (next) {
        sttRef.current?.mute();
        vadRef.current?.pause();
      } else {
        vadRef.current?.start();
        if (callStateRef.current !== 'speaking') {
          sttRef.current?.unmute();
        }
      }
      return next;
    });
  }, []);

  return {
    callState,
    audioLevel,
    transcripts,
    currentCaption,
    playing,
    startCall,
    endCall,
    interruptTutor,
    emotion,
    muted,
    toggleMute,
    micError,
  };
}
