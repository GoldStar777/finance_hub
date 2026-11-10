import type { RepeatEndMode, RepeatFrequency } from '../types';

export const MAX_REPEAT_OCCURRENCES = 366;

export const REPEAT_FREQUENCY_OPTIONS: Array<{
  value: RepeatFrequency;
  label: string;
  usesMonthClamp: boolean;
}> = [
  { value: 'weekly', label: 'Weekly', usesMonthClamp: false },
  { value: 'biweekly', label: 'Every two weeks', usesMonthClamp: false },
  { value: 'monthly', label: 'Monthly', usesMonthClamp: true },
  { value: 'quarterly', label: 'Quarterly', usesMonthClamp: true },
  { value: 'yearly', label: 'Yearly', usesMonthClamp: true },
];

export interface RepeatPreviewOccurrence {
  index: number;
  date: string;
  weekday: string;
  status: 'past' | 'today' | 'planned';
  isClamped: boolean;
  clampReason: string | null;
}

export interface RepeatSchedulePreview {
  dates: RepeatPreviewOccurrence[];
  totalCount: number;
  activeCount: number;
  plannedCount: number;
  hasClampedDates: boolean;
  monthEndRuleText: string | null;
  error: string | null;
}

function parseIsoDateParts(iso: string): { year: number; month: number; day: number } | null {
  if (!iso || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) return null;
  const [yStr, mStr, dStr] = iso.split('-');
  const year = Number(yStr);
  const month = Number(mStr);
  const day = Number(dStr);
  const check = new Date(Date.UTC(year, month - 1, day, 12, 0, 0));
  if (
    check.getUTCFullYear() !== year ||
    check.getUTCMonth() + 1 !== month ||
    check.getUTCDate() !== day
  ) {
    return null;
  }
  return { year, month, day };
}

function formatPartsIso(year: number, month: number, day: number): string {
  return `${String(year).padStart(4, '0')}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

export function daysInMonth(year: number, month: number): number {
  return new Date(Date.UTC(year, month, 0, 12, 0, 0)).getUTCDate();
}

export function addDaysIso(iso: string, days: number): string | null {
  const parts = parseIsoDateParts(iso);
  if (!parts) return null;
  const utc = Date.UTC(parts.year, parts.month - 1, parts.day, 12, 0, 0) + days * 86400000;
  const d = new Date(utc);
  return formatPartsIso(d.getUTCFullYear(), d.getUTCMonth() + 1, d.getUTCDate());
}

export function addMonthsClampedIso(
  anchorIso: string,
  monthsDelta: number
): { date: string; isClamped: boolean } | null {
  const parts = parseIsoDateParts(anchorIso);
  if (!parts) return null;
  const totalMonths = parts.year * 12 + (parts.month - 1) + monthsDelta;
  const targetYear = Math.floor(totalMonths / 12);
  const targetMonth = ((totalMonths % 12) + 12) % 12 + 1;
  const maxDay = daysInMonth(targetYear, targetMonth);
  const targetDay = Math.min(parts.day, maxDay);
  return {
    date: formatPartsIso(targetYear, targetMonth, targetDay),
    isClamped: targetDay < parts.day,
  };
}

export function computeRepeatOccurrenceDate(
  firstIso: string,
  frequency: RepeatFrequency,
  index: number
): { date: string; isClamped: boolean; clampReason: string | null } | null {
  if (frequency === 'weekly') {
    const d = addDaysIso(firstIso, 7 * index);
    return d ? { date: d, isClamped: false, clampReason: null } : null;
  }
  if (frequency === 'biweekly') {
    const d = addDaysIso(firstIso, 14 * index);
    return d ? { date: d, isClamped: false, clampReason: null } : null;
  }
  const monthStep = frequency === 'monthly' ? 1 : frequency === 'quarterly' ? 3 : 12;
  const res = addMonthsClampedIso(firstIso, monthStep * index);
  if (!res) return null;

  let clampReason: string | null = null;
  if (res.isClamped) {
    const parts = parseIsoDateParts(firstIso);
    if (parts && parts.month === 2 && parts.day === 29) {
      clampReason = 'Leap-day adjusted (29 -> 28 Feb)';
    } else {
      clampReason = 'Month-end adjusted';
    }
  }
  return { date: res.date, isClamped: res.isClamped, clampReason };
}

export function suggestDefaultEndDate(
  firstIso: string,
  frequency: RepeatFrequency,
  occurrences = 3
): string {
  const count = Math.max(2, occurrences);
  const res = computeRepeatOccurrenceDate(firstIso, frequency, count - 1);
  return res?.date || firstIso;
}

export function formatDateInTimeZone(dateObj: Date = new Date(), tz?: string | null): string {
  try {
    if (tz) {
      return new Intl.DateTimeFormat('en-CA', {
        timeZone: tz,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
      }).format(dateObj);
    }
  } catch {
    // Fallback below if Intl does not recognize timezone
  }
  return new Intl.DateTimeFormat('en-CA', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(dateObj);
}

function weekdayLabelForIso(iso: string): string {
  const parts = parseIsoDateParts(iso);
  if (!parts) return '';
  return new Date(Date.UTC(parts.year, parts.month - 1, parts.day, 12, 0, 0)).toLocaleDateString('en-GB', {
    weekday: 'short',
    timeZone: 'UTC',
  });
}

export function getMonthEndRuleDescription(frequency: RepeatFrequency): string | null {
  if (frequency === 'monthly' || frequency === 'quarterly' || frequency === 'yearly') {
    return 'Day-of-month rule: Each date keeps your starting day (e.g., the 31st). If a target month has fewer days (or Feb 29 in a non-leap year), that occurrence uses the last day of that month and later occurrences return to the original day.';
  }
  return null;
}

export function generateRepeatPreview(params: {
  firstDate: string;
  frequency: RepeatFrequency;
  endMode: RepeatEndMode;
  lastDate?: string;
  occurrenceCount?: number | '';
  todayLocalIso: string;
  minCount?: number;
}): RepeatSchedulePreview {
  const ruleText = getMonthEndRuleDescription(params.frequency);
  const parsedFirst = parseIsoDateParts(params.firstDate);
  if (!parsedFirst) {
    return {
      dates: [],
      totalCount: 0,
      activeCount: 0,
      plannedCount: 0,
      hasClampedDates: false,
      monthEndRuleText: ruleText,
      error: 'Please select a valid first occurrence date.',
    };
  }

  const minCount = params.minCount ?? 1;
  const rawDates: Array<{ date: string; isClamped: boolean; clampReason: string | null }> = [];

  if (params.endMode === 'count') {
    const n = Number(params.occurrenceCount);
    if (!Number.isInteger(n) || n < minCount) {
      return {
        dates: [],
        totalCount: 0,
        activeCount: 0,
        plannedCount: 0,
        hasClampedDates: false,
        monthEndRuleText: ruleText,
        error: `Number of occurrences must be an integer of at least ${minCount}.`,
      };
    }
    if (n > MAX_REPEAT_OCCURRENCES) {
      return {
        dates: [],
        totalCount: 0,
        activeCount: 0,
        plannedCount: 0,
        hasClampedDates: false,
        monthEndRuleText: ruleText,
        error: `Repeat series cannot exceed ${MAX_REPEAT_OCCURRENCES} occurrences per batch.`,
      };
    }
    for (let i = 0; i < n; i += 1) {
      const occ = computeRepeatOccurrenceDate(params.firstDate, params.frequency, i);
      if (occ) rawDates.push(occ);
    }
  } else {
    const lastIso = params.lastDate || '';
    if (!parseIsoDateParts(lastIso)) {
      return {
        dates: [],
        totalCount: 0,
        activeCount: 0,
        plannedCount: 0,
        hasClampedDates: false,
        monthEndRuleText: ruleText,
        error: 'Please select a valid last occurrence date.',
      };
    }
    if (lastIso < params.firstDate) {
      return {
        dates: [],
        totalCount: 0,
        activeCount: 0,
        plannedCount: 0,
        hasClampedDates: false,
        monthEndRuleText: ruleText,
        error: 'Last occurrence date cannot be earlier than the first occurrence date.',
      };
    }
    let idx = 0;
    while (true) {
      const occ = computeRepeatOccurrenceDate(params.firstDate, params.frequency, idx);
      if (!occ || occ.date > lastIso) break;
      if (rawDates.length >= MAX_REPEAT_OCCURRENCES) {
        return {
          dates: [],
          totalCount: 0,
          activeCount: 0,
          plannedCount: 0,
          hasClampedDates: false,
          monthEndRuleText: ruleText,
          error: `Repeat series cannot exceed ${MAX_REPEAT_OCCURRENCES} occurrences per batch. Please pick an earlier end date.`,
        };
      }
      rawDates.push(occ);
      idx += 1;
    }
  }

  let activeCount = 0;
  let plannedCount = 0;
  let hasClampedDates = false;

  const dates: RepeatPreviewOccurrence[] = rawDates.map((item, i) => {
    let status: 'past' | 'today' | 'planned' = 'past';
    if (item.date > params.todayLocalIso) {
      status = 'planned';
      plannedCount += 1;
    } else if (item.date === params.todayLocalIso) {
      status = 'today';
      activeCount += 1;
    } else {
      status = 'past';
      activeCount += 1;
    }
    if (item.isClamped) hasClampedDates = true;
    return {
      index: i + 1,
      date: item.date,
      weekday: weekdayLabelForIso(item.date),
      status,
      isClamped: item.isClamped,
      clampReason: item.clampReason,
    };
  });

  return {
    dates,
    totalCount: dates.length,
    activeCount,
    plannedCount,
    hasClampedDates,
    monthEndRuleText: ruleText,
    error: null,
  };
}

export function createSubmissionKey(): string {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return `repreq_${crypto.randomUUID()}`;
    }
  } catch {
    // fallback below
  }
  return `repreq_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 12)}`;
}
