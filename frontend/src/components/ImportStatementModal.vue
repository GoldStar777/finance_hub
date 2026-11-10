<template>
  <div v-if="isOpen" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fadeIn">
    <div class="bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder rounded-2xl w-full max-w-2xl max-h-[90vh] shadow-2xl flex flex-col overflow-hidden">
      
      <!-- Modal Header -->
      <div class="px-6 py-4 border-b border-brand-border dark:border-brand-darkborder flex items-center justify-between">
        <div>
          <h2 class="text-sm font-bold uppercase tracking-wider text-slate-900 dark:text-white flex items-center space-x-2">
            <span>Import Statement (CSV / TSV)</span>
          </h2>
          <p class="text-[11px] text-slate-500 dark:text-slate-400">
            Provider-agnostic statement intake with configurable column mappings.
          </p>
        </div>
        <button 
          @click="close"
          class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition text-lg leading-none p-1">
          &times;
        </button>
      </div>

      <!-- Modal Body -->
      <div class="p-6 overflow-y-auto space-y-5 flex-1">
        
        <!-- Error Banner -->
        <div v-if="errorMessage" class="p-3 rounded-xl border border-rose-200 dark:border-rose-900 bg-rose-50 dark:bg-rose-950/40 text-rose-600 dark:text-rose-400 text-xs flex items-center justify-between">
          <span>{{ errorMessage }}</span>
          <button @click="errorMessage = null" class="text-rose-600 font-bold">&times;</button>
        </div>

        <!-- Step 1: File & Account Selection -->
        <div class="space-y-4">
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
                Target Account (Optional)
              </label>
              <select
                v-model="targetAccountId"
                class="w-full bg-slate-50 dark:bg-slate-800/60 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none">
                <option :value="null">Unassigned (choose account later)</option>
                <option v-for="acc in accountsStore.accounts" :key="acc.id" :value="acc.id">
                  {{ acc.name }} ({{ acc.currency }})
                </option>
              </select>
            </div>

            <div>
              <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
                Mapping Profile
              </label>
              <select
                v-model="selectedProfileId"
                @change="applySelectedProfile"
                class="w-full bg-slate-50 dark:bg-slate-800/60 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none">
                <option value="">Custom Mapping (Configure Below)</option>
                <option v-for="prof in stagingStore.profiles" :key="prof.id" :value="prof.id">
                  {{ prof.name }}
                </option>
              </select>
            </div>
          </div>

          <!-- File Dropzone -->
          <div>
            <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
              Select Statement File (.csv, .tsv) *
            </label>
            <div 
              @dragover.prevent="isDragging = true"
              @dragleave.prevent="isDragging = false"
              @drop.prevent="handleFileDrop"
              class="border-2 border-dashed rounded-xl p-5 text-center cursor-pointer transition"
              :class="isDragging ? 'border-emerald-500 bg-emerald-50/10' : 'border-brand-border dark:border-brand-darkborder hover:border-slate-400'"
              @click="triggerFileInput">
              <input 
                ref="fileInput" 
                type="file" 
                accept=".csv,.tsv,.txt" 
                class="hidden" 
                @change="handleFileSelect" />
              
              <div v-if="selectedFile" class="text-xs space-y-1">
                <p class="font-bold text-slate-900 dark:text-white">{{ selectedFile.name }}</p>
                <p class="text-[10px] text-slate-500">{{ (selectedFile.size / 1024).toFixed(1) }} KB &bull; Click or drop another file to change</p>
              </div>
              <div v-else class="text-xs space-y-1 text-slate-500">
                <p class="font-medium text-slate-700 dark:text-slate-300">Click to choose or drag & drop statement file here</p>
                <p class="text-[10px] text-slate-400">Supports standard exports from checking, savings, card, and wallet providers</p>
              </div>
            </div>
          </div>
        </div>

        <!-- Step 2: Column Mapping Configuration -->
        <div v-if="fileHeaders.length > 0" class="pt-4 border-t border-brand-border dark:border-brand-darkborder space-y-4">
          <div class="flex items-center justify-between">
            <h3 class="text-xs font-bold uppercase tracking-wider text-slate-900 dark:text-white">
              Column & Format Mapping
            </h3>
            <span class="text-[10px] text-slate-400">Detected {{ fileHeaders.length }} columns</span>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
            <!-- Date Column -->
            <div>
              <label class="block text-[10px] font-mono uppercase font-semibold text-slate-500 mb-1">
                Date Column *
              </label>
              <select
                v-model="mapping.date_column"
                class="w-full bg-slate-50 dark:bg-slate-800/60 border border-brand-border dark:border-brand-darkborder rounded-lg px-2.5 py-1.5 text-xs text-slate-900 dark:text-white">
                <option v-for="h in fileHeaders" :key="h" :value="h">{{ h }}</option>
              </select>
            </div>

            <!-- Date Format -->
            <div>
              <label class="block text-[10px] font-mono uppercase font-semibold text-slate-500 mb-1">
                Date Format
              </label>
              <select
                v-model="mapping.date_format"
                class="w-full bg-slate-50 dark:bg-slate-800/60 border border-brand-border dark:border-brand-darkborder rounded-lg px-2.5 py-1.5 text-xs text-slate-900 dark:text-white">
                <option value="auto">Auto-detect (Flexible)</option>
                <option value="DD/MM/YYYY">DD/MM/YYYY (UK / EU)</option>
                <option value="YYYY-MM-DD">YYYY-MM-DD (ISO)</option>
                <option value="MM/DD/YYYY">MM/DD/YYYY (US)</option>
                <option value="DD-Mon-YYYY">DD-Mon-YYYY (e.g. 21-Oct-2026)</option>
                <option value="DD.MM.YYYY">DD.MM.YYYY (e.g. 21.10.2026)</option>
              </select>
            </div>

            <!-- Merchant / Narrative -->
            <div>
              <label class="block text-[10px] font-mono uppercase font-semibold text-slate-500 mb-1">
                Merchant / Description *
              </label>
              <select
                v-model="mapping.merchant_column"
                class="w-full bg-slate-50 dark:bg-slate-800/60 border border-brand-border dark:border-brand-darkborder rounded-lg px-2.5 py-1.5 text-xs text-slate-900 dark:text-white">
                <option v-for="h in fileHeaders" :key="h" :value="h">{{ h }}</option>
              </select>
            </div>

            <!-- Amount Mode -->
            <div>
              <label class="block text-[10px] font-mono uppercase font-semibold text-slate-500 mb-1">
                Amount Mode *
              </label>
              <select
                v-model="mapping.amount_mode"
                class="w-full bg-slate-50 dark:bg-slate-800/60 border border-brand-border dark:border-brand-darkborder rounded-lg px-2.5 py-1.5 text-xs text-slate-900 dark:text-white">
                <option value="single_standard">Single column (Negative = Expense)</option>
                <option value="single_inverted">Single column (Positive = Expense [Cards])</option>
                <option value="dual_debit_credit">Dual columns (Debit & Credit)</option>
              </select>
            </div>

            <!-- Amount Column (Single mode) -->
            <div v-if="mapping.amount_mode !== 'dual_debit_credit'">
              <label class="block text-[10px] font-mono uppercase font-semibold text-slate-500 mb-1">
                Amount Column *
              </label>
              <select
                v-model="mapping.amount_column"
                class="w-full bg-slate-50 dark:bg-slate-800/60 border border-brand-border dark:border-brand-darkborder rounded-lg px-2.5 py-1.5 text-xs text-slate-900 dark:text-white">
                <option v-for="h in fileHeaders" :key="h" :value="h">{{ h }}</option>
              </select>
            </div>

            <!-- Debit Column (Dual mode) -->
            <div v-if="mapping.amount_mode === 'dual_debit_credit'">
              <label class="block text-[10px] font-mono uppercase font-semibold text-slate-500 mb-1">
                Debit (Money Out) Column *
              </label>
              <select
                v-model="mapping.debit_column"
                class="w-full bg-slate-50 dark:bg-slate-800/60 border border-brand-border dark:border-brand-darkborder rounded-lg px-2.5 py-1.5 text-xs text-slate-900 dark:text-white">
                <option v-for="h in fileHeaders" :key="h" :value="h">{{ h }}</option>
              </select>
            </div>

            <!-- Credit Column (Dual mode) -->
            <div v-if="mapping.amount_mode === 'dual_debit_credit'">
              <label class="block text-[10px] font-mono uppercase font-semibold text-slate-500 mb-1">
                Credit (Money In) Column *
              </label>
              <select
                v-model="mapping.credit_column"
                class="w-full bg-slate-50 dark:bg-slate-800/60 border border-brand-border dark:border-brand-darkborder rounded-lg px-2.5 py-1.5 text-xs text-slate-900 dark:text-white">
                <option v-for="h in fileHeaders" :key="h" :value="h">{{ h }}</option>
              </select>
            </div>

            <!-- Category Column (Optional) -->
            <div>
              <label class="block text-[10px] font-mono uppercase font-semibold text-slate-500 mb-1">
                Category Column (Optional)
              </label>
              <select
                v-model="mapping.category_column"
                class="w-full bg-slate-50 dark:bg-slate-800/60 border border-brand-border dark:border-brand-darkborder rounded-lg px-2.5 py-1.5 text-xs text-slate-900 dark:text-white">
                <option :value="null">None (Categorize in Review Desk)</option>
                <option v-for="h in fileHeaders" :key="h" :value="h">{{ h }}</option>
              </select>
            </div>
          </div>

          <!-- Save Profile Option -->
          <div class="pt-2 flex items-center space-x-3">
            <label class="flex items-center space-x-2 text-xs text-slate-600 dark:text-slate-300 cursor-pointer">
              <input type="checkbox" v-model="shouldSaveProfile" class="rounded border-slate-300 text-slate-900 focus:ring-0" />
              <span>Save this mapping profile for future imports</span>
            </label>
            <input 
              v-if="shouldSaveProfile" 
              v-model="profileNameToSave"
              type="text" 
              placeholder="Profile Name (e.g. My Bank CSV)"
              class="flex-1 bg-slate-50 dark:bg-slate-800/60 border border-brand-border dark:border-brand-darkborder rounded-lg px-3 py-1 text-xs text-slate-900 dark:text-white" />
          </div>

          <!-- Preview 5 rows table -->
          <div v-if="previewRows.length > 0" class="space-y-1.5 pt-2">
            <span class="text-[10px] font-mono uppercase font-semibold text-slate-400">File Preview (First 5 Rows)</span>
            <div class="overflow-x-auto border border-brand-border dark:border-brand-darkborder rounded-xl">
              <table class="w-full text-left text-[11px] font-mono">
                <thead class="bg-slate-50 dark:bg-slate-800/60 text-slate-500 border-b border-brand-border dark:border-brand-darkborder">
                  <tr>
                    <th v-for="h in fileHeaders" :key="h" class="p-2 whitespace-nowrap">
                      {{ h }}
                    </th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-brand-border dark:divide-brand-darkborder">
                  <tr v-for="(row, rIdx) in previewRows" :key="rIdx" class="hover:bg-slate-50/50 dark:hover:bg-slate-800/30">
                    <td v-for="(val, cIdx) in row" :key="cIdx" class="p-2 whitespace-nowrap text-slate-700 dark:text-slate-300">
                      {{ val }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <!-- Import Results Summary (When Completed) -->
        <div v-if="importResult" class="p-4 rounded-xl border border-emerald-200 dark:border-emerald-900/60 bg-emerald-50/60 dark:bg-emerald-950/20 space-y-3">
          <div class="flex items-center justify-between">
            <h4 class="text-xs font-bold text-emerald-800 dark:text-emerald-300">
              Import Completed Successfully
            </h4>
            <span class="text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-900/60 text-emerald-700 dark:text-emerald-300">
              {{ importResult.staged_count }} Staged
            </span>
          </div>

          <div class="grid grid-cols-3 gap-2 text-center text-xs">
            <div class="p-2 rounded-lg bg-white/70 dark:bg-slate-800/60 border border-brand-border dark:border-brand-darkborder">
              <span class="block text-[10px] text-slate-400 font-mono">Total Rows</span>
              <span class="font-bold text-slate-900 dark:text-white">{{ importResult.total_rows }}</span>
            </div>
            <div class="p-2 rounded-lg bg-white/70 dark:bg-slate-800/60 border border-brand-border dark:border-brand-darkborder">
              <span class="block text-[10px] text-slate-400 font-mono">Staged</span>
              <span class="font-bold text-emerald-600 dark:text-emerald-400">{{ importResult.staged_count }}</span>
            </div>
            <div class="p-2 rounded-lg bg-white/70 dark:bg-slate-800/60 border border-brand-border dark:border-brand-darkborder">
              <span class="block text-[10px] text-slate-400 font-mono">Skipped</span>
              <span class="font-bold text-slate-600 dark:text-slate-300">{{ importResult.skipped_count }}</span>
            </div>
          </div>

          <!-- Skipped Rows Drawer -->
          <div v-if="importResult.skipped_rows && importResult.skipped_rows.length > 0" class="pt-2 space-y-1.5">
            <div class="flex items-center justify-between text-[11px] text-slate-600 dark:text-slate-400 font-medium">
              <span>Skipped Non-Transaction / Malformed Rows:</span>
              <button 
                @click="showSkippedDetails = !showSkippedDetails"
                class="text-brand-primary underline text-[10px]">
                {{ showSkippedDetails ? 'Hide details' : `View ${importResult.skipped_rows.length} skipped rows` }}
              </button>
            </div>
            <div v-if="showSkippedDetails" class="max-h-36 overflow-y-auto rounded-lg bg-white dark:bg-slate-900/80 p-2 border border-brand-border dark:border-brand-darkborder font-mono text-[10px] space-y-1">
              <div v-for="(sr, sIdx) in importResult.skipped_rows" :key="sIdx" class="text-slate-500 border-b border-slate-100 dark:border-slate-800 pb-1">
                <span class="font-bold text-slate-700 dark:text-slate-300">Line {{ sr.line_number }}:</span> {{ sr.reason }}
                <div class="truncate text-slate-400 font-thin">{{ sr.raw }}</div>
              </div>
            </div>
          </div>
        </div>

      </div>

      <!-- Modal Footer -->
      <div class="px-6 py-4 border-t border-brand-border dark:border-brand-darkborder flex items-center justify-between bg-slate-50/50 dark:bg-slate-800/30">
        <button
          @click="close"
          class="px-4 py-2 rounded-full border border-brand-border dark:border-brand-darkborder text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition">
          {{ importResult ? 'Done' : 'Cancel' }}
        </button>

        <button
          v-if="!importResult"
          @click="handleImport"
          :disabled="isSubmitting || !selectedFile || !targetAccountId"
          class="px-5 py-2 rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 text-xs font-semibold hover:opacity-90 transition shadow-sm disabled:opacity-50 flex items-center space-x-2">
          <span v-if="isSubmitting" class="animate-spin w-3 h-3 border-2 border-white dark:border-slate-900 border-t-transparent rounded-full"></span>
          <span>{{ isSubmitting ? 'Parsing Statement...' : 'Import into Review Queue' }}</span>
        </button>

        <button
          v-else
          @click="viewInQueue"
          class="px-5 py-2 rounded-full bg-emerald-600 text-white text-xs font-semibold hover:bg-emerald-500 transition shadow-sm">
          View in Review Queue &rarr;
        </button>
      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch } from 'vue';
import { useRouter } from 'vue-router';
import { api } from '../api/client';
import { useAccountsStore } from '../stores/accounts';
import { useStagingStore } from '../stores/staging';
import type { CSVImportResponse } from '../types';

const props = defineProps<{
  isOpen: boolean;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'imported'): void;
}>();

const router = useRouter();
const accountsStore = useAccountsStore();
const stagingStore = useStagingStore();

const isDragging = ref(false);
const isSubmitting = ref(false);
const errorMessage = ref<string | null>(null);
const fileInput = ref<HTMLInputElement | null>(null);

function triggerFileInput() {
  fileInput.value?.click();
}

const targetAccountId = ref<number | null>(null);
const selectedProfileId = ref<string>('');
const selectedFile = ref<File | null>(null);
const fileHeaders = ref<string[]>([]);
const previewRows = ref<string[][]>([]);

const shouldSaveProfile = ref(false);
const profileNameToSave = ref('');

const importResult = ref<CSVImportResponse | null>(null);
const showSkippedDetails = ref(false);

const mapping = reactive({
  delimiter: 'auto',
  has_header: true,
  skip_rows: 0,
  date_column: '',
  date_format: 'auto',
  merchant_column: '',
  notes_column: null as string | null,
  category_column: null as string | null,
  amount_mode: 'single_standard' as 'single_standard' | 'single_inverted' | 'dual_debit_credit',
  amount_column: '' as string | null,
  debit_column: '' as string | null,
  credit_column: '' as string | null,
});

watch(() => props.isOpen, (val) => {
  if (val) {
    stagingStore.fetchProfiles();
    if (accountsStore.accounts.length === 0) {
      accountsStore.loadData();
    }
    // Default account to first active account
    if (!targetAccountId.value && accountsStore.accounts.length > 0) {
      targetAccountId.value = accountsStore.accounts[0].id;
    }
  } else {
    resetModal();
  }
});

function resetModal() {
  selectedFile.value = null;
  fileHeaders.value = [];
  previewRows.value = [];
  importResult.value = null;
  errorMessage.value = null;
  showSkippedDetails.value = false;
  shouldSaveProfile.value = false;
  profileNameToSave.value = '';
}

function handleFileDrop(e: DragEvent) {
  isDragging.value = false;
  if (e.dataTransfer && e.dataTransfer.files.length > 0) {
    processFile(e.dataTransfer.files[0]);
  }
}

function handleFileSelect(e: Event) {
  const target = e.target as HTMLInputElement;
  if (target.files && target.files.length > 0) {
    processFile(target.files[0]);
  }
}

async function processFile(file: File) {
  selectedFile.value = file;
  errorMessage.value = null;

  try {
    const text = await file.text();
    const lines = text.split(/\r?\n/).filter(l => l.trim().length > 0);
    if (lines.length === 0) {
      throw new Error('File is empty.');
    }

    // Sniff delimiter
    let delim = ',';
    if (lines[0].includes('\t')) delim = '\t';
    else if (lines[0].includes(';')) delim = ';';
    mapping.delimiter = delim;

    // Parse header and top 5 preview rows
    const parseLine = (l: string) => l.split(delim).map(s => s.replace(/^["']|["']$/g, '').trim());
    fileHeaders.value = parseLine(lines[0]);
    previewRows.value = lines.slice(1, 6).map(parseLine);

    // Heuristic auto-selection of columns
    autoDetectColumns(fileHeaders.value);
  } catch (err: any) {
    errorMessage.value = `Could not preview file: ${err.message}`;
  }
}

function autoDetectColumns(headers: string[]) {
  const lower = headers.map(h => h.toLowerCase());
  
  // Date
  const dIdx = lower.findIndex(h => h.includes('date') || h.includes('time'));
  if (dIdx !== -1) mapping.date_column = headers[dIdx];

  // Merchant
  const mIdx = lower.findIndex(h => h.includes('desc') || h.includes('merchant') || h.includes('narrative') || h.includes('payee') || h.includes('name'));
  if (mIdx !== -1) mapping.merchant_column = headers[mIdx];

  // Amount
  const debIdx = lower.findIndex(h => h.includes('debit') || h.includes('paid out') || h.includes('outflow'));
  const credIdx = lower.findIndex(h => h.includes('credit') || h.includes('paid in') || h.includes('inflow'));
  if (debIdx !== -1 && credIdx !== -1) {
    mapping.amount_mode = 'dual_debit_credit';
    mapping.debit_column = headers[debIdx];
    mapping.credit_column = headers[credIdx];
  } else {
    const aIdx = lower.findIndex(h => h.includes('amount') || h.includes('total') || h.includes('value'));
    if (aIdx !== -1) {
      mapping.amount_mode = 'single_standard';
      mapping.amount_column = headers[aIdx];
    }
  }

  // Category
  const cIdx = lower.findIndex(h => h.includes('cat'));
  if (cIdx !== -1) mapping.category_column = headers[cIdx];
}

function applySelectedProfile() {
  if (!selectedProfileId.value) return;
  const prof = stagingStore.profiles.find(p => p.id === selectedProfileId.value);
  if (prof && prof.config) {
    Object.assign(mapping, prof.config);
    if (prof.default_account_id) {
      targetAccountId.value = prof.default_account_id;
    }
  }
}

async function handleImport() {
  if (!selectedFile.value) {
    errorMessage.value = 'Please select a statement file to import.';
    return;
  }

  isSubmitting.value = true;
  errorMessage.value = null;

  try {
    const formData = new FormData();
    formData.append('file', selectedFile.value);
    if (targetAccountId.value) {
      formData.append('account_id', targetAccountId.value.toString());
    }
    formData.append('mapping_config', JSON.stringify(mapping));
    if (shouldSaveProfile.value && profileNameToSave.value.trim()) {
      formData.append('profile_name_to_save', profileNameToSave.value.trim());
    }

    const res = await api.importStatementCsv(formData);
    importResult.value = res;
    await stagingStore.fetchCount();
    emit('imported');
  } catch (err: any) {
    errorMessage.value = err.message || 'Import failed';
  } finally {
    isSubmitting.value = false;
  }
}

function viewInQueue() {
  close();
  router.push('/queue');
}

function close() {
  emit('close');
}
</script>
