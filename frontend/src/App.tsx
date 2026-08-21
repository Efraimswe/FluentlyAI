import { useState } from 'react';
import { Phone, PhoneOff, Sparkles, MessageSquare } from './components/Icons';
import { useVoiceCall } from './hooks/useVoiceCall';
import { VoiceVisualizer } from './components/VoiceVisualizer';

export function App() {
  const {
    callState,
    audioLevel,
    currentCaption,
    startCall,
    endCall,
    interruptTutor
  } = useVoiceCall();

  const [showCaptions, setShowCaptions] = useState(true);

  const isCallActive = callState !== 'idle';

  return (
    <main className="min-h-screen w-full bg-slate-950 text-slate-100 flex flex-col justify-between items-center p-6 relative overflow-hidden select-none">
      {/* Dynamic Background Atmosphere */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        <div className={`absolute -top-40 -left-40 w-96 h-96 rounded-full blur-3xl transition-opacity duration-1000 ${
          callState === 'speaking' ? 'bg-indigo-600/25 opacity-100' :
          callState === 'thinking' ? 'bg-purple-600/25 opacity-100' :
          callState === 'listening' ? 'bg-emerald-600/20 opacity-100' : 'bg-emerald-600/10 opacity-60'
        }`} />
        <div className={`absolute -bottom-40 -right-40 w-96 h-96 rounded-full blur-3xl transition-opacity duration-1000 ${
          callState === 'speaking' ? 'bg-blue-600/20 opacity-100' :
          callState === 'thinking' ? 'bg-pink-600/20 opacity-100' :
          callState === 'listening' ? 'bg-cyan-600/20 opacity-100' : 'bg-slate-800/15 opacity-50'
        }`} />
      </div>

      {/* Header */}
      <header className="relative z-10 text-center pt-4">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-900/80 border border-slate-800 text-xs font-medium text-emerald-400 mb-2">
          <Sparkles className="w-3.5 h-3.5" />
          <span>Alex • AI English Tutor</span>
        </div>
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight bg-gradient-to-r from-slate-100 via-slate-200 to-slate-400 bg-clip-text text-transparent">
          FluentlyAI
        </h1>
        <p className="text-xs sm:text-sm text-slate-400 mt-1">
          Разговорный английский с AI в реальном времени
        </p>
      </header>

      {/* Center Voice Visualizer / Activity Orb */}
      <div className="relative z-10 flex flex-col items-center justify-center my-auto w-full max-w-md">
        <div 
          onClick={callState === 'speaking' ? interruptTutor : undefined}
          title={callState === 'speaking' ? 'Нажмите, чтобы перебить' : undefined}
          className={`relative mb-6 ${callState === 'speaking' ? 'cursor-pointer transition-transform hover:scale-105 active:scale-95' : ''}`}
        >
          <VoiceVisualizer
            state={callState === 'connecting' ? 'thinking' : callState}
            audioLevel={audioLevel}
          />

          {/* Status Chip */}
          <div className="absolute -bottom-2 left-1/2 -translate-x-1/2 whitespace-nowrap">
            <div className={`px-4 py-1.5 rounded-full text-xs font-semibold tracking-wide uppercase transition-all duration-300 backdrop-blur-md shadow-lg border ${
              callState === 'idle'
                ? 'bg-slate-900/80 border-slate-700/60 text-slate-400'
                : callState === 'connecting'
                ? 'bg-amber-500/20 border-amber-500/40 text-amber-300 animate-pulse'
                : callState === 'listening'
                ? 'bg-emerald-500/20 border-emerald-500/40 text-emerald-300'
                : callState === 'thinking'
                ? 'bg-purple-500/20 border-purple-500/40 text-purple-300 animate-pulse'
                : 'bg-blue-500/20 border-blue-500/40 text-blue-300 animate-pulse'
            }`}>
              {callState === 'idle' && 'Нажмите для начала звонка'}
              {callState === 'connecting' && 'Соединение...'}
              {callState === 'listening' && 'Слушаю вас...'}
              {callState === 'thinking' && 'Обдумываю ответ...'}
              {callState === 'speaking' && 'Alex говорит (нажмите или скажите, чтобы перебить)'}
            </div>
          </div>
        </div>

        {/* Live Subtitle / Caption Card */}
        {isCallActive && currentCaption && showCaptions && (
          <div className="w-full px-4 mt-4 animate-fade-in transition-all">
            <div className="bg-slate-900/70 border border-slate-800/80 backdrop-blur-md rounded-2xl p-3.5 text-center shadow-xl">
              <p className="text-sm sm:text-base text-slate-200 font-medium leading-relaxed">
                "{currentCaption}"
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Footer / Controls */}
      <footer className="relative z-10 w-full max-w-sm flex flex-col items-center pb-4 gap-4">
        {/* Main Action Button */}
        {!isCallActive ? (
          <button
            onClick={startCall}
            id="start-call-btn"
            className="w-full group relative flex items-center justify-center gap-3 py-4 px-8 rounded-full bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-slate-950 font-bold text-lg shadow-lg shadow-emerald-500/25 active:scale-95 transition-all duration-200 cursor-pointer"
          >
            <div className="w-8 h-8 rounded-full bg-slate-950/15 flex items-center justify-center">
              <Phone className="w-5 h-5 text-slate-950" />
            </div>
            <span>Позвонить репетитору</span>
          </button>
        ) : (
          <button
            onClick={endCall}
            id="end-call-btn"
            className="w-full group relative flex items-center justify-center gap-3 py-4 px-8 rounded-full bg-gradient-to-r from-red-600 to-rose-600 hover:from-red-500 hover:to-rose-500 text-white font-bold text-lg shadow-lg shadow-red-600/30 active:scale-95 transition-all duration-200 cursor-pointer"
          >
            <div className="w-8 h-8 rounded-full bg-white/20 flex items-center justify-center">
              <PhoneOff className="w-5 h-5 text-white" />
            </div>
            <span>Завершить звонок</span>
          </button>
        )}

        {/* Captions Toggle & Help */}
        {isCallActive && (
          <div className="flex items-center gap-4 text-xs text-slate-400">
            <button
              onClick={() => setShowCaptions(!showCaptions)}
              className="flex items-center gap-1.5 hover:text-slate-200 transition-colors py-1 px-2.5 rounded-lg hover:bg-slate-900/60 cursor-pointer"
            >
              <MessageSquare className="w-3.5 h-3.5" />
              <span>{showCaptions ? 'Скрыть субтитры' : 'Показать субтитры'}</span>
            </button>
          </div>
        )}
      </footer>
    </main>
  );
}

export default App;