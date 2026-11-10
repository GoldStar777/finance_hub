import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { CashFlowSummaryResponse } from '../types';
import { api } from '../api/client';

export const useCashflowStore = defineStore('cashflow', () => {
  const summary = ref<CashFlowSummaryResponse | null>(null);
  const selectedMonth = ref<string>('');
  const selectedCurrency = ref<string>('GBP');
  const selectedAccountId = ref<number | null>(null);

  const loading = ref(false);
  const error = ref<string | null>(null);

  async function loadCashFlow(
    targetMonth?: string,
    targetCurrency?: string,
    targetAccountId?: number | null
  ) {
    loading.value = true;
    error.value = null;

    if (targetMonth !== undefined) {
      selectedMonth.value = targetMonth;
    }
    if (targetCurrency !== undefined) {
      selectedCurrency.value = targetCurrency;
    }
    if (targetAccountId !== undefined) {
      selectedAccountId.value = targetAccountId;
    }

    try {
      const res = await api.getCashFlowSummary(
        selectedMonth.value || undefined,
        selectedCurrency.value || undefined,
        selectedAccountId.value
      );
      summary.value = res;
      selectedMonth.value = res.selected_month;
      selectedCurrency.value = res.currency;
      selectedAccountId.value = res.account_id;
      return res;
    } catch (err: any) {
      error.value = err.message || 'Failed to load cash flow analytics.';
      throw err;
    } finally {
      loading.value = false;
    }
  }

  function goToPrevMonth() {
    if (summary.value?.prev_month) {
      return loadCashFlow(summary.value.prev_month);
    }
  }

  function goToNextMonth() {
    if (summary.value?.next_month) {
      return loadCashFlow(summary.value.next_month);
    }
  }

  function setMonth(month: string) {
    return loadCashFlow(month);
  }

  function setCurrency(currency: string) {
    return loadCashFlow(undefined, currency);
  }

  function setAccount(accountId: number | null) {
    return loadCashFlow(undefined, undefined, accountId);
  }

  return {
    summary,
    selectedMonth,
    selectedCurrency,
    selectedAccountId,
    loading,
    error,
    loadCashFlow,
    goToPrevMonth,
    goToNextMonth,
    setMonth,
    setCurrency,
    setAccount,
  };
});

