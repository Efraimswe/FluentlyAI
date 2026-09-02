import type { Emotion } from '../call/useCall';
import { EMOTION_COLORS } from './Orb';

export interface CallSummaryData {
  durationS: number;
  mood: Emotion;
  praise: string | null;
  loading: boolean;
}

const MOOD_LABELS: Record<Emotion, string> = {
  calm: 'спокойный',
  happy: 'весёлый',
  angry: 'злой',
  offended: 'обиженный',
  sad: 'грустный',
  flirty: 'флиртовал',
  ashamed: 'смущённый',
};

function formatDuration(totalSeconds: number): string {
  const mins = Math.floor(totalSeconds / 60);
  const secs = totalSeconds % 60;
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

export function CallSummary({
  data,
  onAgain,
  onClose,
}: {
  data: CallSummaryData;
  onAgain(): void;
  onClose(): void;
}) {
  return (
    <div className="fixed inset-0 z-30 bg-black/70 flex items-center justify-center px-6">
      <div className="relative w-full max-w-sm rounded-3xl bg-slate-900 border border-slate-800 p-6">
        <button
          type="button"
          onClick={onClose}
          aria-label="Закрыть"
          className="absolute top-3 right-3 w-8 h-8 rounded-full flex items-center justify-center text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors cursor-pointer text-xl leading-none"
        >
          ×
        </button>

        <h2 className="text-lg font-semibold text-slate-100 mb-5">Звонок окончен</h2>

        <div className="flex items-center justify-between py-2 border-b border-slate-800 text-sm">
          <span className="text-slate-400">Поговорили</span>
          <span className="text-slate-200 font-medium">{formatDuration(data.durationS)}</span>
        </div>

        <div className="flex items-center justify-between py-2 border-b border-slate-800 text-sm mb-4">
          <span className="text-slate-400">Чарли был</span>
          <span className="flex items-center gap-2 text-slate-200 font-medium">
            <span
              className="w-3 h-3 rounded-full shrink-0"
              style={{ backgroundColor: EMOTION_COLORS[data.mood] }}
            />
            {MOOD_LABELS[data.mood]}
          </span>
        </div>

        <div className="min-h-[3rem] mb-6">
          {data.loading ? (
            <div className="flex flex-col gap-2">
              <div className="h-4 rounded bg-slate-800 animate-pulse" />
              <div className="h-4 rounded bg-slate-800 animate-pulse w-2/3" />
            </div>
          ) : data.praise ? (
            <p className="text-sm text-slate-200 leading-relaxed">&laquo;{data.praise}&raquo;</p>
          ) : null}
        </div>

        <button
          type="button"
          onClick={onAgain}
          className="w-full py-3 rounded-full bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold cursor-pointer transition-colors"
        >
          Ещё раз
        </button>
      </div>
    </div>
  );
}
