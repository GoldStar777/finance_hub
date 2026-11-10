<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
      <div>
        <div class="flex items-center space-x-3">
          <h1 class="text-xl font-extrabold text-slate-900 dark:text-white tracking-tight">
            Ledger
          </h1>
          <!-- Active vs Recently Deleted View Switcher -->
          <div class="inline-flex items-center bg-slate-100 dark:bg-slate-800 p-0.5 rounded-full border border-slate-200 dark:border-slate-700 text-xs">
            <button 
              type="button"
              @click="switchTab('active')"
              :class="txStore.activeLedgerTab === 'active' ? 'bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-xs font-bold' : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'"
              class="px-3 py-1 rounded-full transition flex items-center space-x-1.5">
              <span>Active</span>
            </button>
            <button 
              type="button"
              @click="switchTab('deleted')"
              :class="txStore.activeLedgerTab === 'deleted' ? 'bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-xs font-bold' : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'"
              class="px-3 py-1 rounded-full transition flex items-center space-x-1.5">
              <span>Recently Deleted</span>
              <span 
                v-if="(txStore.deletedSummary?.total_deleted || 0) > 0"
                class="px-1.5 py-0.2 rounded-full text-[10px] font-mono font-bold bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300">
                {{ txStore.deletedSummary?.total_deleted }}
              </span>
            </button>
          </div>
        </div>
        <p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
          {{ txStore.activeLedgerTab === 'active' ? 'Complete, deterministic record of all transactions, transfers, and adjustments.' : 'Review, recover, or restore soft-deleted transactions with complete preserved history.' }}
        </p>
      </div>

      <div class="flex items-center space-x-2 shrink-0">
        <!-- Reconcile Button if single account selected -->
        <button 
          v-if="selectedNonInvestmentAccount"
          @click="openReconcileModal(selectedNonInvestmentAccount)"
          class="self-start sm:self-auto px-3.5 py-2 text-xs font-semibold rounded-full border border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface hover:bg-slate-100 dark:hover:bg-slate-800 transition text-slate-800 dark:text-slate-200 flex items-center space-x-1.5"
          :title="`Reconcile ${selectedNonInvestmentAccount.name}`">
          <span>⚖️ Reconcile {{ selectedNonInvestmentAccount.name }}</span>
        </button>

        <!-- Export Dropdown Menu -->
        <div class="relative" ref="exportDropdownRef">
          <button 
            type="button"
            @click="isExportOpen = !isExportOpen"
            :disabled="isExporting"
            class="px-3.5 py-2 text-xs font-semibold rounded-full border border-brand-border dark:border-brand-darkborder bg-white dark:bg-brand-darksurface hover:bg-slate-50 dark:hover:bg-slate-800 transition text-slate-800 dark:text-slate-200 shadow-xs flex items-center space-x-1.5"
            :title="`Export all ${txStore.total} matching transactions across all pages`">
            <span v-if="isExporting" class="inline-block animate-spin">⏳</span>
            <span v-else>📥</span>
            <span>Export ({{ txStore.total }})</span>
            <span class="text-[10px] text-slate-400">▾</span>
          </button>

          <!-- Export Popover -->
          <div 
            v-if="isExportOpen"
            class="absolute right-0 mt-1.5 w-72 rounded-2xl bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder shadow-xl z-50 p-3 space-y-2.5">
            <div>
              <div class="text-xs font-bold text-slate-900 dark:text-white flex items-center justify-between">
                <span>Export Matching Ledger</span>
                <span class="px-2 py-0.5 rounded-full text-[10px] font-mono bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300">
                  {{ txStore.total }} items
                </span>
              </div>
              <p class="text-[11px] text-slate-500 dark:text-slate-400 mt-1 leading-relaxed">
                Exports all <strong>{{ txStore.total }}</strong> transactions matching your active filters across all pages, formatted in <strong>{{ baseCurrencyCode }} ({{ baseCurrencySymbol }})</strong>.
              </p>
            </div>

            <div class="pt-2 border-t border-slate-100 dark:border-slate-800 space-y-1">
              <button 
                type="button"
                @click="handleExport('csv')"
                :disabled="isExporting || txStore.total === 0"
                class="w-full text-left px-3 py-2 rounded-xl text-xs font-semibold hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center justify-between transition disabled:opacity-50">
                <div class="flex items-center space-x-2">
                  <span class="text-base">📄</span>
                  <div>
                    <div class="text-slate-900 dark:text-white font-medium">Export as CSV</div>
                    <div class="text-[10px] text-slate-400 font-normal">Standard comma-separated table</div>
                  </div>
                </div>
                <span class="text-[10px] font-mono text-slate-400">.csv</span>
              </button>

              <button 
                type="button"
                @click="handleExport('xlsx')"
                :disabled="isExporting || txStore.total === 0"
                class="w-full text-left px-3 py-2 rounded-xl text-xs font-semibold hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center justify-between transition disabled:opacity-50">
                <div class="flex items-center space-x-2">
                  <span class="text-base">📊</span>
                  <div>
                    <div class="text-slate-900 dark:text-white font-medium">Export as Excel</div>
                    <div class="text-[10px] text-slate-400 font-normal">Formatted workbook with auto-fit & frozen header</div>
                  </div>
                </div>
                <span class="text-[10px] font-mono text-slate-400">.xlsx</span>
              </button>
            </div>
          </div>
        </div>

        <!-- Record Transaction Button -->
        <button 
          @click="txStore.openRecordModal()" 
          class="self-start sm:self-auto px-4 py-2 text-xs font-semibold rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 hover:opacity-90 transition shadow-sm flex items-center space-x-1.5">
          <span>+ Record Transaction</span>
        </button>
      </div>
    </div>

    <!-- Persistent Sticky Ledger Control Dock -->
    <div
      v-if="txStore.activeLedgerTab === 'active'"
      data-testid="ledger-sticky-toolbar"
      class="sticky top-16 z-30 -mx-4 sm:-mx-6 px-4 sm:px-6 py-2.5 backdrop-blur-md bg-brand-cream/95 dark:bg-brand-darkbg/95 border-b border-brand-border/60 dark:border-brand-darkborder/60 transition-all shadow-xs space-y-2.5"
    >
      <!-- Mobile Compact Summary Strip (< md) -->
      <div class="flex md:hidden items-center justify-between gap-2 bg-white dark:bg-brand-darksurface rounded-2xl border border-brand-border dark:border-brand-darkborder px-3 py-2 shadow-xs">
        <button
          type="button"
          @click="isMobileFiltersOpen = !isMobileFiltersOpen"
          class="px-2.5 py-1 rounded-xl text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200 border border-brand-border dark:border-brand-darkborder flex items-center gap-1.5 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
        >
          <span>Controls</span>
          <span
            v-if="activeFilterCount > 0"
            class="px-1.5 py-0.2 rounded-full text-[10px] font-bold bg-slate-900 text-white dark:bg-white dark:text-slate-900 tabular-nums"
          >
            {{ activeFilterCount }}
          </span>
          <svg class="w-3.5 h-3.5 transition-transform" :class="{ 'rotate-180': isMobileFiltersOpen }" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        <div class="flex items-center space-x-2 shrink-0">
          <div class="flex items-center space-x-1">
            <span class="text-[10px] font-mono text-slate-400">Rows:</span>
            <select
              :value="txStore.limit"
              @change="handlePageSizeSelect"
              class="bg-slate-100 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-lg px-2 py-1 text-xs font-mono font-semibold text-slate-800 dark:text-slate-200 focus:outline-none"
            >
              <option v-for="size in [25, 50, 100, 200]" :key="size" :value="size">{{ size }}</option>
            </select>
          </div>

          <button
            type="button"
            @click="isExportOpen = !isExportOpen"
            class="px-2.5 py-1 rounded-lg border border-brand-border dark:border-brand-darkborder bg-slate-50 dark:bg-slate-800 text-xs font-semibold text-slate-700 dark:text-slate-200"
            title="Export filtered transactions"
          >
            📥 Export
          </button>
        </div>
      </div>

      <!-- Expandable / Desktop Controls -->
      <div :class="[isMobileFiltersOpen ? 'block' : 'hidden md:block', 'space-y-2.5']">
        
        <!-- Tier 1: Shared Period & Filters Panels -->
        <SharedFilterToolbar
          :accounts="accountsStore.accounts"
          :categories="txStore.categories"
          :allow-unassigned-account="true"
          :can-navigate-previous="txStore.rangeMeta.canNavigatePrevious"
          :can-navigate-next="txStore.rangeMeta.canNavigateNext"
          :is-loading="txStore.loading"
          :resolved-start-date="txStore.rangeMeta.startDate"
          :resolved-end-date="txStore.rangeMeta.endDate"
          @preset-change="handleSharedPresetChange"
          @navigate-period="handleSharedRefresh"
          @reset-offset="handleSharedRefresh"
          @custom-range-apply="handleSharedRefresh"
          @interval-change="handleSharedIntervalChange"
          @accounts-change="handleSharedRefresh"
          @categories-change="handleSharedRefresh"
          @reset-all="handleSharedRefresh"
        />

        <!-- Compatibility hidden select for form/test integrations -->
        <select v-model="selectedCategoryFilterValue" class="hidden" aria-hidden="true">
          <option :value="null">All Categories</option>
          <option value="uncategorized">Uncategorised</option>
          <option v-for="cat in txStore.categories" :key="cat.id" :value="cat.id">
            {{ cat.name }}
          </option>
        </select>

        <!-- Tier 2: Independent Ledger Page-Specific Controls Panel -->
        <div
          data-testid="ledger-page-controls"
          class="bg-slate-100/85 dark:bg-slate-900/60 rounded-2xl border border-brand-border/80 dark:border-brand-darkborder/80 px-3 py-2 space-y-2"
        >
          <div class="flex flex-wrap items-center justify-between gap-2">
            <!-- Left Ledger-Specific Filters: Search, Type, Status, Nature -->
            <div class="flex flex-wrap items-center gap-2 min-w-0">
              <span class="text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 hidden sm:inline shrink-0">
                Ledger
              </span>

              <!-- Search Query -->
              <div class="relative w-44 sm:w-56">
                <input
                  v-model="txStore.filters.q"
                  @input="handleSearchInput"
                  type="text"
                  placeholder="Search merchant, notes..."
                  aria-label="Search merchant or notes"
                  class="w-full bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder rounded-xl pl-3 pr-7 py-1.5 text-xs text-slate-900 dark:text-white focus:outline-none focus:border-slate-400 dark:focus:border-slate-600"
                />
                <button
                  v-if="txStore.filters.q"
                  type="button"
                  @click="clearSearch"
                  class="absolute right-2 top-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-white text-xs"
                  aria-label="Clear search"
                >
                  &times;
                </button>
              </div>

              <!-- Transaction Type Filter -->
              <select
                v-model="selectedTypeFilterValue"
                @change="handleTypeFilterChange"
                data-testid="ledger-type-filter"
                aria-label="Filter by transaction type"
                class="bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder rounded-xl px-2.5 py-1.5 text-xs font-medium text-slate-900 dark:text-white focus:outline-none"
              >
                <option value="all">All Types</option>
                <option value="expense">Expenses</option>
                <option value="income">Income</option>
                <option value="transfer">Transfers</option>
              </select>

              <!-- Activity Status Filter -->
              <select
                v-model="selectedStatusFilterValue"
                @change="handleStatusFilterChange"
                data-testid="ledger-status-filter"
                aria-label="Filter by activity status"
                class="bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder rounded-xl px-2.5 py-1.5 text-xs font-medium text-slate-900 dark:text-white focus:outline-none"
              >
                <option value="all">All Activity</option>
                <option value="actual">Actuals only</option>
                <option value="planned">Planned only</option>
              </select>

              <!-- Expense Nature Pills -->
              <div class="flex items-center gap-0.5 bg-white/70 dark:bg-white/[0.04] px-1.5 py-0.5 rounded-xl border border-black/5 dark:border-white/5 text-xs">
                <span class="text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 mr-1 hidden sm:inline">Nature</span>
                <button
                  @click="setNatureFilter(null)"
                  type="button"
                  class="px-2 py-0.5 rounded-lg text-[11px] font-semibold transition"
                  :class="txStore.filters.expenseNature === null ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-950 shadow-2xs' : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'"
                >
                  All
                </button>
                <button
                  @click="setNatureFilter('fixed')"
                  type="button"
                  class="px-2 py-0.5 rounded-lg text-[11px] font-semibold transition"
                  :class="txStore.filters.expenseNature === 'fixed' ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-950 shadow-2xs' : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'"
                >
                  Fixed
                </button>
                <button
                  @click="setNatureFilter('variable')"
                  type="button"
                  class="px-2 py-0.5 rounded-lg text-[11px] font-semibold transition"
                  :class="txStore.filters.expenseNature === 'variable' ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-950 shadow-2xs' : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'"
                >
                  Variable
                </button>
              </div>
            </div>

            <!-- Right Controls: Sort, Page Size, Matching Count, Sticky Export -->
            <div class="flex flex-wrap items-center gap-2 shrink-0">
              <!-- Explicit Sort-By Selector -->
              <div class="flex items-center gap-1.5 text-xs">
                <span class="text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">Sort</span>
                <select
                  :value="`${txStore.sortBy}_${txStore.sortOrder}`"
                  @change="handleSortSelect"
                  data-testid="ledger-sort-selector"
                  aria-label="Sort ledger transactions"
                  class="bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder rounded-xl px-2.5 py-1.5 text-xs font-semibold text-slate-900 dark:text-white focus:outline-none"
                >
                  <option value="date_desc">Date (Newest first)</option>
                  <option value="date_asc">Date (Oldest first)</option>
                  <option value="amount_desc">Amount (Highest first)</option>
                  <option value="amount_asc">Amount (Lowest first)</option>
                  <option value="category_asc">Category (A to Z)</option>
                  <option value="category_desc">Category (Z to A)</option>
                  <option value="account_asc">Account (A to Z)</option>
                  <option value="account_desc">Account (Z to A)</option>
                </select>
              </div>

              <!-- Page Size Selector -->
              <div class="hidden sm:flex items-center gap-1.5 text-xs">
                <span class="text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">Rows</span>
                <div class="inline-flex rounded-xl border border-brand-border dark:border-brand-darkborder bg-white dark:bg-brand-darksurface p-0.5">
                  <button
                    v-for="size in [25, 50, 100, 200]"
                    :key="size"
                    type="button"
                    @click="changePageSize(size)"
                    class="px-2 py-0.5 rounded-lg text-[11px] font-semibold transition"
                    :class="txStore.limit === size
                      ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-950 shadow-xs'
                      : 'text-slate-500 hover:text-slate-900 dark:hover:text-white'"
                  >
                    {{ size }}
                  </button>
                </div>
              </div>

              <!-- Matching Transactions Badge -->
              <span class="px-2.5 py-1 rounded-full text-xs font-mono font-semibold bg-white dark:bg-brand-darksurface text-slate-800 dark:text-slate-200 border border-brand-border dark:border-brand-darkborder tabular-nums">
                {{ txStore.total }} matching
              </span>

              <!-- Sticky Bar Export Menu -->
              <div class="relative hidden md:block" ref="stickyExportDropdownRef">
                <button
                  type="button"
                  data-testid="sticky-export-trigger"
                  @click="isStickyExportOpen = !isStickyExportOpen"
                  :disabled="isExporting || txStore.total === 0"
                  class="px-2.5 py-1.5 rounded-xl border border-brand-border dark:border-brand-darkborder bg-white dark:bg-brand-darksurface hover:bg-slate-50 dark:hover:bg-slate-800 text-xs font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-1.5 disabled:opacity-50 transition"
                  title="Export matching ledger rows"
                >
                  <span>📥</span>
                  <span>Export</span>
                  <span class="text-[10px] text-slate-400">▾</span>
                </button>

                <div
                  v-if="isStickyExportOpen"
                  class="absolute right-0 mt-1.5 w-52 rounded-2xl bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder shadow-xl z-50 p-2 space-y-1"
                >
                  <button
                    type="button"
                    @click="handleExport('csv')"
                    :disabled="isExporting || txStore.total === 0"
                    class="w-full text-left px-3 py-2 rounded-xl text-xs font-semibold hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center justify-between transition"
                  >
                    <span>📄 Export CSV</span>
                    <span class="text-[10px] font-mono text-slate-400">.csv</span>
                  </button>
                  <button
                    type="button"
                    @click="handleExport('xlsx')"
                    :disabled="isExporting || txStore.total === 0"
                    class="w-full text-left px-3 py-2 rounded-xl text-xs font-semibold hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center justify-between transition"
                  >
                    <span>📊 Export Excel</span>
                    <span class="text-[10px] font-mono text-slate-400">.xlsx</span>
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- Ledger-Specific Active Pills Row (Independent from Shared Panel 2 Filters) -->
          <div
            v-if="hasLedgerSpecificFilters"
            data-testid="ledger-specific-active-bar"
            class="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-brand-border/60 dark:border-brand-darkborder/60"
          >
            <div class="flex flex-wrap items-center gap-1.5">
              <span class="text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 mr-1">
                Ledger filters:
              </span>

              <div v-if="txStore.filters.q" class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-white dark:bg-brand-darksurface text-slate-800 dark:text-slate-200 border border-brand-border dark:border-brand-darkborder">
                <span>Search: "<strong>{{ txStore.filters.q }}</strong>"</span>
                <button type="button" @click="clearSearch" class="hover:text-rose-500 font-bold ml-1" aria-label="Remove search filter">&times;</button>
              </div>

              <div v-if="txStore.filters.transactionType" class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-white dark:bg-brand-darksurface text-slate-800 dark:text-slate-200 border border-brand-border dark:border-brand-darkborder">
                <span>Type: <strong class="capitalize">{{ txStore.filters.transactionType }}</strong></span>
                <button type="button" @click="clearTypeFilter" class="hover:text-rose-500 font-bold ml-1" aria-label="Remove type filter">&times;</button>
              </div>

              <div v-if="txStore.filters.status && txStore.filters.status !== 'all'" data-testid="status-filter-chip" class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-white dark:bg-brand-darksurface text-slate-800 dark:text-slate-200 border border-brand-border dark:border-brand-darkborder">
                <span>Status: <strong>{{ txStore.filters.status === 'actual' ? 'Actuals Only' : 'Planned Only' }}</strong></span>
                <button type="button" @click="clearStatusFilter" class="hover:text-rose-500 font-bold ml-1" aria-label="Remove status filter">&times;</button>
              </div>

              <div v-if="txStore.filters.expenseNature" class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-white dark:bg-brand-darksurface text-slate-800 dark:text-slate-200 border border-brand-border dark:border-brand-darkborder">
                <span>Nature: <strong class="capitalize">{{ txStore.filters.expenseNature }}</strong></span>
                <button type="button" @click="setNatureFilter(null)" class="hover:text-rose-500 font-bold ml-1" aria-label="Remove nature filter">&times;</button>
              </div>

              <div v-if="txStore.sortBy !== 'date' || txStore.sortOrder !== 'desc'" data-testid="ledger-sort-chip" class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-white dark:bg-brand-darksurface text-slate-800 dark:text-slate-200 border border-brand-border dark:border-brand-darkborder">
                <span>Sort: <strong>{{ formatSortLabel }}</strong></span>
                <button type="button" @click="resetSort" class="hover:text-rose-500 font-bold ml-1" title="Reset sort to newest first" aria-label="Reset sort order">&times;</button>
              </div>
            </div>

            <button
              type="button"
              @click="resetLedgerOnlyControls"
              class="text-xs font-bold text-rose-600 dark:text-rose-400 hover:underline shrink-0"
            >
              Clear ledger filters &times;
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Bulk Selection Bar -->
    <div 
      v-if="txStore.activeLedgerTab === 'active' && selectedCount > 0"
      class="p-3.5 rounded-2xl border border-indigo-200 dark:border-indigo-900 bg-indigo-50/70 dark:bg-indigo-950/40 shadow-sm flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 animate-fadeIn">
      
      <div class="flex items-center space-x-3 text-xs">
        <span class="font-bold text-indigo-950 dark:text-indigo-200 flex items-center space-x-1.5">
          <span>✓</span>
          <span><strong>{{ selectedCount }}</strong> transaction{{ selectedCount === 1 ? '' : 's' }} selected</span>
        </span>

        <!-- Scope Offer: Select all matching transactions across all pages -->
        <template v-if="!txStore.isAllMatchingSelected && txStore.total > txStore.transactions.length">
          <span class="text-indigo-300 dark:text-indigo-700">&bull;</span>
          <button 
            type="button"
            @click="txStore.selectAllMatching()"
            class="text-indigo-700 dark:text-indigo-300 font-semibold hover:underline flex items-center space-x-1">
            <span>Select all {{ txStore.total }} matching transactions across all pages</span>
          </button>
        </template>
        <template v-else-if="txStore.isAllMatchingSelected">
          <span class="text-indigo-300 dark:text-indigo-700">&bull;</span>
          <span class="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-indigo-200 text-indigo-900 dark:bg-indigo-900 dark:text-indigo-200">
            All {{ txStore.total }} matching selected
          </span>
        </template>
      </div>

      <div class="flex items-center space-x-2 shrink-0">
        <button 
          type="button"
          @click="openBulkEditModal"
          class="px-4 py-1.5 text-xs font-semibold rounded-full bg-indigo-600 text-white hover:bg-indigo-700 transition shadow-sm flex items-center space-x-1.5">
          <span>✏️ Bulk Edit ({{ selectedCount }})</span>
        </button>

        <button 
          type="button"
          @click="openBulkDeleteModal"
          class="px-4 py-1.5 text-xs font-semibold rounded-full bg-rose-600 text-white hover:bg-rose-700 transition shadow-sm flex items-center space-x-1.5">
          <span>🗑️ Bulk Delete ({{ selectedCount }})</span>
        </button>

        <button 
          type="button"
          @click="txStore.clearSelection()"
          class="px-3 py-1.5 text-xs font-semibold rounded-full border border-indigo-300 dark:border-indigo-800 text-indigo-800 dark:text-indigo-300 hover:bg-indigo-100 dark:hover:bg-indigo-900/50 transition">
          Deselect all
        </button>
      </div>
    </div>

    <!-- Table Container -->
    <div 
      v-if="txStore.activeLedgerTab === 'active'"
      class="border border-brand-border dark:border-brand-darkborder rounded-2xl bg-white dark:bg-brand-darksurface overflow-hidden shadow-sm">
      <!-- Loading State -->
      <div v-if="txStore.loading" class="p-8 text-center space-y-3">
        <div class="animate-spin w-6 h-6 border-2 border-slate-900 dark:border-white border-t-transparent rounded-full mx-auto"></div>
        <p class="text-xs text-slate-500">Updating ledger records...</p>
      </div>

      <!-- Empty State -->
      <div v-else-if="txStore.transactions.length === 0" class="p-12 text-center space-y-3">
        <div class="w-10 h-10 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-400 mx-auto flex items-center justify-center font-bold">
          🔍
        </div>
        <p class="text-slate-900 dark:text-white font-semibold">No transactions match your criteria</p>
        <p class="text-xs text-slate-500 max-w-sm mx-auto">
          {{ hasActiveFilters ? 'Try adjusting your search or filter options.' : 'Record a transaction to see it here.' }}
        </p>
        <button 
          v-if="hasActiveFilters"
          type="button"
          @click="resetAllFilters"
          class="mt-2 px-3.5 py-1.5 text-xs font-semibold rounded-full border border-brand-border dark:border-brand-darkborder hover:bg-slate-100 dark:hover:bg-slate-800 transition">
          Clear Filters
        </button>
      </div>

      <!-- Transaction Table -->
      <div v-else class="overflow-x-auto">
        <table class="w-full text-left text-xs">
          <thead>
            <tr class="border-b border-brand-border dark:border-brand-darkborder bg-slate-50/50 dark:bg-slate-800/30 text-slate-400 font-mono uppercase text-[10px] tracking-wider">
              <th class="py-3 px-3 text-center w-10">
                <input 
                  type="checkbox"
                  :checked="isCurrentPageAllSelected"
                  :indeterminate.prop="isCurrentPagePartiallySelected"
                  @change="toggleSelectCurrentPage"
                  class="rounded border-slate-300 dark:border-slate-700 text-indigo-600 focus:ring-0 cursor-pointer"
                  aria-label="Select all transactions on this page" />
              </th>
              <th
                v-for="col in ledgerTableColumns"
                :key="col.key"
                :aria-sort="col.sortField ? getAriaSort(col.sortField) : undefined"
                :class="[
                  'py-3 px-4 font-semibold',
                  col.align === 'right' ? 'text-right' : col.align === 'center' ? 'text-center' : 'text-left',
                  col.extraClass || ''
                ]"
              >
                <button
                  v-if="col.sortField"
                  type="button"
                  :data-testid="`sort-heading-${col.sortField}`"
                  @click="toggleHeadingSort(col.sortField)"
                  :aria-label="getSortHeadingAriaLabel(col.sortField, col.label)"
                  :class="[
                    'group inline-flex items-center gap-1 px-1.5 py-1 -mx-1.5 -my-1 rounded-lg uppercase tracking-wider font-mono text-[10px] font-semibold transition-colors whitespace-nowrap focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 cursor-pointer',
                    col.align === 'right' ? 'justify-end' : '',
                    txStore.sortBy === col.sortField
                      ? 'text-slate-900 dark:text-white font-bold bg-slate-200/70 dark:bg-slate-700/50'
                      : 'text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-200/50 dark:hover:bg-slate-700/40'
                  ]"
                >
                  <span>{{ col.label }}</span>
                  <span class="inline-flex items-center shrink-0" aria-hidden="true">
                    <svg
                      v-if="txStore.sortBy === col.sortField && txStore.sortOrder === 'asc'"
                      data-testid="sort-arrow-asc"
                      class="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 15l7-7 7 7" />
                    </svg>
                    <svg
                      v-else-if="txStore.sortBy === col.sortField && txStore.sortOrder === 'desc'"
                      data-testid="sort-arrow-desc"
                      class="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M19 9l-7 7-7-7" />
                    </svg>
                    <svg
                      v-else
                      data-testid="sort-arrow-inactive"
                      class="w-3.5 h-3.5 opacity-35 group-hover:opacity-80 transition-opacity"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 9l4-4 4 4m0 6l-4 4-4-4" />
                    </svg>
                  </span>
                </button>
                <span v-else>{{ col.label }}</span>
              </th>
            </tr>
          </thead>
          <tbody class="divide-y divide-brand-border/60 dark:divide-brand-darkborder/60">
            <tr 
              v-for="tx in txStore.transactions" 
              :key="tx.id"
              class="transition"
              :class="txStore.isRowSelected(tx.id) ? 'bg-indigo-50/50 dark:bg-indigo-950/20' : 'hover:bg-slate-50/60 dark:hover:bg-slate-800/40'">
              
              <!-- Checkbox Selection -->
              <td class="py-3.5 px-3 text-center w-10">
                <input 
                  type="checkbox"
                  :checked="txStore.isRowSelected(tx.id)"
                  @change="txStore.toggleRowSelection(tx.id)"
                  class="rounded border-slate-300 dark:border-slate-700 text-indigo-600 focus:ring-0 cursor-pointer"
                  :aria-label="`Select transaction ${tx.id}`" />
              </td>

              <!-- Date -->
              <td class="py-3.5 px-4 font-mono text-slate-500 whitespace-nowrap">
                <div class="flex items-center space-x-1.5">
                  <span>{{ formatDate(tx.transaction_date) }}</span>
                  <span 
                    v-if="tx.is_planned" 
                    data-testid="tx-planned-badge"
                    class="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border border-amber-300 dark:border-amber-800">
                    Planned
                  </span>
                </div>
              </td>

              <!-- Description & Notes -->
              <td class="py-3.5 px-4 max-w-xs">
                <div class="font-bold text-slate-900 dark:text-white truncate">
                  <span v-if="tx.merchant">{{ tx.merchant }}</span>
                  <span v-else class="italic text-slate-400 font-normal">Merchant not recorded</span>
                </div>
                <div v-if="tx.notes" class="text-[11px] text-slate-400 truncate mt-0.5">
                  {{ tx.notes }}
                </div>
              </td>

              <!-- Category -->
              <td class="py-3.5 px-4 whitespace-nowrap">
                <span 
                  v-if="tx.category_name" 
                  class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                  {{ tx.category_name }}
                </span>
                <span v-else class="text-slate-400 text-[10px]">—</span>
              </td>

              <!-- Budget Nature -->
              <td class="py-3.5 px-4 whitespace-nowrap">
                <span 
                  v-if="tx.transaction_type === 'expense' && tx.expense_nature !== 'unclassified'"
                  class="text-[10px] font-mono uppercase px-2 py-0.5 rounded font-semibold"
                  :class="tx.expense_nature === 'fixed' 
                    ? 'bg-indigo-100 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300' 
                    : 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300'">
                  {{ tx.expense_nature }}
                </span>
                <span v-else class="text-slate-400 text-[10px]">—</span>
              </td>

              <!-- Account -->
              <td class="py-3.5 px-4 whitespace-nowrap">
                <div v-if="tx.is_unassigned || !tx.account_id" class="inline-flex items-center space-x-1.5 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800">
                  <span class="w-1.5 h-1.5 rounded-full bg-amber-500 shrink-0"></span>
                  <span>Unassigned</span>
                </div>
                <div v-else class="flex items-center space-x-1.5 font-medium">
                  <span class="w-2 h-2 rounded-full shrink-0" :style="{ backgroundColor: tx.account_color || '#3B82F6' }"></span>
                  <span class="text-slate-800 dark:text-slate-200">{{ tx.account_name }}</span>
                  <template v-if="tx.transaction_type === 'transfer' && tx.destination_account_name">
                    <span class="text-slate-400">&rarr;</span>
                    <span class="w-2 h-2 rounded-full shrink-0" :style="{ backgroundColor: tx.destination_account_color || '#3B82F6' }"></span>
                    <span class="text-slate-800 dark:text-slate-200">{{ tx.destination_account_name }}</span>
                  </template>
                </div>
              </td>

              <!-- Amount -->
              <td class="py-3.5 px-4 text-right whitespace-nowrap">
                <span 
                  class="font-mono font-bold sensitive text-xs"
                  :class="getAmountClass(tx.transaction_type)">
                  {{ formatTxAmount(tx) }}
                </span>
                <div v-if="tx.formatted_original_amount" class="text-[10px] font-mono text-slate-400 mt-0.5" :title="tx.implied_effective_rate_label || 'Original currency purchase'">
                  {{ tx.formatted_original_amount }}
                  <span v-if="tx.exchange_rate">
                    @ {{ Number(tx.exchange_rate).toFixed(4) }}
                  </span>
                </div>
              </td>

              <!-- Actions (Edit & Delete) -->
              <td class="py-3.5 px-4 text-center whitespace-nowrap">
                <div class="flex items-center justify-center space-x-1">
                  <button 
                    @click="openEditModal(tx)"
                    class="text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 p-1 rounded transition"
                    title="Edit transaction">
                    <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                    </svg>
                  </button>
                  <button 
                    @click="promptDelete(tx)"
                    class="text-slate-400 hover:text-rose-600 dark:hover:text-rose-400 p-1 rounded transition"
                    title="Delete transaction">
                    <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              </td>

            </tr>
          </tbody>
        </table>
      </div>

      <!-- Pagination Footer with Configurable Page Sizes -->
      <div class="p-4 border-t border-brand-border dark:border-brand-darkborder flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-slate-500 font-mono">
        <div>
          Showing {{ paginationStart }} &ndash; {{ paginationEnd }} of {{ txStore.total }} transactions
        </div>

        <!-- Page Size Selector -->
        <div class="flex items-center space-x-2">
          <span class="text-[11px] text-slate-400 font-sans">Rows per page:</span>
          <div class="inline-flex rounded-lg border border-brand-border dark:border-brand-darkborder bg-slate-50 dark:bg-slate-800 p-0.5">
            <button
              v-for="size in [25, 50, 100, 200]"
              :key="size"
              type="button"
              @click="changePageSize(size)"
              class="px-2.5 py-1 rounded-md text-xs font-semibold transition"
              :class="txStore.limit === size
                ? 'bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-xs'
                : 'text-slate-500 hover:text-slate-900 dark:hover:text-white'">
              {{ size }}
            </button>
          </div>
        </div>

        <!-- Pagination Controls -->
        <div class="flex items-center space-x-2">
          <button 
            @click="prevPage" 
            :disabled="txStore.offset === 0"
            class="px-3 py-1.5 rounded-lg border border-brand-border dark:border-brand-darkborder bg-white dark:bg-slate-800 disabled:opacity-40 hover:bg-slate-50 dark:hover:bg-slate-700 transition">
            &larr; Previous
          </button>
          <span class="text-xs px-2 font-sans font-medium text-slate-700 dark:text-slate-300">
            Page {{ currentPage }} of {{ totalPages }}
          </span>
          <button 
            @click="nextPage" 
            :disabled="txStore.offset + txStore.limit >= txStore.total"
            class="px-3 py-1.5 rounded-lg border border-brand-border dark:border-brand-darkborder bg-white dark:bg-slate-800 disabled:opacity-40 hover:bg-slate-50 dark:hover:bg-slate-700 transition">
            Next &rarr;
          </button>
        </div>
      </div>
    </div>

    <!-- Recently Deleted View -->
    <div v-else-if="txStore.activeLedgerTab === 'deleted'" class="space-y-4 animate-fadeIn">
      <!-- Recently Deleted Summary Card -->
      <div class="p-4 rounded-2xl border border-rose-200 dark:border-rose-950/60 bg-rose-50/40 dark:bg-rose-950/20 shadow-xs flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div class="space-y-1">
          <div class="flex items-center space-x-2">
            <span class="text-rose-600 dark:text-rose-400 text-lg">🗑️</span>
            <h2 class="text-sm font-bold text-slate-900 dark:text-white">
              Recently Deleted Transactions
            </h2>
            <span class="px-2 py-0.5 rounded-full text-[11px] font-mono font-bold bg-rose-100 text-rose-800 dark:bg-rose-900 dark:text-rose-200">
              {{ txStore.deletedTotal }} items
            </span>
          </div>
          <p class="text-xs text-slate-600 dark:text-slate-400 leading-relaxed max-w-2xl">
            Transactions here are safely soft-deleted and excluded from balances, cash flow, and reports. Restoring a transaction reinstates its original dates, accounts, categories, and receipt files.
          </p>
        </div>

        <div class="flex items-center gap-3 shrink-0">
          <div class="text-right">
            <div class="text-[10px] uppercase font-mono font-bold text-slate-400">Total Deleted Value</div>
            <div class="text-sm font-extrabold text-slate-900 dark:text-white">
              {{ txStore.deletedSummary?.formatted_total || '£0.00' }}
            </div>
          </div>
          <button 
            type="button"
            @click="switchTab('active')"
            class="px-3.5 py-1.5 text-xs font-semibold rounded-full border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 text-slate-800 dark:text-slate-200 transition shadow-xs">
            &larr; Back to Active
          </button>
        </div>
      </div>

      <!-- Deleted Search & Filter Bar -->
      <div class="flex items-center justify-between gap-3">
        <div class="relative flex-1 max-w-md">
          <input 
            type="text" 
            v-model="txStore.deletedQuery"
            @input="handleDeletedSearch"
            placeholder="Search deleted records by merchant or notes..." 
            class="w-full pl-8 pr-3 py-1.5 text-xs rounded-xl border border-brand-border dark:border-brand-darkborder bg-white dark:bg-brand-darksurface text-slate-800 dark:text-slate-200 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-slate-900 dark:focus:ring-white" />
          <span class="absolute left-2.5 top-2 text-slate-400 text-xs">🔍</span>
        </div>

        <!-- Bulk Restore Action Bar for Deleted Items -->
        <div v-if="txStore.deletedSelectedIds.size > 0" class="flex items-center space-x-2">
          <button 
            type="button"
            @click="handleBulkRestore"
            :disabled="txStore.loading"
            class="px-4 py-1.5 text-xs font-semibold rounded-full bg-emerald-600 hover:bg-emerald-700 text-white transition shadow-sm flex items-center space-x-1.5 disabled:opacity-50">
            <span>🛡️ Restore ({{ txStore.deletedSelectedIds.size }})</span>
          </button>
          <button 
            type="button"
            @click="txStore.clearDeletedSelection()"
            class="px-3 py-1.5 text-xs font-semibold rounded-full border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition">
            Deselect
          </button>
        </div>
      </div>

      <!-- Deleted Table -->
      <div class="border border-brand-border dark:border-brand-darkborder rounded-2xl bg-white dark:bg-brand-darksurface overflow-hidden shadow-sm">
        <div v-if="txStore.deletedLoading" class="p-8 text-center space-y-3">
          <div class="animate-spin w-6 h-6 border-2 border-slate-900 dark:border-white border-t-transparent rounded-full mx-auto"></div>
          <p class="text-xs text-slate-500">Loading deleted records...</p>
        </div>

        <div v-else-if="txStore.deletedTransactions.length === 0" class="p-12 text-center space-y-2">
          <div class="text-3xl">🕊️</div>
          <div class="text-sm font-bold text-slate-900 dark:text-white">Recently Deleted is empty</div>
          <p class="text-xs text-slate-500 dark:text-slate-400 max-w-sm mx-auto">
            {{ txStore.deletedQuery ? 'No deleted transactions match your search.' : 'You have not deleted any transactions in this workspace recently.' }}
          </p>
        </div>

        <table v-else class="w-full text-left border-collapse text-xs">
          <thead>
            <tr class="border-b border-brand-border dark:border-brand-darkborder bg-slate-50/50 dark:bg-slate-800/50 text-slate-500 font-mono text-[11px] uppercase tracking-wider">
              <th class="p-3 w-10 text-center">
                <input 
                  type="checkbox" 
                  :checked="isDeletedPageAllSelected"
                  @change="toggleSelectDeletedPage"
                  class="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 cursor-pointer" />
              </th>
              <th class="p-3">Original Date</th>
              <th class="p-3">Deleted At</th>
              <th class="p-3">Merchant / Description</th>
              <th class="p-3">Account & Destination</th>
              <th class="p-3">Category</th>
              <th class="p-3 text-right">Amount</th>
              <th class="p-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-brand-border dark:divide-brand-darkborder font-sans">
            <tr 
              v-for="tx in txStore.deletedTransactions" 
              :key="tx.id"
              :class="txStore.isDeletedRowSelected(tx.id) ? 'bg-indigo-50/40 dark:bg-indigo-950/30' : 'hover:bg-slate-50/70 dark:hover:bg-slate-800/40'"
              class="transition-colors group">
              
              <td class="p-3 text-center">
                <input 
                  type="checkbox" 
                  :checked="txStore.isDeletedRowSelected(tx.id)"
                  @change="txStore.toggleDeletedRowSelection(tx.id)"
                  class="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 cursor-pointer" />
              </td>

              <td class="p-3 font-mono text-slate-600 dark:text-slate-400 whitespace-nowrap">
                {{ formatDate(tx.transaction_date) }}
              </td>

              <td class="p-3 font-mono text-rose-600 dark:text-rose-400 whitespace-nowrap text-[11px]">
                {{ tx.deleted_at ? formatDeletedTimestamp(tx.deleted_at) : 'Recently' }}
              </td>

              <td class="p-3">
                <div class="font-semibold text-slate-900 dark:text-white flex items-center space-x-1.5">
                  <span>{{ tx.merchant || 'Unlabelled' }}</span>
                  <span v-if="tx.receipt_path" class="text-[10px]" title="Receipt file preserved safely">📎</span>
                </div>
                <div v-if="tx.notes" class="text-[11px] text-slate-400 truncate max-w-xs">
                  {{ tx.notes }}
                </div>
              </td>

              <td class="p-3 text-slate-700 dark:text-slate-300">
                <div v-if="tx.transaction_type === 'transfer'" class="flex items-center space-x-1 font-medium text-amber-700 dark:text-amber-400">
                  <span>{{ tx.account_name || 'Unassigned' }}</span>
                  <span>&rarr;</span>
                  <span>{{ tx.destination_account_name || 'Destination' }}</span>
                </div>
                <div v-else>
                  {{ tx.account_name || 'Unassigned' }}
                </div>
              </td>

              <td class="p-3 text-slate-600 dark:text-slate-400">
                <span 
                  v-if="tx.category_name" 
                  class="px-2 py-0.5 rounded-full text-[10px] font-semibold"
                  :style="{ backgroundColor: (tx.category_color || '#94A3B8') + '20', color: tx.category_color || '#94A3B8' }">
                  {{ tx.category_name }}
                </span>
                <span v-else class="text-slate-400 italic">Uncategorised</span>
              </td>

              <td class="p-3 text-right font-mono font-semibold whitespace-nowrap" :class="getAmountClass(tx.transaction_type)">
                {{ tx.transaction_type === 'expense' ? '-' : (tx.transaction_type === 'income' ? '+' : '') }}{{ tx.formatted_amount }}
              </td>

              <td class="p-3 text-right whitespace-nowrap">
                <button 
                  type="button"
                  @click="handleSingleRestore(tx)"
                  :disabled="txStore.loading"
                  class="px-3 py-1 rounded-full text-xs font-semibold bg-emerald-50 dark:bg-emerald-950/60 border border-emerald-300 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-100 dark:hover:bg-emerald-900/60 transition shadow-2xs flex items-center space-x-1 ml-auto">
                  <span>↩️</span>
                  <span>Restore</span>
                </button>
              </td>
            </tr>
          </tbody>
        </table>

        <!-- Deleted Pagination Controls -->
        <div v-if="txStore.deletedTotal > txStore.deletedLimit" class="p-3 border-t border-brand-border dark:border-brand-darkborder flex items-center justify-between text-xs text-slate-500">
          <div>
            Showing {{ txStore.deletedOffset + 1 }} to {{ Math.min(txStore.deletedOffset + txStore.deletedLimit, txStore.deletedTotal) }} of {{ txStore.deletedTotal }} deleted records
          </div>
          <div class="flex items-center space-x-2">
            <button 
              type="button"
              @click="prevDeletedPage" 
              :disabled="txStore.deletedOffset === 0"
              class="px-3 py-1.5 rounded-lg border border-brand-border dark:border-brand-darkborder bg-white dark:bg-slate-800 disabled:opacity-40 hover:bg-slate-50 dark:hover:bg-slate-700 transition">
              &larr; Previous
            </button>
            <span class="text-xs px-2 font-mono">
              Page {{ currentDeletedPage }} of {{ totalDeletedPages }}
            </span>
            <button 
              type="button"
              @click="nextDeletedPage" 
              :disabled="txStore.deletedOffset + txStore.deletedLimit >= txStore.deletedTotal"
              class="px-3 py-1.5 rounded-lg border border-brand-border dark:border-brand-darkborder bg-white dark:bg-slate-800 disabled:opacity-40 hover:bg-slate-50 dark:hover:bg-slate-700 transition">
              Next &rarr;
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Delete Confirmation Modal -->
    <div 
      v-if="txToDelete" 
      class="fixed inset-0 z-50 bg-slate-950/40 backdrop-blur-sm flex items-center justify-center p-4 animate-fadeIn"
      @click.self="txToDelete = null">
      <div class="bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder rounded-2xl max-w-sm w-full p-6 shadow-2xl space-y-4">
        <h3 class="font-bold text-slate-900 dark:text-white flex items-center space-x-2">
          <span class="text-rose-600 dark:text-rose-400">🗑️</span>
          <span>Delete Transaction</span>
        </h3>
        <p class="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
          Are you sure you want to delete <strong class="text-slate-900 dark:text-white">{{ txToDelete.merchant || 'this transaction' }}</strong> ({{ txToDelete.formatted_amount }})?
        </p>
        <div v-if="txToDelete.transaction_type === 'transfer'" class="p-2.5 rounded-xl border border-amber-200 dark:border-amber-900 bg-amber-50 dark:bg-amber-950/40 text-[11px] text-amber-900 dark:text-amber-200">
          ⚠️ <strong>Paired Transfer:</strong> Deleting this transfer removes the money movement from both accounts simultaneously.
        </div>
        <div v-if="txToDelete.receipt_path" class="p-2.5 rounded-xl border border-blue-200 dark:border-blue-900 bg-blue-50 dark:bg-blue-950/40 text-[11px] text-blue-900 dark:text-blue-200">
          📎 <strong>Preserved Receipt:</strong> The attached receipt file is kept safely in storage and will not be lost.
        </div>
        <p class="text-[11px] text-slate-500">
          This transaction will be moved to <strong>Recently Deleted</strong> and can be restored at any time.
        </p>
        <div class="flex items-center justify-end space-x-3 pt-2">
          <button 
            @click="txToDelete = null" 
            class="px-3.5 py-1.5 text-xs font-semibold rounded-full border border-brand-border dark:border-brand-darkborder hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300">
            Cancel
          </button>
          <button 
            @click="confirmDelete" 
            class="px-4 py-1.5 text-xs font-semibold rounded-full bg-rose-600 text-white hover:bg-rose-700 transition">
            Move to Recently Deleted
          </button>
        </div>
      </div>
    </div>

    <!-- Reconcile Account Modal -->
    <ReconcileAccountModal
      :is-open="isReconcileOpen"
      :account="reconcilingAccount"
      @close="isReconcileOpen = false"
      @reconciled="handleReconciled" />

    <!-- Edit Transaction Modal -->
    <EditTransactionModal
      :is-open="isEditModalOpen"
      :transaction="txToEdit"
      @close="isEditModalOpen = false"
      @saved="handleTxEdited" />

    <!-- Bulk Edit Transactions Modal -->
    <BulkEditTransactionsModal
      :is-open="isBulkEditOpen"
      :selected-count="selectedCount"
      @close="isBulkEditOpen = false"
      @updated="handleBulkUpdated" />

    <!-- Bulk Delete Confirmation Modal -->
    <BulkDeleteConfirmationModal
      :is-open="isBulkDeleteModalOpen"
      :selected-count="selectedCount"
      :is-all-matching="txStore.isAllMatchingSelected"
      :total-count="txStore.total"
      @close="isBulkDeleteModalOpen = false"
      @confirm="handleConfirmBulkDelete" />

    <!-- Floating Undo Notification Banner -->
    <div 
      v-if="txStore.undoToastMessage" 
      class="fixed bottom-6 right-6 z-50 flex items-center space-x-3 px-4 py-3 rounded-2xl bg-slate-900 text-white dark:bg-slate-800 border border-slate-700 dark:border-slate-600 shadow-2xl animate-slideUp">
      <div class="flex items-center space-x-2 text-xs">
        <span class="text-rose-400">🗑️</span>
        <span class="font-medium">{{ txStore.undoToastMessage }}</span>
      </div>
      <button 
        type="button"
        @click="txStore.undoLastDelete()" 
        class="px-3 py-1 text-xs font-bold rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white transition flex items-center space-x-1 shadow-sm">
        <span>↩️</span>
        <span>Undo</span>
      </button>
      <button 
        type="button"
        @click="txStore.dismissUndoToast()" 
        class="text-slate-400 hover:text-white text-xs p-1"
        aria-label="Dismiss undo notification">
        ✕
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAccountsStore } from '../stores/accounts';
import { useTransactionsStore } from '../stores/transactions';
import { useSystemStore } from '../stores/system';
import { useProfilesStore } from '../stores/profiles';
import { useSharedFiltersStore, normalizeSharedPreset } from '../stores/filters';
import SharedFilterToolbar from '../components/SharedFilterToolbar.vue';
import ReconcileAccountModal from '../components/ReconcileAccountModal.vue';
import EditTransactionModal from '../components/EditTransactionModal.vue';
import BulkEditTransactionsModal from '../components/BulkEditTransactionsModal.vue';
import BulkDeleteConfirmationModal from '../components/BulkDeleteConfirmationModal.vue';
import type { Account, Transaction, TransactionType, ExpenseNature } from '../types';

const route = useRoute();
const router = useRouter();
const accountsStore = useAccountsStore();
const txStore = useTransactionsStore();
const systemStore = useSystemStore();
const profilesStore = useProfilesStore();
const sharedFilters = useSharedFiltersStore();

const baseCurrencySymbol = computed(() => systemStore.config?.base_currency_symbol || '£');
const baseCurrencyCode = computed(() => systemStore.config?.base_currency || 'GBP');

const txToDelete = ref<Transaction | null>(null);
const isReconcileOpen = ref(false);
const reconcilingAccount = ref<Account | null>(null);
const isEditModalOpen = ref(false);
const txToEdit = ref<Transaction | null>(null);
const isBulkEditOpen = ref(false);

// Export Menu State
const isExportOpen = ref(false);
const isStickyExportOpen = ref(false);
const isExporting = ref(false);
const exportDropdownRef = ref<HTMLElement | null>(null);
const stickyExportDropdownRef = ref<HTMLElement | null>(null);

// Sortable Table Headings Configuration & Logic
type LedgerSortField = 'date' | 'amount' | 'category' | 'account';
const DEFAULT_SORT_DIRECTIONS: Record<LedgerSortField, 'asc' | 'desc'> = {
  date: 'desc',
  amount: 'desc',
  category: 'asc',
  account: 'asc',
};

const ledgerTableColumns: Array<{
  key: string;
  label: string;
  sortField?: LedgerSortField;
  align?: 'left' | 'right' | 'center';
  extraClass?: string;
}> = [
  { key: 'date', label: 'Date', sortField: 'date', align: 'left' },
  { key: 'description', label: 'Description', align: 'left' },
  { key: 'category', label: 'Category', sortField: 'category', align: 'left' },
  { key: 'nature', label: 'Nature', align: 'left' },
  { key: 'account', label: 'Account', sortField: 'account', align: 'left' },
  { key: 'amount', label: 'Amount', sortField: 'amount', align: 'right' },
  { key: 'actions', label: 'Actions', align: 'center', extraClass: 'w-20' },
];

function toggleHeadingSort(field: LedgerSortField) {
  const nextOrder: 'asc' | 'desc' =
    txStore.sortBy === field
      ? txStore.sortOrder === 'asc'
        ? 'desc'
        : 'asc'
      : DEFAULT_SORT_DIRECTIONS[field];
  txStore.setSort(field, nextOrder);
  updateRouteQuery();
}

function getAriaSort(field: LedgerSortField): 'ascending' | 'descending' | 'none' {
  if (txStore.sortBy !== field) return 'none';
  return txStore.sortOrder === 'asc' ? 'ascending' : 'descending';
}

function getSortHeadingAriaLabel(field: LedgerSortField, label: string): string {
  if (txStore.sortBy === field) {
    const curDir = txStore.sortOrder === 'asc' ? 'ascending' : 'descending';
    const nextDir = txStore.sortOrder === 'asc' ? 'descending' : 'ascending';
    return `Sort by ${label}, currently ${curDir}. Click to sort ${nextDir}.`;
  }
  const defDir = DEFAULT_SORT_DIRECTIONS[field] === 'asc' ? 'ascending' : 'descending';
  return `Sort by ${label} (${defDir}).`;
}

// Sorting Helpers
function handleSortSelect(e: Event) {
  const target = e.target as HTMLSelectElement;
  const val = target.value;
  const [field, order] = val.split('_') as [string, 'asc' | 'desc'];
  txStore.setSort(field, order);
  updateRouteQuery();
}

function resetSort() {
  txStore.setSort('date', 'desc');
  updateRouteQuery();
}

const formatSortLabel = computed(() => {
  const by = txStore.sortBy;
  const ord = txStore.sortOrder;
  if (by === 'amount') return `Amount (${ord === 'asc' ? 'Lowest first' : 'Highest first'})`;
  if (by === 'category') return `Category (${ord === 'asc' ? 'A-Z' : 'Z-A'})`;
  if (by === 'account') return `Account (${ord === 'asc' ? 'A-Z' : 'Z-A'})`;
  return `Date (${ord === 'asc' ? 'Oldest first' : 'Newest first'})`;
});

// Mobile compact toolbar state
const isMobileFiltersOpen = ref(false);

const activeFilterCount = computed(() => {
  let count = 0;
  if (txStore.filters.q && txStore.filters.q.trim()) count++;
  if (sharedFilters.accountIds.length > 0) count += sharedFilters.accountIds.length;
  if (sharedFilters.categoryIds.length > 0) count += sharedFilters.categoryIds.length;
  if (txStore.filters.transactionType) count++;
  if (txStore.filters.expenseNature) count++;
  if (txStore.filters.status && txStore.filters.status !== 'all') count++;
  if (sharedFilters.dateOffset !== 0) count++;
  if (normalizeSharedPreset(sharedFilters.datePreset) === 'custom') count++;
  if (txStore.sortBy !== 'date' || txStore.sortOrder !== 'desc') count++;
  return count;
});

function handlePageSizeSelect(e: Event) {
  const target = e.target as HTMLSelectElement;
  changePageSize(Number(target.value));
}

// Shared Filter Toolbar Event Handlers
function handleSharedPresetChange(preset: string) {
  txStore.syncFiltersFromShared();
  if (preset === 'custom' && !sharedFilters.customStartDate && !sharedFilters.customEndDate) {
    return;
  }
  txStore.clearSelection();
  updateRouteQuery();
  txStore.loadTransactions(0);
}

function handleSharedRefresh() {
  txStore.syncFiltersFromShared();
  txStore.clearSelection();
  updateRouteQuery();
  txStore.loadTransactions(0);
}

function handleSharedIntervalChange() {
  txStore.filters.interval = sharedFilters.interval;
  updateRouteQuery();
}

// Document click listener to close export popovers
function handleDocumentClick(e: MouseEvent) {
  const target = e.target as Node;
  if (isExportOpen.value && exportDropdownRef.value && !exportDropdownRef.value.contains(target)) {
    isExportOpen.value = false;
  }
  if (isStickyExportOpen.value && stickyExportDropdownRef.value && !stickyExportDropdownRef.value.contains(target)) {
    isStickyExportOpen.value = false;
  }
}

onMounted(async () => {
  document.addEventListener('click', handleDocumentClick);
  txStore.loadSavedSort();
  if (accountsStore.accounts.length === 0) {
    accountsStore.loadData();
  }
  if (txStore.categories.length === 0) {
    await txStore.loadCategories();
  }
  if (!systemStore.config) {
    systemStore.loadConfig();
  }
  syncFiltersFromRoute();
  txStore.loadTransactions(0);
  txStore.loadDeletedSummary();
});

onUnmounted(() => {
  document.removeEventListener('click', handleDocumentClick);
});

// Clear stale URL filters on workspace switch so new profile's preferences aren't overwritten
watch(() => profilesStore.activeProfile?.id, (newId, oldId) => {
  if (oldId && newId && newId !== oldId) {
    if (Object.keys(route.query).length > 0) {
      isUpdatingRoute = true;
      router.replace({ query: {} }).finally(() => {
        isUpdatingRoute = false;
      });
    }
  }
});

// Bulk selection helpers
const selectedCount = computed(() => txStore.selectedIds.size);

const isCurrentPageAllSelected = computed(() => {
  return txStore.transactions.length > 0 && txStore.transactions.every(t => txStore.isRowSelected(t.id));
});

const isCurrentPagePartiallySelected = computed(() => {
  const count = txStore.transactions.filter(t => txStore.isRowSelected(t.id)).length;
  return count > 0 && count < txStore.transactions.length;
});

function toggleSelectCurrentPage() {
  if (isCurrentPageAllSelected.value) {
    txStore.deselectCurrentPage();
  } else {
    txStore.selectCurrentPage();
  }
}

function openBulkEditModal() {
  isBulkEditOpen.value = true;
}

async function handleBulkUpdated() {
  await Promise.all([
    accountsStore.loadData(),
    txStore.loadTransactions(txStore.offset),
  ]);
}

const isBulkDeleteModalOpen = ref(false);

function openBulkDeleteModal() {
  isBulkDeleteModalOpen.value = true;
}

async function handleConfirmBulkDelete() {
  isBulkDeleteModalOpen.value = false;
  await txStore.bulkDelete();
}

function switchTab(tab: 'active' | 'deleted') {
  txStore.activeLedgerTab = tab;
  if (tab === 'deleted') {
    txStore.loadDeletedSummary();
    txStore.loadDeletedTransactions(0);
  } else {
    txStore.loadTransactions();
  }
}

// Deleted View Helpers
function formatDeletedTimestamp(isoStr: string): string {
  try {
    const d = new Date(isoStr);
    return d.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return isoStr;
  }
}

const currentDeletedPage = computed(() => {
  return Math.floor(txStore.deletedOffset / txStore.deletedLimit) + 1;
});

const totalDeletedPages = computed(() => {
  return Math.max(1, Math.ceil(txStore.deletedTotal / txStore.deletedLimit));
});

function prevDeletedPage() {
  const newOffset = Math.max(0, txStore.deletedOffset - txStore.deletedLimit);
  txStore.loadDeletedTransactions(newOffset);
}

function nextDeletedPage() {
  const newOffset = txStore.deletedOffset + txStore.deletedLimit;
  if (newOffset < txStore.deletedTotal) {
    txStore.loadDeletedTransactions(newOffset);
  }
}

let deletedSearchTimer: any = null;
function handleDeletedSearch() {
  if (deletedSearchTimer) clearTimeout(deletedSearchTimer);
  deletedSearchTimer = setTimeout(() => {
    txStore.loadDeletedTransactions(0);
  }, 250);
}

const isDeletedPageAllSelected = computed(() => {
  return (
    txStore.deletedTransactions.length > 0 &&
    txStore.deletedTransactions.every(t => txStore.isDeletedRowSelected(t.id))
  );
});

function toggleSelectDeletedPage() {
  if (isDeletedPageAllSelected.value) {
    txStore.deselectCurrentDeletedPage();
  } else {
    txStore.selectCurrentDeletedPage();
  }
}

async function handleSingleRestore(tx: Transaction) {
  await txStore.restoreTransactions([tx.id]);
}

async function handleBulkRestore() {
  const ids = Array.from(txStore.deletedSelectedIds);
  if (ids.length === 0) return;
  await txStore.restoreTransactions(ids);
}

function openEditModal(tx: Transaction) {
  txToEdit.value = tx;
  isEditModalOpen.value = true;
}

async function handleTxEdited() {
  await Promise.all([
    accountsStore.loadData(),
    txStore.loadTransactions(txStore.offset),
  ]);
}

const selectedNonInvestmentAccount = computed(() => {
  const ids = effectiveSelectedAccountIds.value;
  if (ids.length === 1 && typeof ids[0] === 'number') {
    const acc = accountsStore.accounts.find(a => a.id === ids[0]);
    return acc && acc.account_type !== 'investment' ? acc : null;
  }
  return null;
});

function openReconcileModal(acc: Account) {
  reconcilingAccount.value = acc;
  isReconcileOpen.value = true;
}

async function handleReconciled() {
  await Promise.all([
    accountsStore.loadData(),
    txStore.loadTransactions(txStore.offset)
  ]);
}

// Shared Account & Category References
const effectiveSelectedAccountIds = computed<(number | string)[]>(() => sharedFilters.accountIds);
const effectiveSelectedCategoryIds = computed<(number | string)[]>(() => sharedFilters.categoryIds);

const selectedCategoryFilterValue = computed({
  get() {
    if (txStore.filters.uncategorizedOnly || txStore.filters.categoryId === 'uncategorized' || sharedFilters.isUncategorizedSelected) {
      return 'uncategorized';
    }
    return txStore.filters.categoryId ?? null;
  },
  set(val: any) {
    if (val === 'uncategorized') {
      txStore.filters.uncategorizedOnly = true;
      txStore.filters.categoryId = 'uncategorized';
      sharedFilters.selectAllCategories([0]);
      txStore.filters.categoryIds = ['uncategorized'];
      handleFilterChange();
    } else if (val !== null && val !== undefined && val !== '') {
      txStore.filters.uncategorizedOnly = false;
      txStore.filters.categoryId = Number(val);
      sharedFilters.selectAllCategories([Number(val)]);
      txStore.filters.categoryIds = [Number(val)];
      handleFilterChange();
    } else {
      clearCategoryFilter();
    }
  }
});

function clearCategoryFilter() {
  sharedFilters.clearCategories();
  txStore.filters.categoryId = null;
  txStore.filters.uncategorizedOnly = false;
  txStore.filters.categoryIds = [];
  handleFilterChange();
}

// Transaction Type Filter
const selectedTypeFilterValue = computed({
  get() {
    return txStore.filters.transactionType || 'all';
  },
  set(val: string) {
    txStore.filters.transactionType = val === 'all' ? null : (val as TransactionType);
  }
});

function handleTypeFilterChange() {
  handleFilterChange();
}

function clearTypeFilter() {
  txStore.filters.transactionType = null;
  handleFilterChange();
}

// Activity Status Filter
const selectedStatusFilterValue = computed({
  get() {
    return txStore.filters.status || 'all';
  },
  set(val: string) {
    txStore.filters.status = val === 'all' ? null : val;
  }
});

function handleStatusFilterChange() {
  handleFilterChange();
}

function clearStatusFilter() {
  txStore.filters.status = null;
  handleFilterChange();
}

// Ledger-Only Active Filter State Check
const hasLedgerSpecificFilters = computed(() => {
  const f = txStore.filters;
  return Boolean(
    f.transactionType !== null ||
    f.expenseNature !== null ||
    (f.status && f.status !== 'all') ||
    (f.q && f.q.trim()) ||
    txStore.sortBy !== 'date' ||
    txStore.sortOrder !== 'desc'
  );
});

function resetLedgerOnlyControls() {
  txStore.clearSelection();
  txStore.filters.q = '';
  txStore.filters.transactionType = null;
  txStore.filters.expenseNature = null;
  txStore.filters.status = 'all';
  txStore.sortBy = 'date';
  txStore.sortOrder = 'desc';
  txStore.saveSort();
  updateRouteQuery();
  txStore.loadTransactions(0);
}

// Combined Active Filter Check (Shared + Ledger-Specific, used for empty state recovery)
const hasActiveFilters = computed(() => {
  const preset = normalizeSharedPreset(sharedFilters.datePreset);
  return Boolean(
    effectiveSelectedAccountIds.value.length > 0 ||
    effectiveSelectedCategoryIds.value.length > 0 ||
    hasLedgerSpecificFilters.value ||
    preset !== 'all' ||
    sharedFilters.dateOffset !== 0 ||
    txStore.filters.startDate ||
    txStore.filters.endDate
  );
});

// URL Query String Sync with loop guard
let isUpdatingRoute = false;

function updateRouteQuery() {
  const nextQuery: Record<string, string> = {};

  const accs = effectiveSelectedAccountIds.value;
  if (accs.length > 0) {
    nextQuery.account_ids = accs.join(',');
  }

  const cats = effectiveSelectedCategoryIds.value;
  if (
    txStore.filters.uncategorizedOnly ||
    txStore.filters.categoryId === 'uncategorized' ||
    (cats.length === 1 && (cats[0] === 0 || cats[0] === 'uncategorized'))
  ) {
    nextQuery.category_id = 'uncategorized';
  } else if (cats.length > 0) {
    nextQuery.category_ids = cats.join(',');
  }

  if (txStore.filters.transactionType) {
    nextQuery.type = txStore.filters.transactionType;
  }
  if (txStore.filters.expenseNature) {
    nextQuery.nature = txStore.filters.expenseNature;
  }
  if (txStore.filters.status && txStore.filters.status !== 'all') {
    nextQuery.status = txStore.filters.status;
  }

  const curPreset = normalizeSharedPreset(sharedFilters.datePreset);
  if (curPreset !== 'all') {
    nextQuery.date_preset = curPreset;
  }
  if (sharedFilters.dateOffset !== 0) {
    nextQuery.date_offset = String(sharedFilters.dateOffset);
  }
  if (sharedFilters.interval) {
    nextQuery.interval = sharedFilters.interval;
  }
  if (curPreset === 'custom') {
    if (sharedFilters.customStartDate) nextQuery.start_date = sharedFilters.customStartDate;
    if (sharedFilters.customEndDate) nextQuery.end_date = sharedFilters.customEndDate;
  }

  if (txStore.sortBy !== 'date') {
    nextQuery.sort_by = txStore.sortBy;
  }
  if (txStore.sortOrder !== 'desc') {
    nextQuery.sort_order = txStore.sortOrder;
  }
  if (txStore.filters.q && txStore.filters.q.trim()) {
    nextQuery.q = txStore.filters.q.trim();
  }

  const curStr = JSON.stringify(route.query);
  const nextStr = JSON.stringify(nextQuery);
  if (curStr !== nextStr) {
    isUpdatingRoute = true;
    router.replace({ query: nextQuery }).finally(() => {
      isUpdatingRoute = false;
    });
  }
}

function syncFiltersFromRoute() {
  sharedFilters.applyFromRoute(route.query);

  const hasExplicitQuery = Object.keys(route.query).length > 0;

  // Ledger-specific params (clear stale values cleanly when arriving via deep link)
  if (route.query.type !== undefined) {
    txStore.filters.transactionType = (route.query.type as TransactionType) || null;
  } else if (hasExplicitQuery) {
    txStore.filters.transactionType = null;
  }

  if (route.query.nature !== undefined) {
    txStore.filters.expenseNature = (route.query.nature as ExpenseNature) || null;
  } else if (hasExplicitQuery) {
    txStore.filters.expenseNature = null;
  }

  if (route.query.status !== undefined) {
    txStore.filters.status = String(route.query.status) || 'all';
  } else if (hasExplicitQuery) {
    txStore.filters.status = 'all';
  }

  if (route.query.q !== undefined) {
    txStore.filters.q = String(route.query.q);
  } else if (hasExplicitQuery) {
    txStore.filters.q = '';
  }

  // Explicit category=uncategorized URL handling for compatibility & direct bookmarks
  if (route.query.category_id !== undefined) {
    const rawVal = String(route.query.category_id).trim().toLowerCase();
    if (rawVal === '0' || rawVal === 'uncategorised' || rawVal === 'uncategorized') {
      txStore.filters.uncategorizedOnly = true;
      txStore.filters.categoryId = 'uncategorized';
    } else {
      txStore.filters.uncategorizedOnly = false;
      const cid = Number(rawVal);
      txStore.filters.categoryId = (!isNaN(cid) && cid > 0) ? cid : null;
    }
  } else {
    txStore.filters.uncategorizedOnly = false;
    txStore.filters.categoryId = null;
  }

  if (route.query.sort_by !== undefined && typeof route.query.sort_by === 'string') {
    txStore.sortBy = route.query.sort_by;
  }
  if (route.query.sort_order === 'asc' || route.query.sort_order === 'desc') {
    txStore.sortOrder = route.query.sort_order;
  }

  txStore.syncFiltersFromShared();
}

watch(() => route.query, () => {
  if (isUpdatingRoute) return;
  syncFiltersFromRoute();
  txStore.loadTransactions(0);
});

let searchTimeout: any = null;

function handleSearchInput() {
  txStore.clearSelection();
  updateRouteQuery();
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(() => {
    txStore.loadTransactions(0);
  }, 250);
}

function handleFilterChange() {
  txStore.clearSelection();
  updateRouteQuery();
  txStore.loadTransactions(0);
}

function clearSearch() {
  txStore.clearSelection();
  txStore.filters.q = '';
  updateRouteQuery();
  txStore.loadTransactions(0);
}

function setNatureFilter(nature: ExpenseNature | null) {
  txStore.clearSelection();
  txStore.filters.expenseNature = nature;
  updateRouteQuery();
  txStore.loadTransactions(0);
}

function resetAllFilters() {
  sharedFilters.resetAllFilters();
  sharedFilters.setPreset('all');
  isUpdatingRoute = true;
  router.replace({ query: {} }).finally(() => {
    isUpdatingRoute = false;
  });
  txStore.resetFilters();
}

// Page Size & Pagination
const paginationStart = computed(() => {
  if (txStore.total === 0) return 0;
  return txStore.offset + 1;
});

const paginationEnd = computed(() => {
  return Math.min(txStore.offset + txStore.limit, txStore.total);
});

const currentPage = computed(() => {
  if (txStore.limit <= 0) return 1;
  return Math.floor(txStore.offset / txStore.limit) + 1;
});

const totalPages = computed(() => {
  if (txStore.limit <= 0 || txStore.total === 0) return 1;
  return Math.ceil(txStore.total / txStore.limit);
});

function changePageSize(newSize: number) {
  txStore.setPageSize(newSize);
}

function prevPage() {
  const newOffset = Math.max(0, txStore.offset - txStore.limit);
  txStore.loadTransactions(newOffset);
}

function nextPage() {
  if (txStore.offset + txStore.limit < txStore.total) {
    txStore.loadTransactions(txStore.offset + txStore.limit);
  }
}

// Export Handling
async function handleExport(format: 'csv' | 'xlsx') {
  isExporting.value = true;
  isExportOpen.value = false;
  isStickyExportOpen.value = false;
  try {
    await txStore.exportLedger(format);
  } catch (err: any) {
    console.error('Export failed', err);
    alert(`Failed to export ledger: ${err.message || err}`);
  } finally {
    isExporting.value = false;
  }
}

// Delete handling
function promptDelete(tx: Transaction) {
  txToDelete.value = tx;
}

async function confirmDelete() {
  if (!txToDelete.value) return;
  const id = txToDelete.value.id;
  txToDelete.value = null;
  await txStore.deleteTransaction(id);
}

// Formatting helpers
function getAmountClass(type: TransactionType): string {
  switch (type) {
    case 'expense':
      return 'text-rose-600 dark:text-rose-400';
    case 'income':
      return 'text-emerald-600 dark:text-emerald-400';
    case 'transfer':
      return 'text-indigo-600 dark:text-indigo-400';
    default:
      return 'text-slate-800 dark:text-slate-200';
  }
}

function formatTxAmount(tx: Transaction): string {
  if (tx.transaction_type === 'expense') {
    return `-${tx.formatted_amount}`;
  } else if (tx.transaction_type === 'income') {
    return `+${tx.formatted_amount}`;
  }
  return tx.formatted_amount;
}

function formatDate(dateStr: string): string {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric'
  });
}
</script>
