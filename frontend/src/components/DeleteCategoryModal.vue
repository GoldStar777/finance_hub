<template>
  <div 
    v-if="isOpen && category" 
    class="fixed inset-0 z-50 bg-slate-950/60 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto animate-fadeIn"
    @click.self="$emit('close')">
    <section 
      role="dialog" 
      aria-modal="true" 
      aria-labelledby="delete-category-title"
      class="bg-white dark:bg-brand-darksurface border border-rose-200 dark:border-rose-900/60 rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-5 transition-all my-8">
      
      <!-- Modal Header -->
      <div class="flex items-center justify-between pb-3 border-b border-brand-border dark:border-brand-darkborder">
        <div class="flex items-center space-x-2">
          <div class="w-8 h-8 rounded-full bg-rose-100 dark:bg-rose-950/80 text-rose-600 dark:text-rose-400 flex items-center justify-center font-bold text-base">
            ⚠️
          </div>
          <div>
            <h2 id="delete-category-title" class="font-bold text-slate-900 dark:text-white text-base">
              Permanently Delete Category
            </h2>
            <p class="text-xs text-rose-600 dark:text-rose-400 font-semibold">
              Step {{ step }} of 2: {{ step === 1 ? 'Review Transaction Impact' : 'Confirm Permanent Deletion' }}
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

      <!-- STEP 1: Impact Summary & Reassignment -->
      <div v-if="step === 1" class="space-y-4">
        <div class="p-3.5 rounded-xl bg-rose-50/80 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-900/50 text-xs text-rose-900 dark:text-rose-200 space-y-2">
          <p class="font-bold">
            Permanent category deletion removes this classification from your system.
          </p>
          <p class="text-[11px] leading-relaxed">
            Deleting <span class="font-mono font-bold">{{ category.name }}</span> cannot be undone. To prevent historical records from becoming silently orphaned, any assigned transactions must be explicitly handled.
          </p>
        </div>

        <!-- Usage Impact -->
        <div class="p-4 rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50 dark:bg-slate-800/40 space-y-3">
          <span class="text-[11px] font-mono uppercase tracking-wider font-bold text-slate-500 block">
            Transaction Usage Status
          </span>

          <div v-if="loadingImpact" class="py-4 text-center text-xs text-slate-400 animate-pulse">
            Checking transactions linked to category...
          </div>

          <div v-else-if="impact" class="space-y-3">
            <div class="flex items-center justify-between p-3 rounded-lg bg-white dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder">
              <div class="flex items-center space-x-2">
                <span class="w-3.5 h-3.5 rounded-full" :style="{ backgroundColor: category.color || '#8B5CF6' }"></span>
                <span class="text-xs font-bold text-slate-900 dark:text-white">{{ category.name }}</span>
              </div>
              <span class="text-xs font-mono font-bold px-2.5 py-0.5 rounded-full"
                :class="impact.transaction_count > 0 ? 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300' : 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300'">
                {{ impact.transaction_count }} transaction{{ impact.transaction_count === 1 ? '' : 's' }}
              </span>
            </div>

            <!-- If transactions exist, mandate reassignment -->
            <div v-if="impact.transaction_count > 0" class="p-3.5 rounded-xl border border-amber-200 dark:border-amber-900/60 bg-amber-50/60 dark:bg-amber-950/20 space-y-2.5">
              <div class="flex items-start space-x-2">
                <span class="text-amber-600 text-sm">🔒</span>
                <div>
                  <span class="text-xs font-bold text-amber-900 dark:text-amber-200 block">
                    Reassignment Required for {{ impact.transaction_count }} Transaction{{ impact.transaction_count === 1 ? '' : 's' }}
                  </span>
                  <p class="text-[11px] text-amber-800 dark:text-amber-300 mt-0.5">
                    Finance Hub never silently orphans transactions. Select an active destination category to receive these records prior to permanent deletion:
                  </p>
                </div>
              </div>

              <div>
                <label class="block text-[10px] font-mono uppercase font-semibold text-slate-500 mb-1">
                  Reassign to Active Category
                </label>
                <select
                  v-model="reassignToCategoryId"
                  class="w-full bg-white dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none">
                  <option :value="null">-- Select Destination Category --</option>
                  <option 
                    v-for="cat in availableTargetCategories" 
                    :key="cat.id" 
                    :value="cat.id">
                    {{ cat.name }} ({{ cat.category_type === 'income' ? 'Income' : cat.default_expense_nature }})
                  </option>
                </select>
                <p v-if="availableTargetCategories.length === 0" class="text-[11px] text-rose-700 dark:text-rose-300 mt-1.5 font-medium">
                  No other active {{ (category.category_type || 'expense') }} category is available to receive these transactions. Create another one or archive this category instead.
                </p>
              </div>
            </div>

            <div v-else class="text-xs text-slate-500 dark:text-slate-400">
              ✓ No historical transactions currently reference this category. It can be safely deleted.
            </div>
          </div>
        </div>

        <!-- Pre-Deletion Safety Backup Offer -->
        <div class="p-3.5 rounded-xl border border-brand-border dark:border-brand-darkborder bg-indigo-50/50 dark:bg-indigo-950/20 space-y-2">
          <div class="flex items-center justify-between">
            <div>
              <span class="text-xs font-bold text-slate-900 dark:text-white block">Pre-Deletion Safety Backup</span>
              <span class="text-[11px] text-slate-500 dark:text-slate-400">
                Generate an immediate verified backup before deleting.
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
            Recommended Safe Alternative: Archive Category
          </span>
          <p class="text-[11px] text-amber-800 dark:text-amber-400">
            Archiving hides this category from future transaction dropdowns without modifying existing transactions or requiring reassignment.
          </p>
          <button
            type="button"
            @click="handleArchiveInstead"
            :disabled="isArchiving"
            class="mt-1 px-4 py-1.5 rounded-full text-xs font-semibold border border-amber-300 dark:border-amber-800 text-amber-800 dark:text-amber-300 hover:bg-amber-100 dark:hover:bg-amber-900/40 transition">
            {{ isArchiving ? 'Archiving...' : 'Archive This Category Instead' }}
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
            :disabled="loadingImpact || Boolean(impact && impact.transaction_count > 0 && !reassignToCategoryId)"
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
            You are permanently deleting category <span class="font-bold underline">{{ category.name }}</span>.
            <template v-if="impact && impact.transaction_count > 0">
              All {{ impact.transaction_count }} transaction(s) will be reassigned to <span class="font-bold">{{ targetCategoryName }}</span>.
            </template>
            This action cannot be undone.
          </p>
        </div>

        <div class="space-y-1.5">
          <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300">
            Type <span class="font-mono font-bold text-slate-900 dark:text-white px-1 py-0.5 rounded bg-slate-100 dark:bg-slate-800">{{ category.name }}</span> to confirm:
          </label>
          <input
            v-model="typedName"
            type="text"
            :placeholder="category.name"
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
            {{ isDeleting ? 'Permanently Deleting...' : 'Permanently Delete Category' }}
          </button>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import type { Category, CategoryDeletionImpact } from '../types';
import { api } from '../api/client';
import { useSystemStore } from '../stores/system';

const props = defineProps<{
  isOpen: boolean;
  category: Category | null;
  allCategories: Category[];
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'deleted'): void;
  (e: 'archived'): void;
}>();

const systemStore = useSystemStore();

const step = ref<1 | 2>(1);
const impact = ref<CategoryDeletionImpact | null>(null);
const loadingImpact = ref(false);
const reassignToCategoryId = ref<number | null>(null);
const typedName = ref('');
const isDeleting = ref(false);
const isArchiving = ref(false);
const isBackingUp = ref(false);
const backupCreatedMsg = ref<string | null>(null);
const errorMessage = ref<string | null>(null);

const availableTargetCategories = computed(() => {
  if (!props.category) return [];
  const sourcePurpose = props.category.category_type || 'expense';
  return props.allCategories.filter(
    c => c.id !== props.category!.id && c.is_active && (c.category_type || 'expense') === sourcePurpose
  );
});

const targetCategoryName = computed(() => {
  if (!reassignToCategoryId.value) return '';
  const match = props.allCategories.find(c => c.id === reassignToCategoryId.value);
  return match ? match.name : '';
});

const isNameMatched = computed(() => {
  if (!props.category) return false;
  return typedName.value.trim() === props.category.name.trim();
});

watch(() => props.isOpen, (open) => {
  if (open && props.category) {
    step.value = 1;
    typedName.value = '';
    reassignToCategoryId.value = null;
    errorMessage.value = null;
    backupCreatedMsg.value = null;
    loadImpact(props.category.id);
  }
});

async function loadImpact(categoryId: number) {
  loadingImpact.value = true;
  impact.value = null;
  try {
    impact.value = await api.getCategoryDeletionImpact(categoryId);
  } catch (err: any) {
    errorMessage.value = err.message || 'Failed to calculate category deletion impact.';
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
  if (!props.category) return;
  isArchiving.value = true;
  errorMessage.value = null;
  try {
    await api.deleteCategory(props.category.id, false);
    emit('archived');
    emit('close');
  } catch (err: any) {
    errorMessage.value = err.message || 'Failed to archive category.';
  } finally {
    isArchiving.value = false;
  }
}

async function handlePermanentDelete() {
  if (!props.category || !isNameMatched.value) return;
  isDeleting.value = true;
  errorMessage.value = null;
  try {
    await api.deleteCategory(
      props.category.id, 
      true, 
      reassignToCategoryId.value || undefined
    );
    emit('deleted');
    emit('close');
  } catch (err: any) {
    errorMessage.value = err.message || 'Failed to permanently delete category.';
  } finally {
    isDeleting.value = false;
  }
}
</script>
