<template>
  <div 
    v-if="isOpen" 
    class="fixed inset-0 z-50 bg-slate-950/40 backdrop-blur-sm flex items-center justify-center p-4 animate-fadeIn"
    @click.self="emitClose">
    <section 
      role="dialog" 
      aria-modal="true" 
      aria-labelledby="bulk-delete-modal-title"
      class="bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-5 transition-all max-h-[90vh] flex flex-col">
      
      <!-- Modal Header -->
      <div class="flex items-start justify-between pb-3 border-b border-brand-border dark:border-brand-darkborder shrink-0">
        <div>
          <div class="flex items-center space-x-2">
            <h2 id="bulk-delete-modal-title" class="font-bold text-slate-900 dark:text-white text-base flex items-center space-x-2">
              <span class="text-rose-600 dark:text-rose-400">🗑️</span>
              <span>Confirm Bulk Deletion</span>
            </h2>
            <span class="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300">
              {{ countLabel }}
            </span>
          </div>
          <p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Safely move {{ countLabel }} to Recently Deleted with complete recoverable history.
          </p>
        </div>

        <button 
          @click="emitClose" 
          :disabled="isDeleting"
          class="text-slate-400 hover:text-slate-600 dark:hover:text-white text-lg p-1 disabled:opacity-50"
          aria-label="Close dialog">
          &times;
        </button>
      </div>

      <!-- Modal Body -->
      <div class="space-y-4 overflow-y-auto pr-1">
        
        <!-- Error Message -->
        <div v-if="errorMessage" class="p-3 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 text-rose-600 dark:text-rose-400 text-xs">
          <div class="font-bold mb-0.5">Deletion Error</div>
          <div>{{ errorMessage }}</div>
        </div>

        <!-- Scope Explanation Banner -->
        <div class="p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 text-xs text-slate-700 dark:text-slate-300 space-y-1.5">
          <div class="font-bold text-slate-900 dark:text-white flex items-center justify-between">
            <span>Selection Scope</span>
            <span class="font-mono text-[11px] text-slate-500">
              {{ isAllMatching ? 'Cross-Page Selection' : 'Page Selection' }}
            </span>
          </div>
          <p v-if="isAllMatching">
            You are deleting <strong>all {{ totalCount }}</strong> transactions matching your current filters across all pages.
          </p>
          <p v-else>
            You are deleting <strong>{{ selectedCount }}</strong> individually selected transaction{{ selectedCount === 1 ? '' : 's' }}.
          </p>
        </div>

        <!-- Impact Notices -->
        <div class="space-y-2.5 text-xs">
          <!-- Paired Transfer Warning -->
          <div class="p-3 rounded-xl border border-amber-200 dark:border-amber-900/60 bg-amber-50/70 dark:bg-amber-950/30 text-amber-900 dark:text-amber-200 flex items-start space-x-2.5">
            <span class="text-base shrink-0">⚠️</span>
            <div class="space-y-0.5">
              <div class="font-bold">Paired Transfers</div>
              <div class="text-[11px] leading-relaxed text-amber-800 dark:text-amber-300">
                Any paired transfers in this selection will remove the money movement from <strong>both</strong> source and destination accounts simultaneously. No dangling half-transfers will remain.
              </div>
            </div>
          </div>

          <!-- Receipt Retention Notice -->
          <div class="p-3 rounded-xl border border-blue-200 dark:border-blue-900/60 bg-blue-50/70 dark:bg-blue-950/30 text-blue-900 dark:text-blue-200 flex items-start space-x-2.5">
            <span class="text-base shrink-0">📎</span>
            <div class="space-y-0.5">
              <div class="font-bold">Receipt Attachment Preservation</div>
              <div class="text-[11px] leading-relaxed text-blue-800 dark:text-blue-300">
                Receipt image files and document references will <strong>not</strong> be discarded or deleted from disk. They are safely retained in storage and will remain intact upon recovery.
              </div>
            </div>
          </div>

          <!-- Recoverable Deletion Notice -->
          <div class="p-3 rounded-xl border border-emerald-200 dark:border-emerald-900/60 bg-emerald-50/70 dark:bg-emerald-950/30 text-emerald-900 dark:text-emerald-200 flex items-start space-x-2.5">
            <span class="text-base shrink-0">🛡️</span>
            <div class="space-y-0.5">
              <div class="font-bold">Reversible & Safe</div>
              <div class="text-[11px] leading-relaxed text-emerald-800 dark:text-emerald-300">
                This deletion is fully reversible. You can undo immediately using the floating banner or restore anytime from the <strong>Recently Deleted</strong> tab with 100% of original dates, amounts, accounts, and categories.
              </div>
            </div>
          </div>
        </div>

      </div>

      <!-- Modal Footer -->
      <div class="pt-3 border-t border-brand-border dark:border-brand-darkborder flex items-center justify-end space-x-3 shrink-0">
        <button 
          type="button" 
          @click="emitClose"
          :disabled="isDeleting"
          class="px-4 py-2 text-xs font-semibold rounded-full border border-brand-border dark:border-brand-darkborder hover:bg-slate-100 dark:hover:bg-slate-800 transition text-slate-700 dark:text-slate-300 disabled:opacity-50">
          Cancel
        </button>

        <button 
          type="button" 
          @click="handleConfirm"
          :disabled="isDeleting"
          class="px-5 py-2 text-xs font-semibold rounded-full bg-rose-600 hover:bg-rose-700 text-white transition shadow-sm flex items-center space-x-2 disabled:opacity-50">
          <span v-if="isDeleting" class="animate-spin text-sm">⏳</span>
          <span v-else>🗑️</span>
          <span>Move {{ countLabel }} to Recently Deleted</span>
        </button>
      </div>

    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';

const props = defineProps<{
  isOpen: boolean;
  selectedCount: number;
  isAllMatching: boolean;
  totalCount: number;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'confirm'): void;
}>();

const isDeleting = ref(false);
const errorMessage = ref<string | null>(null);

const countLabel = computed(() => {
  const count = props.isAllMatching ? props.totalCount : props.selectedCount;
  return `${count} transaction${count === 1 ? '' : 's'}`;
});

function emitClose() {
  if (isDeleting.value) return;
  errorMessage.value = null;
  emit('close');
}

async function handleConfirm() {
  isDeleting.value = true;
  errorMessage.value = null;
  try {
    emit('confirm');
  } catch (err: any) {
    errorMessage.value = err.message || 'Failed to delete transactions.';
  } finally {
    isDeleting.value = false;
  }
}
</script>
