<template>
  <div 
    v-if="isOpen && transaction" 
    class="fixed inset-0 z-50 bg-slate-950/40 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto animate-fadeIn"
    @click.self="$emit('close')">
    <section 
      role="dialog" 
      aria-modal="true" 
      aria-labelledby="edit-tx-title"
      class="bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-5 transition-all my-8">
      
      <!-- Modal Header -->
      <div class="flex items-center justify-between pb-3 border-b border-brand-border dark:border-brand-darkborder">
        <div>
          <h2 id="edit-tx-title" class="font-bold text-slate-900 dark:text-white">Edit Transaction #{{ transaction.id }}</h2>
          <p class="text-xs text-slate-500 dark:text-slate-400">Modify transaction details, category, or transfer routing.</p>
        </div>
        <button 
          @click="$emit('close')" 
          class="text-slate-400 hover:text-slate-600 dark:hover:text-white text-lg"
          aria-label="Close dialog">
          &times;
        </button>
      </div>

      <!-- Type Switcher -->
      <div class="flex rounded-xl bg-slate-100 dark:bg-slate-800/80 p-1 border border-brand-border dark:border-brand-darkborder">
        <button
          type="button"
          @click="txType = 'expense'"
          class="flex-1 py-1.5 text-xs font-semibold rounded-lg transition"
          :class="txType === 'expense' 
            ? 'bg-white dark:bg-slate-700 text-rose-600 dark:text-rose-400 shadow-sm' 
            : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'">
          Expense
        </button>
        <button
          type="button"
          @click="txType = 'income'"
          class="flex-1 py-1.5 text-xs font-semibold rounded-lg transition"
          :class="txType === 'income' 
            ? 'bg-white dark:bg-slate-700 text-emerald-600 dark:text-emerald-400 shadow-sm' 
            : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'">
          Income
        </button>
        <button
          type="button"
          @click="txType = 'transfer'"
          class="flex-1 py-1.5 text-xs font-semibold rounded-lg transition"
          :class="txType === 'transfer' 
            ? 'bg-white dark:bg-slate-700 text-indigo-600 dark:text-indigo-400 shadow-sm' 
            : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'">
          Transfer
        </button>
        <button
          type="button"
          @click="txType = 'adjustment'"
          class="flex-1 py-1.5 text-xs font-semibold rounded-lg transition"
          :class="txType === 'adjustment' 
            ? 'bg-white dark:bg-slate-700 text-amber-600 dark:text-amber-400 shadow-sm' 
            : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'">
          Adjustment
        </button>
      </div>

      <form @submit.prevent="handleSubmit" class="space-y-4">
        <!-- Error Banner -->
        <div v-if="errorMessage" class="p-3 rounded-lg bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 text-rose-600 dark:text-rose-400 text-xs">
          {{ errorMessage }}
        </div>

        <!-- Date & Amount Row -->
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
              Date
            </label>
            <input 
              v-model="txDate" 
              type="date" 
              required
              class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs font-mono text-slate-900 dark:text-white focus:outline-none" />
          </div>

          <div>
            <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
              Amount ({{ baseCurrencySymbol }})
            </label>
            <div class="relative">
              <span class="absolute left-3 top-2 text-xs font-bold text-slate-400">{{ baseCurrencySymbol }}</span>
              <input 
                v-model.number="amount" 
                type="number" 
                step="0.01" 
                min="0.01" 
                required
                placeholder="0.00"
                @input="onBaseAmountInput"
                class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl pl-7 pr-3 py-2 text-xs font-mono font-bold text-slate-900 dark:text-white focus:outline-none" />
            </div>
          </div>
        </div>

        <!-- Foreign Currency Toggle & Configuration (Expense/Income only) -->
        <div v-if="txType !== 'transfer'" class="rounded-xl border border-brand-border dark:border-brand-darkborder p-3 bg-slate-50/50 dark:bg-slate-800/40 space-y-3">
          <div class="flex items-center justify-between">
            <label class="flex items-center space-x-2 cursor-pointer select-none">
              <input 
                type="checkbox" 
                v-model="isForeign" 
                class="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 w-4 h-4" />
              <span class="text-xs font-semibold text-slate-700 dark:text-slate-300">
                Foreign Currency Transaction
              </span>
            </label>
            <span v-if="isForeign" class="text-[10px] font-mono text-slate-400">
              Preserves original provenance
            </span>
          </div>

          <!-- Foreign Details (Expanded when checked) -->
          <div v-if="isForeign" class="space-y-3 pt-2 border-t border-brand-border/60 dark:border-brand-darkborder/60">
            <!-- Currency & Original Amount Grid -->
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
                  Original Currency
                </label>
                <select 
                  v-model="origCurrency"
                  @change="handleOrigCurrencyChange"
                  class="w-full bg-white dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none">
                  <option 
                    v-for="c in foreignCurrencyOptions" 
                    :key="c.code" 
                    :value="c.code">
                    {{ c.code }} - {{ c.name }} ({{ c.symbol }})
                  </option>
                </select>
              </div>

              <div>
                <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
                  Original Amount ({{ selectedCurrencySpec.symbol }})
                </label>
                <div class="relative">
                  <span class="absolute left-3 top-2 text-xs font-mono font-bold text-slate-400">
                    {{ selectedCurrencySpec.symbol }}
                  </span>
                  <input 
                    v-model.number="origAmount" 
                    type="number" 
                    :step="selectedCurrencyStep"
                    min="0.0001" 
                    required 
                    @input="onOrigAmountInput"
                    placeholder="0.00" 
                    class="w-full bg-white dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl pl-8 pr-3 py-2 text-xs font-mono font-bold text-slate-900 dark:text-white focus:outline-none" />
                </div>
              </div>
            </div>

            <!-- Mode Selector: Bank Charge vs Rate -->
            <div class="space-y-1.5">
              <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500">
                Conversion Method
              </label>
              <div class="flex flex-col sm:flex-row gap-2">
                <button
                  type="button"
                  @click="setForeignMode('actual')"
                  class="flex-1 px-3 py-2 text-xs rounded-xl border text-left transition"
                  :class="foreignMode === 'actual' 
                    ? 'border-indigo-500 bg-indigo-50/50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 font-semibold' 
                    : 'border-brand-border dark:border-brand-darkborder text-slate-600 dark:text-slate-400 hover:bg-white dark:hover:bg-slate-800'">
                  <div>Actual bank charge ({{ baseCurrencyCode }})</div>
                  <div class="text-[10px] font-normal opacity-80 mt-0.5">Enter the exact amount billed to your account</div>
                </button>
                <button
                  type="button"
                  @click="setForeignMode('rate')"
                  class="flex-1 px-3 py-2 text-xs rounded-xl border text-left transition"
                  :class="foreignMode === 'rate' 
                    ? 'border-indigo-500 bg-indigo-50/50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 font-semibold' 
                    : 'border-brand-border dark:border-brand-darkborder text-slate-600 dark:text-slate-400 hover:bg-white dark:hover:bg-slate-800'">
                  <div>Exchange rate</div>
                  <div class="text-[10px] font-normal opacity-80 mt-0.5">Calculate {{ baseCurrencyCode }} amount using rate</div>
                </button>
              </div>
            </div>

            <!-- Exchange Rate Input (When Mode is 'rate') -->
            <div v-if="foreignMode === 'rate'">
              <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
                Exchange Rate ({{ baseCurrencyCode }} per 1 {{ origCurrency }})
              </label>
              <input 
                v-model.number="exchangeRate" 
                type="number" 
                step="0.00000001" 
                min="0.00000001" 
                required
                @input="onRateInput"
                placeholder="e.g. 0.78500000" 
                class="w-full bg-white dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs font-mono text-slate-900 dark:text-white focus:outline-none" />
            </div>

            <!-- Implied Effective Rate Badge (When Mode is 'actual') -->
            <div v-if="foreignMode === 'actual' && impliedRate" class="p-2.5 rounded-lg bg-indigo-50/70 dark:bg-indigo-950/30 border border-indigo-200 dark:border-indigo-900/60 text-[11px] text-indigo-900 dark:text-indigo-300 font-mono flex items-center justify-between">
              <span>Implied Effective Rate:</span>
              <span class="font-bold">1 {{ origCurrency }} = {{ impliedRate }} {{ baseCurrencyCode }}</span>
            </div>
            <p v-if="foreignMode === 'actual' && impliedRate" class="text-[10px] text-slate-400">
              * The posted {{ baseCurrencyCode }} amount is permanent in the ledger; this rate is derived, not a market rate.
            </p>
          </div>
        </div>

        <!-- Merchant / Description -->
        <div>
          <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
            {{ txType === 'transfer' ? 'Transfer Reference' : 'Merchant / Payee (Optional)' }}
          </label>
          <input 
            v-model="merchant" 
            type="text" 
            :placeholder="txType === 'transfer' ? 'Internal Transfer' : 'e.g. Tesco (leave blank if unrecorded)'"
            class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none" />
        </div>

        <!-- Accounts Grid -->
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <!-- Source Account -->
          <div>
            <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
              {{ txType === 'transfer' ? 'From Account' : 'Account (Optional)' }}
            </label>
            <select 
              v-model="accountId" 
              :required="txType === 'transfer' || txType === 'adjustment'"
              class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none">
              <option :value="null">Unassigned (assign later)</option>
              <option v-for="acc in accountsStore.accounts" :key="acc.id" :value="acc.id">
                {{ acc.name }} ({{ acc.currency }})
              </option>
            </select>
          </div>

          <!-- Destination Account (Only for Transfer) -->
          <div v-if="txType === 'transfer'">
            <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
              To Account
            </label>
            <select 
              v-model="destinationAccountId" 
              required
              class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none">
              <option 
                v-for="acc in destinationAccounts" 
                :key="acc.id" 
                :value="acc.id">
                {{ acc.name }} ({{ acc.currency }})
              </option>
            </select>
          </div>
        </div>

        <!-- Category & Expense Nature (Category for Expense/Income; Nature only for Expense) -->
        <div v-if="txType === 'expense' || txType === 'income'" class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div :class="txType === 'income' ? 'sm:col-span-2' : ''">
            <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
              {{ txType === 'income' ? 'Income Category' : 'Expense Category' }}
            </label>
            <select 
              v-model="categoryId" 
              @change="onCategoryChange"
              class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none">
              <option :value="null">Uncategorised</option>
              <option v-for="cat in compatibleCategories" :key="cat.id" :value="cat.id">
                {{ cat.name }}
              </option>
              <option 
                v-if="!hasCategoryInList && categoryId && transaction?.category_name && (!transaction?.category_type || transaction.category_type === txType)" 
                :value="categoryId">
                {{ transaction.category_name }} (Archived)
              </option>
            </select>
            <p v-if="categoryClearedNotice" class="text-[10px] text-amber-600 dark:text-amber-400 mt-1">
              {{ categoryClearedNotice }}
            </p>
          </div>

          <div v-if="txType === 'expense'">
            <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
              Expense Nature (Override)
            </label>
            <select 
              v-model="expenseNature" 
              class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none">
              <option value="fixed">Fixed (Committed)</option>
              <option value="variable">Variable (Discretionary)</option>
              <option value="unclassified">Unclassified</option>
            </select>
          </div>
        </div>
        <p v-else-if="categoryClearedNotice" class="text-[11px] text-amber-600 dark:text-amber-400 bg-amber-50/70 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/50 rounded-xl px-3 py-2">
          {{ categoryClearedNotice }}
        </p>

        <!-- Notes -->
        <div>
          <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
            Notes (Optional)
          </label>
          <input 
            v-model="notes" 
            type="text" 
            placeholder="Add additional context or notes"
            class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none" />
        </div>

        <!-- Modal Footer -->
        <div class="pt-3 flex items-center justify-end space-x-2.5 border-t border-brand-border dark:border-brand-darkborder">
          <button 
            type="button" 
            @click="$emit('close')" 
            class="px-4 py-2 text-xs font-semibold rounded-full border border-brand-border dark:border-brand-darkborder hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300 transition">
            Cancel
          </button>
          <button 
            type="submit" 
            :disabled="isSubmitting"
            class="px-5 py-2 text-xs font-semibold rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 shadow-sm hover:opacity-90 transition disabled:opacity-50">
            {{ isSubmitting ? 'Saving Changes...' : 'Save Changes' }}
          </button>
        </div>
      </form>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import type { Transaction, TransactionType, ExpenseNature, TransactionUpdatePayload } from '../types';
import { useAccountsStore } from '../stores/accounts';
import { useTransactionsStore } from '../stores/transactions';
import { useSystemStore } from '../stores/system';
import { filterCategoriesForTransactionType, isCategoryCompatibleWithTransaction } from '../utils/categoryPurpose';

const props = defineProps<{
  isOpen: boolean;
  transaction: Transaction | null;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'saved'): void;
}>();

const accountsStore = useAccountsStore();
const txStore = useTransactionsStore();
const systemStore = useSystemStore();

const txType = ref<TransactionType>('expense');
const txDate = ref<string>('');
const amount = ref<number | null>(null);
const merchant = ref<string>('');
const accountId = ref<number | null>(null);
const destinationAccountId = ref<number | null>(null);
const categoryId = ref<number | null>(null);
const categoryClearedNotice = ref<string | null>(null);
const isPopulatingForm = ref(false);
const expenseNature = ref<ExpenseNature>('unclassified');
const notes = ref<string>('');

// Foreign Currency State
const isForeign = ref(false);
const origCurrency = ref('USD');
const origAmount = ref<number | ''>('');
const foreignMode = ref<'actual' | 'rate'>('actual');
const exchangeRate = ref<number | ''>('');

const isSubmitting = ref(false);
const errorMessage = ref<string | null>(null);

const baseCurrencyCode = computed(() => systemStore.config?.base_currency || 'GBP');
const baseCurrencySymbol = computed(() => systemStore.config?.base_currency_symbol || '£');

const foreignCurrencyOptions = computed(() => {
  if (systemStore.config?.supported_currencies) {
    return Object.values(systemStore.config.supported_currencies)
      .filter(c => c.code !== baseCurrencyCode.value)
      .map(c => ({
        code: c.code,
        symbol: c.symbol,
        name: c.name,
        precision: c.precision,
      }));
  }
  return [
    { code: 'USD', symbol: '$', name: 'US Dollar', precision: 2 },
    { code: 'EUR', symbol: '€', name: 'Euro', precision: 2 },
    { code: 'CAD', symbol: 'CA$', name: 'Canadian Dollar', precision: 2 },
    { code: 'AUD', symbol: 'A$', name: 'Australian Dollar', precision: 2 },
    { code: 'JPY', symbol: '¥', name: 'Japanese Yen', precision: 0 },
    { code: 'CHF', symbol: 'CHF', name: 'Swiss Franc', precision: 2 },
  ];
});

const selectedCurrencySpec = computed(() => {
  const found = foreignCurrencyOptions.value.find(c => c.code === origCurrency.value);
  return found || { code: origCurrency.value, symbol: origCurrency.value, precision: 2, name: origCurrency.value };
});

const selectedCurrencyStep = computed(() => {
  const p = selectedCurrencySpec.value.precision;
  if (p === 0) return '1';
  if (p === 3) return '0.001';
  return '0.01';
});

const impliedRate = computed(() => {
  if (!isForeign.value || !origAmount.value || !amount.value) return null;
  const o = Number(origAmount.value);
  const b = Number(amount.value);
  if (o <= 0 || b <= 0) return null;
  return (b / o).toFixed(6);
});

function handleOrigCurrencyChange() {
  if (foreignMode.value === 'rate') {
    recalculateFromRate();
  }
}

function setForeignMode(mode: 'actual' | 'rate') {
  foreignMode.value = mode;
  if (mode === 'rate') {
    if (impliedRate.value && !exchangeRate.value) {
      exchangeRate.value = Number(impliedRate.value);
    }
    recalculateFromRate();
  }
}

function onOrigAmountInput() {
  if (foreignMode.value === 'rate') {
    recalculateFromRate();
  }
}

function onRateInput() {
  if (foreignMode.value === 'rate') {
    recalculateFromRate();
  }
}

function onBaseAmountInput() {
  if (foreignMode.value === 'rate') {
    if (origAmount.value && Number(origAmount.value) > 0 && amount.value && Number(amount.value) > 0) {
      exchangeRate.value = Number((Number(amount.value) / Number(origAmount.value)).toFixed(8));
    }
  }
}

function recalculateFromRate() {
  if (origAmount.value && exchangeRate.value) {
    const o = Number(origAmount.value);
    const r = Number(exchangeRate.value);
    if (o > 0 && r > 0) {
      amount.value = Number((o * r).toFixed(2));
    }
  }
}

const destinationAccounts = computed(() => {
  return accountsStore.accounts.filter(a => a.id !== accountId.value);
});

const compatibleCategories = computed(() =>
  filterCategoriesForTransactionType(txStore.categories, txType.value)
);

const hasCategoryInList = computed(() => {
  if (!categoryId.value) return true;
  return compatibleCategories.value.some(c => c.id === categoryId.value);
});

watch(txType, (nextType) => {
  if (isPopulatingForm.value) return;
  if (categoryId.value !== null) {
    const inStore = isCategoryCompatibleWithTransaction(txStore.categories, categoryId.value, nextType);
    const archivedMatch = Boolean(
      props.transaction &&
      props.transaction.category_id === categoryId.value &&
      (props.transaction.category_type || 'expense') === nextType
    );
    if (!inStore && !archivedMatch) {
      categoryId.value = null;
      expenseNature.value = 'unclassified';
      categoryClearedNotice.value =
        nextType === 'transfer' || nextType === 'adjustment'
          ? `Cleared previous category because ${nextType} entries do not use categories.`
          : `Cleared incompatible category because ${nextType} transactions require an ${nextType} category.`;
      return;
    }
  }
  if (nextType !== 'expense') {
    expenseNature.value = 'unclassified';
  }
  categoryClearedNotice.value = null;
});

watch(() => props.isOpen, (open) => {
  if (open && props.transaction) {
    populateForm(props.transaction);
  }
});

onMounted(() => {
  if (!systemStore.config) {
    systemStore.loadConfig();
  }
});

function populateForm(tx: Transaction) {
  isPopulatingForm.value = true;
  errorMessage.value = null;
  categoryClearedNotice.value = null;
  txType.value = tx.transaction_type;
  txDate.value = tx.transaction_date ? tx.transaction_date.split('T')[0] : '';
  amount.value = tx.amount_pounds;
  merchant.value = tx.merchant || '';
  accountId.value = tx.account_id ?? null;
  destinationAccountId.value = tx.destination_account_id || null;
  categoryId.value = tx.category_id || null;
  expenseNature.value = tx.expense_nature || 'unclassified';
  notes.value = tx.notes || '';
  isPopulatingForm.value = false;

  if (tx.original_currency && tx.original_amount) {
    isForeign.value = true;
    origCurrency.value = tx.original_currency;
    origAmount.value = tx.original_amount;
    exchangeRate.value = tx.exchange_rate || '';
    foreignMode.value = tx.is_implied_rate ? 'actual' : (tx.exchange_rate ? 'rate' : 'actual');
  } else {
    isForeign.value = false;
    origCurrency.value = 'USD';
    origAmount.value = '';
    exchangeRate.value = '';
    foreignMode.value = 'actual';
  }
}

function onCategoryChange() {
  categoryClearedNotice.value = null;
  if (categoryId.value && txType.value === 'expense') {
    const cat = txStore.categories.find(c => c.id === categoryId.value);
    if (cat && cat.default_expense_nature !== 'unclassified') {
      expenseNature.value = cat.default_expense_nature;
    }
  }
}

async function handleSubmit() {
  if (!props.transaction) return;
  if (txType.value === 'transfer' || txType.value === 'adjustment') {
    if (!accountId.value) {
      errorMessage.value = `Account is required for ${txType.value} transactions.`;
      return;
    }
  }
  if (amount.value === null || amount.value <= 0) {
    errorMessage.value = 'Amount must be greater than zero.';
    return;
  }
  if (txType.value === 'transfer') {
    if (!destinationAccountId.value) {
      errorMessage.value = 'Destination account is required for transfers.';
      return;
    }
    if (destinationAccountId.value === accountId.value) {
      errorMessage.value = 'Source and destination accounts must be distinct.';
      return;
    }
  }

  if (isForeign.value && txType.value !== 'transfer') {
    if (!origAmount.value || Number(origAmount.value) <= 0) {
      errorMessage.value = 'Please enter a valid original amount for the foreign transaction.';
      return;
    }
    if (foreignMode.value === 'rate' && (!exchangeRate.value || Number(exchangeRate.value) <= 0)) {
      errorMessage.value = 'Please enter a valid positive exchange rate.';
      return;
    }
  }

  isSubmitting.value = true;
  errorMessage.value = null;

  try {
    const payload: TransactionUpdatePayload = {
      transaction_type: txType.value,
      transaction_date: txDate.value ? `${txDate.value}T12:00:00Z` : undefined,
      amount: amount.value,
      merchant: merchant.value ? merchant.value.trim() : (txType.value === 'transfer' ? 'Internal Transfer' : undefined),
      account_id: accountId.value || null,
      destination_account_id: txType.value === 'transfer' ? destinationAccountId.value : null,
      category_id: (txType.value === 'expense' || txType.value === 'income') ? categoryId.value : null,
      expense_nature: txType.value === 'expense' ? expenseNature.value : 'unclassified',
      notes: notes.value || undefined,
    };

    if (isForeign.value && txType.value !== 'transfer' && origAmount.value && origCurrency.value) {
      payload.original_amount = Number(origAmount.value);
      payload.original_currency = origCurrency.value;
      if (foreignMode.value === 'rate' && exchangeRate.value) {
        payload.exchange_rate = Number(exchangeRate.value);
      } else {
        payload.exchange_rate = null;
      }
    } else {
      payload.original_amount = null;
      payload.original_currency = null;
      payload.exchange_rate = null;
    }

    await txStore.updateTransaction(props.transaction.id, payload);

    emit('saved');
    emit('close');
  } catch (err: any) {
    errorMessage.value = err.message || 'Failed to update transaction.';
  } finally {
    isSubmitting.value = false;
  }
}
</script>
