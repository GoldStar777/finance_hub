<template>
  <div 
    v-if="isOpen" 
    class="fixed inset-0 z-50 bg-slate-950/40 backdrop-blur-sm flex items-center justify-center p-4 animate-fadeIn"
    @click.self="emitClose">
    <section 
      role="dialog" 
      aria-modal="true" 
      aria-labelledby="bulk-edit-modal-title"
      class="bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-5 transition-all max-h-[90vh] flex flex-col">
      
      <!-- Modal Header -->
      <div class="flex items-start justify-between pb-3 border-b border-brand-border dark:border-brand-darkborder shrink-0">
        <div>
          <div class="flex items-center space-x-2">
            <h2 id="bulk-edit-modal-title" class="font-bold text-slate-900 dark:text-white text-base">
              Bulk Edit Transactions
            </h2>
            <span class="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-300">
              {{ selectedCount }} selected
            </span>
          </div>
          <p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Apply batch updates to <strong>{{ selectedCount }}</strong> transaction{{ selectedCount === 1 ? '' : 's' }}.
          </p>
        </div>

        <button 
          @click="emitClose" 
          class="text-slate-400 hover:text-slate-600 dark:hover:text-white text-lg p-1"
          aria-label="Close dialog">
          &times;
        </button>
      </div>

      <!-- Modal Body -->
      <div class="space-y-4 overflow-y-auto pr-1">
        
        <!-- Error Message -->
        <div v-if="errorMessage" class="p-3 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 text-rose-600 dark:text-rose-400 text-xs">
          <div class="font-bold mb-0.5">Validation Error</div>
          <div>{{ errorMessage }}</div>
        </div>

        <!-- Success Toast -->
        <div v-if="successMessage" class="p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-900 text-emerald-700 dark:text-emerald-300 text-xs font-semibold">
          {{ successMessage }}
        </div>

        <!-- Fields Selection Card -->
        <div class="p-4 rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50/60 dark:bg-slate-800/40 space-y-3.5">
          
          <!-- 1. Transaction Type -->
          <div class="space-y-1">
            <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500">
              Transaction Type
            </label>
            <select 
              v-model="typeAction"
              class="w-full bg-white dark:bg-slate-900 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs font-semibold text-slate-900 dark:text-white focus:outline-none focus:border-indigo-500">
              <option value="keep">Leave unchanged (keep original types)</option>
              <option value="expense">Change to Expense (deduction from account)</option>
              <option value="income">Change to Income (addition to account)</option>
            </select>
            <p class="text-[10px] text-slate-400">
              Amounts, nominal dates, and timestamps are strictly preserved.
            </p>
          </div>

          <!-- 2. Category -->
          <div class="space-y-1">
            <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500">
              Category
            </label>
            <select 
              v-model="categoryAction"
              class="w-full bg-white dark:bg-slate-900 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs font-semibold text-slate-900 dark:text-white focus:outline-none focus:border-indigo-500">
              <option value="keep">Leave unchanged (keep original categories)</option>
              <option value="uncategorized">Uncategorised (Clear category)</option>
              <optgroup v-if="typeAction === 'expense'" label="Expense Categories">
                <option v-for="cat in expenseCategories" :key="cat.id" :value="`cat_${cat.id}`">
                  {{ cat.name }}
                </option>
              </optgroup>
              <optgroup v-else-if="typeAction === 'income'" label="Income Categories">
                <option v-for="cat in incomeCategories" :key="cat.id" :value="`cat_${cat.id}`">
                  {{ cat.name }}
                </option>
              </optgroup>
              <template v-else>
                <optgroup v-if="expenseCategories.length > 0" label="Expense Categories">
                  <option v-for="cat in expenseCategories" :key="cat.id" :value="`cat_${cat.id}`">
                    {{ cat.name }}
                  </option>
                </optgroup>
                <optgroup v-if="incomeCategories.length > 0" label="Income Categories">
                  <option v-for="cat in incomeCategories" :key="cat.id" :value="`cat_${cat.id}`">
                    {{ cat.name }}
                  </option>
                </optgroup>
              </template>
            </select>
            <p v-if="categoryResetNotice" class="text-[11px] text-amber-600 dark:text-amber-400">
              {{ categoryResetNotice }}
            </p>
          </div>

          <!-- 3. Account -->
          <div class="space-y-1">
            <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500">
              Account
            </label>
            <select 
              v-model="accountAction"
              class="w-full bg-white dark:bg-slate-900 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs font-semibold text-slate-900 dark:text-white focus:outline-none focus:border-indigo-500">
              <option value="keep">Leave unchanged (keep original accounts)</option>
              <option value="unassigned">⚠️ Unassigned (Clear account)</option>
              <optgroup label="Accounts">
                <option v-for="acc in accountsStore.accounts" :key="acc.id" :value="`acc_${acc.id}`">
                  {{ acc.name }} ({{ acc.currency }})
                </option>
              </optgroup>
            </select>
          </div>

        </div>

        <!-- Confirmation Summary Card -->
        <div 
          v-if="hasChangesToApply"
          class="p-4 rounded-xl border border-indigo-200 dark:border-indigo-900/60 bg-indigo-50/50 dark:bg-indigo-950/30 text-xs space-y-2">
          <div class="font-bold text-indigo-950 dark:text-indigo-200 flex items-center space-x-1.5">
            <span>📋</span>
            <span>Confirmation: The following changes will be applied to {{ selectedCount }} transactions:</span>
          </div>

          <ul class="space-y-1 text-[11px] text-indigo-900 dark:text-indigo-300 font-mono">
            <li v-if="typeAction !== 'keep'" class="flex items-center space-x-2">
              <span class="text-indigo-400">&bull;</span>
              <span>Transaction Type &rarr; <strong>{{ typeAction === 'expense' ? 'Expense' : 'Income' }}</strong></span>
            </li>
            <li v-if="categoryAction !== 'keep'" class="flex items-center space-x-2">
              <span class="text-indigo-400">&bull;</span>
              <span>Category &rarr; <strong>{{ resolvedCategoryName }}</strong></span>
            </li>
            <li v-if="accountAction !== 'keep'" class="flex items-center space-x-2">
              <span class="text-indigo-400">&bull;</span>
              <span>Account &rarr; <strong>{{ resolvedAccountName }}</strong></span>
            </li>
          </ul>

          <div class="pt-1 text-[10px] text-indigo-800/80 dark:text-indigo-400/80 border-t border-indigo-200/50 dark:border-indigo-800/50">
            ℹ️ All other fields (amounts, dates, merchants, notes, receipts, and currency provenance) will remain untouched.
          </div>
        </div>

        <!-- No Selection Notice -->
        <div v-else class="p-3 text-center text-xs text-slate-400 italic">
          Select one or more fields above to prepare your batch update.
        </div>

      </div>

      <!-- Action Buttons -->
      <div class="pt-2 flex items-center justify-end space-x-2.5 border-t border-brand-border dark:border-brand-darkborder shrink-0">
        <button 
          type="button" 
          @click="emitClose" 
          class="px-4 py-2 text-xs font-semibold rounded-full border border-brand-border dark:border-brand-darkborder hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300 transition">
          Cancel
        </button>

        <button 
          type="button" 
          @click="handleApply" 
          :disabled="isSubmitting || !hasChangesToApply"
          class="px-5 py-2 text-xs font-semibold rounded-full shadow-sm transition disabled:opacity-50 bg-slate-900 text-white dark:bg-white dark:text-slate-900 hover:opacity-90">
          {{ isSubmitting ? 'Applying...' : `Apply Changes to ${selectedCount} Transaction${selectedCount === 1 ? '' : 's'}` }}
        </button>
      </div>

    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useAccountsStore } from '../stores/accounts';
import { useTransactionsStore } from '../stores/transactions';
import { filterCategoriesForTransactionType, isCategoryCompatibleWithTransaction } from '../utils/categoryPurpose';
import type { BulkTransactionUpdatePayload } from '../types';

const props = defineProps<{
  isOpen: boolean;
  selectedCount: number;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'updated', count: number): void;
}>();

const accountsStore = useAccountsStore();
const txStore = useTransactionsStore();

const typeAction = ref<'keep' | 'income' | 'expense'>('keep');
const categoryAction = ref<string>('keep');
const accountAction = ref<string>('keep');

const isSubmitting = ref(false);
const errorMessage = ref<string | null>(null);
const successMessage = ref<string | null>(null);
const categoryResetNotice = ref<string | null>(null);

const expenseCategories = computed(() => filterCategoriesForTransactionType(txStore.categories, 'expense'));
const incomeCategories = computed(() => filterCategoriesForTransactionType(txStore.categories, 'income'));

watch(typeAction, (nextType) => {
  if (nextType === 'keep') {
    categoryResetNotice.value = null;
    return;
  }
  if (categoryAction.value.startsWith('cat_')) {
    const chosenId = Number(categoryAction.value.replace('cat_', ''));
    if (!isCategoryCompatibleWithTransaction(txStore.categories, chosenId, nextType)) {
      categoryAction.value = 'uncategorized';
      categoryResetNotice.value = `Incompatible category selection was switched to Uncategorised for ${nextType} transactions. Choose an ${nextType} category or keep Uncategorised.`;
      return;
    }
  } else if (categoryAction.value === 'keep') {
    categoryAction.value = 'uncategorized';
    categoryResetNotice.value = `Changing type to ${nextType} defaults Category to Uncategorised so incompatible categories are never retained.`;
    return;
  }
  categoryResetNotice.value = null;
});

const hasChangesToApply = computed(() => {
  return typeAction.value !== 'keep' || categoryAction.value !== 'keep' || accountAction.value !== 'keep';
});

const resolvedCategoryName = computed(() => {
  if (categoryAction.value === 'keep') return 'Leave unchanged';
  if (categoryAction.value === 'uncategorized') return 'Uncategorised';
  const catId = Number(categoryAction.value.replace('cat_', ''));
  const found = txStore.categories.find(c => c.id === catId);
  return found ? found.name : 'Unknown';
});

const resolvedAccountName = computed(() => {
  if (accountAction.value === 'keep') return 'Leave unchanged';
  if (accountAction.value === 'unassigned') return 'Unassigned';
  const accId = Number(accountAction.value.replace('acc_', ''));
  const found = accountsStore.accounts.find(a => a.id === accId);
  return found ? found.name : 'Unknown';
});

watch(() => props.isOpen, (open) => {
  if (open) {
    resetForm();
  }
});

function resetForm() {
  typeAction.value = 'keep';
  categoryAction.value = 'keep';
  accountAction.value = 'keep';
  errorMessage.value = null;
  successMessage.value = null;
  categoryResetNotice.value = null;
  isSubmitting.value = false;
}

function emitClose() {
  emit('close');
}

async function handleApply() {
  if (!hasChangesToApply.value) return;
  isSubmitting.value = true;
  errorMessage.value = null;
  successMessage.value = null;

  try {
    const payload: Omit<BulkTransactionUpdatePayload, 'transaction_ids'> = {};

    // 1. Transaction Type
    if (typeAction.value !== 'keep') {
      payload.update_transaction_type = true;
      payload.transaction_type = typeAction.value;
    }

    // 2. Category
    if (categoryAction.value !== 'keep') {
      payload.update_category = true;
      if (categoryAction.value === 'uncategorized') {
        payload.category_id = null;
      } else {
        payload.category_id = Number(categoryAction.value.replace('cat_', ''));
      }
    }

    // 3. Account
    if (accountAction.value !== 'keep') {
      payload.update_account = true;
      if (accountAction.value === 'unassigned') {
        payload.account_id = null;
      } else {
        payload.account_id = Number(accountAction.value.replace('acc_', ''));
      }
    }

    const res = await txStore.bulkUpdate(payload);

    successMessage.value = res?.message || `Successfully updated ${props.selectedCount} transactions.`;
    emit('updated', res?.updated_count || props.selectedCount);

    setTimeout(() => {
      emitClose();
    }, 1200);

  } catch (err: any) {
    errorMessage.value = err.message || 'Failed to apply bulk updates.';
  } finally {
    isSubmitting.value = false;
  }
}
</script>

