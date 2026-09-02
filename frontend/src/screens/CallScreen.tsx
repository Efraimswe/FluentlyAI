import { useEffect, useState } from 'react';
import { useCall } from '../call/useCall';
import { useAuth } from '../auth/useAuth';
import { Orb } from '../components/Orb';
import { Chat } from '../components/Chat';
import { LiveInput } from '../components/LiveInput';
import { CallSummary } from '../components/CallSummary';
import { AuthModal } from '../components/AuthModal';
import { Paywall } from './Paywall';
import { Phone, PhoneOff, ChevronLeft } from '../components/Icons';

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) || '';

export interface CallScreenProps {
  navigate(to: string): void;
}

export function CallScreen({ navigate }: CallScreenProps) {
  const {
    callState,
    audioLevel,
    transcripts,
    currentCaption,
    playing,
    startCall,
    endCall,
    emotion,
    muted,
    toggleMute,
    micError,
    summary,
    dismissSummary,
    limits,
    limitHit,
    dismissLimit,
    refreshLimits,
  } = useCall();
  const { user, signOut } = useAuth();
  const [panelOpen, setPanelOpen] = useState(false);
  const [manualAuthOpen, setManualAuthOpen] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/api/warmup`).catch(() => {});
  }, []);

  useEffect(() => {
    const onCheckoutSuccess = () => {
      void refreshLimits();
      void dismissLimit(true);
    };
    window.addEventListener('cc:checkout-success', onCheckoutSuccess);
    return () => window.removeEventListener('cc:checkout-success', onCheckoutSuccess);
  }, [refreshLimits, dismissLimit]);

  const isIdle = callState === 'idle';
  const screen: 'idle' | 'micError' | 'call' = micError ? 'micError' : isIdle ? 'idle' : 'call';

  const statusText =
    callState === 'connecting'
      ? 'Соединяю…'
      : callState === 'listening'
        ? 'Слушаю'
        : callState === 'thinking'
          ? 'Думаю'
          : callState === 'reconnecting'
            ? 'Переподключаюсь…'
            : '';

  return (
    <div className="h-dvh w-full bg-slate-950 text-slate-100 flex flex-col overflow-hidden relative select-none">
      <button
        type="button"
        onClick={() => setPanelOpen(true)}
        aria-label="Открыть панель"
        className="absolute top-3 right-3 z-10 p-2 opacity-40 hover:opacity-70 transition-opacity cursor-pointer"
      >
        <ChevronLeft className="w-5 h-5 rotate-180" />
      </button>

      <div
        className={`absolute top-0 right-0 h-full w-64 bg-slate-900/95 backdrop-blur-md z-20 border-l border-slate-800 transition-transform duration-300 ${
          panelOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <div className="p-3 flex items-center justify-start">
          <button
            type="button"
            onClick={() => setPanelOpen(false)}
            aria-label="Закрыть панель"
            className="p-2 opacity-70 hover:opacity-100 transition-opacity cursor-pointer"
          >
            <ChevronLeft className="w-5 h-5" />
          </button>
        </div>
        <div className="px-4 text-sm text-slate-300 flex flex-col gap-1">
          <span>
            {limits === null || limits.left === null
              ? 'Осталось: ∞'
              : limits.period === 'day'
                ? `Осталось сегодня: ${limits.left} из ${limits.limit}`
                : `Осталось: ${limits.left} из ${limits.limit}`}
          </span>
          {limits ? (
            <span className="text-xs text-slate-500">
              {limits.status === 'guest' ? 'Гость' : limits.status === 'subscriber' ? 'Подписка' : 'Бесплатно'}
            </span>
          ) : null}
        </div>
      </div>

      <div className="absolute top-3 left-3 z-10 text-xs opacity-60 flex flex-col items-start gap-1">
        {isIdle ? (
          <button type="button" onClick={() => navigate('/')} className="underline cursor-pointer">
            ← Главная
          </button>
        ) : null}
        <div className="flex items-center gap-2">
          {user ? (
            <>
              <button type="button" onClick={() => navigate('/account')} className="underline cursor-pointer">
                {user.email}
              </button>
              <button type="button" onClick={() => void signOut()} className="underline cursor-pointer">
                Выйти
              </button>
            </>
          ) : (
            <button type="button" onClick={() => setManualAuthOpen(true)} className="underline cursor-pointer">
              Войти
            </button>
          )}
        </div>
      </div>

      {screen === 'idle' ? (
        <div className="flex-1 flex flex-col items-center justify-center gap-6">
          <span className="text-sm text-slate-400 lg:text-xl">Charlie</span>
          <button
            type="button"
            onClick={() => startCall()}
            aria-label="Позвонить"
            className="w-20 h-20 rounded-full bg-emerald-500 hover:bg-emerald-400 flex items-center justify-center shadow-lg shadow-emerald-500/30 active:scale-95 transition-transform cursor-pointer lg:w-24 lg:h-24"
          >
            <Phone className="w-8 h-8 text-slate-950" />
          </button>
        </div>
      ) : null}

      {screen === 'micError' ? (
        <div className="flex-1 flex items-center justify-center px-6">
          <div className="w-full max-w-sm lg:max-w-md bg-slate-900/80 border border-slate-800 rounded-2xl p-6 flex flex-col items-center gap-4 text-center">
            <h2 className="text-lg font-semibold">Нет доступа к микрофону</h2>
            <p className="text-sm text-slate-400 leading-relaxed">
              Разрешите доступ: значок замка в адресной строке → Микрофон → Разрешить.
              <br />
              На iPhone: Настройки → Safari → Микрофон.
            </p>
            <button
              type="button"
              onClick={() => startCall()}
              className="px-6 py-3 rounded-full bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold cursor-pointer"
            >
              Повторить
            </button>
          </div>
        </div>
      ) : null}

      {screen === 'call' ? (
        <>
          <div className="flex-1 flex flex-col min-h-0 lg:grid lg:grid-cols-[1fr_minmax(360px,480px)] lg:h-dvh">
            <div className="flex-1 flex flex-col min-h-0">
              <div className="pt-6 flex items-center justify-center min-h-8">
                {statusText ? (
                  <span
                    className={`px-4 py-1.5 rounded-full text-xs font-medium tracking-wide border ${
                      callState === 'reconnecting'
                        ? 'bg-amber-500/10 border-amber-500/40 text-amber-300 animate-pulse'
                        : 'bg-slate-900/80 border-slate-800 text-slate-300'
                    }`}
                  >
                    {statusText}
                  </span>
                ) : null}
              </div>

              <div className="flex-1 flex flex-col items-center justify-center gap-4 min-h-0">
                <Orb
                  emotion={emotion}
                  speaking={callState === 'speaking'}
                  thinking={callState === 'thinking' || callState === 'connecting'}
                  audioLevel={audioLevel}
                  muted={muted}
                  onToggleMute={toggleMute}
                  className="lg:w-80 lg:h-80"
                />
                <div className="contents lg:hidden">
                  <Chat items={transcripts} playing={playing} />
                </div>
                <button
                  type="button"
                  onClick={endCall}
                  aria-label="Положить трубку"
                  className="hidden lg:flex w-16 h-16 rounded-full bg-red-600 hover:bg-red-500 items-center justify-center shadow-lg shadow-red-600/30 active:scale-95 transition-transform cursor-pointer"
                >
                  <PhoneOff className="w-6 h-6 text-white" />
                </button>
              </div>
            </div>

            <div className="hidden lg:flex lg:flex-col lg:border-l lg:border-slate-800 lg:min-h-0">
              <div className="flex-1 min-h-0 lg:flex lg:flex-col lg:px-4 lg:pt-4">
                <Chat items={transcripts} playing={playing} />
              </div>
              <div className="lg:p-4">
                <LiveInput text={currentCaption} listening={callState === 'listening'} />
              </div>
            </div>
          </div>

          <div className="px-6 pt-3 pb-[env(safe-area-inset-bottom)] flex flex-col items-center gap-4 lg:hidden">
            <LiveInput text={currentCaption} listening={callState === 'listening'} />
            <button
              type="button"
              onClick={endCall}
              aria-label="Положить трубку"
              className="w-16 h-16 rounded-full bg-red-600 hover:bg-red-500 flex items-center justify-center shadow-lg shadow-red-600/30 active:scale-95 transition-transform cursor-pointer mb-4"
            >
              <PhoneOff className="w-6 h-6 text-white" />
            </button>
          </div>
        </>
      ) : null}

      {summary && isIdle && !limitHit ? (
        <CallSummary
          data={summary}
          onAgain={() => {
            dismissSummary();
            startCall();
          }}
          onClose={dismissSummary}
        />
      ) : null}

      {limitHit ? (
        limitHit.status === 'guest' || limits?.status === 'guest' ? (
          <AuthModal
            open
            reason="guest_limit"
            onClose={() => {
              dismissLimit();
              endCall();
            }}
          />
        ) : (
          <Paywall
            open
            status={limitHit.status}
            period={limits?.period ?? null}
            onClose={() => {
              dismissLimit();
              endCall();
            }}
          />
        )
      ) : null}

      <AuthModal open={manualAuthOpen} reason="manual" onClose={() => setManualAuthOpen(false)} />
    </div>
  );
}
