import { useState, useRef, useCallback, useEffect } from 'react';

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

  const wsRef = useRef<WebSocket | null>(null);
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
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'user_interrupted' }));
      }
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

  // Start Call
  const startCall = useCallback(async () => {
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

      // Connect WebSocket via 127.0.0.1
      const host = window.location.hostname === 'localhost' ? '127.0.0.1' : window.location.hostname;
      const wsUrl = import.meta.env.VITE_WS_URL || `ws://${host}:8000/ws/call`;
      console.log('Connecting to WebSocket:', wsUrl);
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('WebSocket connected, sending start_call');
        setCallState('listening');
        ws.send(JSON.stringify({ type: 'start_call' }));
      };

      ws.onmessage = async (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === 'status') {
            setCallState(data.state);
          } else if (data.type === 'transcript') {
            setCurrentCaption(data.text);
            setTranscripts((prev) => [
              ...prev,
              {
                id: Math.random().toString(),
                speaker: data.speaker,
                text: data.text,
                timestamp: new Date()
              }
            ]);
          } else if (data.type === 'audio_packet') {
            await playAudioBase64(data.audio_base64, data.text || '');
          } else if (data.type === 'interrupted') {
            stopCurrentAudio();
            setCallState('listening');
            setTimeout(() => {
              resumeRecognition();
            }, 200);
          } else if (data.type === 'call_ended') {
            endCall();
          }
        } catch (e) {
          console.error('Error parsing WS message:', e);
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket Error:', error);
        setCurrentCaption('Ошибка соединения с сервером');
      };

      ws.onclose = () => {
        setCallState('idle');
      };

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
          if (finalTranscript.trim() && wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            setCallState('thinking');
            pauseRecognition(); // Mute mic while thinking and answering
            wsRef.current.send(
              JSON.stringify({
                type: 'user_speech',
                text: finalTranscript.trim()
              })
            );
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
  }, [playAudioBase64, stopCurrentAudio, updateAudioLevel, pauseRecognition, resumeRecognition]);

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

    if (wsRef.current) {
      if (wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'stop_call' }));
      }
      wsRef.current.close();
      wsRef.current = null;
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