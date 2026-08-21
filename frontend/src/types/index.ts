export interface Scenario {
  id: string;
  title: string;
  category: string;
  icon: string;
  level: string;
  description: string;
  color: string;
}

export interface TranscriptItem {
  id: string;
  speaker: 'user' | 'tutor';
  text: string;
  timestamp: Date;
}

export type CallState = 'idle' | 'connecting' | 'listening' | 'thinking' | 'speaking';

export interface CorrectionItem {
  original: string;
  improved: string;
  explanation: string;
}

export interface VocabularyItem {
  word: string;
  translation: string;
  example: string;
}

export interface CallAnalysis {
  fluency_score: number;
  summary: string;
  talk_time_percentage: number;
  user_phrases_count: number;
  duration_seconds: number;
  corrections: CorrectionItem[];
  vocabulary: VocabularyItem[];
}
