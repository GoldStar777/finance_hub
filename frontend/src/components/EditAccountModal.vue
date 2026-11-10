<template>
  <div 
    v-if="isOpen && account" 
    class="fixed inset-0 z-50 bg-slate-950/40 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto animate-fadeIn"
    @click.self="$emit('close')">
    <section 
      role="dialog" 
      aria-modal="true" 
      aria-labelledby="edit-account-title"
      class="bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-5 transition-all my-8">
      
      <!-- Modal Header -->
      <div class="flex items-center justify-between pb-3 border-b border-brand-border dark:border-brand-darkborder">
        <div>
          <h2 id="edit-account-title" class="font-bold text-slate-900 dark:text-white">
            Manage Account: {{ account.name }}
          </h2>
          <p class="text-xs text-slate-500 dark:text-slate-400">
            Edit account details, visual color, or archive status.
          </p>
        </div>
        <button 
          @click="$emit('close')" 
          class="text-slate-400 hover:text-slate-600 dark:hover:text-white text-lg"
          aria-label="Close dialog">
          &times;
        </button>
      </div>

      <form @submit.prevent="handleSubmit" class="space-y-4">
        <!-- Error Banner -->
        <div v-if="errorMessage" class="p-3 rounded-lg bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 text-rose-600 dark:text-rose-400 text-xs">
          {{ errorMessage }}
        </div>

        <!-- Account Name -->
        <div>
          <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
            Account Name
          </label>
          <input 
            v-model="name" 
            type="text" 
            required 
            class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3.5 py-2.5 text-xs text-slate-900 dark:text-white focus:outline-none" />
        </div>

        <div class="grid grid-cols-2 gap-3">
          <!-- Account Type -->
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

          <!-- Currency (Read-Only) -->
          <div>
            <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
              Currency
            </label>
            <input 
              :value="account.currency" 
              disabled 
              class="w-full bg-slate-100 dark:bg-slate-800/50 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2.5 text-xs font-mono font-semibold text-slate-500 cursor-not-allowed" />
          </div>
        </div>


        <!-- Opening Balance Anchor -->
        <div v-if="accountType !== 'investment'" class="p-3 rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50/60 dark:bg-slate-800/30 space-y-2">
          <div class="flex items-center justify-between">
            <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500">
              Opening Balance Anchor
            </label>
            <span v-if="account.anchor_label" class="text-[10px] text-slate-500 dark:text-slate-400 font-mono">
              {{ account.anchor_label }}
            </span>
          </div>
          <input 
            v-model.number="startingBalance" 
            type="number" 
            step="0.01" 
            class="w-full bg-white dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3.5 py-2 text-xs font-mono font-semibold text-slate-900 dark:text-white focus:outline-none" />

          <div class="flex items-center space-x-2 pt-1">
            <button
              type="button"
              @click="asOfMode = 'now'"
              :class="[
                'px-3 py-1 text-[11px] rounded-lg font-medium transition',
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
                'px-3 py-1 text-[11px] rounded-lg font-medium transition',
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
              class="flex-1 bg-white dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-2.5 py-1 text-xs text-slate-900 dark:text-white focus:outline-none" />
          </div>
        </div>

        <!-- Color Picker -->
        <div>
          <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
            Accent Color
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
                :style="{ backgroundColor: c }">
              </button>
            </div>
          </div>
        </div>

        <!-- Archive Section -->
        <div class="pt-2 border-t border-brand-border dark:border-brand-darkborder">
          <div class="p-3 rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50/60 dark:bg-slate-800/30 space-y-2">
            <div class="flex items-center justify-between text-xs">
              <span class="font-bold text-slate-900 dark:text-white flex items-center space-x-1.5">
                <span>{{ account.is_active ? '📦' : '♻️' }}</span>
                <span>{{ account.is_active ? 'Archive Account' : 'Reactivate Account' }}</span>
              </span>
              <span 
                class="px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold"
                :class="account.is_active ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-300'">
                {{ account.is_active ? 'Active' : 'Archived' }}
              </span>
            </div>

            <p class="text-[11px] text-slate-500 dark:text-slate-400">
              {{ account.is_active 
                ? 'Archiving hides this account from active lists and selection menus. All historical transactions, balances, and reports remain safely preserved and will NOT be deleted.' 
                : 'Reactivating restores this account to active lists and selection dropdowns.' }}
            </p>

            <button
              type="button"
              @click="handleToggleArchive"
              :disabled="isArchiving"
              class="w-full py-1.5 px-3 rounded-lg text-xs font-semibold transition flex items-center justify-center space-x-1"
              :class="account.is_active 
                ? 'border border-amber-300 text-amber-700 hover:bg-amber-50 dark:border-amber-900 dark:text-amber-400 dark:hover:bg-amber-950/40' 
                : 'bg-emerald-600 text-white hover:bg-emerald-500'">
              <span>{{ isArchiving ? 'Processing...' : (account.is_active ? 'Archive This Account' : 'Reactivate Account') }}</span>
            </button>

            <!-- Permanent Deletion Link -->
            <div class="pt-2 border-t border-slate-200 dark:border-slate-700/60 flex items-center justify-between text-xs">
              <span class="text-[11px] text-slate-500 dark:text-slate-400">Need to erase account & records?</span>
              <button
                type="button"
                @click="openDeleteModal"
                class="text-[11px] font-semibold text-rose-600 dark:text-rose-400 hover:underline">
                Permanently Delete...
              </button>
            </div>
          </div>
        </div>

        <!-- Footer -->
        <div class="pt-2 flex items-center justify-end space-x-2.5 border-t border-brand-border dark:border-brand-darkborder">
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
            {{ isSubmitting ? 'Saving...' : 'Save Changes' }}
          </button>
        </div>
      </form>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import type { Account, AccountType } from '../types';
import { useAccountsStore } from '../stores/accounts';

const props = defineProps<{
  isOpen: boolean;
  account: Account | null;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'saved'): void;
  (e: 'delete', account: Account): void;
}>();

const accountsStore = useAccountsStore();

const name = ref('');
const accountType = ref<AccountType>('current');
const color = ref('#3B82F6');
const startingBalance = ref<number>(0);
const asOfMode = ref<'now' | 'date'>('now');
const asOfDate = ref<string>(new Date().toISOString().split('T')[0]);

const isSubmitting = ref(false);
const isArchiving = ref(false);
const errorMessage = ref<string | null>(null);

const presetColors = [
  '#3B82F6', '#10B981', '#6366F1', '#EC4899', '#F59E0B', '#8B5CF6', '#14B8A6', '#64748B'
];

watch(() => props.isOpen, (open) => {
  if (open && props.account) {
    populateForm(props.account);
  }
});

function populateForm(acc: Account) {
  errorMessage.value = null;
  name.value = acc.name;
  accountType.value = acc.account_type;
  color.value = acc.color || '#3B82F6';
  startingBalance.value = acc.starting_balance_pounds || 0;
  asOfMode.value = 'now';
  if (acc.anchor_date) {
    asOfDate.value = acc.anchor_date.split('T')[0];
  }
}

async function handleSubmit() {
  if (!props.account) return;
  isSubmitting.value = true;
  errorMessage.value = null;

  try {
    await accountsStore.updateAccount(props.account.id, {
      name: name.value.trim(),
      account_type: accountType.value,
      color: color.value,
      starting_balance: startingBalance.value,
      as_of_mode: asOfMode.value,
      as_of_date: asOfMode.value === 'date' ? asOfDate.value : undefined,
    });
    emit('saved');
    emit('close');
  } catch (err: any) {
    errorMessage.value = err.message || 'Failed to update account.';
  } finally {
    isSubmitting.value = false;
  }
}

async function handleToggleArchive() {
  if (!props.account) return;
  const willArchive = props.account.is_active;

  if (willArchive) {
    if (!confirm(`Are you sure you want to archive "${props.account.name}"? Historical transactions and balances will remain safe, but the account will be hidden from active lists.`)) {
      return;
    }
  }

  isArchiving.value = true;
  errorMessage.value = null;

  try {
    if (willArchive) {
      await accountsStore.archiveAccount(props.account.id);
    } else {
      await accountsStore.unarchiveAccount(props.account.id);
    }
    emit('saved');
    emit('close');
  } catch (err: any) {
    errorMessage.value = err.message || 'Failed to update archive status.';
  } finally {
    isArchiving.value = false;
  }
}

function openDeleteModal() {
  if (!props.account) return;
  emit('delete', props.account);
  emit('close');
}
</script>

