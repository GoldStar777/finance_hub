import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { Account, AccountCreatePayload, AccountUpdatePayload, DashboardSummary } from '../types';
import { api, getActiveProfileId } from '../api/client';
import { useInvestmentsStore } from './investments';

export const useAccountsStore = defineStore('accounts', () => {
  const accounts = ref<Account[]>([]);
  const summary = ref<DashboardSummary | null>(null);
  const showArchived = ref(false);
  const loading = ref(false);
  const error = ref<string | null>(null);
  let currentLoadEpoch = 0;

  const activeAccounts = computed(() => accounts.value.filter(a => a.is_active !== false));

  function reset() {
    currentLoadEpoch++;
    accounts.value = [];
    summary.value = null;
    error.value = null;
    loading.value = false;
  }

  async function loadData() {
    currentLoadEpoch++;
    const epoch = currentLoadEpoch;
    const reqProfile = getActiveProfileId();
    loading.value = true;
    error.value = null;
    try {
      const [accsRes, sumRes] = await Promise.allSettled([
        api.getAccounts(showArchived.value),
        api.getDashboardSummary()
      ]);
      if (epoch !== currentLoadEpoch || reqProfile !== getActiveProfileId()) {
        return;
      }
      if (accsRes.status === 'fulfilled') {
        accounts.value = accsRes.value;
      }
      if (sumRes.status === 'fulfilled') {
        summary.value = sumRes.value;
      }
      if (accsRes.status === 'rejected') {
        error.value = accsRes.reason?.message || 'Failed to load financial data.';
      } else if (sumRes.status === 'rejected') {
        console.warn('Dashboard summary failed to load:', sumRes.reason);
      }
    } catch (err: any) {
      if (epoch !== currentLoadEpoch || reqProfile !== getActiveProfileId()) {
        return;
      }
      error.value = err.message || 'Failed to load financial data.';
    } finally {
      if (epoch === currentLoadEpoch && reqProfile === getActiveProfileId()) {
        loading.value = false;
      }
    }
  }

  async function createAccount(payload: AccountCreatePayload) {
    loading.value = true;
    error.value = null;
    try {
      const newAcc = await api.createAccount(payload);
      accounts.value.push(newAcc);
      summary.value = await api.getDashboardSummary();
      await useInvestmentsStore().loadAllData();
      return newAcc;
    } catch (err: any) {
      error.value = err.message || 'Failed to create account.';
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function updateAccount(id: number, payload: AccountUpdatePayload) {
    loading.value = true;
    error.value = null;
    try {
      const updated = await api.updateAccount(id, payload);
      await loadData();
      await useInvestmentsStore().loadAllData();
      return updated;
    } catch (err: any) {
      error.value = err.message || 'Failed to update account.';
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function archiveAccount(id: number) {
    loading.value = true;
    error.value = null;
    try {
      await api.deleteAccount(id, false); // Sets is_active = false
      await loadData();
      await useInvestmentsStore().loadAllData();
    } catch (err: any) {
      error.value = err.message || 'Failed to archive account.';
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function permanentlyDeleteAccount(id: number) {
    loading.value = true;
    error.value = null;
    try {
      await api.deleteAccount(id, true);
      await loadData();
      await useInvestmentsStore().loadAllData();
    } catch (err: any) {
      error.value = err.message || 'Failed to permanently delete account.';
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function unarchiveAccount(id: number) {
    return updateAccount(id, { is_active: true });
  }

  function toggleShowArchived() {
    showArchived.value = !showArchived.value;
    return loadData();
  }

  return {
    accounts,
    activeAccounts,
    summary,
    showArchived,
    loading,
    error,
    loadData,
    createAccount,
    updateAccount,
    archiveAccount,
    permanentlyDeleteAccount,
    unarchiveAccount,
    toggleShowArchived,
    reset,
  };
});

