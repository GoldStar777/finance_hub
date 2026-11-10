import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { getActiveProfileId } from '../api/client';

export interface ActiveSharedFilterChip {
  key: string;
  type: 'account' | 'category' | 'offset' | 'custom_date';
  id?: number | string;
  label: string;
  color?: string;
}

export function normalizeSharedPreset(preset: string): string {
  const clean = (preset || 'month').trim().toLowerCase();
  if (clean === '1y') return 'year';
  return clean;
}

export function getDefaultIntervalForPreset(preset: string): string {
  const p = normalizeSharedPreset(preset);
  if (p === 'day' || p === 'week' || p === 'month') return 'day';
  if (p === '3m') return 'week';
  if (p === '5y') return 'quarter';
  return 'month';
}

export const SHARED_PRESET_OPTIONS = [
  { value: 'day', label: 'Day' },
  { value: 'week', label: 'Week' },
  { value: 'month', label: 'Month' },
  { value: '3m', label: '3M' },
  { value: '6m', label: '6M' },
  { value: 'year', label: '1Y' },
  { value: '5y', label: '5Y' },
  { value: 'all', label: 'All' },
  { value: 'custom', label: 'Custom' },
] as const;

export const SHARED_INTERVAL_OPTIONS = [
  { value: 'day', label: 'Day' },
  { value: 'week', label: 'Week' },
  { value: 'month', label: 'Month' },
  { value: 'quarter', label: 'Quarter' },
  { value: 'year', label: 'Year' },
] as const;

export const useSharedFiltersStore = defineStore('sharedFilters', () => {
  // Shared Filter State
  const datePreset = ref<string>('month');
  const dateOffset = ref<number>(0);
  const customStartDate = ref<string>('');
  const customEndDate = ref<string>('');
  const interval = ref<string>(''); // Group-by interval: 'day' | 'week' | 'month' | 'quarter' | 'year' | ''
  const accountIds = ref<(number | string)[]>([]);
  const categoryIds = ref<(number | string)[]>([]);

  const SHARED_FILTERS_KEY_PREFIX = 'finance_hub_shared_filters_';

  function getStorageKey(profileId?: string | null): string {
    const pid = profileId || getActiveProfileId() || 'default';
    return `${SHARED_FILTERS_KEY_PREFIX}${pid}`;
  }

  function loadPreferences(profileId?: string | null): boolean {
    if (typeof window === 'undefined' || !window.localStorage) return false;
    try {
      const raw = window.localStorage.getItem(getStorageKey(profileId));
      if (!raw) return false;
      const p = JSON.parse(raw);
      if (p && typeof p === 'object') {
        if (typeof p.datePreset === 'string') datePreset.value = normalizeSharedPreset(p.datePreset);
        if (typeof p.dateOffset === 'number') dateOffset.value = Math.min(0, p.dateOffset);
        if (typeof p.customStartDate === 'string') customStartDate.value = p.customStartDate;
        if (typeof p.customEndDate === 'string') customEndDate.value = p.customEndDate;
        if (typeof p.interval === 'string') interval.value = p.interval;
        if (Array.isArray(p.accountIds)) {
          accountIds.value = p.accountIds
            .map((v: any) => (v === 'unassigned' ? 'unassigned' : Number(v)))
            .filter((v: number | string) => v === 'unassigned' || !isNaN(v as number));
        }
        if (Array.isArray(p.categoryIds)) {
          categoryIds.value = Array.from(
            new Set(
              p.categoryIds
                .map((v: any) => (v === 'uncategorized' || v === 'uncategorised' || v === '0' || v === 0 ? 0 : Number(v)))
                .filter((v: number) => !isNaN(v))
            )
          );
        }
        return true;
      }
    } catch (err) {
      console.warn('Failed to parse saved shared filter preferences:', err);
    }
    return false;
  }

  function savePreferences(profileId?: string | null) {
    if (typeof window === 'undefined' || !window.localStorage) return;
    try {
      const p = {
        datePreset: datePreset.value,
        dateOffset: dateOffset.value,
        customStartDate: customStartDate.value,
        customEndDate: customEndDate.value,
        interval: interval.value,
        accountIds: accountIds.value,
        categoryIds: categoryIds.value,
      };
      window.localStorage.setItem(getStorageKey(profileId), JSON.stringify(p));
    } catch (err) {
      console.warn('Failed to save shared filter preferences:', err);
    }
  }

  function switchProfile(newProfileId: string) {
    // Reset to defaults then load from that profile's storage
    datePreset.value = 'month';
    dateOffset.value = 0;
    customStartDate.value = '';
    customEndDate.value = '';
    interval.value = '';
    accountIds.value = [];
    categoryIds.value = [];
    loadPreferences(newProfileId);
  }

  /**
   * Evaluates incoming route query parameters.
   * Explicit valid query parameters override stored preferences for bookmarkable URLs & drilldowns.
   * If the route query has no filter parameters (e.g. ordinary navigation from navbar), stored shared preferences are preserved.
   */
  function applyFromRoute(routeQuery: Record<string, any>) {
    let hasExplicitParams = false;

    // Check date preset
    const presetVal = routeQuery.preset || routeQuery.date_preset;
    if (presetVal && typeof presetVal === 'string') {
      datePreset.value = normalizeSharedPreset(presetVal);
      if (routeQuery.offset === undefined && routeQuery.date_offset === undefined) {
        dateOffset.value = 0;
      }
      hasExplicitParams = true;
    }

    // Check custom dates
    const hasStart = Boolean(routeQuery.start_date && typeof routeQuery.start_date === 'string');
    const hasEnd = Boolean(routeQuery.end_date && typeof routeQuery.end_date === 'string');
    if (hasStart) {
      customStartDate.value = String(routeQuery.start_date);
      hasExplicitParams = true;
    }
    if (hasEnd) {
      customEndDate.value = String(routeQuery.end_date);
      hasExplicitParams = true;
    }
    if ((hasStart || hasEnd) && !presetVal) {
      datePreset.value = 'custom';
      dateOffset.value = 0;
    }

    // Check interval
    if (routeQuery.interval && typeof routeQuery.interval === 'string') {
      interval.value = routeQuery.interval;
      hasExplicitParams = true;
    }

    // Check offset
    const offsetVal = routeQuery.offset !== undefined ? routeQuery.offset : routeQuery.date_offset;
    if (offsetVal !== undefined && offsetVal !== '') {
      const off = parseInt(String(offsetVal), 10);
      if (!isNaN(off)) {
        dateOffset.value = Math.min(0, off);
        hasExplicitParams = true;
      }
    }

    // Check accounts
    if (routeQuery.account_ids && typeof routeQuery.account_ids === 'string') {
      accountIds.value = routeQuery.account_ids
        .split(',')
        .map((s: string) => s.trim())
        .filter(Boolean)
        .map((v: string) => (v.toLowerCase() === 'unassigned' ? 'unassigned' : parseInt(v, 10)))
        .filter((v: number | string) => v === 'unassigned' || !isNaN(v as number));
      hasExplicitParams = true;
    } else if (routeQuery.unassigned_only === 'true' || routeQuery.account_id === 'unassigned') {
      accountIds.value = ['unassigned'];
      hasExplicitParams = true;
    } else if (routeQuery.account_id !== undefined && routeQuery.account_id !== '') {
      const aid = parseInt(String(routeQuery.account_id), 10);
      if (!isNaN(aid) && aid > 0) {
        accountIds.value = [aid];
        hasExplicitParams = true;
      }
    }

    // Check categories
    if (routeQuery.category_ids && typeof routeQuery.category_ids === 'string') {
      categoryIds.value = Array.from(
        new Set(
          routeQuery.category_ids
            .split(',')
            .map((s: string) => s.trim().toLowerCase())
            .filter(Boolean)
            .map((v: string) => (v === '0' || v === 'uncategorized' || v === 'uncategorised' ? 0 : parseInt(v, 10)))
            .filter((v: number) => !isNaN(v))
        )
      );
      hasExplicitParams = true;
    } else if (
      routeQuery.uncategorized_only === 'true' ||
      routeQuery.category_id === '0' ||
      routeQuery.category_id === 'uncategorized' ||
      routeQuery.category_id === 'uncategorised' ||
      routeQuery.category_id === 0
    ) {
      categoryIds.value = [0];
      hasExplicitParams = true;
    } else if (routeQuery.category_id !== undefined && routeQuery.category_id !== '') {
      const cid = parseInt(String(routeQuery.category_id), 10);
      if (!isNaN(cid) && cid > 0) {
        categoryIds.value = [cid];
        hasExplicitParams = true;
      }
    }

    if (hasExplicitParams) {
      savePreferences();
    } else {
      loadPreferences();
    }
  }

  // State mutations
  function setPreset(newPreset: string) {
    const normalized = normalizeSharedPreset(newPreset);
    datePreset.value = normalized;
    dateOffset.value = 0; // Reset offset on preset change
    if (normalized !== 'custom') {
      customStartDate.value = '';
      customEndDate.value = '';
      interval.value = ''; // Auto-adjust interval to preset default
    }
    savePreferences();
  }

  function navigateOffset(delta: number) {
    dateOffset.value = Math.min(0, dateOffset.value + delta);
    savePreferences();
  }

  function resetOffset() {
    dateOffset.value = 0;
    savePreferences();
  }

  function setInterval(newInterval: string) {
    interval.value = newInterval;
    savePreferences();
  }

  function setCustomDates(start: string, end: string) {
    datePreset.value = 'custom';
    dateOffset.value = 0;
    customStartDate.value = start;
    customEndDate.value = end;
    interval.value = '';
    savePreferences();
  }

  function clearCustomDates() {
    if (datePreset.value === 'custom') {
      datePreset.value = 'month';
    }
    customStartDate.value = '';
    customEndDate.value = '';
    dateOffset.value = 0;
    savePreferences();
  }

  function toggleAccount(id: number | string) {
    const cur = [...accountIds.value];
    const idx = cur.indexOf(id);
    if (idx >= 0) {
      cur.splice(idx, 1);
    } else {
      cur.push(id);
    }
    accountIds.value = cur;
    savePreferences();
  }

  function selectAllAccounts(all: (number | string)[]) {
    accountIds.value = Array.from(new Set(all));
    savePreferences();
  }

  function clearAccounts() {
    accountIds.value = [];
    savePreferences();
  }

  function toggleCategory(id: number | string) {
    const cur = [...categoryIds.value];
    const normalized = id === 'uncategorized' || id === 'uncategorised' || id === '0' ? 0 : id;
    const idx = cur.indexOf(normalized);
    if (idx >= 0) {
      cur.splice(idx, 1);
    } else {
      cur.push(normalized);
    }
    categoryIds.value = cur;
    savePreferences();
  }

  function selectAllCategories(all: (number | string)[]) {
    categoryIds.value = Array.from(
      new Set(all.map(v => (v === 'uncategorized' || v === 'uncategorised' || v === '0' ? 0 : v)))
    );
    savePreferences();
  }

  function clearCategories() {
    categoryIds.value = [];
    savePreferences();
  }

  function resetAllFilters() {
    if (datePreset.value === 'custom') {
      datePreset.value = 'month';
    }
    dateOffset.value = 0;
    customStartDate.value = '';
    customEndDate.value = '';
    accountIds.value = [];
    categoryIds.value = [];
    savePreferences();
  }

  // Active numeric arrays for API / analysis compatibility
  const numericAccountIds = computed<number[]>(() => {
    return accountIds.value.filter((v): v is number => typeof v === 'number');
  });

  const numericCategoryIds = computed<number[]>(() => {
    return categoryIds.value.map(v => (v === 'uncategorized' || v === 'uncategorised' ? 0 : Number(v))).filter(v => !isNaN(v));
  });

  const isUnassignedAccountSelected = computed<boolean>(() => {
    return accountIds.value.includes('unassigned');
  });

  const isUncategorizedSelected = computed<boolean>(() => {
    return categoryIds.value.includes(0) || categoryIds.value.includes('uncategorized') || categoryIds.value.includes('uncategorised');
  });

  return {
    datePreset,
    dateOffset,
    customStartDate,
    customEndDate,
    interval,
    accountIds,
    categoryIds,
    numericAccountIds,
    numericCategoryIds,
    isUnassignedAccountSelected,
    isUncategorizedSelected,
    loadPreferences,
    savePreferences,
    switchProfile,
    applyFromRoute,
    setPreset,
    navigateOffset,
    resetOffset,
    setInterval,
    setCustomDates,
    clearCustomDates,
    toggleAccount,
    selectAllAccounts,
    clearAccounts,
    toggleCategory,
    selectAllCategories,
    clearCategories,
    resetAllFilters,
  };
});
