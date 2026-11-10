<template>
  <div v-if="isOpen && item" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fadeIn" @keydown.esc="handleClose">
    <div 
      class="bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder rounded-2xl w-full max-w-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
      data-testid="split-expense-modal"
    >
      <!-- Modal Header -->
      <div class="px-6 py-4 border-b border-brand-border dark:border-brand-darkborder flex items-center justify-between shrink-0">
        <div class="flex items-center space-x-2.5">
          <span class="p-2 rounded-xl bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 text-sm">
            ✂️
          </span>
          <div>
            <h3 class="text-sm sm:text-base font-bold text-slate-900 dark:text-white">
              {{ isConfirmingApproval ? 'Confirm Ledger Approval' : 'Split Receipt Expense' }}
            </h3>
            <p class="text-[11px] text-slate-500 dark:text-slate-400">
              {{ isConfirmingApproval ? 'Review shared details and allocations before approving to the Ledger.' : 'Divide a single receipt payment into multiple categorized expense rows.' }}
            </p>
          </div>
        </div>
        <button 
          @click="handleClose" 
          type="button"
          class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 text-xl font-semibold leading-none p-1">
          &times;
        </button>
      </div>

      <!-- Modal Body (Scrollable) -->
      <div class="p-6 overflow-y-auto space-y-5 flex-1">

        <!-- ==================== CONFIRMATION VIEW ==================== -->
        <div v-if="isConfirmingApproval" class="space-y-4" data-testid="split-confirmation-view">
          <div class="p-4 rounded-xl border border-indigo-200 dark:border-indigo-900/50 bg-indigo-50/60 dark:bg-indigo-950/30 space-y-3">
            <h4 class="text-xs font-bold uppercase tracking-wider text-indigo-950 dark:text-indigo-200 flex items-center space-x-1.5">
              <span>📋</span>
              <span>Shared Transaction Provenance</span>
            </h4>
            <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <div>
                <span class="text-[10px] text-slate-500 uppercase font-mono block">Merchant</span>
                <span class="font-bold text-slate-900 dark:text-white">{{ sharedMerchant || 'Receipt Purchase' }}</span>
              </div>
              <div>
                <span class="text-[10px] text-slate-500 uppercase font-mono block">Transaction Date</span>
                <span class="font-bold text-slate-900 dark:text-white">{{ sharedDate || 'Not set' }}</span>
              </div>
              <div>
                <span class="text-[10px] text-slate-500 uppercase font-mono block">Payment Account</span>
                <span class="font-bold text-slate-900 dark:text-white">
                  {{ selectedAccount ? `${selectedAccount.name} (${selectedAccount.currency})` : 'Unassigned (No account)' }}
                </span>
              </div>
              <div>
                <span class="text-[10px] text-slate-500 uppercase font-mono block">Total Receipt Paid</span>
                <span class="font-bold font-mono text-slate-900 dark:text-white">{{ formatCurrencyPence(receiptTotalPence) }}</span>
              </div>
            </div>
          </div>

          <div class="space-y-2">
            <h4 class="text-xs font-bold text-slate-700 dark:text-slate-300">Allocations to be recorded into Ledger:</h4>
            <div class="border border-brand-border dark:border-brand-darkborder rounded-xl overflow-hidden divide-y divide-brand-border dark:divide-brand-darkborder">
              <div 
                v-for="(row, idx) in rows" 
                :key="row.localId"
                class="p-3 flex items-center justify-between text-xs bg-white dark:bg-brand-darksurface"
              >
                <div class="space-y-0.5">
                  <div class="font-semibold text-slate-900 dark:text-white flex items-center space-x-2">
                    <span class="px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">#{{ idx + 1 }}</span>
                    <span>{{ getCategoryName(row.categoryId) }}</span>
                    <span class="text-[10px] font-mono px-1.5 py-0.2 rounded bg-slate-100 dark:bg-slate-800 text-slate-500 capitalize">{{ row.expenseNature }}</span>
                  </div>
                  <div v-if="row.notes" class="text-[11px] text-slate-500 italic pl-6">
                    "{{ row.notes }}"
                  </div>
                </div>
                <div class="font-mono font-bold text-slate-900 dark:text-white text-sm">
                  {{ formatCurrencyPence(Math.round(Number(row.amountStr) * 100)) }}
                </div>
              </div>
            </div>
          </div>

          <div class="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-900/50 text-[11px] text-emerald-900 dark:text-emerald-200">
            ✓ <strong>Integrity check:</strong> The {{ rows.length }} split transactions sum exactly to {{ formatCurrencyPence(receiptTotalPence) }}. The unsplit parent receipt candidate will be cleanly archived and will never appear as a duplicate.
          </div>
        </div>

        <!-- ==================== EDITING VIEW ==================== -->
        <div v-else class="space-y-5" data-testid="split-editing-view">
          
          <!-- Shared Receipt Details Card (Editable) -->
          <div class="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 space-y-3.5">
            <div class="flex items-center justify-between">
              <span class="font-mono text-[10px] uppercase font-bold text-slate-500 dark:text-slate-400 tracking-wider">
                Shared Receipt Details (applied to every split row)
              </span>
              <div class="font-mono text-sm font-extrabold text-slate-900 dark:text-white">
                Total: {{ formatCurrencyPence(receiptTotalPence) }}
              </div>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
              <!-- Merchant -->
              <div>
                <label class="block text-[11px] font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Merchant <span class="text-rose-500">*</span>
                </label>
                <input 
                  type="text"
                  v-model="sharedMerchant"
                  placeholder="e.g. Marks & Spencer"
                  data-testid="split-shared-merchant-input"
                  class="w-full text-xs rounded-lg border border-brand-border dark:border-brand-darkborder px-2.5 py-1.5 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              <!-- Transaction Date -->
              <div>
                <label class="block text-[11px] font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Transaction Date <span class="text-rose-500">*</span>
                </label>
                <input 
                  type="date"
                  v-model="sharedDate"
                  data-testid="split-shared-date-input"
                  class="w-full text-xs rounded-lg border border-brand-border dark:border-brand-darkborder px-2.5 py-1.5 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              <!-- Payment Account -->
              <div>
                <label class="block text-[11px] font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Payment Account
                </label>
                <select 
                  v-model="sharedAccountId"
                  data-testid="split-shared-account-select"
                  class="w-full text-xs rounded-lg border px-2.5 py-1.5 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  :class="!sharedAccountId ? 'border-amber-400 dark:border-amber-600 bg-amber-50/30' : 'border-brand-border dark:border-brand-darkborder'"
                >
                  <option :value="null">-- Select Account (Unassigned) --</option>
                  <option v-for="acc in activeAccounts" :key="acc.id" :value="acc.id">
                    {{ acc.name }} ({{ acc.currency }})
                  </option>
                </select>
              </div>
            </div>

            <!-- Accounting Allocation Notice -->
            <div class="p-2.5 rounded-lg bg-indigo-50/70 dark:bg-indigo-950/30 border border-indigo-200 dark:border-indigo-900/50 flex items-start space-x-2 text-[11px] text-indigo-950 dark:text-indigo-200 leading-relaxed">
              <span class="shrink-0 text-indigo-500 font-bold mt-0.5">ℹ️</span>
              <div>
                <strong>Multiple accounting allocations:</strong> These rows represent separate category allocations of a single payment, not separate bank or card charges. Shared receipt date, merchant, account, and receipt attachments are copied to every row.
              </div>
            </div>

            <!-- Unassigned Account Info -->
            <div v-if="!sharedAccountId" class="p-2 rounded-lg bg-slate-100 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 text-[11px] text-slate-600 dark:text-slate-300 flex items-center space-x-1.5">
              <span>ℹ️</span>
              <span><strong>Account unassigned:</strong> Transactions can be approved to the ledger as Unassigned, or you can choose an account above.</span>
            </div>

            <!-- Shared Notes -->
            <div>
              <label class="block text-[11px] font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Shared Receipt Notes (optional)
              </label>
              <input 
                type="text"
                v-model="sharedNotes"
                placeholder="e.g. Weekly family shopping receipt..."
                data-testid="split-shared-notes-input"
                class="w-full text-xs rounded-lg border border-brand-border dark:border-brand-darkborder px-2.5 py-1.5 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
          </div>

          <!-- Allocation Progress & Math Bar -->
          <div 
            class="p-3 rounded-xl border transition-colors flex flex-wrap items-center justify-between gap-3 text-xs"
            :class="isExactMatch 
              ? 'bg-emerald-50 dark:bg-emerald-950/30 border-emerald-200 dark:border-emerald-800 text-emerald-900 dark:text-emerald-200' 
              : 'bg-amber-50 dark:bg-amber-950/30 border-amber-200 dark:border-amber-800 text-amber-900 dark:text-amber-200'"
          >
            <div class="flex items-center space-x-3">
              <span class="text-sm font-bold">
                {{ isExactMatch ? '✓' : '⚠️' }}
              </span>
              <div>
                <div class="font-bold flex items-center space-x-1.5">
                  <span>Allocated: {{ formatCurrencyPence(allocatedPence) }}</span>
                  <span class="text-slate-400">/</span>
                  <span>Total: {{ formatCurrencyPence(receiptTotalPence) }}</span>
                </div>
                <div class="text-[11px] font-medium mt-0.5">
                  <span v-if="isExactMatch" class="text-emerald-700 dark:text-emerald-300">
                    Exact match! Ready to save or review before approval.
                  </span>
                  <span v-else-if="remainingPence > 0" class="text-amber-700 dark:text-amber-300">
                    {{ formatCurrencyPence(remainingPence) }} remaining to allocate.
                  </span>
                  <span v-else class="text-rose-600 dark:text-rose-400">
                    Over-allocated by {{ formatCurrencyPence(Math.abs(remainingPence)) }}!
                  </span>
                </div>
              </div>
            </div>

            <button
              type="button"
              @click="addSplitRow"
              class="px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 font-semibold text-xs text-slate-800 dark:text-slate-200 transition shadow-xs flex items-center space-x-1 shrink-0"
            >
              <span>+ Add Split Row</span>
            </button>
          </div>

          <!-- Split Rows -->
          <div class="space-y-3">
            <div 
              v-for="(row, idx) in rows" 
              :key="row.localId"
              class="p-3.5 rounded-xl border border-brand-border dark:border-brand-darkborder bg-white dark:bg-brand-darksurface shadow-xs space-y-3 relative group"
              :data-testid="`split-row-${idx}`"
            >
              <div class="flex items-center justify-between">
                <span class="px-2 py-0.5 rounded-md text-[10px] font-mono font-bold bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                  Split Row #{{ idx + 1 }}
                </span>

                <button 
                  type="button"
                  @click="removeSplitRow(idx)"
                  :disabled="rows.length <= 2"
                  class="text-xs text-slate-400 hover:text-rose-600 disabled:opacity-30 disabled:hover:text-slate-400 transition"
                  title="Remove this split row (minimum 2 rows required)"
                >
                  &times; Remove
                </button>
              </div>

              <div class="grid grid-cols-1 sm:grid-cols-12 gap-3">
                <!-- Amount -->
                <div class="sm:col-span-4">
                  <label class="block text-[11px] font-semibold text-slate-600 dark:text-slate-400 mb-1">
                    Amount ({{ currencyCode }}) <span class="text-rose-500">*</span>
                  </label>
                  <div class="relative">
                    <span class="absolute left-2.5 top-1.5 text-xs text-slate-400 font-medium">
                      {{ currencySymbol }}
                    </span>
                    <input 
                      type="number"
                      step="0.01"
                      min="0.01"
                      v-model="row.amountStr"
                      @input="onAmountInput(row)"
                      placeholder="0.00"
                      class="w-full text-xs rounded-lg border pl-6 pr-2.5 py-1.5 bg-white dark:bg-slate-900 text-slate-900 dark:text-white font-mono font-semibold focus:outline-none focus:ring-1 focus:ring-indigo-500"
                      :class="!row.amountStr || Number(row.amountStr) <= 0 ? 'border-rose-400 dark:border-rose-600' : 'border-brand-border dark:border-brand-darkborder'"
                    />
                  </div>
                </div>

                <!-- Category -->
                <div class="sm:col-span-5">
                  <label class="block text-[11px] font-semibold text-slate-600 dark:text-slate-400 mb-1">
                    Category
                  </label>
                  <select 
                    v-model="row.categoryId"
                    @change="onCategorySelect(row)"
                    class="w-full text-xs rounded-lg border border-brand-border dark:border-brand-darkborder px-2.5 py-1.5 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  >
                    <option :value="null">Uncategorised</option>
                    <option v-for="cat in activeCategories" :key="cat.id" :value="cat.id">
                      {{ cat.name }}
                    </option>
                  </select>
                </div>

                <!-- Expense Nature -->
                <div class="sm:col-span-3">
                  <label class="block text-[11px] font-semibold text-slate-600 dark:text-slate-400 mb-1">
                    Nature
                  </label>
                  <select 
                    v-model="row.expenseNature"
                    @change="row.natureManuallyOverridden = true"
                    class="w-full text-xs rounded-lg border border-brand-border dark:border-brand-darkborder px-2 py-1.5 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  >
                    <option value="unclassified">Unclassified</option>
                    <option value="variable">Variable</option>
                    <option value="fixed">Fixed</option>
                  </select>
                </div>
              </div>

              <!-- Notes -->
              <div>
                <label class="block text-[11px] font-semibold text-slate-600 dark:text-slate-400 mb-1">
                  Line Notes (optional)
                </label>
                <input 
                  type="text"
                  v-model="row.notes"
                  placeholder="e.g. Household items, groceries, personal care..."
                  class="w-full text-xs rounded-lg border border-brand-border dark:border-brand-darkborder px-2.5 py-1.5 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
            </div>
          </div>
        </div>

        <!-- Error Alert -->
        <div v-if="submissionError" class="p-3 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 text-xs text-rose-700 dark:text-rose-300">
          <strong>Error:</strong> {{ submissionError }}
        </div>

      </div>

      <!-- Modal Footer Actions -->
      <div class="px-6 py-4 border-t border-brand-border dark:border-brand-darkborder flex flex-col sm:flex-row items-center justify-between gap-3 shrink-0 bg-slate-50/50 dark:bg-slate-900/20">
        
        <!-- Cancel / Back -->
        <button 
          v-if="isConfirmingApproval"
          type="button"
          @click="isConfirmingApproval = false"
          :disabled="isSubmitting"
          data-testid="split-back-btn"
          class="w-full sm:w-auto px-4 py-2 rounded-full border border-slate-300 dark:border-slate-700 text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition disabled:opacity-50"
        >
          ← Back to Editing
        </button>

        <button 
          v-else
          type="button"
          @click="handleClose"
          :disabled="isSubmitting"
          class="w-full sm:w-auto px-4 py-2 rounded-full border border-slate-300 dark:border-slate-700 text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition disabled:opacity-50"
        >
          Cancel
        </button>

        <!-- Right Action Buttons -->
        <div class="flex items-center space-x-2.5 w-full sm:w-auto justify-end">
          
          <template v-if="isConfirmingApproval">
            <button 
              type="button"
              @click="executeApprovalToLedger"
              :disabled="isSubmitting"
              data-testid="split-confirm-approve-btn"
              class="px-5 py-2 rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 hover:opacity-90 text-xs font-semibold transition shadow-sm flex items-center space-x-1.5 disabled:opacity-50"
            >
              <span v-if="isSubmitting" class="animate-spin w-3 h-3 border-2 border-white dark:border-slate-900 border-t-transparent rounded-full"></span>
              <span>Confirm & Approve to Ledger</span>
            </button>
          </template>

          <template v-else>
            <!-- Save Splits to Review Queue -->
            <button 
              type="button"
              @click="handleSubmit(false)"
              :disabled="!canSubmit || isSubmitting"
              data-testid="split-save-queue-btn"
              class="px-4 py-2 rounded-full border border-brand-border dark:border-brand-darkborder bg-white dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 text-xs font-semibold text-slate-800 dark:text-slate-200 transition shadow-xs flex items-center space-x-1.5 disabled:opacity-50"
            >
              <span v-if="isSubmitting && submitAction === 'queue'" class="animate-spin w-3 h-3 border-2 border-slate-500 border-t-transparent rounded-full"></span>
              <span>Save Splits to Queue</span>
            </button>

            <!-- Approve Split Directly to Ledger (triggers confirmation) -->
            <button 
              v-if="allowImmediateApprove"
              type="button"
              @click="promptApprovalConfirmation"
              :disabled="!canSubmit || isSubmitting"
              data-testid="split-approve-ledger-btn"
              class="px-4 py-2 rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 hover:opacity-90 text-xs font-semibold transition shadow-sm flex items-center space-x-1.5 disabled:opacity-50"
            >
              <span>Approve Split to Ledger</span>
            </button>
          </template>

        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { api } from '../api/client';
import { filterCategoriesForTransactionType, isCategoryCompatibleWithTransaction } from '../utils/categoryPurpose';
import type { Account, Category, ExpenseNature, StagingSplitRow } from '../types';

interface InternalSplitRow {
  localId: number;
  amountStr: string;
  categoryId: number | null;
  expenseNature: ExpenseNature;
  notes: string;
  natureManuallyOverridden: boolean;
}

const props = withDefaults(defineProps<{
  isOpen: boolean;
  item: any;
  accounts?: Account[];
  categories: Category[];
  baseCurrency?: string;
  baseCurrencySymbol?: string;
  allowImmediateApprove?: boolean;
}>(), {
  accounts: () => [],
  baseCurrency: 'GBP',
  baseCurrencySymbol: '£',
  allowImmediateApprove: true,
});

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'splitSuccess', payload: {
    action: 'queued' | 'approved';
    parentId: number;
    createdItems: any[];
    transactionIds: number[];
    accountId?: number | null;
    merchant?: string;
    date?: string;
  }): void;
}>();

let nextLocalId = 1;
const rows = ref<InternalSplitRow[]>([]);
const isSubmitting = ref(false);
const submitAction = ref<'queue' | 'approve' | null>(null);
const submissionError = ref<string | null>(null);
const isConfirmingApproval = ref(false);

// Shared Fields
const sharedMerchant = ref('');
const sharedDate = ref('');
const sharedAccountId = ref<number | null>(null);
const sharedNotes = ref('');

const activeCategories = computed(() => {
  return filterCategoriesForTransactionType(props.categories || [], 'expense');
});

const activeAccounts = computed(() => {
  return (props.accounts || []).filter(a => a.is_active !== false);
});

const selectedAccount = computed(() => {
  if (sharedAccountId.value == null) return null;
  return activeAccounts.value.find(a => a.id === sharedAccountId.value) || null;
});

const currencyCode = computed(() => {
  return props.item?.currency || props.baseCurrency || 'GBP';
});

const currencySymbol = computed(() => {
  const code = currencyCode.value.toUpperCase();
  if (code === 'GBP') return '£';
  if (code === 'EUR') return '€';
  if (code === 'USD') return '$';
  return props.baseCurrencySymbol || '£';
});

const receiptTotalPence = computed(() => {
  if (!props.item) return 0;
  if (props.item.extracted_amount_pence != null && props.item.extracted_amount_pence > 0) {
    return props.item.extracted_amount_pence;
  }
  if (props.item.amount_input) {
    return Math.round(Number(props.item.amount_input) * 100);
  }
  return 0;
});

const allocatedPence = computed(() => {
  return rows.value.reduce((sum, r) => {
    const p = Math.round((Number(r.amountStr) || 0) * 100);
    return sum + p;
  }, 0);
});

const remainingPence = computed(() => {
  return receiptTotalPence.value - allocatedPence.value;
});

const isExactMatch = computed(() => {
  return receiptTotalPence.value > 0 && 
    remainingPence.value === 0 && 
    rows.value.length >= 2 && 
    rows.value.every(r => Math.round((Number(r.amountStr) || 0) * 100) > 0);
});

const canSubmit = computed(() => {
  return isExactMatch.value && !isSubmitting.value;
});

function formatCurrencyPence(pence: number): string {
  const sym = currencySymbol.value;
  const abs = Math.abs(pence);
  const formatted = (abs / 100).toFixed(2);
  return pence < 0 ? `-${sym}${formatted}` : `${sym}${formatted}`;
}

function getCategoryName(catId: number | null): string {
  if (!catId) return 'Uncategorised';
  const c = props.categories.find(cat => cat.id === catId);
  return c ? c.name : 'Uncategorised';
}

function formatDateForInput(dateVal: any): string {
  if (!dateVal) return '';
  try {
    const dt = new Date(dateVal);
    if (isNaN(dt.getTime())) return String(dateVal).substring(0, 10);
    return dt.toISOString().split('T')[0];
  } catch {
    return String(dateVal).substring(0, 10);
  }
}

// Initialize split rows and shared fields when modal opens
watch(() => props.isOpen, (open) => {
  if (open && props.item) {
    submissionError.value = null;
    isSubmitting.value = false;
    submitAction.value = null;
    isConfirmingApproval.value = false;

    // Populate shared fields
    sharedMerchant.value = props.item.extracted_merchant || props.item.merchant_input || props.item.merchant || '';
    sharedDate.value = formatDateForInput(props.item.extracted_date || props.item.date_input || props.item.transaction_date);
    sharedAccountId.value = props.item.suggested_account_id ?? props.item.account_id ?? null;
    sharedNotes.value = props.item.notes || '';

    const total = receiptTotalPence.value;
    const rawCatId = props.item.suggested_category_id || props.item.category_id || null;
    const initialCatId = isCategoryCompatibleWithTransaction(activeCategories.value, rawCatId, 'expense')
      ? rawCatId
      : null;
    const initialNature = (props.item.suggested_expense_nature || props.item.expense_nature || 'unclassified') as ExpenseNature;

    // Row 1 gets half or full minus row 2
    const split1Pence = Math.floor(total / 2);
    const split2Pence = total - split1Pence;

    rows.value = [
      {
        localId: nextLocalId++,
        amountStr: (split1Pence / 100).toFixed(2),
        categoryId: initialCatId,
        expenseNature: initialNature,
        notes: '',
        natureManuallyOverridden: false
      },
      {
        localId: nextLocalId++,
        amountStr: (split2Pence / 100).toFixed(2),
        categoryId: null,
        expenseNature: 'unclassified' as ExpenseNature,
        notes: '',
        natureManuallyOverridden: false
      }
    ];

    // Default nature for row 1 if category is set
    if (initialCatId) {
      const cat = props.categories.find(c => c.id === initialCatId);
      if (cat?.default_expense_nature && cat.default_expense_nature !== 'unclassified') {
        rows.value[0].expenseNature = cat.default_expense_nature;
      }
    }
  }
}, { immediate: true });

function onAmountInput(_row: InternalSplitRow) {
  submissionError.value = null;
}

function onCategorySelect(row: InternalSplitRow) {
  submissionError.value = null;
  if (!row.natureManuallyOverridden && row.categoryId) {
    const cat = props.categories.find(c => c.id === row.categoryId);
    if (cat?.default_expense_nature && cat.default_expense_nature !== 'unclassified') {
      row.expenseNature = cat.default_expense_nature;
    }
  }
}

function addSplitRow() {
  const rem = remainingPence.value;
  const nextAmt = rem > 0 ? (rem / 100).toFixed(2) : '0.00';
  rows.value.push({
    localId: nextLocalId++,
    amountStr: nextAmt,
    categoryId: null,
    expenseNature: 'unclassified' as ExpenseNature,
    notes: '',
    natureManuallyOverridden: false
  });
}

function removeSplitRow(idx: number) {
  if (rows.value.length <= 2) return;
  rows.value.splice(idx, 1);
}

function handleClose() {
  if (isSubmitting.value) return;
  isConfirmingApproval.value = false;
  emit('close');
}

function promptApprovalConfirmation() {
  if (!canSubmit.value || !props.item) return;
  submissionError.value = null;
  isConfirmingApproval.value = true;
}

function executeApprovalToLedger() {
  handleSubmit(true);
}

async function handleSubmit(commitToLedger: boolean) {
  if (!canSubmit.value || !props.item) return;

  isSubmitting.value = true;
  submitAction.value = commitToLedger ? 'approve' : 'queue';
  submissionError.value = null;

  try {
    const payloadSplits: StagingSplitRow[] = rows.value.map(r => ({
      amount_pence: Math.round(Number(r.amountStr) * 100),
      category_id: r.categoryId,
      category_name: props.categories.find(c => c.id === r.categoryId)?.name || undefined,
      expense_nature: r.expenseNature,
      notes: r.notes.trim() || undefined
    }));

    const res = await api.splitStagingItem(props.item.id, {
      splits: payloadSplits,
      commit_to_ledger: commitToLedger,
      account_id: sharedAccountId.value,
      transaction_date: sharedDate.value ? new Date(sharedDate.value).toISOString() : undefined,
      merchant: sharedMerchant.value.trim() || undefined,
      notes: sharedNotes.value.trim() || undefined
    });

    emit('splitSuccess', {
      action: res.action,
      parentId: props.item.id,
      createdItems: res.created_items || [],
      transactionIds: res.transaction_ids || [],
      accountId: sharedAccountId.value,
      merchant: sharedMerchant.value.trim() || undefined,
      date: sharedDate.value || undefined
    });

    emit('close');
  } catch (err: any) {
    submissionError.value = err.message || 'Failed to split expense receipt.';
  } finally {
    isSubmitting.value = false;
    submitAction.value = null;
  }
}
</script>