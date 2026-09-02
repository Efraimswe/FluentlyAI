import { useEffect, useRef, useState } from 'react';
import type { Playing, TranscriptItem } from '../call/useCall';

export interface ChatProps {
  items: TranscriptItem[];
  playing: Playing | null;
}

interface ShimmerTextProps {
  text: string;
  startedAt: number;
  durationMs: number;
}

function ShimmerText({ text, startedAt, durationMs }: ShimmerTextProps) {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    let frameId: number;
    const tick = () => {
      const p = Math.min(1, (performance.now() - startedAt) / durationMs);
      setProgress(p);
      if (p < 1) frameId = requestAnimationFrame(tick);
    };
    frameId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frameId);
  }, [startedAt, durationMs]);

  const revealPercent = 100 - progress * 100;

  return (
    <span className="relative inline-block">
      <span className="text-slate-300">{text}</span>
      <span
        className="absolute inset-0 text-white"
        style={{ clipPath: `inset(0 ${revealPercent}% 0 0)` }}
      >
        {text}
      </span>
    </span>
  );
}

export function Chat({ items, playing }: ChatProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [items]);

  return (
    <div ref={scrollRef} className="w-full flex-1 min-h-0 overflow-y-auto flex flex-col gap-2 px-1">
      {items.map((item) => {
        const isUser = item.speaker === 'user';
        const isPlaying = playing !== null && item.seq === playing.seq;
        return (
          <div key={item.id} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`text-sm max-w-[85%] px-3 py-2 ${
                isUser
                  ? 'bg-slate-800 rounded-2xl rounded-br-sm'
                  : 'bg-slate-900 border border-slate-800 rounded-2xl rounded-bl-sm'
              }`}
            >
              {isPlaying ? (
                <ShimmerText text={item.text} startedAt={playing.startedAt} durationMs={playing.durationMs} />
              ) : (
                <span className={isUser ? undefined : 'text-slate-200'}>{item.text}</span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
