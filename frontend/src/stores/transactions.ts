import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { 
  Transaction, 
  TransactionCreatePayload, 
  TransactionUpdatePayload, 
  TransactionFilters,
  RepeatTransactionCreatePayload,
  Category,
  CategoryCreatePayload,
  CategoryUpdatePayload,
  BulkTransactionUpdatePayload,
  RecentlyDeletedSummary,
} from '../types';
import { api, getActiveProfileId } from '../api/client';
import { useAccountsStore } from './accounts';
import { useStagingStore } from './staging';
import { useSharedFiltersStore } from './filters';
import { useAnalysisStore } from './analysis';
import { useReviewStore } from './review';

export const useTransactionsStore = defineStore('transactions', () => {
  const transactions = ref<Transaction[]>([]);
  const recentTransactions = ref<Transaction[]>([]);
  const categories = ref<Category[]>([]);
  const total = ref(0);

  function getSavedPageSize(): number {
    try {
      const profileId = getActiveProfileId() || 'default';
      const saved = localStorage.getItem(`finance_hub_ledger_limit_${profileId}`);
      if (saved) {
        const parsed = parseInt(saved, 10);
        if ([25, 50, 100, 200].includes(parsed)) {
          return parsed;
        }
      }
    } catch {
      // ignore
    }
    return 25;
  }

  const limit = ref(getSavedPageSize());
  const offset = ref(0);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const rangeMeta = ref<{
    startDate: string | null;
    endDate: string | null;
    canNavigatePrevious: boolean;
    canNavigateNext: boolean;
  }>({
    startDate: null,
    endDate: null,
    canNavigatePrevious: true,
    canNavigateNext: false,
  });
  let currentLoadEpoch = 0;

  const filters = ref<TransactionFilters>({
    accountId: null,
    accountIds: [],
    categoryId: null,
    categoryIds: [],
    uncategorizedOnly: false,
    unassignedOnly: false,
    transactionType: null,
    transactionTypes: [],
    expenseNature: null,
    q: '',
    datePreset: 'all',
    startDate: undefined,
    endDate: undefined,
    status: 'all',
  });

  const isRecordModalOpen = ref(false);

  // Sorting State
  const sortBy = ref<string>('date');
  const sortOrder = ref<'asc' | 'desc'>('desc');
  const LEDGER_SORT_KEY_PREFIX = 'finance_hub_ledger_sort_';

  function getSortStorageKey(profileId?: string | null): string {
    const pid = profileId || getActiveProfileId() || 'default';
    return `${LEDGER_SORT_KEY_PREFIX}${pid}`;
  }

  function loadSavedSort(profileId?: string | null): boolean {
    if (typeof window === 'undefined' || !window.localStorage) return false;
    try {
      const raw = window.localStorage.getItem(getSortStorageKey(profileId));
      if (!raw) return false;
      const s = JSON.parse(raw);
      if (s && typeof s === 'object') {
        if (typeof s.sortBy === 'string') sortBy.value = s.sortBy;
        if (s.sortOrder === 'asc' || s.sortOrder === 'desc') sortOrder.value = s.sortOrder;
        return true;
      }
    } catch {
      // ignore
    }
    return false;
  }

  function saveSort(profileId?: string | null) {
    if (typeof window === 'undefined' || !window.localStorage) return;
    try {
      window.localStorage.setItem(getSortStorageKey(profileId), JSON.stringify({
        sortBy: sortBy.value,
        sortOrder: sortOrder.value,
      }));
    } catch {
      // ignore
    }
  }

  function setSort(newBy: string, newOrder: 'asc' | 'desc') {
    sortBy.value = newBy;
    sortOrder.value = newOrder;
    saveSort();
    clearSelection();
    return loadTransactions(0);
  }

  // Bulk Selection State
  const selectedIds = ref<Set<number>>(new Set());
  const isAllMatchingSelected = ref(false);

  // Recently Deleted State
  const activeLedgerTab = ref<'active' | 'deleted'>('active');
  const deletedTransactions = ref<Transaction[]>([]);
  const deletedTotal = ref(0);
  const deletedLoading = ref(false);
  const deletedSummary = ref<RecentlyDeletedSummary | null>(null);
  const deletedOffset = ref(0);
  const deletedLimit = ref(25);
  const deletedQuery = ref('');
  const deletedSelectedIds = ref<Set<number>>(new Set());

  // Undo Notification State
  const lastDeletionBatchId = ref<string | null>(null);
  const lastDeletedCount = ref(0);
  const undoToastMessage = ref<string | null>(null);
  let undoToastTimer: any = null;

  function triggerUndoToast(message: string, batchId: string, count: number) {
    if (undoToastTimer) {
      clearTimeout(undoToastTimer);
      undoToastTimer = null;
    }
    undoToastMessage.value = message;
    lastDeletionBatchId.value = batchId;
    lastDeletedCount.value = count;
    undoToastTimer = setTimeout(() => {
      dismissUndoToast();
    }, 10000); // 10 second auto-dismiss
  }

  function dismissUndoToast() {
    if (undoToastTimer) {
      clearTimeout(undoToastTimer);
      undoToastTimer = null;
    }
    undoToastMessage.value = null;
    lastDeletionBatchId.value = null;
    lastDeletedCount.value = 0;
  }

  function syncFiltersFromShared() {
    const sharedFilters = useSharedFiltersStore();
    filters.value.accountIds = [...sharedFilters.accountIds];
    filters.value.accountId = null;
    filters.value.unassignedOnly = false;
    filters.value.categoryIds = [...sharedFilters.categoryIds];
    filters.value.categoryId = null;
    filters.value.uncategorizedOnly = sharedFilters.isUncategorizedSelected && sharedFilters.categoryIds.length === 1;
    filters.value.datePreset = sharedFilters.datePreset;
    filters.value.dateOffset = sharedFilters.dateOffset;
    if (sharedFilters.datePreset === 'custom') {
      filters.value.startDate = sharedFilters.customStartDate || undefined;
      filters.value.endDate = sharedFilters.customEndDate || undefined;
    } else {
      filters.value.startDate = undefined;
      filters.value.endDate = undefined;
    }
  }

  function reset() {
    currentLoadEpoch++;
    transactions.value = [];
    recentTransactions.value = [];
    categories.value = [];
    total.value = 0;
    offset.value = 0;
    limit.value = getSavedPageSize();
    error.value = null;
    loading.value = false;
    sortBy.value = 'date';
    sortOrder.value = 'desc';
    loadSavedSort();
    filters.value.transactionType = null;
    filters.value.transactionTypes = [];
    filters.value.expenseNature = null;
    filters.value.q = '';
    filters.value.status = 'all';
    syncFiltersFromShared();
    rangeMeta.value = {
      startDate: null,
      endDate: null,
      canNavigatePrevious: true,
      canNavigateNext: false,
    };
    clearSelection();
    deletedTransactions.value = [];
    deletedTotal.value = 0;
    deletedSummary.value = null;
    deletedSelectedIds.value = new Set();
    dismissUndoToast();
  }

  function isRowSelected(id: number): boolean {
    return selectedIds.value.has(id);
  }

  function toggleRowSelection(id: number) {
    const next = new Set(selectedIds.value);
    if (next.has(id)) {
      next.delete(id);
      isAllMatchingSelected.value = false;
    } else {
      next.add(id);
    }
    selectedIds.value = next;
  }

  function selectCurrentPage() {
    const next = new Set(selectedIds.value);
    transactions.value.forEach(t => next.add(t.id));
    selectedIds.value = next;
  }

  function deselectCurrentPage() {
    const next = new Set(selectedIds.value);
    transactions.value.forEach(t => next.delete(t.id));
    selectedIds.value = next;
    isAllMatchingSelected.value = false;
  }

  function clearSelection() {
    selectedIds.value = new Set();
    isAllMatchingSelected.value = false;
  }

  async function selectAllMatching() {
    loading.value = true;
    try {
      const res = await api.getMatchingTransactionIds({
        ...filters.value,
        sort_by: sortBy.value,
        sort_order: sortOrder.value,
      });
      selectedIds.value = new Set(res.ids);
      isAllMatchingSelected.value = true;
    } catch (err: any) {
      console.error('Failed to select all matching transactions', err);
    } finally {
      loading.value = false;
    }
  }

  function openRecordModal() {
    isRecordModalOpen.value = true;
  }

  function closeRecordModal() {
    isRecordModalOpen.value = false;
  }

  const accountsStore = useAccountsStore();

  async function loadCategories(includeInactive = false) {
    const reqProfile = getActiveProfileId();
    try {
      const res = await api.getCategories(includeInactive);
      if (reqProfile !== getActiveProfileId()) return;
      categories.value = res;
    } catch (err: any) {
      if (reqProfile !== getActiveProfileId()) return;
      console.error('Failed to load categories', err);
    }
  }

  async function createCategory(payload: CategoryCreatePayload) {
    loading.value = true;
    error.value = null;
    try {
      const created = await api.createCategory(payload);
      await loadCategories();
      return created;
    } catch (err: any) {
      error.value = err.message || 'Failed to create category.';
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function updateCategory(id: number, payload: CategoryUpdatePayload) {
    loading.value = true;
    error.value = null;
    try {
      const updated = await api.updateCategory(id, payload);
      await loadCategories();
      return updated;
    } catch (err: any) {
      error.value = err.message || 'Failed to update category.';
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function deleteCategory(id: number, permanent = false, reassignToId?: number) {
    loading.value = true;
    error.value = null;
    try {
      await api.deleteCategory(id, permanent, reassignToId);
      await loadCategories();
    } catch (err: any) {
      error.value = err.message || 'Failed to delete category.';
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function loadTransactions(newOffset?: number) {
    currentLoadEpoch++;
    const epoch = currentLoadEpoch;
    const reqProfile = getActiveProfileId();
    loading.value = true;
    error.value = null;
    if (newOffset !== undefined) {
      offset.value = newOffset;
    }
    try {
      const response = await api.getTransactions({
        ...filters.value,
        sort_by: sortBy.value,
        sort_order: sortOrder.value,
        limit: limit.value,
        offset: offset.value,
      });
      if (epoch !== currentLoadEpoch || reqProfile !== getActiveProfileId()) {
        return;
      }
      transactions.value = response.items;
      total.value = response.total;
      rangeMeta.value = {
        startDate: response.range_start_date ?? null,
        endDate: response.range_end_date ?? null,
        canNavigatePrevious: response.can_navigate_previous ?? true,
        canNavigateNext: response.can_navigate_next ?? ((filters.value.dateOffset ?? 0) < 0),
      };
    } catch (err: any) {
      if (epoch !== currentLoadEpoch || reqProfile !== getActiveProfileId()) {
        return;
      }
      error.value = err.message || 'Failed to load transactions.';
    } finally {
      if (epoch === currentLoadEpoch && reqProfile === getActiveProfileId()) {
        loading.value = false;
      }
    }
  }

  async function loadRecent(count = 6) {
    const reqProfile = getActiveProfileId();
    try {
      const response = await api.getTransactions({ limit: count, offset: 0 });
      if (reqProfile !== getActiveProfileId()) return;
      recentTransactions.value = response.items;
    } catch (err: any) {
      if (reqProfile !== getActiveProfileId()) return;
      console.error('Failed to load recent transactions', err);
    }
  }

  async function refreshAfterCreate() {
    const stagingStore = useStagingStore();
    const analysisStore = useAnalysisStore();
    const reviewStore = useReviewStore();
    const tasks: Promise<unknown>[] = [
      accountsStore.loadData(),
      loadRecent(),
      loadTransactions(0),
      stagingStore.fetchCount(),
      stagingStore.fetchSuggestions(),
    ];
    if (analysisStore.data) {
      tasks.push(analysisStore.loadAnalysis());
    }
    if (reviewStore.report !== null) {
      tasks.push(reviewStore.loadFindings());
    }
    await Promise.allSettled(tasks);
  }

  async function createTransaction(payload: TransactionCreatePayload) {
    loading.value = true;
    error.value = null;
    try {
      const created = await api.createTransaction(payload);
      await refreshAfterCreate();
      return created;
    } catch (err: any) {
      error.value = err.message || 'Failed to create transaction.';
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function createRepeatTransactions(payload: RepeatTransactionCreatePayload) {
    loading.value = true;
    error.value = null;
    try {
      const created = await api.createRepeatTransactions(payload);
      await refreshAfterCreate();
      return created;
    } catch (err: any) {
      error.value = err.message || 'Failed to create repeating transactions.';
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function updateTransaction(id: number, payload: TransactionUpdatePayload) {
    loading.value = true;
    error.value = null;
    try {
      const updated = await api.updateTransaction(id, payload);
      const stagingStore = useStagingStore();
      const reviewStore = useReviewStore();
      await Promise.all([
        accountsStore.loadData(),
        loadRecent(),
        loadTransactions(),
        stagingStore.fetchCount(),
        stagingStore.fetchSuggestions(),
        ...(reviewStore.report !== null ? [reviewStore.loadFindings()] : []),
      ]);
      return updated;
    } catch (err: any) {
      error.value = err.message || 'Failed to update transaction.';
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function deleteTransaction(id: number) {
    loading.value = true;
    error.value = null;
    try {
      await api.deleteTransaction(id);
      const stagingStore = useStagingStore();
      const reviewStore = useReviewStore();
      await Promise.allSettled([
        accountsStore.loadData(),
        loadRecent(),
        loadTransactions(),
        stagingStore.fetchCount(),
        stagingStore.fetchSuggestions(),
        loadDeletedSummary(),
        ...(reviewStore.report !== null ? [reviewStore.loadFindings()] : []),
      ]);
      triggerUndoToast('Moved 1 transaction to Recently Deleted.', 'single', 1);
    } catch (err: any) {
      error.value = err.message || 'Failed to delete transaction.';
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function bulkDelete(targetIds?: number[]) {
    const ids = targetIds || Array.from(selectedIds.value);
    if (ids.length === 0) return;
    loading.value = true;
    error.value = null;
    try {
      const res = await api.bulkDeleteTransactions({ transaction_ids: ids });
      clearSelection();
      const stagingStore = useStagingStore();
      const reviewStore = useReviewStore();
      await Promise.allSettled([
        accountsStore.loadData(),
        loadRecent(),
        loadTransactions(offset.value),
        stagingStore.fetchCount(),
        stagingStore.fetchSuggestions(),
        loadDeletedSummary(),
        ...(reviewStore.report !== null ? [reviewStore.loadFindings()] : []),
      ]);
      triggerUndoToast(
        `Moved ${res.deleted_count} transaction${res.deleted_count === 1 ? '' : 's'} to Recently Deleted.`,
        res.deletion_batch_id,
        res.deleted_count
      );
      return res;
    } catch (err: any) {
      error.value = err.message || 'Failed to delete selected transactions.';
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function restoreTransactions(ids?: number[], batchId?: string) {
    loading.value = true;
    error.value = null;
    try {
      const res = await api.restoreTransactions({ transaction_ids: ids, batch_id: batchId });
      clearDeletedSelection();
      dismissUndoToast();
      const stagingStore = useStagingStore();
      const reviewStore = useReviewStore();
      await Promise.allSettled([
        accountsStore.loadData(),
        loadRecent(),
        loadTransactions(),
        loadDeletedTransactions(),
        loadDeletedSummary(),
        stagingStore.fetchCount(),
        stagingStore.fetchSuggestions(),
        ...(reviewStore.report !== null ? [reviewStore.loadFindings()] : []),
      ]);
      return res;
    } catch (err: any) {
      error.value = err.message || 'Failed to restore transactions.';
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function undoLastDelete() {
    loading.value = true;
    error.value = null;
    try {
      const res = await api.undoDeleteTransactions(lastDeletionBatchId.value || undefined);
      dismissUndoToast();
      const stagingStore = useStagingStore();
      const reviewStore = useReviewStore();
      await Promise.allSettled([
        accountsStore.loadData(),
        loadRecent(),
        loadTransactions(),
        loadDeletedTransactions(),
        loadDeletedSummary(),
        stagingStore.fetchCount(),
        stagingStore.fetchSuggestions(),
        ...(reviewStore.report !== null ? [reviewStore.loadFindings()] : []),
      ]);
      return res;
    } catch (err: any) {
      error.value = err.message || 'Failed to undo deletion.';
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function loadDeletedSummary() {
    try {
      deletedSummary.value = await api.getDeletedSummary();
    } catch (err) {
      console.error('Failed to load deleted summary', err);
    }
  }

  async function loadDeletedTransactions(newOffset?: number) {
    deletedLoading.value = true;
    if (newOffset !== undefined) {
      deletedOffset.value = newOffset;
    }
    try {
      const res = await api.getDeletedTransactions({
        limit: deletedLimit.value,
        offset: deletedOffset.value,
        q: deletedQuery.value || undefined,
      });
      deletedTransactions.value = res.items;
      deletedTotal.value = res.total;
    } catch (err: any) {
      console.error('Failed to load deleted transactions', err);
    } finally {
      deletedLoading.value = false;
    }
  }

  function isDeletedRowSelected(id: number): boolean {
    return deletedSelectedIds.value.has(id);
  }

  function toggleDeletedRowSelection(id: number) {
    const next = new Set(deletedSelectedIds.value);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    deletedSelectedIds.value = next;
  }

  function selectCurrentDeletedPage() {
    const next = new Set(deletedSelectedIds.value);
    deletedTransactions.value.forEach(t => next.add(t.id));
    deletedSelectedIds.value = next;
  }

  function deselectCurrentDeletedPage() {
    const next = new Set(deletedSelectedIds.value);
    deletedTransactions.value.forEach(t => next.delete(t.id));
    deletedSelectedIds.value = next;
  }

  function clearDeletedSelection() {
    deletedSelectedIds.value = new Set();
  }

  async function bulkUpdate(payload: Omit<BulkTransactionUpdatePayload, 'transaction_ids'>) {
    if (selectedIds.value.size === 0) return;
    loading.value = true;
    error.value = null;
    try {
      const res = await api.bulkUpdateTransactions({
        ...payload,
        transaction_ids: Array.from(selectedIds.value),
      });
      clearSelection();
      const stagingStore = useStagingStore();
      await Promise.all([
        accountsStore.loadData(),
        loadRecent(),
        loadTransactions(offset.value),
        stagingStore.fetchCount(),
        stagingStore.fetchSuggestions(),
      ]);
      return res;
    } catch (err: any) {
      error.value = err.message || 'Failed to apply bulk updates.';
      throw err;
    } finally {
      loading.value = false;
    }
  }

  function setPageSize(newLimit: number) {
    if (![25, 50, 100, 200].includes(newLimit)) return;
    limit.value = newLimit;
    try {
      const profileId = getActiveProfileId() || 'default';
      localStorage.setItem(`finance_hub_ledger_limit_${profileId}`, newLimit.toString());
    } catch {
      // ignore
    }
    offset.value = 0;
    return loadTransactions(0);
  }

  async function exportLedger(format: 'csv' | 'xlsx'): Promise<void> {
    const blob = await api.downloadTransactionsExport({
      ...filters.value,
      sort_by: sortBy.value,
      sort_order: sortOrder.value,
    }, format);
    const profileId = getActiveProfileId() || 'default';
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    const filename = `ledger_export_${profileId}_${timestamp}.${format}`;
    
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  }

  function resetLedgerSpecificFilters() {
    clearSelection();
    filters.value.transactionType = null;
    filters.value.transactionTypes = [];
    filters.value.expenseNature = null;
    filters.value.q = '';
    filters.value.status = 'all';
    offset.value = 0;
    return loadTransactions(0);
  }

  function resetFilters() {
    clearSelection();
    filters.value = {
      accountId: null,
      accountIds: [],
      categoryId: null,
      categoryIds: [],
      uncategorizedOnly: false,
      unassignedOnly: false,
      transactionType: null,
      transactionTypes: [],
      expenseNature: null,
      q: '',
      datePreset: 'all',
      dateOffset: 0,
      startDate: undefined,
      endDate: undefined,
      status: 'all',
    };
    offset.value = 0;
    return loadTransactions(0);
  }

  return {
    transactions,
    recentTransactions,
    categories,
    total,
    limit,
    offset,
    loading,
    error,
    rangeMeta,
    filters,
    syncFiltersFromShared,
    resetLedgerSpecificFilters,
    selectedIds,
    isAllMatchingSelected,
    isRecordModalOpen,
    openRecordModal,
    closeRecordModal,
    loadCategories,
    createCategory,
    updateCategory,
    deleteCategory,
    loadTransactions,
    loadRecent,
    createTransaction,
    createRepeatTransactions,
    updateTransaction,
    deleteTransaction,
    bulkDelete,
    restoreTransactions,
    undoLastDelete,
    loadDeletedSummary,
    loadDeletedTransactions,
    isDeletedRowSelected,
    toggleDeletedRowSelection,
    selectCurrentDeletedPage,
    deselectCurrentDeletedPage,
    clearDeletedSelection,
    triggerUndoToast,
    dismissUndoToast,
    activeLedgerTab,
    deletedTransactions,
    deletedTotal,
    deletedLoading,
    deletedSummary,
    deletedOffset,
    deletedLimit,
    deletedQuery,
    deletedSelectedIds,
    lastDeletionBatchId,
    lastDeletedCount,
    undoToastMessage,
    isRowSelected,
    toggleRowSelection,
    selectCurrentPage,
    deselectCurrentPage,
    clearSelection,
    selectAllMatching,
    bulkUpdate,
    setPageSize,
    exportLedger,
    sortBy,
    sortOrder,
    setSort,
    loadSavedSort,
    saveSort,
    resetFilters,
    reset,
  };
});
