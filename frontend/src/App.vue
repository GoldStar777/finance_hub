<template>
  <div class="min-h-screen flex flex-col bg-brand-cream dark:bg-brand-darkbg text-slate-800 dark:text-slate-100 transition-colors">
    <CommandHeader 
      :app-name="appName" 
      :show-date-time="showDateTime"
      @open-record-transaction="txStore.openRecordModal()"
      @open-import="isImportModalOpen = true"
      @open-settings="isSettingsOpen = true" />
    
    <main class="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-8">
      <router-view 
        @open-add-account="isManageModalOpen = true"
        @open-manage-accounts-categories="isManageModalOpen = true" />
    </main>

    <ManageAccountsCategoriesModal
      :is-open="isManageModalOpen"
      @close="isManageModalOpen = false" />
    <AddAccountModal 
      :is-open="isAddAccountModalOpen" 
      @close="isAddAccountModalOpen = false" 
      @created="handleAccountCreated" />
    <RecordTransactionModal
      :is-open="txStore.isRecordModalOpen"
      @close="txStore.closeRecordModal()" />
    <UnifiedImportModal
      :is-open="isImportModalOpen"
      @close="isImportModalOpen = false" />
    <AppSettingsModal 
      :is-open="isSettingsOpen" 
      :app-name="appName" 
      :show-date-time="showDateTime"
      @close="isSettingsOpen = false" 
      @save="saveAppName"
      @update:show-date-time="updateShowDateTime"
      @open-manage="handleOpenManageFromSettings"
      @open-profiles="handleOpenProfilesFromSettings" />
    <ManageProfilesModal
      :is-open="isProfilesModalOpen || profilesStore.isManageModalOpen"
      @close="isProfilesModalOpen = false; profilesStore.closeManageModal()" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import CommandHeader from './components/CommandHeader.vue';
import ManageAccountsCategoriesModal from './components/ManageAccountsCategoriesModal.vue';
import ManageProfilesModal from './components/ManageProfilesModal.vue';
import AddAccountModal from './components/AddAccountModal.vue';
import RecordTransactionModal from './components/RecordTransactionModal.vue';
import UnifiedImportModal from './components/UnifiedImportModal.vue';
import AppSettingsModal from './components/AppSettingsModal.vue';
import { useThemeStore } from './stores/theme';
import { useStealthStore } from './stores/stealth';
import { useAccountsStore } from './stores/accounts';
import { useInvestmentsStore } from './stores/investments';
import { useTransactionsStore } from './stores/transactions';
import { useSystemStore } from './stores/system';
import { useProfilesStore } from './stores/profiles';
import { PROFILE_STORAGE_KEY } from './api/client';
import type { AccountCreatePayload } from './types';

const themeStore = useThemeStore();
const stealthStore = useStealthStore();
const accountsStore = useAccountsStore();
const investmentsStore = useInvestmentsStore();
const txStore = useTransactionsStore();
const systemStore = useSystemStore();
const profilesStore = useProfilesStore();

const isManageModalOpen = ref(false);
const isAddAccountModalOpen = ref(false);
const isImportModalOpen = ref(false);
const isSettingsOpen = ref(false);
const isProfilesModalOpen = ref(false);
const appName = ref(localStorage.getItem('appName') || 'Finance Hub');
const showDateTime = ref(localStorage.getItem('showDateTime') !== 'false');

function updateShowDateTime(val: boolean) {
  showDateTime.value = val;
  localStorage.setItem('showDateTime', val ? 'true' : 'false');
}

function saveAppName(name: string) {
  if (!name) return;
  appName.value = name;
  localStorage.setItem('appName', name);
}

function handleOpenManageFromSettings() {
  isSettingsOpen.value = false;
  isManageModalOpen.value = true;
}

function handleOpenProfilesFromSettings() {
  isSettingsOpen.value = false;
  isProfilesModalOpen.value = true;
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    isManageModalOpen.value = false;
    isAddAccountModalOpen.value = false;
    isImportModalOpen.value = false;
    isSettingsOpen.value = false;
    isProfilesModalOpen.value = false;
    profilesStore.closeManageModal();
    txStore.closeRecordModal();
    return;
  }
  // Ignore keystrokes when typing inside input or textarea
  const target = e.target as HTMLElement;
  if (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable || e.metaKey || e.ctrlKey || e.altKey) return;

  if (e.key === 's' || e.key === 'S') {
    stealthStore.toggleStealth();
  } else if (e.key === 't' || e.key === 'T') {
    themeStore.toggleTheme();
  } else if (e.key === 'n' || e.key === 'N') {
    e.preventDefault();
    isManageModalOpen.value = true;
  } else if (e.key === 'e' || e.key === 'E') {
    e.preventDefault();
    txStore.openRecordModal();
  } else if (e.key === 'i' || e.key === 'I') {
    e.preventDefault();
    isImportModalOpen.value = true;
  }
}

async function handleAccountCreated(payload: AccountCreatePayload) {
  try {
    await accountsStore.createAccount(payload);
    await investmentsStore.loadAllData();
    isAddAccountModalOpen.value = false;
  } catch (err) {
    // Error handled in store
  }
}

function handleStorageChange(e: StorageEvent) {
  if (e.key === PROFILE_STORAGE_KEY && e.newValue) {
    profilesStore.syncFromStorage(e.newValue);
  }
}

onMounted(() => {
  window.addEventListener('storage', handleStorageChange);
  profilesStore.loadProfiles();
  themeStore.initTheme();
  stealthStore.initStealth();
  systemStore.loadConfig();
  window.addEventListener('keydown', handleKeydown);
});

onUnmounted(() => {
  window.removeEventListener('storage', handleStorageChange);
  window.removeEventListener('keydown', handleKeydown);
});
</script>

