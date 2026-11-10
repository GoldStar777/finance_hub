import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { ProfileMetadata, ProfileImpactResponse } from '../types';
import { api, setActiveProfileId, getActiveProfileId } from '../api/client';
import { useAccountsStore } from './accounts';
import { useTransactionsStore } from './transactions';
import { useStagingStore } from './staging';
import { useInvestmentsStore } from './investments';
import { useSystemStore } from './system';
import { useAnalysisStore } from './analysis';
import { useSharedFiltersStore } from './filters';
import { useReviewStore } from './review';

export const useProfilesStore = defineStore('profiles', () => {
  const profiles = ref<ProfileMetadata[]>([]);
  const activeProfile = ref<ProfileMetadata | null>(null);
  const loading = ref(false);
  const isSwitching = ref(false);
  const error = ref<string | null>(null);
  const isManageModalOpen = ref(false);
  const switchEpoch = ref(0);

  function openManageModal() {
    isManageModalOpen.value = true;
  }

  function closeManageModal() {
    isManageModalOpen.value = false;
  }

  async function reloadProfileStores() {
    const accountsStore = useAccountsStore();
    const txStore = useTransactionsStore();
    const stagingStore = useStagingStore();
    const investmentsStore = useInvestmentsStore();
    const systemStore = useSystemStore();
    const analysisStore = useAnalysisStore();
    const sharedFilters = useSharedFiltersStore();
    const reviewStore = useReviewStore();

    // Switch shared filter storage first so dependent stores read the target workspace's filters on reset
    sharedFilters.switchProfile(getActiveProfileId() || 'default');

    // Reset store states immediately to clear previous profile's data from memory
    accountsStore.reset?.();
    txStore.reset?.();
    stagingStore.reset?.();
    investmentsStore.reset?.();
    analysisStore.reset?.();
    reviewStore.reset?.();

    await Promise.allSettled([
      accountsStore.loadData(),
      txStore.loadTransactions(),
      txStore.loadRecent(),
      txStore.loadCategories(),
      stagingStore.fetchCount(),
      stagingStore.fetchItems(),
      stagingStore.fetchSuggestions(),
      stagingStore.fetchProfiles(),
      investmentsStore.loadAllData(),
      systemStore.loadConfig(),
      systemStore.loadBackupStatus(),
      systemStore.loadArchives(),
      analysisStore.loadAnalysis(),
      reviewStore.loadFindings()
    ]);
  }

  async function loadProfiles(includeArchived = true) {
    loading.value = true;
    error.value = null;
    try {
      const data = await api.listProfiles(includeArchived);
      profiles.value = data;

      const savedId = getActiveProfileId();
      let targetProfile: ProfileMetadata | null = null;

      if (savedId) {
        targetProfile = data.find(p => p.id === savedId && !p.is_archived) || null;
      }

      const wasInvalid = Boolean(savedId && !targetProfile);

      if (!targetProfile) {
        // Safe fallback: registry active, default profile, or first non-archived profile
        targetProfile = data.find(p => p.is_active && !p.is_archived)
          || data.find(p => p.is_default && !p.is_archived)
          || data.find(p => !p.is_archived)
          || data[0]
          || null;
      }

      if (targetProfile) {
        activeProfile.value = targetProfile;
        setActiveProfileId(targetProfile.id);

        profiles.value = profiles.value.map(p => ({
          ...p,
          is_active: p.id === targetProfile.id
        }));

        // If the saved profile was invalid, child components may have fired with an invalid/empty ID;
        // reload all profile-scoped stores with the validated fallback profile.
        if (wasInvalid) {
          await reloadProfileStores();
        }
      }
      return data;
    } catch (err: any) {
      error.value = err.message || 'Failed to load profiles.';
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function switchProfile(profileId: string) {
    if (activeProfile.value?.id === profileId && !isSwitching.value) {
      return activeProfile.value;
    }

    switchEpoch.value++;
    const currentEpoch = switchEpoch.value;
    isSwitching.value = true;
    error.value = null;

    try {
      // 1. Tell backend to switch active profile
      const selected = await api.selectProfile(profileId);
      
      // If another switch was initiated in flight, abandon this outdated switch
      if (switchEpoch.value !== currentEpoch) {
        return selected;
      }

      // 2. Synchronously persist to localStorage and store state
      setActiveProfileId(selected.id);
      activeProfile.value = selected;

      // Update local profiles list status
      profiles.value = profiles.value.map(p => ({
        ...p,
        is_active: p.id === selected.id
      }));

      // 3. Reset and reload all profile-scoped stores in parallel
      await reloadProfileStores();

      return selected;
    } catch (err: any) {
      if (switchEpoch.value === currentEpoch) {
        error.value = err.message || 'Failed to switch profile.';
      }
      throw err;
    } finally {
      if (switchEpoch.value === currentEpoch) {
        isSwitching.value = false;
      }
    }
  }

  async function syncFromStorage(newProfileId: string | null) {
    if (!newProfileId || activeProfile.value?.id === newProfileId) {
      return;
    }

    switchEpoch.value++;
    const currentEpoch = switchEpoch.value;
    setActiveProfileId(newProfileId);

    let target = profiles.value.find(p => p.id === newProfileId && !p.is_archived);
    if (!target) {
      try {
        const data = await api.listProfiles(true);
        profiles.value = data;
        target = data.find(p => p.id === newProfileId && !p.is_archived);
      } catch {
        // ignore
      }
    }

    if (switchEpoch.value !== currentEpoch) {
      return;
    }

    if (target) {
      activeProfile.value = target;
      profiles.value = profiles.value.map(p => ({
        ...p,
        is_active: p.id === target.id
      }));
      await reloadProfileStores();
    } else {
      await loadProfiles();
    }
  }

  async function createProfile(name: string, autoSwitch = true) {
    loading.value = true;
    error.value = null;
    try {
      const created = await api.createProfile({ name });
      await loadProfiles(true);
      if (autoSwitch) {
        await switchProfile(created.id);
      }
      return created;
    } catch (err: any) {
      error.value = err.message || 'Failed to create profile.';
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function renameProfile(profileId: string, newName: string) {
    loading.value = true;
    error.value = null;
    try {
      const updated = await api.updateProfile(profileId, { name: newName });
      await loadProfiles(true);
      if (activeProfile.value?.id === profileId) {
        activeProfile.value = updated;
      }
      return updated;
    } catch (err: any) {
      error.value = err.message || 'Failed to rename profile.';
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function toggleArchiveProfile(profileId: string, archiveState: boolean) {
    loading.value = true;
    error.value = null;
    try {
      const updated = await api.updateProfile(profileId, { is_archived: archiveState });
      await loadProfiles(true);
      return updated;
    } catch (err: any) {
      error.value = err.message || 'Failed to update profile archive status.';
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function getProfileImpact(profileId: string): Promise<ProfileImpactResponse> {
    try {
      return await api.getProfileImpact(profileId);
    } catch (err: any) {
      error.value = err.message || 'Failed to fetch profile impact summary.';
      throw err;
    }
  }

  async function deleteProfile(profileId: string, confirmName: string) {
    loading.value = true;
    error.value = null;
    try {
      await api.deleteProfile(profileId, { confirm_name: confirmName });
      await loadProfiles(true);
    } catch (err: any) {
      error.value = err.message || 'Failed to delete profile.';
      throw err;
    } finally {
      loading.value = false;
    }
  }

  return {
    profiles,
    activeProfile,
    loading,
    isSwitching,
    error,
    isManageModalOpen,
    openManageModal,
    closeManageModal,
    loadProfiles,
    switchProfile,
    createProfile,
    renameProfile,
    toggleArchiveProfile,
    getProfileImpact,
    deleteProfile,
    reloadProfileStores,
    syncFromStorage,
  };
});
