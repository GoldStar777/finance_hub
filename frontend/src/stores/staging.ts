import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { api } from '../api/client';
import { useAccountsStore } from './accounts';
import { useTransactionsStore } from './transactions';
import { useReviewStore } from './review';
import type { 
  StagingItem, 
  StagingItemUpdatePayload, 
  StatementMappingProfile, 
  StatementMappingProfileCreatePayload,
  ReviewDuplicateSuggestion,
  ReviewTransferSuggestion,
  StagingSplitRequest
} from '../types';

export const useStagingStore = defineStore('staging', () => {
  const items = ref<StagingItem[]>([]);
  const pendingCount = ref<number>(0);
  const loading = ref<boolean>(false);
  const error = ref<string | null>(null);

  // Suggestions state
  const duplicateSuggestions = ref<ReviewDuplicateSuggestion[]>([]);
  const transferSuggestions = ref<ReviewTransferSuggestion[]>([]);
  const suggestionsSummary = ref<{ duplicates_count: number; transfers_count: number }>({
    duplicates_count: 0,
    transfers_count: 0
  });
  const loadingSuggestions = ref<boolean>(false);

  const statusFilter = ref<string>('pending');
  const sourceFilter = ref<string>('all');
  const selectedIds = ref<number[]>([]);
  const profiles = ref<StatementMappingProfile[]>([]);

  const filteredItems = computed(() => {
    return items.value.filter(item => {
      if (sourceFilter.value !== 'all' && item.source_type !== sourceFilter.value) {
        return false;
      }
      return true;
    });
  });

  const duplicateItems = computed(() => {
    return items.value.filter(item => item.is_potential_duplicate);
  });

  const suggestionsCount = computed(() => {
    return (duplicateSuggestions.value?.length || 0) + (transferSuggestions.value?.length || 0);
  });

  function reset() {
    items.value = [];
    pendingCount.value = 0;
    selectedIds.value = [];
    error.value = null;
    loading.value = false;
    duplicateSuggestions.value = [];
    transferSuggestions.value = [];
    suggestionsSummary.value = { duplicates_count: 0, transfers_count: 0 };
    loadingSuggestions.value = false;
  }

  async function fetchSuggestions() {
    loadingSuggestions.value = true;
    try {
      const res = await api.getReviewSuggestions();
      duplicateSuggestions.value = res.duplicate_suggestions || [];
      transferSuggestions.value = res.transfer_suggestions || [];
      suggestionsSummary.value = res.summary || { duplicates_count: 0, transfers_count: 0 };
    } catch (err: any) {
      console.error('Failed to load review suggestions', err);
    } finally {
      loadingSuggestions.value = false;
    }
  }

  async function confirmDuplicate(duplicateStagingId: number, suggestionId?: string) {
    loading.value = true;
    error.value = null;
    try {
      await api.confirmDuplicateSuggestion(duplicateStagingId, suggestionId);
      items.value = items.value.filter(i => i.id !== duplicateStagingId);
      selectedIds.value = selectedIds.value.filter(id => id !== duplicateStagingId);
      if (suggestionId) {
        duplicateSuggestions.value = duplicateSuggestions.value.filter(s => s.id !== suggestionId);
        suggestionsSummary.value.duplicates_count = Math.max(0, suggestionsSummary.value.duplicates_count - 1);
      }
      await fetchCount();
      await fetchSuggestions();
    } catch (err: any) {
      error.value = err.message || 'Failed to exclude duplicate item';
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function confirmTransfer(
    sourceId: number,
    sourceKind: string,
    destinationId: number,
    destinationKind: string,
    suggestionId?: string
  ) {
    loading.value = true;
    error.value = null;
    try {
      await api.confirmTransferSuggestion(sourceId, sourceKind, destinationId, destinationKind, suggestionId);
      if (sourceKind === 'staging') {
        items.value = items.value.filter(i => i.id !== sourceId);
        selectedIds.value = selectedIds.value.filter(id => id !== sourceId);
      }
      if (destinationKind === 'staging') {
        items.value = items.value.filter(i => i.id !== destinationId);
        selectedIds.value = selectedIds.value.filter(id => id !== destinationId);
      }
      if (suggestionId) {
        transferSuggestions.value = transferSuggestions.value.filter(s => s.id !== suggestionId);
        suggestionsSummary.value.transfers_count = Math.max(0, suggestionsSummary.value.transfers_count - 1);
      }
      const accountsStore = useAccountsStore();
      const txStore = useTransactionsStore();
      await Promise.all([
        fetchCount(),
        fetchSuggestions(),
        accountsStore.loadData(),
        txStore.loadRecent(),
        txStore.loadTransactions(),
      ]);
    } catch (err: any) {
      error.value = err.message || 'Failed to confirm transfer pairing';
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function dismissSuggestion(suggestionId: string) {
    try {
      await api.dismissReviewSuggestion(suggestionId);
      duplicateSuggestions.value = duplicateSuggestions.value.filter(s => s.id !== suggestionId);
      transferSuggestions.value = transferSuggestions.value.filter(s => s.id !== suggestionId);
      suggestionsSummary.value.duplicates_count = duplicateSuggestions.value.length;
      suggestionsSummary.value.transfers_count = transferSuggestions.value.length;
      const reviewStore = useReviewStore();
      if (reviewStore.report !== null) {
        await reviewStore.loadFindings();
      }
    } catch (err: any) {
      console.error('Failed to dismiss suggestion', err);
    }
  }

  async function fetchCount() {
    try {
      const res = await api.getStagingCount();
      pendingCount.value = res.pending_count;
    } catch {
      // ignore
    }
  }

  async function fetchItems() {
    loading.value = true;
    error.value = null;
    try {
      const src = sourceFilter.value !== 'all' ? sourceFilter.value : undefined;
      items.value = await api.getStagingItems(statusFilter.value, src);
      selectedIds.value = [];
      await fetchCount();
    } catch (err: any) {
      error.value = err.message || 'Failed to load staging items';
    } finally {
      loading.value = false;
    }
  }

  async function updateItem(id: number, payload: StagingItemUpdatePayload) {
    try {
      const updated = await api.updateStagingItem(id, payload);
      const idx = items.value.findIndex(i => i.id === id);
      if (idx !== -1) {
        items.value[idx] = updated;
      }
      await fetchSuggestions();
      return updated;
    } catch (err: any) {
      error.value = err.message || 'Failed to update item';
      throw err;
    }
  }

  async function approveItem(id: number) {
    try {
      await api.approveStagingItem(id);
      items.value = items.value.filter(i => i.id !== id);
      selectedIds.value = selectedIds.value.filter(selId => selId !== id);
      const accountsStore = useAccountsStore();
      const txStore = useTransactionsStore();
      await Promise.all([
        fetchCount(),
        fetchSuggestions(),
        accountsStore.loadData(),
        txStore.loadRecent(),
      ]);
    } catch (err: any) {
      error.value = err.message || 'Failed to approve item';
      throw err;
    }
  }

  async function discardItem(id: number) {
    try {
      await api.discardStagingItem(id);
      items.value = items.value.filter(i => i.id !== id);
      selectedIds.value = selectedIds.value.filter(selId => selId !== id);
      await Promise.all([
        fetchCount(),
        fetchSuggestions(),
      ]);
    } catch (err: any) {
      error.value = err.message || 'Failed to discard item';
      throw err;
    }
  }

  async function splitItem(id: number, payload: StagingSplitRequest) {
    loading.value = true;
    error.value = null;
    try {
      const res = await api.splitStagingItem(id, payload);
      items.value = items.value.filter(i => i.id !== id);
      selectedIds.value = selectedIds.value.filter(selId => selId !== id);

      if (res.action === 'queued' && res.created_items && res.created_items.length > 0) {
        items.value = [...res.created_items, ...items.value];
      }

      const accountsStore = useAccountsStore();
      const txStore = useTransactionsStore();
      await Promise.all([
        fetchCount(),
        fetchSuggestions(),
        ...(res.action === 'approved' ? [
          accountsStore.loadData(),
          txStore.loadRecent(),
          txStore.loadTransactions()
        ] : [])
      ]);
      return res;
    } catch (err: any) {
      error.value = err.message || 'Failed to split expense';
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function batchApprove(includeDuplicates: boolean = false) {
    loading.value = true;
    error.value = null;
    try {
      const idsToApprove = selectedIds.value.length > 0 ? selectedIds.value : undefined;
      const res = await api.batchApproveStagingItems({
        item_ids: idsToApprove,
        include_duplicates: includeDuplicates
      });
      const accountsStore = useAccountsStore();
      const txStore = useTransactionsStore();
      await Promise.all([
        fetchItems(),
        fetchSuggestions(),
        accountsStore.loadData(),
        txStore.loadRecent(),
      ]);
      return res;
    } catch (err: any) {
      error.value = err.message || 'Failed to batch approve items';
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function batchReject() {
    if (selectedIds.value.length === 0) return;
    loading.value = true;
    error.value = null;
    try {
      await api.batchRejectStagingItems(selectedIds.value);
      await Promise.all([
        fetchItems(),
        fetchSuggestions(),
      ]);
    } catch (err: any) {
      error.value = err.message || 'Failed to batch reject items';
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function fetchProfiles() {
    try {
      profiles.value = await api.getMappingProfiles();
    } catch {
      // ignore
    }
  }

  async function saveProfile(payload: StatementMappingProfileCreatePayload) {
    try {
      const created = await api.createMappingProfile(payload);
      profiles.value.push(created);
      return created;
    } catch (err: any) {
      error.value = err.message || 'Failed to save profile';
      throw err;
    }
  }

  async function deleteProfile(id: string) {
    try {
      await api.deleteMappingProfile(id);
      profiles.value = profiles.value.filter(p => p.id !== id);
    } catch (err: any) {
      error.value = err.message || 'Failed to delete profile';
      throw err;
    }
  }

  function toggleSelectAll(select: boolean) {
    if (select) {
      selectedIds.value = filteredItems.value.map(i => i.id);
    } else {
      selectedIds.value = [];
    }
  }

  function toggleSelect(id: number) {
    if (selectedIds.value.includes(id)) {
      selectedIds.value = selectedIds.value.filter(i => i !== id);
    } else {
      selectedIds.value.push(id);
    }
  }

  return {
    items,
    pendingCount,
    loading,
    error,
    statusFilter,
    sourceFilter,
    selectedIds,
    profiles,
    filteredItems,
    duplicateItems,
    suggestionsCount,
    duplicateSuggestions,
    transferSuggestions,
    suggestionsSummary,
    loadingSuggestions,
    fetchSuggestions,
    confirmDuplicate,
    confirmTransfer,
    dismissSuggestion,
    fetchCount,
    fetchItems,
    updateItem,
    approveItem,
    discardItem,
    splitItem,
    batchApprove,
    batchReject,
    fetchProfiles,
    saveProfile,
    deleteProfile,
    toggleSelectAll,
    toggleSelect,
    reset,
  };
});

