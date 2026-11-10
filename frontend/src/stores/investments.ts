import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { 
  PortfolioSummary, 
  AccountHoldingsResponse, 
  Holding, 
  HoldingCreatePayload, 
  HoldingUpdatePayload,
  HoldingValuation, 
  HoldingValuationCreatePayload 
} from '../types';
import { api, getActiveProfileId } from '../api/client';
import { useAccountsStore } from './accounts';

export const useInvestmentsStore = defineStore('investments', () => {
  const summary = ref<PortfolioSummary | null>(null);
  const selectedAccountId = ref<number | null>(null);
  const accountHoldings = ref<Record<number, AccountHoldingsResponse>>({});
  const activeHolding = ref<Holding | null>(null);
  const activeValuations = ref<HoldingValuation[]>([]);
  
  const loading = ref(false);
  const valuationsLoading = ref(false);
  const error = ref<string | null>(null);
  let currentLoadEpoch = 0;

  function reset() {
    currentLoadEpoch++;
    summary.value = null;
    selectedAccountId.value = null;
    accountHoldings.value = {};
    activeHolding.value = null;
    activeValuations.value = [];
    error.value = null;
    loading.value = false;
  }

  async function loadSummary() {
    currentLoadEpoch++;
    const epoch = currentLoadEpoch;
    const reqProfile = getActiveProfileId();
    loading.value = true;
    error.value = null;
    try {
      const res = await api.getPortfolioSummary();
      if (epoch !== currentLoadEpoch || reqProfile !== getActiveProfileId()) {
        return;
      }
      summary.value = res;
    } catch (err: any) {
      if (epoch !== currentLoadEpoch || reqProfile !== getActiveProfileId()) {
        return;
      }
      error.value = err.message || 'Failed to load portfolio summary.';
    } finally {
      if (epoch === currentLoadEpoch && reqProfile === getActiveProfileId()) {
        loading.value = false;
      }
    }
  }

  async function loadHoldingsForAccount(accountId: number) {
    try {
      const res = await api.getAccountHoldings(accountId);
      accountHoldings.value[accountId] = res;
      return res;
    } catch (err: any) {
      error.value = err.message || `Failed to load holdings for account ${accountId}.`;
      throw err;
    }
  }

  async function loadAllData() {
    currentLoadEpoch++;
    const epoch = currentLoadEpoch;
    const reqProfile = getActiveProfileId();
    loading.value = true;
    error.value = null;
    try {
      const sum = await api.getPortfolioSummary();
      if (epoch !== currentLoadEpoch || reqProfile !== getActiveProfileId()) {
        return;
      }
      summary.value = sum;
      if (sum && sum.accounts.length > 0) {
        await Promise.all(
          sum.accounts.map(acc => loadHoldingsForAccount(acc.account_id))
        );
      }
    } catch (err: any) {
      if (epoch !== currentLoadEpoch || reqProfile !== getActiveProfileId()) {
        return;
      }
      error.value = err.message || 'Failed to load investment data.';
    } finally {
      if (epoch === currentLoadEpoch && reqProfile === getActiveProfileId()) {
        loading.value = false;
      }
    }
  }

  async function createHolding(accountId: number, payload: HoldingCreatePayload) {
    loading.value = true;
    error.value = null;
    try {
      const holding = await api.createHolding(accountId, payload);
      await Promise.all([
        loadHoldingsForAccount(accountId),
        loadSummary(),
        useAccountsStore().loadData()
      ]);
      return holding;
    } catch (err: any) {
      error.value = err.message || 'Failed to create holding.';
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function updateHolding(holdingId: number, oldAccountId: number, payload: HoldingUpdatePayload) {
    try {
      const holding = await api.updateHolding(holdingId, payload);
      const targetAccountId = payload.account_id || oldAccountId;
      const accountsToReload = [oldAccountId];
      if (targetAccountId !== oldAccountId) {
        accountsToReload.push(targetAccountId);
      }
      await Promise.all([
        ...accountsToReload.map(id => loadHoldingsForAccount(id)),
        loadSummary(),
        useAccountsStore().loadData()
      ]);
      return holding;
    } catch (err: any) {
      error.value = err.message || 'Failed to update holding.';
      throw err;
    }
  }

  async function deleteHolding(holdingId: number, accountId: number) {
    loading.value = true;
    try {
      await api.deleteHolding(holdingId);
      await Promise.all([
        loadHoldingsForAccount(accountId),
        loadSummary(),
        useAccountsStore().loadData()
      ]);
    } catch (err: any) {
      error.value = err.message || 'Failed to delete holding.';
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function loadValuations(holding: Holding) {
    activeHolding.value = holding;
    valuationsLoading.value = true;
    try {
      activeValuations.value = await api.getHoldingValuations(holding.id);
    } catch (err: any) {
      error.value = err.message || 'Failed to load valuation history.';
    } finally {
      valuationsLoading.value = false;
    }
  }

  async function recordValuation(holdingId: number, accountId: number, payload: HoldingValuationCreatePayload) {
    try {
      const val = await api.recordHoldingValuation(holdingId, payload);
      if (activeHolding.value && activeHolding.value.id === holdingId) {
        activeValuations.value = await api.getHoldingValuations(holdingId);
      }
      await Promise.all([
        loadHoldingsForAccount(accountId),
        loadSummary(),
        useAccountsStore().loadData()
      ]);
      return val;
    } catch (err: any) {
      error.value = err.message || 'Failed to record valuation.';
      throw err;
    }
  }

  async function updateValuation(
    valuationId: number, 
    holdingId: number, 
    accountId: number, 
    payload: Partial<HoldingValuationCreatePayload>
  ) {
    try {
      const val = await api.updateHoldingValuation(valuationId, payload);
      activeValuations.value = await api.getHoldingValuations(holdingId);
      await Promise.all([
        loadHoldingsForAccount(accountId),
        loadSummary(),
        useAccountsStore().loadData()
      ]);
      return val;
    } catch (err: any) {
      error.value = err.message || 'Failed to update valuation.';
      throw err;
    }
  }

  async function deleteValuation(valuationId: number, holdingId: number, accountId: number) {
    try {
      await api.deleteHoldingValuation(valuationId);
      activeValuations.value = await api.getHoldingValuations(holdingId);
      await Promise.all([
        loadHoldingsForAccount(accountId),
        loadSummary(),
        useAccountsStore().loadData()
      ]);
    } catch (err: any) {
      error.value = err.message || 'Failed to delete valuation.';
      throw err;
    }
  }

  async function switchValuationMode(accountId: number, mode: 'snapshot' | 'holdings') {
    loading.value = true;
    try {
      await api.updateValuationMode(accountId, mode);
      await Promise.all([
        loadHoldingsForAccount(accountId),
        loadSummary(),
        useAccountsStore().loadData()
      ]);
    } catch (err: any) {
      error.value = err.message || `Failed to switch valuation mode to ${mode}.`;
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function syncCheckpoint(accountId: number, effectiveDate?: string, notes?: string) {
    try {
      const res = await api.syncCheckpoint(accountId, {
        effective_date: effectiveDate,
        notes: notes
      });
      await Promise.all([
        loadSummary(),
        useAccountsStore().loadData()
      ]);
      return res;
    } catch (err: any) {
      error.value = err.message || 'Failed to sync account checkpoint.';
      throw err;
    }
  }

  return {
    summary,
    selectedAccountId,
    accountHoldings,
    activeHolding,
    activeValuations,
    loading,
    valuationsLoading,
    error,
    loadSummary,
    loadHoldingsForAccount,
    loadAllData,
    createHolding,
    updateHolding,
    deleteHolding,
    loadValuations,
    recordValuation,
    updateValuation,
    deleteValuation,
    switchValuationMode,
    syncCheckpoint,
    reset,
  };
});

