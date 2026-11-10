<template>
  <div 
    v-if="isOpen && account" 
    class="fixed inset-0 z-50 bg-slate-950/60 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto animate-fadeIn"
    @click.self="$emit('close')">
    <section 
      role="dialog" 
      aria-modal="true" 
      aria-labelledby="delete-account-title"
      class="bg-white dark:bg-brand-darksurface border border-rose-200 dark:border-rose-900/60 rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-5 transition-all my-8">
      
      <!-- Modal Header -->
      <div class="flex items-center justify-between pb-3 border-b border-brand-border dark:border-brand-darkborder">
        <div class="flex items-center space-x-2">
          <div class="w-8 h-8 rounded-full bg-rose-100 dark:bg-rose-950/80 text-rose-600 dark:text-rose-400 flex items-center justify-center font-bold text-base">
            ⚠️
          </div>
          <div>
            <h2 id="delete-account-title" class="font-bold text-slate-900 dark:text-white text-base">
              Permanently Delete Account
            </h2>
            <p class="text-xs text-rose-600 dark:text-rose-400 font-semibold">
              Step {{ step }} of 2: {{ step === 1 ? 'Review Destruction Impact' : 'Confirm Permanent Deletion' }}
            </p>
          </div>
        </div>
        <button 
          @click="$emit('close')" 
          class="text-slate-400 hover:text-slate-600 dark:hover:text-white text-lg"
          aria-label="Close dialog">
          &times;
        </button>
      </div>

      <!-- Error Banner -->
      <div v-if="errorMessage" class="p-3 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 text-rose-600 dark:text-rose-400 text-xs">
        {{ errorMessage }}
      </div>

      <!-- STEP 1: Impact Summary & Safety Backup -->
      <div v-if="step === 1" class="space-y-4">
        <div class="p-3.5 rounded-xl bg-rose-50/80 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-900/50 text-xs text-rose-900 dark:text-rose-200 space-y-2">
          <p class="font-bold">
            Permanent deletion is irreversible.
          </p>
          <p class="text-[11px] leading-relaxed">
            Deleting <span class="font-mono font-bold">{{ account.name }}</span> will permanently erase the account and all linked financial records from your database.
          </p>
        </div>

        <!-- Impact Breakdown List -->
        <div class="p-4 rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50 dark:bg-slate-800/40 space-y-2.5">
          <span class="text-[11px] font-mono uppercase tracking-wider font-bold text-slate-500 block">
            Financial Records Affected
          </span>

          <div v-if="loadingImpact" class="py-4 text-center text-xs text-slate-400 animate-pulse">
            Analyzing account ledger records...
          </div>

          <div v-else-if="impact" class="grid grid-cols-2 gap-2 text-xs">
            <div class="p-2.5 rounded-lg bg-white dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder">
              <span class="text-[10px] text-slate-400 font-mono uppercase block">Standard Transactions</span>
              <span class="text-sm font-bold font-mono text-slate-900 dark:text-white">{{ impact.transaction_count }}</span>
              <span class="text-[10px] text-slate-400 block mt-0.5">Primary debits/credits</span>
            </div>

            <div class="p-2.5 rounded-lg bg-white dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder">
              <span class="text-[10px] text-slate-400 font-mono uppercase block">Linked Transfers</span>
              <span class="text-sm font-bold font-mono text-slate-900 dark:text-white">{{ impact.transfer_count }}</span>
              <span class="text-[10px] text-slate-400 block mt-0.5">Source & destination</span>
            </div>

            <div class="p-2.5 rounded-lg bg-white dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder">
              <span class="text-[10px] text-slate-400 font-mono uppercase block">Reconciliation Snapshots</span>
              <span class="text-sm font-bold font-mono text-slate-900 dark:text-white">{{ impact.snapshot_count }}</span>
              <span class="text-[10px] text-slate-400 block mt-0.5">Verification checkpoints</span>
            </div>

            <div class="p-2.5 rounded-lg bg-white dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder">
              <span class="text-[10px] text-slate-400 font-mono uppercase block">Holdings & Valuations</span>
              <span class="text-sm font-bold font-mono text-slate-900 dark:text-white">{{ impact.holding_count }} ({{ impact.holding_valuation_count }} vals)</span>
              <span class="text-[10px] text-slate-400 block mt-0.5">Investment assets</span>
            </div>
          </div>
        </div>

        <!-- Optional Safety Backup Offer -->
        <div class="p-3.5 rounded-xl border border-brand-border dark:border-brand-darkborder bg-indigo-50/50 dark:bg-indigo-950/20 space-y-2">
          <div class="flex items-center justify-between">
            <div>
              <span class="text-xs font-bold text-slate-900 dark:text-white block">Pre-Deletion Safety Backup</span>
              <span class="text-[11px] text-slate-500 dark:text-slate-400">
                Generate an immediate verified backup before destroying records.
              </span>
            </div>
            <button
              type="button"
              @click="handleCreateSafetyBackup"
              :disabled="isBackingUp"
              class="px-3 py-1.5 rounded-full text-xs font-semibold bg-indigo-600 text-white hover:bg-indigo-500 transition disabled:opacity-50 shrink-0">
              {{ isBackingUp ? 'Backing up...' : 'Create Backup Now' }}
            </button>
          </div>
          <div v-if="backupCreatedMsg" class="text-[11px] font-mono text-emerald-600 dark:text-emerald-400">
            ✓ {{ backupCreatedMsg }}
          </div>
        </div>

        <!-- Safer Alternative: Archive -->
        <div class="p-3.5 rounded-xl border border-amber-200 dark:border-amber-900/50 bg-amber-50/60 dark:bg-amber-950/20 space-y-1.5">
          <span class="text-xs font-bold text-amber-900 dark:text-amber-300 block">
            Recommended Safe Alternative: Archive Account
          </span>
          <p class="text-[11px] text-amber-800 dark:text-amber-400">
            Archiving hides this account from active lists and selection dropdowns without modifying or deleting any historical transactions, balances, or reports.
          </p>
          <button
            type="button"
            @click="handleArchiveInstead"
            :disabled="isArchiving"
            class="mt-1 px-4 py-1.5 rounded-full text-xs font-semibold border border-amber-300 dark:border-amber-800 text-amber-800 dark:text-amber-300 hover:bg-amber-100 dark:hover:bg-amber-900/40 transition">
            {{ isArchiving ? 'Archiving...' : 'Archive This Account Instead' }}
          </button>
        </div>

        <!-- Step 1 Footer -->
        <div class="pt-3 flex items-center justify-between border-t border-brand-border dark:border-brand-darkborder">
          <button 
            type="button" 
            @click="$emit('close')" 
            class="px-4 py-2 text-xs font-semibold rounded-full border border-brand-border dark:border-brand-darkborder text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800">
            Cancel
          </button>
          <button 
            type="button" 
            @click="step = 2"
            :disabled="loadingImpact"
            class="px-5 py-2 text-xs font-semibold rounded-full bg-rose-600 text-white hover:bg-rose-700 transition disabled:opacity-50">
            Proceed to Final Confirmation &rarr;
          </button>
        </div>
      </div>

      <!-- STEP 2: Name Matching Confirmation -->
      <div v-else-if="step === 2" class="space-y-4">
        <div class="p-4 rounded-xl border border-rose-200 dark:border-rose-900/60 bg-rose-50/60 dark:bg-rose-950/30 text-xs text-rose-900 dark:text-rose-200 space-y-2">
          <p class="font-bold text-sm">
            Final Confirmation
          </p>
          <p class="text-xs leading-relaxed">
            You are about to permanently delete account <span class="font-bold underline">{{ account.name }}</span> and all of its associated records. This action <span class="font-bold uppercase">cannot be undone</span>.
          </p>
        </div>

        <div class="space-y-1.5">
          <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300">
            Type <span class="font-mono font-bold text-slate-900 dark:text-white px-1 py-0.5 rounded bg-slate-100 dark:bg-slate-800">{{ account.name }}</span> to confirm:
          </label>
          <input
            v-model="typedName"
            type="text"
            :placeholder="account.name"
            class="w-full rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50 dark:bg-slate-800 px-3.5 py-2.5 text-xs text-slate-900 dark:text-white font-mono focus:outline-none focus:border-rose-500" />
        </div>

        <!-- Step 2 Footer -->
        <div class="pt-3 flex items-center justify-between border-t border-brand-border dark:border-brand-darkborder">
          <button 
            type="button" 
            @click="step = 1" 
            class="px-4 py-2 text-xs font-semibold rounded-full border border-brand-border dark:border-brand-darkborder text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800">
            &larr; Back to Summary
          </button>
          <button 
            type="button" 
            @click="handlePermanentDelete"
            :disabled="!isNameMatched || isDeleting"
            class="px-5 py-2 text-xs font-semibold rounded-full bg-rose-600 text-white hover:bg-rose-700 transition disabled:opacity-40 disabled:cursor-not-allowed">
            {{ isDeleting ? 'Permanently Deleting...' : 'Permanently Delete Account' }}
          </button>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import type { Account, AccountDeletionImpact } from '../types';
import { api } from '../api/client';
import { useAccountsStore } from '../stores/accounts';
import { useSystemStore } from '../stores/system';

const props = defineProps<{
  isOpen: boolean;
  account: Account | null;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'deleted'): void;
  (e: 'archived'): void;
}>();

const accountsStore = useAccountsStore();
const systemStore = useSystemStore();

const step = ref<1 | 2>(1);
const impact = ref<AccountDeletionImpact | null>(null);
const loadingImpact = ref(false);
const typedName = ref('');
const isDeleting = ref(false);
const isArchiving = ref(false);
const isBackingUp = ref(false);
const backupCreatedMsg = ref<string | null>(null);
const errorMessage = ref<string | null>(null);

const isNameMatched = computed(() => {
  if (!props.account) return false;
  return typedName.value.trim() === props.account.name.trim();
});

watch(() => props.isOpen, (open) => {
  if (open && props.account) {
    step.value = 1;
    typedName.value = '';
    errorMessage.value = null;
    backupCreatedMsg.value = null;
    loadImpact(props.account.id);
  }
});

async function loadImpact(accountId: number) {
  loadingImpact.value = true;
  impact.value = null;
  try {
    impact.value = await api.getAccountDeletionImpact(accountId);
  } catch (err: any) {
    errorMessage.value = err.message || 'Failed to calculate account deletion impact.';
  } finally {
    loadingImpact.value = false;
  }
}

async function handleCreateSafetyBackup() {
  isBackingUp.value = true;
  errorMessage.value = null;
  try {
    const res = await systemStore.createBackup();
    backupCreatedMsg.value = `Verified backup saved: ${res.filename} (${res.size_formatted})`;
  } catch (err: any) {
    errorMessage.value = err.message || 'Failed to create safety backup.';
  } finally {
    isBackingUp.value = false;
  }
}

async function handleArchiveInstead() {
  if (!props.account) return;
  isArchiving.value = true;
  errorMessage.value = null;
  try {
    await accountsStore.archiveAccount(props.account.id);
    emit('archived');
    emit('close');
  } catch (err: any) {
    errorMessage.value = err.message || 'Failed to archive account.';
  } finally {
    isArchiving.value = false;
  }
}

async function handlePermanentDelete() {
  if (!props.account || !isNameMatched.value) return;
  isDeleting.value = true;
  errorMessage.value = null;
  try {
    await accountsStore.permanentlyDeleteAccount(props.account.id);
    emit('deleted');
    emit('close');
  } catch (err: any) {
    errorMessage.value = err.message || 'Failed to permanently delete account.';
  } finally {
    isDeleting.value = false;
  }
}
</script>

