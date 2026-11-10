import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type {
  DataQualityFinding,
  DataQualityFindingType,
  DataQualityReportResponse,
  DataQualitySeverity,
  DataQualitySummary,
} from '../types';
import { api, getActiveProfileId } from '../api/client';
import { useAccountsStore } from './accounts';
import { useTransactionsStore } from './transactions';
import { useStagingStore } from './staging';

export const useReviewStore = defineStore('review', () => {
  const report = ref<DataQualityReportResponse | null>(null);
  const loading = ref(false);
  const actionLoading = ref(false);
  const error = ref<string | null>(null);

  const selectedFindingType = ref<DataQualityFindingType | 'all'>('all');
  const selectedSeverity = ref<DataQualitySeverity | 'all'>('all');
  const searchQuery = ref('');
  const selectedAccountFilter = ref<string>('');
  const selectedCategoryFilter = ref<string>('');
  const startDate = ref('');
  const endDate = ref('');
  const includeDismissed = ref(false);

  const selectedFindingId = ref<string | null>(null);

  const findings = computed<DataQualityFinding[]>(() => report.value?.findings || []);

  const summary = computed<DataQualitySummary>(() => {
    return (
      report.value?.summary || {
        total_active: 0,
        dismissed_count: 0,
        by_type: {},
        by_severity: {},
        scanned_transactions_count: 0,
        scanned_staging_count: 0,
      }
    );
  });

  const activeCount = computed<number>(() => summary.value.total_active || 0);

  const selectedFinding = computed<DataQualityFinding | null>(() => {
    if (findings.value.length === 0) return null;
    if (selectedFindingId.value) {
      const match = findings.value.find((f) => f.id === selectedFindingId.value);
      if (match) return match;
    }
    return findings.value[0] || null;
  });

  function reset() {
    report.value = null;
    loading.value = false;
    actionLoading.value = false;
    error.value = null;
    selectedFindingId.value = null;
    selectedFindingType.value = 'all';
    selectedSeverity.value = 'all';
    searchQuery.value = '';
    selectedAccountFilter.value = '';
    selectedCategoryFilter.value = '';
    startDate.value = '';
    endDate.value = '';
    includeDismissed.value = false;
  }

  function resetFilters() {
    selectedFindingType.value = 'all';
    selectedSeverity.value = 'all';
    searchQuery.value = '';
    selectedAccountFilter.value = '';
    selectedCategoryFilter.value = '';
    startDate.value = '';
    endDate.value = '';
  }

  async function loadFindings() {
    const reqProfile = getActiveProfileId();
    loading.value = true;
    error.value = null;
    try {
      const data = await api.getDataQualityFindings({
        finding_type: selectedFindingType.value === 'all' ? undefined : selectedFindingType.value,
        severity: selectedSeverity.value === 'all' ? undefined : selectedSeverity.value,
        q: searchQuery.value || undefined,
        account_id: selectedAccountFilter.value || undefined,
        category_id: selectedCategoryFilter.value || undefined,
        start_date: startDate.value || undefined,
        end_date: endDate.value || undefined,
        include_dismissed: includeDismissed.value,
      });
      if (reqProfile !== getActiveProfileId()) return;
      report.value = data;
      if (data.findings.length > 0 && !data.findings.some((f) => f.id === selectedFindingId.value)) {
        selectedFindingId.value = data.findings[0].id;
      } else if (data.findings.length === 0) {
        selectedFindingId.value = null;
      }
      return data;
    } catch (err: any) {
      if (reqProfile !== getActiveProfileId()) return;
      error.value = err.message || 'Failed to scan workspace review findings.';
    } finally {
      if (reqProfile === getActiveProfileId()) {
        loading.value = false;
      }
    }
  }

  async function refreshRelatedStores() {
    const accountsStore = useAccountsStore();
    const txStore = useTransactionsStore();
    const stagingStore = useStagingStore();
    await Promise.allSettled([
      loadFindings(),
      stagingStore.fetchSuggestions(),
      stagingStore.fetchCount(),
      accountsStore.loadData(),
      txStore.loadRecent(),
      txStore.loadTransactions(),
    ]);
  }

  async function assignCategory(transactionId: number, categoryId: number) {
    actionLoading.value = true;
    error.value = null;
    try {
      await api.updateTransaction(transactionId, { category_id: categoryId });
      await refreshRelatedStores();
    } catch (err: any) {
      error.value = err.message || 'Failed to assign category.';
      throw err;
    } finally {
      actionLoading.value = false;
    }
  }

  async function assignAccount(transactionId: number, accountId: number) {
    actionLoading.value = true;
    error.value = null;
    try {
      await api.updateTransaction(transactionId, { account_id: accountId });
      await refreshRelatedStores();
    } catch (err: any) {
      error.value = err.message || 'Failed to assign account.';
      throw err;
    } finally {
      actionLoading.value = false;
    }
  }

  async function confirmExcludeStagingDuplicate(stagingId: number, suggestionId?: string) {
    actionLoading.value = true;
    error.value = null;
    try {
      const stagingStore = useStagingStore();
      await stagingStore.confirmDuplicate(stagingId, suggestionId);
      await loadFindings();
    } catch (err: any) {
      error.value = err.message || 'Failed to exclude duplicate candidate.';
      throw err;
    } finally {
      actionLoading.value = false;
    }
  }

  async function confirmSoftDeleteLedgerDuplicate(transactionId: number) {
    actionLoading.value = true;
    error.value = null;
    try {
      const txStore = useTransactionsStore();
      await txStore.bulkDelete([transactionId]);
      await loadFindings();
    } catch (err: any) {
      error.value = err.message || 'Failed to move duplicate transaction to Recently Deleted.';
      throw err;
    } finally {
      actionLoading.value = false;
    }
  }

  async function confirmPairTransfer(
    sourceId: number,
    sourceKind: string,
    destinationId: number,
    destinationKind: string,
    suggestionId?: string
  ) {
    actionLoading.value = true;
    error.value = null;
    try {
      const stagingStore = useStagingStore();
      await stagingStore.confirmTransfer(sourceId, sourceKind, destinationId, destinationKind, suggestionId);
      await loadFindings();
    } catch (err: any) {
      error.value = err.message || 'Failed to pair dual-account transfer.';
      throw err;
    } finally {
      actionLoading.value = false;
    }
  }

  async function dismissFinding(findingId: string) {
    actionLoading.value = true;
    error.value = null;
    try {
      await api.dismissDataQualityFinding(findingId);
      const stagingStore = useStagingStore();
      await Promise.allSettled([
        loadFindings(),
        stagingStore.fetchSuggestions(),
      ]);
    } catch (err: any) {
      error.value = err.message || 'Failed to hide suggestion.';
      throw err;
    } finally {
      actionLoading.value = false;
    }
  }

  async function restoreDismissed(findingId?: string, restoreAll = false) {
    actionLoading.value = true;
    error.value = null;
    try {
      await api.restoreDismissedReviewFindings({
        finding_id: findingId,
        restore_all: restoreAll || !findingId,
      });
      const stagingStore = useStagingStore();
      await Promise.allSettled([
        loadFindings(),
        stagingStore.fetchSuggestions(),
      ]);
    } catch (err: any) {
      error.value = err.message || 'Failed to restore hidden suggestion.';
      throw err;
    } finally {
      actionLoading.value = false;
    }
  }

  return {
    report,
    findings,
    summary,
    activeCount,
    selectedFindingId,
    selectedFinding,
    loading,
    actionLoading,
    error,
    selectedFindingType,
    selectedSeverity,
    searchQuery,
    selectedAccountFilter,
    selectedCategoryFilter,
    startDate,
    endDate,
    includeDismissed,
    reset,
    resetFilters,
    loadFindings,
    assignCategory,
    assignAccount,
    confirmExcludeStagingDuplicate,
    confirmSoftDeleteLedgerDuplicate,
    confirmPairTransfer,
    dismissFinding,
    restoreDismissed,
  };
});
