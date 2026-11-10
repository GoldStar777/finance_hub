<template>
  <div v-if="isOpen" class="fixed inset-0 z-50 overflow-y-auto" aria-labelledby="modal-title" role="dialog" aria-modal="true">
    <!-- Backdrop -->
    <div 
      class="fixed inset-0 bg-slate-900/60 dark:bg-slate-950/80 backdrop-blur-sm transition-opacity" 
      @click="handleClose">
    </div>

    <div class="flex min-h-screen items-center justify-center p-4">
      <div 
        class="relative w-full max-w-4xl transform rounded-2xl bg-white dark:bg-brand-darksurface p-6 shadow-2xl transition-all border border-brand-border dark:border-brand-darkborder text-slate-800 dark:text-slate-100 flex flex-col max-h-[90vh]">
        
        <!-- Header -->
        <div class="flex items-center justify-between pb-4 border-b border-brand-border dark:border-brand-darkborder shrink-0">
          <div class="flex items-center space-x-3">
            <span class="text-xl">📥</span>
            <div>
              <h3 id="modal-title" class="text-base font-bold text-slate-900 dark:text-white flex items-center space-x-2">
                <span>Unified Financial Import</span>
                <span 
                  v-if="stage === 'review' && importData" 
                  class="text-xs font-mono px-2 py-0.5 rounded-full font-semibold"
                  :class="getDocumentBadgeClass(importData.document_type)">
                  {{ importData.document_type_label }}
                </span>
              </h3>
              <p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                {{ stage === 'upload' 
                  ? 'Accepts receipts, bank statements (CSV/TSV/Excel), screenshots, and PDFs with local inspection.' 
                  : `Review and complete extracted transactions from ${importData?.filename}.` 
                }}
              </p>
            </div>
          </div>

          <button 
            @click="handleClose" 
            class="rounded-lg p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition">
            <span class="text-lg leading-none">&times;</span>
          </button>
        </div>

        <!-- STAGE 1: UPLOAD / DROP ZONE -->
        <div v-if="stage === 'upload'" class="py-6 space-y-6 overflow-y-auto">
          <!-- Drop Area -->
          <div 
            @dragover.prevent="isDragging = true"
            @dragleave.prevent="isDragging = false"
            @drop.prevent="onDrop"
            @click="triggerFileInput"
            class="border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer transition flex flex-col items-center justify-center space-y-3"
            :class="isDragging 
              ? 'border-emerald-500 bg-emerald-50/50 dark:bg-emerald-950/20' 
              : 'border-slate-300 dark:border-slate-700 hover:border-slate-400 dark:hover:border-slate-600 bg-slate-50/50 dark:bg-slate-900/50'">
            
            <input 
              ref="fileInput" 
              type="file" 
              class="hidden" 
              @change="onFileSelected" />

            <div class="w-14 h-14 rounded-full bg-slate-200/80 dark:bg-slate-800 flex items-center justify-center text-2xl shadow-inner">
              📂
            </div>

            <div>
              <p class="text-sm font-semibold text-slate-800 dark:text-slate-200">
                Drop your receipt, statement, screenshot, or spreadsheet here
              </p>
              <p class="text-xs text-slate-500 dark:text-slate-400 mt-1">
                or <span class="text-emerald-600 dark:text-emerald-400 underline font-medium">browse from your computer</span> (any file format accepted)
              </p>
            </div>

            <div class="flex flex-wrap items-center justify-center gap-2 pt-2 text-[11px] font-mono text-slate-400 dark:text-slate-500">
              <span class="px-2 py-0.5 rounded bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700">🧾 Receipts</span>
              <span class="px-2 py-0.5 rounded bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700">📄 CSV / TSV</span>
              <span class="px-2 py-0.5 rounded bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700">📊 Excel (.xlsx)</span>
              <span class="px-2 py-0.5 rounded bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700">📱 Mobile Screenshots</span>
              <span class="px-2 py-0.5 rounded bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700">📑 PDF</span>
            </div>
          </div>

          <!-- Target Account Option -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4 p-4 rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50 dark:bg-slate-900/40">
            <div>
              <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Target Account (Optional)
              </label>
              <select 
                v-model="targetAccountId" 
                class="w-full text-xs rounded-xl border border-brand-border dark:border-brand-darkborder bg-white dark:bg-slate-900 px-3 py-2 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-emerald-500">
                <option :value="null">Unassigned (choose account later)</option>
                <option v-for="acc in accountsStore.accounts" :key="acc.id" :value="acc.id">
                  {{ acc.name }} ({{ acc.currency }})
                </option>
              </select>
              <p class="text-[11px] text-slate-500 dark:text-slate-400 mt-1">
                Leave unassigned if you're not sure which account was used.
              </p>
            </div>

            <div class="text-xs text-slate-500 dark:text-slate-400 flex flex-col justify-center space-y-1">
              <span class="font-semibold text-slate-700 dark:text-slate-300">Privacy & Local Processing</span>
              <span>All classification and OCR occurs strictly offline on your Mac. No file contents or financial data leave your computer.</span>
            </div>
          </div>

          <!-- Error Alert -->
          <div v-if="uploadError" class="p-3.5 rounded-xl border border-rose-200 dark:border-rose-900 bg-rose-50 dark:bg-rose-950/40 text-xs text-rose-700 dark:text-rose-300 flex items-start space-x-2">
            <span>⚠️</span>
            <span>{{ uploadError }}</span>
          </div>

          <!-- Loading indicator -->
          <div v-if="isProcessing" class="flex items-center justify-center space-x-3 py-4 text-xs font-semibold text-slate-600 dark:text-slate-300">
            <span class="animate-spin w-4 h-4 border-2 border-emerald-500 border-t-transparent rounded-full"></span>
            <span>Analyzing file signature, running local extractors, and checking for duplicates...</span>
          </div>
        </div>

        <!-- STAGE 2: INTERACTIVE REVIEW POP-UP -->
        <div v-else-if="stage === 'review' && importData" class="py-4 space-y-4 overflow-y-auto flex-1">
          <!-- Error Alert in Review Stage -->
          <div 
            v-if="reviewError" 
            class="p-3.5 rounded-xl border border-rose-200 dark:border-rose-900 bg-rose-50 dark:bg-rose-950/40 text-xs text-rose-700 dark:text-rose-300 flex items-start justify-between space-x-2">
            <div class="flex items-start space-x-2">
              <span class="text-base shrink-0">⚠️</span>
              <div>
                <p class="font-semibold">{{ reviewError }}</p>
                <p class="text-[11px] text-rose-600 dark:text-rose-400 mt-0.5">
                  The candidate remains in the list. You can retry or choose another action.
                </p>
              </div>
            </div>
            <button 
              type="button"
              @click="reviewError = null" 
              class="text-rose-500 hover:text-rose-700 dark:hover:text-rose-200 text-sm font-bold shrink-0">
              &times;
            </button>
          </div>

          <!-- Summary Banner -->
          <div 
            class="p-3 rounded-xl border flex items-start space-x-3 text-xs"
            :class="importData.document_type === 'unsupported' 
              ? 'border-amber-200 dark:border-amber-900 bg-amber-50 dark:bg-amber-950/40 text-amber-900 dark:text-amber-200' 
              : 'border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 text-slate-700 dark:text-slate-300'">
            <span class="text-base shrink-0">{{ importData.document_type === 'unsupported' ? '💡' : 'ℹ️' }}</span>
            <div class="flex-1">
              <p class="font-semibold">{{ importData.summary }}</p>
              <p class="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                File: <span class="font-mono">{{ importData.filename }}</span> ({{ formatFileSize(importData.file_size_bytes) }}) · MIME: <span class="font-mono">{{ importData.mime_type }}</span>
              </p>
            </div>
            <button 
              @click="resetToUpload" 
              class="text-xs text-slate-500 hover:text-slate-900 dark:hover:text-white underline shrink-0">
              Choose another file
            </button>
          </div>

          <!-- Progressive Review Dashboard Cards -->
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div class="p-3 rounded-xl border border-emerald-200 dark:border-emerald-900/60 bg-emerald-50/50 dark:bg-emerald-950/20 text-center">
              <span class="text-xs font-semibold text-emerald-700 dark:text-emerald-300">Ready to Add</span>
              <p class="text-xl font-bold text-emerald-800 dark:text-emerald-200">{{ readyToAddCount }}</p>
            </div>
            <div class="p-3 rounded-xl border border-amber-200 dark:border-amber-900/60 bg-amber-50/50 dark:bg-amber-950/20 text-center">
              <span class="text-xs font-semibold text-amber-700 dark:text-amber-300">Needs Review</span>
              <p class="text-xl font-bold text-amber-800 dark:text-amber-200">{{ needsReviewCount }}</p>
            </div>
            <div class="p-3 rounded-xl border border-blue-200 dark:border-blue-900/60 bg-blue-50/50 dark:bg-blue-950/20 text-center">
              <span class="text-xs font-semibold text-blue-700 dark:text-blue-300">Added to Ledger</span>
              <p class="text-xl font-bold text-blue-800 dark:text-blue-200">{{ alreadyAddedCount }}</p>
            </div>
            <div class="p-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 text-center">
              <span class="text-xs font-semibold text-slate-600 dark:text-slate-400">Excluded</span>
              <p class="text-xl font-bold text-slate-700 dark:text-slate-300">{{ excludedCount }}</p>
            </div>
          </div>

          <!-- Direction Analysis Banner & Controls -->
          <div 
            v-if="importData.direction_summary || reviewItems.length > 0"
            class="p-3.5 rounded-xl border space-y-2.5 text-xs transition"
            :class="directionSummaryClass">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div class="flex items-center space-x-2">
                <span class="text-sm">🧭</span>
                <span class="font-bold">Transaction Direction Analysis</span>
                <span 
                  v-if="importData.direction_summary?.evidence_type" 
                  class="px-2 py-0.5 rounded text-[10px] font-mono bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700">
                  {{ importData.direction_summary.evidence_type }}
                </span>
              </div>

              <!-- Direction Counts -->
              <div class="flex items-center space-x-2 font-mono text-[11px]">
                <span class="px-2 py-0.5 rounded-full bg-rose-100 dark:bg-rose-950/60 text-rose-800 dark:text-rose-300 font-semibold">
                  {{ expenseCount }} Expense{{ expenseCount === 1 ? '' : 's' }}
                </span>
                <span class="px-2 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300 font-semibold">
                  {{ incomeCount }} Income
                </span>
                <span 
                  v-if="uncertainCount > 0" 
                  class="px-2 py-0.5 rounded-full bg-amber-100 dark:bg-amber-950/60 text-amber-800 dark:text-amber-300 font-bold animate-pulse">
                  ⚠️ {{ uncertainCount }} Uncertain
                </span>
              </div>
            </div>

            <p class="text-[11px] opacity-90 leading-relaxed">
              {{ importData.direction_summary?.evidence_description || 'Derived from transaction columns.' }}
            </p>

            <div v-if="uncertainCount > 0" class="p-2 rounded-lg bg-amber-500/10 border border-amber-400/30 text-amber-900 dark:text-amber-200 text-[11px]">
              <strong>Unsigned amounts require review:</strong> Transaction directions could not be unambiguously derived from statement columns. Set or verify directions before committing.
            </div>

            <!-- Batch Direction Controls -->
            <div class="flex flex-wrap items-center justify-end gap-2 pt-1 border-t border-slate-200/60 dark:border-slate-800/60">
              <button 
                type="button" 
                @click="invertAllDirections"
                class="px-2.5 py-1 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition font-medium text-[11px] flex items-center space-x-1">
                <span>🔄 Invert all directions</span>
              </button>
              <button 
                v-if="uncertainCount > 0"
                type="button" 
                @click="setAllUncertainTo('expense')"
                class="px-2.5 py-1 rounded-lg border border-rose-300 dark:border-rose-800 bg-white dark:bg-slate-900 text-rose-700 dark:text-rose-300 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition font-medium text-[11px]">
                Set {{ uncertainCount }} uncertain to Expense
              </button>
              <button 
                v-if="uncertainCount > 0"
                type="button" 
                @click="setAllUncertainTo('income')"
                class="px-2.5 py-1 rounded-lg border border-emerald-300 dark:border-emerald-800 bg-white dark:bg-slate-900 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-50 dark:hover:bg-emerald-950/40 transition font-medium text-[11px]">
                Set {{ uncertainCount }} uncertain to Income
              </button>
            </div>
          </div>

          <!-- Items Review List -->
          <div class="space-y-3">
            <div 
              v-for="(item, idx) in reviewItems" 
              :key="item.id"
              :id="`review-item-${idx}`"
              class="p-4 rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50/50 dark:bg-slate-900/50 space-y-3 transition"
              :class="{
                'border-amber-400 dark:border-amber-600 bg-amber-50/20': item.is_potential_duplicate || item.direction_uncertain,
                'border-rose-400 dark:border-rose-600 bg-rose-50/20': !isRowValid(item)
              }">
              
              <!-- Item Row Top: Index, Type & Exclusion Button -->
              <div class="flex flex-wrap items-center justify-between gap-2 text-xs">
                <div class="flex items-center space-x-2">
                  <span class="font-mono font-bold text-slate-400 dark:text-slate-500">#{{ idx + 1 }}</span>
                  <select 
                    v-model="item.transaction_type" 
                    @change="onRowTypeChange(item)"
                    class="rounded-lg border border-brand-border dark:border-brand-darkborder bg-white dark:bg-slate-900 px-2 py-1 text-xs font-semibold focus:outline-none focus:ring-1 focus:ring-emerald-500">
                    <option value="expense">Expense</option>
                    <option value="income">Income</option>
                    <option value="transfer">Transfer</option>
                  </select>

                  <span 
                    v-if="item.direction_uncertain" 
                    class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 dark:bg-amber-950 text-amber-800 dark:text-amber-300">
                    ⚠️ Direction uncertain
                  </span>

                  <span 
                    v-if="item.is_potential_duplicate" 
                    class="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-amber-100 dark:bg-amber-950 text-amber-800 dark:text-amber-300">
                    ⚠️ Duplicate
                  </span>

                  <span 
                    v-if="item.missing_fields && item.missing_fields.length > 0" 
                    class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-100 dark:bg-rose-950 text-rose-800 dark:text-rose-300">
                    Needs Attention
                  </span>
                </div>

                <!-- Row Actions: Split, Apply to Similar, Skip, Approve & Next, Exclude -->
                <div class="flex items-center space-x-2">
                  <button
                    type="button"
                    v-if="item.transaction_type === 'expense' && (Number(item.amount_input) || 0) > 0"
                    @click="openSplitModal(item, idx)"
                    class="px-2 py-1 rounded-md text-[11px] font-medium border border-indigo-200 dark:border-indigo-800 bg-indigo-50/70 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 hover:bg-indigo-100 dark:hover:bg-indigo-900/60 transition flex items-center space-x-1"
                    title="Divide this single receipt expense into two or more categorized rows">
                    <span>✂️ Split</span>
                  </button>

                  <button
                    type="button"
                    v-if="item.merchant_input && item.merchant_input.trim()"
                    @click="openApplyToSimilar(item)"
                    class="px-2 py-1 rounded-md text-[11px] font-medium border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition flex items-center space-x-1"
                    title="Apply type, category, or account to similar transactions in this import">
                    <span>⚡️ Apply to similar...</span>
                  </button>

                  <button
                    type="button"
                    @click="skipItem(idx)"
                    class="px-2 py-1 rounded-md text-[11px] text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200 transition"
                    title="Skip to next item">
                    Skip ↷
                  </button>

                  <button
                    type="button"
                    @click="approveRowAndNext(item, idx)"
                    :disabled="isRowApproving[item.id] || isCommitting || !isRowValid(item)"
                    class="px-2.5 py-1 rounded-md text-[11px] font-semibold bg-emerald-600 hover:bg-emerald-700 text-white transition shadow-xs flex items-center space-x-1 disabled:opacity-40"
                    title="Approve this row to ledger and advance to next">
                    <span v-if="isRowApproving[item.id]" class="animate-spin w-2.5 h-2.5 border border-white border-t-transparent rounded-full"></span>
                    <span>✓ Approve & next</span>
                  </button>

                  <button 
                    type="button"
                    @click="excludeItem(item, idx)" 
                    :disabled="isDiscarding[item.id] || isCommitting"
                    class="text-xs text-slate-400 hover:text-rose-500 transition flex items-center space-x-1 disabled:opacity-50"
                    :title="item.is_potential_duplicate ? 'Exclude as duplicate' : 'Exclude this item'">
                    <span v-if="isDiscarding[item.id]" class="animate-spin w-3 h-3 border-2 border-slate-400 border-t-transparent rounded-full"></span>
                    <span>&times; Exclude</span>
                  </button>
                </div>
              </div>

              <!-- Main Fields Grid -->
              <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                <!-- Date -->
                <div>
                  <label class="block text-[11px] font-semibold text-slate-600 dark:text-slate-400 mb-1">
                    Date <span class="text-rose-500">*</span>
                  </label>
                  <input 
                    type="date" 
                    v-model="item.date_input" 
                    class="w-full text-xs rounded-lg border px-2.5 py-1.5 bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                    :class="!item.date_input ? 'border-rose-400 dark:border-rose-600 ring-1 ring-rose-400' : 'border-brand-border dark:border-brand-darkborder'" />
                  <p v-if="item.date_uncertain" class="text-[10px] text-amber-600 dark:text-amber-400 mt-0.5 font-medium">
                    ⚠️ Review date
                  </p>
                </div>

                <!-- Merchant / Payee -->
                <div>
                  <label class="block text-[11px] font-semibold text-slate-600 dark:text-slate-400 mb-1">
                    Merchant / Payee
                  </label>
                  <input 
                    type="text" 
                    v-model="item.merchant_input" 
                    placeholder="Merchant not recorded" 
                    class="w-full text-xs rounded-lg border border-brand-border dark:border-brand-darkborder px-2.5 py-1.5 bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500" />
                  <p v-if="item.merchant_uncertain || !item.merchant_input" class="text-[10px] text-amber-600 dark:text-amber-400 mt-0.5 font-medium">
                    ⚠️ Review merchant
                  </p>
                </div>

                <!-- Amount -->
                <div>
                  <label class="block text-[11px] font-semibold text-slate-600 dark:text-slate-400 mb-1">
                    Amount ({{ item.currency }}) <span class="text-rose-500">*</span>
                  </label>
                  <div class="relative">
                    <span class="absolute left-2.5 top-1.5 text-xs text-slate-400">
                      {{ getCurrencySymbol(item.currency) }}
                    </span>
                    <input 
                      type="number" 
                      step="0.01" 
                      min="0.01"
                      v-model="item.amount_input" 
                      placeholder="0.00" 
                      class="w-full text-xs rounded-lg border pl-6 pr-2.5 py-1.5 bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                      :class="!item.amount_input || Number(item.amount_input) <= 0 ? 'border-rose-400 dark:border-rose-600 ring-1 ring-rose-400' : 'border-brand-border dark:border-brand-darkborder'" />
                  </div>
                </div>

                <!-- Account -->
                <div>
                  <label class="block text-[11px] font-semibold text-slate-600 dark:text-slate-400 mb-1">
                    Account
                  </label>
                  <select 
                    v-model="item.account_id" 
                    class="w-full text-xs rounded-lg border border-brand-border dark:border-brand-darkborder px-2.5 py-1.5 bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500">
                    <option :value="null">Unassigned (assign later)</option>
                    <option v-for="acc in accountsStore.accounts" :key="acc.id" :value="acc.id">
                      {{ acc.name }}
                    </option>
                  </select>
                  <p v-if="item.account_match_reason" class="text-[10px] text-emerald-600 dark:text-emerald-400 mt-0.5 truncate" :title="item.account_match_reason">
                    💡 {{ item.account_match_reason }}
                  </p>
                </div>
              </div>

              <!-- Secondary Fields Grid (Category, Nature, Transfer Dest) -->
              <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-1 border-t border-slate-200/60 dark:border-slate-800/60">
                <!-- Category -->
                <div v-if="item.transaction_type !== 'transfer'">
                  <label class="block text-[11px] font-semibold text-slate-600 dark:text-slate-400 mb-1">
                    {{ item.transaction_type === 'income' ? 'Income Category' : 'Expense Category' }}
                  </label>
                  <select 
                    v-model="item.category_id" 
                    @change="onCategoryChange(item)"
                    class="w-full text-xs rounded-lg border border-brand-border dark:border-brand-darkborder px-2.5 py-1.5 bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500">
                    <option :value="null">Uncategorised</option>
                    <option v-for="cat in getCategoriesForType(item.transaction_type)" :key="cat.id" :value="cat.id">
                      {{ cat.name }}
                    </option>
                  </select>
                  <p v-if="item.category_cleared_notice" class="text-[10px] text-amber-600 dark:text-amber-400 mt-0.5">
                    {{ item.category_cleared_notice }}
                  </p>
                  <p v-else-if="item.category_match_reason" class="text-[10px] text-emerald-600 dark:text-emerald-400 mt-0.5 truncate" :title="item.category_match_reason">
                    💡 {{ item.category_match_reason }}
                  </p>
                </div>

                <!-- Nature (Only for Expense) -->
                <div v-if="item.transaction_type === 'expense'">
                  <label class="block text-[11px] font-semibold text-slate-600 dark:text-slate-400 mb-1">
                    Expense Nature
                  </label>
                  <select 
                    v-model="item.expense_nature" 
                    @change="onNatureChange(item)"
                    class="w-full text-xs rounded-lg border border-brand-border dark:border-brand-darkborder px-2.5 py-1.5 bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500">
                    <option value="unclassified">Unclassified</option>
                    <option value="variable">Variable</option>
                    <option value="fixed">Fixed</option>
                  </select>
                </div>

                <!-- Destination Account (If Transfer) -->
                <div v-if="item.transaction_type === 'transfer'">
                  <label class="block text-[11px] font-semibold text-slate-600 dark:text-slate-400 mb-1">
                    Destination Account <span class="text-rose-500">*</span>
                  </label>
                  <select 
                    v-model="item.destination_account_id" 
                    class="w-full text-xs rounded-lg border border-brand-border dark:border-brand-darkborder px-2.5 py-1 bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500">
                    <option :value="null">Select destination...</option>
                    <option 
                      v-for="acc in accountsStore.accounts" 
                      :key="acc.id" 
                      :value="acc.id"
                      :disabled="acc.id === item.account_id">
                      {{ acc.name }}
                    </option>
                  </select>
                </div>

                <!-- Notes (If not Transfer) -->
                <div v-else>
                  <label class="block text-[11px] font-semibold text-slate-600 dark:text-slate-400 mb-1">
                    Notes
                  </label>
                  <input 
                    type="text" 
                    v-model="item.notes" 
                    placeholder="Optional notes" 
                    class="w-full text-xs rounded-lg border border-brand-border dark:border-brand-darkborder px-2.5 py-1 bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500" />
                </div>
              </div>

              <!-- Foreign Currency Notice -->
              <div v-if="item.currency_conflict || item.original_currency" class="p-2.5 rounded-lg border border-sky-200 dark:border-sky-900 bg-sky-50 dark:bg-sky-950/30 text-xs text-sky-800 dark:text-sky-300">
                <span class="font-bold">Foreign Provenance:</span>
                Original amount was {{ item.original_currency }} {{ item.original_amount }}. Enter the actual base charge charged to your account above.
              </div>

              <!-- Advisory Duplicate Warning & Exclusion Action -->
              <div v-if="item.is_potential_duplicate && item.duplicate_matches && item.duplicate_matches.length > 0" class="p-3 rounded-lg border border-amber-200 dark:border-amber-900 bg-amber-50 dark:bg-amber-950/40 text-xs text-amber-800 dark:text-amber-200 space-y-2">
                <div class="font-semibold flex items-center space-x-1">
                  <span>⚠️ Advisory duplicate match found:</span>
                </div>
                <div v-for="match in item.duplicate_matches" :key="match.id" class="text-[11px] text-amber-700 dark:text-amber-300 pl-2 border-l-2 border-amber-400 dark:border-amber-600">
                  Transaction #{{ match.id }} · {{ match.merchant || 'Merchant not recorded' }} · £{{ (match.amount_pence / 100).toFixed(2) }} ({{ match.match_reasons?.join(', ') }})
                </div>

                <div class="pt-2 border-t border-amber-200/80 dark:border-amber-800/80 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <p class="text-[11px] text-amber-800 dark:text-amber-300">
                    Matches an existing ledger transaction. Exclude as duplicate to discard this candidate from both this import and the review queue.
                  </p>
                  <button
                    type="button"
                    @click="excludeAsDuplicate(item, idx)"
                    :disabled="isDiscarding[item.id] || isCommitting"
                    class="shrink-0 px-3 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-700 text-white font-semibold text-xs transition shadow-xs flex items-center space-x-1.5 disabled:opacity-50">
                    <span v-if="isDiscarding[item.id]" class="animate-spin w-3 h-3 border-2 border-white border-t-transparent rounded-full"></span>
                    <span>🚫 Exclude as duplicate</span>
                  </button>
                </div>
              </div>

            </div>
          </div>
        </div>

        <!-- STAGE 2 ACTIONS FOOTER -->
        <div v-if="stage === 'review'" class="pt-4 border-t border-brand-border dark:border-brand-darkborder flex flex-wrap items-center justify-between gap-3 shrink-0">
          <div class="flex items-center space-x-2 text-xs text-slate-500 dark:text-slate-400">
            <span class="font-medium">{{ reviewItems.length }} remaining</span>
            <span>·</span>
            <span class="text-emerald-600 dark:text-emerald-400 font-semibold">{{ readyToAddCount }} ready to add</span>
            <span v-if="alreadyAddedCount > 0" class="text-blue-600 dark:text-blue-400 font-semibold">· {{ alreadyAddedCount }} added</span>
          </div>

          <div class="flex items-center space-x-2.5">
            <button 
              type="button"
              @click="handleDiscardAll"
              :disabled="isCommitting || isAnyDiscarding" 
              class="px-3.5 py-1.5 rounded-full border border-slate-300 dark:border-slate-700 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition flex items-center space-x-1.5 disabled:opacity-50">
              <span v-if="isCommitting && commitAction === 'discard'" class="animate-spin w-3 h-3 border-2 border-slate-500 border-t-transparent rounded-full"></span>
              <span>Discard</span>
            </button>

            <button 
              type="button"
              @click="handleQueueAll"
              :disabled="isCommitting || isAnyDiscarding" 
              class="px-3.5 py-1.5 rounded-full border border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-semibold text-slate-800 dark:text-slate-200 transition shadow-xs flex items-center space-x-1.5 disabled:opacity-50">
              <span v-if="isCommitting && commitAction === 'queue'" class="animate-spin w-3 h-3 border-2 border-slate-500 border-t-transparent rounded-full"></span>
              <span>Send to Review Queue</span>
            </button>

            <!-- Progressive Approval: Add Reviewed to Ledger (X) -->
            <button 
              v-if="readyToAddCount > 0 && readyToAddCount < reviewItems.length"
              type="button"
              @click="handleApproveReviewed"
              :disabled="isCommitting || isAnyDiscarding" 
              class="px-4 py-1.5 rounded-full bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold transition shadow-sm flex items-center space-x-1.5 disabled:opacity-50">
              <span v-if="isCommitting && commitAction === 'approve_reviewed'" class="animate-spin w-3 h-3 border-2 border-white border-t-transparent rounded-full"></span>
              <span>Add Reviewed to Ledger ({{ readyToAddCount }})</span>
            </button>

            <!-- Add All to Ledger Now -->
            <button 
              type="button"
              @click="handleApproveAll"
              :disabled="isCommitting || !canApproveAll || isAnyDiscarding" 
              class="px-4 py-1.5 rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 text-xs font-semibold hover:opacity-90 transition shadow-sm flex items-center space-x-1.5 disabled:opacity-50">
              <span v-if="isCommitting && commitAction === 'approve'" class="animate-spin w-3 h-3 border-2 border-slate-500 border-t-transparent rounded-full"></span>
              <span>Add All to Ledger Now ({{ reviewItems.length }})</span>
            </button>
          </div>
        </div>

        <!-- APPLY TO SIMILAR MODAL DIALOG -->
        <div v-if="isSimilarModalOpen && similarSourceItem" class="fixed inset-0 z-60 overflow-y-auto" role="dialog" aria-modal="true">
          <div class="fixed inset-0 bg-slate-900/60 dark:bg-slate-950/80 backdrop-blur-xs transition-opacity" @click="isSimilarModalOpen = false"></div>
          <div class="flex min-h-screen items-center justify-center p-4">
            <div class="relative w-full max-w-xl rounded-2xl bg-white dark:bg-brand-darksurface p-5 shadow-2xl border border-brand-border dark:border-brand-darkborder text-slate-800 dark:text-slate-100 space-y-4">
              <div class="flex items-center justify-between pb-3 border-b border-brand-border dark:border-brand-darkborder">
                <div>
                  <h4 class="text-sm font-bold flex items-center space-x-1.5">
                    <span>⚡️ Apply to Similar Transactions</span>
                  </h4>
                  <p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                    Propagate corrections from <span class="font-semibold text-slate-800 dark:text-slate-200">"{{ similarSourceItem.merchant_input }}"</span> across this import.
                  </p>
                </div>
                <button @click="isSimilarModalOpen = false" class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 text-lg leading-none">&times;</button>
              </div>

              <!-- Choose fields to apply -->
              <div class="p-3 rounded-xl bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 space-y-2">
                <span class="text-xs font-semibold text-slate-700 dark:text-slate-300">Fields to apply to matches:</span>
                <div class="grid grid-cols-2 gap-2 text-xs">
                  <label class="flex items-center space-x-2 cursor-pointer">
                    <input type="checkbox" v-model="similarApplyType" class="rounded text-emerald-600 focus:ring-emerald-500" />
                    <span>Type: <strong class="capitalize">{{ similarSourceItem.transaction_type }}</strong></span>
                  </label>
                  <label class="flex items-center space-x-2 cursor-pointer">
                    <input type="checkbox" v-model="similarApplyCategory" class="rounded text-emerald-600 focus:ring-emerald-500" />
                    <span>Category: <strong>{{ similarSourceItem.category_name || 'Uncategorised' }}</strong></span>
                  </label>
                  <label class="flex items-center space-x-2 cursor-pointer">
                    <input type="checkbox" v-model="similarApplyAccount" class="rounded text-emerald-600 focus:ring-emerald-500" />
                    <span>Account: <strong>{{ getAccountName(similarSourceItem.account_id) }}</strong></span>
                  </label>
                  <label class="flex items-center space-x-2 cursor-pointer">
                    <input type="checkbox" v-model="similarApplyNature" class="rounded text-emerald-600 focus:ring-emerald-500" />
                    <span>Nature: <strong class="capitalize">{{ similarSourceItem.expense_nature }}</strong></span>
                  </label>
                </div>
              </div>

              <!-- Matching list -->
              <div class="space-y-2">
                <div class="flex items-center justify-between text-xs">
                  <span class="font-semibold text-slate-700 dark:text-slate-300">
                    Matching transactions ({{ similarMatches.length }} found, {{ selectedSimilarCount }} selected):
                  </span>
                  <button 
                    type="button" 
                    @click="toggleAllSimilarSelection" 
                    class="text-emerald-600 dark:text-emerald-400 hover:underline">
                    {{ allSimilarSelected ? 'Deselect all' : 'Select all' }}
                  </button>
                </div>

                <div v-if="similarMatches.length === 0" class="p-4 text-center text-xs text-slate-500 border border-dashed rounded-xl">
                  No other pending transactions match "{{ similarSourceItem.merchant_input }}".
                </div>

                <div v-else class="max-h-52 overflow-y-auto space-y-1.5 pr-1 text-xs">
                  <label 
                    v-for="(m, mIdx) in similarMatches" 
                    :key="m.item.id" 
                    class="flex items-center justify-between p-2 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/50 transition">
                    <div class="flex items-center space-x-2 min-w-0">
                      <input type="checkbox" v-model="m.selected" class="rounded text-emerald-600 focus:ring-emerald-500" />
                      <span class="font-mono text-slate-400 text-[11px] shrink-0">#{{ mIdx + 1 }}</span>
                      <span class="font-mono text-slate-600 dark:text-slate-400 shrink-0">{{ m.item.date_input || 'No date' }}</span>
                      <span class="truncate font-medium text-slate-800 dark:text-slate-200">{{ m.item.merchant_input || 'No merchant' }}</span>
                    </div>
                    <div class="flex items-center space-x-2 font-mono shrink-0 pl-2">
                      <span>£{{ Number(m.item.amount_input || 0).toFixed(2) }}</span>
                      <span class="px-1.5 py-0.5 rounded text-[10px] capitalize bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                        {{ m.item.transaction_type }}
                      </span>
                    </div>
                  </label>
                </div>
              </div>

              <!-- Future profile learning checkbox -->
              <div class="p-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-900/30 text-xs">
                <label class="flex items-start space-x-2 cursor-pointer">
                  <input type="checkbox" v-model="similarRememberFuture" class="mt-0.5 rounded text-emerald-600 focus:ring-emerald-500" />
                  <span class="text-slate-600 dark:text-slate-300">
                    Remember this assignment for future imports in this profile
                  </span>
                </label>
                <p class="text-[10px] text-slate-400 dark:text-slate-500 mt-1 pl-5">
                  If unchecked, corrections are strictly limited to the current import.
                </p>
              </div>

              <!-- Modal footer -->
              <div class="flex items-center justify-end space-x-2.5 pt-3 border-t border-brand-border dark:border-brand-darkborder">
                <button 
                  type="button" 
                  @click="isSimilarModalOpen = false" 
                  class="px-3.5 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition">
                  Cancel
                </button>
                <button 
                  type="button" 
                  @click="applyToSimilarConfirm" 
                  :disabled="selectedSimilarCount === 0"
                  class="px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold transition disabled:opacity-50 shadow-xs">
                  Apply to {{ selectedSimilarCount }} matching transaction{{ selectedSimilarCount === 1 ? '' : 's' }}
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- SPLIT EXPENSE MODAL -->
        <SplitExpenseModal
          :is-open="isSplitModalOpen"
          :item="splittingItem"
          :accounts="accountsStore.accounts"
          :categories="activeCategories"
          :base-currency="systemStore.config?.base_currency || 'GBP'"
          :base-currency-symbol="systemStore.config?.base_currency_symbol || '£'"
          :allow-immediate-approve="true"
          @close="isSplitModalOpen = false; splittingItem = null; splittingItemIndex = -1"
          @split-success="handleSplitSuccess"
        />

      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { api } from '../api/client';
import { useAccountsStore } from '../stores/accounts';
import { useTransactionsStore } from '../stores/transactions';
import { useStagingStore } from '../stores/staging';
import { useSystemStore } from '../stores/system';
import SplitExpenseModal from './SplitExpenseModal.vue';
import { filterCategoriesForTransactionType, isCategoryCompatibleWithTransaction } from '../utils/categoryPurpose';
import type { 
  UnifiedImportResponse, 
  ExpenseNature,
  TransactionType,
  UnifiedImportCommitPayload
} from '../types';

const props = defineProps<{
  isOpen: boolean;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'imported', result: any): void;
}>();

const accountsStore = useAccountsStore();
const transactionsStore = useTransactionsStore();
const stagingStore = useStagingStore();
const systemStore = useSystemStore();

const activeCategories = computed(() => {
  return transactionsStore.categories.filter(c => c.is_active);
});

watch(() => props.isOpen, (newVal) => {
  if (newVal) {
    if (transactionsStore.categories.length === 0) {
      transactionsStore.loadCategories();
    }
    if (accountsStore.accounts.length === 0) {
      accountsStore.loadData();
    }
    if (!systemStore.config) {
      systemStore.loadConfig();
    }
  }
});

onMounted(() => {
  if (transactionsStore.categories.length === 0) {
    transactionsStore.loadCategories();
  }
});

const stage = ref<'upload' | 'review'>('upload');
const isDragging = ref(false);
const isProcessing = ref(false);
const isCommitting = ref(false);
const uploadError = ref<string | null>(null);
const targetAccountId = ref<number | null>(null);
const fileInput = ref<HTMLInputElement | null>(null);

// Session counters
const alreadyAddedCount = ref(0);
const excludedCount = ref(0);

const importData = ref<UnifiedImportResponse | null>(null);
const reviewItems = ref<Array<{
  id: number;
  date_input: string;
  merchant_input: string;
  amount_input: number | string;
  currency: string;
  account_id: number | null;
  account_match_reason?: string | null;
  destination_account_id: number | null;
  transaction_type: TransactionType;
  direction_uncertain: boolean;
  direction_evidence?: string | null;
  category_id: number | null;
  category_name: string;
  expense_nature: ExpenseNature;
  is_nature_manually_overridden: boolean;
  notes: string;
  original_amount?: number | null;
  original_currency?: string | null;
  currency_conflict: boolean;
  is_potential_duplicate: boolean;
  duplicate_matches: any[];
  missing_fields: string[];
  date_uncertain?: boolean;
  merchant_uncertain?: boolean;
  category_match_reason?: string | null;
  category_cleared_notice?: string | null;
}>>([]);

function triggerFileInput() {
  fileInput.value?.click();
}

function onFileSelected(e: Event) {
  const target = e.target as HTMLInputElement;
  if (target.files && target.files.length > 0) {
    processUpload(target.files[0]);
  }
}

function onDrop(e: DragEvent) {
  isDragging.value = false;
  if (e.dataTransfer && e.dataTransfer.files.length > 0) {
    processUpload(e.dataTransfer.files[0]);
  }
}

async function processUpload(file: File) {
  uploadError.value = null;
  isProcessing.value = true;
  alreadyAddedCount.value = 0;
  excludedCount.value = 0;

  try {
    const formData = new FormData();
    formData.append('file', file);
    if (targetAccountId.value) {
      formData.append('account_id', targetAccountId.value.toString());
    }

    const res = await api.importUnifiedFile(formData);
    importData.value = res;

    // Map response items to editable models
    reviewItems.value = res.items.map(it => ({
      id: it.id,
      date_input: it.extracted_date ? it.extracted_date.split('T')[0] : '',
      merchant_input: it.extracted_merchant || '',
      amount_input: it.extracted_amount_pounds !== null ? it.extracted_amount_pounds : '',
      currency: it.currency || 'GBP',
      account_id: it.suggested_account_id,
      account_match_reason: it.suggested_account_match_reason,
      destination_account_id: null,
      transaction_type: it.transaction_type || 'expense',
      direction_uncertain: it.direction_uncertain || false,
      direction_evidence: it.direction_evidence || null,
      category_id: it.suggested_category_id || null,
      category_name: it.suggested_category_name || '',
      expense_nature: (it.suggested_expense_nature as ExpenseNature) || 'unclassified',
      is_nature_manually_overridden: false,
      notes: it.notes || '',
      original_amount: it.original_amount,
      original_currency: it.original_currency,
      currency_conflict: it.currency_conflict,
      is_potential_duplicate: it.is_potential_duplicate,
      duplicate_matches: it.duplicate_matches,
      missing_fields: it.missing_fields || [],
      date_uncertain: it.date_uncertain || false,
      merchant_uncertain: it.merchant_uncertain || false,
      category_match_reason: it.category_match_reason || null
    }));

    stage.value = 'review';
    await Promise.all([
      stagingStore.fetchCount(),
      stagingStore.fetchSuggestions(),
    ]);
  } catch (err: any) {
    uploadError.value = err.message || 'Failed to process file.';
  } finally {
    isProcessing.value = false;
    if (fileInput.value) fileInput.value.value = '';
  }
}

function getCategoriesForType(txType: string) {
  return filterCategoriesForTransactionType(transactionsStore.categories, txType);
}

function reconcileCategoryForType(item: any) {
  if (
    item.category_id !== null &&
    item.category_id !== undefined &&
    !isCategoryCompatibleWithTransaction(transactionsStore.categories, item.category_id, item.transaction_type)
  ) {
    item.category_id = null;
    item.category_name = '';
    item.expense_nature = 'unclassified';
    item.category_cleared_notice =
      item.transaction_type === 'transfer'
        ? 'Category cleared for transfer.'
        : `Cleared previous category for ${item.transaction_type} direction.`;
  } else {
    item.category_cleared_notice = null;
  }
  if (item.transaction_type !== 'expense') {
    item.expense_nature = 'unclassified';
  }
}

function onRowTypeChange(item: any) {
  item.direction_uncertain = false;
  item.missing_fields = (item.missing_fields || []).filter((f: string) => f !== 'transaction_type');
  reconcileCategoryForType(item);
}

function onCategoryChange(item: any) {
  item.category_cleared_notice = null;
  const cat = transactionsStore.categories.find(c => c.id === item.category_id);
  item.category_name = cat ? cat.name : '';

  // Auto-default expense nature from category only if user has not manually overridden it on expense rows
  if (item.transaction_type === 'expense' && !item.is_nature_manually_overridden) {
    if (cat && cat.default_expense_nature) {
      item.expense_nature = cat.default_expense_nature.toLowerCase() as ExpenseNature;
    } else if (!item.category_id) {
      item.expense_nature = 'unclassified';
    }
  } else if (item.transaction_type !== 'expense') {
    item.expense_nature = 'unclassified';
  }
}

function onNatureChange(item: any) {
  item.is_nature_manually_overridden = true;
}

const isDiscarding = ref<Record<number, boolean>>({});
const isRowApproving = ref<Record<number, boolean>>({});
const reviewError = ref<string | null>(null);
const commitAction = ref<'approve' | 'approve_reviewed' | 'queue' | 'discard' | null>(null);
const isAnyDiscarding = computed(() => Object.values(isDiscarding.value).some(Boolean));

// Row validity helper
function isRowValid(item: any): boolean {
  const hasDate = Boolean(item.date_input);
  const hasAmount = Boolean(item.amount_input) && Number(item.amount_input) > 0;
  if (!hasDate || !hasAmount) return false;
  if (item.transaction_type === 'transfer' && (!item.account_id || !item.destination_account_id)) {
    return false;
  }
  return true;
}

// Progressive review computed properties
const readyItems = computed(() => {
  return reviewItems.value.filter(isRowValid);
});

const readyToAddCount = computed(() => readyItems.value.length);
const needsReviewCount = computed(() => reviewItems.value.length - readyToAddCount.value);

const expenseCount = computed(() => reviewItems.value.filter(i => i.transaction_type === 'expense').length);
const incomeCount = computed(() => reviewItems.value.filter(i => i.transaction_type === 'income').length);
const uncertainCount = computed(() => reviewItems.value.filter(i => i.direction_uncertain).length);

const directionSummaryClass = computed(() => {
  if (uncertainCount.value > 0) {
    return 'border-amber-300 dark:border-amber-800 bg-amber-50/60 dark:bg-amber-950/30 text-amber-900 dark:text-amber-200';
  }
  return 'border-slate-200 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-900/60 text-slate-700 dark:text-slate-300';
});

function invertAllDirections() {
  if (!confirm('Invert all transaction directions in this import? Expenses will become Income, and Income will become Expenses.')) {
    return;
  }
  for (const item of reviewItems.value) {
    if (item.transaction_type === 'expense') {
      item.transaction_type = 'income';
    } else if (item.transaction_type === 'income') {
      item.transaction_type = 'expense';
    }
    item.direction_uncertain = false;
    item.missing_fields = item.missing_fields.filter(f => f !== 'transaction_type');
    reconcileCategoryForType(item);
  }
}

function setAllUncertainTo(type: 'expense' | 'income') {
  for (const item of reviewItems.value) {
    if (item.direction_uncertain) {
      item.transaction_type = type;
      item.direction_uncertain = false;
      item.missing_fields = item.missing_fields.filter(f => f !== 'transaction_type');
      reconcileCategoryForType(item);
    }
  }
}

function getAccountName(accId: number | null): string {
  if (!accId) return 'Unassigned';
  const a = accountsStore.accounts.find(acc => acc.id === accId);
  return a ? a.name : `Account #${accId}`;
}

async function discardItemFromStaging(item: any, idx: number) {
  if (!item || !item.id) {
    reviewItems.value.splice(idx, 1);
    excludedCount.value++;
    if (reviewItems.value.length === 0) handleClose();
    return;
  }

  // Prevent duplicate concurrent requests
  if (isDiscarding.value[item.id] || isCommitting.value) return;

  isDiscarding.value[item.id] = true;
  reviewError.value = null;
  uploadError.value = null;

  try {
    await api.discardStagingItem(item.id);
    reviewItems.value.splice(idx, 1);
    excludedCount.value++;
    await stagingStore.fetchCount();
    await Promise.all([
      stagingStore.fetchItems(),
      stagingStore.fetchSuggestions(),
    ]);
    if (reviewItems.value.length === 0) {
      handleClose();
    }
  } catch (err: any) {
    reviewError.value = err.message || 'Failed to exclude candidate from queue.';
    uploadError.value = reviewError.value;
  } finally {
    delete isDiscarding.value[item.id];
  }
}

async function excludeAsDuplicate(item: any, idx: number) {
  await discardItemFromStaging(item, idx);
}

async function excludeItem(item: any, idx: number) {
  await discardItemFromStaging(item, idx);
}

// Row-level "Approve & Next"
async function approveRowAndNext(item: any, idx: number) {
  if (!isRowValid(item)) {
    reviewError.value = `Row #${idx + 1} is missing a required date, amount, or transfer destination.`;
    return;
  }
  if (!importData.value) return;

  isRowApproving.value[item.id] = true;
  reviewError.value = null;

  try {
    const payload: UnifiedImportCommitPayload = {
      batch_id: importData.value.batch_id,
      action: 'approve_selected',
      items: [{
        id: item.id,
        merchant: item.merchant_input.trim() || null,
        amount: Number(item.amount_input),
        transaction_date: item.date_input ? `${item.date_input}T12:00:00Z` : null,
        account_id: item.account_id,
        destination_account_id: item.destination_account_id,
        transaction_type: item.transaction_type,
        category_id: item.category_id,
        category_name: item.category_name.trim() || null,
        expense_nature: item.expense_nature,
        notes: item.notes.trim() || null,
        original_amount: item.original_amount,
        original_currency: item.original_currency
      }]
    };

    await api.commitUnifiedImport(payload);
    alreadyAddedCount.value++;
    reviewItems.value.splice(idx, 1);
    await Promise.all([
      accountsStore.loadData(),
      transactionsStore.loadTransactions(),
      stagingStore.fetchCount(),
      stagingStore.fetchItems(),
      stagingStore.fetchSuggestions(),
    ]);

    if (reviewItems.value.length === 0) {
      handleClose();
    } else {
      const nextIdx = Math.min(idx, reviewItems.value.length - 1);
      scrollToItem(nextIdx);
    }
  } catch (err: any) {
    reviewError.value = err.message || 'Failed to approve transaction.';
  } finally {
    delete isRowApproving.value[item.id];
  }
}

function skipItem(idx: number) {
  const nextIdx = idx + 1 < reviewItems.value.length ? idx + 1 : 0;
  scrollToItem(nextIdx);
}

// Manual Split Modal State & Handlers
const isSplitModalOpen = ref(false);
const splittingItem = ref<any>(null);
const splittingItemIndex = ref<number>(-1);

function openSplitModal(item: any, idx: number) {
  splittingItem.value = item;
  splittingItemIndex.value = idx;
  isSplitModalOpen.value = true;
}

async function handleSplitSuccess(payload: {
  action: 'queued' | 'approved';
  parentId: number;
  createdItems: any[];
  transactionIds: number[];
  accountId?: number | null;
  merchant?: string;
  date?: string;
}) {
  if (splittingItemIndex.value === -1) return;

  if (payload.action === 'approved') {
    alreadyAddedCount.value += payload.transactionIds.length;
    reviewItems.value.splice(splittingItemIndex.value, 1);
    await Promise.all([
      accountsStore.loadData(),
      transactionsStore.loadTransactions(),
      stagingStore.fetchCount(),
      stagingStore.fetchItems(),
      stagingStore.fetchSuggestions(),
    ]);

    if (reviewItems.value.length === 0) {
      handleClose();
    }
  } else if (payload.action === 'queued') {
    const parent = splittingItem.value;
    const resolvedAccountId = payload.accountId !== undefined ? payload.accountId : parent.account_id;
    const resolvedMerchant = payload.merchant || parent.merchant_input;
    const resolvedDate = payload.date ? payload.date.substring(0, 10) : parent.date_input;

    const newReviewRows = (payload.createdItems || []).map((c: any) => ({
      id: c.id,
      date_input: c.extracted_date ? c.extracted_date.substring(0, 10) : resolvedDate,
      merchant_input: c.extracted_merchant || resolvedMerchant,
      amount_input: c.extracted_amount_pence ? (c.extracted_amount_pence / 100).toFixed(2) : '',
      account_id: c.suggested_account_id != null ? c.suggested_account_id : resolvedAccountId,
      destination_account_id: null,
      transaction_type: 'expense' as TransactionType,
      direction_uncertain: false,
      direction_evidence: null,
      category_id: c.suggested_category_id != null ? c.suggested_category_id : null,
      category_name: c.suggested_category_name || '',
      expense_nature: (c.suggested_expense_nature || 'unclassified') as ExpenseNature,
      is_nature_manually_overridden: false,
      notes: c.notes || '',
      currency: c.currency || parent.currency || 'GBP',
      original_amount: c.original_amount,
      original_currency: c.original_currency,
      currency_conflict: false,
      is_potential_duplicate: false,
      duplicate_matches: [],
      missing_fields: [] as string[],
      date_uncertain: false,
      merchant_uncertain: false,
      account_match_reason: parent.account_match_reason,
      category_match_reason: c.category_match_reason,
      is_split: true,
      split_parent_id: payload.parentId
    }));

    reviewItems.value.splice(splittingItemIndex.value, 1, ...newReviewRows);
    await stagingStore.fetchCount();
  }

  isSplitModalOpen.value = false;
  splittingItem.value = null;
  splittingItemIndex.value = -1;
}

function scrollToItem(idx: number) {
  const el = document.getElementById(`review-item-${idx}`);
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}

// "Apply to Similar..." feature
const isSimilarModalOpen = ref(false);
const similarSourceItem = ref<any>(null);
const similarApplyType = ref(true);
const similarApplyCategory = ref(true);
const similarApplyAccount = ref(true);
const similarApplyNature = ref(true);
const similarRememberFuture = ref(false); // Unchecked by default for safety!
const similarMatches = ref<Array<{ item: any; selected: boolean }>>([]);

const selectedSimilarCount = computed(() => {
  return similarMatches.value.filter(m => m.selected).length;
});

const allSimilarSelected = computed(() => {
  return similarMatches.value.length > 0 && similarMatches.value.every(m => m.selected);
});

function toggleAllSimilarSelection() {
  const target = !allSimilarSelected.value;
  for (const m of similarMatches.value) {
    m.selected = target;
  }
}

function normalizeMerchant(merchant: string): string {
  if (!merchant) return '';
  const noise = new Set([
    'ltd', 'limited', 'inc', 'incorporated', 'corp', 'corporation', 'llc', 'plc',
    'stores', 'store', 'supermarket', 'express', 'local', 'uk', 'online',
    'retail', 'shop', 'com', 'gb', 'london', 'vendor', 'services', 'service',
    'group', 'holdings', 'enterprises', 'direct', 'bill', 'billing'
  ]);
  const cleaned = merchant.toLowerCase().replace(/[^a-z0-9\s]/g, ' ');
  const tokens = cleaned.split(/\s+/).filter(Boolean);
  const filtered = tokens.filter(t => !noise.has(t));
  return (filtered.length > 0 ? filtered : tokens).join(' ');
}

function openApplyToSimilar(sourceItem: any) {
  similarSourceItem.value = sourceItem;
  similarApplyType.value = true;
  similarApplyCategory.value = Boolean(sourceItem.category_id);
  similarApplyAccount.value = Boolean(sourceItem.account_id);
  similarApplyNature.value = Boolean(sourceItem.expense_nature && sourceItem.expense_nature !== 'unclassified');
  similarRememberFuture.value = false;

  const srcNorm = normalizeMerchant(sourceItem.merchant_input);
  const matches: Array<{ item: any; selected: boolean }> = [];

  for (const it of reviewItems.value) {
    if (it.id === sourceItem.id) continue;
    const itNorm = normalizeMerchant(it.merchant_input);
    let isMatch = false;
    if (srcNorm && itNorm) {
      if (srcNorm === itNorm) {
        isMatch = true;
      } else if (srcNorm.length >= 4 && itNorm.length >= 4 && (srcNorm.includes(itNorm) || itNorm.includes(srcNorm))) {
        isMatch = true;
      }
    } else if (sourceItem.merchant_input && it.merchant_input && sourceItem.merchant_input.trim().toLowerCase() === it.merchant_input.trim().toLowerCase()) {
      isMatch = true;
    }
    if (isMatch) {
      matches.push({ item: it, selected: true });
    }
  }

  similarMatches.value = matches;
  isSimilarModalOpen.value = true;
}

function applyToSimilarConfirm() {
  const src = similarSourceItem.value;
  if (!src) return;

  const selectedMatches = similarMatches.value.filter(m => m.selected);
  for (const match of selectedMatches) {
    const it = match.item;
    if (similarApplyType.value) {
      it.transaction_type = src.transaction_type;
      it.direction_uncertain = false;
      it.missing_fields = it.missing_fields.filter((f: string) => f !== 'transaction_type');
      reconcileCategoryForType(it);
    }
    if (similarApplyCategory.value) {
      if (isCategoryCompatibleWithTransaction(transactionsStore.categories, src.category_id, it.transaction_type)) {
        it.category_id = src.category_id;
        it.category_name = src.category_name;
        it.category_cleared_notice = null;
        it.category_match_reason = `Matched similar merchant "${src.merchant_input}"`;
      }
    }
    if (similarApplyAccount.value) {
      it.account_id = src.account_id;
      it.account_match_reason = `Matched similar merchant "${src.merchant_input}"`;
    }
    if (similarApplyNature.value && it.transaction_type === 'expense') {
      it.expense_nature = src.expense_nature;
      it.is_nature_manually_overridden = true;
    }
  }

  // If user explicitly checked remember for future imports and account is assigned
  if (similarRememberFuture.value && src.account_id && src.merchant_input) {
    api.saveAccountAssociation(src.merchant_input.trim(), src.account_id).catch(() => {});
  }

  isSimilarModalOpen.value = false;
}

function resetToUpload() {
  stage.value = 'upload';
  importData.value = null;
  reviewItems.value = [];
  uploadError.value = null;
  reviewError.value = null;
  isDiscarding.value = {};
  isRowApproving.value = {};
  isCommitting.value = false;
  commitAction.value = null;
  alreadyAddedCount.value = 0;
  excludedCount.value = 0;
  isSimilarModalOpen.value = false;
  similarSourceItem.value = null;
}

function handleClose() {
  resetToUpload();
  emit('close');
}

const canApproveAll = computed(() => {
  return reviewItems.value.length > 0 && reviewItems.value.every(isRowValid);
});

// Partial progressive commit: Add Reviewed to Ledger (X)
async function handleApproveReviewed() {
  if (!importData.value || readyItems.value.length === 0 || isCommitting.value || isAnyDiscarding.value) return;
  isCommitting.value = true;
  commitAction.value = 'approve_reviewed';
  reviewError.value = null;
  uploadError.value = null;

  const itemsToCommit = readyItems.value;
  try {
    const payload: UnifiedImportCommitPayload = {
      batch_id: importData.value.batch_id,
      action: 'approve_selected',
      items: itemsToCommit.map(it => ({
        id: it.id,
        merchant: it.merchant_input.trim() || null,
        amount: Number(it.amount_input),
        transaction_date: it.date_input ? `${it.date_input}T12:00:00Z` : null,
        account_id: it.account_id,
        destination_account_id: it.destination_account_id,
        transaction_type: it.transaction_type,
        category_id: it.category_id,
        category_name: it.category_name.trim() || null,
        expense_nature: it.expense_nature,
        notes: it.notes.trim() || null,
        original_amount: it.original_amount,
        original_currency: it.original_currency
      }))
    };

    const res = await api.commitUnifiedImport(payload);
    alreadyAddedCount.value += itemsToCommit.length;

    // Remove committed items from reviewItems
    const committedIds = new Set(itemsToCommit.map(i => i.id));
    reviewItems.value = reviewItems.value.filter(it => !committedIds.has(it.id));

    await Promise.all([
      accountsStore.loadData(),
      transactionsStore.loadTransactions(),
      stagingStore.fetchCount(),
      stagingStore.fetchItems(),
      stagingStore.fetchSuggestions(),
    ]);

    if (reviewItems.value.length === 0) {
      emit('imported', res);
      handleClose();
    }
  } catch (err: any) {
    reviewError.value = err.message || 'Failed to approve reviewed transactions.';
    uploadError.value = reviewError.value;
  } finally {
    isCommitting.value = false;
    commitAction.value = null;
  }
}

async function handleApproveAll() {
  if (!importData.value || !canApproveAll.value || isCommitting.value || isAnyDiscarding.value) return;
  isCommitting.value = true;
  commitAction.value = 'approve';
  reviewError.value = null;
  uploadError.value = null;

  try {
    const payload: UnifiedImportCommitPayload = {
      batch_id: importData.value.batch_id,
      action: 'approve_all',
      items: reviewItems.value.map(it => ({
        id: it.id,
        merchant: it.merchant_input.trim() || null,
        amount: Number(it.amount_input),
        transaction_date: it.date_input ? `${it.date_input}T12:00:00Z` : null,
        account_id: it.account_id,
        destination_account_id: it.destination_account_id,
        transaction_type: it.transaction_type,
        category_id: it.category_id,
        category_name: it.category_name.trim() || null,
        expense_nature: it.expense_nature,
        notes: it.notes.trim() || null,
        original_amount: it.original_amount,
        original_currency: it.original_currency
      }))
    };

    const res = await api.commitUnifiedImport(payload);
    await Promise.all([
      accountsStore.loadData(),
      transactionsStore.loadTransactions(),
      stagingStore.fetchCount(),
      stagingStore.fetchItems(),
      stagingStore.fetchSuggestions(),
    ]);
    emit('imported', res);
    handleClose();
  } catch (err: any) {
    reviewError.value = err.message || 'Failed to approve transactions.';
    uploadError.value = reviewError.value;
  } finally {
    isCommitting.value = false;
    commitAction.value = null;
  }
}

async function handleQueueAll() {
  if (!importData.value || isCommitting.value || isAnyDiscarding.value) return;
  isCommitting.value = true;
  commitAction.value = 'queue';
  reviewError.value = null;
  uploadError.value = null;

  try {
    const payload: UnifiedImportCommitPayload = {
      batch_id: importData.value.batch_id,
      action: 'queue_all',
      items: reviewItems.value.map(it => ({
        id: it.id,
        merchant: it.merchant_input.trim() || null,
        amount: it.amount_input ? Number(it.amount_input) : null,
        transaction_date: it.date_input ? `${it.date_input}T12:00:00Z` : null,
        account_id: it.account_id,
        destination_account_id: it.destination_account_id,
        transaction_type: it.transaction_type,
        category_id: it.category_id,
        category_name: it.category_name.trim() || null,
        expense_nature: it.expense_nature,
        notes: it.notes.trim() || null,
        original_amount: it.original_amount,
        original_currency: it.original_currency
      }))
    };

    await api.commitUnifiedImport(payload);
    await Promise.all([
      stagingStore.fetchCount(),
      stagingStore.fetchItems(),
      stagingStore.fetchSuggestions(),
    ]);
    emit('imported', { queued: true });
    handleClose();
  } catch (err: any) {
    reviewError.value = err.message || 'Failed to queue items.';
    uploadError.value = reviewError.value;
  } finally {
    isCommitting.value = false;
    commitAction.value = null;
  }
}

async function handleDiscardAll() {
  if (!importData.value) {
    handleClose();
    return;
  }
  if (isCommitting.value || isAnyDiscarding.value) return;

  isCommitting.value = true;
  commitAction.value = 'discard';
  reviewError.value = null;
  uploadError.value = null;

  try {
    await api.commitUnifiedImport({
      batch_id: importData.value.batch_id,
      action: 'discard_all',
      items: reviewItems.value.map(it => ({ id: it.id }))
    });
    await stagingStore.fetchCount();
    await Promise.all([
      stagingStore.fetchItems(),
      stagingStore.fetchSuggestions(),
    ]);
    handleClose();
  } catch (err: any) {
    reviewError.value = err.message || 'Failed to discard batch.';
    uploadError.value = reviewError.value;
  } finally {
    isCommitting.value = false;
    commitAction.value = null;
  }
}

function getDocumentBadgeClass(docType: string): string {
  switch (docType) {
    case 'receipt':
      return 'bg-blue-100 dark:bg-blue-950 text-blue-800 dark:text-blue-300';
    case 'statement':
      return 'bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300';
    case 'statement_screenshot':
      return 'bg-purple-100 dark:bg-purple-950 text-purple-800 dark:text-purple-300';
    default:
      return 'bg-amber-100 dark:bg-amber-950 text-amber-800 dark:text-amber-300';
  }
}

function getCurrencySymbol(curr: string): string {
  switch (curr) {
    case 'GBP': return '£';
    case 'USD': return '$';
    case 'EUR': return '€';
    case 'JPY': return '¥';
    default: return curr || '£';
  }
}

function formatFileSize(bytes: number): string {
  if (!bytes) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}
</script>
