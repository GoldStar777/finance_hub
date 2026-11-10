<template>
  <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
    <!-- Net Worth Card -->
    <div class="relative overflow-hidden rounded-xl border border-emerald-200 dark:border-emerald-800/50 bg-gradient-to-br from-emerald-50/70 via-white to-emerald-100/50 dark:from-brand-darksurface dark:via-brand-darksurface dark:to-emerald-950/40 p-6 shadow-sm transition">
      <div class="flex items-center justify-between">
        <span class="font-mono text-[11px] uppercase tracking-wider text-slate-500 dark:text-slate-400 font-semibold">
          Net Worth Balance
        </span>
        <span class="text-xs px-2.5 py-0.5 rounded-full font-mono bg-emerald-200/60 dark:bg-emerald-950 text-emerald-900 dark:text-emerald-300 font-medium">
          Total
        </span>
      </div>
      <div class="text-3xl font-extrabold tracking-tight sensitive text-slate-900 dark:text-white mt-3 font-mono">
        {{ summary?.formatted_net_worth || zeroDisplay }}
      </div>
      <p class="text-xs text-slate-500 dark:text-slate-400 mt-1.5">
        Liquid holdings + investments minus active debt
      </p>
    </div>

    <!-- Liquid Reserves Card -->
    <div class="relative overflow-hidden rounded-xl border border-sky-200 dark:border-sky-800/50 bg-gradient-to-br from-sky-50/70 via-white to-sky-100/50 dark:from-brand-darksurface dark:via-brand-darksurface dark:to-sky-950/40 p-6 shadow-sm transition">
      <div class="flex items-center justify-between">
        <span class="font-mono text-[11px] uppercase tracking-wider text-slate-500 dark:text-slate-400 font-semibold">
          Liquid Reserves
        </span>
        <span class="text-xs px-2.5 py-0.5 rounded-full font-mono bg-sky-200/60 dark:bg-sky-950 text-sky-900 dark:text-sky-300 font-medium">
          Current & Savings
        </span>
      </div>
      <div class="text-3xl font-extrabold tracking-tight sensitive text-sky-800 dark:text-sky-300 mt-3 font-mono">
        {{ summary?.formatted_total_liquid || zeroDisplay }}
      </div>
      <p class="text-xs text-slate-500 dark:text-slate-400 mt-1.5">
        Immediate deployable capital across bank accounts
      </p>
    </div>

    <!-- Invested Assets Card -->
    <div class="relative overflow-hidden rounded-xl border border-indigo-200 dark:border-indigo-800/50 bg-gradient-to-br from-indigo-50/70 via-white to-indigo-100/50 dark:from-brand-darksurface dark:via-brand-darksurface dark:to-indigo-950/40 p-6 shadow-sm transition">
      <div class="flex items-center justify-between">
        <span class="font-mono text-[11px] uppercase tracking-wider text-slate-500 dark:text-slate-400 font-semibold">
          Invested Assets
        </span>
        <span class="text-xs px-2.5 py-0.5 rounded-full font-mono bg-indigo-200/60 dark:bg-indigo-950 text-indigo-900 dark:text-indigo-300 font-medium">
          Portfolios
        </span>
      </div>
      <div class="text-3xl font-extrabold tracking-tight sensitive text-indigo-800 dark:text-indigo-300 mt-3 font-mono">
        {{ summary?.formatted_total_invested || zeroDisplay }}
      </div>
      <p class="text-xs text-slate-500 dark:text-slate-400 mt-1.5">
        Securities, funds, crypto & pensions
      </p>
    </div>

    <!-- Credit Liabilities Card -->
    <div class="relative overflow-hidden rounded-xl border border-rose-200 dark:border-rose-800/50 bg-gradient-to-br from-rose-50/70 via-white to-rose-100/50 dark:from-brand-darksurface dark:via-brand-darksurface dark:to-rose-950/40 p-6 shadow-sm transition">
      <div class="flex items-center justify-between">
        <span class="font-mono text-[11px] uppercase tracking-wider text-slate-500 dark:text-slate-400 font-semibold">
          Credit Liabilities
        </span>
        <span class="text-xs px-2.5 py-0.5 rounded-full font-mono bg-rose-200/60 dark:bg-rose-950 text-rose-900 dark:text-rose-300 font-medium">
          Unsettled Debt
        </span>
      </div>
      <div class="text-3xl font-extrabold tracking-tight sensitive text-rose-700 dark:text-rose-400 mt-3 font-mono">
        {{ summary?.formatted_total_debt || zeroDisplay }}
      </div>
      <p class="text-xs text-slate-500 dark:text-slate-400 mt-1.5">
        Active credit card statement balances
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { DashboardSummary } from '../types';
import { useSystemStore } from '../stores/system';

defineProps<{
  summary: DashboardSummary | null;
}>();

const systemStore = useSystemStore();
const zeroDisplay = computed(() => `${systemStore.config?.base_currency_symbol || '£'}0.00`);
</script>
