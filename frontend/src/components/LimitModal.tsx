export interface LimitModalProps {
  period: 'total' | 'day' | null;
  onClose(): void;
}

export function LimitModal({ period, onClose }: LimitModalProps) {
  const title = period === 'day' ? 'На сегодня всё' : 'Бесплатные сообщения закончились';

  return (
    <div className="fixed inset-0 z-30 bg-black/70 flex items-center justify-center px-6">
      <div className="relative w-full max-w-sm rounded-3xl bg-slate-900 border border-slate-800 p-6">
        <h2 className="text-lg font-semibold text-slate-100 mb-2">{title}</h2>
        <p className="text-sm text-slate-400 mb-6 leading-relaxed">
          Подписка появится совсем скоро — Чарли тебе позвонит.
        </p>
        <button
          type="button"
          onClick={onClose}
          className="w-full py-3 rounded-full bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold cursor-pointer transition-colors"
        >
          Ок
        </button>
      </div>
    </div>
  );
}
