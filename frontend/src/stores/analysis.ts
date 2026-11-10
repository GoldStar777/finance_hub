import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type {
  ComprehensiveAnalysisResponse,
  AnalysisQueryParams,
  AnalysisExportReportType,
  AnalysisExportFormat,
} from '../types';
import { api, getActiveProfileId } from '../api/client';
import { useSharedFiltersStore } from './filters';

export type AnalysisSection = 'overview' | 'spending' | 'networth' | 'investments';
export type SpendingGroupingMode = 'category' | 'nature';
export type SpendingChartType = 'stacked_bar' | 'line';

export interface ActiveFilterChip {
  key: string;
  type: 'account' | 'category' | 'offset';
  id?: number;
  label: string;
  color?: string;
}

export const useAnalysisStore = defineStore('analysis', () => {
  const sharedFilters = useSharedFiltersStore();

  const data = ref<ComprehensiveAnalysisResponse | null>(null);
  const isLoading = ref(false);
  const isExporting = ref(false);
  const error = ref<string | null>(null);

  // Active section
  const activeSection = ref<AnalysisSection>('overview');

  // Filter controls synchronized with useSharedFiltersStore
  const selectedPreset = computed<string>({
    get: () => sharedFilters.datePreset,
    set: (val: string) => sharedFilters.setPreset(val),
  });
  const selectedOffset = computed<number>({
    get: () => sharedFilters.dateOffset,
    set: (val: number) => {
      sharedFilters.dateOffset = val;
      sharedFilters.savePreferences();
    },
  });
  const customStartDate = computed<string>({
    get: () => sharedFilters.customStartDate,
    set: (val: string) => {
      sharedFilters.customStartDate = val;
      sharedFilters.savePreferences();
    },
  });
  const customEndDate = computed<string>({
    get: () => sharedFilters.customEndDate,
    set: (val: string) => {
      sharedFilters.customEndDate = val;
      sharedFilters.savePreferences();
    },
  });
  const selectedInterval = computed<string>({
    get: () => sharedFilters.interval,
    set: (val: string) => sharedFilters.setInterval(val),
  });
  const selectedCurrency = ref<string>('');

  // Multi-select Account & Category Filters (category ID 0 = Uncategorised)
  const selectedAccountIds = computed<number[]>({
    get: () => sharedFilters.numericAccountIds,
    set: (val: number[]) => sharedFilters.selectAllAccounts(val),
  });
  const selectedCategoryIds = computed<number[]>({
    get: () => sharedFilters.numericCategoryIds,
    set: (val: number[]) => sharedFilters.selectAllCategories(val),
  });

  // Balances chart account selection (Requirement 5)
  const selectedBalanceAccountIds = ref<number[]>([]);

  // Backwards-compatible single-select getters
  const selectedAccountId = computed<number | null>(() =>
    sharedFilters.numericAccountIds.length === 1 ? sharedFilters.numericAccountIds[0] : null
  );
  const selectedCategoryId = computed<number | null>(() =>
    sharedFilters.numericCategoryIds.length === 1 ? sharedFilters.numericCategoryIds[0] : null
  );

  // Spending visualization sub-controls & category focus (Requirement 4)
  const spendingGroupingMode = ref<SpendingGroupingMode>('category');
  const spendingChartType = ref<SpendingChartType>('stacked_bar');
  const spendingFocusCategoryId = ref<number | null>(null); // null = Total Spend (All categories)
  const selectedCategoryLineIds = ref<number[]>([]);
  const showTotalSpendLine = ref<boolean>(true);
  const showNatureLines = ref<{ fixed: boolean; variable: boolean; unclassified: boolean }>({
    fixed: true,
    variable: true,
    unclassified: false,
  });

  const ANALYSIS_PREFS_KEY_PREFIX = 'finance_hub_analysis_prefs_';

  function getStorageKey(profileId?: string | null): string {
    const pid = profileId || getActiveProfileId() || 'default';
    return `${ANALYSIS_PREFS_KEY_PREFIX}${pid}`;
  }

  function loadSavedPreferences(profileId?: string | null): boolean {
    sharedFilters.loadPreferences(profileId);
    if (typeof window === 'undefined' || !window.localStorage) return false;
    try {
      const raw = window.localStorage.getItem(getStorageKey(profileId));
      if (!raw) return false;
      const p = JSON.parse(raw);
      if (p && typeof p === 'object') {
        if (typeof p.currency === 'string') selectedCurrency.value = p.currency;
        if (Array.isArray(p.balanceAccountIds)) selectedBalanceAccountIds.value = p.balanceAccountIds.map(Number);
        if (p.spendingFocusCategoryId !== undefined) spendingFocusCategoryId.value = p.spendingFocusCategoryId;
        if (['overview', 'spending', 'networth', 'investments'].includes(p.activeSection)) {
          activeSection.value = p.activeSection;
        }
        if (['category', 'nature'].includes(p.spendingGroupingMode)) {
          spendingGroupingMode.value = p.spendingGroupingMode;
        }
        if (['stacked_bar', 'line'].includes(p.spendingChartType)) {
          spendingChartType.value = p.spendingChartType;
        }
        return true;
      }
    } catch (err) {
      console.warn('Failed to parse saved analysis preferences:', err);
    }
    return false;
  }

  function savePreferences(profileId?: string | null) {
    sharedFilters.savePreferences(profileId);
    if (typeof window === 'undefined' || !window.localStorage) return;
    try {
      const p = {
        currency: selectedCurrency.value,
        balanceAccountIds: selectedBalanceAccountIds.value,
        spendingFocusCategoryId: spendingFocusCategoryId.value,
        activeSection: activeSection.value,
        spendingGroupingMode: spendingGroupingMode.value,
        spendingChartType: spendingChartType.value,
      };
      window.localStorage.setItem(getStorageKey(profileId), JSON.stringify(p));
    } catch (err) {
      console.warn('Failed to save analysis preferences:', err);
    }
  }

  function initFromRouteOrPreferences(routeQuery: Record<string, any>) {
    // 1. Delegate shared filters to sharedFilters store (precedence: explicit params > stored)
    sharedFilters.applyFromRoute(routeQuery);

    // 2. Load analysis-specific preferences
    loadSavedPreferences();

    // 3. Explicit route query overrides for analysis-specific state
    if (routeQuery.section && ['overview', 'spending', 'networth', 'investments'].includes(routeQuery.section)) {
      activeSection.value = routeQuery.section as AnalysisSection;
    }
    if (routeQuery.currency && typeof routeQuery.currency === 'string') {
      selectedCurrency.value = routeQuery.currency;
    }

    savePreferences();
  }

  function buildQueryParams(overrides?: Partial<AnalysisQueryParams>): AnalysisQueryParams {
    const effPreset = overrides?.preset ?? sharedFilters.datePreset;
    const effStart = effPreset === 'custom' ? (overrides?.start_date ?? sharedFilters.customStartDate) : undefined;
    const effEnd = effPreset === 'custom' ? (overrides?.end_date ?? sharedFilters.customEndDate) : undefined;
    const effAccounts = overrides?.account_ids ?? (sharedFilters.numericAccountIds.length > 0 ? [...sharedFilters.numericAccountIds] : undefined);
    const effCategories = overrides?.category_ids ?? (sharedFilters.numericCategoryIds.length > 0 ? [...sharedFilters.numericCategoryIds] : undefined);
    const effOffset = overrides?.offset !== undefined ? overrides.offset : sharedFilters.dateOffset;
    const effInterval = overrides?.interval ?? sharedFilters.interval;

    return {
      preset: effPreset,
      start_date: effStart,
      end_date: effEnd,
      interval: effInterval || undefined,
      currency: (overrides?.currency ?? selectedCurrency.value) || undefined,
      account_ids: effAccounts,
      account_id:
        overrides?.account_id !== undefined
          ? overrides.account_id
          : effAccounts?.length === 1
          ? effAccounts[0]
          : undefined,
      category_ids: effCategories,
      category_id:
        overrides?.category_id !== undefined
          ? overrides.category_id
          : effCategories?.length === 1
          ? effCategories[0]
          : undefined,
      offset: effOffset,
    };
  }

  async function loadAnalysis(overrides?: Partial<AnalysisQueryParams>) {
    const reqProfile = getActiveProfileId();
    if (data.value === null && !overrides) {
      loadSavedPreferences(reqProfile);
    }
    isLoading.value = true;
    error.value = null;
    try {
      const params = buildQueryParams(overrides);
      const res = await api.getAnalysis(params);
      if (reqProfile !== getActiveProfileId()) return;
      data.value = res;

      // Sync currency with resolved server value
      selectedCurrency.value = res.currency;

      savePreferences(reqProfile);

      // Initialize default top 3 spending categories for line chart if empty
      if (selectedCategoryLineIds.value.length === 0 && res.categories && res.categories.length > 0) {
        selectedCategoryLineIds.value = res.categories
          .filter(c => c.category_id !== null && c.total_pence > 0)
          .slice(0, 3)
          .map(c => c.category_id as number);
      }
    } catch (err: any) {
      error.value = err.message || 'Failed to load analysis data';
      console.error('Analysis error:', err);
    } finally {
      isLoading.value = false;
    }
  }

  async function exportReport(reportType: AnalysisExportReportType, format: AnalysisExportFormat) {
    isExporting.value = true;
    try {
      const params = buildQueryParams();
      await api.downloadAnalysisExport(reportType, format, params);
    } catch (err: any) {
      error.value = err.message || `Failed to export ${reportType} as ${format.toUpperCase()}`;
      console.error('Export error:', err);
    } finally {
      isExporting.value = false;
    }
  }

  function setPreset(preset: string) {
    sharedFilters.setPreset(preset);
    savePreferences();
    if (preset !== 'custom') {
      loadAnalysis({ preset, offset: 0, interval: undefined });
    }
  }

  function navigatePeriod(delta: number) {
    if (!data.value) return;
    if (delta < 0 && !data.value.range_info.can_navigate_previous) return;
    if (delta > 0 && !data.value.range_info.can_navigate_next) return;
    const nextOffset = Math.min(0, sharedFilters.dateOffset + delta);
    sharedFilters.navigateOffset(delta);
    savePreferences();
    loadAnalysis({ offset: nextOffset });
  }

  function resetPeriodOffset() {
    if (sharedFilters.dateOffset === 0) return;
    sharedFilters.resetOffset();
    savePreferences();
    loadAnalysis({ offset: 0 });
  }

  function setCustomRange(startDate: string, endDate: string) {
    sharedFilters.setCustomDates(startDate, endDate);
    savePreferences();
    loadAnalysis({ preset: 'custom', start_date: startDate, end_date: endDate, offset: 0, interval: undefined });
  }

  function setInterval(interval: string) {
    sharedFilters.setInterval(interval);
    savePreferences();
    loadAnalysis({ interval });
  }

  function setCurrency(currency: string) {
    selectedCurrency.value = currency;
    sharedFilters.clearAccounts(); // Reset account filter when switching currency
    savePreferences();
    loadAnalysis({ currency, account_ids: undefined, account_id: null });
  }

  function setAccount(accountId: number | null) {
    sharedFilters.selectAllAccounts(accountId !== null ? [accountId] : []);
    savePreferences();
    loadAnalysis();
  }

  function setAccounts(accountIds: number[]) {
    sharedFilters.selectAllAccounts(accountIds);
    savePreferences();
    loadAnalysis();
  }

  function toggleAccountFilter(accountId: number) {
    sharedFilters.toggleAccount(accountId);
    savePreferences();
    loadAnalysis();
  }

  function removeAccountFilter(accountId: number) {
    sharedFilters.toggleAccount(accountId);
    savePreferences();
    loadAnalysis();
  }

  function clearAccountFilters() {
    if (sharedFilters.accountIds.length === 0) return;
    sharedFilters.clearAccounts();
    savePreferences();
    loadAnalysis();
  }

  function setCategory(categoryId: number | null) {
    sharedFilters.selectAllCategories(categoryId !== null ? [categoryId] : []);
    savePreferences();
    loadAnalysis();
  }

  function setCategories(categoryIds: number[]) {
    sharedFilters.selectAllCategories(categoryIds);
    savePreferences();
    loadAnalysis();
  }

  function toggleCategoryFilter(categoryId: number) {
    sharedFilters.toggleCategory(categoryId);
    savePreferences();
    loadAnalysis();
  }

  function removeCategoryFilter(categoryId: number) {
    sharedFilters.toggleCategory(categoryId);
    savePreferences();
    loadAnalysis();
  }

  function clearCategoryFilters() {
    if (sharedFilters.categoryIds.length === 0) return;
    sharedFilters.clearCategories();
    savePreferences();
    loadAnalysis();
  }

  function resetAllFilters() {
    sharedFilters.resetAllFilters();
    savePreferences();
    loadAnalysis({ account_ids: undefined, account_id: null, category_ids: undefined, category_id: null, offset: 0 });
  }

  function toggleCategoryLine(categoryId: number) {
    const idx = selectedCategoryLineIds.value.indexOf(categoryId);
    if (idx >= 0) {
      selectedCategoryLineIds.value.splice(idx, 1);
    } else {
      selectedCategoryLineIds.value.push(categoryId);
    }
    savePreferences();
  }

  function setSection(section: AnalysisSection | string) {
    if (['overview', 'spending', 'networth', 'investments'].includes(section)) {
      activeSection.value = section as AnalysisSection;
      savePreferences();
    }
  }

  function toggleBalanceAccount(accountId: number) {
    const idx = selectedBalanceAccountIds.value.indexOf(accountId);
    if (idx >= 0) {
      selectedBalanceAccountIds.value.splice(idx, 1);
    } else {
      selectedBalanceAccountIds.value.push(accountId);
    }
    savePreferences();
  }

  function setBalanceAccounts(accountIds: number[]) {
    selectedBalanceAccountIds.value = Array.from(new Set(accountIds));
    savePreferences();
  }

  function setSpendingFocusCategory(catId: number | null) {
    spendingFocusCategoryId.value = catId;
    savePreferences();
  }

  const availableAccountsForCurrency = computed(() => {
    if (!data.value) return [];
    return data.value.available_accounts.filter(a => a.currency === selectedCurrency.value);
  });

  const hasActiveFilters = computed(() => {
    return (
      sharedFilters.accountIds.length > 0 ||
      sharedFilters.categoryIds.length > 0 ||
      sharedFilters.dateOffset !== 0
    );
  });

  const activeFilterChips = computed<ActiveFilterChip[]>(() => {
    const chips: ActiveFilterChip[] = [];
    const accounts = data.value?.available_accounts || [];
    const categories = data.value?.available_categories || [];

    for (const accId of sharedFilters.numericAccountIds) {
      const acc = accounts.find(a => a.id === accId);
      chips.push({
        key: `account-${accId}`,
        type: 'account',
        id: accId,
        label: acc ? acc.name : `Account #${accId}`,
        color: acc?.color || '#64748B',
      });
    }

    for (const catId of sharedFilters.numericCategoryIds) {
      if (catId === 0) {
        chips.push({
          key: 'category-0',
          type: 'category',
          id: 0,
          label: 'Uncategorised',
          color: '#94A3B8',
        });
      } else {
        const cat = categories.find(c => c.id === catId);
        chips.push({
          key: `category-${catId}`,
          type: 'category',
          id: catId,
          label: cat ? cat.name : `Category #${catId}`,
          color: cat?.color || '#8B5CF6',
        });
      }
    }

    if (sharedFilters.dateOffset !== 0) {
      chips.push({
        key: `offset-${sharedFilters.dateOffset}`,
        type: 'offset',
        label: `${Math.abs(sharedFilters.dateOffset)} period${Math.abs(sharedFilters.dateOffset) > 1 ? 's' : ''} back`,
      });
    }

    return chips;
  });

  function reset() {
    data.value = null;
    isLoading.value = false;
    isExporting.value = false;
    error.value = null;
    activeSection.value = 'overview';
    selectedCurrency.value = '';
    selectedBalanceAccountIds.value = [];
    spendingFocusCategoryId.value = null;
    spendingGroupingMode.value = 'category';
    spendingChartType.value = 'stacked_bar';
    selectedCategoryLineIds.value = [];
    showTotalSpendLine.value = true;
    showNatureLines.value = { fixed: true, variable: true, unclassified: false };
    selectedAccountIds.value = [];
    selectedCategoryIds.value = [];
    sharedFilters.switchProfile(getActiveProfileId() || 'default');
    loadSavedPreferences();
  }

  return {
    data,
    isLoading,
    isExporting,
    error,
    activeSection,
    selectedPreset,
    selectedOffset,
    customStartDate,
    customEndDate,
    selectedInterval,
    selectedCurrency,
    selectedAccountIds,
    selectedCategoryIds,
    selectedBalanceAccountIds,
    selectedAccountId,
    selectedCategoryId,
    spendingGroupingMode,
    spendingChartType,
    spendingFocusCategoryId,
    selectedCategoryLineIds,
    showTotalSpendLine,
    showNatureLines,
    availableAccountsForCurrency,
    hasActiveFilters,
    activeFilterChips,
    buildQueryParams,
    loadAnalysis,
    exportReport,
    setPreset,
    navigatePeriod,
    resetPeriodOffset,
    setCustomRange,
    setInterval,
    setCurrency,
    setAccount,
    setAccounts,
    toggleAccountFilter,
    removeAccountFilter,
    clearAccountFilters,
    setCategory,
    setCategories,
    toggleCategoryFilter,
    removeCategoryFilter,
    clearCategoryFilters,
    resetAllFilters,
    toggleCategoryLine,
    setSection,
    toggleBalanceAccount,
    setBalanceAccounts,
    setSpendingFocusCategory,
    loadSavedPreferences,
    savePreferences,
    initFromRouteOrPreferences,
    reset,
  };
});
