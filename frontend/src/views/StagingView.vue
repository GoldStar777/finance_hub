<template>
  <div class="space-y-6 animate-fadeIn pb-12">
    
    <!-- Top Action Bar -->
    <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
      <div>
        <h1 class="text-xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center space-x-2.5">
          <span>Review Desk</span>
          <span 
            v-if="stagingStore.pendingCount > 0" 
            class="px-2 py-0.5 rounded-full text-xs font-mono font-semibold bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300">
            {{ stagingStore.pendingCount }} pending
          </span>
        </h1>
        <p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
          Review, correct, and approve transactions extracted from statements and receipts before permanent entry.
        </p>
      </div>

      <!-- Action Buttons -->
      <div class="flex flex-wrap items-center gap-2 shrink-0">
        <router-link
          to="/review"
          data-testid="queue-open-review-link"
          class="px-3 py-1.5 rounded-full border border-indigo-200 dark:border-indigo-800 bg-indigo-50/70 dark:bg-indigo-950/40 text-xs font-semibold text-indigo-700 dark:text-indigo-200 hover:opacity-90 transition">
          Data Quality &amp; Review &rarr;
        </router-link>

        <button
          @click="isUnifiedImportOpen = true"
          class="px-4 py-1.5 rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 text-xs font-semibold hover:opacity-90 transition shadow-sm flex items-center space-x-1.5">
          <span>+ Import (Receipt, Statement, Screenshot)</span>
        </button>

        <button
          @click="isImportModalOpen = true"
          class="px-3 py-1.5 rounded-full border border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface hover:bg-slate-100 dark:hover:bg-slate-800 transition text-xs font-semibold text-slate-700 dark:text-slate-300 flex items-center space-x-1"
          title="Advanced CSV statement mapper with custom column mapping">
          <span>CSV Mapper</span>
        </button>
      </div>
    </div>

    <!-- Filter & Batch Action Bar -->
    <div class="p-3.5 rounded-2xl border border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface flex flex-wrap items-center justify-between gap-3 shadow-xs">
      
      <!-- Left Filters -->
      <div class="flex items-center space-x-2 text-xs">
        <button
          v-for="src in sourceFilters"
          :key="src.value"
          @click="setSourceFilter(src.value)"
          class="px-3 py-1 rounded-full font-semibold transition"
          :class="stagingStore.sourceFilter === src.value
            ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-900'
            : 'text-slate-500 hover:text-slate-900 dark:hover:text-white'">
          {{ src.label }}
        </button>

        <span class="text-slate-300 dark:text-slate-700 font-thin">|</span>

        <!-- Status Filter -->
        <button
          @click="toggleStatusFilter"
          class="text-xs text-slate-500 hover:text-slate-900 dark:hover:text-white font-medium">
          Showing: <span class="font-bold uppercase">{{ stagingStore.statusFilter }}</span>
        </button>
      </div>

      <!-- Right Batch Actions (When items selected) -->
      <div v-if="stagingStore.selectedIds.length > 0" class="flex items-center space-x-2">
        <span class="text-xs text-slate-500 font-mono">
          {{ stagingStore.selectedIds.length }} selected
        </span>

        <button
          @click="handleBatchApprove(false)"
          :disabled="stagingStore.loading"
          class="px-3 py-1 rounded-full bg-emerald-600 text-white text-xs font-semibold hover:bg-emerald-500 transition shadow-xs flex items-center space-x-1">
          <span>Approve Clean</span>
        </button>

        <button
          v-if="selectedDuplicatesCount > 0"
          @click="handleBatchApprove(true)"
          :disabled="stagingStore.loading"
          class="px-3 py-1 rounded-full bg-amber-600 text-white text-xs font-semibold hover:bg-amber-500 transition shadow-xs"
          title="Approve all selected items including flagged duplicates">
          <span>Approve All (Incl. {{ selectedDuplicatesCount }} Duplicates)</span>
        </button>

        <button
          @click="handleBatchReject"
          :disabled="stagingStore.loading"
          class="px-3 py-1 rounded-full border border-rose-300 dark:border-rose-900 text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/40 text-xs font-semibold transition">
          Discard
        </button>
      </div>
    </div>

    <!-- Error Banner -->
    <div v-if="stagingStore.error" class="p-3 rounded-xl border border-rose-200 dark:border-rose-900 bg-rose-50 dark:bg-rose-950/40 text-rose-600 dark:text-rose-400 text-xs flex items-center justify-between">
      <span>{{ stagingStore.error }}</span>
      <button @click="stagingStore.error = null" class="text-rose-600 font-bold">&times;</button>
    </div>

    <!-- Advisory Refinement Suggestions Card -->
    <div 
      v-if="stagingStore.duplicateSuggestions.length > 0 || stagingStore.transferSuggestions.length > 0"
      class="p-4 rounded-2xl border border-indigo-200 dark:border-indigo-900/80 bg-indigo-50/40 dark:bg-indigo-950/20 shadow-xs space-y-4 animate-fadeIn">
      
      <!-- Suggestions Header -->
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div class="flex items-start sm:items-center space-x-2.5">
          <div class="w-8 h-8 rounded-xl bg-indigo-100 dark:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300 flex items-center justify-center text-base shrink-0 font-bold">
            💡
          </div>
          <div>
            <div class="flex items-center space-x-2">
              <h2 class="text-sm font-bold text-slate-900 dark:text-white">
                Advisory Refinement Suggestions
              </h2>
              <span class="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-indigo-200 text-indigo-900 dark:bg-indigo-900/80 dark:text-indigo-200">
                {{ stagingStore.duplicateSuggestions.length + stagingStore.transferSuggestions.length }} suggestions
              </span>
            </div>
            <p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              Explainable, strictly local suggestions to streamline duplicate handling and transfer pairing. Records are only modified upon your confirmation.
            </p>
          </div>
        </div>

        <!-- Controls: Tabs + Collapse -->
        <div class="flex items-center space-x-2 shrink-0">
          <div class="inline-flex rounded-xl border border-indigo-200 dark:border-indigo-900 bg-white/80 dark:bg-slate-900/80 p-0.5 text-xs font-semibold">
            <button
              v-if="stagingStore.duplicateSuggestions.length > 0"
              type="button"
              @click="activeSuggestionTab = 'duplicates'"
              class="px-3 py-1 rounded-lg transition flex items-center space-x-1.5"
              :class="activeSuggestionTab === 'duplicates'
                ? 'bg-indigo-600 text-white shadow-xs'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'">
              <span>Duplicates</span>
              <span class="px-1.5 py-0.2 rounded-full text-[10px] font-mono bg-white/20 text-white" v-if="activeSuggestionTab === 'duplicates'">
                {{ stagingStore.duplicateSuggestions.length }}
              </span>
              <span class="text-[10px] font-mono text-slate-400" v-else>
                ({{ stagingStore.duplicateSuggestions.length }})
              </span>
            </button>
            <button
              v-if="stagingStore.transferSuggestions.length > 0"
              type="button"
              @click="activeSuggestionTab = 'transfers'"
              class="px-3 py-1 rounded-lg transition flex items-center space-x-1.5"
              :class="activeSuggestionTab === 'transfers'
                ? 'bg-indigo-600 text-white shadow-xs'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'">
              <span>Transfers</span>
              <span class="px-1.5 py-0.2 rounded-full text-[10px] font-mono bg-white/20 text-white" v-if="activeSuggestionTab === 'transfers'">
                {{ stagingStore.transferSuggestions.length }}
              </span>
              <span class="text-[10px] font-mono text-slate-400" v-else>
                ({{ stagingStore.transferSuggestions.length }})
              </span>
            </button>
          </div>

          <button
            type="button"
            @click="isSuggestionsCollapsed = !isSuggestionsCollapsed"
            class="p-1.5 rounded-lg border border-indigo-200 dark:border-indigo-900 text-slate-500 hover:text-slate-800 dark:hover:text-white transition"
            :title="isSuggestionsCollapsed ? 'Expand suggestions' : 'Collapse suggestions'">
            <span>{{ isSuggestionsCollapsed ? '▼' : '▲' }}</span>
          </button>
        </div>
      </div>

      <!-- Suggestion Cards Container -->
      <div v-if="!isSuggestionsCollapsed" class="space-y-3 pt-2 border-t border-indigo-100 dark:border-indigo-900/50">
        
        <!-- Duplicates Tab -->
        <div v-if="activeSuggestionTab === 'duplicates'" class="space-y-3">
          <div 
            v-for="sug in stagingStore.duplicateSuggestions" 
            :key="sug.id"
            class="p-3.5 rounded-xl border border-brand-border dark:border-brand-darkborder bg-white dark:bg-brand-darksurface shadow-xs space-y-3">
            
            <div class="flex items-center justify-between">
              <div class="flex items-center space-x-2">
                <span class="px-2 py-0.5 rounded-md text-[10px] font-mono uppercase font-semibold bg-amber-100 dark:bg-amber-950/60 text-amber-800 dark:text-amber-300">
                  Potential Duplicate
                </span>
                <span class="text-xs text-slate-500 font-medium">
                  {{ sug.subtype === 'staging_ledger' ? 'Matches committed ledger transaction' : 'Matches another pending staging item' }}
                </span>
              </div>
              <button 
                type="button"
                @click="handleDismissSuggestion(sug.id)"
                class="text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 font-medium transition"
                title="Dismiss suggestion for this profile">
                Dismiss
              </button>
            </div>

            <!-- Comparison Grid -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
              <!-- Candidate in Staging -->
              <div class="p-3 rounded-lg border border-amber-200 dark:border-amber-900/50 bg-amber-50/30 dark:bg-amber-950/20 space-y-1.5 text-xs">
                <div class="flex items-center justify-between text-[11px] font-semibold text-amber-900 dark:text-amber-300">
                  <span>Candidate in Queue (Staging #{{ sug.record_a.id }})</span>
                  <span class="font-mono font-bold">{{ sug.record_a.formatted_amount }}</span>
                </div>
                <div class="font-bold text-slate-900 dark:text-white">{{ sug.record_a.merchant }}</div>
                <div class="flex items-center justify-between text-[11px] text-slate-500">
                  <span>Date: {{ sug.record_a.date }}</span>
                  <span>Account: {{ sug.record_a.account_name || 'Unassigned' }}</span>
                </div>
                <div v-if="sug.record_a.source_filename" class="text-[10px] text-slate-400 truncate">
                  File: {{ sug.record_a.source_filename }}
                </div>
              </div>

              <!-- Matched Record -->
              <div class="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-850 space-y-1.5 text-xs">
                <div class="flex items-center justify-between text-[11px] font-semibold text-slate-600 dark:text-slate-400">
                  <span>
                    {{ sug.record_b.kind === 'ledger' ? 'Committed Ledger Transaction #' + sug.record_b.id : 'Pending Queue Item #' + sug.record_b.id }}
                  </span>
                  <span class="font-mono font-bold">{{ sug.record_b.formatted_amount }}</span>
                </div>
                <div class="font-bold text-slate-900 dark:text-white">{{ sug.record_b.merchant }}</div>
                <div class="flex items-center justify-between text-[11px] text-slate-500">
                  <span>Date: {{ sug.record_b.date }}</span>
                  <span>Account: {{ sug.record_b.account_name || 'Unassigned' }}</span>
                </div>
              </div>
            </div>

            <!-- Reasons list -->
            <div class="flex flex-wrap items-center gap-1.5 pt-1 text-[11px] text-slate-600 dark:text-slate-400">
              <span class="font-semibold text-slate-500 text-[10px] uppercase font-mono mr-1">Evidence:</span>
              <span 
                v-for="(reason, rIdx) in sug.reasons" 
                :key="rIdx"
                class="px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 font-medium">
                {{ reason }}
              </span>
            </div>

            <!-- Actions Bar -->
            <div class="flex items-center justify-end space-x-2 pt-2 border-t border-slate-100 dark:border-slate-800">
              <button
                type="button"
                @click="handleDismissSuggestion(sug.id)"
                class="px-3 py-1 rounded-full border border-brand-border dark:border-brand-darkborder text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-semibold transition">
                Keep Both
              </button>
              <button
                type="button"
                @click="handleConfirmDuplicate(sug)"
                class="px-3.5 py-1 rounded-full bg-rose-600 text-white hover:bg-rose-500 text-xs font-semibold transition shadow-xs flex items-center space-x-1">
                <span>Exclude Candidate (#{{ sug.record_a.id }})</span>
              </button>
            </div>
          </div>
        </div>

        <!-- Transfers Tab -->
        <div v-if="activeSuggestionTab === 'transfers'" class="space-y-3">
          <div 
            v-for="sug in stagingStore.transferSuggestions" 
            :key="sug.id"
            class="p-3.5 rounded-xl border border-brand-border dark:border-brand-darkborder bg-white dark:bg-brand-darksurface shadow-xs space-y-3">
            
            <div class="flex items-center justify-between">
              <div class="flex items-center space-x-2">
                <span class="px-2 py-0.5 rounded-md text-[10px] font-mono uppercase font-semibold bg-indigo-100 dark:bg-indigo-950/60 text-indigo-800 dark:text-indigo-300">
                  Potential Transfer
                </span>
                <span class="text-xs text-slate-500 font-medium">
                  Matching outflow and inflow across accounts (impact £0 on cash flow)
                </span>
              </div>
              <button 
                type="button"
                @click="handleDismissSuggestion(sug.id)"
                class="text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 font-medium transition"
                title="Dismiss suggestion for this profile">
                Dismiss
              </button>
            </div>

            <!-- Flow Container -->
            <div class="grid grid-cols-1 md:grid-cols-11 gap-2 items-center text-xs">
              <!-- Outflow -->
              <div class="md:col-span-5 p-3 rounded-lg border border-rose-200 dark:border-rose-900/50 bg-rose-50/30 dark:bg-rose-950/20 space-y-1">
                <div class="flex items-center justify-between text-[11px] font-semibold text-rose-800 dark:text-rose-300">
                  <span>Source (Outflow): {{ sug.source_record.account_name }}</span>
                  <span class="font-mono font-bold">-{{ sug.source_record.formatted_amount }}</span>
                </div>
                <div class="font-bold text-slate-900 dark:text-white">{{ sug.source_record.merchant }}</div>
                <div class="flex items-center justify-between text-[11px] text-slate-500">
                  <span>Date: {{ sug.source_record.date }}</span>
                  <span class="font-mono">{{ sug.source_record.kind === 'ledger' ? 'Ledger #' + sug.source_record.id : 'Staging #' + sug.source_record.id }}</span>
                </div>
                <div v-if="sug.source_record.source_filename" class="text-[10px] text-slate-400 truncate">
                  Source: {{ sug.source_record.source_filename }}
                </div>
              </div>

              <!-- Arrow -->
              <div class="md:col-span-1 text-center font-bold text-slate-400 text-base">
                ➔
              </div>

              <!-- Inflow -->
              <div class="md:col-span-5 p-3 rounded-lg border border-emerald-200 dark:border-emerald-900/50 bg-emerald-50/30 dark:bg-emerald-950/20 space-y-1">
                <div class="flex items-center justify-between text-[11px] font-semibold text-emerald-800 dark:text-emerald-300">
                  <span>Destination (Inflow): {{ sug.destination_record.account_name }}</span>
                  <span class="font-mono font-bold">+{{ sug.destination_record.formatted_amount }}</span>
                </div>
                <div class="font-bold text-slate-900 dark:text-white">{{ sug.destination_record.merchant }}</div>
                <div class="flex items-center justify-between text-[11px] text-slate-500">
                  <span>Date: {{ sug.destination_record.date }}</span>
                  <span class="font-mono">{{ sug.destination_record.kind === 'ledger' ? 'Ledger #' + sug.destination_record.id : 'Staging #' + sug.destination_record.id }}</span>
                </div>
                <div v-if="sug.destination_record.source_filename" class="text-[10px] text-slate-400 truncate">
                  Source: {{ sug.destination_record.source_filename }}
                </div>
              </div>
            </div>

            <!-- Reasons list -->
            <div class="flex flex-wrap items-center gap-1.5 pt-1 text-[11px] text-slate-600 dark:text-slate-400">
              <span class="font-semibold text-slate-500 text-[10px] uppercase font-mono mr-1">Evidence:</span>
              <span 
                v-for="(reason, rIdx) in sug.reasons" 
                :key="rIdx"
                class="px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 font-medium">
                {{ reason }}
              </span>
            </div>

            <!-- Action Explanation -->
            <div 
              v-if="sug.action_explanation"
              class="p-2.5 rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-200/80 dark:border-slate-700/60 text-[11px] text-slate-600 dark:text-slate-300 leading-relaxed">
              <span class="font-semibold text-slate-800 dark:text-slate-200 mr-1">What confirming does:</span>
              <span>{{ sug.action_explanation }}</span>
            </div>

            <!-- Actions Bar -->
            <div class="flex items-center justify-end space-x-2 pt-2 border-t border-slate-100 dark:border-slate-800">
              <button
                type="button"
                @click="handleDismissSuggestion(sug.id)"
                class="px-3 py-1 rounded-full border border-brand-border dark:border-brand-darkborder text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-semibold transition">
                Keep Separate
              </button>
              <button
                type="button"
                @click="handleConfirmTransfer(sug)"
                class="px-3.5 py-1 rounded-full bg-indigo-600 text-white hover:bg-indigo-500 text-xs font-semibold transition shadow-xs flex items-center space-x-1">
                <span>Pair as Dual-Account Transfer</span>
              </button>
            </div>
          </div>
        </div>

      </div>
    </div>

    <!-- Review Queue Table -->
    <div class="rounded-2xl border border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface overflow-hidden shadow-xs">
      
      <!-- Table Header -->
      <div class="overflow-x-auto">
        <table class="w-full text-left border-collapse">
          <thead>
            <tr class="border-b border-brand-border dark:border-brand-darkborder bg-slate-50/50 dark:bg-slate-800/30 text-[11px] font-mono uppercase text-slate-500">
              <th class="py-3 px-4 w-10 text-center">
                <input 
                  type="checkbox" 
                  :checked="isAllSelected"
                  @change="handleToggleSelectAll"
                  class="rounded border-slate-300 text-slate-900 focus:ring-0" />
              </th>
              <th class="py-3 px-4">Date</th>
              <th class="py-3 px-4">Merchant / Narrative</th>
              <th class="py-3 px-4">Account</th>
              <th class="py-3 px-4">Category</th>
              <th class="py-3 px-4">Nature</th>
              <th class="py-3 px-4 text-right">Amount</th>
              <th class="py-3 px-4 text-center">Advisories</th>
              <th class="py-3 px-4 text-right">Actions</th>
            </tr>
          </thead>

          <tbody class="divide-y divide-brand-border dark:divide-brand-darkborder text-xs">
            <!-- Empty State -->
            <tr v-if="stagingStore.filteredItems.length === 0">
              <td colspan="9" class="py-16 text-center text-slate-400 space-y-2">
                <p class="font-medium text-slate-600 dark:text-slate-300">No transactions in the review queue</p>
                <p class="text-[11px]">Import a bank statement or upload receipt photos to begin reviewing.</p>
              </td>
            </tr>

            <!-- Item Rows -->
            <tr 
              v-for="item in stagingStore.filteredItems" 
              :key="item.id"
              class="hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition group"
              :class="[
                item.is_potential_duplicate ? 'bg-amber-50/20 dark:bg-amber-950/10' : '',
                highlightedItemId === item.id ? 'ring-2 ring-inset ring-indigo-500 bg-indigo-50/40 dark:bg-indigo-950/30' : ''
              ]">
              
              <!-- Checkbox -->
              <td class="py-3 px-4 text-center">
                <input 
                  type="checkbox" 
                  :checked="stagingStore.selectedIds.includes(item.id)"
                  @change="stagingStore.toggleSelect(item.id)"
                  class="rounded border-slate-300 text-slate-900 focus:ring-0" />
              </td>

              <!-- Date -->
              <td class="py-3 px-4 font-mono text-slate-600 dark:text-slate-300 whitespace-nowrap">
                <div class="flex items-center space-x-1.5">
                  <span v-if="item.extracted_date">{{ formatDate(item.extracted_date) }}</span>
                  <span v-else class="text-rose-500 font-semibold italic">Missing Date</span>
                  <span 
                    v-if="isItemPlanned(item)" 
                    data-testid="staging-item-planned-badge"
                    class="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border border-amber-300 dark:border-amber-800">
                    Planned
                  </span>
                </div>
              </td>

              <!-- Merchant / Narrative -->
              <td class="py-3 px-4 font-medium text-slate-900 dark:text-white max-w-xs">
                <div class="flex items-center space-x-2">
                  <!-- Receipt Thumbnail -->
                  <button 
                    v-if="item.receipt_url"
                    @click="previewReceiptImage = item.receipt_url"
                    class="w-6 h-6 rounded border border-brand-border dark:border-brand-darkborder overflow-hidden shrink-0 hover:opacity-80 transition"
                    title="View receipt image">
                    <img :src="item.receipt_url" class="w-full h-full object-cover" />
                  </button>

                  <div class="truncate">
                    <span v-if="item.extracted_merchant">{{ item.extracted_merchant }}</span>
                    <span v-else class="text-slate-400 italic">Merchant not recorded</span>
                    
                    <span v-if="item.transaction_type === 'transfer'" class="ml-1.5 px-1.5 py-0.2 rounded text-[10px] bg-sky-100 dark:bg-sky-950 text-sky-700 dark:text-sky-300 font-mono">
                      Transfer &rarr; {{ item.destination_account_name || 'Account' }}
                    </span>
                  </div>
                </div>
              </td>

              <!-- Account -->
              <td class="py-3 px-4 whitespace-nowrap">
                <span 
                  v-if="item.suggested_account_name"
                  class="inline-flex items-center space-x-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium"
                  :style="{ backgroundColor: `${item.suggested_account_color || '#3B82F6'}15`, color: item.suggested_account_color || '#3B82F6' }">
                  <span class="w-1.5 h-1.5 rounded-full" :style="{ backgroundColor: item.suggested_account_color || '#3B82F6' }"></span>
                  <span>{{ item.suggested_account_name }}</span>
                </span>
                <span v-else class="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800">Unassigned</span>
              </td>

              <!-- Category -->
              <td class="py-3 px-4 whitespace-nowrap">
                <span v-if="item.suggested_category_name" class="text-slate-600 dark:text-slate-300">
                  {{ item.suggested_category_name }}
                </span>
                <span v-else class="text-slate-400 italic">Uncategorized</span>
              </td>

              <!-- Nature (Fixed / Variable for Expense only) -->
              <td class="py-3 px-4 whitespace-nowrap font-mono text-[10px]">
                <template v-if="item.transaction_type === 'expense'">
                  <span 
                    v-if="item.suggested_expense_nature === 'fixed'"
                    class="px-1.5 py-0.5 rounded bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300">
                    Fixed
                  </span>
                  <span 
                    v-else-if="item.suggested_expense_nature === 'variable'"
                    class="px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-950 text-amber-700 dark:text-amber-300">
                    Variable
                  </span>
                  <span v-else class="text-slate-400">Unclassified</span>
                </template>
                <span v-else class="text-slate-400">&mdash;</span>
              </td>

              <!-- Amount -->
              <td class="py-3 px-4 text-right font-mono font-bold whitespace-nowrap">
                <div v-if="item.formatted_amount">
                  <span 
                    :class="[
                      stealthStore.isStealth ? 'filter blur-[5px]' : '',
                      item.transaction_type === 'income' ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-900 dark:text-white'
                    ]">
                    {{ item.transaction_type === 'income' ? '+' : '-' }}{{ item.formatted_amount }}
                  </span>
                </div>
                <div v-else-if="item.requires_base_amount" class="text-amber-600 dark:text-amber-400 font-semibold text-[11px]">
                  Requires Base Amount
                </div>
                <div v-else class="text-rose-500 font-semibold italic">Missing Amount</div>

                <div v-if="item.formatted_original_amount" class="text-[10px] font-mono font-normal text-slate-400 mt-0.5">
                  {{ item.formatted_original_amount }}
                </div>
              </td>

              <!-- Advisory Badges -->
              <td class="py-3 px-4 text-center whitespace-nowrap">
                <div class="inline-flex items-center space-x-1.5">
                  <!-- Duplicate Advisory Badge -->
                  <button 
                    v-if="item.is_potential_duplicate"
                    @click="activeDuplicateItem = item"
                    class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 hover:opacity-80 transition flex items-center space-x-1"
                    title="Click to review matched transaction">
                    <span>&#9888; Possible Duplicate</span>
                  </button>

                  <!-- Requires Base Amount Badge -->
                  <button
                    v-if="item.requires_base_amount"
                    @click="openEditModal(item)"
                    class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 hover:opacity-80 transition flex items-center space-x-1"
                    title="Foreign purchase needs the actual card/bank charge before approval">
                    <span>&#128177; Needs Base Charge</span>
                  </button>

                  <!-- Currency Conflict Badge -->
                  <span 
                    v-if="item.currency_conflict"
                    class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-rose-100 dark:bg-rose-950/60 text-rose-700 dark:text-rose-300 cursor-help"
                    :title="item.currency_conflict_message || 'Statement currency does not match account currency'">
                    &#128177; Currency Alert
                  </span>

                  <!-- OCR Uncertainty Badge -->
                  <span 
                    v-if="item.source_type === 'receipt_image' && (item.ocr_confidence === 0 || (!item.extracted_amount_pence && !item.original_amount))"
                    class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400"
                    title="Manual review required">
                    Manual Review
                  </span>

                  <!-- Anchor Disambiguation Badge -->
                  <button 
                    v-if="item.anchor_status"
                    type="button"
                    @click="toggleAnchorMode(item)"
                    class="px-2 py-0.5 rounded-full text-[10px] font-semibold flex items-center space-x-1 transition hover:opacity-80"
                    :class="item.anchor_mode === 'after_anchor' 
                      ? 'bg-indigo-100 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-900/40' 
                      : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700'"
                    :title="item.anchor_mode === 'after_anchor' ? 'Will adjust the current account balance forward. Click to mark as already reflected.' : (item.anchor_explanation || 'Already reflected in balance anchor. Click to change.')">
                    <span>⚓</span>
                    <span>{{ item.anchor_mode === 'after_anchor' ? 'Adjusts Balance' : 'Already in Anchor' }}</span>
                  </button>
                </div>
              </td>

              <!-- Row Action Buttons -->
              <td class="py-3 px-4 text-right whitespace-nowrap">
                <div class="inline-flex items-center space-x-1.5">
                  <button
                    @click="openEditModal(item)"
                    class="p-1 rounded text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition"
                    title="Edit transaction details">
                    Edit
                  </button>

                  <!-- Manual Expense Splitting Action -->
                  <button
                    v-if="item.transaction_type === 'expense' && (item.extracted_amount_pence || 0) > 0"
                    @click="openSplitModal(item)"
                    class="px-2 py-0.5 rounded-full border border-indigo-200 dark:border-indigo-800 bg-indigo-50/70 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 hover:bg-indigo-100 dark:hover:bg-indigo-900/60 transition text-[11px] font-semibold flex items-center space-x-1"
                    title="Split expense across multiple categories">
                    <span>✂️ Split</span>
                  </button>

                  <button
                    v-if="!item.requires_base_amount"
                    @click="handleApproveSingle(item)"
                    class="px-2.5 py-1 rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 hover:opacity-90 text-[11px] font-semibold transition shadow-xs"
                    title="Approve into ledger">
                    Approve
                  </button>
                  <button
                    v-else
                    @click="openEditModal(item)"
                    class="px-2.5 py-1 rounded-full bg-amber-600 text-white hover:bg-amber-500 text-[11px] font-semibold transition shadow-xs"
                    title="Enter posted base amount before approving">
                    Resolve
                  </button>

                  <button
                    @click="handleDiscardSingle(item)"
                    class="p-1 rounded text-slate-400 hover:text-rose-600 dark:hover:text-rose-400 transition"
                    title="Discard item">
                    &times;
                  </button>
                </div>
              </td>

            </tr>
          </tbody>
        </table>
      </div>

    </div>

    <!-- Duplicate Comparison Modal / Drawer -->
    <div v-if="activeDuplicateItem" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fadeIn">
      <div class="bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder rounded-2xl w-full max-w-lg shadow-2xl p-6 space-y-4">
        <div class="flex items-center justify-between">
          <h3 class="text-sm font-bold text-slate-900 dark:text-white flex items-center space-x-2">
            <span class="text-amber-500 font-bold">&#9888;</span>
            <span>Duplicate Advisory Review</span>
          </h3>
          <button @click="activeDuplicateItem = null" class="text-slate-400 hover:text-slate-600 text-lg leading-none">&times;</button>
        </div>

        <p class="text-xs text-slate-500">
          This record matches one or more transactions already recorded in your ledger. Review both items before deciding.
        </p>

        <!-- Candidate Staging Item -->
        <div class="p-3 rounded-xl border border-amber-200 dark:border-amber-900/40 bg-amber-50/40 dark:bg-amber-950/20 text-xs space-y-1">
          <span class="text-[10px] font-mono uppercase font-bold text-amber-700 dark:text-amber-400">Incoming Record (Review Queue)</span>
          <div class="flex justify-between font-medium text-slate-900 dark:text-white">
            <span>{{ activeDuplicateItem.extracted_merchant }}</span>
            <span class="font-mono font-bold">{{ activeDuplicateItem.formatted_amount }}</span>
          </div>
          <div class="text-[11px] text-slate-500">
            Date: {{ formatDate(activeDuplicateItem.extracted_date) }} &bull; Source: {{ activeDuplicateItem.source_type }}
          </div>
        </div>

        <!-- Matched Existing Transactions -->
        <div class="space-y-2">
          <span class="text-[10px] font-mono uppercase font-bold text-slate-400">Existing Ledger Transaction(s)</span>
          <div 
            v-for="m in activeDuplicateItem.duplicate_matches" 
            :key="m.id"
            class="p-3 rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50/50 dark:bg-slate-800/40 text-xs space-y-1">
            <div class="flex justify-between font-medium text-slate-900 dark:text-white">
              <span>{{ m.merchant }}</span>
              <span class="font-mono font-bold">{{ (m.amount_pence / 100).toFixed(2) }}</span>
            </div>
            <div class="text-[11px] text-slate-500">
              Date: {{ formatDate(m.transaction_date) }} &bull; Account: {{ m.account_name }}
            </div>
            <div class="pt-1 text-[10px] text-amber-600 dark:text-amber-400 flex flex-wrap gap-1">
              <span v-for="(reason, rIdx) in m.match_reasons" :key="rIdx" class="px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-950 font-mono">
                {{ reason }}
              </span>
            </div>
          </div>
        </div>

        <!-- Modal Actions -->
        <div class="pt-2 flex items-center justify-between">
          <button
            @click="handleDiscardDuplicate(activeDuplicateItem)"
            class="px-4 py-1.5 rounded-full border border-rose-300 dark:border-rose-900 text-rose-600 dark:text-rose-400 hover:bg-rose-50 text-xs font-semibold">
            Discard Duplicate
          </button>

          <button
            @click="handleApproveDuplicate(activeDuplicateItem)"
            class="px-4 py-1.5 rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 hover:opacity-90 text-xs font-semibold">
            Approve Anyway (Separate Charge)
          </button>
        </div>
      </div>
    </div>

    <!-- Edit Staging Item Modal -->
    <div v-if="editingItem" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fadeIn">
      <div class="bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder rounded-2xl w-full max-w-md shadow-2xl p-6 space-y-4">
        <div class="flex items-center justify-between border-b border-brand-border dark:border-brand-darkborder pb-3">
          <h3 class="text-sm font-bold text-slate-900 dark:text-white">
            Edit Transaction Details
          </h3>
          <button @click="editingItem = null" class="text-slate-400 hover:text-slate-600 text-lg leading-none">&times;</button>
        </div>

        <form @submit.prevent="saveEditedItem" class="space-y-3.5 text-xs">
          <!-- Foreign Info Banner if foreign origin -->
          <div v-if="editingItem?.requires_base_amount || editingItem?.original_currency" class="p-3 rounded-xl bg-amber-50/70 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/60 text-amber-900 dark:text-amber-200 space-y-1">
            <div class="font-semibold flex items-center justify-between">
              <span>Foreign Purchase Detected</span>
              <span class="font-mono text-xs">{{ editingItem.formatted_original_amount || (editingItem.original_amount + ' ' + (editingItem.original_currency || '')) }}</span>
            </div>
            <p class="text-[11px] text-amber-800/80 dark:text-amber-300/80">
              Please enter the exact posted {{ baseCurrencyCode }} amount billed by your bank or card to approve this transaction into the ledger.
            </p>
          </div>

          <!-- Merchant -->
          <div>
            <label class="block text-[10px] font-mono uppercase font-semibold text-slate-500 mb-1">Merchant / Narrative (Optional)</label>
            <input 
              v-model="editForm.merchant" 
              type="text" 
              placeholder="e.g. Tesco (leave blank if unrecorded)"
              class="w-full bg-slate-50 dark:bg-slate-800/60 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-slate-900 dark:text-white" />
          </div>

          <!-- Amount & Date -->
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-[10px] font-mono uppercase font-semibold text-slate-500 mb-1">Base Amount ({{ baseCurrencySymbol }}) *</label>
              <input 
                v-model.number="editForm.amount" 
                type="number" 
                step="0.01" 
                min="0.01"
                required
                placeholder="0.00"
                class="w-full bg-slate-50 dark:bg-slate-800/60 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-slate-900 dark:text-white font-mono font-bold" />
            </div>
            <div>
              <label class="block text-[10px] font-mono uppercase font-semibold text-slate-500 mb-1">Date *</label>
              <input 
                v-model="editForm.date" 
                type="date" 
                required
                class="w-full bg-slate-50 dark:bg-slate-800/60 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-slate-900 dark:text-white" />
            </div>
          </div>

          <!-- Transaction Type -->
          <div>
            <label class="block text-[10px] font-mono uppercase font-semibold text-slate-500 mb-1">Transaction Type</label>
            <select 
              v-model="editForm.transaction_type"
              class="w-full bg-slate-50 dark:bg-slate-800/60 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-slate-900 dark:text-white">
              <option value="expense">Expense (Outflow)</option>
              <option value="income">Income (Inflow)</option>
              <option value="transfer">Internal Transfer</option>
            </select>
          </div>

          <!-- Destination Account (If Transfer) -->
          <div v-if="editForm.transaction_type === 'transfer'">
            <label class="block text-[10px] font-mono uppercase font-semibold text-slate-500 mb-1">Destination Account *</label>
            <select 
              v-model="editForm.destination_account_id"
              required
              class="w-full bg-slate-50 dark:bg-slate-800/60 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-slate-900 dark:text-white">
              <option :value="null" disabled>Select destination account...</option>
              <option 
                v-for="acc in accountsStore.accounts.filter(a => a.id !== editForm.account_id)" 
                :key="acc.id" 
                :value="acc.id">
                {{ acc.name }}
              </option>
            </select>
          </div>

          <!-- Account Selector -->
          <div>
            <label class="block text-[10px] font-mono uppercase font-semibold text-slate-500 mb-1">
              Account {{ editForm.transaction_type === 'transfer' ? '*' : '(Optional)' }}
            </label>
            <select 
              v-model="editForm.account_id"
              class="w-full bg-slate-50 dark:bg-slate-800/60 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-slate-900 dark:text-white">
              <option :value="null">Unassigned (assign later)</option>
              <option v-for="acc in accountsStore.accounts" :key="acc.id" :value="acc.id">
                {{ acc.name }}
              </option>
            </select>
          </div>

          <!-- Category & Nature (If not transfer) -->
          <div v-if="editForm.transaction_type !== 'transfer'" class="grid gap-3" :class="editForm.transaction_type === 'expense' ? 'grid-cols-2' : 'grid-cols-1'">
            <div>
              <label class="block text-[10px] font-mono uppercase font-semibold text-slate-500 mb-1">
                {{ editForm.transaction_type === 'income' ? 'Income Category' : 'Expense Category' }}
              </label>
              <select
                v-model="editForm.category_name"
                class="w-full bg-slate-50 dark:bg-slate-800/60 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-slate-900 dark:text-white">
                <option value="">Uncategorised</option>
                <option v-for="cat in compatibleEditCategories" :key="cat.id" :value="cat.name">
                  {{ cat.name }}
                </option>
              </select>
              <p v-if="editCategoryClearedNotice" class="text-[10px] text-amber-600 dark:text-amber-400 mt-1">
                {{ editCategoryClearedNotice }}
              </p>
            </div>
            <div v-if="editForm.transaction_type === 'expense'">
              <label class="block text-[10px] font-mono uppercase font-semibold text-slate-500 mb-1">Expense Nature</label>
              <select 
                v-model="editForm.expense_nature"
                class="w-full bg-slate-50 dark:bg-slate-800/60 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-slate-900 dark:text-white">
                <option value="unclassified">Unclassified</option>
                <option value="fixed">Fixed</option>
                <option value="variable">Variable</option>
              </select>
            </div>
          </div>
          <p v-else-if="editCategoryClearedNotice" class="text-[11px] text-amber-600 dark:text-amber-400">
            {{ editCategoryClearedNotice }}
          </p>

          <!-- Anchor Treatment Selection -->
          <div v-if="editingItem.anchor_status" class="p-3 rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50/60 dark:bg-slate-800/30 space-y-1.5">
            <div class="flex items-center justify-between">
              <label class="block text-[10px] font-mono uppercase font-semibold text-slate-500">
                Balance Anchor Treatment
              </label>
              <span class="text-[10px] font-mono text-slate-400">
                {{ editingItem.anchor_status === 'after_anchor' ? 'Post-Anchor' : 'On/Pre-Anchor' }}
              </span>
            </div>
            <p class="text-[11px] text-slate-500 dark:text-slate-400">
              {{ editingItem.anchor_explanation }}
            </p>
            <div class="flex items-center space-x-4 pt-1">
              <label class="flex items-center space-x-1.5 text-xs text-slate-700 dark:text-slate-300 cursor-pointer">
                <input
                  type="radio"
                  v-model="editForm.anchor_mode"
                  value="already_reflected"
                  class="text-slate-900 focus:ring-0" />
                <span>Already in anchor balance</span>
              </label>
              <label class="flex items-center space-x-1.5 text-xs text-slate-700 dark:text-slate-300 cursor-pointer">
                <input
                  type="radio"
                  v-model="editForm.anchor_mode"
                  value="after_anchor"
                  class="text-slate-900 focus:ring-0" />
                <span>Applies after anchor</span>
              </label>
            </div>
          </div>

          <!-- Notes -->
          <div>
            <label class="block text-[10px] font-mono uppercase font-semibold text-slate-500 mb-1">Notes</label>
            <textarea 
              v-model="editForm.notes" 
              rows="2"
              class="w-full bg-slate-50 dark:bg-slate-800/60 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-slate-900 dark:text-white"></textarea>
          </div>

          <!-- Modal Footer -->
          <div class="pt-3 border-t border-brand-border dark:border-brand-darkborder flex justify-end space-x-2">
            <button
              type="button"
              @click="editingItem = null"
              class="px-4 py-1.5 rounded-full border border-brand-border dark:border-brand-darkborder text-slate-600 dark:text-slate-300">
              Cancel
            </button>
            <button
              type="submit"
              class="px-4 py-1.5 rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 font-semibold">
              Save Changes
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Receipt Lightbox Modal -->
    <div v-if="previewReceiptImage" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md animate-fadeIn" @click="previewReceiptImage = null">
      <div class="relative max-w-2xl max-h-[90vh] overflow-hidden rounded-2xl" @click.stop>
        <button 
          @click="previewReceiptImage = null"
          class="absolute top-3 right-3 w-8 h-8 rounded-full bg-slate-900/80 text-white flex items-center justify-center font-bold hover:bg-slate-900 transition">
          &times;
        </button>
        <img :src="previewReceiptImage" class="w-full h-auto max-h-[85vh] object-contain rounded-2xl" />
      </div>
    </div>

    <!-- Unified Import Modal -->
    <UnifiedImportModal 
      :is-open="isUnifiedImportOpen" 
      @close="isUnifiedImportOpen = false" 
      @imported="handleUnifiedImportFinished" />

    <!-- Statement Import Modal -->
    <ImportStatementModal 
      :is-open="isImportModalOpen" 
      @close="isImportModalOpen = false" 
      @imported="handleImportFinished" />

    <!-- Split Expense Modal -->
    <SplitExpenseModal
      :is-open="isSplitModalOpen"
      :item="splittingItem"
      :accounts="accountsStore.accounts"
      :categories="transactionsStore.categories"
      :base-currency="baseCurrencyCode"
      :base-currency-symbol="baseCurrencySymbol"
      :allow-immediate-approve="true"
      @close="isSplitModalOpen = false; splittingItem = null"
      @split-success="handleSplitSuccess" />

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { useRoute } from 'vue-router';
import { useStagingStore } from '../stores/staging';
import { useAccountsStore } from '../stores/accounts';
import { useTransactionsStore } from '../stores/transactions';
import { useStealthStore } from '../stores/stealth';
import { useSystemStore } from '../stores/system';
import ImportStatementModal from '../components/ImportStatementModal.vue';
import UnifiedImportModal from '../components/UnifiedImportModal.vue';
import SplitExpenseModal from '../components/SplitExpenseModal.vue';
import { filterCategoriesForTransactionType, expectedCategoryTypeForTransaction, getCategoryPurpose } from '../utils/categoryPurpose';
import type { StagingItem, ExpenseNature, TransactionType, ReviewDuplicateSuggestion, ReviewTransferSuggestion } from '../types';

const route = useRoute();
const stagingStore = useStagingStore();
const accountsStore = useAccountsStore();
const transactionsStore = useTransactionsStore();
const stealthStore = useStealthStore();
const systemStore = useSystemStore();

const highlightedItemId = ref<number | null>(null);

const baseCurrencySymbol = computed(() => systemStore.config?.base_currency_symbol || '£');
const baseCurrencyCode = computed(() => systemStore.config?.base_currency || 'GBP');

const isUnifiedImportOpen = ref(false);
const isImportModalOpen = ref(false);

const isSuggestionsCollapsed = ref(false);
const activeSuggestionTab = ref<'duplicates' | 'transfers'>('duplicates');

watch([() => stagingStore.duplicateSuggestions.length, () => stagingStore.transferSuggestions.length], ([dupCount, tfCount]) => {
  if (dupCount === 0 && tfCount > 0) {
    activeSuggestionTab.value = 'transfers';
  } else if (tfCount === 0 && dupCount > 0) {
    activeSuggestionTab.value = 'duplicates';
  }
}, { immediate: true });

async function handleConfirmDuplicate(sug: ReviewDuplicateSuggestion) {
  try {
    await stagingStore.confirmDuplicate(sug.record_a.id, sug.id);
  } catch (err: any) {
    alert(`Failed to exclude duplicate item: ${err.message || err}`);
  }
}

async function handleConfirmTransfer(sug: ReviewTransferSuggestion) {
  try {
    await stagingStore.confirmTransfer(
      sug.source_record.id,
      sug.source_record.kind,
      sug.destination_record.id,
      sug.destination_record.kind,
      sug.id
    );
  } catch (err: any) {
    alert(`Failed to pair transfer: ${err.message || err}`);
  }
}

async function handleDismissSuggestion(sugId: string) {
  await stagingStore.dismissSuggestion(sugId);
}

const activeDuplicateItem = ref<StagingItem | null>(null);
const editingItem = ref<StagingItem | null>(null);
const previewReceiptImage = ref<string | null>(null);

const sourceFilters = [
  { label: 'All Sources', value: 'all' },
  { label: 'Statements', value: 'statement_csv' },
  { label: 'Receipts', value: 'receipt_image' }
];

const editForm = ref({
  merchant: '',
  amount: 0,
  date: '',
  account_id: 0,
  destination_account_id: null as number | null,
  transaction_type: 'expense' as TransactionType,
  category_name: '',
  expense_nature: 'unclassified' as ExpenseNature,
  notes: '',
  anchor_mode: 'auto'
});
const isPopulatingStagingEdit = ref(false);
const editCategoryClearedNotice = ref<string | null>(null);

const compatibleEditCategories = computed(() =>
  filterCategoriesForTransactionType(transactionsStore.categories, editForm.value.transaction_type)
);

watch(() => editForm.value.transaction_type, (nextType) => {
  if (isPopulatingStagingEdit.value) return;
  const expected = expectedCategoryTypeForTransaction(nextType);
  if (editForm.value.category_name.trim()) {
    const matched = transactionsStore.categories.find(
      c => c.name.toLowerCase() === editForm.value.category_name.trim().toLowerCase()
    );
    if (!expected || (matched && getCategoryPurpose(matched) !== expected)) {
      editForm.value.category_name = '';
      editForm.value.expense_nature = 'unclassified';
      editCategoryClearedNotice.value =
        nextType === 'transfer'
          ? 'Category cleared because transfers do not use categories.'
          : `Cleared previous category because ${nextType} items require an ${nextType} category.`;
      return;
    }
  }
  if (nextType !== 'expense') {
    editForm.value.expense_nature = 'unclassified';
  }
  editCategoryClearedNotice.value = null;
});

function applyQueueRouteParams() {
  if (route.query.status === 'pending' || route.query.status === 'all') {
    stagingStore.statusFilter = String(route.query.status);
  }
  if (route.query.tab === 'duplicates' || route.query.tab === 'transfers') {
    activeSuggestionTab.value = route.query.tab;
    isSuggestionsCollapsed.value = false;
  }
  const itemParam = Number(route.query.item_id);
  highlightedItemId.value = !isNaN(itemParam) && itemParam > 0 ? itemParam : null;
}

watch(() => route.query, () => {
  applyQueueRouteParams();
});

onMounted(async () => {
  applyQueueRouteParams();
  await Promise.all([
    stagingStore.fetchItems(),
    stagingStore.fetchSuggestions(),
    accountsStore.loadData(),
    transactionsStore.categories.length === 0 ? transactionsStore.loadCategories() : Promise.resolve(),
    systemStore.config ? Promise.resolve() : systemStore.loadConfig()
  ]);
});

// Manual Split Modal State & Handlers
const isSplitModalOpen = ref(false);
const splittingItem = ref<StagingItem | null>(null);

function openSplitModal(item: StagingItem) {
  splittingItem.value = item;
  isSplitModalOpen.value = true;
}

async function handleSplitSuccess() {
  await Promise.all([
    stagingStore.fetchItems(),
    stagingStore.fetchCount(),
    stagingStore.fetchSuggestions(),
    accountsStore.loadData(),
    transactionsStore.loadRecent(),
    transactionsStore.loadTransactions()
  ]);
  isSplitModalOpen.value = false;
  splittingItem.value = null;
}

const isAllSelected = computed(() => {
  return stagingStore.filteredItems.length > 0 &&
    stagingStore.filteredItems.every(i => stagingStore.selectedIds.includes(i.id));
});

const selectedDuplicatesCount = computed(() => {
  return stagingStore.filteredItems.filter(i => 
    stagingStore.selectedIds.includes(i.id) && i.is_potential_duplicate
  ).length;
});

function formatDate(dateStr?: string | null) {
  if (!dateStr) return '';
  const dt = new Date(dateStr);
  return dt.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

function isItemPlanned(item: any): boolean {
  if (!item || !item.extracted_date) return false;
  const todayStr = new Date().toLocaleDateString('en-CA');
  const dStr = String(item.extracted_date).slice(0, 10);
  return dStr > todayStr;
}

function setSourceFilter(src: string) {
  stagingStore.sourceFilter = src;
}

function toggleStatusFilter() {
  stagingStore.statusFilter = stagingStore.statusFilter === 'pending' ? 'all' : 'pending';
  stagingStore.fetchItems();
}

function handleToggleSelectAll(e: Event) {
  const target = e.target as HTMLInputElement;
  stagingStore.toggleSelectAll(target.checked);
}

async function handleApproveSingle(item: StagingItem) {
  try {
    await stagingStore.approveItem(item.id);
  } catch (err: any) {
    alert(err.message || 'Approval failed');
  }
}

async function handleDiscardSingle(item: StagingItem) {
  if (confirm(`Discard '${item.extracted_merchant || 'this transaction'}' from review?`)) {
    await stagingStore.discardItem(item.id);
  }
}

async function handleApproveDuplicate(item: StagingItem) {
  activeDuplicateItem.value = null;
  await handleApproveSingle(item);
}

async function handleDiscardDuplicate(item: StagingItem) {
  activeDuplicateItem.value = null;
  await stagingStore.discardItem(item.id);
}

async function handleBatchApprove(includeDuplicates: boolean) {
  try {
    const res = await stagingStore.batchApprove(includeDuplicates);
    if (res.excluded_duplicates_count > 0) {
      alert(`Approved ${res.approved_count} items. Excluded ${res.excluded_duplicates_count} potential duplicates for individual review.`);
    }
  } catch (err: any) {
    alert(err.message || 'Batch approve failed');
  }
}

async function handleBatchReject() {
  if (confirm(`Discard all ${stagingStore.selectedIds.length} selected items?`)) {
    await stagingStore.batchReject();
  }
}

async function toggleAnchorMode(item: StagingItem) {
  const newMode = item.anchor_mode === 'after_anchor' ? 'already_reflected' : 'after_anchor';
  try {
    await stagingStore.updateItem(item.id, { anchor_mode: newMode });
    item.anchor_mode = newMode;
  } catch (err) {
    console.error('Failed to toggle anchor mode', err);
  }
}

function openEditModal(item: StagingItem) {
  isPopulatingStagingEdit.value = true;
  editCategoryClearedNotice.value = null;
  editingItem.value = item;
  editForm.value = {
    merchant: item.extracted_merchant || '',
    amount: item.amount_pounds || 0,
    date: item.extracted_date ? item.extracted_date.substring(0, 10) : '',
    account_id: item.suggested_account_id || (accountsStore.accounts[0]?.id ?? 0),
    destination_account_id: item.destination_account_id || null,
    transaction_type: (item.transaction_type || 'expense') as TransactionType,
    category_name: item.suggested_category_name || '',
    expense_nature: item.transaction_type === 'expense' ? (item.suggested_expense_nature || 'unclassified') : 'unclassified',
    notes: item.notes || '',
    anchor_mode: item.anchor_mode || 'already_reflected'
  };
  isPopulatingStagingEdit.value = false;
}

async function saveEditedItem() {
  if (!editingItem.value) return;
  try {
    await stagingStore.updateItem(editingItem.value.id, {
      merchant: editForm.value.merchant,
      amount: editForm.value.amount,
      transaction_date: editForm.value.date ? `${editForm.value.date}T12:00:00Z` : undefined,
      account_id: editForm.value.account_id,
      destination_account_id: editForm.value.destination_account_id,
      transaction_type: editForm.value.transaction_type,
      category_name: editForm.value.category_name,
      expense_nature: editForm.value.expense_nature,
      notes: editForm.value.notes,
      anchor_mode: editForm.value.anchor_mode
    });
    editingItem.value = null;
  } catch (err: any) {
    alert(err.message || 'Save failed');
  }
}

function handleImportFinished() {
  stagingStore.fetchItems();
  stagingStore.fetchSuggestions();
}

async function handleUnifiedImportFinished() {
  await Promise.all([
    stagingStore.fetchItems(),
    stagingStore.fetchCount(),
    stagingStore.fetchSuggestions(),
    accountsStore.loadData()
  ]);
}
</script>
