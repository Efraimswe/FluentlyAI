import { MicVAD } from '@ricky0123/vad-web';

export interface VadEvents {
  onSpeechStart(): void;
  onSpeechEnd(): void;
}

export interface VadOptions {
  /** silence needed to end speech, default 500 */
  silenceMs?: number;
  /** min continuous speech before onSpeechStart fires (ignores coughs/"uh-huh"), default 300 */
  minSpeechMs?: number;
  /** speech probability threshold when Charlie is silent, default 0.5 */
  thresholdIdle?: number;
  /** threshold while Charlie's audio is playing (rejects speaker bleed), default 0.8 */
  thresholdWhileSpeaking?: number;
}

/**
 * We use MicVAD from @ricky0123/vad-web ONLY as the audio pipeline + Silero model
 * runner, and drive our own state machine from onFrameProcessed, because we need
 * a threshold that changes at runtime (0.5 idle vs 0.8 while Charlie is speaking),
 * a 300 ms minimum speech, a 500 ms end-of-speech silence, and a mute window for
 * echo protection.
 */
export class Vad {
  private vad: MicVAD;
  private events: VadEvents;

  private silenceMs: number;
  private minSpeechMs: number;
  private thresholdIdle: number;
  private thresholdWhileSpeaking: number;

  private charlieSpeaking = false;
  private mutedUntil = 0;

  private isSpeaking = false;
  private candidateMs = 0;
  private silenceAcc = 0;

  private constructor(vad: MicVAD, events: VadEvents, opts?: VadOptions) {
    this.vad = vad;
    this.events = events;
    this.silenceMs = opts?.silenceMs ?? 500;
    this.minSpeechMs = opts?.minSpeechMs ?? 300;
    this.thresholdIdle = opts?.thresholdIdle ?? 0.5;
    this.thresholdWhileSpeaking = opts?.thresholdWhileSpeaking ?? 0.8;
  }

  static async create(stream: MediaStream, events: VadEvents, opts?: VadOptions): Promise<Vad> {
    let instance: Vad;
    let vad: MicVAD;
    try {
      vad = await MicVAD.new({
        model: 'v5',
        baseAssetPath: '/',
        onnxWASMBasePath: '/',
        getStream: async () => stream,
        pauseStream: async () => {},
        resumeStream: async () => stream,
        onFrameProcessed: (p, frame) => instance.onFrame(p.isSpeech, frame.length),
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      throw new Error('VAD init failed: ' + message);
    }
    instance = new Vad(vad, events, opts);
    return instance;
  }

  start(): void {
    this.vad.start();
  }

  pause(): void {
    this.vad.pause();
    this.isSpeaking = false;
    this.candidateMs = 0;
    this.silenceAcc = 0;
  }

  destroy(): void {
    if (typeof this.vad.destroy === 'function') {
      this.vad.destroy();
    } else {
      this.pause();
    }
  }

  /** Call with true when Charlie's audio starts playing, false when it stops. */
  setCharlieSpeaking(v: boolean): void {
    this.charlieSpeaking = v;
  }

  /** Ignore mic frames for `ms` (echo guard right after playback starts — TASK-08 uses it). */
  muteFor(ms: number): void {
    this.mutedUntil = Date.now() + ms;
  }

  get speaking(): boolean {
    return this.isSpeaking;
  }

  get listening(): boolean {
    return this.vad.listening;
  }

  private onFrame(prob: number, samples: number): void {
    if (Date.now() < this.mutedUntil) return;

    const frameMs = samples / 16;
    const thr = this.charlieSpeaking ? this.thresholdWhileSpeaking : this.thresholdIdle;

    if (!this.isSpeaking) {
      if (prob >= thr) {
        this.candidateMs += frameMs;
        if (this.candidateMs >= this.minSpeechMs) {
          this.isSpeaking = true;
          this.silenceAcc = 0;
          this.events.onSpeechStart();
        }
      } else {
        this.candidateMs = 0;
      }
    } else {
      if (prob < thr - 0.15) {
        this.silenceAcc += frameMs;
        if (this.silenceAcc >= this.silenceMs) {
          this.isSpeaking = false;
          this.candidateMs = 0;
          this.events.onSpeechEnd();
        }
      } else {
        this.silenceAcc = 0;
      }
    }
  }
}
