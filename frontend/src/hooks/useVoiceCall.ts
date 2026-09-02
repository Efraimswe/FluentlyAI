import { useState, useRef, useCallback, useEffect } from 'react';

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) || '';

export type CallState = 'idle' | 'connecting' | 'listening' | 'thinking' | 'speaking';

export interface TranscriptItem {
  id: string;
  speaker: 'user' | 'tutor';
  text: string;
  timestamp: Date;
}

export function useVoiceCall() {
  const [callState, setCallState] = useState<CallState>('idle');
  const [audioLevel, setAudioLevel] = useState<number>(0);
  const [transcripts, setTranscripts] = useState<TranscriptItem[]>([]);
  const [currentCaption, setCurrentCaption] = useState<string>('');

  const abortRef = useRef<AbortController | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const recognitionRef = useRef<any>(null);
  const currentAudioSourceRef = useRef<AudioBufferSourceNode | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const callStateRef = useRef<CallState>('idle');
  const activeAudioElementRef = useRef<HTMLAudioElement | null>(null);
  const isRecognitionActiveRef = useRef<boolean>(false);

  useEffect(() => {
    callStateRef.current = callState;
  }, [callState]);

  // Audio level polling for visualizer
  const updateAudioLevel = useCallback(() => {
    if (!analyserRef.current) return;
    const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount);
    analyserRef.current.getByteFrequencyData(dataArray);

    let sum = 0;
    for (let i = 0; i < dataArray.length; i++) {
      sum += dataArray[i];
    }
    const average = sum / dataArray.length;
    const normalized = Math.min(1, average / 128);
    setAudioLevel(normalized);

    animFrameRef.current = requestAnimationFrame(updateAudioLevel);
  }, []);

  // Safely stop recognition
  const pauseRecognition = useCallback(() => {
    if (recognitionRef.current && isRecognitionActiveRef.current) {
      try {
        isRecognitionActiveRef.current = false;
        recognitionRef.current.abort();
      } catch (e) {}
    }
  }, []);

  // Safely resume recognition
  const resumeRecognition = useCallback(() => {
    if (recognitionRef.current && !isRecognitionActiveRef.current && callStateRef.current !== 'idle') {
      try {
        isRecognitionActiveRef.current = true;
        recognitionRef.current.start();
      } catch (e) {
        // Recognition might already be running
      }
    }
  }, []);

  // Stop current playing audio
  const stopCurrentAudio = useCallback(() => {
    if (currentAudioSourceRef.current) {
      try {
        currentAudioSourceRef.current.stop();
      } catch (e) {}
      currentAudioSourceRef.current = null;
    }
    if (activeAudioElementRef.current) {
      try {
        activeAudioElementRef.current.pause();
        activeAudioElementRef.current.currentTime = 0;
      } catch (e) {}
      activeAudioElementRef.current = null;
    }
    if (window.speechSynthesis && window.speechSynthesis.speaking) {
      window.speechSynthesis.cancel();
    }
  }, []);

  // Manual or Click-to-Interrupt (Barge-in)
  const interruptTutor = useCallback(() => {
    if (callStateRef.current === 'speaking' || callStateRef.current === 'thinking') {
      console.log('>>> Interrupting tutor');
      stopCurrentAudio();
      setCallState('listening');
      abortRef.current?.abort();
      setTimeout(() => {
        resumeRecognition();
      }, 100);
    }
  }, [stopCurrentAudio, resumeRecognition]);

  // Play incoming audio with 100% Anti-Echo Microphone Muting
  const playAudioBase64 = useCallback(async (base64Data: string, textFallback: string) => {
    try {
      // 1. Instantly mute mic recognition so speakers cannot feed back into microphone
      pauseRecognition();
      stopCurrentAudio();

      if (!audioContextRef.current) {
        const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
        audioContextRef.current = new AudioCtx();
      }

      if (audioContextRef.current.state === 'suspended') {
        await audioContextRef.current.resume();
      }

      const binaryString = atob(base64Data);
      const len = binaryString.length;
      const bytes = new Uint8Array(len);
      for (let i = 0; i < len; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      const audioBuffer = await audioContextRef.current.decodeAudioData(bytes.buffer.slice(0));
      const source = audioContextRef.current.createBufferSource();
      source.buffer = audioBuffer;

      // Play tutor audio directly through speakers
      source.connect(audioContextRef.current.destination);

      // Route to analyser ONLY for visualizer waves (never connect analyser to destination to prevent mic loopback echo!)
      if (analyserRef.current) {
        source.connect(analyserRef.current);
      }

      // When tutor finishes speaking:
      source.onended = () => {
        if (callStateRef.current === 'speaking') {
          setCallState('listening');
          // Wait 400ms for room echo to decay, then resume microphone!
          setTimeout(() => {
            resumeRecognition();
          }, 400);
        }
      };

      currentAudioSourceRef.current = source;
      setCallState('speaking');
      source.start();
    } catch (err) {
      console.warn('AudioContext decode failed, falling back to HTML5 audio/speechSynthesis:', err);
      try {
        const audio = new Audio(`data:audio/mp3;base64,${base64Data}`);
        activeAudioElementRef.current = audio;
        audio.onended = () => {
          if (callStateRef.current === 'speaking') {
            setCallState('listening');
            setTimeout(() => {
              resumeRecognition();
            }, 400);
          }
        };
        setCallState('speaking');
        await audio.play();
      } catch (audioErr) {
        console.warn('HTML5 audio failed, falling back to SpeechSynthesis:', audioErr);
        if ('speechSynthesis' in window) {
          const utter = new SpeechSynthesisUtterance(textFallback);
          utter.lang = 'en-US';
          utter.onend = () => {
            if (callStateRef.current === 'speaking') {
              setCallState('listening');
              setTimeout(() => {
                resumeRecognition();
              }, 400);
            }
          };
          setCallState('speaking');
          window.speechSynthesis.speak(utter);
        } else {
          setCallState('listening');
          resumeRecognition();
        }
      }
    }
  }, [stopCurrentAudio, pauseRecognition, resumeRecognition]);

  // Send user text to backend, stream SSE reply
  const sendTurn = useCallback(async (text: string) => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setCallState('thinking');
    try {
      const res = await fetch(`${API_BASE}/api/turn`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
        signal: ctrl.signal
      });
      if (!res.ok || !res.body) throw new Error(`turn failed: ${res.status}`);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      let tutorText = '';
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
          const data = JSON.parse(dataStr);
          if (event === 'text') {
            tutorText += data.delta ?? '';
            setCurrentCaption(tutorText);
          } else if (event === 'audio') {
            setTranscripts((prev) => [
              ...prev,
              {
                id: Math.random().toString(),
                speaker: 'tutor',
                text: data.text ?? '',
                timestamp: new Date()
              }
            ]);
            await playAudioBase64(data.b64 ?? '', data.text ?? '');
          } else if (event === 'done') {
            if (callStateRef.current !== 'speaking') {
              setCallState('listening');
              resumeRecognition();
            }
          }
        }
      }
    } catch (err: any) {
      if (err?.name !== 'AbortError') {
        console.error('turn error:', err);
        setCurrentCaption('Ошибка соединения с сервером');
        setCallState('listening');
        resumeRecognition();
      }
    }
  }, [playAudioBase64, resumeRecognition]);

  // Start Call
  const startCall = useCallback(async (_scenarioId: string = 'casual') => {
    try {
      setCallState('connecting');
      setTranscripts([]);
      setCurrentCaption('');

      // Init Audio Context & Analyser
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      const audioCtx = new AudioCtx();
      if (audioCtx.state === 'suspended') {
        await audioCtx.resume();
      }
      audioContextRef.current = audioCtx;

      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      analyserRef.current = analyser;

      // Request Mic Access with Hardware Echo Cancellation
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true
          }
        });
        micStreamRef.current = stream;
        const source = audioCtx.createMediaStreamSource(stream);
        source.connect(analyser);
      } catch (micErr) {
        console.warn('Mic access issue:', micErr);
      }

      updateAudioLevel();

      // Warm up backend and get greeting via SSE
      fetch(`${API_BASE}/api/warmup`).catch(() => {});
      setCallState('listening');
      sendTurn('');

      // Initialize Web Speech Recognition
      const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      if (SpeechRecognition) {
        const recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = 'en-US';

        recognition.onresult = (event: any) => {
          // If tutor is speaking, discard any residual audio immediately
          if (callStateRef.current === 'speaking' || !isRecognitionActiveRef.current) {
            return;
          }

          let interimTranscript = '';
          let finalTranscript = '';

          for (let i = event.resultIndex; i < event.results.length; ++i) {
            if (event.results[i].isFinal) {
              finalTranscript += event.results[i][0].transcript;
            } else {
              interimTranscript += event.results[i][0].transcript;
            }
          }

          const rawText = finalTranscript.trim() || interimTranscript.trim();
          if (!rawText) return;

          setCurrentCaption(rawText);

          // If final phrase is ready, send to backend
          if (finalTranscript.trim()) {
            const userText = finalTranscript.trim();
            setTranscripts((prev) => [
              ...prev,
              {
                id: Math.random().toString(),
                speaker: 'user',
                text: userText,
                timestamp: new Date()
              }
            ]);
            pauseRecognition(); // Mute mic while thinking and answering
            sendTurn(userText);
          }
        };

        recognition.onerror = (e: any) => {
          console.warn('SpeechRecognition warning:', e);
        };

        recognition.onend = () => {
          // Restart only if supposed to be active
          if (callStateRef.current === 'listening' && isRecognitionActiveRef.current) {
            try {
              recognition.start();
            } catch (err) {}
          }
        };

        try {
          isRecognitionActiveRef.current = true;
          recognition.start();
          recognitionRef.current = recognition;
        } catch (e) {
          console.warn('Recognition start error:', e);
        }
      }
    } catch (err) {
      console.error('Failed to start call:', err);
      endCall();
    }
  }, [playAudioBase64, stopCurrentAudio, updateAudioLevel, pauseRecognition, resumeRecognition, sendTurn]);

  // End Call
  const endCall = useCallback(() => {
    stopCurrentAudio();
    pauseRecognition();

    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch (e) {}
      recognitionRef.current = null;
    }

    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }

    if (micStreamRef.current) {
      micStreamRef.current.getTracks().forEach((track) => track.stop());
      micStreamRef.current = null;
    }

    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }

    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }

    setCallState('idle');
    setAudioLevel(0);
  }, [stopCurrentAudio, pauseRecognition]);

  return {
    callState,
    audioLevel,
    transcripts,
    currentCaption,
    startCall,
    endCall,
    interruptTutor
  };
}