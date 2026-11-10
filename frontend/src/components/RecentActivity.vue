<template>
  <section class="space-y-4">
    <div class="flex items-center justify-between">
      <div>
        <h2 class="font-mono text-xs uppercase tracking-wider font-bold text-slate-500 dark:text-slate-400">
          Recent Activity
        </h2>
        <p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
          Latest movements across your depository and credit accounts.
        </p>
      </div>

      <div class="flex items-center space-x-3">
        <router-link 
          to="/ledger" 
          class="text-xs font-semibold text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white transition flex items-center space-x-1">
          <span>View Ledger</span>
          <span>&rarr;</span>
        </router-link>
      </div>
    </div>

    <!-- Loading Skeleton -->
    <div v-if="txStore.loading && txStore.recentTransactions.length === 0" class="space-y-2.5">
      <div v-for="i in 4" :key="i" class="h-16 rounded-xl bg-slate-100 dark:bg-slate-800/40 animate-pulse"></div>
    </div>

    <!-- Empty State -->
    <div 
      v-else-if="txStore.recentTransactions.length === 0" 
      class="border border-brand-border dark:border-brand-darkborder rounded-2xl bg-white/60 dark:bg-brand-darksurface/60 p-8 text-center space-y-2">
      <div class="w-9 h-9 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-500 mx-auto flex items-center justify-center font-bold text-sm">
        💸
      </div>
      <p class="text-xs font-semibold text-slate-800 dark:text-slate-200">No transactions recorded yet</p>
      <p class="text-[11px] text-slate-500 max-w-sm mx-auto">
        Record an expense, income payment, or internal transfer to begin populating your ledger.
      </p>
      <button 
        @click="$emit('open-record')" 
        class="mt-2 px-3.5 py-1.5 text-xs font-semibold rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 shadow-sm hover:opacity-90 transition">
        + Record Transaction
      </button>
    </div>

    <!-- Activity Items List -->
    <div v-else class="space-y-2">
      <div 
        v-for="tx in txStore.recentTransactions" 
        :key="tx.id"
        class="group flex items-center justify-between p-3.5 rounded-xl border border-brand-border dark:border-brand-darkborder bg-white dark:bg-brand-darksurface hover:border-slate-300 dark:hover:border-slate-700 transition">
        
        <!-- Left: Icon & Details -->
        <div class="flex items-center space-x-3.5 min-w-0">
          <div 
            class="w-9 h-9 rounded-xl flex items-center justify-center font-bold text-sm shrink-0"
            :class="getTypeIconClass(tx.transaction_type)">
            <span v-if="tx.transaction_type === 'expense'">&darr;</span>
            <span v-else-if="tx.transaction_type === 'income'">&uarr;</span>
            <span v-else>&harr;</span>
          </div>

          <div class="min-w-0">
            <div class="flex items-center space-x-2">
              <span class="text-xs font-bold text-slate-900 dark:text-white truncate">
                <span v-if="tx.merchant">{{ tx.merchant }}</span>
                <span v-else class="italic text-slate-400 font-normal">Merchant not recorded</span>
              </span>
              <!-- Nature Badge for Expenses -->
              <span 
                v-if="tx.transaction_type === 'expense' && tx.expense_nature !== 'unclassified'"
                class="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded font-semibold"
                :class="tx.expense_nature === 'fixed' 
                  ? 'bg-indigo-100 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300' 
                  : 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300'">
                {{ tx.expense_nature }}
              </span>
            </div>

            <!-- Subline: Date, Account, Category -->
            <div class="flex items-center space-x-2 text-[10px] text-slate-400 dark:text-slate-500 font-mono mt-0.5">
              <span>{{ formatDate(tx.transaction_date) }}</span>
              <span>&bull;</span>
              <span v-if="tx.is_unassigned || !tx.account_id" class="inline-flex items-center space-x-1 px-1.5 py-0.2 rounded text-[10px] font-semibold bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300">
                <span>Unassigned</span>
              </span>
              <span v-else class="flex items-center space-x-1 text-slate-600 dark:text-slate-400">
                <span class="w-1.5 h-1.5 rounded-full inline-block" :style="{ backgroundColor: tx.account_color || '#3B82F6' }"></span>
                <span>{{ tx.account_name || 'Account' }}</span>
                <template v-if="tx.transaction_type === 'transfer' && tx.destination_account_name">
                  <span>&rarr;</span>
                  <span class="w-1.5 h-1.5 rounded-full inline-block" :style="{ backgroundColor: tx.destination_account_color || '#3B82F6' }"></span>
                  <span>{{ tx.destination_account_name }}</span>
                </template>
              </span>
              <template v-if="tx.category_name">
                <span>&bull;</span>
                <span class="px-1.5 py-0.2 rounded text-[10px] bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                  {{ tx.category_name }}
                </span>
              </template>
            </div>
          </div>
        </div>

        <!-- Right: Amount -->
        <div class="text-right shrink-0 ml-4">
          <div 
            class="text-xs font-mono font-bold sensitive"
            :class="getAmountClass(tx.transaction_type)">
            {{ formatTxAmount(tx) }}
          </div>
          <span class="text-[10px] font-mono text-slate-400 capitalize block">
            {{ tx.transaction_type }}
          </span>
        </div>

      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted } from 'vue';
import { useTransactionsStore } from '../stores/transactions';
import type { Transaction, TransactionType } from '../types';

defineEmits<{
  (e: 'open-record'): void;
}>();

const txStore = useTransactionsStore();

onMounted(() => {
  txStore.loadRecent();
});

function getTypeIconClass(type: TransactionType): string {
  switch (type) {
    case 'expense':
      return 'bg-rose-100 dark:bg-rose-950/60 text-rose-600 dark:text-rose-400';
    case 'income':
      return 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400';
    case 'transfer':
      return 'bg-indigo-100 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400';
    default:
      return 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400';
  }
}

function getAmountClass(type: TransactionType): string {
  switch (type) {
    case 'expense':
      return 'text-rose-600 dark:text-rose-400';
    case 'income':
      return 'text-emerald-600 dark:text-emerald-400';
    case 'transfer':
      return 'text-indigo-600 dark:text-indigo-400';
    default:
      return 'text-slate-800 dark:text-slate-200';
  }
}

function formatTxAmount(tx: Transaction): string {
  if (tx.transaction_type === 'expense') {
    return `-${tx.formatted_amount}`;
  } else if (tx.transaction_type === 'income') {
    return `+${tx.formatted_amount}`;
  }
  return tx.formatted_amount;
}

function formatDate(dateStr: string): string {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric'
  });
}
</script>
