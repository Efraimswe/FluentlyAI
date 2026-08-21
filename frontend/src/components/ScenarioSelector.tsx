import type { Scenario } from '../types';
import { SCENARIOS } from '../data/scenarios';

interface ScenarioSelectorProps {
  selectedId: string;
  onSelect: (scenario: Scenario) => void;
  disabled?: boolean;
}

export function ScenarioSelector({ selectedId, onSelect, disabled }: ScenarioSelectorProps) {
  return (
    <div className="w-full max-w-xl px-2 my-auto">
      <div className="text-center mb-4">
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">
          Выберите тему для разговора
        </h2>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {SCENARIOS.map((scenario) => {
          const isSelected = scenario.id === selectedId;

          return (
            <button
              key={scenario.id}
              onClick={() => onSelect(scenario)}
              disabled={disabled}
              className={`group relative text-left p-4 rounded-2xl border transition-all duration-300 backdrop-blur-md cursor-pointer ${
                isSelected
                  ? 'bg-slate-900/90 border-emerald-500/80 shadow-lg shadow-emerald-500/15 ring-1 ring-emerald-500/50 scale-[1.02]'
                  : 'bg-slate-900/50 border-slate-800/80 hover:bg-slate-900/80 hover:border-slate-700/80 hover:scale-[1.01]'
              } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              {/* Header: Icon & Category */}
              <div className="flex items-center justify-between mb-2">
                <span className="text-2xl transform group-hover:scale-110 transition-transform">
                  {scenario.icon}
                </span>
                <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-slate-800/90 text-slate-400 border border-slate-700/60">
                  {scenario.level}
                </span>
              </div>

              {/* Title */}
              <h3 className={`font-bold text-sm sm:text-base mb-1 transition-colors ${
                isSelected ? 'text-emerald-400' : 'text-slate-100 group-hover:text-slate-200'
              }`}>
                {scenario.title}
              </h3>

              {/* Description */}
              <p className="text-xs text-slate-400 leading-relaxed line-clamp-2">
                {scenario.description}
              </p>

              {/* Active Selection Indicator */}
              {isSelected && (
                <div className="absolute top-3 right-3 w-2 h-2 rounded-full bg-emerald-400 shadow-sm shadow-emerald-400" />
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
