import { useEffect, useState } from 'react';
import { useAuth } from '../auth/useAuth';
import { authHeaders } from '../auth/supabase';
import { AuthModal } from '../components/AuthModal';
import { openCheckout } from '../payments/checkout';

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) || '';

interface Subscription {
  status: string;
  renews_at: string | null;
  trial_ends_at: string | null;
  cancelled_at: string | null;
  customer_portal_url: string | null;
}

interface MeResponse {
  status: 'guest' | 'registered' | 'trial' | 'subscriber';
  user: { id: string; email: string | null } | null;
  subscription: Subscription | null;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  const dd = d.getDate().toString().padStart(2, '0');
  const mm = (d.getMonth() + 1).toString().padStart(2, '0');
  const yyyy = d.getFullYear();
  return `${dd}.${mm}.${yyyy}`;
}

export interface AccountProps {
  navigate(to: string): void;
}

export function Account({ navigate }: AccountProps) {
  const { user, signOut } = useAuth();
  const [me, setMe] = useState<MeResponse | null>(null);
  const [manualAuthOpen, setManualAuthOpen] = useState(false);
  const [checkoutNotice] = useState(
    () => new URLSearchParams(window.location.search).get('checkout') === 'success',
  );
  const [checkoutBusy, setCheckoutBusy] = useState(false);
  const [checkoutError, setCheckoutError] = useState(false);

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

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const headers = await authHeaders();
        const res = await fetch(`${API_BASE}/api/me`, { headers });
        if (!res.ok || cancelled) return;
        const data = (await res.json()) as MeResponse;
        if (!cancelled) setMe(data);
      } catch {
        // ignore, keep previous state
      }
    };
    void load();
    const onSuccess = () => void load();
    window.addEventListener('cc:checkout-success', onSuccess);
    return () => {
      cancelled = true;
      window.removeEventListener('cc:checkout-success', onSuccess);
    };
  }, []);

  useEffect(() => {
    if (!checkoutNotice) return;
    const params = new URLSearchParams(window.location.search);
    params.delete('checkout');
    const query = params.toString();
    const newUrl = window.location.pathname + (query ? `?${query}` : '');
    window.history.replaceState({}, '', newUrl);
  }, [checkoutNotice]);

  const subscription = me?.subscription ?? null;
  const status = me?.status ?? 'guest';

  return (
    <div className="min-h-dvh w-full bg-slate-950 text-slate-100">
      <div className="max-w-md mx-auto px-5 py-8 flex flex-col gap-6 lg:max-w-xl">
        <button
          type="button"
          onClick={() => navigate('/')}
          className="text-sm text-slate-400 hover:text-slate-200 transition-colors self-start cursor-pointer"
        >
          ← Назад
        </button>

        <h1 className="text-2xl font-bold">Аккаунт</h1>

        {checkoutNotice ? (
          <div className="text-sm text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 rounded-xl px-4 py-3">
            Подписка оформлена. Чарли на связи.
          </div>
        ) : null}

        {!user ? (
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
            <p className="text-sm text-slate-300">Ты не вошёл.</p>
            <button
              type="button"
              onClick={() => setManualAuthOpen(true)}
              className="self-start px-6 py-3 rounded-full bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold cursor-pointer transition-colors lg:w-auto lg:px-8"
            >
              Войти
            </button>
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            <p className="text-sm text-slate-300">{user.email}</p>

            <div className="rounded-2xl bg-slate-900 border border-slate-800 p-4 flex flex-col gap-3 lg:p-8">
              <h2 className="text-sm font-semibold text-slate-200">Подписка</h2>

              {status === 'registered' ? (
                <>
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
                    <p className="text-sm text-slate-400">Бесплатный доступ. 10 сообщений.</p>
                    <button
                      type="button"
                      onClick={() => void handleCheckout()}
                      disabled={checkoutBusy}
                      className={`self-start px-5 py-2.5 rounded-full bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold transition-colors text-sm lg:w-auto lg:px-8 ${
                        checkoutBusy ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'
                      }`}
                    >
                      {checkoutBusy ? 'Открываю оплату…' : 'Подписаться, €9,99 в месяц'}
                    </button>
                  </div>
                  {checkoutError ? (
                    <p className="text-red-400 text-sm">Не получилось открыть оплату. Попробуй ещё раз.</p>
                  ) : null}
                </>
              ) : null}

              {status === 'trial' ? (
                <p className="text-sm text-slate-400">
                  {subscription?.trial_ends_at
                    ? `Пробный период до ${formatDate(subscription.trial_ends_at)}. Потом €9,99 в месяц.`
                    : 'Пробный период. Потом €9,99 в месяц.'}
                </p>
              ) : null}

              {status === 'subscriber' ? (
                <>
                  <p className="text-sm text-slate-400">
                    Подписка активна.
                    {subscription?.renews_at ? ` Продление ${formatDate(subscription.renews_at)}.` : ''}
                  </p>
                  {subscription?.cancelled_at ? (
                    <p className="text-sm text-amber-400">
                      Отменена, работает до{' '}
                      {formatDate(subscription.renews_at ?? subscription.cancelled_at)}
                    </p>
                  ) : null}
                </>
              ) : null}

              {(status === 'trial' || status === 'subscriber') && subscription?.customer_portal_url ? (
                <a
                  href={subscription.customer_portal_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-sm underline text-slate-300 hover:text-slate-100 self-start"
                >
                  Управлять подпиской
                </a>
              ) : null}
            </div>

            <button
              type="button"
              onClick={() => {
                void signOut().then(() => navigate('/'));
              }}
              className="self-start text-sm text-slate-400 hover:text-slate-200 underline cursor-pointer"
            >
              Выйти
            </button>
          </div>
        )}
      </div>

      <AuthModal open={manualAuthOpen} reason="manual" onClose={() => setManualAuthOpen(false)} />
    </div>
  );
}
