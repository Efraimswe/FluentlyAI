import { useState } from 'react';
import type { CallAnalysis, TranscriptItem, Scenario } from '../types';
import { Sparkles, MessageSquare } from './Icons';

interface PostCallReportProps {
  analysis: CallAnalysis | null;
  transcripts: TranscriptItem[];
  scenario: Scenario;
  isAnalyzing: boolean;
  onRestart: () => void;
  onBackToScenarios: () => void;
}

export function PostCallReport({
  analysis,
  transcripts,
  scenario,
  isAnalyzing,
  onRestart,
  onBackToScenarios
}: PostCallReportProps) {
  const [showTranscript, setShowTranscript] = useState(false);

  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  if (isAnalyzing) {
    return (
      <div className="w-full max-w-lg mx-auto p-8 rounded-3xl bg-slate-900/90 border border-slate-800 backdrop-blur-xl shadow-2xl text-center flex flex-col items-center justify-center my-auto animate-fade-in">
        <div className="relative mb-6">
          <div className="w-16 h-16 rounded-full border-4 border-emerald-500/30 border-t-emerald-400 animate-spin" />
          <div className="absolute inset-0 flex items-center justify-center">
            <Sparkles className="w-6 h-6 text-emerald-400 animate-pulse" />
          </div>
        </div>
        <h3 className="text-xl font-bold text-slate-100 mb-2">
          Анализируем ваш разговор...
        </h3>
        <p className="text-sm text-slate-400 max-w-xs leading-relaxed">
          AI-тренер проверяет грамматику, беглость речи и собирает полезные слова.
        </p>
      </div>
    );
  }

  if (!analysis) {
    return null;
  }

  const scoreColor =
    analysis.fluency_score >= 85
      ? 'from-emerald-400 to-teal-400 text-emerald-400'
      : analysis.fluency_score >= 70
      ? 'from-sky-400 to-blue-400 text-sky-400'
      : 'from-amber-400 to-orange-400 text-amber-400';

  return (
    <div className="w-full max-w-2xl mx-auto my-auto p-4 sm:p-6 rounded-3xl bg-slate-900/90 border border-slate-800/90 backdrop-blur-xl shadow-2xl animate-fade-in overflow-y-auto max-h-[85vh]">
      {/* Header with Fluency Score */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pb-5 border-b border-slate-800">
        <div>
          <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-800/90 text-xs font-semibold text-slate-300 mb-1.5">
            <span>{scenario.icon}</span>
            <span>{scenario.title}</span>
          </div>
          <h2 className="text-xl sm:text-2xl font-extrabold text-slate-100">
            Итоги тренировки
          </h2>
        </div>

        {/* Fluency Ring Badge */}
        <div className="flex items-center gap-3 bg-slate-950/60 px-4 py-2.5 rounded-2xl border border-slate-800 shadow-inner">
          <div className="text-right">
            <div className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
              Fluency Score
            </div>
            <div className="text-xs text-slate-400">Беглость речи</div>
          </div>
          <div className={`text-3xl font-black bg-gradient-to-r ${scoreColor} bg-clip-text text-transparent`}>
            {analysis.fluency_score}%
          </div>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-3 gap-2 sm:gap-3 my-4">
        <div className="p-3 rounded-2xl bg-slate-950/40 border border-slate-800/80 text-center">
          <div className="text-xs text-slate-400 mb-0.5">Время звонка</div>
          <div className="text-base sm:text-lg font-bold text-slate-200">
            {formatDuration(analysis.duration_seconds)}
          </div>
        </div>

        <div className="p-3 rounded-2xl bg-slate-950/40 border border-slate-800/80 text-center">
          <div className="text-xs text-slate-400 mb-0.5">Вы говорили</div>
          <div className="text-base sm:text-lg font-bold text-emerald-400">
            {analysis.talk_time_percentage}%
          </div>
        </div>

        <div className="p-3 rounded-2xl bg-slate-950/40 border border-slate-800/80 text-center">
          <div className="text-xs text-slate-400 mb-0.5">Сказано фраз</div>
          <div className="text-base sm:text-lg font-bold text-slate-200">
            {analysis.user_phrases_count}
          </div>
        </div>
      </div>

      {/* Coach Summary */}
      <div className="p-4 rounded-2xl bg-emerald-950/20 border border-emerald-500/30 mb-4">
        <div className="flex items-center gap-2 text-xs font-bold text-emerald-400 uppercase tracking-wider mb-1.5">
          <Sparkles className="w-3.5 h-3.5" />
          <span>Отзыв AI-тренера</span>
        </div>
        <p className="text-xs sm:text-sm text-slate-200 leading-relaxed font-medium">
          {analysis.summary}
        </p>
      </div>

      {/* Grammar & Expressions Breakdown */}
      {analysis.corrections && analysis.corrections.length > 0 && (
        <div className="mb-4">
          <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
            <span>🎯 Разбор грамматики и выражений</span>
          </h3>
          <div className="space-y-2.5">
            {analysis.corrections.map((corr, idx) => (
              <div key={idx} className="p-3.5 rounded-2xl bg-slate-950/50 border border-slate-800/90 text-xs sm:text-sm">
                <div className="flex items-start gap-2 mb-1.5">
                  <span className="text-red-400 font-bold">❌</span>
                  <span className="text-slate-300 line-through decoration-red-400/60 font-medium">
                    "{corr.original}"
                  </span>
                </div>
                <div className="flex items-start gap-2 mb-2">
                  <span className="text-emerald-400 font-bold">✅</span>
                  <span className="text-emerald-300 font-semibold">
                    "{corr.improved}"
                  </span>
                </div>
                <div className="pl-6 text-[11px] sm:text-xs text-slate-400 bg-slate-900/60 p-2 rounded-xl border border-slate-800/50">
                  💡 {corr.explanation}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Vocabulary Bank */}
      {analysis.vocabulary && analysis.vocabulary.length > 0 && (
        <div className="mb-4">
          <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
            <span>📚 Новые слова и фразы</span>
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {analysis.vocabulary.map((vocab, idx) => (
              <div key={idx} className="p-3 rounded-2xl bg-slate-950/50 border border-slate-800/90 flex flex-col justify-between">
                <div className="flex items-baseline justify-between gap-2 mb-1">
                  <span className="text-sm font-bold text-indigo-300">{vocab.word}</span>
                  <span className="text-xs text-slate-400">{vocab.translation}</span>
                </div>
                <div className="text-[11px] text-slate-400 italic">
                  "{vocab.example}"
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Full Transcript Toggle */}
      <div className="mb-5">
        <button
          onClick={() => setShowTranscript(!showTranscript)}
          className="w-full flex items-center justify-between p-3 rounded-2xl bg-slate-950/30 hover:bg-slate-950/60 border border-slate-800 text-xs font-medium text-slate-400 hover:text-slate-200 transition-colors cursor-pointer"
        >
          <span className="flex items-center gap-2">
            <MessageSquare className="w-3.5 h-3.5" />
            <span>Полная запись разговора ({transcripts.length} реплик)</span>
          </span>
          <span>{showTranscript ? 'Свернуть ▲' : 'Развернуть ▼'}</span>
        </button>

        {showTranscript && (
          <div className="mt-2 p-3 rounded-2xl bg-slate-950/80 border border-slate-800 space-y-2 max-h-48 overflow-y-auto">
            {transcripts.map((item, idx) => (
              <div
                key={idx}
                className={`p-2 rounded-xl text-xs ${
                  item.speaker === 'user'
                    ? 'bg-slate-900 text-slate-200 ml-4 border-l-2 border-emerald-500'
                    : 'bg-indigo-950/30 text-indigo-200 mr-4 border-l-2 border-indigo-500'
                }`}
              >
                <span className="font-bold uppercase text-[10px] text-slate-400 block mb-0.5">
                  {item.speaker === 'user' ? 'Вы' : 'Alex'}
                </span>
                <span>{item.text}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Action Buttons */}
      <div className="flex flex-col sm:flex-row items-center gap-3 pt-3 border-t border-slate-800">
        <button
          onClick={onRestart}
          className="w-full sm:flex-1 py-3 px-6 rounded-2xl bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-slate-950 font-bold text-sm shadow-lg shadow-emerald-500/20 active:scale-95 transition-all cursor-pointer text-center"
        >
          Повторить тему ({scenario.title})
        </button>
        <button
          onClick={onBackToScenarios}
          className="w-full sm:flex-1 py-3 px-6 rounded-2xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold text-sm border border-slate-700 active:scale-95 transition-all cursor-pointer text-center"
        >
          Выбрать другую тему
        </button>
      </div>
    </div>
  );
}
