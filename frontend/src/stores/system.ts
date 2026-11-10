import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { 
  SystemSettings, 
  SystemSettingsUpdatePayload, 
  BackupArchiveInfo,
  SystemConfig 
} from '../types';
import { api } from '../api/client';

export const useSystemStore = defineStore('system', () => {
  const settings = ref<SystemSettings | null>(null);
  const config = ref<SystemConfig | null>(null);
  const archives = ref<BackupArchiveInfo[]>([]);
  const loading = ref(false);
  const creatingBackup = ref(false);
  const error = ref<string | null>(null);
  const successMessage = ref<string | null>(null);
  const initialized = ref(false);

  async function loadConfig() {
    try {
      config.value = await api.getSystemConfig();
    } catch (err: any) {
      console.error('Failed to load system config', err);
    }
  }

  async function loadBackupStatus() {
    try {
      settings.value = await api.getBackupStatus();
    } catch (err: any) {
      console.error('Failed to load backup status', err);
    }
  }

  async function loadArchives() {
    loading.value = true;
    error.value = null;
    try {
      archives.value = await api.getBackupArchives();
    } catch (err: any) {
      error.value = err.message || 'Failed to load backup archives.';
    } finally {
      loading.value = false;
    }
  }

  async function updateSettings(payload: SystemSettingsUpdatePayload) {
    loading.value = true;
    error.value = null;
    try {
      settings.value = await api.updateSystemSettings(payload);
      return settings.value;
    } catch (err: any) {
      error.value = err.message || 'Failed to update backup settings.';
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function createBackup() {
    creatingBackup.value = true;
    error.value = null;
    successMessage.value = null;
    try {
      const res = await api.createBackup();
      successMessage.value = `Backup created successfully (${res.filename})`;
      await Promise.all([
        loadBackupStatus(),
        loadArchives(),
      ]);
      return res;
    } catch (err: any) {
      error.value = err.message || 'Failed to generate backup.';
      throw err;
    } finally {
      creatingBackup.value = false;
    }
  }

  async function initSystem() {
    if (initialized.value) return;
    initialized.value = true;
    await Promise.all([
      loadConfig(),
      loadBackupStatus()
    ]);
  }

  return {
    settings,
    config,
    archives,
    loading,
    creatingBackup,
    error,
    successMessage,
    initSystem,
    loadConfig,
    loadBackupStatus,
    loadArchives,
    updateSettings,
    createBackup,
  };
});

