<template>
  <div 
    class="relative overflow-hidden bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder rounded-xl p-5 shadow-sm flex flex-col justify-between transition hover:border-slate-300 dark:hover:border-slate-700 hover:shadow-md cursor-pointer focus:outline-none focus:ring-2 focus:ring-brand-primary"
    :style="`background-image: linear-gradient(to left, ${account.color || '#3B82F6'}10 0%, transparent 45%);`"
    role="button"
    tabindex="0"
    data-testid="account-card"
    :aria-label="`View details for ${account.name}`"
    @click="$emit('inspect', account)"
    @keydown.enter.self="$emit('inspect', account)"
    @keydown.space.prevent.self="$emit('inspect', account)">
    
    <!-- Accent Line on Left -->
    <div 
      class="absolute left-0 top-0 bottom-0 w-1.5" 
      :style="{ backgroundColor: account.color || '#3B82F6' }">
    </div>

    <div class="pl-2.5">
      <div class="flex items-start justify-between mb-2">
        <div>
          <h3 class="text-sm font-bold text-slate-900 dark:text-white truncate">
            {{ account.name }}
          </h3>
          <div class="flex items-center space-x-1.5 mt-0.5">
            <span class="text-[10px] font-mono uppercase tracking-wider text-slate-400 block">
              {{ formatAccountType(account.account_type) }}
            </span>
            <span 
              v-if="account.account_type === 'cash'" 
              class="text-[9px] font-mono px-1.5 py-0.2 rounded bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-900/40 font-semibold uppercase">
              Cash
            </span>
            <span 
              v-if="account.account_type === 'credit_card'" 
              class="text-[9px] font-mono px-1 py-0.2 rounded bg-rose-50 dark:bg-rose-950/60 text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-900/40 font-semibold uppercase">
              Liability
            </span>
          </div>
        </div>
        <div class="flex items-center space-x-1.5 shrink-0">
          <span 
            v-if="!account.is_active" 
            class="text-[9px] font-mono px-1.5 py-0.5 rounded bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300 font-semibold uppercase">
            Archived
          </span>
          <span class="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 font-semibold">
            {{ account.currency }}
          </span>
          <button
            type="button"
            @click.stop="$emit('edit', account)"
            class="text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 p-0.5 rounded transition"
            title="Edit account details and status">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
            </svg>
          </button>
        </div>
      </div>

      <div class="mt-4 flex items-end justify-between">
        <div>
          <span class="text-[10px] font-mono tracking-wider text-slate-400 block mb-0.5">
            {{ account.account_type === 'credit_card' && account.current_balance_pence < 0 ? 'Balance owed' : (account.anchor_label || 'Ledger balance') }}
          </span>
          <div 
            class="text-2xl font-extrabold sensitive font-mono"
            :class="account.current_balance_pence < 0 ? 'text-rose-600 dark:text-rose-400' : 'text-slate-900 dark:text-white'">
            {{ account.formatted_balance }}
          </div>
        </div>

        <div v-if="account.account_type === 'investment'" class="text-right">
          <span 
            v-if="account.valuation_mode === 'holdings'" 
            class="inline-flex items-center space-x-1 text-[10px] font-mono px-2 py-0.5 rounded-full bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 font-medium border border-indigo-200 dark:border-indigo-900/40"
            :title="account.has_unvalued_holdings ? 'Contains unvalued holdings' : 'Valued via active holdings'">
            <span v-if="account.has_unvalued_holdings" class="w-1.5 h-1.5 rounded-full bg-amber-500"></span>
            <span>{{ account.holdings_count === 0 ? 'No Holdings' : (account.has_unvalued_holdings ? 'Unvalued Holdings' : `${account.holdings_count} Holdings`) }}</span>
          </span>
          <span 
            v-else 
            class="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-500 font-medium">
            Snapshot
          </span>
        </div>

        <div v-else class="text-right">
          <button
            type="button"
            @click.stop="$emit('reconcile', account)"
            class="inline-flex items-center space-x-1 text-[10px] font-mono px-2 py-0.5 rounded-full border transition hover:opacity-80 cursor-pointer"
            :class="account.last_reconciled_at 
              ? (account.last_reconciled_discrepancy_pence === 0 
                ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-900/40' 
                : 'bg-amber-50 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-900/40')
              : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700'"
            :title="account.last_reconciled_at ? `Last reconciled on ${formatDate(account.last_reconciled_at)}` : 'Click to reconcile balance against statement'">
            <span>⚖️</span>
            <span>{{ account.last_reconciled_at ? `Reconciled ${formatShortDate(account.last_reconciled_at)}` : 'Reconcile' }}</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Account, AccountType } from '../types';

defineProps<{
  account: Account;
}>();

defineEmits<{
  (e: 'inspect', account: Account): void;
  (e: 'reconcile', account: Account): void;
  (e: 'edit', account: Account): void;
}>();

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

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
  } catch {
    return iso;
  }
}

function formatShortDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
  } catch {
    return iso;
  }
}
</script>
