<template>
  <div 
    v-if="isOpen" 
    class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/60 backdrop-blur-sm animate-fadeIn"
    role="dialog"
    aria-modal="true"
    aria-labelledby="manage-profiles-title"
    @keydown.esc="handleClose">

    <!-- Modal Dialog Card -->
    <div 
      class="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-2xl w-full max-w-2xl overflow-hidden flex flex-col max-h-[90vh]">
      
      <!-- Header -->
      <div class="px-6 py-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between shrink-0 bg-slate-50/50 dark:bg-slate-900/50">
        <div class="flex items-center space-x-2.5">
          <div class="w-8 h-8 rounded-xl bg-indigo-100 dark:bg-indigo-950/80 text-indigo-600 dark:text-indigo-400 flex items-center justify-center text-sm font-bold">
            📁
          </div>
          <div>
            <h2 id="manage-profiles-title" class="font-bold text-slate-900 dark:text-white text-base">
              Financial Workspaces
            </h2>
            <p class="text-xs text-slate-500 dark:text-slate-400">
              Isolate ledgers, accounts, receipts, and settings across distinct profiles.
            </p>
          </div>
        </div>
        <button 
          type="button"
          @click="handleClose"
          class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition"
          aria-label="Close dialog">
          <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <!-- Content Area -->
      <div class="p-6 overflow-y-auto space-y-6">

        <!-- Error Alert -->
        <div 
          v-if="errorMessage" 
          class="p-3 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900/50 text-rose-700 dark:text-rose-300 text-xs flex items-center justify-between">
          <span>{{ errorMessage }}</span>
          <button @click="errorMessage = null" class="font-bold text-rose-500 hover:text-rose-700">✕</button>
        </div>

        <!-- Success Toast -->
        <div 
          v-if="successMessage" 
          class="p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-900/50 text-emerald-700 dark:text-emerald-300 text-xs flex items-center justify-between">
          <span>{{ successMessage }}</span>
          <button @click="successMessage = null" class="font-bold text-emerald-500 hover:text-emerald-700">✕</button>
        </div>

        <!-- Create Profile Section -->
        <div class="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-800/40">
          <div class="flex items-center justify-between mb-2">
            <label for="new-profile-name" class="text-xs font-bold text-slate-800 dark:text-slate-200">
              Create New Workspace
            </label>
            <span class="text-[11px] text-slate-500 dark:text-slate-400">
              Fresh SQLite database with zero records
            </span>
          </div>
          <form @submit.prevent="handleCreateProfile" class="flex items-center gap-2">
            <input 
              id="new-profile-name"
              v-model="newProfileName" 
              type="text" 
              placeholder="e.g. Business Finances, Rental Property, Side Hustle"
              maxlength="100"
              class="flex-1 px-3.5 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 dark:focus:ring-indigo-400/50"
              :disabled="creating" />
            <button 
              type="submit"
              :disabled="!newProfileName.trim() || creating"
              class="px-4 py-2 text-xs font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white disabled:opacity-50 disabled:cursor-not-allowed transition flex items-center space-x-1.5 shrink-0 shadow-sm">
              <span v-if="creating">Creating...</span>
              <span v-else>+ Create Workspace</span>
            </button>
          </form>
        </div>

        <!-- Active Workspaces List -->
        <div>
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Active Workspaces ({{ activeProfilesList.length }})
            </h3>
            <span class="text-[11px] text-slate-400">
              Appearance preferences remain shared across all workspaces
            </span>
          </div>

          <div class="space-y-2.5">
            <div 
              v-for="profile in activeProfilesList" 
              :key="profile.id"
              class="p-3.5 rounded-xl border transition flex items-center justify-between gap-3"
              :class="profile.is_active 
                ? 'border-indigo-400 dark:border-indigo-600 bg-indigo-50/20 dark:bg-indigo-950/20 shadow-sm' 
                : 'border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:border-slate-300 dark:hover:border-slate-700'">
              
              <!-- Left: Name & Metadata -->
              <div class="flex-1 min-w-0">
                <div class="flex items-center space-x-2">
                  <!-- Inline Rename Field or Display -->
                  <div v-if="renamingId === profile.id" class="flex items-center space-x-1.5">
                    <input 
                      v-model="renameValue"
                      type="text"
                      class="px-2 py-1 text-xs font-semibold rounded border border-indigo-400 bg-white dark:bg-slate-800 text-slate-900 dark:text-white focus:outline-none"
                      @keydown.enter.prevent="submitRename(profile.id)"
                      @keydown.esc.prevent="cancelRename"
                      autofocus />
                    <button 
                      type="button" 
                      @click="submitRename(profile.id)" 
                      class="px-2 py-1 text-[11px] font-bold rounded bg-indigo-600 text-white hover:bg-indigo-700">
                      Save
                    </button>
                    <button 
                      type="button" 
                      @click="cancelRename" 
                      class="px-2 py-1 text-[11px] rounded bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-200">
                      Cancel
                    </button>
                  </div>

                  <span v-else class="text-xs font-bold text-slate-900 dark:text-white truncate">
                    {{ profile.name }}
                  </span>

                  <!-- Status Badges -->
                  <span 
                    v-if="profile.is_active" 
                    class="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-emerald-100 dark:bg-emerald-950/80 text-emerald-800 dark:text-emerald-300">
                    Active
                  </span>
                  <span 
                    v-if="profile.is_default" 
                    class="px-2 py-0.5 rounded-full text-[10px] font-mono text-slate-600 dark:text-slate-400 bg-slate-100 dark:bg-slate-800">
                    Default
                  </span>
                </div>

                <div class="flex items-center space-x-3 text-[11px] text-slate-400 mt-1">
                  <span>Created: {{ formatDate(profile.created_at) }}</span>
                  <span class="text-slate-300 dark:text-slate-700">•</span>
                  <span class="font-mono text-[10px] text-slate-400 truncate max-w-32" :title="profile.id">
                    ID: {{ profile.id === 'default' ? 'default' : profile.id.slice(0, 8) + '...' }}
                  </span>
                </div>
              </div>

              <!-- Right: Actions -->
              <div class="flex items-center space-x-1.5 shrink-0">
                <!-- Switch Button -->
                <button
                  v-if="!profile.is_active"
                  type="button"
                  @click="handleSwitch(profile.id)"
                  :disabled="profilesStore.isSwitching"
                  class="px-3 py-1.5 text-xs font-semibold rounded-lg bg-slate-900 hover:bg-slate-800 text-white dark:bg-white dark:hover:bg-slate-100 dark:text-slate-900 transition shadow-sm">
                  Switch
                </button>

                <!-- Rename Action -->
                <button
                  v-if="renamingId !== profile.id"
                  type="button"
                  @click="startRename(profile)"
                  class="p-1.5 rounded-lg text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
                  title="Rename workspace">
                  ✏️
                </button>

                <!-- Archive Action -->
                <button
                  v-if="!profile.is_active"
                  type="button"
                  @click="handleArchive(profile.id, true)"
                  class="p-1.5 rounded-lg text-slate-500 hover:text-amber-600 hover:bg-amber-50 dark:hover:bg-amber-950/30 transition"
                  title="Archive workspace (hide from switcher)">
                  📦
                </button>
                <span 
                  v-else 
                  class="p-1.5 text-slate-300 dark:text-slate-700 cursor-not-allowed" 
                  title="Cannot archive the active workspace">
                  📦
                </span>

                <!-- Delete Action -->
                <button
                  type="button"
                  @click="openDeleteDialog(profile)"
                  :disabled="profile.is_active || profilesStore.profiles.length <= 1"
                  :class="(profile.is_active || profilesStore.profiles.length <= 1)
                    ? 'opacity-30 cursor-not-allowed text-slate-400 p-1.5'
                    : 'text-rose-500 hover:text-rose-700 hover:bg-rose-50 dark:hover:bg-rose-950/30 p-1.5 rounded-lg transition'"
                  :title="getDeleteTooltip(profile)">
                  🗑️
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Archived Workspaces Section (Collapsible / Present if any archived) -->
        <div v-if="archivedProfilesList.length > 0">
          <div class="flex items-center justify-between mb-3 pt-2 border-t border-slate-200 dark:border-slate-800">
            <h3 class="text-xs font-bold uppercase tracking-wider text-amber-600 dark:text-amber-400">
              Archived Workspaces ({{ archivedProfilesList.length }})
            </h3>
            <span class="text-[11px] text-slate-400">
              Preserved safely on disk, hidden from header switcher
            </span>
          </div>

          <div class="space-y-2">
            <div 
              v-for="profile in archivedProfilesList" 
              :key="profile.id"
              class="p-3.5 rounded-xl border border-dashed border-amber-200 dark:border-amber-900/50 bg-amber-50/20 dark:bg-amber-950/10 flex items-center justify-between gap-3">
              
              <div>
                <div class="flex items-center space-x-2">
                  <span class="text-xs font-bold text-slate-800 dark:text-slate-200">{{ profile.name }}</span>
                  <span class="px-2 py-0.5 rounded-full text-[10px] font-mono bg-amber-100 dark:bg-amber-950/80 text-amber-800 dark:text-amber-300">
                    Archived
                  </span>
                </div>
                <div class="text-[11px] text-slate-400 mt-0.5">
                  Created: {{ formatDate(profile.created_at) }}
                </div>
              </div>

              <div class="flex items-center space-x-2 shrink-0">
                <!-- Unarchive Action -->
                <button
                  type="button"
                  @click="handleArchive(profile.id, false)"
                  class="px-2.5 py-1 text-xs font-medium rounded-lg border border-amber-300 dark:border-amber-700 text-amber-800 dark:text-amber-300 hover:bg-amber-100 dark:hover:bg-amber-900/40 transition">
                  Unarchive
                </button>

                <!-- Delete Action -->
                <button
                  type="button"
                  @click="openDeleteDialog(profile)"
                  :disabled="profilesStore.profiles.length <= 1"
                  class="text-rose-500 hover:text-rose-700 hover:bg-rose-50 dark:hover:bg-rose-950/30 p-1.5 rounded-lg transition"
                  title="Permanently delete workspace">
                  🗑️
                </button>
              </div>
            </div>
          </div>
        </div>

      </div>

      <!-- Footer -->
      <div class="px-6 py-3.5 border-t border-slate-200 dark:border-slate-800 flex items-center justify-between shrink-0 bg-slate-50/50 dark:bg-slate-900/50">
        <div class="text-[11px] text-slate-500 dark:text-slate-400">
          Current workspace: <strong class="text-slate-900 dark:text-white">{{ profilesStore.activeProfile?.name || 'Default' }}</strong>
        </div>
        <button 
          type="button"
          @click="handleClose"
          class="px-4 py-2 text-xs font-semibold rounded-lg border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition">
          Close
        </button>
      </div>

    </div>

    <!-- Permanent Deletion Safeguard Sub-Dialog -->
    <div 
      v-if="deletingProfile"
      class="fixed inset-0 z-60 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm animate-fadeIn"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="delete-profile-dialog-title">
      
      <div class="bg-white dark:bg-slate-900 border border-rose-300 dark:border-rose-900/70 rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden flex flex-col animate-scaleUp">
        
        <!-- Header -->
        <div class="px-6 py-4 border-b border-rose-200 dark:border-rose-900/40 bg-rose-50/70 dark:bg-rose-950/50 flex items-center justify-between">
          <div class="flex items-center space-x-2.5">
            <div class="w-8 h-8 rounded-xl bg-rose-100 dark:bg-rose-900/80 text-rose-600 dark:text-rose-300 flex items-center justify-center text-sm font-bold">
              ⚠️
            </div>
            <div>
              <h3 id="delete-profile-dialog-title" class="font-bold text-rose-900 dark:text-rose-200 text-sm">
                Permanently Delete Workspace
              </h3>
              <p class="text-[11px] text-rose-700 dark:text-rose-300">
                Irreversible destructive operation
              </p>
            </div>
          </div>
          <button 
            type="button"
            @click="closeDeleteDialog"
            class="text-rose-400 hover:text-rose-600 p-1 rounded-lg">
            ✕
          </button>
        </div>

        <!-- Body -->
        <div class="p-6 space-y-4">
          <!-- Impact Summary Details -->
          <div v-if="impactLoading" class="text-center py-4 text-xs text-slate-400">
            Calculating workspace impact metrics...
          </div>
          <div v-else-if="impactData" class="space-y-3">
            <p class="text-xs text-slate-700 dark:text-slate-300 leading-relaxed">
              You are about to permanently delete <strong class="text-slate-900 dark:text-white">{{ deletingProfile.name }}</strong>.
              All isolated data in its database and storage folder will be erased permanently:
            </p>

            <div class="grid grid-cols-2 gap-2 text-xs bg-slate-50 dark:bg-slate-800/60 p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 font-mono">
              <div>Accounts: <strong class="text-slate-900 dark:text-white">{{ impactData.accounts_count }}</strong></div>
              <div>Transactions: <strong class="text-slate-900 dark:text-white">{{ impactData.transactions_count }}</strong></div>
              <div>Holdings: <strong class="text-slate-900 dark:text-white">{{ impactData.holdings_count }}</strong></div>
              <div>Categories: <strong class="text-slate-900 dark:text-white">{{ impactData.categories_count }}</strong></div>
              <div>Pending Queue: <strong class="text-slate-900 dark:text-white">{{ impactData.staging_items_count }}</strong></div>
              <div>Receipt Files: <strong class="text-slate-900 dark:text-white">{{ impactData.receipt_files_count }}</strong></div>
              <div>Backup Files: <strong class="text-slate-900 dark:text-white">{{ impactData.backup_files_count }}</strong></div>
              <div>Disk Space: <strong class="text-rose-600 dark:text-rose-400">{{ impactData.disk_usage_formatted }}</strong></div>
            </div>

            <!-- Blocking Reason (if any) -->
            <div 
              v-if="!impactData.can_delete" 
              class="p-3 rounded-lg bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900/50 text-amber-800 dark:text-amber-300 text-xs">
              {{ impactData.blocking_reason }}
            </div>

            <!-- Confirmation Prompt -->
            <div v-if="impactData.can_delete" class="pt-2">
              <label for="confirm-delete-input" class="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
                To confirm, type <span class="select-all font-bold text-rose-600 dark:text-rose-400 font-mono">{{ deletingProfile.name }}</span> below:
              </label>
              <input 
                id="confirm-delete-input"
                v-model="deleteConfirmText" 
                type="text"
                class="w-full px-3.5 py-2 text-xs rounded-lg border border-rose-300 dark:border-rose-800 bg-white dark:bg-slate-900 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-rose-500/50 font-mono"
                :placeholder="deletingProfile.name"
                autofocus />
            </div>
          </div>
        </div>

        <!-- Footer -->
        <div class="px-6 py-3.5 border-t border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50 flex items-center justify-end space-x-2">
          <button 
            type="button"
            @click="closeDeleteDialog"
            class="px-4 py-2 text-xs font-semibold rounded-lg border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition">
            Cancel
          </button>
          <button 
            type="button"
            @click="confirmPermanentDelete"
            :disabled="!isDeleteConfirmed || deleteExecuting"
            class="px-4 py-2 text-xs font-semibold rounded-lg bg-rose-600 hover:bg-rose-700 text-white disabled:opacity-40 disabled:cursor-not-allowed transition shadow-sm">
            <span v-if="deleteExecuting">Deleting...</span>
            <span v-else>Permanently Delete</span>
          </button>
        </div>

      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import type { ProfileMetadata, ProfileImpactResponse } from '../types';
import { useProfilesStore } from '../stores/profiles';

const props = defineProps<{
  isOpen: boolean;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
}>();

const profilesStore = useProfilesStore();

const newProfileName = ref('');
const creating = ref(false);
const errorMessage = ref<string | null>(null);
const successMessage = ref<string | null>(null);

const renamingId = ref<string | null>(null);
const renameValue = ref('');

const deletingProfile = ref<ProfileMetadata | null>(null);
const impactLoading = ref(false);
const impactData = ref<ProfileImpactResponse | null>(null);
const deleteConfirmText = ref('');
const deleteExecuting = ref(false);

const activeProfilesList = computed(() => {
  return profilesStore.profiles.filter(p => !p.is_archived);
});

const archivedProfilesList = computed(() => {
  return profilesStore.profiles.filter(p => p.is_archived);
});

const isDeleteConfirmed = computed(() => {
  if (!deletingProfile.value || !impactData.value?.can_delete) return false;
  return deleteConfirmText.value.trim() === deletingProfile.value.name.trim();
});

watch(() => props.isOpen, (open) => {
  if (open) {
    errorMessage.value = null;
    successMessage.value = null;
    profilesStore.loadProfiles(true);
  }
});

function handleClose() {
  if (deletingProfile.value) {
    closeDeleteDialog();
    return;
  }
  emit('close');
}

function formatDate(isoStr: string) {
  if (!isoStr) return '';
  try {
    const d = new Date(isoStr);
    return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
  } catch {
    return isoStr;
  }
}

function getDeleteTooltip(profile: ProfileMetadata): string {
  if (profile.is_active) return 'Cannot delete the active workspace. Switch first.';
  if (profilesStore.profiles.length <= 1) return 'Cannot delete the only remaining workspace.';
  return 'Permanently delete workspace';
}

async function handleCreateProfile() {
  const name = newProfileName.value.trim();
  if (!name) return;
  creating.value = true;
  errorMessage.value = null;
  successMessage.value = null;

  try {
    const created = await profilesStore.createProfile(name, false);
    newProfileName.value = '';
    successMessage.value = `Workspace "${created.name}" created successfully.`;
  } catch (err: any) {
    errorMessage.value = err.message || 'Failed to create workspace.';
  } finally {
    creating.value = false;
  }
}

async function handleSwitch(profileId: string) {
  errorMessage.value = null;
  try {
    await profilesStore.switchProfile(profileId);
    successMessage.value = `Switched to workspace "${profilesStore.activeProfile?.name}".`;
  } catch (err: any) {
    errorMessage.value = err.message || 'Failed to switch workspace.';
  }
}

function startRename(profile: ProfileMetadata) {
  renamingId.value = profile.id;
  renameValue.value = profile.name;
}

function cancelRename() {
  renamingId.value = null;
  renameValue.value = '';
}

async function submitRename(profileId: string) {
  const trimmed = renameValue.value.trim();
  if (!trimmed) return;
  errorMessage.value = null;
  try {
    await profilesStore.renameProfile(profileId, trimmed);
    renamingId.value = null;
    successMessage.value = 'Workspace renamed successfully.';
  } catch (err: any) {
    errorMessage.value = err.message || 'Failed to rename workspace.';
  }
}

async function handleArchive(profileId: string, archiveState: boolean) {
  errorMessage.value = null;
  try {
    await profilesStore.toggleArchiveProfile(profileId, archiveState);
    successMessage.value = archiveState ? 'Workspace archived.' : 'Workspace unarchived.';
  } catch (err: any) {
    errorMessage.value = err.message || 'Failed to update archive status.';
  }
}

async function openDeleteDialog(profile: ProfileMetadata) {
  deletingProfile.value = profile;
  deleteConfirmText.value = '';
  impactLoading.value = true;
  impactData.value = null;

  try {
    const impact = await profilesStore.getProfileImpact(profile.id);
    impactData.value = impact;
  } catch (err: any) {
    errorMessage.value = err.message || 'Failed to evaluate impact.';
    closeDeleteDialog();
  } finally {
    impactLoading.value = false;
  }
}

function closeDeleteDialog() {
  deletingProfile.value = null;
  impactData.value = null;
  deleteConfirmText.value = '';
}

async function confirmPermanentDelete() {
  if (!deletingProfile.value || !isDeleteConfirmed.value) return;
  deleteExecuting.value = true;
  errorMessage.value = null;

  const targetName = deletingProfile.value.name;
  const targetId = deletingProfile.value.id;

  try {
    await profilesStore.deleteProfile(targetId, deleteConfirmText.value.trim());
    closeDeleteDialog();
    successMessage.value = `Workspace "${targetName}" deleted permanently.`;
  } catch (err: any) {
    errorMessage.value = err.message || 'Failed to delete workspace.';
  } finally {
    deleteExecuting.value = false;
  }
}
</script>

