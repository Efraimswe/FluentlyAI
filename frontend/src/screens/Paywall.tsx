import { useState } from 'react';
import { openCheckout } from '../payments/checkout';

export interface PaywallProps {
  open: boolean;
  status: string;
  period: 'total' | 'day' | null;
  onClose(): void;
}

export function Paywall({ open, status, period, onClose }: PaywallProps) {
  const [checkoutBusy, setCheckoutBusy] = useState(false);
  const [checkoutError, setCheckoutError] = useState(false);

  if (!open) return null;

  const isDayLimit = period === 'day' || status === 'trial' || status === 'subscriber';

  const handleCheckout = async () => {
    if (checkoutBusy) return;
    setCheckoutBusy(true);
    setCheckoutError(false);
    try {
      await openCheckout();
    } catch (err) {
      console.error('checkout failed:', err);
      setCheckoutError(true);
      setCheckoutBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-30 bg-black/70 flex items-center justify-center px-6">
      <div className="relative w-full max-w-sm rounded-3xl bg-slate-900 border border-slate-800 p-6 lg:max-w-md lg:p-8">
        <button
          type="button"
          onClick={onClose}
          aria-label="Закрыть"
          className="absolute top-3 right-3 w-8 h-8 rounded-full flex items-center justify-center text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors cursor-pointer text-xl leading-none"
        >
          ×
        </button>

        {isDayLimit ? (
          <>
            <h2 className="text-lg font-semibold text-slate-100 mb-2">На сегодня всё</h2>
            <p className="text-sm text-slate-400 mb-6 leading-relaxed">
              Сто сообщений за день. Чарли тоже устаёт. Завтра он снова на связи.
            </p>
            <button
              type="button"
              onClick={onClose}
              className="w-full py-3 rounded-full bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold cursor-pointer transition-colors"
            >
              Ок
            </button>
          </>
        ) : (
          <>
            <h2 className="text-lg font-semibold text-slate-100 mb-2">10 бесплатных закончились</h2>
            <p className="text-sm text-slate-400 mb-6 leading-relaxed">
              Чарли перезвонит за €9,99 в месяц. Сто сообщений в день. Первые 3 дня бесплатно,
              потом спишется, отменить можно в любой момент.
            </p>
            <button
              type="button"
              onClick={() => void handleCheckout()}
              disabled={checkoutBusy}
              className={`w-full py-3 rounded-full bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold transition-colors ${
                checkoutBusy ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'
              }`}
            >
              {checkoutBusy ? 'Открываю оплату…' : 'Попробовать 3 дня'}
            </button>
            {checkoutError ? (
              <p className="text-red-400 text-sm mt-2">Не получилось открыть оплату. Попробуй ещё раз.</p>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
