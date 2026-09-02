import { useState, type FormEvent } from 'react';
import { useAuth } from '../auth/useAuth';

export interface AuthModalProps {
  open: boolean;
  reason: 'guest_limit' | 'manual';
  onClose(): void;
}

const TITLES: Record<AuthModalProps['reason'], { title: string; subtitle: string }> = {
  guest_limit: {
    title: 'Чарли хочет продолжить',
    subtitle: 'Зарегистрируйся, и он тебе перезвонит. 10 сообщений бесплатно.',
  },
  manual: {
    title: 'Войти',
    subtitle: 'Чтобы Чарли тебя помнил.',
  },
};

function GoogleIcon() {
  return (
    <svg viewBox="0 0 48 48" className="w-5 h-5" aria-hidden="true">
      <path
        fill="#FFC107"
        d="M43.611 20.083H42V20H24v8h11.303c-1.649 4.657-6.08 8-11.303 8-6.627 0-12-5.373-12-12s5.373-12 12-12c3.059 0 5.842 1.154 7.961 3.039l5.657-5.657C34.046 6.053 29.268 4 24 4 12.955 4 4 12.955 4 24s8.955 20 20 20 20-8.955 20-20c0-1.341-.138-2.65-.389-3.917z"
      />
      <path
        fill="#FF3D00"
        d="M6.306 14.691l6.571 4.819C14.655 15.108 18.961 12 24 12c3.059 0 5.842 1.154 7.961 3.039l5.657-5.657C34.046 6.053 29.268 4 24 4 16.318 4 9.656 8.337 6.306 14.691z"
      />
      <path
        fill="#4CAF50"
        d="M24 44c5.166 0 9.86-1.977 13.409-5.192l-6.19-5.238C29.211 35.091 26.715 36 24 36c-5.202 0-9.619-3.317-11.283-7.946l-6.522 5.025C9.505 39.556 16.227 44 24 44z"
      />
      <path
        fill="#1976D2"
        d="M43.611 20.083H42V20H24v8h11.303a12.04 12.04 0 0 1-4.087 5.571l.003-.002 6.19 5.238C36.971 39.205 44 34 44 24c0-1.341-.138-2.65-.389-3.917z"
      />
    </svg>
  );
}

export function AuthModal({ open, reason, onClose }: AuthModalProps) {
  const { signInWithGoogle, signInWithEmail } = useAuth();
  const [email, setEmail] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  if (!open) return null;

  const copy = TITLES[reason];

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    const { error: submitError } = await signInWithEmail(email);
    setSubmitting(false);
    if (submitError) {
      setError(submitError);
      return;
    }
    setSent(true);
  }

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

        <h2 className="text-lg font-semibold text-slate-100 mb-2">{copy.title}</h2>
        <p className="text-sm text-slate-400 mb-5">{copy.subtitle}</p>

        <button
          type="button"
          onClick={() => void signInWithGoogle()}
          className="w-full py-3 rounded-full bg-white hover:bg-slate-100 text-slate-900 font-semibold cursor-pointer transition-colors flex items-center justify-center gap-2"
        >
          <GoogleIcon />
          Продолжить с Google
        </button>

        <div className="flex items-center gap-3 my-5">
          <div className="h-px flex-1 bg-slate-800" />
          <span className="text-xs text-slate-500">или</span>
          <div className="h-px flex-1 bg-slate-800" />
        </div>

        {sent ? (
          <p className="text-sm text-slate-200 leading-relaxed">
            Ссылка ушла на {email}. Открой письмо и нажми войти.
          </p>
        ) : (
          <form onSubmit={handleSubmit}>
            <input
              type="email"
              required
              placeholder="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full py-3 px-4 rounded-full bg-slate-800 border border-slate-700 text-slate-100 placeholder:text-slate-500 mb-3 outline-none focus:border-slate-500"
            />
            <button
              type="submit"
              disabled={submitting}
              className="w-full py-3 rounded-full bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold cursor-pointer transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
            >
              Прислать ссылку
            </button>
            {error ? <p className="text-red-400 text-sm mt-2">{error}</p> : null}
          </form>
        )}
      </div>
    </div>
  );
}
