let ctx: AudioContext | null = null;

/** Returns the shared AudioContext (creates it on first call). */
export function getAudioContext(): AudioContext {
  if (!ctx) {
    const Ctor =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    ctx = new Ctor();
  }
  return ctx;
}

/**
 * Must be called from a user gesture (the "Call" tap). Creates/resumes the shared
 * AudioContext and plays a 1-sample silent buffer so iOS Safari unlocks audio output.
 */
export async function unlockAudio(): Promise<AudioContext> {
  const c = getAudioContext();
  if (c.state === 'suspended') await c.resume();
  const buf = c.createBuffer(1, 1, c.sampleRate);
  const src = c.createBufferSource();
  src.buffer = buf;
  src.connect(c.destination);
  src.start(0);
  return c;
}

export interface MicHandle {
  stream: MediaStream;
  /** Stops all tracks. */
  stop(): void;
}

/**
 * Opens the microphone with hardware echo cancellation + noise suppression + AGC.
 * Throws the original DOMException (NotAllowedError / NotFoundError) — callers show the "no mic access" screen.
 */
export async function openMic(): Promise<MicHandle> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });
  return {
    stream,
    stop() {
      for (const track of stream.getTracks()) track.stop();
    },
  };
}
