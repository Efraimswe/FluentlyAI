import type { Scenario } from '../types';

export const SCENARIOS: Scenario[] = [
  {
    id: 'casual',
    title: 'Casual Talk',
    category: 'Daily Life',
    icon: '☕️',
    level: 'All Levels',
    description: 'Легкий, остроумный разговор о жизни, хобби и планах.',
    color: 'from-amber-500/20 to-orange-500/20 border-amber-500/40 text-amber-300'
  },
  {
    id: 'airport',
    title: 'Airport & Customs',
    category: 'Travel',
    icon: '✈️',
    level: 'Intermediate',
    description: 'Паспортный контроль и таможня в аэропорту JFK Нью-Йорка.',
    color: 'from-sky-500/20 to-blue-500/20 border-sky-500/40 text-sky-300'
  },
  {
    id: 'job_interview',
    title: 'Job Interview',
    category: 'Career',
    icon: '💼',
    level: 'Advanced',
    description: 'Реалистичное собеседование с международным tech-рекрутером.',
    color: 'from-purple-500/20 to-indigo-500/20 border-purple-500/40 text-purple-300'
  },
  {
    id: 'restaurant',
    title: 'Cafe & Dining',
    category: 'Food',
    icon: '🍕',
    level: 'Beginner / All',
    description: 'Заказ еды, напитков и живой диалог с официантом в кафе.',
    color: 'from-emerald-500/20 to-teal-500/20 border-emerald-500/40 text-emerald-300'
  }
];
