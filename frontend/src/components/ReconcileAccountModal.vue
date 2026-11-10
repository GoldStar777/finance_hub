<template>
  <div 
    v-if="isOpen && account" 
    class="fixed inset-0 z-50 bg-slate-950/40 backdrop-blur-sm flex items-center justify-center p-4 animate-fadeIn"
    @click.self="emitClose">
    <section 
      role="dialog" 
      aria-modal="true" 
      aria-labelledby="reconcile-modal-title"
      class="bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder rounded-2xl max-w-xl w-full p-6 shadow-2xl space-y-5 transition-all max-h-[90vh] flex flex-col">
      
      <!-- Modal Header -->
      <div class="flex items-start justify-between pb-3 border-b border-brand-border dark:border-brand-darkborder shrink-0">
        <div>
          <div class="flex items-center space-x-2">
            <h2 id="reconcile-modal-title" class="font-bold text-slate-900 dark:text-white text-base">
              Account Reconciliation
            </h2>
            <span class="px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-300">
              {{ formatAccountType(account.account_type) }}
            </span>
          </div>
          <p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Confirm <strong>{{ account.name }}</strong> ({{ account.currency }}) ground-truth balance anchor from your statement.
          </p>
        </div>

        <button 
          @click="emitClose" 
          class="text-slate-400 hover:text-slate-600 dark:hover:text-white text-lg p-1"
          aria-label="Close dialog">
          &times;
        </button>
      </div>

      <!-- Navigation Tabs: Reconcile vs History -->
      <div class="flex items-center space-x-2 border-b border-brand-border dark:border-brand-darkborder pb-2 shrink-0 text-xs">
        <button
          type="button"
          @click="activeTab = 'reconcile'"
          class="px-3 py-1.5 rounded-full font-semibold transition"
          :class="activeTab === 'reconcile' 
            ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-900 shadow-sm' 
            : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'">
          Reconcile Balance
        </button>

        <button
          type="button"
          @click="switchToHistoryTab"
          class="px-3 py-1.5 rounded-full font-semibold transition flex items-center space-x-1.5"
          :class="activeTab === 'history' 
            ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-900 shadow-sm' 
            : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'">
          <span>Reconciliation History</span>
          <span 
            v-if="snapshots.length > 0" 
            class="px-1.5 py-0.2 text-[10px] rounded-full font-mono font-bold"
            :class="activeTab === 'history' ? 'bg-indigo-500 text-white' : 'bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300'">
            {{ snapshots.length }}
          </span>
        </button>
      </div>

      <!-- Tab 1: Reconcile Balance Flow -->
      <div v-if="activeTab === 'reconcile'" class="space-y-4 overflow-y-auto pr-1">
        
        <!-- Error Message -->
        <div v-if="errorMessage" class="p-3 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 text-rose-600 dark:text-rose-400 text-xs">
          {{ errorMessage }}
        </div>

        <!-- Success Toast -->
        <div v-if="successMessage" class="p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-900 text-emerald-700 dark:text-emerald-300 text-xs font-semibold">
          {{ successMessage }}
        </div>

        <!-- Ground Truth Statement Balance & Date Selection -->
        <div class="space-y-3">
          
          <!-- As-Of Cutoff Selection -->
          <div class="p-3.5 rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50/70 dark:bg-slate-800/40 space-y-2.5">
            <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500">
              Correct as of:
            </label>
            <div class="flex items-center space-x-3 text-xs">
              <label class="flex items-center space-x-1.5 cursor-pointer font-semibold text-slate-800 dark:text-slate-200">
                <input 
                  type="radio" 
                  value="now" 
                  v-model="asOfMode"
                  class="text-indigo-600 focus:ring-indigo-500 dark:bg-slate-900 dark:border-slate-700" />
                <span>Now (Current time)</span>
              </label>

              <label class="flex items-center space-x-1.5 cursor-pointer font-semibold text-slate-800 dark:text-slate-200">
                <input 
                  type="radio" 
                  value="date" 
                  v-model="asOfMode"
                  class="text-indigo-600 focus:ring-indigo-500 dark:bg-slate-900 dark:border-slate-700" />
                <span>Past statement date</span>
              </label>
            </div>

            <!-- Date Picker when Past Date is selected -->
            <div v-if="asOfMode === 'date'" class="pt-1.5">
              <input 
                v-model="asOfDate"
                type="date"
                class="w-full bg-white dark:bg-slate-900 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs font-mono text-slate-900 dark:text-white focus:outline-none focus:border-indigo-500" />
            </div>

            <!-- Resolved Effective Timestamp Badge -->
            <div class="flex items-center space-x-1.5 text-[11px] font-mono text-indigo-700 dark:text-indigo-300 pt-0.5">
              <span>📍</span>
              <span><strong>Resolved Anchor:</strong> {{ resolvedAnchorLabel }}</span>
            </div>
          </div>

          <!-- Balance Comparison Strip -->
          <div class="grid grid-cols-2 gap-3.5">
            
            <!-- App Calculated Balance -->
            <div class="p-4 rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50/70 dark:bg-slate-800/40 space-y-1">
              <span class="text-[10px] font-mono uppercase font-semibold text-slate-400 block">
                App Ledger Balance
              </span>
              <div class="text-xl font-extrabold font-mono sensitive text-slate-900 dark:text-white">
                {{ formattedCalculatedBalance }}
              </div>
              <p class="text-[11px] text-slate-500 dark:text-slate-400">
                Pre-reconciliation balance calculated up to this cutoff.
              </p>
            </div>

            <!-- Statement Actual Balance Input -->
            <div class="p-4 rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50/70 dark:bg-slate-800/40 space-y-2">
              <div class="flex items-center justify-between">
                <span class="text-[10px] font-mono uppercase font-semibold text-slate-400 block">
                  Statement Balance ({{ currencySymbol }})
                </span>

                <!-- Credit Card Debt Toggle Helper -->
                <div v-if="isCreditCard" class="flex items-center space-x-1 text-[10px] font-mono">
                  <button
                    type="button"
                    @click="cardSign = -1"
                    class="px-1.5 py-0.5 rounded transition font-bold"
                    :class="cardSign === -1 ? 'bg-rose-500 text-white' : 'text-slate-400 hover:text-slate-600 dark:hover:text-slate-300'">
                    Debt (-)
                  </button>
                  <button
                    type="button"
                    @click="cardSign = 1"
                    class="px-1.5 py-0.5 rounded transition font-bold"
                    :class="cardSign === 1 ? 'bg-emerald-500 text-white' : 'text-slate-400 hover:text-slate-600 dark:hover:text-slate-300'">
                    Credit (+)
                  </button>
                </div>
              </div>

              <div class="relative">
                <span class="absolute left-3 top-2.5 text-xs font-mono font-bold text-slate-400">
                  {{ isCreditCard && cardSign === -1 ? `-${currencySymbol}` : currencySymbol }}
                </span>
                <input 
                  v-model.number="enteredBalance"
                  type="number" 
                  step="0.01" 
                  placeholder="0.00"
                  class="w-full bg-white dark:bg-slate-900 border border-brand-border dark:border-brand-darkborder rounded-xl pl-8 pr-3 py-2 text-xs font-mono font-bold text-slate-900 dark:text-white focus:outline-none focus:border-indigo-500" />
              </div>

              <p v-if="isCreditCard" class="text-[10px] text-slate-400">
                {{ cardSign === -1 ? 'Balance owed on credit card.' : 'Positive overpayment / credit balance.' }}
              </p>
            </div>

          </div>

          <!-- Real-Time Discrepancy Card -->
          <div 
            v-if="enteredBalance !== null && !isNaN(enteredBalance)"
            class="p-4 rounded-xl border transition-all space-y-1.5"
            :class="discrepancyPence === 0 
              ? 'border-emerald-200 dark:border-emerald-900/60 bg-emerald-50/50 dark:bg-emerald-950/20' 
              : (discrepancyPence > 0 
                ? 'border-blue-200 dark:border-blue-900/60 bg-blue-50/50 dark:bg-blue-950/20' 
                : 'border-amber-200 dark:border-amber-900/60 bg-amber-50/50 dark:bg-amber-950/20')">
            
            <div class="flex items-center justify-between text-xs">
              <span class="font-bold flex items-center space-x-1.5" :class="discrepancyPence === 0 ? 'text-emerald-800 dark:text-emerald-300' : (discrepancyPence > 0 ? 'text-blue-900 dark:text-blue-300' : 'text-amber-900 dark:text-amber-300')">
                <span>{{ discrepancyPence === 0 ? '✅' : (discrepancyPence > 0 ? '📈' : '📉') }}</span>
                <span>{{ discrepancyTitle }}</span>
              </span>
              <span class="font-mono font-bold text-sm sensitive" :class="discrepancyPence === 0 ? 'text-emerald-700 dark:text-emerald-400' : (discrepancyPence > 0 ? 'text-blue-700 dark:text-blue-400' : 'text-amber-700 dark:text-amber-400')">
                {{ formattedDiscrepancy }}
              </span>
            </div>

            <p class="text-[11px]" :class="discrepancyPence === 0 ? 'text-emerald-700 dark:text-emerald-400' : (discrepancyPence > 0 ? 'text-blue-800 dark:text-blue-400' : 'text-amber-800 dark:text-amber-400')">
              {{ discrepancyExplanation }}
            </p>
          </div>

          <!-- Discrepancy Explanation Note & Optional Missing Transaction Form -->
          <div v-if="discrepancyPence !== 0" class="space-y-3 pt-1">
            
            <!-- Optional Discrepancy Note -->
            <div>
              <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
                Discrepancy Explanation Note (Optional)
              </label>
              <input 
                v-model="notes"
                type="text" 
                placeholder="e.g. Bank fee missing, timing difference on pending deposit"
                class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none" />
              <p class="text-[10px] text-slate-400 mt-1">
                Saved to the observational reconciliation snapshot. Does not alter your ledger or anchor.
              </p>
            </div>

            <!-- Optional Missing Transaction Accordion -->
            <div class="border border-brand-border dark:border-brand-darkborder rounded-xl p-3.5 bg-slate-50/50 dark:bg-slate-800/20 space-y-3">
              <label class="flex items-center justify-between cursor-pointer">
                <div class="flex items-center space-x-2">
                  <input 
                    type="checkbox" 
                    v-model="includeMissingTx"
                    class="rounded border-slate-300 text-indigo-600 focus:ring-0 dark:border-slate-600" />
                  <span class="text-xs font-bold text-slate-800 dark:text-slate-200">
                    Record missing transaction (for cash-flow/spending reports)
                  </span>
                </div>
                <span class="text-xs text-slate-400 font-mono">{{ includeMissingTx ? '▲' : '▼' }}</span>
              </label>

              <div v-if="includeMissingTx" class="space-y-3 pt-2 border-t border-brand-border dark:border-brand-darkborder text-xs">
                
                <div class="grid grid-cols-2 gap-2.5">
                  <div>
                    <label class="block text-[10px] font-mono uppercase font-semibold text-slate-400 mb-1">
                      Type
                    </label>
                    <select 
                      v-model="missingTxType"
                      class="w-full bg-white dark:bg-slate-900 border border-brand-border dark:border-brand-darkborder rounded-lg px-2.5 py-1.5 text-xs text-slate-900 dark:text-white">
                      <option value="expense">Expense</option>
                      <option value="income">Income</option>
                    </select>
                  </div>

                  <div>
                    <label class="block text-[10px] font-mono uppercase font-semibold text-slate-400 mb-1">
                      Amount ({{ currencySymbol }})
                    </label>
                    <input 
                      v-model.number="missingTxAmount"
                      type="number" 
                      step="0.01"
                      class="w-full bg-white dark:bg-slate-900 border border-brand-border dark:border-brand-darkborder rounded-lg px-2.5 py-1.5 text-xs font-mono font-bold text-slate-900 dark:text-white" />
                  </div>
                </div>

                <div class="grid grid-cols-2 gap-2.5">
                  <div>
                    <label class="block text-[10px] font-mono uppercase font-semibold text-slate-400 mb-1">
                      Merchant / Description
                    </label>
                    <input 
                      v-model="missingTxMerchant"
                      type="text"
                      placeholder="e.g. Monthly maintenance fee"
                      class="w-full bg-white dark:bg-slate-900 border border-brand-border dark:border-brand-darkborder rounded-lg px-2.5 py-1.5 text-xs text-slate-900 dark:text-white" />
                  </div>

                  <div>
                    <label class="block text-[10px] font-mono uppercase font-semibold text-slate-400 mb-1">
                      Category
                    </label>
                    <select 
                      v-model="missingTxCategoryId"
                      class="w-full bg-white dark:bg-slate-900 border border-brand-border dark:border-brand-darkborder rounded-lg px-2.5 py-1.5 text-xs text-slate-900 dark:text-white">
                      <option :value="null">Uncategorised</option>
                      <option v-for="cat in compatibleMissingTxCategories" :key="cat.id" :value="cat.id">
                        {{ cat.name }}
                      </option>
                    </select>
                    <p v-if="missingTxCategoryClearedNotice" class="text-[10px] text-amber-600 dark:text-amber-400 mt-1">
                      {{ missingTxCategoryClearedNotice }}
                    </p>
                  </div>
                </div>

                <div>
                  <label class="block text-[10px] font-mono uppercase font-semibold text-slate-400 mb-1">
                    Transaction Date (for cash-flow reports)
                  </label>
                  <input 
                    v-model="missingTxDate"
                    type="date"
                    class="w-full bg-white dark:bg-slate-900 border border-brand-border dark:border-brand-darkborder rounded-lg px-2.5 py-1.5 text-xs font-mono text-slate-900 dark:text-white" />
                </div>

                <!-- Guidance Note -->
                <div class="p-2.5 rounded-lg bg-indigo-50/70 dark:bg-indigo-950/40 text-[11px] text-indigo-900 dark:text-indigo-300">
                  ℹ️ This transaction appears in Cash-Flow and Spending reports, but is treated as already included in your confirmed anchor balance and will <strong>not double-deduct</strong> from this account.
                </div>

              </div>

            </div>

          </div>

          <!-- General Note Field when discrepancy is 0 -->
          <div v-else class="pt-1">
            <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
              Reconciliation Notes (Optional)
            </label>
            <input 
              v-model="notes"
              type="text" 
              placeholder="e.g. Monthly statement check"
              class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none" />
          </div>

        </div>

        <!-- Action Buttons -->
        <div class="pt-2 flex items-center justify-end space-x-2.5 border-t border-brand-border dark:border-brand-darkborder">
          <button 
            type="button" 
            @click="emitClose" 
            class="px-4 py-2 text-xs font-semibold rounded-full border border-brand-border dark:border-brand-darkborder hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300 transition">
            Cancel
          </button>

          <button 
            type="button" 
            @click="handleSubmit" 
            :disabled="isSubmitting || enteredBalance === null || isNaN(enteredBalance)"
            class="px-5 py-2 text-xs font-semibold rounded-full shadow-sm transition disabled:opacity-50 bg-slate-900 text-white dark:bg-white dark:text-slate-900 hover:opacity-90">
            {{ isSubmitting ? 'Confirming...' : `Confirm Statement Balance (${formattedEnteredBalance})` }}
          </button>
        </div>

      </div>

      <!-- Tab 2: Reconciliation History Flow -->
      <div v-else-if="activeTab === 'history'" class="space-y-4 overflow-y-auto pr-1">
        
        <div v-if="historyLoading" class="h-36 rounded-xl bg-slate-100 dark:bg-slate-800/40 animate-pulse"></div>

        <div v-else-if="snapshots.length === 0" class="text-center py-10 space-y-2">
          <div class="text-2xl">⚖️</div>
          <p class="text-xs font-semibold text-slate-800 dark:text-slate-200">No reconciliation history yet</p>
          <p class="text-[11px] text-slate-500 max-w-sm mx-auto">
            Use the "Reconcile Balance" tab to confirm your first ground-truth statement balance checkpoint.
          </p>
        </div>

        <div v-else class="space-y-2.5">
          <div 
            v-for="snap in snapshots"
            :key="snap.id"
            class="p-3.5 rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50/50 dark:bg-slate-800/30 hover:bg-slate-50 dark:hover:bg-slate-800/60 transition flex items-center justify-between text-xs">
            
            <div class="space-y-1">
              <div class="flex items-center space-x-2">
                <span class="font-mono font-bold text-slate-900 dark:text-white">
                  {{ formatDate(snap.snapshot_date) }}
                </span>
                <span 
                  class="px-2 py-0.2 rounded-full text-[10px] font-mono font-bold"
                  :class="snap.discrepancy_pence === 0 ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300' : 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300'">
                  {{ snap.discrepancy_pence === 0 ? 'Balanced' : `Diff: ${snap.formatted_discrepancy}` }}
                </span>
              </div>
              
              <div class="text-[11px] text-slate-500 dark:text-slate-400 font-mono flex items-center space-x-3">
                <span>Statement: <strong class="sensitive">{{ snap.formatted_actual_balance }}</strong></span>
                <span>Calculated: <strong class="sensitive">{{ snap.formatted_calculated_balance }}</strong></span>
              </div>

              <div v-if="snap.notes" class="text-[11px] text-slate-600 dark:text-slate-300 italic pt-0.5">
                "{{ snap.notes }}"
              </div>
            </div>

            <!-- Delete Snapshot Button -->
            <button
              @click="deleteSnapshot(snap.id)"
              class="text-slate-400 hover:text-rose-500 transition p-1.5 rounded-lg hover:bg-rose-50 dark:hover:bg-rose-950/40"
              title="Delete this snapshot record">
              🗑️
            </button>

          </div>
        </div>

      </div>

    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import type { Account, AccountSnapshotItem, AccountType, ReconciliationSummaryResponse } from '../types';
import { api } from '../api/client';
import { useTransactionsStore } from '../stores/transactions';
import { filterCategoriesForTransactionType, isCategoryCompatibleWithTransaction } from '../utils/categoryPurpose';

const txStore = useTransactionsStore();

const props = defineProps<{
  isOpen: boolean;
  account: Account | null;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'reconciled'): void;
}>();

const activeTab = ref<'reconcile' | 'history'>('reconcile');
const enteredBalance = ref<number | null>(null);
const cardSign = ref<number>(-1); // -1 for debt, 1 for credit
const asOfMode = ref<'now' | 'date'>('now');
const asOfDate = ref<string>(new Date().toISOString().split('T')[0]);
const notes = ref<string>('');

// Optional missing transaction state
const includeMissingTx = ref<boolean>(false);
const missingTxType = ref<'expense' | 'income'>('expense');
const missingTxAmount = ref<number | null>(null);
const missingTxMerchant = ref<string>('');
const missingTxCategoryId = ref<number | null>(null);
const missingTxDate = ref<string>(new Date().toISOString().split('T')[0]);
const missingTxNotes = ref<string>('');
const missingTxCategoryClearedNotice = ref<string | null>(null);

const compatibleMissingTxCategories = computed(() =>
  filterCategoriesForTransactionType(txStore.categories, missingTxType.value)
);

watch(missingTxType, (nextType) => {
  if (
    missingTxCategoryId.value !== null &&
    !isCategoryCompatibleWithTransaction(txStore.categories, missingTxCategoryId.value, nextType)
  ) {
    missingTxCategoryId.value = null;
    missingTxCategoryClearedNotice.value = `Cleared previous category because ${nextType} transactions require an ${nextType} category.`;
  } else {
    missingTxCategoryClearedNotice.value = null;
  }
});

const isSubmitting = ref(false);
const historyLoading = ref(false);
const errorMessage = ref<string | null>(null);
const successMessage = ref<string | null>(null);
const reconciliationSummary = ref<ReconciliationSummaryResponse | null>(null);

const snapshots = ref<AccountSnapshotItem[]>([]);

const isCreditCard = computed(() => props.account?.account_type === 'credit_card');
const currencySymbol = computed(() => {
  const curr = props.account?.currency || 'GBP';
  return curr === 'GBP' ? '£' : (curr === 'EUR' ? '€' : (curr === 'USD' ? '$' : `${curr} `));
});

const calculatedBalancePence = computed(() => {
  if (reconciliationSummary.value) {
    return reconciliationSummary.value.calculated_balance_pence;
  }
  return props.account?.current_balance_pence || 0;
});

const formattedCalculatedBalance = computed(() => {
  if (reconciliationSummary.value) {
    return reconciliationSummary.value.formatted_calculated_balance;
  }
  return props.account?.formatted_balance || '£0.00';
});

const appTimezone = computed(() => reconciliationSummary.value?.app_timezone || 'Europe/London');

const resolvedAnchorLabel = computed(() => {
  if (asOfMode.value === 'now') {
    return `Now (${new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })} in ${appTimezone.value})`;
  }
  return `End of day ${asOfDate.value} (23:59:59 in ${appTimezone.value})`;
});

// Compute signed actual balance in pence
const signedActualPence = computed(() => {
  if (enteredBalance.value === null || isNaN(enteredBalance.value)) return 0;
  const raw = Math.round(Math.abs(enteredBalance.value) * 100);
  if (isCreditCard.value) {
    return cardSign.value === -1 ? -raw : raw;
  }
  return enteredBalance.value < 0 ? -raw : raw;
});

const formattedEnteredBalance = computed(() => {
  const sym = currencySymbol.value;
  const pounds = Math.abs(signedActualPence.value) / 100;
  const formatted = pounds.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (isCreditCard.value && signedActualPence.value < 0) {
    return `-${sym}${formatted}`;
  }
  return `${sym}${formatted}`;
});

const discrepancyPence = computed(() => {
  if (enteredBalance.value === null || isNaN(enteredBalance.value)) return 0;
  return signedActualPence.value - calculatedBalancePence.value;
});

const formattedDiscrepancy = computed(() => {
  const p = discrepancyPence.value;
  const sym = currencySymbol.value;
  const absPounds = (Math.abs(p) / 100).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (p === 0) return `${sym}0.00`;
  return p > 0 ? `+${sym}${absPounds}` : `-${sym}${absPounds}`;
});

const formattedAbsDiscrepancy = computed(() => {
  const sym = currencySymbol.value;
  const absPounds = (Math.abs(discrepancyPence.value) / 100).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `${sym}${absPounds}`;
});

const discrepancyTitle = computed(() => {
  if (discrepancyPence.value === 0) return 'Exact Match';
  if (discrepancyPence.value > 0) return 'Statement Higher (+ Difference)';
  return 'Statement Lower (- Difference)';
});

const discrepancyExplanation = computed(() => {
  const diffStr = formattedAbsDiscrepancy.value;
  if (discrepancyPence.value === 0) {
    return 'Your statement balance matches the app ledger balance perfectly.';
  }
  if (discrepancyPence.value > 0) {
    return `Your bank/card statement has ${diffStr} more than the app ledger (e.g. unrecorded deposit, credit adjustment, or missing income).`;
  }
  return `Your bank/card statement has ${diffStr} less than the app ledger (e.g. unrecorded expense, bank charge, or higher card debt).`;
});

// Auto-fill missing transaction defaults when discrepancy changes
watch(discrepancyPence, (diff) => {
  if (diff !== 0) {
    missingTxType.value = diff < 0 ? 'expense' : 'income';
    missingTxAmount.value = Math.abs(diff) / 100;
    missingTxDate.value = asOfMode.value === 'date' ? asOfDate.value : new Date().toISOString().split('T')[0];
  }
});

watch(() => props.isOpen, async (open) => {
  if (open && props.account) {
    resetForm();
    await Promise.all([
      loadSummary(),
      loadHistory(),
      txStore.categories.length === 0 ? txStore.loadCategories() : Promise.resolve(),
    ]);
  }
});

function resetForm() {
  activeTab.value = 'reconcile';
  errorMessage.value = null;
  successMessage.value = null;
  notes.value = '';
  asOfMode.value = 'now';
  asOfDate.value = new Date().toISOString().split('T')[0];
  includeMissingTx.value = false;
  missingTxAmount.value = null;
  missingTxMerchant.value = '';
  missingTxCategoryId.value = null;
  missingTxNotes.value = '';

  if (props.account) {
    const balPounds = (props.account.current_balance_pence / 100);
    if (props.account.account_type === 'credit_card') {
      cardSign.value = balPounds < 0 ? -1 : 1;
      enteredBalance.value = Math.abs(balPounds);
    } else {
      enteredBalance.value = balPounds;
    }
  }
}

async function loadSummary() {
  if (!props.account) return;
  try {
    reconciliationSummary.value = await api.getReconciliationSummary(props.account.id);
  } catch (err: any) {
    console.error('Failed to load reconciliation summary', err);
  }
}

async function loadHistory() {
  if (!props.account) return;
  historyLoading.value = true;
  try {
    snapshots.value = await api.getReconciliationSnapshots(props.account.id);
  } catch (err: any) {
    console.error('Failed to load snapshots history', err);
  } finally {
    historyLoading.value = false;
  }
}

function switchToHistoryTab() {
  activeTab.value = 'history';
  loadHistory();
}

async function handleSubmit() {
  if (!props.account || enteredBalance.value === null || isNaN(enteredBalance.value)) return;
  isSubmitting.value = true;
  errorMessage.value = null;
  successMessage.value = null;

  try {
    const actualPounds = signedActualPence.value / 100;
    const payload: any = {
      actual_balance: actualPounds,
      as_of_mode: asOfMode.value,
      as_of_date: asOfMode.value === 'date' ? asOfDate.value : undefined,
      notes: notes.value ? notes.value.trim() : undefined,
    };

    if (includeMissingTx.value && missingTxAmount.value && missingTxAmount.value > 0) {
      payload.missing_transaction = {
        transaction_type: missingTxType.value,
        amount: missingTxAmount.value,
        merchant: missingTxMerchant.value.trim() || 'Missing Transaction',
        category_id: missingTxCategoryId.value || undefined,
        transaction_date: missingTxDate.value || asOfDate.value,
        notes: missingTxNotes.value ? missingTxNotes.value.trim() : undefined,
      };
    }

    const res = await api.recordReconciliationSnapshot(props.account.id, payload);

    successMessage.value = res.explanation;

    emit('reconciled');
    await Promise.all([loadSummary(), loadHistory()]);

    setTimeout(() => {
      emitClose();
    }, 1500);

  } catch (err: any) {
    errorMessage.value = err.message || 'Failed to save reconciliation snapshot.';
  } finally {
    isSubmitting.value = false;
  }
}

async function deleteSnapshot(snapshotId: number) {
  if (!props.account) return;
  if (!confirm('Are you sure you want to delete this historical snapshot record?')) return;
  try {
    await api.deleteReconciliationSnapshot(props.account.id, snapshotId);
    snapshots.value = snapshots.value.filter(s => s.id !== snapshotId);
    emit('reconciled');
  } catch (err: any) {
    alert(err.message || 'Failed to delete snapshot.');
  }
}

function emitClose() {
  emit('close');
}

function formatAccountType(type: AccountType): string {
  switch (type) {
    case 'current': return 'Current Account';
    case 'savings': return 'Savings Account';
    case 'cash': return 'Cash Account';
    case 'credit_card': return 'Credit Card';
    case 'investment': return 'Investment Portfolio';
    default: return type;
  }
}

function formatDate(isoStr: string): string {
  const d = new Date(isoStr);
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}
</script>
