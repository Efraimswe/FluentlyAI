import { useEffect } from 'react';
import { EMOTION_COLORS } from '../components/Orb';
import type { Emotion } from '../call/useCall';

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) || '';

export interface LandingProps {
  navigate(to: string): void;
}

interface CharlieLine {
  emotion: Emotion;
  text: string;
}

const CHARLIE_LINES: CharlieLine[] = [
  { emotion: 'happy', text: 'Dude, finally! I was literally about to text you.' },
  { emotion: 'sad', text: 'Three people showed up Friday. Three. One of them was the sound guy.' },
  { emotion: 'angry', text: 'Look, I was in the middle of a sentence. Kinda important one.' },
];

const HOW_IT_WORKS: string[] = [
  'Жмёшь «Позвонить». Чарли берёт трубку первым, у него всегда что-то случилось за день.',
  'Говоришь как умеешь. Он не поправляет, а переспрашивает, если не понял. Как живой.',
  'Перебивай, спорь, спрашивай про его музыку. Он обижается, если отвечать «ок».',
];

function CallButton({ onClick }: { onClick(): void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full py-4 rounded-full bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-lg cursor-pointer transition-colors lg:w-auto lg:px-10"
    >
      Позвонить Чарли
    </button>
  );
}

export function Landing({ navigate }: LandingProps) {
  useEffect(() => {
    fetch(`${API_BASE}/api/warmup`).catch(() => {});
  }, []);

  return (
    <div className="min-h-dvh w-full bg-slate-950 text-slate-100">
      <div className="max-w-md mx-auto px-5 py-10 flex flex-col gap-10 lg:max-w-6xl lg:px-10">
        <div className="flex flex-col gap-10 lg:grid lg:grid-cols-2 lg:gap-16 lg:items-center lg:min-h-[70vh]">
          <section className="flex flex-col gap-4">
            <span className="text-xs tracking-wide opacity-60">Charlie Calls</span>
            <h1 className="text-3xl font-bold leading-tight lg:text-5xl">
              Чарли — бармен из Остина. Ему можно позвонить.
            </h1>
            <p className="text-slate-300 lg:text-lg">
              Он не учитель. Он просто говорит по-английски, потому что другого не знает. Ты
              звонишь, он берёт трубку, вы болтаете. Английский подтягивается сам.
            </p>
            <CallButton onClick={() => navigate('/call')} />
            <span className="text-xs text-slate-400">
              Бесплатно и без регистрации. Первые 2 реплики.
            </span>
          </section>

          <section className="flex flex-col gap-3">
            <span className="text-xs opacity-60">Так он разговаривает</span>
            {CHARLIE_LINES.map((line, i) => (
              <div key={i} className="flex justify-start">
                <div className="flex items-start gap-2 max-w-[90%] px-3 py-2 bg-slate-900 border border-slate-800 rounded-2xl rounded-bl-sm">
                  <span
                    className="mt-1.5 w-[10px] h-[10px] rounded-full shrink-0"
                    style={{ backgroundColor: EMOTION_COLORS[line.emotion] }}
                  />
                  <span className="text-sm text-slate-200">{line.text}</span>
                </div>
              </div>
            ))}
          </section>
        </div>

        <section className="flex flex-col gap-4">
          <h2 className="text-lg font-semibold">Как это работает</h2>
          <ol className="flex flex-col gap-3 lg:grid lg:grid-cols-3 lg:gap-8">
            {HOW_IT_WORKS.map((step, i) => (
              <li
                key={i}
                className="flex items-start gap-3 lg:rounded-2xl lg:border lg:border-slate-800 lg:bg-slate-900/60 lg:p-6"
              >
                <span className="shrink-0 w-6 h-6 rounded-full bg-slate-800 flex items-center justify-center text-xs font-medium">
                  {i + 1}
                </span>
                <span className="text-sm text-slate-300 leading-relaxed">{step}</span>
              </li>
            ))}
          </ol>
        </section>

        <div className="flex flex-col gap-10 lg:mx-auto lg:max-w-2xl lg:text-center">
          <section className="flex flex-col gap-3">
            <h2 className="text-lg font-semibold">Сколько стоит</h2>
            <p className="text-sm text-slate-300 leading-relaxed">
              Первые 2 реплики бесплатно, без регистрации. Зарегистрировался — ещё 10.
            </p>
            <p className="text-sm text-slate-300 leading-relaxed">
              Дальше €9,99 в месяц, 100 сообщений в день. Первые 3 дня бесплатно, карта нужна.
            </p>
          </section>

          <CallButton onClick={() => navigate('/call')} />
        </div>

        <footer className="text-xs opacity-50 pb-[env(safe-area-inset-bottom)] flex items-center gap-2 flex-wrap lg:flex lg:justify-between">
          <span>Charlie Calls</span>
          <span>·</span>
          <a href="/privacy.html" className="underline">
            Политика конфиденциальности
          </a>
          <span>·</span>
          <button type="button" onClick={() => navigate('/account')} className="underline cursor-pointer">
            Аккаунт
          </button>
        </footer>
      </div>
    </div>
  );
}
