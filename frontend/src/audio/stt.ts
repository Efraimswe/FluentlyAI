export interface SttEvents {
  /** partial transcript of the utterance in progress (whole current utterance text, not a delta) */
  onInterim(text: string): void;
  /** called by finalize(): the full utterance text collected since the last finalize */
  onFinal(text: string): void;
  onError(err: Error): void;
  onClose(): void;
}

const DEEPGRAM_WS_URL =
  'wss://api.deepgram.com/v1/listen?model=nova-3&encoding=linear16&sample_rate=16000&channels=1&interim_results=true&smart_format=true&punctuate=true&language=en&endpointing=false';

const CONNECT_TIMEOUT_MS = 10_000;
const FINALIZE_TIMEOUT_MS = 800;
const KEEPALIVE_INTERVAL_MS = 5_000;

const WORKLET_SRC = `
class Pcm16CaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = new Float32Array(0);
  }

  process(inputs) {
    const input = inputs[0];
    const channel = input && input[0];
    if (channel && channel.length) {
      const merged = new Float32Array(this._buffer.length + channel.length);
      merged.set(this._buffer, 0);
      merged.set(channel, this._buffer.length);
      this._buffer = merged;
    }

    const chunkSamples = Math.floor(sampleRate * 0.1);
    if (chunkSamples > 0 && this._buffer.length >= chunkSamples) {
      const src = this._buffer.subarray(0, chunkSamples);
      this._buffer = this._buffer.slice(chunkSamples);

      const ratio = sampleRate / 16000;
      const outLen = Math.floor(src.length / ratio);
      const int16 = new Int16Array(outLen);
      for (let i = 0; i < outLen; i++) {
        const start = i * ratio;
        const end = (i + 1) * ratio;
        let sum = 0;
        let count = 0;
        for (let j = Math.floor(start); j < end && j < src.length; j++) {
          sum += src[j];
          count++;
        }
        const avg = count > 0 ? sum / count : 0;
        const s = Math.max(-1, Math.min(1, avg));
        int16[i] = s * 0x7fff;
      }
      this.port.postMessage(int16.buffer, [int16.buffer]);
    }

    return true;
  }
}

registerProcessor('pcm16-capture', Pcm16CaptureProcessor);
`;

const registeredContexts = new WeakSet<AudioContext>();

async function ensureWorkletRegistered(ctx: AudioContext): Promise<void> {
  if (registeredContexts.has(ctx)) return;
  const blob = new Blob([WORKLET_SRC], { type: 'application/javascript' });
  const workletUrl = URL.createObjectURL(blob);
  try {
    await ctx.audioWorklet.addModule(workletUrl);
  } finally {
    URL.revokeObjectURL(workletUrl);
  }
  registeredContexts.add(ctx);
}

export class Stt {
  private ws: WebSocket;
  private node: AudioWorkletNode;
  private source: MediaStreamAudioSourceNode;
  private events: SttEvents;
  private muted = false;
  private finals: string[] = [];
  private interim = '';
  private keepAliveTimer: ReturnType<typeof setInterval> | null = null;
  private pendingFinalize: { resolve: (text: string) => void; timer: ReturnType<typeof setTimeout> } | null = null;

  private constructor(ws: WebSocket, node: AudioWorkletNode, source: MediaStreamAudioSourceNode, events: SttEvents) {
    this.ws = ws;
    this.node = node;
    this.source = source;
    this.events = events;
  }

  static async connect(
    stream: MediaStream,
    ctx: AudioContext,
    token: string,
    events: SttEvents,
    auth: 'bearer' | 'token' = 'bearer',
  ): Promise<Stt> {
    await ensureWorkletRegistered(ctx);

    const ws = new WebSocket(DEEPGRAM_WS_URL, [auth, token]);
    ws.binaryType = 'arraybuffer';

    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => {
        ws.close();
        reject(new Error('Deepgram connect timeout'));
      }, CONNECT_TIMEOUT_MS);
      ws.onopen = () => {
        clearTimeout(timer);
        resolve();
      };
      ws.onerror = () => {
        clearTimeout(timer);
        reject(new Error('Deepgram connection error'));
      };
    });

    const source = ctx.createMediaStreamSource(stream);
    const node = new AudioWorkletNode(ctx, 'pcm16-capture');
    source.connect(node);

    const stt = new Stt(ws, node, source, events);
    stt.attachHandlers();
    stt.startKeepAlive();
    return stt;
  }

  private attachHandlers(): void {
    this.ws.onmessage = (ev: MessageEvent) => {
      let msg: any;
      try {
        msg = JSON.parse(ev.data as string);
      } catch {
        return;
      }
      if (msg.type !== 'Results') return;

      const t: string = msg.channel?.alternatives?.[0]?.transcript ?? '';
      if (t) {
        if (msg.is_final) {
          this.finals.push(t);
          this.interim = '';
        } else {
          this.interim = t;
        }
      }
      this.events.onInterim([...this.finals, this.interim].filter(Boolean).join(' ').trim());

      if (msg.from_finalize === true && this.pendingFinalize) {
        this.resolveFinalize();
      }
    };

    this.ws.onerror = () => {
      this.events.onError(new Error('Deepgram WebSocket error'));
    };

    this.ws.onclose = () => {
      this.stopKeepAlive();
      this.events.onClose();
    };

    this.node.port.onmessage = (e: MessageEvent) => {
      if (!this.muted && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(e.data);
      }
    };
  }

  private startKeepAlive(): void {
    this.keepAliveTimer = setInterval(() => {
      if (this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: 'KeepAlive' }));
      }
    }, KEEPALIVE_INTERVAL_MS);
  }

  private stopKeepAlive(): void {
    if (this.keepAliveTimer !== null) {
      clearInterval(this.keepAliveTimer);
      this.keepAliveTimer = null;
    }
  }

  private resolveFinalize(): void {
    if (!this.pendingFinalize) return;
    const text = [...this.finals, this.interim].join(' ').trim();
    clearTimeout(this.pendingFinalize.timer);
    const resolve = this.pendingFinalize.resolve;
    this.pendingFinalize = null;
    this.finals = [];
    this.interim = '';
    this.events.onFinal(text);
    resolve(text);
  }

  /** stop sending audio (keeps socket open) */
  mute(): void {
    this.muted = true;
  }

  unmute(): void {
    this.muted = false;
  }

  /** Ask Deepgram to flush; resolves with the final text (also fires onFinal). Waits <= 800 ms for the finalize result. */
  finalize(): Promise<string> {
    return new Promise<string>((resolve) => {
      const timer = setTimeout(() => this.resolveFinalize(), FINALIZE_TIMEOUT_MS);
      this.pendingFinalize = { resolve, timer };
      if (this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: 'Finalize' }));
      }
    });
  }

  close(): void {
    this.stopKeepAlive();
    if (this.pendingFinalize) {
      clearTimeout(this.pendingFinalize.timer);
      this.pendingFinalize = null;
    }
    if (this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'CloseStream' }));
    }
    this.node.port.onmessage = null;
    this.node.disconnect();
    this.source.disconnect();
    this.ws.close();
  }

  get connected(): boolean {
    return this.ws.readyState === WebSocket.OPEN;
  }
}
