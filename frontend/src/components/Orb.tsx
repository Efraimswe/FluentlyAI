import { Mic, MicOff } from './Icons';
import type { Emotion } from '../call/useCall';

export interface OrbProps {
  emotion: Emotion;
  speaking: boolean;
  thinking: boolean;
  audioLevel: number;
  muted: boolean;
  onToggleMute(): void;
}

interface EmotionStyle {
  core: string;
  glow: string;
  duration: string;
}

const EMOTION_STYLES: Record<Emotion, EmotionStyle> = {
  calm: { core: '#7dd3fc', glow: '#38bdf8', duration: '2.4s' },
  happy: { core: '#fbbf24', glow: '#f59e0b', duration: '1.2s' },
  angry: { core: '#ef4444', glow: '#dc2626', duration: '0.5s' },
  offended: { core: '#6d28d9', glow: '#4c1d95', duration: '3.2s' },
  sad: { core: '#64748b', glow: '#475569', duration: '5s' },
  flirty: { core: '#f472b6', glow: '#ec4899', duration: '1.8s' },
  ashamed: { core: '#e9a3b5', glow: '#d48aa0', duration: '2.8s' },
};

export function Orb({ emotion, speaking, thinking, audioLevel, muted, onToggleMute }: OrbProps) {
  const style = EMOTION_STYLES[emotion];
  const levelScale = 1 + audioLevel * 0.15;

  return (
    <div className="relative w-56 h-56 sm:w-64 sm:h-64 shrink-0">
      <div
        className={`orb-pulse-layer absolute inset-0 rounded-full ${
          speaking ? `orb-pulse-${emotion}` : thinking ? 'orb-breathe' : ''
        }`}
        style={{
          animationDuration: speaking || thinking ? style.duration : undefined,
          background: `radial-gradient(circle at 35% 30%, ${style.core}, ${style.glow})`,
          boxShadow: `0 0 60px 10px ${style.glow}66`,
          transition: 'background 600ms ease, box-shadow 600ms ease',
        }}
      >
        <div
          className="absolute inset-0 rounded-full"
          style={{
            transform: `scale(${speaking ? levelScale : 1})`,
            transition: 'transform 100ms linear',
          }}
        />
      </div>

      {speaking && emotion === 'angry' && (
        <div
          className="orb-ring-expand absolute inset-0 rounded-full pointer-events-none"
          style={{ boxShadow: `0 0 0 2px ${style.glow}` }}
        />
      )}

      <button
        type="button"
        onClick={onToggleMute}
        aria-label="Микрофон"
        aria-pressed={muted}
        className={`absolute bottom-0 right-0 translate-x-1/4 translate-y-1/4 w-11 h-11 rounded-full flex items-center justify-center border shadow-lg transition-colors cursor-pointer ${
          muted
            ? 'bg-red-500/90 border-red-400 text-white'
            : 'bg-slate-900/90 border-slate-700 text-slate-100'
        }`}
      >
        {muted ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
      </button>
    </div>
  );
}
