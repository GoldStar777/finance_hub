<template>
  <div class="space-y-8 animate-fadeIn">
    <!-- Top Hero Metrics -->
    <SummaryCards :summary="accountsStore.summary" />

    <!-- Accounts Section -->
    <section class="space-y-4">
      <div class="flex items-center justify-between">
        <div>
          <h2 class="text-sm font-bold text-slate-900 dark:text-white uppercase tracking-wider font-mono">
            Accounts
          </h2>
          <p class="text-xs text-slate-500">
            Click any account card to view its ground-truth balance breakdown and history.
          </p>
        </div>
        <div class="flex items-center space-x-2">
          <button 
            type="button"
            @click="accountsStore.toggleShowArchived()"
            class="text-xs font-semibold px-3 py-1.5 rounded-full border transition"
            :class="accountsStore.showArchived 
              ? 'border-indigo-300 dark:border-indigo-700 bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300' 
              : 'border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-400'">
            {{ accountsStore.showArchived ? 'Hide Archived' : 'Show Archived' }}
          </button>
          <button 
            @click="$emit('open-add-account')" 
            class="px-3.5 py-1.5 text-xs font-semibold rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 shadow-sm hover:opacity-90 transition flex items-center space-x-1.5"
            title="Add a new financial account">
            <span>+</span>
            <span>Add Account</span>
          </button>
          <button 
            @click="$emit('open-manage-accounts-categories')" 
            class="px-3 py-1.5 text-xs font-semibold rounded-full border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
            title="Manage Accounts & Categories">
            <span>Manage Accounts</span>
          </button>
        </div>
      </div>

      <!-- Loading State -->
      <div v-if="accountsStore.loading && accountsStore.accounts.length === 0" class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        <div v-for="i in 4" :key="i" class="h-32 rounded-xl bg-slate-100 dark:bg-slate-800/40 animate-pulse"></div>
      </div>

      <!-- Error State -->
      <div v-else-if="accountsStore.error" class="p-6 rounded-xl border border-rose-200 dark:border-rose-900 bg-rose-50 dark:bg-rose-950/30 text-rose-600 dark:text-rose-400 text-xs">
        {{ accountsStore.error }}
      </div>

      <!-- Accounts Groups -->
      <div v-else-if="accountsStore.accounts.length > 0" class="space-y-6" data-testid="dashboard-account-groups">
        <div v-for="grp in accountGroups" :key="grp.id" class="space-y-3">
          <div class="flex items-center justify-between border-b border-brand-border/60 dark:border-brand-darkborder/60 pb-1.5">
            <div class="flex items-center space-x-2">
              <h3 class="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wider font-mono">
                {{ grp.title }}
              </h3>
              <span class="text-[10px] font-mono px-2 py-0.2 rounded-full border font-semibold" :class="grp.badgeClass">
                {{ grp.badge }}
              </span>
              <span class="text-[11px] text-slate-400 hidden sm:inline">
                · {{ grp.subtitle }}
              </span>
            </div>
            <div class="text-xs font-mono font-bold text-slate-700 dark:text-slate-300">
              <span class="text-[10px] uppercase font-normal text-slate-400 mr-1.5">Subtotal:</span>
              <span :class="grp.totalPence < 0 ? 'text-rose-600 dark:text-rose-400' : 'text-slate-900 dark:text-white'">
                {{ grp.formattedTotal }}
              </span>
            </div>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            <AccountCard 
              v-for="acc in grp.accounts" 
              :key="acc.id" 
              :account="acc"
              @inspect="openAccountDetailModal"
              @reconcile="openReconcileModal"
              @edit="openEditAccountModal" />
          </div>
        </div>
      </div>

      <!-- Empty State -->
      <div v-else class="border border-brand-border dark:border-brand-darkborder rounded-2xl bg-white/60 dark:bg-brand-darksurface/60 p-12 text-center space-y-3">
        <div class="w-10 h-10 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-500 mx-auto flex items-center justify-center font-bold">
          💳
        </div>
        <p class="text-slate-900 dark:text-white font-semibold">No accounts configured yet</p>
        <p class="text-xs text-slate-500 max-w-sm mx-auto">Add your bank current account, credit card, or savings account to start tracking balances.</p>
        <button 
          @click="$emit('open-manage-accounts-categories')" 
          class="mt-2 px-4 py-2 text-xs font-semibold rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 shadow-sm hover:opacity-90 transition">
          + Add First Account
        </button>
      </div>
    </section>

    <!-- Recent Activity Section -->
    <RecentActivity 
      @open-record="txStore.openRecordModal()" />

    <!-- Modals -->
    <AccountDetailModal
      :is-open="isDetailModalOpen"
      :account-id="selectedDetailAccountId"
      @close="isDetailModalOpen = false; selectedDetailAccountId = null"
      @edit="openEditAccountModal"
      @reconcile="openReconcileModal" />

    <AddAccountModal 
      :is-open="isModalOpen" 
      @close="isModalOpen = false" 
      @created="handleAccountCreated" />

    <ReconcileAccountModal
      :is-open="isReconcileOpen"
      :account="reconcilingAccount"
      @close="isReconcileOpen = false"
      @reconciled="handleReconciled" />

    <EditAccountModal
      :is-open="isEditAccountOpen"
      :account="editingAccount"
      @close="isEditAccountOpen = false"
      @saved="handleAccountSaved"
      @delete="openDeleteAccountModal" />

    <DeleteAccountModal
      :is-open="isDeleteAccountOpen"
      :account="deletingAccount"
      @close="isDeleteAccountOpen = false"
      @deleted="handleAccountDeleted"
      @archived="handleAccountSaved" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useAccountsStore } from '../stores/accounts';
import { useTransactionsStore } from '../stores/transactions';
import { useSystemStore } from '../stores/system';
import SummaryCards from '../components/SummaryCards.vue';
import AccountCard from '../components/AccountCard.vue';
import AccountDetailModal from '../components/AccountDetailModal.vue';
import RecentActivity from '../components/RecentActivity.vue';
import AddAccountModal from '../components/AddAccountModal.vue';
import EditAccountModal from '../components/EditAccountModal.vue';
import DeleteAccountModal from '../components/DeleteAccountModal.vue';
import ReconcileAccountModal from '../components/ReconcileAccountModal.vue';
import type { Account, AccountCreatePayload } from '../types';

const accountsStore = useAccountsStore();
const txStore = useTransactionsStore();
const systemStore = useSystemStore();

defineEmits(['open-manage-accounts-categories', 'open-add-account']);

const isModalOpen = ref(false);
const isReconcileOpen = ref(false);
const reconcilingAccount = ref<Account | null>(null);
const isEditAccountOpen = ref(false);
const editingAccount = ref<Account | null>(null);
const isDeleteAccountOpen = ref(false);
const deletingAccount = ref<Account | null>(null);
const isDetailModalOpen = ref(false);
const selectedDetailAccountId = ref<number | null>(null);

const currencySymbol = computed(() => systemStore.config?.base_currency_symbol || '£');

function formatPence(pence: number, symbol = '£'): string {
  const abs = Math.abs(pence);
  const formatted = (abs / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return pence < 0 ? `-${symbol}${formatted}` : `${symbol}${formatted}`;
}

const accountGroups = computed(() => {
  const all = accountsStore.accounts;
  const groups: Array<{
    id: string;
    title: string;
    subtitle: string;
    badge: string;
    badgeClass: string;
    accounts: Account[];
    totalPence: number;
    formattedTotal: string;
  }> = [];

  const depository = all.filter(a => a.account_type === 'current' || a.account_type === 'savings');
  if (depository.length > 0) {
    const tot = depository.reduce((s, a) => s + (a.current_balance_pence || 0), 0);
    groups.push({
      id: 'depository',
      title: 'Depository Accounts',
      subtitle: 'Checking & Savings bank balances',
      badge: 'Liquid Assets',
      badgeClass: 'bg-blue-50 dark:bg-blue-950/60 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-900/40',
      accounts: depository,
      totalPence: tot,
      formattedTotal: formatPence(tot, currencySymbol.value)
    });
  }

  const cashAccounts = all.filter(a => a.account_type === 'cash');
  if (cashAccounts.length > 0) {
    const tot = cashAccounts.reduce((s, a) => s + (a.current_balance_pence || 0), 0);
    groups.push({
      id: 'cash',
      title: 'Cash Accounts',
      subtitle: 'Physical cash & wallet balances',
      badge: 'Liquid Cash',
      badgeClass: 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-900/40',
      accounts: cashAccounts,
      totalPence: tot,
      formattedTotal: formatPence(tot, currencySymbol.value)
    });
  }

  const credit = all.filter(a => a.account_type === 'credit_card');
  if (credit.length > 0) {
    const tot = credit.reduce((s, a) => s + (a.current_balance_pence || 0), 0);
    groups.push({
      id: 'credit',
      title: 'Credit Liabilities',
      subtitle: 'Credit cards & revolving credit (negative = owed)',
      badge: 'Liabilities',
      badgeClass: 'bg-rose-50 dark:bg-rose-950/60 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-900/40',
      accounts: credit,
      totalPence: tot,
      formattedTotal: formatPence(tot, currencySymbol.value)
    });
  }

  const investment = all.filter(a => a.account_type === 'investment');
  if (investment.length > 0) {
    const tot = investment.reduce((s, a) => s + (a.current_balance_pence || 0), 0);
    groups.push({
      id: 'investment',
      title: 'Investment Portfolios',
      subtitle: 'Security holdings and brokerages',
      badge: 'Investments',
      badgeClass: 'bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border-indigo-200 dark:border-indigo-900/40',
      accounts: investment,
      totalPence: tot,
      formattedTotal: formatPence(tot, currencySymbol.value)
    });
  }

  const others = all.filter(a => 
    a.account_type !== 'current' && 
    a.account_type !== 'savings' && 
    a.account_type !== 'cash' && 
    a.account_type !== 'credit_card' && 
    a.account_type !== 'investment'
  );
  if (others.length > 0) {
    const tot = others.reduce((s, a) => s + (a.current_balance_pence || 0), 0);
    groups.push({
      id: 'other',
      title: 'Other Accounts',
      subtitle: 'Additional ledger accounts',
      badge: 'Accounts',
      badgeClass: 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border-slate-200 dark:border-slate-700',
      accounts: others,
      totalPence: tot,
      formattedTotal: formatPence(tot, currencySymbol.value)
    });
  }

  return groups;
});

onMounted(() => {
  accountsStore.loadData();
  txStore.loadRecent();
});

function openAccountDetailModal(acc: Account) {
  selectedDetailAccountId.value = acc.id;
  isDetailModalOpen.value = true;
}

function openReconcileModal(acc: Account) {
  reconcilingAccount.value = acc;
  isReconcileOpen.value = true;
}

function openEditAccountModal(acc: Account) {
  editingAccount.value = acc;
  isEditAccountOpen.value = true;
}

function openDeleteAccountModal(acc: Account) {
  deletingAccount.value = acc;
  isDeleteAccountOpen.value = true;
}

async function handleAccountSaved() {
  await accountsStore.loadData();
}

async function handleAccountDeleted() {
  await Promise.all([
    accountsStore.loadData(),
    txStore.loadRecent(),
    txStore.loadTransactions(0),
  ]);
}

async function handleReconciled() {
  await Promise.all([
    accountsStore.loadData(),
    txStore.loadRecent()
  ]);
}

async function handleAccountCreated(payload: AccountCreatePayload) {
  try {
    await accountsStore.createAccount(payload);
    isModalOpen.value = false;
  } catch (err) {
    // Error is set in store
  }
}
</script>
