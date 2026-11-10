<template>
  <div 
    v-if="isOpen" 
    class="fixed inset-0 z-50 bg-slate-950/40 backdrop-blur-sm flex items-center justify-center p-4"
    @click.self="$emit('close')">
    <section 
      role="dialog" 
      aria-modal="true" 
      aria-labelledby="add-account-title"
      class="bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-5 transition-all">
      
      <div class="flex items-center justify-between pb-3 border-b border-brand-border dark:border-brand-darkborder">
        <div>
          <h2 id="add-account-title" class="font-bold text-slate-900 dark:text-white">Add Financial Account</h2>
          <p class="text-xs text-slate-500 dark:text-slate-400">Current, savings, credit cards or investment portfolios.</p>
        </div>
        <button 
          @click="$emit('close')" 
          class="text-slate-400 hover:text-slate-600 dark:hover:text-white text-lg"
          aria-label="Close dialog">
          &times;
        </button>
      </div>

      <form @submit.prevent="handleSubmit" class="space-y-4">
        <div v-if="errorMessage" class="p-3 rounded-lg bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 text-rose-600 dark:text-rose-400 text-xs">
          {{ errorMessage }}
        </div>

        <div>
          <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
            Account Name
          </label>
          <input 
            v-model="name" 
            type="text" 
            required 
            placeholder="e.g. Barclays Current, Amex Gold, Vanguard ISA" 
            class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3.5 py-2.5 text-xs text-slate-900 dark:text-white focus:outline-none focus:border-slate-400 dark:focus:border-slate-600" />
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
              Account Type
            </label>
            <select 
              v-model="accountType" 
              class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2.5 text-xs text-slate-900 dark:text-white focus:outline-none">
              <option value="current">Current</option>
              <option value="savings">Savings</option>
              <option value="cash">Cash</option>
              <option value="credit_card">Credit Card</option>
              <option value="investment">Investment</option>
            </select>
          </div>

          <div>
            <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
              Currency
            </label>
            <input 
              :value="baseCurrency" 
              type="text" 
              disabled
              title="All financial accounts must use the configured base currency."
              class="w-full bg-slate-100 dark:bg-slate-800/60 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2.5 text-xs font-mono uppercase text-slate-500 dark:text-slate-400 cursor-not-allowed" />
            <span class="text-[10px] text-slate-400 mt-1 block">Locked to base ledger currency</span>
          </div>
        </div>

        <!-- Investment Account Info Banner -->
        <div v-if="accountType === 'investment'" class="p-3.5 rounded-xl border border-indigo-200 dark:border-indigo-900/40 bg-indigo-50/50 dark:bg-indigo-950/20 text-indigo-700 dark:text-indigo-300 text-xs space-y-1">
          <div class="font-semibold flex items-center space-x-1.5">
            <span>📈</span>
            <span>Holdings-Based Balance</span>
          </div>
          <p class="text-[11px] text-indigo-600/90 dark:text-indigo-300/80">
            Investment accounts derive their total balance automatically from active holdings and their latest valuations. No opening balance is required.
          </p>
        </div>

        <template v-else>
          <div>
            <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
              Starting Balance ({{ baseSymbol }})
            </label>
            <input 
              v-model.number="startingBalance" 
              type="number" 
              step="0.01" 
              placeholder="0.00" 
              class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3.5 py-2.5 text-xs font-mono font-semibold text-slate-900 dark:text-white focus:outline-none" />
            <span class="text-[10px] text-slate-400 mt-1 block">Negative values for starting credit card debt.</span>
          </div>

          <div>
            <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
              Correct as of
            </label>
            <div class="flex items-center space-x-2">
              <button
                type="button"
                @click="asOfMode = 'now'"
                :class="[
                  'px-3.5 py-1.5 text-xs rounded-lg font-medium transition',
                  asOfMode === 'now'
                    ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-900 shadow-sm'
                    : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'
                ]">
                Now
              </button>
              <button
                type="button"
                @click="asOfMode = 'date'"
                :class="[
                  'px-3.5 py-1.5 text-xs rounded-lg font-medium transition',
                  asOfMode === 'date'
                    ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-900 shadow-sm'
                    : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'
                ]">
                Past Date
              </button>
              <input
                v-if="asOfMode === 'date'"
                v-model="asOfDate"
                type="date"
                required
                class="flex-1 bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-1.5 text-xs text-slate-900 dark:text-white focus:outline-none" />
            </div>
            <span class="text-[10px] text-slate-400 mt-1 block">
              {{ asOfMode === 'now' 
                ? 'Captures current exact timestamp. Transactions entered afterward will adjust this balance.' 
                : 'Closing balance on this date. Transactions on or before this cutoff are already included.' }}
            </span>
          </div>
        </template>

        <div>
          <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
            Accent Badge Color
          </label>
          <div class="flex items-center space-x-2">
            <input 
              v-model="color" 
              type="color" 
              class="w-9 h-9 p-0 rounded-lg border border-brand-border dark:border-brand-darkborder bg-transparent cursor-pointer" />
            <div class="flex space-x-1.5">
              <button 
                v-for="c in presetColors" 
                :key="c" 
                type="button" 
                @click="color = c"
                class="w-6 h-6 rounded-full border border-black/10 transition transform hover:scale-110"
                :style="{ backgroundColor: c }"
                :title="c">
              </button>
            </div>
          </div>
        </div>

        <div class="pt-3 flex justify-end space-x-2.5 border-t border-brand-border dark:border-brand-darkborder">
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
            {{ isSubmitting ? 'Creating...' : 'Create Account' }}
          </button>
        </div>
      </form>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import type { AccountType } from '../types';
import { useSystemStore } from '../stores/system';

defineProps<{
  isOpen: boolean;
}>();

const emit = defineEmits(['close', 'created']);
const systemStore = useSystemStore();

const baseCurrency = computed(() => systemStore.config?.base_currency || 'GBP');
const baseSymbol = computed(() => systemStore.config?.base_currency_symbol || '£');

const name = ref('');
const accountType = ref<AccountType>('current');
const startingBalance = ref<number>(0);
const asOfMode = ref<'now' | 'date'>('now');
const asOfDate = ref<string>(new Date().toISOString().split('T')[0]);
const color = ref('#3B82F6');
const isSubmitting = ref(false);
const errorMessage = ref<string | null>(null);

const presetColors = ['#3B82F6', '#10B981', '#8B5CF6', '#F59E0B', '#EF4444', '#06B6D4'];

async function handleSubmit() {
  if (!name.value.trim()) return;
  isSubmitting.value = true;
  errorMessage.value = null;

  const isInvestment = accountType.value === 'investment';
  try {
    emit('created', {
      name: name.value.trim(),
      account_type: accountType.value,
      currency: baseCurrency.value,
      starting_balance: isInvestment ? 0 : (startingBalance.value || 0),
      as_of_mode: isInvestment ? undefined : asOfMode.value,
      as_of_date: (!isInvestment && asOfMode.value === 'date') ? asOfDate.value : undefined,
      valuation_mode: isInvestment ? 'holdings' : 'snapshot',
      color: color.value,
    });
    // Reset form
    name.value = '';
    startingBalance.value = 0;
    asOfMode.value = 'now';
    asOfDate.value = new Date().toISOString().split('T')[0];
  } catch (err: any) {
    errorMessage.value = err.message || 'Failed to create account.';
  } finally {
    isSubmitting.value = false;
  }
}
</script>

