<template>
  <div class="space-y-2.5" @keydown.esc="closePopovers">
    <!-- Shared Two-Panel Row: Panel 1 (Period) + Panel 2 (Filters) -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-2.5 items-stretch">
      
      <!-- ================================================================== -->
      <!-- PANEL 1: PERIOD                                                    -->
      <!-- ================================================================== -->
      <section
        data-testid="shared-period-panel"
        aria-label="Shared period controls"
        class="lg:col-span-7 bg-white dark:bg-brand-darksurface rounded-2xl border border-brand-border dark:border-brand-darkborder shadow-xs p-3 flex flex-col justify-between gap-2.5 min-w-0"
      >
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="flex items-center gap-2">
            <span class="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Period
            </span>
            <span
              v-if="resolvedRangeText"
              data-testid="period-resolved-range"
              class="px-2 py-0.5 rounded-full text-[11px] font-medium bg-black/[0.04] dark:bg-white/[0.06] text-slate-600 dark:text-slate-300 tabular-nums truncate max-w-[220px] sm:max-w-none"
            >
              {{ resolvedRangeText }}
            </span>
          </div>

          <!-- Prev / Current / Next Period Navigation -->
          <div
            v-if="sharedFilters.datePreset !== 'all' && sharedFilters.datePreset !== 'custom'"
            class="inline-flex items-center gap-0.5 bg-black/[0.04] dark:bg-white/[0.05] p-0.5 rounded-xl border border-black/5 dark:border-white/5 shrink-0"
          >
            <button
              type="button"
              data-testid="period-nav-prev"
              @click="handleNavigate(-1)"
              :disabled="isNavPreviousDisabled || isLoading"
              class="px-2 py-1 rounded-lg text-xs font-semibold flex items-center gap-1 transition-all disabled:opacity-35 disabled:cursor-not-allowed text-slate-800 dark:text-slate-200 hover:bg-white dark:hover:bg-white/10"
              title="Previous period"
              aria-label="Previous period"
            >
              <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
              </svg>
              <span class="hidden sm:inline">Prev</span>
            </button>

            <button
              v-if="sharedFilters.dateOffset !== 0"
              type="button"
              data-testid="period-nav-current"
              @click="handleResetOffset"
              class="px-2 py-1 rounded-lg text-[11px] font-bold bg-slate-900/10 dark:bg-white/15 text-slate-900 dark:text-white hover:bg-slate-900/15 dark:hover:bg-white/20 transition-colors"
              title="Return to current period"
            >
              Current
            </button>

            <button
              type="button"
              data-testid="period-nav-next"
              @click="handleNavigate(1)"
              :disabled="isNavNextDisabled || isLoading"
              class="px-2 py-1 rounded-lg text-xs font-semibold flex items-center gap-1 transition-all disabled:opacity-35 disabled:cursor-not-allowed text-slate-800 dark:text-slate-200 hover:bg-white dark:hover:bg-white/10"
              title="Next period (cannot exceed current)"
              aria-label="Next period"
            >
              <span class="hidden sm:inline">Next</span>
              <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
              </svg>
            </button>
          </div>
        </div>

        <!-- Presets Row -->
        <div
          role="group"
          aria-label="Date range presets"
          class="flex flex-wrap items-center gap-0.5 bg-black/[0.04] dark:bg-white/[0.05] p-1 rounded-xl border border-black/5 dark:border-white/5"
        >
          <button
            v-for="p in presetOptions"
            :key="p.value"
            type="button"
            :data-testid="`preset-btn-${p.value}`"
            @click="handleSelectPreset(p.value)"
            :aria-pressed="normalizedActivePreset === p.value"
            :class="[
              'px-2.5 py-1 rounded-lg text-xs font-semibold transition-all whitespace-nowrap',
              normalizedActivePreset === p.value
                ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-950 shadow-xs'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5'
            ]"
          >
            {{ p.label }}
          </button>
        </div>

        <!-- Bottom Row: Group-By Interval & Custom Date Inputs -->
        <div class="flex flex-wrap items-center justify-between gap-2">
          <!-- Group By Interval -->
          <div class="inline-flex flex-wrap items-center gap-1.5 bg-black/[0.04] dark:bg-white/[0.05] px-2.5 py-1 rounded-xl border border-black/5 dark:border-white/5">
            <span class="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Group by
            </span>
            <div class="flex flex-wrap items-center gap-0.5" role="group" aria-label="Group by interval">
              <button
                v-for="intv in intervalOptionsList"
                :key="intv.value"
                type="button"
                :data-testid="`interval-btn-${intv.value}`"
                @click="handleSelectInterval(intv.value)"
                :aria-pressed="effectiveInterval === intv.value"
                :class="[
                  'px-2 py-0.5 rounded-md text-xs font-semibold transition-all',
                  effectiveInterval === intv.value
                    ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-950 font-bold shadow-2xs'
                    : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5'
                ]"
              >
                {{ intv.label }}
              </button>
            </div>
          </div>

          <!-- Inline Custom Date Inputs -->
          <div
            v-if="normalizedActivePreset === 'custom'"
            data-testid="custom-date-range-inputs"
            class="flex flex-wrap items-center gap-1.5"
          >
            <input
              type="date"
              v-model="localCustomStartDate"
              aria-label="Custom start date"
              class="px-2 py-1 rounded-lg bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder text-xs text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-slate-400"
            />
            <span class="text-xs text-slate-500">to</span>
            <input
              type="date"
              v-model="localCustomEndDate"
              aria-label="Custom end date"
              class="px-2 py-1 rounded-lg bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder text-xs text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-slate-400"
            />
            <button
              type="button"
              data-testid="apply-custom-date-btn"
              @click="applyCustomDates"
              class="px-3 py-1 rounded-lg bg-slate-900 text-white dark:bg-white dark:text-slate-950 text-xs font-bold hover:opacity-90 transition-opacity"
            >
              Apply
            </button>
          </div>
        </div>
      </section>

      <!-- ================================================================== -->
      <!-- PANEL 2: FILTERS                                                   -->
      <!-- ================================================================== -->
      <section
        data-testid="shared-filters-panel"
        aria-label="Shared account and category filters"
        class="lg:col-span-5 bg-white dark:bg-brand-darksurface rounded-2xl border border-brand-border dark:border-brand-darkborder shadow-xs p-3 flex flex-col justify-between gap-2.5 min-w-0"
      >
        <div class="flex items-center justify-between gap-2">
          <span class="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            Filters
          </span>

          <button
            v-if="hasActiveFilterChips"
            type="button"
            data-testid="reset-all-filters-btn"
            @click="handleResetAll"
            class="text-xs font-bold text-rose-600 dark:text-rose-400 hover:underline flex items-center gap-1"
          >
            <span>Reset filters</span>
            <span aria-hidden="true">&times;</span>
          </button>
        </div>

        <!-- Account & Category Multi-Select Triggers -->
        <div class="flex flex-wrap items-center gap-2">
          
          <!-- Searchable Multi-Select Account Filter -->
          <div class="relative flex-1 min-w-[140px]" ref="accountDropdownRef">
            <button
              type="button"
              data-testid="account-multiselect-trigger"
              @click="toggleAccountPopover"
              :class="[
                'w-full inline-flex items-center justify-between gap-2 px-3 py-1.5 rounded-xl text-xs font-semibold border transition-all',
                sharedFilters.accountIds.length > 0
                  ? 'bg-slate-100 dark:bg-slate-800 border-slate-400 dark:border-slate-500 text-slate-900 dark:text-white shadow-xs'
                  : 'bg-white dark:bg-brand-darksurface border-brand-border dark:border-brand-darkborder text-slate-700 dark:text-slate-300 hover:border-slate-400 dark:hover:border-slate-500'
              ]"
              aria-haspopup="listbox"
              :aria-expanded="isAccountPopoverOpen"
            >
              <span class="inline-flex items-center gap-1.5 min-w-0">
                <svg class="w-3.5 h-3.5 text-slate-500 dark:text-slate-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
                </svg>
                <span class="truncate">{{ accountFilterSummaryLabel }}</span>
              </span>
              <span class="inline-flex items-center gap-1.5 shrink-0">
                <span
                  v-if="sharedFilters.accountIds.length > 0"
                  class="px-1.5 py-0.2 rounded-full text-[10px] font-bold bg-slate-900 text-white dark:bg-white dark:text-slate-900 tabular-nums"
                >
                  {{ sharedFilters.accountIds.length }}
                </span>
                <svg class="w-3.5 h-3.5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                </svg>
              </span>
            </button>

            <!-- Account Multi-Select Popover -->
            <div
              v-if="isAccountPopoverOpen"
              data-testid="account-multiselect-popover"
              class="absolute left-0 mt-1.5 w-72 sm:w-80 max-w-[calc(100vw-2rem)] rounded-2xl bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder shadow-xl z-50 p-3 space-y-2.5"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Filter Accounts{{ accountFilterCurrency ? ` (${accountFilterCurrency})` : '' }}
                </span>
                <div class="flex items-center gap-2 text-[11px] font-semibold">
                  <button
                    type="button"
                    @click="handleSelectAllAccounts"
                    class="text-emerald-600 dark:text-emerald-400 hover:underline"
                  >
                    Select all
                  </button>
                  <span class="text-slate-400">&middot;</span>
                  <button
                    type="button"
                    @click="handleClearAccounts"
                    class="text-slate-500 hover:text-slate-900 dark:hover:text-white"
                  >
                    Clear
                  </button>
                </div>
              </div>

              <!-- Search input -->
              <div class="relative">
                <input
                  v-model="accountSearchQuery"
                  type="text"
                  placeholder="Search accounts..."
                  aria-label="Search accounts"
                  class="w-full pl-8 pr-3 py-1.5 rounded-xl bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder text-xs text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
                <svg class="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </div>

              <!-- Options list -->
              <div role="listbox" aria-multiselectable="true" class="max-h-56 overflow-y-auto space-y-1">
                <!-- Optional Unassigned Option (enabled in Ledger) -->
                <label
                  v-if="allowUnassignedAccount && showUnassignedInAccountFilter"
                  :class="[
                    'flex items-center justify-between gap-2 py-2 px-2.5 rounded-xl cursor-pointer text-xs transition-colors border-l-4',
                    sharedFilters.isUnassignedAccountSelected
                      ? 'bg-slate-100 dark:bg-slate-800/80 font-semibold text-slate-900 dark:text-white'
                      : 'border-transparent hover:bg-slate-50 dark:hover:bg-slate-800/50 text-slate-700 dark:text-slate-300'
                  ]"
                  :style="{
                    borderLeftColor: sharedFilters.isUnassignedAccountSelected ? '#F59E0B' : 'transparent'
                  }"
                >
                  <div class="flex items-center gap-2 min-w-0">
                    <input
                      type="checkbox"
                      :checked="sharedFilters.isUnassignedAccountSelected"
                      @change="handleToggleAccount('unassigned')"
                      class="rounded border-slate-300 dark:border-slate-600 text-emerald-600 focus:ring-emerald-500"
                    />
                    <span class="w-2.5 h-2.5 rounded-full shrink-0 bg-amber-500"></span>
                    <span class="italic truncate">Unassigned</span>
                  </div>
                  <span class="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-700 dark:text-amber-300 font-medium shrink-0">
                    No Acct
                  </span>
                </label>

                <label
                  v-for="acc in filteredAccountOptions"
                  :key="acc.id"
                  :class="[
                    'flex items-center justify-between gap-2 py-2 px-2.5 rounded-xl cursor-pointer text-xs transition-colors border-l-4',
                    isAccountSelected(acc.id)
                      ? 'bg-slate-100 dark:bg-slate-800/80 font-semibold text-slate-900 dark:text-white'
                      : 'border-transparent hover:bg-slate-50 dark:hover:bg-slate-800/50 text-slate-700 dark:text-slate-300'
                  ]"
                  :style="{
                    borderLeftColor: isAccountSelected(acc.id) ? (acc.color || '#64748B') : 'transparent'
                  }"
                >
                  <div class="flex items-center gap-2 min-w-0">
                    <input
                      type="checkbox"
                      :checked="isAccountSelected(acc.id)"
                      @change="handleToggleAccount(acc.id)"
                      class="rounded border-slate-300 dark:border-slate-600 text-emerald-600 focus:ring-emerald-500"
                    />
                    <span
                      class="w-2.5 h-2.5 rounded-full shrink-0"
                      :style="{ backgroundColor: acc.color || '#64748B' }"
                    ></span>
                    <span class="truncate">{{ acc.name }}</span>
                  </div>
                  <span class="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-black/5 dark:bg-white/10 text-slate-500 dark:text-slate-400 shrink-0 font-medium">
                    {{ acc.account_type ? formatAccountTypeLabel(acc.account_type) : acc.currency }}
                  </span>
                </label>

                <div
                  v-if="!(allowUnassignedAccount && showUnassignedInAccountFilter) && filteredAccountOptions.length === 0"
                  class="py-4 text-center text-xs text-slate-500"
                >
                  No matching accounts found.
                </div>
              </div>
            </div>
          </div>

          <!-- Searchable Multi-Select Category Filter -->
          <div class="relative flex-1 min-w-[140px]" ref="categoryDropdownRef">
            <button
              type="button"
              data-testid="category-multiselect-trigger"
              @click="toggleCategoryPopover"
              :class="[
                'w-full inline-flex items-center justify-between gap-2 px-3 py-1.5 rounded-xl text-xs font-semibold border transition-all',
                sharedFilters.categoryIds.length > 0
                  ? 'bg-slate-100 dark:bg-slate-800 border-slate-400 dark:border-slate-500 text-slate-900 dark:text-white shadow-xs'
                  : 'bg-white dark:bg-brand-darksurface border-brand-border dark:border-brand-darkborder text-slate-700 dark:text-slate-300 hover:border-slate-400 dark:hover:border-slate-500'
              ]"
              aria-haspopup="listbox"
              :aria-expanded="isCategoryPopoverOpen"
            >
              <span class="inline-flex items-center gap-1.5 min-w-0">
                <svg class="w-3.5 h-3.5 text-slate-500 dark:text-slate-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
                </svg>
                <span class="truncate">{{ categoryFilterSummaryLabel }}</span>
              </span>
              <span class="inline-flex items-center gap-1.5 shrink-0">
                <span
                  v-if="sharedFilters.categoryIds.length > 0"
                  class="px-1.5 py-0.2 rounded-full text-[10px] font-bold bg-slate-900 text-white dark:bg-white dark:text-slate-900 tabular-nums"
                >
                  {{ sharedFilters.categoryIds.length }}
                </span>
                <svg class="w-3.5 h-3.5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                </svg>
              </span>
            </button>

            <!-- Category Multi-Select Popover -->
            <div
              v-if="isCategoryPopoverOpen"
              data-testid="category-multiselect-popover"
              class="absolute right-0 lg:right-0 mt-1.5 w-72 sm:w-80 max-w-[calc(100vw-2rem)] rounded-2xl bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder shadow-xl z-50 p-3 space-y-2.5"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Filter Categories
                </span>
                <div class="flex items-center gap-2 text-[11px] font-semibold">
                  <button
                    type="button"
                    @click="handleSelectAllCategories"
                    class="text-emerald-600 dark:text-emerald-400 hover:underline"
                  >
                    Select all
                  </button>
                  <span class="text-slate-400">&middot;</span>
                  <button
                    type="button"
                    @click="handleClearCategories"
                    class="text-slate-500 hover:text-slate-900 dark:hover:text-white"
                  >
                    Clear
                  </button>
                </div>
              </div>

              <!-- Search input -->
              <div class="relative">
                <input
                  v-model="categorySearchQuery"
                  type="text"
                  placeholder="Search categories..."
                  aria-label="Search categories"
                  class="w-full pl-8 pr-3 py-1.5 rounded-xl bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder text-xs text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
                <svg class="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </div>

              <!-- Options list (including Uncategorised = 0) -->
              <div role="listbox" aria-multiselectable="true" class="max-h-56 overflow-y-auto space-y-1">
                <label
                  v-if="showUncategorisedInCategoryFilter"
                  :class="[
                    'flex items-center justify-between gap-2 py-2 px-2.5 rounded-xl cursor-pointer text-xs transition-colors border-l-4',
                    sharedFilters.isUncategorizedSelected
                      ? 'bg-slate-100 dark:bg-slate-800/80 font-semibold text-slate-900 dark:text-white'
                      : 'border-transparent hover:bg-slate-50 dark:hover:bg-slate-800/50 text-slate-700 dark:text-slate-300'
                  ]"
                  :style="{
                    borderLeftColor: sharedFilters.isUncategorizedSelected ? '#94A3B8' : 'transparent'
                  }"
                >
                  <div class="flex items-center gap-2 min-w-0">
                    <input
                      type="checkbox"
                      :checked="sharedFilters.isUncategorizedSelected"
                      @change="handleToggleCategory(0)"
                      class="rounded border-slate-300 dark:border-slate-600 text-emerald-600 focus:ring-emerald-500"
                    />
                    <span class="w-2.5 h-2.5 rounded-full shrink-0 bg-slate-400"></span>
                    <span class="italic truncate">Uncategorised</span>
                  </div>
                  <span class="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-slate-500/10 text-slate-500 dark:text-slate-400 font-medium shrink-0">
                    Unclassified
                  </span>
                </label>

                <label
                  v-for="cat in filteredCategoryOptions"
                  :key="cat.id"
                  :class="[
                    'flex items-center justify-between gap-2 py-2 px-2.5 rounded-xl cursor-pointer text-xs transition-colors border-l-4',
                    isCategorySelected(cat.id)
                      ? 'bg-slate-100 dark:bg-slate-800/80 font-semibold text-slate-900 dark:text-white'
                      : 'border-transparent hover:bg-slate-50 dark:hover:bg-slate-800/50 text-slate-700 dark:text-slate-300'
                  ]"
                  :style="{
                    borderLeftColor: isCategorySelected(cat.id) ? (cat.color || '#8B5CF6') : 'transparent'
                  }"
                >
                  <div class="flex items-center gap-2 min-w-0">
                    <input
                      type="checkbox"
                      :checked="isCategorySelected(cat.id)"
                      @change="handleToggleCategory(cat.id)"
                      class="rounded border-slate-300 dark:border-slate-600 text-emerald-600 focus:ring-emerald-500"
                    />
                    <span
                      class="w-2.5 h-2.5 rounded-full shrink-0"
                      :style="{ backgroundColor: cat.color || '#8B5CF6' }"
                    ></span>
                    <span class="truncate">{{ cat.name }}</span>
                  </div>
                  <span
                    v-if="cat.category_type === 'income'"
                    class="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 shrink-0 font-medium"
                  >
                    Income
                  </span>
                  <span
                    v-else-if="cat.default_nature || cat.default_expense_nature"
                    class="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-black/5 dark:bg-white/10 text-slate-500 dark:text-slate-400 shrink-0 font-medium"
                  >
                    {{ cat.default_nature || cat.default_expense_nature }}
                  </span>
                </label>

                <div
                  v-if="!showUncategorisedInCategoryFilter && filteredCategoryOptions.length === 0"
                  class="py-4 text-center text-xs text-slate-500"
                >
                  No matching categories found.
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Unified Active Shared Filter Chips Row -->
        <div
          v-if="hasActiveFilterChips"
          data-testid="active-filter-chips-bar"
          class="flex flex-wrap items-center gap-1.5 pt-2 border-t border-brand-border/60 dark:border-brand-darkborder/60"
        >
          <span
            v-for="chip in activeChips"
            :key="chip.key"
            :data-testid="`shared-filter-chip-${chip.type}`"
            class="inline-flex items-center gap-1.5 pl-2.5 pr-1.5 py-0.5 rounded-full text-xs font-semibold text-slate-800 dark:text-slate-200 border transition-all shadow-2xs"
            :style="{
              backgroundColor: chip.color ? `${chip.color}18` : 'rgba(100, 116, 139, 0.10)',
              borderColor: chip.color ? `${chip.color}45` : 'rgba(100, 116, 139, 0.25)',
              borderLeftWidth: '3px',
              borderLeftColor: chip.color || '#64748B'
            }"
          >
            <span
              class="w-1.5 h-1.5 rounded-full shrink-0"
              :style="{ backgroundColor: chip.color || '#64748B' }"
            ></span>
            <span class="text-[10px] uppercase tracking-wider text-slate-500 dark:text-slate-400 font-bold">
              {{ chip.prefix }}:
            </span>
            <span class="truncate max-w-[140px]">{{ chip.label }}</span>
            <button
              type="button"
              @click="removeChip(chip)"
              :aria-label="`Remove ${chip.label} filter`"
              class="p-0.5 rounded-full hover:bg-black/10 dark:hover:bg-white/10 text-slate-400 hover:text-slate-700 dark:hover:text-white transition-colors"
            >
              <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </span>
        </div>
        <div
          v-else
          class="pt-1.5 border-t border-brand-border/40 dark:border-brand-darkborder/40 text-[11px] text-slate-400 dark:text-slate-500 flex items-center justify-between"
        >
          <span>All accounts &amp; categories included</span>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import {
  useSharedFiltersStore,
  SHARED_PRESET_OPTIONS,
  SHARED_INTERVAL_OPTIONS,
  normalizeSharedPreset,
  getDefaultIntervalForPreset,
} from '../stores/filters';

export interface SharedAccountItem {
  id: number;
  name: string;
  currency: string;
  account_type?: string;
  color?: string | null;
  is_active?: boolean;
}

export interface SharedCategoryItem {
  id: number;
  name: string;
  category_type?: string;
  default_nature?: string;
  default_expense_nature?: string;
  color?: string | null;
  is_active?: boolean;
}

interface UnifiedFilterChip {
  key: string;
  type: 'account' | 'category' | 'offset' | 'custom_date';
  prefix: string;
  id?: number | string;
  label: string;
  color: string;
}

const props = withDefaults(defineProps<{
  accounts: SharedAccountItem[];
  categories: SharedCategoryItem[];
  allowUnassignedAccount?: boolean;
  accountFilterCurrency?: string;
  canNavigatePrevious?: boolean;
  canNavigateNext?: boolean;
  isLoading?: boolean;
  resolvedStartDate?: string | null;
  resolvedEndDate?: string | null;
  resolvedInterval?: string | null;
}>(), {
  allowUnassignedAccount: false,
  accountFilterCurrency: '',
  canNavigatePrevious: true,
  canNavigateNext: false,
  isLoading: false,
  resolvedStartDate: null,
  resolvedEndDate: null,
  resolvedInterval: null,
});

const emit = defineEmits<{
  (e: 'preset-change', preset: string): void;
  (e: 'navigate-period', delta: number): void;
  (e: 'reset-offset'): void;
  (e: 'custom-range-apply', startDate: string, endDate: string): void;
  (e: 'interval-change', interval: string): void;
  (e: 'accounts-change'): void;
  (e: 'categories-change'): void;
  (e: 'reset-all'): void;
}>();

const sharedFilters = useSharedFiltersStore();

const presetOptions = SHARED_PRESET_OPTIONS;
const intervalOptionsList = SHARED_INTERVAL_OPTIONS;

const isAccountPopoverOpen = ref(false);
const isCategoryPopoverOpen = ref(false);
const accountSearchQuery = ref('');
const categorySearchQuery = ref('');
const accountDropdownRef = ref<HTMLElement | null>(null);
const categoryDropdownRef = ref<HTMLElement | null>(null);

const localCustomStartDate = ref(sharedFilters.customStartDate || '');
const localCustomEndDate = ref(sharedFilters.customEndDate || '');

watch(
  () => [sharedFilters.customStartDate, sharedFilters.customEndDate, props.resolvedStartDate, props.resolvedEndDate],
  () => {
    if (sharedFilters.customStartDate) {
      localCustomStartDate.value = sharedFilters.customStartDate;
    } else if (props.resolvedStartDate && !localCustomStartDate.value) {
      localCustomStartDate.value = props.resolvedStartDate;
    }
    if (sharedFilters.customEndDate) {
      localCustomEndDate.value = sharedFilters.customEndDate;
    } else if (props.resolvedEndDate && !localCustomEndDate.value) {
      localCustomEndDate.value = props.resolvedEndDate;
    }
  },
  { immediate: true }
);

const normalizedActivePreset = computed(() => normalizeSharedPreset(sharedFilters.datePreset));

const effectiveInterval = computed(() => {
  return sharedFilters.interval || props.resolvedInterval || getDefaultIntervalForPreset(normalizedActivePreset.value);
});

const resolvedRangeText = computed(() => {
  if (normalizedActivePreset.value === 'all' && !props.resolvedStartDate) {
    return 'All dates';
  }
  const start = props.resolvedStartDate || (normalizedActivePreset.value === 'custom' ? sharedFilters.customStartDate : null);
  const end = props.resolvedEndDate || (normalizedActivePreset.value === 'custom' ? sharedFilters.customEndDate : null);
  if (!start || !end) return '';
  try {
    const s = new Date(`${start}T12:00:00Z`);
    const e = new Date(`${end}T12:00:00Z`);
    const opt: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' };
    return `${s.toLocaleDateString('en-GB', opt)} – ${e.toLocaleDateString('en-GB', opt)}`;
  } catch {
    return `${start} – ${end}`;
  }
});

const isNavPreviousDisabled = computed(() => props.canNavigatePrevious === false);
const isNavNextDisabled = computed(() => props.canNavigateNext === false || sharedFilters.dateOffset >= 0);

function closePopovers() {
  isAccountPopoverOpen.value = false;
  isCategoryPopoverOpen.value = false;
}

function toggleAccountPopover() {
  isAccountPopoverOpen.value = !isAccountPopoverOpen.value;
  if (isAccountPopoverOpen.value) {
    isCategoryPopoverOpen.value = false;
  }
}

function toggleCategoryPopover() {
  isCategoryPopoverOpen.value = !isCategoryPopoverOpen.value;
  if (isCategoryPopoverOpen.value) {
    isAccountPopoverOpen.value = false;
  }
}

function handleDocumentClick(e: MouseEvent) {
  const target = e.target as Node | null;
  if (!target) return;
  if (isAccountPopoverOpen.value && accountDropdownRef.value && !accountDropdownRef.value.contains(target)) {
    isAccountPopoverOpen.value = false;
  }
  if (isCategoryPopoverOpen.value && categoryDropdownRef.value && !categoryDropdownRef.value.contains(target)) {
    isCategoryPopoverOpen.value = false;
  }
}

onMounted(() => {
  document.addEventListener('click', handleDocumentClick);
});

onUnmounted(() => {
  document.removeEventListener('click', handleDocumentClick);
});

// Period Handlers
function handleSelectPreset(preset: string) {
  sharedFilters.setPreset(preset);
  if (preset === 'custom') {
    if (!localCustomStartDate.value && props.resolvedStartDate) {
      localCustomStartDate.value = props.resolvedStartDate;
    }
    if (!localCustomEndDate.value && props.resolvedEndDate) {
      localCustomEndDate.value = props.resolvedEndDate;
    }
  }
  emit('preset-change', preset);
}

function handleNavigate(delta: number) {
  if (delta < 0 && isNavPreviousDisabled.value) return;
  if (delta > 0 && isNavNextDisabled.value) return;
  sharedFilters.navigateOffset(delta);
  emit('navigate-period', delta);
}

function handleResetOffset() {
  if (sharedFilters.dateOffset === 0) return;
  sharedFilters.resetOffset();
  emit('reset-offset');
}

function applyCustomDates() {
  let start = localCustomStartDate.value;
  let end = localCustomEndDate.value;
  if (start && end && start > end) {
    [start, end] = [end, start];
    localCustomStartDate.value = start;
    localCustomEndDate.value = end;
  }
  if (!start && !end) return;
  sharedFilters.setCustomDates(start, end);
  emit('custom-range-apply', start, end);
}

function handleSelectInterval(intv: string) {
  sharedFilters.setInterval(intv);
  emit('interval-change', intv);
}

// Accounts Filtering & Popover Helpers
const activeEligibleAccounts = computed(() => {
  return props.accounts.filter(a => a.is_active !== false);
});

const filteredAccountOptions = computed(() => {
  const q = accountSearchQuery.value.trim().toLowerCase();
  const list = activeEligibleAccounts.value;
  if (!q) return list;
  return list.filter(
    a =>
      a.name.toLowerCase().includes(q) ||
      (a.account_type && a.account_type.toLowerCase().includes(q)) ||
      a.currency.toLowerCase().includes(q)
  );
});

const showUnassignedInAccountFilter = computed(() => {
  const q = accountSearchQuery.value.trim().toLowerCase();
  if (!q) return true;
  return 'unassigned'.includes(q) || 'no account'.includes(q);
});

function isAccountSelected(id: number | string): boolean {
  return sharedFilters.accountIds.includes(id);
}

const accountFilterSummaryLabel = computed(() => {
  const ids = sharedFilters.accountIds;
  if (ids.length === 0) return 'All Accounts';
  if (ids.length === 1) return getAccountLabel(ids[0]);
  return `${ids.length} Accounts`;
});

function getAccountLabel(id: number | string): string {
  if (id === 'unassigned') return 'Unassigned';
  const acc = props.accounts.find(a => a.id === Number(id));
  return acc ? acc.name : `Account #${id}`;
}

function getAccountColor(id: number | string): string {
  if (id === 'unassigned') return '#F59E0B';
  const acc = props.accounts.find(a => a.id === Number(id));
  return acc?.color || '#64748B';
}

function formatAccountTypeLabel(t: string): string {
  if (t === 'credit_card') return 'Credit';
  if (t === 'investment') return 'Invest';
  if (t === 'cash') return 'Cash';
  return t;
}

function handleToggleAccount(id: number | string) {
  sharedFilters.toggleAccount(id);
  emit('accounts-change');
}

function handleSelectAllAccounts() {
  const ids: (number | string)[] = filteredAccountOptions.value.map(a => a.id);
  if (props.allowUnassignedAccount && showUnassignedInAccountFilter.value) {
    ids.push('unassigned');
  }
  sharedFilters.selectAllAccounts(ids);
  emit('accounts-change');
}

function handleClearAccounts() {
  if (sharedFilters.accountIds.length === 0) return;
  sharedFilters.clearAccounts();
  emit('accounts-change');
}

// Categories Filtering & Popover Helpers
const activeEligibleCategories = computed(() => {
  return props.categories.filter(c => c.is_active !== false);
});

const filteredCategoryOptions = computed(() => {
  const q = categorySearchQuery.value.trim().toLowerCase();
  const list = activeEligibleCategories.value;
  if (!q) return list;
  return list.filter(c => {
    const nature = (c.default_nature || c.default_expense_nature || '').toLowerCase();
    const purpose = (c.category_type || 'expense').toLowerCase();
    return c.name.toLowerCase().includes(q) || nature.includes(q) || purpose.includes(q);
  });
});

const showUncategorisedInCategoryFilter = computed(() => {
  const q = categorySearchQuery.value.trim().toLowerCase();
  if (!q) return true;
  return 'uncategorised'.includes(q) || 'uncategorized'.includes(q) || 'unclassified'.includes(q);
});

function isCategorySelected(id: number | string): boolean {
  if (id === 0 || id === 'uncategorized' || id === 'uncategorised') {
    return sharedFilters.isUncategorizedSelected;
  }
  return sharedFilters.categoryIds.includes(Number(id));
}

const categoryFilterSummaryLabel = computed(() => {
  const ids = sharedFilters.categoryIds;
  if (ids.length === 0) return 'All Categories';
  if (ids.length === 1) return getCategoryLabel(ids[0]);
  return `${ids.length} Categories`;
});

function getCategoryLabel(id: number | string): string {
  if (id === 0 || id === 'uncategorized' || id === 'uncategorised' || id === '0') return 'Uncategorised';
  const cat = props.categories.find(c => c.id === Number(id));
  return cat ? cat.name : `Category #${id}`;
}

function getCategoryColor(id: number | string): string {
  if (id === 0 || id === 'uncategorized' || id === 'uncategorised' || id === '0') return '#94A3B8';
  const cat = props.categories.find(c => c.id === Number(id));
  return cat?.color || '#8B5CF6';
}

function handleToggleCategory(id: number | string) {
  sharedFilters.toggleCategory(id);
  emit('categories-change');
}

function handleSelectAllCategories() {
  const ids: (number | string)[] = filteredCategoryOptions.value.map(c => c.id);
  if (showUncategorisedInCategoryFilter.value) {
    ids.unshift(0);
  }
  sharedFilters.selectAllCategories(ids);
  emit('categories-change');
}

function handleClearCategories() {
  if (sharedFilters.categoryIds.length === 0) return;
  sharedFilters.clearCategories();
  emit('categories-change');
}

// Active Shared Chips (Uniform Across Analysis and Ledger)
const activeChips = computed<UnifiedFilterChip[]>(() => {
  const chips: UnifiedFilterChip[] = [];

  for (const accId of sharedFilters.accountIds) {
    chips.push({
      key: `account-${accId}`,
      type: 'account',
      prefix: 'Acct',
      id: accId,
      label: getAccountLabel(accId),
      color: getAccountColor(accId),
    });
  }

  for (const catId of sharedFilters.categoryIds) {
    chips.push({
      key: `category-${catId}`,
      type: 'category',
      prefix: 'Cat',
      id: catId,
      label: getCategoryLabel(catId),
      color: getCategoryColor(catId),
    });
  }

  if (sharedFilters.dateOffset !== 0) {
    chips.push({
      key: `offset-${sharedFilters.dateOffset}`,
      type: 'offset',
      prefix: 'Window',
      label: `${Math.abs(sharedFilters.dateOffset)} period${Math.abs(sharedFilters.dateOffset) > 1 ? 's' : ''} back`,
      color: '#F59E0B',
    });
  }

  if (normalizedActivePreset.value === 'custom' && (sharedFilters.customStartDate || sharedFilters.customEndDate)) {
    chips.push({
      key: 'custom-date',
      type: 'custom_date',
      prefix: 'Dates',
      label: `${sharedFilters.customStartDate || '...'} to ${sharedFilters.customEndDate || '...'}`,
      color: '#10B981',
    });
  }

  return chips;
});

const hasActiveFilterChips = computed(() => activeChips.value.length > 0);

function removeChip(chip: UnifiedFilterChip) {
  if (chip.type === 'account' && chip.id !== undefined) {
    handleToggleAccount(chip.id);
  } else if (chip.type === 'category' && chip.id !== undefined) {
    handleToggleCategory(chip.id);
  } else if (chip.type === 'offset') {
    handleResetOffset();
  } else if (chip.type === 'custom_date') {
    sharedFilters.clearCustomDates();
    localCustomStartDate.value = '';
    localCustomEndDate.value = '';
    emit('preset-change', sharedFilters.datePreset);
  }
}

function handleResetAll() {
  sharedFilters.resetAllFilters();
  localCustomStartDate.value = '';
  localCustomEndDate.value = '';
  emit('reset-all');
}
</script>
