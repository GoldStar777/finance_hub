<template>
  <div class="space-y-6 pb-16 max-w-full" @keydown.esc="closeFilterPopovers">
    <!-- Page Title & Compact Context Header -->
    <header class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
      <div>
        <div class="flex items-center gap-2.5">
          <h1 class="text-2xl sm:text-3xl font-heading font-bold tracking-tight text-brand-forest dark:text-brand-cream">
            Financial Analysis
          </h1>
          <span
            v-if="analysisStore.data"
            class="px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-brand-sage/15 text-brand-sage border border-brand-sage/25 tabular-nums"
          >
            {{ formatRangeLabel(analysisStore.data.range_info.start_date, analysisStore.data.range_info.end_date) }}
          </span>
        </div>
        <p class="text-xs sm:text-sm text-brand-muted mt-0.5">
          Anchor-verified balances, transfer-neutral cash flow, and period-by-period spending comparison.
        </p>
      </div>

      <!-- Quick Ledger Drill-Through for Current Scope -->
      <div v-if="analysisStore.data" class="flex items-center gap-2 self-start sm:self-auto">
        <span class="text-[11px] text-brand-muted hidden md:inline">
          Timezone: <strong class="font-semibold text-brand-forest dark:text-brand-cream">{{ analysisStore.data.range_info.app_timezone }}</strong>
        </span>
        <router-link
          :to="getScopeLedgerUrl()"
          class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-black/5 dark:bg-white/5 hover:bg-brand-sage/15 text-brand-forest dark:text-brand-cream hover:text-brand-sage border border-black/10 dark:border-white/10 transition-colors"
        >
          <span>View Scope in Ledger</span>
          <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3" />
          </svg>
        </router-link>
      </div>
    </header>

    <!-- Persistent Sticky Analysis Control Dock -->
    <div
      data-testid="analysis-sticky-toolbar"
      class="sticky top-16 z-30 -mx-4 sm:-mx-6 px-4 sm:px-6 py-2.5 backdrop-blur-md bg-brand-cream/95 dark:bg-brand-darkbg/95 border-b border-brand-border/60 dark:border-brand-darkborder/60 transition-all shadow-xs space-y-2.5"
    >
      <!-- Mobile Compact Summary Strip (< md) -->
      <div class="flex md:hidden items-center justify-between gap-2 bg-white dark:bg-brand-darksurface rounded-2xl border border-brand-border dark:border-brand-darkborder px-3 py-2 shadow-xs">
        <div class="flex items-center gap-1.5 min-w-0">
          <span class="px-2 py-0.5 rounded-lg text-[10px] font-bold bg-slate-900 text-white dark:bg-white dark:text-slate-950 uppercase tracking-wider shrink-0">
            {{ activeSectionLabel }}
          </span>
          <span class="text-xs font-semibold text-slate-800 dark:text-slate-200 truncate">
            {{ shortRangeLabel }}
          </span>
          <span
            v-if="analysisStore.hasActiveFilters"
            class="px-1.5 py-0.2 rounded-full text-[10px] font-bold bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-500/30 shrink-0 tabular-nums"
          >
            {{ activeFilterCount }}
          </span>
        </div>
        <div class="flex items-center gap-1 shrink-0">
          <button
            v-if="analysisStore.data && analysisStore.selectedPreset !== 'all' && analysisStore.selectedPreset !== 'custom'"
            type="button"
            @click="analysisStore.navigatePeriod(-1)"
            :disabled="!analysisStore.data.range_info.can_navigate_previous || analysisStore.isLoading"
            class="p-1 rounded-lg text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-30 disabled:cursor-not-allowed"
            title="Previous period"
          >
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <button
            v-if="analysisStore.data && analysisStore.selectedPreset !== 'all' && analysisStore.selectedPreset !== 'custom'"
            type="button"
            @click="analysisStore.navigatePeriod(1)"
            :disabled="!analysisStore.data.range_info.can_navigate_next || analysisStore.isLoading"
            class="p-1 rounded-lg text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-30 disabled:cursor-not-allowed"
            title="Next period"
          >
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
            </svg>
          </button>
          <button
            type="button"
            @click="isMobileControlsExpanded = !isMobileControlsExpanded"
            class="inline-flex items-center gap-1 px-2.5 py-1 rounded-xl text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200 border border-brand-border dark:border-brand-darkborder hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
          >
            <span>Controls</span>
            <svg class="w-3.5 h-3.5 transition-transform" :class="{ 'rotate-180': isMobileControlsExpanded }" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
            </svg>
          </button>
        </div>
      </div>

      <!-- Expandable / Desktop Controls -->
      <div :class="[isMobileControlsExpanded ? 'block' : 'hidden md:block', 'space-y-2.5']">
        <!-- Tier 1: Shared Period & Filters Panels -->
        <SharedFilterToolbar
          :accounts="analysisStore.availableAccountsForCurrency"
          :categories="analysisStore.data?.available_categories || []"
          :allow-unassigned-account="false"
          :account-filter-currency="analysisStore.selectedCurrency || 'GBP'"
          :can-navigate-previous="analysisStore.data?.range_info.can_navigate_previous ?? true"
          :can-navigate-next="analysisStore.data?.range_info.can_navigate_next ?? false"
          :is-loading="analysisStore.isLoading"
          :resolved-start-date="analysisStore.data?.range_info.start_date || null"
          :resolved-end-date="analysisStore.data?.range_info.end_date || null"
          :resolved-interval="analysisStore.data?.range_info.interval || null"
          @preset-change="handleSharedPresetChange"
          @navigate-period="handleSharedRefresh"
          @reset-offset="handleSharedRefresh"
          @custom-range-apply="handleSharedRefresh"
          @interval-change="handleSharedRefresh"
          @accounts-change="handleSharedRefresh"
          @categories-change="handleSharedRefresh"
          @reset-all="handleSharedRefresh"
        />

        <!-- Tier 2: Independent Analysis Section & Currency Controls -->
        <div
          data-testid="analysis-page-controls"
          class="bg-slate-100/85 dark:bg-slate-900/60 rounded-2xl border border-brand-border/80 dark:border-brand-darkborder/80 px-3 py-2 flex flex-wrap items-center justify-between gap-2"
        >
          <div class="flex flex-wrap items-center gap-2 min-w-0 max-w-full">
            <span class="text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 hidden sm:inline shrink-0">
              Analysis
            </span>
            <nav
              aria-label="Analysis sections"
              class="flex items-center gap-1 bg-white/70 dark:bg-white/[0.04] p-1 rounded-xl border border-black/5 dark:border-white/5 overflow-x-auto max-w-full"
            >
              <button
                v-for="sec in sections"
                :key="sec.id"
                type="button"
                @click="analysisStore.setSection(sec.id)"
                :class="[
                  'px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 whitespace-nowrap',
                  analysisStore.activeSection === sec.id
                    ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-950 shadow-xs'
                    : 'text-slate-700 dark:text-slate-300 hover:text-slate-950 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5'
                ]"
              >
                <span>{{ sec.label }}</span>
              </button>
            </nav>
          </div>

          <div class="flex items-center gap-2 shrink-0">
            <select
              v-if="analysisStore.data && analysisStore.data.available_currencies.length > 1"
              :value="analysisStore.selectedCurrency"
              @change="analysisStore.setCurrency(($event.target as HTMLSelectElement).value)"
              aria-label="Currency filter"
              class="px-2.5 py-1.5 rounded-xl bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder text-xs font-semibold text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-emerald-500"
            >
              <option v-for="c in analysisStore.data.available_currencies" :key="c" :value="c">
                {{ c }}
              </option>
            </select>
          </div>
        </div>
      </div>
    </div>

    <!-- Loading Skeleton -->
    <div v-if="analysisStore.isLoading && !analysisStore.data" class="grid grid-cols-1 md:grid-cols-4 gap-4 animate-pulse">
      <div v-for="i in 4" :key="i" class="h-28 rounded-2xl bg-black/5 dark:bg-white/5"></div>
      <div class="md:col-span-4 h-80 rounded-2xl bg-black/5 dark:bg-white/5"></div>
    </div>

    <!-- Error State -->
    <div
      v-else-if="analysisStore.error"
      class="p-6 rounded-2xl bg-rose-500/10 border border-rose-500/20 text-rose-600 dark:text-rose-400 flex items-center justify-between"
    >
      <div>
        <h3 class="font-bold">Unable to load analysis</h3>
        <p class="text-sm mt-1">{{ analysisStore.error }}</p>
      </div>
      <button
        type="button"
        @click="analysisStore.loadAnalysis()"
        class="px-4 py-2 rounded-xl bg-rose-500 text-white text-xs font-bold"
      >
        Retry
      </button>
    </div>

    <!-- Main Analysis Content -->
    <template v-else-if="analysisStore.data">
      <!-- ====================================================================== -->
      <!-- SECTION 1: OVERVIEW & CASH FLOW                                        -->
      <!-- ====================================================================== -->
      <section v-if="analysisStore.activeSection === 'overview'" class="space-y-6">
        <!-- Headline KPI Cards (Clear Hierarchy) -->
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <!-- Operating Income -->
          <div class="bg-white dark:bg-brand-darkcard p-5 rounded-2xl border border-black/8 dark:border-white/10 shadow-xs">
            <div class="flex items-center justify-between">
              <span class="text-xs font-bold uppercase tracking-wider text-brand-muted">Operating Income</span>
              <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
            </div>
            <p class="text-2xl font-heading font-bold text-emerald-600 dark:text-emerald-400 mt-2 tabular-nums">
              {{ analysisStore.data.totals.formatted_income }}
            </p>
            <p class="text-[11px] text-brand-muted mt-1.5">
              External inflows across {{ analysisStore.data.time_series.length }} {{ analysisStore.data.range_info.interval }}s
            </p>
          </div>

          <!-- Operating Spending -->
          <div class="bg-white dark:bg-brand-darkcard p-5 rounded-2xl border border-black/8 dark:border-white/10 shadow-xs">
            <div class="flex items-center justify-between">
              <span class="text-xs font-bold uppercase tracking-wider text-brand-muted">Operating Spending</span>
              <span class="w-2 h-2 rounded-full bg-rose-500"></span>
            </div>
            <p class="text-2xl font-heading font-bold text-rose-600 dark:text-rose-400 mt-2 tabular-nums">
              {{ analysisStore.data.totals.formatted_expenses }}
            </p>
            <div class="flex items-center gap-2 text-[11px] text-brand-muted mt-1.5 tabular-nums">
              <span>Fixed {{ analysisStore.data.totals.fixed_percentage }}%</span>
              <span>·</span>
              <span>Variable {{ analysisStore.data.totals.variable_percentage }}%</span>
            </div>
          </div>

          <!-- Net Operating Savings -->
          <div class="bg-white dark:bg-brand-darkcard p-5 rounded-2xl border border-black/8 dark:border-white/10 shadow-xs">
            <div class="flex items-center justify-between">
              <span class="text-xs font-bold uppercase tracking-wider text-brand-muted">Net Cash Flow</span>
              <span
                v-if="analysisStore.data.totals.is_savings_rate_applicable"
                class="px-2 py-0.5 rounded-full text-[11px] font-bold bg-brand-sage/15 text-brand-sage tabular-nums"
              >
                {{ analysisStore.data.totals.savings_rate }}% saved
              </span>
            </div>
            <p
              :class="[
                'text-2xl font-heading font-bold mt-2 tabular-nums',
                analysisStore.data.totals.net_savings_pence >= 0
                  ? 'text-emerald-600 dark:text-emerald-400'
                  : 'text-rose-600 dark:text-rose-400'
              ]"
            >
              {{ analysisStore.data.totals.formatted_net_savings }}
            </p>
            <p class="text-[11px] text-brand-muted mt-1.5">
              Income minus operating spending (transfers = {{ analysisStore.data.currency_symbol }}0 impact)
            </p>
          </div>

          <!-- Latest Net Worth Position -->
          <div class="bg-white dark:bg-brand-darkcard p-5 rounded-2xl border border-black/8 dark:border-white/10 shadow-xs">
            <div class="flex items-center justify-between">
              <span class="text-xs font-bold uppercase tracking-wider text-brand-muted">Period-End Net Worth</span>
              <span
                v-if="latestNetWorthBucket?.has_inferred_balances"
                class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/15 text-amber-600 dark:text-amber-400"
              >
                Includes Inferred
              </span>
              <span
                v-else
                class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
              >
                Anchor-Verified
              </span>
            </div>
            <p class="text-2xl font-heading font-bold text-brand-forest dark:text-brand-cream mt-2 tabular-nums">
              {{ latestNetWorthBucket ? latestNetWorthBucket.formatted_net_worth : '—' }}
            </p>
            <p class="text-[11px] text-brand-muted mt-1.5 tabular-nums" v-if="latestNetWorthBucket">
              Assets {{ latestNetWorthBucket.formatted_total_assets }} · Debt {{ latestNetWorthBucket.formatted_total_debt }}
            </p>
          </div>
        </div>

        <!-- Financial Integrity & Accounting Separation Bar -->
        <div class="bg-white/70 dark:bg-brand-darkcard/70 px-4 py-3 rounded-2xl border border-black/8 dark:border-white/10 flex flex-wrap items-center justify-between gap-3 text-xs">
          <div class="flex items-center gap-2 text-brand-muted">
            <span class="px-2 py-0.5 rounded-md bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-bold text-[11px]">
              {{ analysisStore.data.currency_symbol }}0 Transfer Impact
            </span>
            <span>
              Internal transfers moved <strong class="text-brand-forest dark:text-brand-cream tabular-nums">{{ analysisStore.data.totals.formatted_transfers_volume }}</strong>
              ({{ analysisStore.data.totals.transfers_count }} transfers) and are strictly excluded from income &amp; spending.
            </span>
          </div>
          <div v-if="analysisStore.data.totals.adjustments_count > 0" class="text-brand-muted tabular-nums">
            Reconciliation adjustments (separated):
            <strong class="text-brand-forest dark:text-brand-cream">{{ analysisStore.data.totals.formatted_adjustments_net }}</strong>
            ({{ analysisStore.data.totals.adjustments_count }})
          </div>
        </div>

        <!-- Planned Activity & Forecast (Strictly Separated from Actuals) -->
        <div
          v-if="analysisStore.data.forecast?.has_planned_activity"
          data-testid="analysis-forecast-section"
          class="bg-white dark:bg-brand-darkcard p-5 sm:p-6 rounded-2xl border border-amber-500/20 bg-amber-500/[0.02] dark:border-amber-500/30 shadow-xs space-y-4"
        >
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <div class="flex items-center gap-2">
                <span class="text-base">📅</span>
                <h2 class="text-base sm:text-lg font-heading font-bold text-slate-900 dark:text-white">
                  Planned Activity &amp; Forecast
                </h2>
                <span class="px-2 py-0.5 rounded-full text-[11px] font-bold bg-amber-500/15 text-amber-700 dark:text-amber-400 font-mono">
                  {{ analysisStore.data.forecast.planned_transactions_count }} planned
                </span>
              </div>
              <p class="text-xs text-brand-muted mt-0.5">
                Future-dated activity within this analysis window. Planned activity is strictly isolated and does not alter completed cash flow or account balances until its effective date.
              </p>
            </div>
            <div class="flex items-center gap-3 text-xs shrink-0 font-mono">
              <span class="text-emerald-600 dark:text-emerald-400 font-semibold">
                +{{ analysisStore.data.forecast.formatted_planned_income }}
              </span>
              <span class="text-slate-300 dark:text-slate-700">·</span>
              <span class="text-rose-600 dark:text-rose-400 font-semibold">
                -{{ analysisStore.data.forecast.formatted_planned_expenses }}
              </span>
              <span class="text-slate-300 dark:text-slate-700">·</span>
              <span class="font-bold text-slate-800 dark:text-slate-200">
                Net {{ analysisStore.data.forecast.formatted_planned_net }}
              </span>
            </div>
          </div>

          <!-- Planned Items Table -->
          <div class="overflow-x-auto rounded-xl border border-brand-border/60 dark:border-brand-darkborder/60">
            <table class="w-full text-xs text-left">
              <thead class="bg-slate-50 dark:bg-slate-800/60 text-slate-500 font-mono uppercase text-[10px]">
                <tr>
                  <th class="py-2 px-3">Date</th>
                  <th class="py-2 px-3">Merchant / Payee</th>
                  <th class="py-2 px-3">Account</th>
                  <th class="py-2 px-3">Category</th>
                  <th class="py-2 px-3 text-right">Amount</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-brand-border/40 dark:divide-brand-darkborder/40">
                <tr
                  v-for="item in analysisStore.data.forecast.items"
                  :key="item.id"
                  class="hover:bg-slate-50/50 dark:hover:bg-slate-800/30"
                >
                  <td class="py-2 px-3 font-mono text-slate-500 whitespace-nowrap">
                    {{ item.date }}
                  </td>
                  <td class="py-2 px-3 font-medium text-slate-900 dark:text-white">
                    {{ item.merchant || 'Merchant not recorded' }}
                  </td>
                  <td class="py-2 px-3 text-slate-600 dark:text-slate-400">
                    {{ item.account_name }}
                  </td>
                  <td class="py-2 px-3 text-slate-600 dark:text-slate-400">
                    {{ item.category_name }}
                  </td>
                  <td
                    :class="[
                      'py-2 px-3 text-right font-mono font-semibold whitespace-nowrap',
                      item.transaction_type === 'income'
                        ? 'text-emerald-600 dark:text-emerald-400'
                        : 'text-rose-600 dark:text-rose-400'
                    ]"
                  >
                    {{ item.transaction_type === 'income' ? '+' : '-' }}{{ item.formatted_amount }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Chart 1: Cumulative Cash Flow Trajectory -->
        <div class="bg-white dark:bg-brand-darkcard p-5 sm:p-6 rounded-2xl border border-black/8 dark:border-white/10 shadow-xs space-y-4">
          <div class="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
            <div>
              <div class="flex items-center gap-2">
                <h2 class="text-base sm:text-lg font-heading font-bold text-brand-forest dark:text-brand-cream">
                  Cumulative Cash Flow Trajectory
                </h2>
                <span class="text-xs font-bold px-2 py-0.5 rounded-full bg-brand-sage/15 text-brand-sage tabular-nums">
                  Net: {{ analysisStore.data.totals.formatted_cumulative_net_flow }}
                </span>
              </div>
              <p class="text-xs text-brand-muted mt-0.5">
                <strong class="font-semibold text-brand-forest dark:text-brand-cream">Question answered:</strong>
                Is cumulative operating income staying ahead of cumulative spending across the selected range?
              </p>
            </div>

            <!-- Interactive Series Toggles -->
            <div class="flex flex-wrap items-center gap-1.5">
              <button
                type="button"
                @click="showCumulativeIncome = !showCumulativeIncome"
                :class="[
                  'px-2.5 py-1 rounded-lg text-xs font-semibold border transition-all flex items-center gap-1.5',
                  showCumulativeIncome
                    ? 'bg-emerald-500/10 border-emerald-500/40 text-emerald-700 dark:text-emerald-300'
                    : 'bg-black/5 dark:bg-white/5 border-transparent text-brand-muted opacity-60'
                ]"
              >
                <span class="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
                <span>Cumulative Income ({{ analysisStore.data.totals.formatted_cumulative_income }})</span>
              </button>

              <button
                type="button"
                @click="showCumulativeSpending = !showCumulativeSpending"
                :class="[
                  'px-2.5 py-1 rounded-lg text-xs font-semibold border transition-all flex items-center gap-1.5',
                  showCumulativeSpending
                    ? 'bg-rose-500/10 border-rose-500/40 text-rose-700 dark:text-rose-300'
                    : 'bg-black/5 dark:bg-white/5 border-transparent text-brand-muted opacity-60'
                ]"
              >
                <span class="w-2.5 h-2.5 rounded-full bg-rose-500"></span>
                <span>Cumulative Spending ({{ analysisStore.data.totals.formatted_cumulative_expenses }})</span>
              </button>

              <button
                type="button"
                @click="showCumulativeNetSavings = !showCumulativeNetSavings"
                :class="[
                  'px-2.5 py-1 rounded-lg text-xs font-semibold border transition-all flex items-center gap-1.5',
                  showCumulativeNetSavings
                    ? 'bg-blue-500/10 border-blue-500/40 text-blue-700 dark:text-blue-300'
                    : 'bg-black/5 dark:bg-white/5 border-transparent text-brand-muted opacity-60'
                ]"
              >
                <span class="w-2.5 h-2.5 rounded-full bg-blue-500"></span>
                <span>Net Flow ({{ analysisStore.data.totals.formatted_cumulative_net_flow }})</span>
              </button>
            </div>
          </div>

          <!-- Empty State -->
          <div
            v-if="analysisStore.data.time_series.length === 0"
            class="p-8 text-center rounded-2xl bg-slate-50 dark:bg-slate-800/40 border border-dashed border-slate-200 dark:border-slate-800 text-xs text-brand-muted"
          >
            No cash flow records found for this period. Adjust your date range or filters.
          </div>

          <!-- Single Point Checkpoint Banner -->
          <div
            v-else-if="cumulativeChartData.isSinglePoint && cumulativeChartData.points[0]"
            class="p-4 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/60 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs"
          >
            <div>
              <div class="font-bold text-slate-800 dark:text-slate-100 flex items-center gap-2">
                <span>Single Period Checkpoint:</span>
                <span class="font-mono text-brand-sage">{{ cumulativeChartData.points[0].label }}</span>
              </div>
              <p class="text-[11px] text-brand-muted mt-0.5">Select a wider range or smaller grouping interval (e.g. Day or Week) to explore trajectory over time.</p>
            </div>
            <div class="flex items-center gap-3 font-mono font-bold">
              <span class="text-emerald-500">Income: {{ cumulativeChartData.points[0].formatted_income }}</span>
              <span class="text-rose-500">Spend: {{ cumulativeChartData.points[0].formatted_expenses }}</span>
              <span :class="cumulativeChartData.points[0].net_savings_pence >= 0 ? 'text-blue-500' : 'text-rose-500'">Net: {{ cumulativeChartData.points[0].formatted_net_savings }}</span>
            </div>
          </div>

          <div
            v-if="analysisStore.data.time_series.length > 0"
            class="w-full overflow-x-auto pb-2"
          >
            <div class="relative min-w-[640px]" :style="{ width: cumulativeChartData.width + 'px', height: '240px' }">
              <svg :width="cumulativeChartData.width" :height="cumulativeChartData.height" class="overflow-visible" role="region" aria-label="Cumulative Cash Flow Line Chart">
                <!-- Grid Lines and Y-Axis Ticks -->
                <g v-for="tick in cumulativeChartData.scale.ticks" :key="tick.valuePence">
                  <line
                    :x1="cumulativeChartData.paddingLeft"
                    :y1="tick.y"
                    :x2="cumulativeChartData.width - cumulativeChartData.paddingRight"
                    :y2="tick.y"
                    :stroke="tick.isZero ? 'currentColor' : 'currentColor'"
                    :class="tick.isZero ? 'text-slate-400 dark:text-slate-500' : 'text-slate-200/80 dark:text-slate-800/80'"
                    :stroke-dasharray="tick.isZero ? 'none' : '3 3'"
                    :stroke-width="tick.isZero ? 1.5 : 1"
                  />
                  <text
                    :x="cumulativeChartData.paddingLeft - 10"
                    :y="tick.y + 3.5"
                    text-anchor="end"
                    class="text-[10px] fill-slate-500 dark:fill-slate-400 font-mono font-medium select-none"
                  >
                    {{ tick.formattedLabel }}
                  </text>
                </g>

                <!-- Cumulative Income Line (Solid actuals, dashed planned forecast) -->
                <template v-if="showCumulativeIncome">
                  <path
                    v-for="(p, i) in cumulativeChartData.incomeSolidPaths"
                    :key="'inc-s-' + i"
                    :d="p"
                    fill="none"
                    stroke="#10B981"
                    stroke-width="2.5"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                  <path
                    v-for="(p, i) in cumulativeChartData.incomeDashedPaths"
                    :key="'inc-d-' + i"
                    :d="p"
                    fill="none"
                    stroke="#10B981"
                    stroke-width="2.5"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-dasharray="5 4"
                  />
                </template>

                <!-- Cumulative Spending Line (Solid actuals, dashed planned forecast) -->
                <template v-if="showCumulativeSpending">
                  <path
                    v-for="(p, i) in cumulativeChartData.spendingSolidPaths"
                    :key="'sp-s-' + i"
                    :d="p"
                    fill="none"
                    stroke="#F43F5E"
                    stroke-width="2.5"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                  <path
                    v-for="(p, i) in cumulativeChartData.spendingDashedPaths"
                    :key="'sp-d-' + i"
                    :d="p"
                    fill="none"
                    stroke="#F43F5E"
                    stroke-width="2.5"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-dasharray="5 4"
                  />
                </template>

                <!-- Cumulative Net Flow Line (Solid actuals, dashed planned forecast) -->
                <template v-if="showCumulativeNetSavings">
                  <path
                    v-for="(p, i) in cumulativeChartData.netSavingsSolidPaths"
                    :key="'net-s-' + i"
                    :d="p"
                    fill="none"
                    stroke="#3B82F6"
                    stroke-width="2.5"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                  <path
                    v-for="(p, i) in cumulativeChartData.netSavingsDashedPaths"
                    :key="'net-d-' + i"
                    :d="p"
                    fill="none"
                    stroke="#3B82F6"
                    stroke-width="2.5"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-dasharray="5 4"
                  />
                </template>

                <!-- Interactive Points & X-axis Ticks -->
                <g v-for="(pt, idx) in cumulativeChartData.points" :key="idx">
                  <!-- Vertical Guideline on Focus / Hover -->
                  <line
                    v-if="hoveredCumulativeIdx === idx"
                    :x1="pt.x"
                    :y1="cumulativeChartData.paddingTop"
                    :x2="pt.x"
                    :y2="cumulativeChartData.bottomY"
                    stroke="currentColor"
                    class="text-brand-sage/60 dark:text-brand-sage/80"
                    stroke-width="1.25"
                    stroke-dasharray="3 3"
                  />

                  <!-- Point Markers with Distinct Styles for Actual vs Planned -->
                  <circle
                    v-if="showCumulativeIncome"
                    :cx="pt.x"
                    :cy="pt.yIncome"
                    :r="hoveredCumulativeIdx === idx ? 5.5 : 3.5"
                    :fill="pt.is_planned ? 'white' : '#10B981'"
                    :stroke="'#10B981'"
                    :stroke-width="pt.is_planned ? 2 : 1"
                    class="transition-all"
                  />
                  <circle
                    v-if="showCumulativeSpending"
                    :cx="pt.x"
                    :cy="pt.ySpending"
                    :r="hoveredCumulativeIdx === idx ? 5.5 : 3.5"
                    :fill="pt.is_planned ? 'white' : '#F43F5E'"
                    :stroke="'#F43F5E'"
                    :stroke-width="pt.is_planned ? 2 : 1"
                    class="transition-all"
                  />
                  <circle
                    v-if="showCumulativeNetSavings"
                    :cx="pt.x"
                    :cy="pt.yNetSavings"
                    :r="hoveredCumulativeIdx === idx ? 5.5 : 3.5"
                    :fill="pt.is_planned ? 'white' : (pt.net_savings_pence >= 0 ? '#3B82F6' : '#E11D48')"
                    :stroke="pt.net_savings_pence >= 0 ? '#3B82F6' : '#E11D48'"
                    :stroke-width="pt.is_planned ? 2 : 1"
                    class="transition-all"
                  />

                  <!-- Accessible Interactive Hit Target -->
                  <rect
                    :x="pt.x - 18"
                    :y="cumulativeChartData.paddingTop"
                    width="36"
                    :height="cumulativeChartData.bottomY - cumulativeChartData.paddingTop"
                    fill="transparent"
                    class="cursor-pointer focus:outline-none"
                    tabindex="0"
                    role="button"
                    :aria-label="pt.accessibilityLabel"
                    @mouseenter="hoveredCumulativeIdx = idx"
                    @mouseleave="hoveredCumulativeIdx = null"
                    @focus="hoveredCumulativeIdx = idx"
                    @blur="hoveredCumulativeIdx = null"
                    @keydown.left.prevent="navigateChartPoint(idx, -1, cumulativeChartData.points.length, (i) => hoveredCumulativeIdx = i)"
                    @keydown.right.prevent="navigateChartPoint(idx, 1, cumulativeChartData.points.length, (i) => hoveredCumulativeIdx = i)"
                  />

                  <!-- X-Axis Date Labels -->
                  <g
                    v-if="shouldShowTick(idx, cumulativeChartData.points.length)"
                    :transform="`translate(${pt.x}, ${cumulativeChartData.height - 22})`"
                  >
                    <text text-anchor="middle" class="text-[10px] fill-brand-muted font-medium select-none">
                      {{ getAxisLabelParts(pt.label, pt.start_date).line1 }}
                    </text>
                    <text
                      v-if="getAxisLabelParts(pt.label, pt.start_date).line2"
                      y="12"
                      text-anchor="middle"
                      class="text-[9px] fill-brand-muted/80 select-none"
                    >
                      {{ getAxisLabelParts(pt.label, pt.start_date).line2 }}
                    </text>
                  </g>
                </g>
              </svg>

              <!-- Safe Bounded Hover Tooltip -->
              <div
                v-if="hoveredCumulativeIdx !== null && cumulativeChartData.points[hoveredCumulativeIdx]"
                class="absolute z-30 pointer-events-none bg-brand-darkbg text-white px-3.5 py-2.5 rounded-xl text-xs shadow-xl border border-white/15 space-y-1"
                :style="getCumulativeTooltipStyle(cumulativeChartData.points[hoveredCumulativeIdx])"
              >
                <div class="flex items-center justify-between gap-3 border-b border-white/10 pb-1">
                  <span class="font-bold text-brand-sage">{{ cumulativeChartData.points[hoveredCumulativeIdx].label }}</span>
                  <span v-if="cumulativeChartData.points[hoveredCumulativeIdx].is_planned" class="px-1.5 py-0.5 rounded text-[10px] bg-amber-500/20 text-amber-300 font-semibold uppercase">
                    Planned
                  </span>
                </div>
                <p v-if="showCumulativeIncome" class="text-[11px] flex items-center justify-between gap-4">
                  <span class="text-emerald-400">Cum. Income:</span>
                  <span class="font-mono font-bold">{{ cumulativeChartData.points[hoveredCumulativeIdx].formatted_income }}</span>
                </p>
                <p v-if="showCumulativeSpending" class="text-[11px] flex items-center justify-between gap-4">
                  <span class="text-rose-400">Cum. Spending:</span>
                  <span class="font-mono font-bold">{{ cumulativeChartData.points[hoveredCumulativeIdx].formatted_expenses }}</span>
                </p>
                <p v-if="showCumulativeNetSavings" class="text-[11px] flex items-center justify-between gap-4">
                  <span class="text-blue-400">Cum. Net Flow:</span>
                  <span class="font-mono font-bold">{{ cumulativeChartData.points[hoveredCumulativeIdx].formatted_net_savings }}</span>
                </p>
              </div>
            </div>
          </div>
        </div>

        <!-- Chart 2: Period Income vs Spending Bar Chart -->
        <div class="bg-white dark:bg-brand-darkcard p-5 sm:p-6 rounded-2xl border border-black/8 dark:border-white/10 shadow-xs space-y-4">
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div>
              <h2 class="text-base sm:text-lg font-heading font-bold text-brand-forest dark:text-brand-cream">
                Income vs. Operating Spending by Period
              </h2>
              <p class="text-xs text-brand-muted mt-0.5">
                <strong class="font-semibold text-brand-forest dark:text-brand-cream">Question answered:</strong>
                Which individual periods generated an operating surplus or deficit?
              </p>
            </div>
            <div class="flex items-center gap-4 text-xs">
              <span class="flex items-center gap-1.5 text-brand-muted">
                <span class="w-2.5 h-2.5 rounded-xs bg-emerald-500"></span> Income
              </span>
              <span class="flex items-center gap-1.5 text-brand-muted">
                <span class="w-2.5 h-2.5 rounded-xs bg-rose-500"></span> Spending
              </span>
            </div>
          </div>

          <div v-if="analysisStore.data.time_series.length > 0" class="w-full overflow-x-auto pb-2">
            <div
              class="flex items-end gap-2 min-h-[190px] pt-8 pb-2 px-2"
              :style="{ minWidth: Math.max(100, analysisStore.data.time_series.length * 46) + 'px' }"
            >
              <router-link
                v-for="(b, idx) in analysisStore.data.time_series"
                :key="b.key"
                :to="getBucketLedgerUrl(b)"
                class="flex-1 min-w-[34px] flex flex-col items-center group relative focus:outline-none"
              >
                <!-- Hover Tooltip -->
                <div class="opacity-0 group-hover:opacity-100 group-focus:opacity-100 transition-opacity absolute -top-6 z-20 pointer-events-none bg-brand-darkbg text-white px-2.5 py-1.5 rounded-lg text-[10px] shadow-md whitespace-nowrap">
                  <p class="font-bold">{{ b.label }}</p>
                  <p class="text-emerald-400">In: {{ b.formatted_income }}</p>
                  <p class="text-rose-400">Out: {{ b.formatted_expenses }}</p>
                  <p class="font-bold">Net: {{ b.formatted_net_savings }}</p>
                </div>

                <div class="w-full h-32 flex items-end justify-center gap-1 border-b border-black/10 dark:border-white/10 pb-1">
                  <div
                    class="w-3 max-w-[14px] bg-emerald-500/85 group-hover:bg-emerald-500 rounded-t transition-all"
                    :style="{ height: getBarHeight(b.income_pence) + '%' }"
                  ></div>
                  <div
                    class="w-3 max-w-[14px] bg-rose-500/85 group-hover:bg-rose-500 rounded-t transition-all"
                    :style="{ height: getBarHeight(b.expenses_pence) + '%' }"
                  ></div>
                </div>

                <div
                  v-if="shouldShowTick(idx, analysisStore.data.time_series.length)"
                  class="mt-1.5 text-center leading-tight"
                >
                  <span class="block text-[10px] text-brand-muted font-medium">
                    {{ getAxisLabelParts(b.label, b.start_date).line1 }}
                  </span>
                  <span
                    v-if="getAxisLabelParts(b.label, b.start_date).line2"
                    class="block text-[9px] text-brand-muted/75"
                  >
                    {{ getAxisLabelParts(b.label, b.start_date).line2 }}
                  </span>
                </div>
              </router-link>
            </div>
          </div>
        </div>

        <!-- Table: Cash Flow & Cumulative Trajectory by Period (With CSV & XLSX Export) -->
        <div class="bg-white dark:bg-brand-darkcard rounded-2xl border border-black/8 dark:border-white/10 shadow-xs overflow-hidden">
          <div class="p-4 sm:p-5 border-b border-black/5 dark:border-white/5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h3 class="text-base font-heading font-bold text-brand-forest dark:text-brand-cream">
                Period Cash Flow &amp; Cumulative Breakdown
              </h3>
              <p class="text-xs text-brand-muted mt-0.5">
                Complete interval table with operating income, spending, net savings, and running cumulative totals.
              </p>
            </div>

            <!-- Export Menu -->
            <div class="relative inline-block text-left self-start sm:self-auto" data-export-menu>
              <button
                type="button"
                data-testid="export-overview-menu-trigger"
                @click="toggleExportMenu('overview')"
                :disabled="analysisStore.isExporting"
                class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-200 border border-brand-border dark:border-brand-darkborder hover:bg-slate-50 dark:hover:bg-slate-700 shadow-xs transition-colors disabled:opacity-50"
                aria-haspopup="true"
                :aria-expanded="openExportMenu === 'overview'"
              >
                <svg class="w-3.5 h-3.5 text-slate-500 dark:text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                <span>Export</span>
                <svg class="w-3 h-3 text-slate-400 transition-transform" :class="{ 'rotate-180': openExportMenu === 'overview' }" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              <div
                v-if="openExportMenu === 'overview'"
                class="absolute right-0 mt-1.5 w-44 rounded-xl bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder shadow-xl z-30 py-1"
              >
                <button
                  type="button"
                  data-testid="export-overview-csv"
                  @click="triggerExport('overview_cashflow', 'csv')"
                  class="w-full text-left px-3 py-2 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center justify-between"
                >
                  <span>CSV Spreadsheet</span>
                  <span class="text-[10px] font-mono text-slate-400 uppercase">.csv</span>
                </button>
                <button
                  type="button"
                  data-testid="export-overview-xlsx"
                  @click="triggerExport('overview_cashflow', 'xlsx')"
                  class="w-full text-left px-3 py-2 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center justify-between border-t border-slate-100 dark:border-slate-800"
                >
                  <span>Excel Workbook</span>
                  <span class="text-[10px] font-mono text-emerald-600 dark:text-emerald-400 font-bold uppercase">.xlsx</span>
                </button>
              </div>
            </div>
          </div>

          <div class="overflow-x-auto max-h-[420px]">
            <table class="w-full text-left border-collapse text-xs">
              <thead class="sticky top-0 z-10 bg-brand-cream dark:bg-brand-darkbg border-b border-black/10 dark:border-white/10 text-[11px] uppercase tracking-wider text-brand-muted">
                <tr>
                  <th class="py-3 px-4 font-bold">Period</th>
                  <th class="py-3 px-4 font-bold text-right">Income</th>
                  <th class="py-3 px-4 font-bold text-right">Spending</th>
                  <th class="py-3 px-4 font-bold text-right">Net Savings</th>
                  <th class="py-3 px-4 font-bold text-right">Cum. Income</th>
                  <th class="py-3 px-4 font-bold text-right">Cum. Spending</th>
                  <th class="py-3 px-4 font-bold text-right">Cum. Net Flow</th>
                  <th class="py-3 px-4 font-bold text-right">Savings Rate</th>
                  <th class="py-3 px-4 font-bold text-right">Transfers (Excl.)</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-black/5 dark:divide-white/5 tabular-nums">
                <tr
                  v-for="b in analysisStore.data.time_series"
                  :key="b.key"
                  class="hover:bg-black/[0.02] dark:hover:bg-white/[0.02]"
                >
                  <td class="py-2.5 px-4 font-semibold text-brand-forest dark:text-brand-cream whitespace-nowrap">
                    <router-link :to="getBucketLedgerUrl(b)" class="hover:text-brand-sage hover:underline">
                      {{ b.label }}
                    </router-link>
                    <span
                      v-if="b.is_partial"
                      class="ml-1.5 px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-600 dark:text-amber-400 text-[10px]"
                    >
                      Partial
                    </span>
                  </td>
                  <td class="py-2.5 px-4 text-right text-emerald-600 dark:text-emerald-400 font-medium">{{ b.formatted_income }}</td>
                  <td class="py-2.5 px-4 text-right text-rose-600 dark:text-rose-400 font-medium">{{ b.formatted_expenses }}</td>
                  <td
                    :class="[
                      'py-2.5 px-4 text-right font-bold',
                      b.net_savings_pence >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'
                    ]"
                  >
                    {{ b.formatted_net_savings }}
                  </td>
                  <td class="py-2.5 px-4 text-right text-brand-muted">{{ b.formatted_cumulative_income }}</td>
                  <td class="py-2.5 px-4 text-right text-brand-muted">{{ b.formatted_cumulative_expenses }}</td>
                  <td
                    :class="[
                      'py-2.5 px-4 text-right font-bold',
                      b.cumulative_net_flow_pence >= 0 ? 'text-blue-600 dark:text-blue-400' : 'text-rose-600 dark:text-rose-400'
                    ]"
                  >
                    {{ b.formatted_cumulative_net_flow }}
                  </td>
                  <td class="py-2.5 px-4 text-right text-brand-muted">
                    {{ b.is_savings_rate_applicable ? `${b.savings_rate}%` : 'N/A' }}
                  </td>
                  <td class="py-2.5 px-4 text-right text-brand-muted">{{ b.formatted_transfers_volume }}</td>
                </tr>
              </tbody>
              <tfoot class="sticky bottom-0 bg-brand-cream dark:bg-brand-darkbg border-t-2 border-black/15 dark:border-white/15 font-bold tabular-nums">
                <tr>
                  <td class="py-3 px-4 text-brand-forest dark:text-brand-cream">Range Total</td>
                  <td class="py-3 px-4 text-right text-emerald-600 dark:text-emerald-400">{{ analysisStore.data.totals.formatted_income }}</td>
                  <td class="py-3 px-4 text-right text-rose-600 dark:text-rose-400">{{ analysisStore.data.totals.formatted_expenses }}</td>
                  <td class="py-3 px-4 text-right">{{ analysisStore.data.totals.formatted_net_savings }}</td>
                  <td class="py-3 px-4 text-right">{{ analysisStore.data.totals.formatted_cumulative_income }}</td>
                  <td class="py-3 px-4 text-right">{{ analysisStore.data.totals.formatted_cumulative_expenses }}</td>
                  <td class="py-3 px-4 text-right text-blue-600 dark:text-blue-400">{{ analysisStore.data.totals.formatted_cumulative_net_flow }}</td>
                  <td class="py-3 px-4 text-right">
                    {{ analysisStore.data.totals.is_savings_rate_applicable ? `${analysisStore.data.totals.savings_rate}%` : 'N/A' }}
                  </td>
                  <td class="py-3 px-4 text-right text-brand-muted">{{ analysisStore.data.totals.formatted_transfers_volume }}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>

        <!-- Income Breakdown by Category (Separate from Expense Spending) -->
        <div
          v-if="(analysisStore.data.income_categories?.length || 0) > 0"
          data-testid="income-categories-card"
          class="bg-white dark:bg-brand-darksurface rounded-2xl border border-brand-border dark:border-brand-darkborder shadow-xs p-5 sm:p-6 space-y-4"
        >
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h3 class="text-base font-heading font-bold text-slate-900 dark:text-white">
                Income Breakdown by Category
              </h3>
              <p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                Operating inflows across income categories in this range (Total: <strong class="text-emerald-600 dark:text-emerald-400">{{ analysisStore.data.totals.formatted_income }}</strong>).
              </p>
            </div>
            <div class="relative inline-block text-left" data-export-menu>
              <button
                type="button"
                data-testid="export-income-menu-trigger"
                @click="toggleExportMenu('income_categories')"
                :disabled="analysisStore.isExporting"
                class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-200 border border-brand-border dark:border-brand-darkborder hover:bg-slate-50 dark:hover:bg-slate-700 shadow-xs transition-colors disabled:opacity-50"
                aria-haspopup="true"
                :aria-expanded="openExportMenu === 'income_categories'"
              >
                <svg class="w-3.5 h-3.5 text-slate-500 dark:text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                <span>Export Income</span>
              </button>
              <div
                v-if="openExportMenu === 'income_categories'"
                class="absolute right-0 mt-1.5 w-48 rounded-xl bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder shadow-xl z-30 py-1"
              >
                <button
                  type="button"
                  @click="triggerExport('income_categories', 'csv')"
                  class="w-full text-left px-3 py-2 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center justify-between"
                >
                  <span>Summary (CSV)</span>
                  <span class="text-[10px] font-mono text-slate-400 uppercase">.csv</span>
                </button>
                <button
                  type="button"
                  @click="triggerExport('income_categories', 'xlsx')"
                  class="w-full text-left px-3 py-2 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center justify-between border-t border-slate-100 dark:border-slate-800"
                >
                  <span>Summary (Excel)</span>
                  <span class="text-[10px] font-mono text-emerald-600 dark:text-emerald-400 font-bold uppercase">.xlsx</span>
                </button>
                <button
                  type="button"
                  @click="triggerExport('income_matrix', 'xlsx')"
                  class="w-full text-left px-3 py-2 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center justify-between border-t border-slate-100 dark:border-slate-800"
                >
                  <span>Period Matrix (Excel)</span>
                  <span class="text-[10px] font-mono text-emerald-600 dark:text-emerald-400 font-bold uppercase">.xlsx</span>
                </button>
              </div>
            </div>
          </div>

          <div class="space-y-2.5 divide-y divide-black/5 dark:divide-white/5">
            <div
              v-for="cat in analysisStore.data.income_categories"
              :key="cat.category_id ?? 'uncat_income'"
              class="pt-2.5 first:pt-0 space-y-1"
            >
              <div class="flex items-center justify-between text-xs">
                <div class="flex items-center gap-2 min-w-0">
                  <span class="w-2.5 h-2.5 rounded-full shrink-0" :style="{ backgroundColor: cat.category_color }"></span>
                  <button
                    type="button"
                    @click="analysisStore.toggleCategoryFilter(cat.category_id ?? 0)"
                    class="font-semibold text-slate-900 dark:text-white hover:text-emerald-600 dark:hover:text-emerald-400 truncate text-left"
                    :title="`Filter Analysis by ${cat.category_name}`"
                  >
                    {{ cat.category_name }}
                  </button>
                  <span class="text-[10px] text-slate-400">({{ cat.transaction_count }} tx)</span>
                </div>
                <div class="flex items-center gap-2 shrink-0 tabular-nums">
                  <span class="font-bold text-emerald-600 dark:text-emerald-400">{{ cat.formatted_total }}</span>
                  <span class="text-[11px] text-slate-500 w-10 text-right">{{ cat.percentage }}%</span>
                </div>
              </div>
              <div class="w-full h-1.5 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                <div
                  class="h-full rounded-full transition-all"
                  :style="{ width: `${Math.max(2, cat.percentage)}%`, backgroundColor: cat.category_color || '#10B981' }"
                ></div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ====================================================================== -->
      <!-- SECTION 2: SPENDING ANALYSIS (Matrix + Composition Mix + Trend View)   -->
      <!-- ====================================================================== -->
      <section v-else-if="analysisStore.activeSection === 'spending'" class="space-y-6">
        <!-- Headline Spending KPIs -->
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div class="bg-white dark:bg-brand-darkcard p-5 rounded-2xl border border-black/8 dark:border-white/10 shadow-xs">
            <span class="text-xs font-bold uppercase tracking-wider text-brand-muted">Total Operating Spend</span>
            <p class="text-2xl font-heading font-bold text-rose-600 dark:text-rose-400 mt-1.5 tabular-nums">
              {{ analysisStore.data.totals.formatted_expenses }}
            </p>
            <p class="text-[11px] text-brand-muted mt-1">
              Across {{ analysisStore.data.categories.length }} active spending categories
            </p>
          </div>

          <div class="bg-white dark:bg-brand-darkcard p-5 rounded-2xl border border-black/8 dark:border-white/10 shadow-xs">
            <div class="flex items-center justify-between">
              <span class="text-xs font-bold uppercase tracking-wider text-brand-muted">Fixed Commitments</span>
              <span class="text-xs font-bold text-indigo-500 tabular-nums">{{ analysisStore.data.totals.fixed_percentage }}%</span>
            </div>
            <p class="text-2xl font-heading font-bold text-brand-forest dark:text-brand-cream mt-1.5 tabular-nums">
              {{ analysisStore.data.totals.formatted_fixed_expenses }}
            </p>
            <p class="text-[11px] text-brand-muted mt-1">Recurring bills &amp; essential commitments</p>
          </div>

          <div class="bg-white dark:bg-brand-darkcard p-5 rounded-2xl border border-black/8 dark:border-white/10 shadow-xs">
            <div class="flex items-center justify-between">
              <span class="text-xs font-bold uppercase tracking-wider text-brand-muted">Variable Discretionary</span>
              <span class="text-xs font-bold text-amber-500 tabular-nums">{{ analysisStore.data.totals.variable_percentage }}%</span>
            </div>
            <p class="text-2xl font-heading font-bold text-brand-forest dark:text-brand-cream mt-1.5 tabular-nums">
              {{ analysisStore.data.totals.formatted_variable_expenses }}
            </p>
            <p class="text-[11px] text-brand-muted mt-1">Flexible day-to-day spending</p>
          </div>

          <div class="bg-white dark:bg-brand-darkcard p-5 rounded-2xl border border-black/8 dark:border-white/10 shadow-xs">
            <div class="flex items-center justify-between">
              <span class="text-xs font-bold uppercase tracking-wider text-brand-muted">Unclassified</span>
              <span class="text-xs font-bold text-slate-400 tabular-nums">{{ analysisStore.data.totals.unclassified_percentage }}%</span>
            </div>
            <p class="text-2xl font-heading font-bold text-brand-forest dark:text-brand-cream mt-1.5 tabular-nums">
              {{ analysisStore.data.totals.formatted_unclassified_expenses }}
            </p>
            <p class="text-[11px] text-brand-muted mt-1">Uncategorised or unassigned nature</p>
          </div>
        </div>

        <!-- PRIMARY VIEW: Category Spending Matrix by Period + CSV/XLSX Exports (Requirement 2) -->
        <div
          data-testid="spending-matrix-card"
          class="bg-white dark:bg-brand-darkcard rounded-2xl border border-black/8 dark:border-white/10 shadow-xs overflow-hidden"
        >
          <div class="p-5 sm:p-6 border-b border-black/5 dark:border-white/5 flex flex-col lg:flex-row lg:items-center justify-between gap-3">
            <div>
              <div class="flex items-center gap-2">
                <span class="px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider bg-brand-sage/20 text-brand-sage">
                  Primary Comparison Matrix
                </span>
                <h2 class="text-base sm:text-lg font-heading font-bold text-brand-forest dark:text-brand-cream">
                  Category Spending Matrix by Period
                </h2>
              </div>
              <p class="text-xs text-brand-muted mt-1">
                <strong class="font-semibold text-brand-forest dark:text-brand-cream">Question answered:</strong>
                How does each category’s exact spend compare across every {{ analysisStore.data.range_info.interval }} in the selected range? Click any cell or total to inspect transactions in the Ledger.
              </p>
            </div>

            <!-- Export Menu -->
            <div class="relative inline-block text-left" data-export-menu>
              <button
                type="button"
                data-testid="export-spending-matrix-menu-trigger"
                @click="toggleExportMenu('spending-matrix')"
                :disabled="analysisStore.isExporting"
                class="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-200 border border-brand-border dark:border-brand-darkborder hover:bg-slate-50 dark:hover:bg-slate-700 shadow-xs transition-colors disabled:opacity-50"
                aria-haspopup="true"
                :aria-expanded="openExportMenu === 'spending-matrix'"
              >
                <svg class="w-3.5 h-3.5 text-slate-500 dark:text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                <span>Export</span>
                <svg class="w-3 h-3 text-slate-400 transition-transform" :class="{ 'rotate-180': openExportMenu === 'spending-matrix' }" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              <div
                v-if="openExportMenu === 'spending-matrix'"
                class="absolute right-0 mt-1.5 w-44 rounded-xl bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder shadow-xl z-30 py-1"
              >
                <button
                  type="button"
                  data-testid="export-spending-matrix-csv"
                  @click="triggerExport('spending_matrix', 'csv')"
                  class="w-full text-left px-3 py-2 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center justify-between"
                >
                  <span>CSV Spreadsheet</span>
                  <span class="text-[10px] font-mono text-slate-400 uppercase">.csv</span>
                </button>
                <button
                  type="button"
                  data-testid="export-spending-matrix-xlsx"
                  @click="triggerExport('spending_matrix', 'xlsx')"
                  class="w-full text-left px-3 py-2 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center justify-between border-t border-slate-100 dark:border-slate-800"
                >
                  <span>Excel Workbook</span>
                  <span class="text-[10px] font-mono text-emerald-600 dark:text-emerald-400 font-bold uppercase">.xlsx</span>
                </button>
              </div>
            </div>
          </div>

          <div
            v-if="matrixRows.length > 0 && matrixPeriods.length > 0"
            class="overflow-x-auto max-h-[520px] relative"
          >
            <table class="w-full text-left border-collapse text-xs">
              <thead class="sticky top-0 z-20 bg-brand-cream dark:bg-brand-darkbg border-b border-black/10 dark:border-white/10">
                <tr>
                  <th class="sticky left-0 z-30 bg-brand-cream dark:bg-brand-darkbg py-3 px-4 font-bold text-brand-forest dark:text-brand-cream border-r border-black/10 dark:border-white/10 min-w-[180px]">
                    Category
                  </th>
                  <th
                    v-for="col in matrixPeriods"
                    :key="col.key"
                    class="py-3 px-3 font-bold text-right text-brand-muted whitespace-nowrap min-w-[96px]"
                  >
                    <router-link :to="getColumnDrilldownUrl(col)" class="hover:text-brand-sage hover:underline">
                      {{ col.label }}
                    </router-link>
                  </th>
                  <th class="sticky right-0 z-30 bg-brand-cream dark:bg-brand-darkbg py-3 px-4 font-bold text-right text-brand-forest dark:text-brand-cream border-l border-black/10 dark:border-white/10 min-w-[120px]">
                    Row Total
                  </th>
                </tr>
              </thead>

              <tbody class="divide-y divide-black/5 dark:divide-white/5 tabular-nums">
                <tr
                  v-for="row in matrixRows"
                  :key="row.category_id ?? 'uncat'"
                  class="hover:bg-black/[0.02] dark:hover:bg-white/[0.02] group"
                >
                  <!-- Sticky Left Category Cell -->
                  <td class="sticky left-0 z-10 bg-white dark:bg-brand-darkcard group-hover:bg-brand-cream/60 dark:group-hover:bg-brand-darkbg/80 py-2.5 px-4 border-r border-black/10 dark:border-white/10">
                    <div class="flex items-center justify-between gap-2">
                      <router-link
                        :to="getRowDrilldownUrl(row)"
                        class="flex items-center gap-2 font-semibold text-brand-forest dark:text-brand-cream hover:text-brand-sage truncate"
                      >
                        <span
                          class="w-2.5 h-2.5 rounded-full shrink-0"
                          :style="{ backgroundColor: row.category_color || '#94A3B8' }"
                        ></span>
                        <span :class="{ 'italic': row.is_uncategorized }">{{ row.category_name }}</span>
                      </router-link>
                      <span class="text-[10px] text-brand-muted shrink-0">{{ row.percentage }}%</span>
                    </div>
                  </td>

                  <!-- Period Cells -->
                  <td
                    v-for="col in matrixPeriods"
                    :key="col.key"
                    class="py-2.5 px-3 text-right whitespace-nowrap"
                  >
                    <router-link
                      v-if="getCellAmountPence(row, col) > 0"
                      :to="getCellDrilldownUrl(row, col)"
                      class="font-medium text-brand-forest dark:text-brand-cream hover:text-brand-sage hover:underline"
                    >
                      {{ row.cells[col.key]?.formatted_amount }}
                    </router-link>
                    <span v-else class="text-brand-muted/35">—</span>
                  </td>

                  <!-- Sticky Right Row Total -->
                  <td class="sticky right-0 z-10 bg-white dark:bg-brand-darkcard group-hover:bg-brand-cream/60 dark:group-hover:bg-brand-darkbg/80 py-2.5 px-4 text-right font-bold border-l border-black/10 dark:border-white/10 whitespace-nowrap">
                    <router-link :to="getRowDrilldownUrl(row)" class="text-brand-forest dark:text-brand-cream hover:text-brand-sage hover:underline">
                      {{ row.formatted_row_total }}
                    </router-link>
                  </td>
                </tr>
              </tbody>

              <!-- Sticky Bottom Period Totals & Grand Total -->
              <tfoot class="sticky bottom-0 z-20 bg-brand-cream dark:bg-brand-darkbg border-t-2 border-black/15 dark:border-white/15 font-bold tabular-nums">
                <tr>
                  <td class="sticky left-0 z-30 bg-brand-cream dark:bg-brand-darkbg py-3 px-4 text-brand-forest dark:text-brand-cream border-r border-black/10 dark:border-white/10">
                    Period Total
                  </td>
                  <td
                    v-for="col in matrixPeriods"
                    :key="col.key"
                    class="py-3 px-3 text-right whitespace-nowrap"
                  >
                    <router-link :to="getColumnDrilldownUrl(col)" class="text-rose-600 dark:text-rose-400 hover:underline">
                      {{ col.formatted_period_total }}
                    </router-link>
                  </td>
                  <td class="sticky right-0 z-30 bg-brand-cream dark:bg-brand-darkbg py-3 px-4 text-right border-l border-black/10 dark:border-white/10 whitespace-nowrap">
                    <router-link :to="getGrandTotalDrilldownUrl()" class="text-rose-600 dark:text-rose-400 hover:underline">
                      {{ analysisStore.data.spending_matrix?.formatted_grand_total }}
                    </router-link>
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>

          <div v-else class="p-10 text-center text-sm text-brand-muted">
            No operating expenses recorded for the selected date range and filter combination.
          </div>
        </div>

        <!-- Two Distinct, Non-Redundant Visualizations (Requirement 3):
             1. Category Spending Mix (Composition of Range)
             2. Spending Trajectory Over Time (Temporal Change Across Intervals) -->
        <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <!-- Visualization 1: Category Spending Mix (Composition in Range) -->
          <div class="lg:col-span-5 bg-white dark:bg-brand-darkcard p-5 sm:p-6 rounded-2xl border border-black/8 dark:border-white/10 shadow-xs flex flex-col justify-between space-y-4">
            <div class="flex items-start justify-between gap-2">
              <div>
                <h3 class="text-base font-heading font-bold text-brand-forest dark:text-brand-cream">
                  Category Spending Mix
                </h3>
                <p class="text-xs text-brand-muted mt-0.5">
                  <strong class="font-semibold text-brand-forest dark:text-brand-cream">Question answered:</strong>
                  What share of total spending went to each category in this range?
                </p>
              </div>
              <!-- Export Menu -->
              <div class="relative inline-block text-left" data-export-menu>
                <button
                  type="button"
                  data-testid="export-categories-menu-trigger"
                  @click="toggleExportMenu('categories')"
                  :disabled="analysisStore.isExporting"
                  class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-xl text-xs font-semibold bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-200 border border-brand-border dark:border-brand-darkborder hover:bg-slate-50 dark:hover:bg-slate-700 shadow-xs transition-colors disabled:opacity-50"
                  aria-haspopup="true"
                  :aria-expanded="openExportMenu === 'categories'"
                >
                  <svg class="w-3.5 h-3.5 text-slate-500 dark:text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                  <span>Export</span>
                  <svg class="w-3 h-3 text-slate-400 transition-transform" :class="{ 'rotate-180': openExportMenu === 'categories' }" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                  </svg>
                </button>

                <div
                  v-if="openExportMenu === 'categories'"
                  class="absolute right-0 mt-1.5 w-44 rounded-xl bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder shadow-xl z-30 py-1"
                >
                  <button
                    type="button"
                    data-testid="export-categories-csv"
                    @click="triggerExport('spending_categories', 'csv')"
                    class="w-full text-left px-3 py-2 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center justify-between"
                  >
                    <span>CSV Spreadsheet</span>
                    <span class="text-[10px] font-mono text-slate-400 uppercase">.csv</span>
                  </button>
                  <button
                    type="button"
                    data-testid="export-categories-xlsx"
                    @click="triggerExport('spending_categories', 'xlsx')"
                    class="w-full text-left px-3 py-2 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center justify-between border-t border-slate-100 dark:border-slate-800"
                  >
                    <span>Excel Workbook</span>
                    <span class="text-[10px] font-mono text-emerald-600 dark:text-emerald-400 font-bold uppercase">.xlsx</span>
                  </button>
                </div>
              </div>
            </div>

            <div v-if="donutChartData.segments.length > 0" class="space-y-4">
              <!-- SVG Donut Chart -->
              <div class="flex items-center justify-center relative py-1">
                <svg width="200" height="200" viewBox="0 0 200 200" class="overflow-visible">
                  <path
                    v-for="(seg, idx) in donutChartData.segments"
                    :key="idx"
                    :d="seg.path"
                    :fill="seg.category_color"
                    class="cursor-pointer transition-transform duration-150 origin-center hover:scale-[1.03]"
                    :opacity="hoveredDonutIdx === null || hoveredDonutIdx === idx ? 1 : 0.45"
                    @mouseenter="hoveredDonutIdx = idx"
                    @mouseleave="hoveredDonutIdx = null"
                    @click="analysisStore.toggleCategoryFilter(seg.category_id ?? 0)"
                  />
                </svg>
                <!-- Center Callout -->
                <div class="absolute inset-0 flex flex-col items-center justify-center pointer-events-none text-center px-6">
                  <template v-if="hoveredDonutIdx !== null && donutChartData.segments[hoveredDonutIdx]">
                    <span class="text-[11px] font-bold text-brand-muted truncate max-w-[96px]">
                      {{ donutChartData.segments[hoveredDonutIdx].category_name }}
                    </span>
                    <span class="text-sm font-heading font-bold text-brand-forest dark:text-brand-cream tabular-nums">
                      {{ donutChartData.segments[hoveredDonutIdx].formatted_total }}
                    </span>
                    <span class="text-[10px] font-bold text-brand-sage tabular-nums">
                      {{ donutChartData.segments[hoveredDonutIdx].percentage }}%
                    </span>
                  </template>
                  <template v-else>
                    <span class="text-[10px] uppercase tracking-wider text-brand-muted font-bold">Total Outflow</span>
                    <span class="text-sm font-heading font-bold text-brand-forest dark:text-brand-cream tabular-nums">
                      {{ donutChartData.formattedTotal }}
                    </span>
                  </template>
                </div>
              </div>

              <!-- Ranked Category Composition List with Share Bars -->
              <div class="max-h-64 overflow-y-auto space-y-2 pr-1 divide-y divide-black/5 dark:divide-white/5">
                <div
                  v-for="(cat, idx) in donutChartData.segments"
                  :key="cat.category_id ?? 'uncat'"
                  class="pt-2 first:pt-0 flex flex-col gap-1 group cursor-pointer"
                  @mouseenter="hoveredDonutIdx = idx"
                  @mouseleave="hoveredDonutIdx = null"
                >
                  <div class="flex items-center justify-between text-xs">
                    <div class="flex items-center gap-2 min-w-0">
                      <span class="w-2.5 h-2.5 rounded-full shrink-0" :style="{ backgroundColor: cat.category_color }"></span>
                      <button
                        type="button"
                        @click="analysisStore.toggleCategoryFilter(cat.category_id ?? 0)"
                        class="font-semibold text-brand-forest dark:text-brand-cream hover:text-brand-sage truncate text-left"
                        :title="`Filter Analysis by ${cat.category_name}`"
                      >
                        {{ cat.category_name }}
                      </button>
                      <span class="text-[10px] text-brand-muted">({{ cat.transaction_count }} tx)</span>
                    </div>
                    <div class="flex items-center gap-2 shrink-0 tabular-nums">
                      <span class="font-bold text-brand-forest dark:text-brand-cream">{{ cat.formatted_total }}</span>
                      <span class="text-[11px] text-brand-muted w-10 text-right">{{ cat.percentage }}%</span>
                    </div>
                  </div>
                  <div class="w-full h-1.5 rounded-full bg-black/5 dark:bg-white/5 overflow-hidden">
                    <div
                      class="h-full rounded-full transition-all"
                      :style="{ width: `${Math.max(2, cat.percentage)}%`, backgroundColor: cat.category_color }"
                    ></div>
                  </div>
                </div>
              </div>
            </div>

            <div v-else class="py-12 text-center text-xs text-brand-muted">
              No category spending to display in this range.
            </div>
          </div>

          <!-- Visualization 2: Redesigned Spending Trajectory Over Time (Requirement 4) -->
          <div class="lg:col-span-7 bg-white dark:bg-brand-darksurface p-5 sm:p-6 rounded-2xl border border-brand-border dark:border-brand-darkborder shadow-xs space-y-4">
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <h3 class="text-base font-heading font-bold text-slate-900 dark:text-white">
                  Spending Trajectory Over Time
                </h3>
                <p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  <strong class="font-semibold text-slate-800 dark:text-slate-200">Question answered:</strong>
                  How much did you spend in each {{ analysisStore.data.range_info.interval }}, which categories drove changes, and how did category spending trend?
                </p>
              </div>

              <!-- View Controls: Bars vs Line Chart + Category vs Nature -->
              <div class="flex flex-wrap items-center gap-1.5">
                <div class="flex items-center bg-black/[0.04] dark:bg-white/[0.05] p-0.5 rounded-xl border border-brand-border dark:border-brand-darkborder">
                  <button
                    type="button"
                    @click="analysisStore.spendingChartType = 'stacked_bar'"
                    :class="[
                      'px-2.5 py-1 rounded-lg text-xs font-semibold transition-all',
                      analysisStore.spendingChartType === 'stacked_bar'
                        ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-950 shadow-2xs font-bold'
                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                    ]"
                  >
                    Period Bars
                  </button>
                  <button
                    type="button"
                    @click="analysisStore.spendingChartType = 'line'"
                    :class="[
                      'px-2.5 py-1 rounded-lg text-xs font-semibold transition-all',
                      analysisStore.spendingChartType === 'line'
                        ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-950 shadow-2xs font-bold'
                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                    ]"
                  >
                    Trend Lines
                  </button>
                </div>

                <div class="flex items-center bg-black/[0.04] dark:bg-white/[0.05] p-0.5 rounded-xl border border-brand-border dark:border-brand-darkborder">
                  <button
                    type="button"
                    @click="analysisStore.spendingGroupingMode = 'category'"
                    :class="[
                      'px-2.5 py-1 rounded-lg text-xs font-semibold transition-all',
                      analysisStore.spendingGroupingMode === 'category'
                        ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-950 shadow-2xs font-bold'
                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                    ]"
                  >
                    By Category
                  </button>
                  <button
                    type="button"
                    @click="analysisStore.spendingGroupingMode = 'nature'"
                    :class="[
                      'px-2.5 py-1 rounded-lg text-xs font-semibold transition-all',
                      analysisStore.spendingGroupingMode === 'nature'
                        ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-950 shadow-2xs font-bold'
                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                    ]"
                  >
                    Fixed vs Variable
                  </button>
                </div>
              </div>
            </div>

            <!-- Focused Category Selection Bar (Requirement 4) -->
            <div class="pt-2 border-t border-brand-border/60 dark:border-brand-darkborder/60 space-y-2">
              <div class="flex items-center justify-between text-xs">
                <span class="font-bold text-slate-700 dark:text-slate-300">Focus Trajectory:</span>
                <button
                  v-if="analysisStore.spendingFocusCategoryId !== null"
                  type="button"
                  @click="analysisStore.setSpendingFocusCategory(null)"
                  class="text-xs text-emerald-600 dark:text-emerald-400 font-semibold hover:underline flex items-center gap-1"
                >
                  <span>Reset to All Categories</span>
                  <span>&times;</span>
                </button>
              </div>

              <!-- Category Focus Pills -->
              <div class="flex items-center gap-1.5 overflow-x-auto pb-1 max-w-full">
                <button
                  type="button"
                  @click="analysisStore.setSpendingFocusCategory(null)"
                  :class="[
                    'px-3 py-1 rounded-xl text-xs font-semibold border transition-all flex items-center gap-1.5 whitespace-nowrap shrink-0',
                    analysisStore.spendingFocusCategoryId === null
                      ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-950 font-bold shadow-xs'
                      : 'bg-black/[0.03] dark:bg-white/[0.04] border-brand-border dark:border-brand-darkborder text-slate-700 dark:text-slate-300 hover:border-slate-400'
                  ]"
                >
                  <span>All Categories (Total Spend)</span>
                </button>

                <button
                  v-for="cat in (analysisStore.data.categories || []).filter(c => c.total_pence > 0).slice(0, 6)"
                  :key="cat.category_id ?? 'uncat'"
                  type="button"
                  @click="analysisStore.setSpendingFocusCategory(cat.category_id ?? 0)"
                  :class="[
                    'px-2.5 py-1 rounded-xl text-xs font-semibold border transition-all flex items-center gap-1.5 whitespace-nowrap shrink-0 border-l-4',
                    analysisStore.spendingFocusCategoryId === (cat.category_id ?? 0)
                      ? 'bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-white font-bold shadow-xs'
                      : 'bg-black/[0.03] dark:bg-white/[0.04] border-brand-border dark:border-brand-darkborder text-slate-700 dark:text-slate-300 hover:border-slate-400'
                  ]"
                  :style="{
                    borderLeftColor: cat.category_color || '#8B5CF6'
                  }"
                >
                  <span class="w-2 h-2 rounded-full shrink-0" :style="{ backgroundColor: cat.category_color || '#8B5CF6' }"></span>
                  <span>{{ cat.category_name }}</span>
                  <span class="text-[10px] opacity-75 font-mono">({{ cat.formatted_total }})</span>
                </button>
              </div>

              <!-- Summary Context Banner -->
              <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 py-2 px-3 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-brand-border dark:border-brand-darkborder text-xs">
                <div>
                  <span class="block text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">Total Spent</span>
                  <span class="font-bold text-slate-900 dark:text-white font-mono">{{ spendingTrajectoryStats.formattedTotal }}</span>
                  <span v-if="analysisStore.spendingFocusCategoryId !== null" class="text-[10px] text-slate-500 ml-1">({{ spendingTrajectoryStats.totalSharePct }}%)</span>
                </div>
                <div>
                  <span class="block text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">Period Average</span>
                  <span class="font-bold text-slate-900 dark:text-white font-mono">{{ spendingTrajectoryStats.formattedAverage }}</span>
                </div>
                <div>
                  <span class="block text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">Peak Period</span>
                  <span class="font-bold text-slate-900 dark:text-white truncate block">{{ spendingTrajectoryStats.peakLabel }}</span>
                </div>
                <div>
                  <span class="block text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">Peak Spend</span>
                  <span class="font-bold text-rose-600 dark:text-rose-400 font-mono">{{ spendingTrajectoryStats.peakAmount }}</span>
                </div>
              </div>
            </div>

            <!-- Mode A: Redesigned Period Bars Trajectory -->
            <div v-if="analysisStore.spendingChartType === 'stacked_bar'" class="w-full overflow-x-auto pb-2">
              <div
                class="flex items-end gap-3 min-h-[240px] pt-12 pb-2 px-2"
                :style="{ minWidth: Math.max(100, spendingTrajectoryBars.length * 56) + 'px' }"
              >
                <div
                  v-for="(b, idx) in spendingTrajectoryBars"
                  :key="b.key"
                  class="flex-1 min-w-[42px] flex flex-col items-center group relative"
                  @mouseenter="hoveredStackedIdx = idx"
                  @mouseleave="hoveredStackedIdx = null"
                >
                  <!-- Rich Interactive Tooltip -->
                  <div
                    v-if="hoveredStackedIdx === idx"
                    class="absolute -top-12 z-30 pointer-events-none bg-slate-950 text-white px-3 py-2.5 rounded-xl text-xs shadow-xl whitespace-nowrap border border-white/15 space-y-1.5 min-w-[200px]"
                  >
                    <div class="flex items-center justify-between gap-3 border-b border-white/10 pb-1">
                      <span class="font-bold text-emerald-400">{{ b.label }}</span>
                      <span class="font-mono font-bold">{{ b.formatted_amount }}</span>
                    </div>

                    <div v-if="b.delta_pct !== null" class="text-[11px] flex items-center justify-between gap-2">
                      <span class="text-slate-400">vs prev {{ analysisStore.data.range_info.interval }}:</span>
                      <span :class="b.delta_pence && b.delta_pence > 0 ? 'text-rose-400 font-bold' : 'text-emerald-400 font-bold'">
                        {{ b.delta_pence && b.delta_pence > 0 ? '+' : '' }}{{ b.delta_pct }}%
                      </span>
                    </div>

                    <!-- Category Breakdown -->
                    <template v-if="analysisStore.spendingFocusCategoryId === null">
                      <div class="space-y-0.5 pt-1">
                        <span class="text-[10px] text-slate-400 uppercase tracking-wider block font-semibold">Top Categories:</span>
                        <div
                          v-for="seg in b.category_segments.slice(0, 4)"
                          :key="seg.name"
                          class="flex items-center justify-between gap-3 text-[11px]"
                        >
                          <div class="flex items-center gap-1.5 min-w-0">
                            <span class="w-2 h-2 rounded-full shrink-0" :style="{ backgroundColor: seg.color }"></span>
                            <span class="truncate max-w-[110px]">{{ seg.name }}</span>
                          </div>
                          <span class="font-mono text-slate-200">{{ seg.pct }}%</span>
                        </div>
                      </div>

                      <!-- Movers vs previous period -->
                      <div v-if="b.top_movers.length > 0" class="pt-1 border-t border-white/10">
                        <span class="text-[10px] text-slate-400 uppercase tracking-wider block font-semibold">Key Period Changes:</span>
                        <div
                          v-for="m in b.top_movers"
                          :key="m.name"
                          class="flex items-center justify-between gap-2 text-[11px]"
                        >
                          <span class="truncate max-w-[120px]">{{ m.name }}</span>
                          <span :class="m.isPositive ? 'text-rose-400' : 'text-emerald-400'" class="font-mono">
                            {{ m.formattedDelta }}
                          </span>
                        </div>
                      </div>
                    </template>

                    <div class="pt-1 text-[10px] text-slate-400 text-center italic">
                      Click bar to inspect in Ledger ↗
                    </div>
                  </div>

                  <!-- Amount label above bar -->
                  <span class="text-[10px] font-mono font-bold text-slate-700 dark:text-slate-300 mb-1 opacity-80 group-hover:opacity-100 transition-opacity">
                    {{ b.formatted_amount }}
                  </span>

                  <!-- Interactive Column linked to Ledger -->
                  <router-link
                    :to="getPeriodCategoryLedgerUrl(b, analysisStore.spendingFocusCategoryId)"
                    class="w-full h-36 flex items-end justify-center border-b border-brand-border dark:border-brand-darkborder pb-1 group-hover:brightness-110"
                    :title="`View ${b.label} in Ledger`"
                  >
                    <div
                      class="w-7 max-w-[28px] flex flex-col-reverse rounded-t overflow-hidden transition-all shadow-xs"
                      :style="{
                        height: Math.max(6, Math.min(100, (b.amount_pence / spendingTrajectoryMaxPence) * 100)) + '%'
                      }"
                    >
                      <!-- Proportional category segments -->
                      <div
                        v-for="seg in b.category_segments"
                        :key="seg.name"
                        :style="{
                          height: `${seg.pct}%`,
                          backgroundColor: seg.color
                        }"
                        class="transition-all"
                      ></div>
                    </div>
                  </router-link>

                  <!-- Axis Label & Delta Indicator -->
                  <div class="mt-2 text-center leading-tight">
                    <span class="block text-xs font-bold text-slate-800 dark:text-slate-200">
                      {{ getAxisLabelParts(b.label, b.start_date).line1 }}
                    </span>
                    <span
                      v-if="getAxisLabelParts(b.label, b.start_date).line2"
                      class="block text-[10px] text-slate-500 dark:text-slate-400"
                    >
                      {{ getAxisLabelParts(b.label, b.start_date).line2 }}
                    </span>

                    <span
                      v-if="b.delta_pct !== null"
                      :class="[
                        'inline-block px-1 rounded text-[9px] font-bold mt-1 tabular-nums',
                        b.delta_pence && b.delta_pence > 0
                          ? 'bg-rose-500/10 text-rose-600 dark:text-rose-400'
                          : 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                      ]"
                    >
                      {{ b.delta_pence && b.delta_pence > 0 ? '+' : '' }}{{ b.delta_pct }}%
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Mode B: Multi-Series Trend Line Chart -->
            <div v-else class="space-y-3">
              <!-- Line Series Toggles -->
              <div class="flex flex-wrap items-center gap-1.5">
                <button
                  type="button"
                  @click="analysisStore.showTotalSpendLine = !analysisStore.showTotalSpendLine"
                  :class="[
                    'px-2.5 py-1 rounded-lg text-[11px] font-semibold border transition-all flex items-center gap-1.5',
                    analysisStore.showTotalSpendLine
                      ? 'bg-rose-500/15 border-rose-500/40 text-rose-600 dark:text-rose-400 font-bold'
                      : 'bg-black/5 dark:bg-white/5 border-transparent text-slate-500 opacity-60'
                  ]"
                >
                  <span class="w-2 h-2 rounded-full bg-rose-500"></span>
                  <span>Total Spend</span>
                </button>

                <template v-if="analysisStore.spendingGroupingMode === 'category'">
                  <button
                    v-for="cat in analysisStore.data.categories.slice(0, 6)"
                    :key="cat.category_id ?? 'uncat'"
                    v-show="cat.category_id !== null"
                    type="button"
                    @click="cat.category_id && analysisStore.toggleCategoryLine(cat.category_id)"
                    :class="[
                      'px-2.5 py-1 rounded-lg text-[11px] font-semibold border transition-all flex items-center gap-1.5 border-l-4',
                      cat.category_id && analysisStore.selectedCategoryLineIds.includes(cat.category_id)
                        ? 'bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-white font-bold'
                        : 'bg-black/5 dark:bg-white/5 border-transparent text-slate-500 opacity-60'
                    ]"
                    :style="{
                      borderLeftColor: cat.category_color || '#8B5CF6'
                    }"
                  >
                    <span class="w-2 h-2 rounded-full" :style="{ backgroundColor: cat.category_color }"></span>
                    <span>{{ cat.category_name }}</span>
                  </button>
                </template>
                <template v-else>
                  <button
                    type="button"
                    @click="analysisStore.showNatureLines.fixed = !analysisStore.showNatureLines.fixed"
                    :class="[
                      'px-2.5 py-1 rounded-lg text-[11px] font-semibold border transition-all flex items-center gap-1.5',
                      analysisStore.showNatureLines.fixed ? 'bg-indigo-500/15 border-indigo-500/40 text-indigo-500 font-bold' : 'opacity-50'
                    ]"
                  >
                    <span class="w-2 h-2 rounded-full bg-indigo-500"></span> Fixed
                  </button>
                  <button
                    type="button"
                    @click="analysisStore.showNatureLines.variable = !analysisStore.showNatureLines.variable"
                    :class="[
                      'px-2.5 py-1 rounded-lg text-[11px] font-semibold border transition-all flex items-center gap-1.5',
                      analysisStore.showNatureLines.variable ? 'bg-amber-500/15 border-amber-500/40 text-amber-500 font-bold' : 'opacity-50'
                    ]"
                  >
                    <span class="w-2 h-2 rounded-full bg-amber-500"></span> Variable
                  </button>
                </template>
              </div>

              <!-- Empty State -->
              <div
                v-if="spendingLineChartData.isEmpty"
                class="p-8 text-center rounded-2xl bg-slate-50 dark:bg-slate-800/40 border border-dashed border-slate-200 dark:border-slate-800 text-xs text-brand-muted"
              >
                No spending records found for this period.
              </div>

              <!-- Single Point Checkpoint Banner -->
              <div
                v-else-if="spendingLineChartData.isSinglePoint && spendingLineChartData.points[0]"
                class="p-4 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/60 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs"
              >
                <div>
                  <div class="font-bold text-slate-800 dark:text-slate-100 flex items-center gap-2">
                    <span>Single Period Spending Checkpoint:</span>
                    <span class="font-mono text-brand-sage">{{ spendingLineChartData.points[0].label }}</span>
                  </div>
                  <p class="text-[11px] text-brand-muted mt-0.5">Select a wider range or smaller grouping interval (e.g. Day or Week) to explore spending trajectory.</p>
                </div>
                <div class="flex items-center gap-3 font-mono font-bold text-rose-500">
                  <span>Total Spend: {{ spendingLineChartData.points[0].formattedTotal }}</span>
                </div>
              </div>

              <div v-if="!spendingLineChartData.isEmpty" class="w-full overflow-x-auto pb-2">
                <div class="relative min-w-[640px]" :style="{ width: spendingLineChartData.width + 'px', height: '240px' }">
                  <svg :width="spendingLineChartData.width" :height="spendingLineChartData.height" class="overflow-visible" role="region" aria-label="Spending Trajectory Line Chart">
                    <!-- Grid Lines and Y-Axis Ticks -->
                    <g v-for="tick in spendingLineChartData.scale.ticks" :key="tick.valuePence">
                      <line
                        :x1="spendingLineChartData.paddingLeft"
                        :y1="tick.y"
                        :x2="spendingLineChartData.width - spendingLineChartData.paddingRight"
                        :y2="tick.y"
                        :stroke="tick.isZero ? 'currentColor' : 'currentColor'"
                        :class="tick.isZero ? 'text-slate-400 dark:text-slate-500' : 'text-slate-200/80 dark:text-slate-800/80'"
                        :stroke-dasharray="tick.isZero ? 'none' : '3 3'"
                        :stroke-width="tick.isZero ? 1.5 : 1"
                      />
                      <text
                        :x="spendingLineChartData.paddingLeft - 10"
                        :y="tick.y + 3.5"
                        text-anchor="end"
                        class="text-[10px] fill-slate-500 dark:fill-slate-400 font-mono font-medium select-none"
                      >
                        {{ tick.formattedLabel }}
                      </text>
                    </g>

                    <!-- Total Spend Line & Area (Solid actuals, dashed planned forecast) -->
                    <template v-if="analysisStore.showTotalSpendLine">
                      <path
                        v-for="(p, i) in spendingLineChartData.totalSolidPaths"
                        :key="'tot-s-' + i"
                        :d="p"
                        fill="none"
                        stroke="#F43F5E"
                        stroke-width="2.5"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                      />
                      <path
                        v-for="(p, i) in spendingLineChartData.totalDashedPaths"
                        :key="'tot-d-' + i"
                        :d="p"
                        fill="none"
                        stroke="#F43F5E"
                        stroke-width="2.5"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        stroke-dasharray="5 4"
                      />
                    </template>

                    <!-- Category Lines (Solid actuals, dashed planned) -->
                    <template v-for="cl in spendingLineChartData.categoryLines" :key="cl.id">
                      <path
                        v-for="(p, i) in cl.solidPaths"
                        :key="'cat-s-' + cl.id + '-' + i"
                        :d="p"
                        fill="none"
                        :stroke="cl.color"
                        stroke-width="2"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                      />
                      <path
                        v-for="(p, i) in cl.dashedPaths"
                        :key="'cat-d-' + cl.id + '-' + i"
                        :d="p"
                        fill="none"
                        :stroke="cl.color"
                        stroke-width="2"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        stroke-dasharray="5 4"
                      />
                    </template>

                    <!-- Nature Lines (Solid actuals, dashed planned) -->
                    <template v-for="nl in spendingLineChartData.natureLines" :key="nl.nature">
                      <path
                        v-for="(p, i) in nl.solidPaths"
                        :key="'nat-s-' + nl.nature + '-' + i"
                        :d="p"
                        fill="none"
                        :stroke="nl.color"
                        stroke-width="2"
                        :stroke-dasharray="nl.strokeDasharray"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                      />
                      <path
                        v-for="(p, i) in nl.dashedPaths"
                        :key="'nat-d-' + nl.nature + '-' + i"
                        :d="p"
                        fill="none"
                        :stroke="nl.color"
                        stroke-width="2"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        stroke-dasharray="5 4"
                      />
                    </template>

                    <!-- Interactive Points & X-axis Ticks -->
                    <g v-for="(pt, idx) in spendingLineChartData.points" :key="idx">
                      <!-- Vertical Focus Guideline -->
                      <line
                        v-if="hoveredSpendLineIdx === idx"
                        :x1="pt.x"
                        :y1="spendingLineChartData.paddingTop"
                        :x2="pt.x"
                        :y2="spendingLineChartData.zeroY"
                        stroke="currentColor"
                        class="text-rose-400/50 dark:text-rose-400/70"
                        stroke-width="1.25"
                        stroke-dasharray="3 3"
                      />

                      <!-- Total Spend Point Marker -->
                      <circle
                        v-if="analysisStore.showTotalSpendLine"
                        :cx="pt.x"
                        :cy="pt.totalY"
                        :r="hoveredSpendLineIdx === idx ? 5.5 : 3.5"
                        :fill="pt.is_planned ? 'white' : '#F43F5E'"
                        :stroke="'#F43F5E'"
                        :stroke-width="pt.is_planned ? 2 : 1"
                        class="transition-all"
                      />

                      <!-- Category Point Markers -->
                      <template v-if="analysisStore.spendingGroupingMode === 'category'">
                        <circle
                          v-for="cat in pt.categoryItems"
                          :key="cat.id"
                          :cx="pt.x"
                          :cy="cat.y"
                          :r="hoveredSpendLineIdx === idx ? 5 : 3"
                          :fill="pt.is_planned ? 'white' : cat.color"
                          :stroke="cat.color"
                          :stroke-width="pt.is_planned ? 2 : 1"
                          class="transition-all"
                        />
                      </template>

                      <!-- Nature Point Markers -->
                      <template v-else-if="analysisStore.spendingGroupingMode === 'nature'">
                        <rect
                          v-if="analysisStore.showNatureLines.fixed"
                          :x="pt.x - (hoveredSpendLineIdx === idx ? 4.5 : 3)"
                          :y="pt.fixedY - (hoveredSpendLineIdx === idx ? 4.5 : 3)"
                          :width="hoveredSpendLineIdx === idx ? 9 : 6"
                          :height="hoveredSpendLineIdx === idx ? 9 : 6"
                          :fill="pt.is_planned ? 'white' : '#6366F1'"
                          :stroke="'#6366F1'"
                          :stroke-width="pt.is_planned ? 2 : 1"
                          class="transition-all"
                        />
                        <polygon
                          v-if="analysisStore.showNatureLines.variable"
                          :points="`${pt.x},${pt.variableY - (hoveredSpendLineIdx === idx ? 5.5 : 3.5)} ${pt.x + (hoveredSpendLineIdx === idx ? 5.5 : 3.5)},${pt.variableY} ${pt.x},${pt.variableY + (hoveredSpendLineIdx === idx ? 5.5 : 3.5)} ${pt.x - (hoveredSpendLineIdx === idx ? 5.5 : 3.5)},${pt.variableY}`"
                          :fill="pt.is_planned ? 'white' : '#F59E0B'"
                          :stroke="'#F59E0B'"
                          :stroke-width="pt.is_planned ? 2 : 1"
                          class="transition-all"
                        />
                      </template>

                      <!-- Accessible Interactive Hit Target -->
                      <rect
                        :x="pt.x - 18"
                        :y="spendingLineChartData.paddingTop"
                        width="36"
                        :height="spendingLineChartData.zeroY - spendingLineChartData.paddingTop"
                        fill="transparent"
                        class="cursor-pointer focus:outline-none"
                        tabindex="0"
                        role="button"
                        :aria-label="pt.accessibilityLabel"
                        @mouseenter="hoveredSpendLineIdx = idx"
                        @mouseleave="hoveredSpendLineIdx = null"
                        @focus="hoveredSpendLineIdx = idx"
                        @blur="hoveredSpendLineIdx = null"
                        @keydown.left.prevent="navigateChartPoint(idx, -1, spendingLineChartData.points.length, (i) => hoveredSpendLineIdx = i)"
                        @keydown.right.prevent="navigateChartPoint(idx, 1, spendingLineChartData.points.length, (i) => hoveredSpendLineIdx = i)"
                      />

                      <!-- X-Axis Date Labels -->
                      <g
                        v-if="shouldShowTick(idx, spendingLineChartData.points.length)"
                        :transform="`translate(${pt.x}, ${spendingLineChartData.height - 22})`"
                      >
                        <text text-anchor="middle" class="text-[10px] fill-slate-500 font-medium select-none">
                          {{ getAxisLabelParts(pt.label, pt.start_date).line1 }}
                        </text>
                        <text
                          v-if="getAxisLabelParts(pt.label, pt.start_date).line2"
                          y="12"
                          text-anchor="middle"
                          class="text-[9px] fill-slate-400 select-none"
                        >
                          {{ getAxisLabelParts(pt.label, pt.start_date).line2 }}
                        </text>
                      </g>
                    </g>
                  </svg>

                  <!-- Accessible Bounded Hover Tooltip -->
                  <div
                    v-if="hoveredSpendLineIdx !== null && spendingLineChartData.points[hoveredSpendLineIdx]"
                    class="absolute z-30 pointer-events-none bg-slate-950 text-white px-3.5 py-2.5 rounded-xl text-xs shadow-xl border border-white/15 space-y-1.5"
                    :style="getSpendTooltipStyle(spendingLineChartData.points[hoveredSpendLineIdx])"
                  >
                    <div class="flex items-center justify-between gap-4 font-bold border-b border-white/10 pb-1">
                      <span>{{ spendingLineChartData.points[hoveredSpendLineIdx].label }}</span>
                      <span v-if="spendingLineChartData.points[hoveredSpendLineIdx].is_planned" class="px-1.5 py-0.5 rounded text-[10px] bg-amber-500/20 text-amber-300 font-semibold uppercase">
                        Planned
                      </span>
                    </div>
                    <div v-if="analysisStore.showTotalSpendLine" class="flex items-center justify-between gap-4 text-rose-400">
                      <span>Total Spend:</span>
                      <span class="font-mono font-bold">{{ spendingLineChartData.points[hoveredSpendLineIdx].formattedTotal }}</span>
                    </div>

                    <template v-if="analysisStore.spendingGroupingMode === 'nature'">
                      <div v-if="analysisStore.showNatureLines.fixed" class="flex items-center justify-between gap-4 text-indigo-300 text-[11px]">
                        <span class="flex items-center gap-1.5">
                          <span class="w-2 h-2 rounded-xs bg-indigo-500"></span> Fixed:
                        </span>
                        <span class="font-mono">{{ spendingLineChartData.points[hoveredSpendLineIdx].formattedFixed }}</span>
                      </div>
                      <div v-if="analysisStore.showNatureLines.variable" class="flex items-center justify-between gap-4 text-amber-300 text-[11px]">
                        <span class="flex items-center gap-1.5">
                          <span class="w-2 h-2 rounded-xs bg-amber-500"></span> Variable:
                        </span>
                        <span class="font-mono">{{ spendingLineChartData.points[hoveredSpendLineIdx].formattedVariable }}</span>
                      </div>
                      <div v-if="analysisStore.showNatureLines.unclassified" class="flex items-center justify-between gap-4 text-slate-300 text-[11px]">
                        <span class="flex items-center gap-1.5">
                          <span class="w-2 h-2 rounded-xs bg-slate-400"></span> Unclassified:
                        </span>
                        <span class="font-mono">{{ spendingLineChartData.points[hoveredSpendLineIdx].formattedUnclassified }}</span>
                      </div>
                    </template>

                    <template v-else-if="spendingLineChartData.points[hoveredSpendLineIdx].categoryItems.length > 0">
                      <div
                        v-for="cat in spendingLineChartData.points[hoveredSpendLineIdx].categoryItems"
                        :key="cat.id"
                        class="flex items-center justify-between gap-4 text-[11px]"
                      >
                        <span class="flex items-center gap-1.5" :style="{ color: cat.color }">
                          <span class="w-2 h-2 rounded-full" :style="{ backgroundColor: cat.color }"></span>
                          {{ cat.name }}
                        </span>
                        <span class="font-mono text-slate-200">{{ cat.formattedAmount }}</span>
                      </div>
                    </template>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ====================================================================== -->
      <!-- SECTION 3: BALANCES & NET WORTH                                        -->
      <!-- ====================================================================== -->
      <section v-else-if="analysisStore.activeSection === 'networth'" class="space-y-6">
        <!-- Pre-Anchor Inferred History Advisory Banner -->
        <div
          v-if="hasAnyInferredBalances"
          class="p-4 rounded-2xl bg-amber-500/10 border border-amber-500/25 text-amber-800 dark:text-amber-300 text-xs flex items-start gap-3"
        >
          <span class="px-2 py-0.5 rounded bg-amber-500/20 font-bold uppercase tracking-wider text-[10px] shrink-0 mt-0.5">
            Inferred History
          </span>
          <p>
            One or more period-end balances precede the account’s earliest ground-truth balance anchor and are
            <strong>inferred retrospectively</strong> by reversing historical transactions. Inferred periods are explicitly marked below.
          </p>
        </div>

        <!-- Net Worth & Account Balances Trajectory Chart (Requirement 5) -->
        <div class="bg-white dark:bg-brand-darksurface p-5 sm:p-6 rounded-2xl border border-brand-border dark:border-brand-darkborder shadow-xs space-y-4">
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h2 class="text-base sm:text-lg font-heading font-bold text-slate-900 dark:text-white">
                Net Worth &amp; Balance Sheet Trajectory
              </h2>
              <p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                <strong class="font-semibold text-slate-800 dark:text-slate-200">Question answered:</strong>
                How have gross assets, liabilities, net worth, and individual account balances evolved at each period end?
              </p>
            </div>
            <div class="flex flex-wrap items-center gap-3 text-xs">
              <span class="flex items-center gap-1.5 text-slate-700 dark:text-slate-300 font-medium">
                <span class="w-2.5 h-2.5 rounded-full bg-emerald-500"></span> Net Worth
              </span>
              <span class="flex items-center gap-1.5 text-slate-700 dark:text-slate-300 font-medium">
                <span class="w-2.5 h-2.5 rounded-full bg-blue-500"></span> Gross Assets
              </span>
              <span class="flex items-center gap-1.5 text-slate-700 dark:text-slate-300 font-medium">
                <span class="w-2.5 h-2.5 rounded-full bg-rose-500"></span> Liabilities
              </span>
            </div>
          </div>

          <!-- Account Selection Controls for Chart (Requirement 5) -->
          <div class="pt-2 border-t border-brand-border/60 dark:border-brand-darkborder/60 space-y-2">
            <div class="flex items-center justify-between text-xs">
              <span class="font-bold text-slate-700 dark:text-slate-300">Plot Individual Accounts on Chart:</span>
              <button
                v-if="analysisStore.selectedBalanceAccountIds.length > 0"
                type="button"
                @click="analysisStore.setBalanceAccounts([])"
                class="text-xs text-emerald-600 dark:text-emerald-400 font-semibold hover:underline"
              >
                Clear charted accounts
              </button>
            </div>

            <div class="flex flex-wrap items-center gap-1.5">
              <button
                v-for="acc in (analysisStore.data?.net_worth_series[0]?.account_balances || [])"
                :key="acc.account_id"
                type="button"
                @click="analysisStore.toggleBalanceAccount(acc.account_id)"
                :class="[
                  'px-2.5 py-1 rounded-xl text-xs font-semibold border transition-all flex items-center gap-1.5 border-l-4',
                  analysisStore.selectedBalanceAccountIds.includes(acc.account_id)
                    ? 'bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-white font-bold shadow-xs'
                    : 'bg-black/[0.03] dark:bg-white/[0.04] border-brand-border dark:border-brand-darkborder text-slate-700 dark:text-slate-300 hover:border-slate-400'
                ]"
                :style="{
                  borderLeftColor: getAccountColor(acc.account_id)
                }"
              >
                <span class="w-2 h-2 rounded-full shrink-0" :style="{ backgroundColor: getAccountColor(acc.account_id) }"></span>
                <span>{{ acc.account_name }}</span>
                <span
                  v-if="analysisStore.selectedBalanceAccountIds.includes(acc.account_id)"
                  class="px-1.5 py-0.2 rounded-full text-[9px] font-bold bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                >
                  Charted ✓
                </span>
              </button>
            </div>
          </div>

          <!-- Empty State -->
          <div
            v-if="netWorthChartData.isEmpty"
            class="p-8 text-center rounded-2xl bg-slate-50 dark:bg-slate-800/40 border border-dashed border-slate-200 dark:border-slate-800 text-xs text-brand-muted"
          >
            No balance or net worth records found for this period.
          </div>

          <!-- Single Point Checkpoint Banner -->
          <div
            v-else-if="netWorthChartData.isSinglePoint && netWorthChartData.points[0]"
            class="p-4 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/60 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs"
          >
            <div>
              <div class="font-bold text-slate-800 dark:text-slate-100 flex items-center gap-2">
                <span>Single Balance Checkpoint:</span>
                <span class="font-mono text-brand-sage">{{ netWorthChartData.points[0].label }} ({{ netWorthChartData.points[0].date }})</span>
                <span v-if="netWorthChartData.points[0].has_inferred" class="px-1.5 py-0.5 rounded text-[10px] bg-amber-500/20 text-amber-600 dark:text-amber-400 font-bold uppercase">
                  Inferred Pre-Anchor
                </span>
                <span v-else class="px-1.5 py-0.5 rounded text-[10px] bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 font-bold uppercase">
                  Confirmed Anchor
                </span>
              </div>
              <p class="text-[11px] text-brand-muted mt-0.5">Select a wider range or smaller grouping interval (e.g. Month or Week) to explore balance evolution over time.</p>
            </div>
            <div class="flex items-center gap-3 font-mono font-bold">
              <span class="text-emerald-500">Net Worth: {{ netWorthChartData.points[0].formatted_nw }}</span>
              <span class="text-blue-500">Assets: {{ netWorthChartData.points[0].formatted_assets }}</span>
              <span class="text-rose-500">Liabilities: {{ netWorthChartData.points[0].formatted_debt }}</span>
            </div>
          </div>

          <!-- Line Chart with Interactive Accounts -->
          <div v-if="!netWorthChartData.isEmpty" class="w-full overflow-x-auto pb-2">
            <div class="relative min-w-[640px]" :style="{ width: netWorthChartData.width + 'px', height: '240px' }">
              <svg :width="netWorthChartData.width" :height="netWorthChartData.height" class="overflow-visible" role="region" aria-label="Balances and Net Worth Trajectory Chart">
                <!-- Grid Lines and Y-Axis Ticks -->
                <g v-for="tick in netWorthChartData.scale.ticks" :key="tick.valuePence">
                  <line
                    :x1="netWorthChartData.paddingLeft"
                    :y1="tick.y"
                    :x2="netWorthChartData.width - netWorthChartData.paddingRight"
                    :y2="tick.y"
                    :stroke="tick.isZero ? 'currentColor' : 'currentColor'"
                    :class="tick.isZero ? 'text-slate-400 dark:text-slate-500' : 'text-slate-200/80 dark:text-slate-800/80'"
                    :stroke-dasharray="tick.isZero ? 'none' : '3 3'"
                    :stroke-width="tick.isZero ? 1.5 : 1"
                  />
                  <text
                    :x="netWorthChartData.paddingLeft - 10"
                    :y="tick.y + 3.5"
                    text-anchor="end"
                    class="text-[10px] fill-slate-500 dark:fill-slate-400 font-mono font-medium select-none"
                  >
                    {{ tick.formattedLabel }}
                  </text>
                </g>

                <!-- Assets & Debt Reference Lines -->
                <path :d="netWorthChartData.assetsLinePath" fill="none" stroke="#3B82F6" stroke-width="1.75" stroke-dasharray="3 3" />
                <path :d="netWorthChartData.debtLinePath" fill="none" stroke="#F43F5E" stroke-width="1.75" stroke-dasharray="3 3" />
                
                <!-- Individual Plotted Account Lines -->
                <path
                  v-for="al in netWorthChartData.accountLines"
                  :key="al.id"
                  :d="al.path"
                  fill="none"
                  :stroke="al.color"
                  stroke-width="2.25"
                  stroke-linecap="round"
                />

                <!-- Net Worth Segments (Solid = Confirmed Anchor, Dashed = Inferred Pre-Anchor) -->
                <path
                  v-for="(p, i) in netWorthChartData.solidNetWorthPaths"
                  :key="'nw-s-' + i"
                  :d="p"
                  fill="none"
                  stroke="#10B981"
                  stroke-width="2.75"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
                <path
                  v-for="(p, i) in netWorthChartData.inferredNetWorthPaths"
                  :key="'nw-inf-' + i"
                  :d="p"
                  fill="none"
                  stroke="#F59E0B"
                  stroke-width="2.5"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-dasharray="5 4"
                />

                <!-- Points & Hover -->
                <g v-for="(pt, idx) in netWorthChartData.points" :key="idx">
                  <!-- Focus Guideline -->
                  <line
                    v-if="hoveredNwIdx === idx"
                    :x1="pt.x"
                    :y1="netWorthChartData.paddingTop"
                    :x2="pt.x"
                    :y2="netWorthChartData.height - 44"
                    stroke="currentColor"
                    class="text-emerald-500/50 dark:text-emerald-400/60"
                    stroke-width="1.25"
                    stroke-dasharray="3 3"
                  />

                  <!-- Net Worth Point -->
                  <circle
                    :cx="pt.x"
                    :cy="pt.y"
                    :r="hoveredNwIdx === idx ? 5.5 : 3.5"
                    :fill="pt.has_inferred ? '#F59E0B' : '#10B981'"
                    :stroke="pt.has_inferred ? '#D97706' : '#059669'"
                    :stroke-width="pt.has_inferred ? 2 : 1"
                    class="cursor-pointer transition-all"
                  />

                  <!-- Plotted Account Circles -->
                  <circle
                    v-for="ap in pt.accounts"
                    :key="ap.id"
                    :cx="pt.x"
                    :cy="ap.y"
                    :r="hoveredNwIdx === idx ? 4.5 : 3"
                    :fill="ap.color"
                    class="cursor-pointer transition-all"
                  />

                  <!-- Accessible Interactive Hit Target -->
                  <rect
                    :x="pt.x - 18"
                    :y="netWorthChartData.paddingTop"
                    width="36"
                    :height="netWorthChartData.height - 44 - netWorthChartData.paddingTop"
                    fill="transparent"
                    class="cursor-pointer focus:outline-none"
                    tabindex="0"
                    role="button"
                    :aria-label="pt.accessibilityLabel"
                    @mouseenter="hoveredNwIdx = idx"
                    @mouseleave="hoveredNwIdx = null"
                    @focus="hoveredNwIdx = idx"
                    @blur="hoveredNwIdx = null"
                    @keydown.left.prevent="navigateChartPoint(idx, -1, netWorthChartData.points.length, (i) => hoveredNwIdx = i)"
                    @keydown.right.prevent="navigateChartPoint(idx, 1, netWorthChartData.points.length, (i) => hoveredNwIdx = i)"
                  />

                  <!-- X-Axis Date Labels -->
                  <g
                    v-if="shouldShowTick(idx, netWorthChartData.points.length)"
                    :transform="`translate(${pt.x}, ${netWorthChartData.height - 22})`"
                  >
                    <text text-anchor="middle" class="text-[10px] fill-slate-500 font-medium select-none">
                      {{ getAxisLabelParts(pt.label, pt.date).line1 }}
                    </text>
                    <text
                      v-if="getAxisLabelParts(pt.label, pt.date).line2"
                      y="12"
                      text-anchor="middle"
                      class="text-[9px] fill-slate-400 select-none"
                    >
                      {{ getAxisLabelParts(pt.label, pt.date).line2 }}
                    </text>
                  </g>
                </g>
              </svg>

              <!-- Accessible Bounded Hover Tooltip -->
              <div
                v-if="hoveredNwIdx !== null && netWorthChartData.points[hoveredNwIdx]"
                class="absolute z-30 pointer-events-none bg-slate-950 text-white px-3.5 py-2.5 rounded-xl text-xs shadow-xl border border-white/15 space-y-1.5"
                :style="getNetWorthTooltipStyle(netWorthChartData.points[hoveredNwIdx])"
              >
                <div class="flex items-center justify-between gap-4 font-bold border-b border-white/10 pb-1">
                  <span>{{ netWorthChartData.points[hoveredNwIdx].label }} ({{ netWorthChartData.points[hoveredNwIdx].date }})</span>
                  <span
                    class="px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase"
                    :class="netWorthChartData.points[hoveredNwIdx].has_inferred ? 'bg-amber-500/20 text-amber-300' : 'bg-emerald-500/20 text-emerald-300'"
                  >
                    {{ netWorthChartData.points[hoveredNwIdx].has_inferred ? 'Inferred Pre-Anchor' : 'Confirmed Anchor' }}
                  </span>
                </div>
                <div class="flex items-center justify-between gap-4 text-emerald-400">
                  <span>Net Worth:</span>
                  <span class="font-mono font-bold">{{ netWorthChartData.points[hoveredNwIdx].formatted_nw }}</span>
                </div>
                <div class="flex items-center justify-between text-[11px] text-slate-300">
                  <span>Gross Assets:</span>
                  <span class="font-mono text-blue-400">{{ netWorthChartData.points[hoveredNwIdx].formatted_assets }}</span>
                </div>
                <div class="flex items-center justify-between text-[11px] text-slate-300">
                  <span>Liabilities:</span>
                  <span class="font-mono text-rose-400">{{ netWorthChartData.points[hoveredNwIdx].formatted_debt }}</span>
                </div>
                <!-- Selected account values in tooltip -->
                <div
                  v-for="ap in netWorthChartData.points[hoveredNwIdx].accounts"
                  :key="ap.id"
                  class="flex items-center justify-between text-[11px] pt-1 border-t border-white/10"
                >
                  <span class="flex items-center gap-1.5 truncate max-w-[130px]">
                    <span class="w-2 h-2 rounded-full shrink-0" :style="{ backgroundColor: ap.color }"></span>
                    <span>{{ ap.name }}:</span>
                  </span>
                  <span class="font-mono font-bold text-slate-200">{{ ap.formatted_balance }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Balances & Net Worth History Table (Ordered Newest Period First) -->
        <div class="bg-white dark:bg-brand-darksurface rounded-2xl border border-brand-border dark:border-brand-darkborder shadow-xs overflow-hidden">
          <div class="p-4 sm:p-5 border-b border-brand-border/60 dark:border-brand-darkborder/60 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h3 class="text-base font-heading font-bold text-slate-900 dark:text-white">
                Period-End Account Balances &amp; Net Worth
              </h3>
              <p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                Anchor-verified period-end balances ordered newest first. Click any account column header to plot or unplot that account on the chart.
              </p>
            </div>
            <!-- Export Menu -->
            <div class="relative inline-block text-left" data-export-menu>
              <button
                type="button"
                data-testid="export-networth-menu-trigger"
                @click="toggleExportMenu('networth')"
                :disabled="analysisStore.isExporting"
                class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-200 border border-brand-border dark:border-brand-darkborder hover:bg-slate-50 dark:hover:bg-slate-700 shadow-xs transition-colors disabled:opacity-50"
                aria-haspopup="true"
                :aria-expanded="openExportMenu === 'networth'"
              >
                <svg class="w-3.5 h-3.5 text-slate-500 dark:text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                <span>Export</span>
                <svg class="w-3 h-3 text-slate-400 transition-transform" :class="{ 'rotate-180': openExportMenu === 'networth' }" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              <div
                v-if="openExportMenu === 'networth'"
                class="absolute right-0 mt-1.5 w-44 rounded-xl bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder shadow-xl z-30 py-1"
              >
                <button
                  type="button"
                  data-testid="export-networth-csv"
                  @click="triggerExport('net_worth', 'csv')"
                  class="w-full text-left px-3 py-2 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center justify-between"
                >
                  <span>CSV Spreadsheet</span>
                  <span class="text-[10px] font-mono text-slate-400 uppercase">.csv</span>
                </button>
                <button
                  type="button"
                  data-testid="export-networth-xlsx"
                  @click="triggerExport('net_worth', 'xlsx')"
                  class="w-full text-left px-3 py-2 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center justify-between border-t border-slate-100 dark:border-slate-800"
                >
                  <span>Excel Workbook</span>
                  <span class="text-[10px] font-mono text-emerald-600 dark:text-emerald-400 font-bold uppercase">.xlsx</span>
                </button>
              </div>
            </div>
          </div>

          <div class="overflow-x-auto max-h-[460px]">
            <table class="w-full text-left border-collapse text-xs">
              <thead class="sticky top-0 z-10 bg-slate-50 dark:bg-slate-900 border-b border-brand-border dark:border-brand-darkborder text-[11px] uppercase tracking-wider text-slate-500 dark:text-slate-400">
                <tr>
                  <th class="py-3 px-4 font-bold">Period End</th>
                  <th class="py-3 px-4 font-bold">Provenance</th>
                  <th class="py-3 px-4 font-bold text-right">Gross Assets</th>
                  <th class="py-3 px-4 font-bold text-right">Liabilities</th>
                  <th class="py-3 px-4 font-bold text-right">Net Worth</th>
                  <!-- Interactive Account Column Headers (Requirement 5) -->
                  <th
                    v-for="acc in (analysisStore.data?.net_worth_series[0]?.account_balances || [])"
                    :key="acc.account_id"
                    @click="analysisStore.toggleBalanceAccount(acc.account_id)"
                    class="py-3 px-4 font-bold text-right whitespace-nowrap cursor-pointer hover:bg-black/5 dark:hover:bg-white/5 transition-colors select-none group"
                    :title="`Click to ${analysisStore.selectedBalanceAccountIds.includes(acc.account_id) ? 'hide from' : 'plot on'} chart`"
                  >
                    <div class="inline-flex items-center gap-1.5 justify-end">
                      <span
                        class="w-2.5 h-2.5 rounded-full shrink-0"
                        :style="{ backgroundColor: getAccountColor(acc.account_id) }"
                      ></span>
                      <span :class="analysisStore.selectedBalanceAccountIds.includes(acc.account_id) ? 'underline font-extrabold text-slate-900 dark:text-white' : 'text-slate-600 dark:text-slate-300'">
                        {{ acc.account_name }}
                      </span>
                      <span
                        v-if="analysisStore.selectedBalanceAccountIds.includes(acc.account_id)"
                        class="px-1.5 py-0.2 rounded-full text-[9px] font-bold bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30"
                      >
                        Charted ✓
                      </span>
                      <span
                        v-else
                        class="opacity-0 group-hover:opacity-100 text-[10px] text-slate-400 transition-opacity"
                      >
                        +Chart
                      </span>
                    </div>
                  </th>
                </tr>
              </thead>
              <!-- Newest Period First (Requirement 5) -->
              <tbody class="divide-y divide-brand-border/40 dark:divide-brand-darkborder/40 tabular-nums">
                <tr
                  v-for="nw in sortedNetWorthSeries"
                  :key="nw.key"
                  class="hover:bg-black/[0.02] dark:hover:bg-white/[0.02]"
                >
                  <td class="py-2.5 px-4 font-semibold text-slate-900 dark:text-white whitespace-nowrap">
                    {{ nw.label }} <span class="text-[10px] text-slate-500 dark:text-slate-400">({{ nw.date }})</span>
                  </td>
                  <td class="py-2.5 px-4 whitespace-nowrap">
                    <span
                      v-if="nw.has_inferred_balances"
                      class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-500/30"
                    >
                      Inferred Pre-Anchor
                    </span>
                    <span
                      v-else
                      class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border border-emerald-500/30"
                    >
                      Anchor-Verified
                    </span>
                  </td>
                  <td class="py-2.5 px-4 text-right text-emerald-600 dark:text-emerald-400 font-semibold">{{ nw.formatted_total_assets }}</td>
                  <td class="py-2.5 px-4 text-right text-rose-600 dark:text-rose-400 font-semibold">{{ nw.formatted_total_debt }}</td>
                  <td class="py-2.5 px-4 text-right font-bold text-slate-900 dark:text-white">{{ nw.formatted_net_worth }}</td>
                  <td
                    v-for="ab in nw.account_balances"
                    :key="ab.account_id"
                    class="py-2.5 px-4 text-right whitespace-nowrap text-slate-800 dark:text-slate-200"
                  >
                    <span :class="{ 'font-bold': analysisStore.selectedBalanceAccountIds.includes(ab.account_id) }">
                      {{ ab.formatted_balance }}
                    </span>
                    <span
                      v-if="ab.is_inferred"
                      class="ml-1 text-[10px] text-amber-500 font-bold"
                      :title="ab.inferred_warning || 'Inferred prior to opening balance anchor'"
                    >
                      (Inferred)
                    </span>
                    <span
                      v-if="ab.reconciliation_discrepancy_pence"
                      class="ml-1 text-[10px] text-rose-500"
                      title="Observational reconciliation snapshot discrepancy"
                    >
                      (Δ {{ formatPence(ab.reconciliation_discrepancy_pence) }})
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <!-- ====================================================================== -->
      <!-- SECTION 4: INVESTMENTS (Portfolio Valuation History)                   -->
      <!-- ====================================================================== -->
      <section v-else-if="analysisStore.activeSection === 'investments'" class="space-y-6">
        <!-- Explicit Non-IRR / Sparse Checkpoint Guidance Banner -->
        <div class="p-4 rounded-2xl bg-blue-500/10 border border-blue-500/20 text-xs text-brand-forest dark:text-brand-cream flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <strong class="font-bold">Portfolio Valuation History (Not IRR or Investment Returns):</strong>
            Reflects dated holding valuation checkpoints on or before each period end. Carried-forward checkpoints are labeled with their source date; periods prior to the first checkpoint are shown as <span class="font-semibold">Unavailable</span>.
          </div>
          <span v-if="analysisStore.data?.is_investments_sparse" class="px-2.5 py-1 rounded-lg bg-amber-500/15 text-amber-600 dark:text-amber-400 font-semibold shrink-0">
            Sparse Checkpoints Detected
          </span>
        </div>

        <!-- Investments Valuation Chart -->
        <div class="bg-white dark:bg-brand-darkcard p-5 sm:p-6 rounded-2xl border border-black/8 dark:border-white/10 shadow-xs space-y-4">
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div>
              <h2 class="text-base sm:text-lg font-heading font-bold text-brand-forest dark:text-brand-cream">
                Portfolio Valuation History by Period
              </h2>
              <p class="text-xs text-brand-muted mt-0.5">
                <strong class="font-semibold text-brand-forest dark:text-brand-cream">Question answered:</strong>
                What was the recorded valuation of my investment holdings at each period-end checkpoint?
              </p>
            </div>
          </div>

          <!-- Empty State -->
          <div
            v-if="investmentsChartData.isEmpty"
            class="p-8 text-center rounded-2xl bg-slate-50 dark:bg-slate-800/40 border border-dashed border-slate-200 dark:border-slate-800 text-xs text-brand-muted"
          >
            No investment valuation checkpoints recorded for this window. Add valuation snapshots in Accounts & Categories to plot valuation history.
          </div>

          <!-- Single Point Checkpoint Banner -->
          <div
            v-else-if="investmentsChartData.isSinglePoint && investmentsChartData.points.find(p => p.is_available)"
            class="p-4 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/60 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs"
          >
            <div>
              <div class="font-bold text-slate-800 dark:text-slate-100 flex items-center gap-2">
                <span>Single Valuation Checkpoint:</span>
                <span class="font-mono text-brand-sage">{{ investmentsChartData.points.find(p => p.is_available)?.label }} ({{ investmentsChartData.points.find(p => p.is_available)?.date }})</span>
                <span
                  class="px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase"
                  :class="investmentsChartData.points.find(p => p.is_available)?.is_carried_forward ? 'bg-amber-500/20 text-amber-600 dark:text-amber-400' : 'bg-purple-500/20 text-purple-600 dark:text-purple-400'"
                >
                  {{ investmentsChartData.points.find(p => p.is_available)?.is_carried_forward ? 'Carried Forward' : 'Fresh Checkpoint' }}
                </span>
              </div>
              <p class="text-[11px] text-brand-muted mt-0.5">Select a wider range or record multiple dated checkpoints to explore portfolio trajectory.</p>
            </div>
            <div class="flex items-center gap-3 font-mono font-bold text-purple-600 dark:text-purple-400">
              <span>Valuation: {{ investmentsChartData.points.find(p => p.is_available)?.formatted }}</span>
            </div>
          </div>

          <div v-if="!investmentsChartData.isEmpty" class="w-full overflow-x-auto pb-2">
            <div class="relative min-w-[640px]" :style="{ width: investmentsChartData.width + 'px', height: '240px' }">
              <svg :width="investmentsChartData.width" :height="investmentsChartData.height" class="overflow-visible" role="region" aria-label="Portfolio Valuation History Line Chart">
                <!-- Grid Lines and Y-Axis Ticks -->
                <g v-for="tick in investmentsChartData.scale.ticks" :key="tick.valuePence">
                  <line
                    :x1="investmentsChartData.paddingLeft"
                    :y1="tick.y"
                    :x2="investmentsChartData.width - investmentsChartData.paddingRight"
                    :y2="tick.y"
                    :stroke="tick.isZero ? 'currentColor' : 'currentColor'"
                    :class="tick.isZero ? 'text-slate-400 dark:text-slate-500' : 'text-slate-200/80 dark:text-slate-800/80'"
                    :stroke-dasharray="tick.isZero ? 'none' : '3 3'"
                    :stroke-width="tick.isZero ? 1.5 : 1"
                  />
                  <text
                    :x="investmentsChartData.paddingLeft - 10"
                    :y="tick.y + 3.5"
                    text-anchor="end"
                    class="text-[10px] fill-slate-500 dark:fill-slate-400 font-mono font-medium select-none"
                  >
                    {{ tick.formattedLabel }}
                  </text>
                </g>

                <!-- Valuation Lines: Solid purple for fresh, dashed amber for carried forward. Broken on unavailable -->
                <path
                  v-for="(p, i) in investmentsChartData.freshPaths"
                  :key="'inv-fr-' + i"
                  :d="p"
                  fill="none"
                  stroke="#8B5CF6"
                  stroke-width="2.5"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
                <path
                  v-for="(p, i) in investmentsChartData.carriedForwardPaths"
                  :key="'inv-cf-' + i"
                  :d="p"
                  fill="none"
                  stroke="#F59E0B"
                  stroke-width="2.5"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-dasharray="5 3"
                />

                <!-- Points & Hover -->
                <g v-for="(pt, idx) in investmentsChartData.points" :key="idx">
                  <!-- Focus Guideline -->
                  <line
                    v-if="hoveredInvestmentsIdx === idx && pt.is_available"
                    :x1="pt.x"
                    :y1="investmentsChartData.paddingTop"
                    :x2="pt.x"
                    :y2="investmentsChartData.zeroY"
                    stroke="currentColor"
                    class="text-purple-400/50 dark:text-purple-400/70"
                    stroke-width="1.25"
                    stroke-dasharray="3 3"
                  />

                  <!-- Point Circle: Fresh valuation (solid purple circle), Carried forward (amber diamond), Unavailable (hollow slate circle) -->
                  <circle
                    v-if="pt.is_available && !pt.is_carried_forward"
                    :cx="pt.x"
                    :cy="pt.y"
                    :r="hoveredInvestmentsIdx === idx ? 5.5 : 3.5"
                    fill="#8B5CF6"
                    stroke="#7C3AED"
                    stroke-width="1.5"
                    class="transition-all"
                  />
                  <polygon
                    v-else-if="pt.is_available && pt.is_carried_forward"
                    :points="`${pt.x},${pt.y - (hoveredInvestmentsIdx === idx ? 5.5 : 4)} ${pt.x + (hoveredInvestmentsIdx === idx ? 5.5 : 4)},${pt.y} ${pt.x},${pt.y + (hoveredInvestmentsIdx === idx ? 5.5 : 4)} ${pt.x - (hoveredInvestmentsIdx === idx ? 5.5 : 4)},${pt.y}`"
                    fill="#F59E0B"
                    stroke="#D97706"
                    stroke-width="1.5"
                    class="transition-all"
                  />
                  <circle
                    v-else
                    :cx="pt.x"
                    :cy="pt.y"
                    :r="3.5"
                    fill="none"
                    stroke="#94A3B8"
                    stroke-width="1.5"
                    stroke-dasharray="2 2"
                    class="opacity-60"
                  />

                  <!-- Accessible Interactive Hit Target -->
                  <rect
                    :x="pt.x - 18"
                    :y="investmentsChartData.paddingTop"
                    width="36"
                    :height="investmentsChartData.zeroY - investmentsChartData.paddingTop"
                    fill="transparent"
                    class="cursor-pointer focus:outline-none"
                    tabindex="0"
                    role="button"
                    :aria-label="pt.accessibilityLabel"
                    @mouseenter="hoveredInvestmentsIdx = idx"
                    @mouseleave="hoveredInvestmentsIdx = null"
                    @focus="hoveredInvestmentsIdx = idx"
                    @blur="hoveredInvestmentsIdx = null"
                    @keydown.left.prevent="navigateChartPoint(idx, -1, investmentsChartData.points.length, (i) => hoveredInvestmentsIdx = i)"
                    @keydown.right.prevent="navigateChartPoint(idx, 1, investmentsChartData.points.length, (i) => hoveredInvestmentsIdx = i)"
                  />

                  <!-- X-Axis Date Labels -->
                  <g
                    v-if="shouldShowTick(idx, investmentsChartData.points.length)"
                    :transform="`translate(${pt.x}, ${investmentsChartData.height - 22})`"
                  >
                    <text text-anchor="middle" class="text-[10px] fill-brand-muted font-medium select-none">
                      {{ getAxisLabelParts(pt.label, pt.date).line1 }}
                    </text>
                    <text
                      v-if="getAxisLabelParts(pt.label, pt.date).line2"
                      y="12"
                      text-anchor="middle"
                      class="text-[9px] fill-brand-muted/80 select-none"
                    >
                      {{ getAxisLabelParts(pt.label, pt.date).line2 }}
                    </text>
                  </g>
                </g>
              </svg>

              <!-- Accessible Bounded Hover Tooltip -->
              <div
                v-if="hoveredInvestmentsIdx !== null && investmentsChartData.points[hoveredInvestmentsIdx]"
                class="absolute z-30 pointer-events-none bg-slate-950 text-white px-3.5 py-2.5 rounded-xl text-xs shadow-xl border border-white/15 space-y-1.5"
                :style="getInvestmentsTooltipStyle(investmentsChartData.points[hoveredInvestmentsIdx])"
              >
                <div class="flex items-center justify-between gap-4 font-bold border-b border-white/10 pb-1">
                  <span>{{ investmentsChartData.points[hoveredInvestmentsIdx].label }} ({{ investmentsChartData.points[hoveredInvestmentsIdx].date }})</span>
                  <span
                    class="px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase"
                    :class="{
                      'bg-purple-500/20 text-purple-300': !investmentsChartData.points[hoveredInvestmentsIdx].is_carried_forward && investmentsChartData.points[hoveredInvestmentsIdx].is_available,
                      'bg-amber-500/20 text-amber-300': investmentsChartData.points[hoveredInvestmentsIdx].is_carried_forward,
                      'bg-slate-500/20 text-slate-300': !investmentsChartData.points[hoveredInvestmentsIdx].is_available
                    }"
                  >
                    {{ !investmentsChartData.points[hoveredInvestmentsIdx].is_available ? 'Unavailable' : investmentsChartData.points[hoveredInvestmentsIdx].is_carried_forward ? 'Carried Forward' : 'Fresh Valuation' }}
                  </span>
                </div>
                <div v-if="investmentsChartData.points[hoveredInvestmentsIdx].is_available" class="flex items-center justify-between gap-4">
                  <span class="text-slate-300">Total Valuation:</span>
                  <span class="font-mono font-bold text-purple-300">{{ investmentsChartData.points[hoveredInvestmentsIdx].formatted }}</span>
                </div>
                <div v-else class="text-[11px] text-slate-400">
                  No valuation recorded for this period
                </div>
                <div v-if="investmentsChartData.points[hoveredInvestmentsIdx].is_carried_forward && investmentsChartData.points[hoveredInvestmentsIdx].cf_date" class="text-[10px] text-amber-300/90">
                  Carried forward from {{ investmentsChartData.points[hoveredInvestmentsIdx].cf_date }}
                </div>
                <div v-if="investmentsChartData.points[hoveredInvestmentsIdx].is_available" class="text-[10px] text-slate-400">
                  {{ investmentsChartData.points[hoveredInvestmentsIdx].valued_count }} of {{ investmentsChartData.points[hoveredInvestmentsIdx].holdings_count }} accounts valued
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Investments Table (With CSV & XLSX Export) -->
        <div class="bg-white dark:bg-brand-darkcard rounded-2xl border border-black/8 dark:border-white/10 shadow-xs overflow-hidden">
          <div class="p-4 sm:p-5 border-b border-black/5 dark:border-white/5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h3 class="text-base font-heading font-bold text-brand-forest dark:text-brand-cream">
                Investment Valuation Checkpoints by Period
              </h3>
              <p class="text-xs text-brand-muted mt-0.5">
                Dated checkpoint valuations and carried-forward provenance per investment account.
              </p>
            </div>
            <!-- Export Menu -->
            <div class="relative inline-block text-left" data-export-menu>
              <button
                type="button"
                data-testid="export-investments-menu-trigger"
                @click="toggleExportMenu('investments')"
                :disabled="analysisStore.isExporting"
                class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-200 border border-brand-border dark:border-brand-darkborder hover:bg-slate-50 dark:hover:bg-slate-700 shadow-xs transition-colors disabled:opacity-50"
                aria-haspopup="true"
                :aria-expanded="openExportMenu === 'investments'"
              >
                <svg class="w-3.5 h-3.5 text-slate-500 dark:text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                <span>Export</span>
                <svg class="w-3 h-3 text-slate-400 transition-transform" :class="{ 'rotate-180': openExportMenu === 'investments' }" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              <div
                v-if="openExportMenu === 'investments'"
                class="absolute right-0 mt-1.5 w-44 rounded-xl bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder shadow-xl z-30 py-1"
              >
                <button
                  type="button"
                  data-testid="export-investments-csv"
                  @click="triggerExport('investments', 'csv')"
                  class="w-full text-left px-3 py-2 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center justify-between"
                >
                  <span>CSV Spreadsheet</span>
                  <span class="text-[10px] font-mono text-slate-400 uppercase">.csv</span>
                </button>
                <button
                  type="button"
                  data-testid="export-investments-xlsx"
                  @click="triggerExport('investments', 'xlsx')"
                  class="w-full text-left px-3 py-2 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center justify-between border-t border-slate-100 dark:border-slate-800"
                >
                  <span>Excel Workbook</span>
                  <span class="text-[10px] font-mono text-emerald-600 dark:text-emerald-400 font-bold uppercase">.xlsx</span>
                </button>
              </div>
            </div>
          </div>

          <div class="overflow-x-auto max-h-[420px]">
            <table class="w-full text-left border-collapse text-xs">
              <thead class="sticky top-0 z-10 bg-brand-cream dark:bg-brand-darkbg border-b border-black/10 dark:border-white/10 text-[11px] uppercase tracking-wider text-brand-muted">
                <tr>
                  <th class="py-3 px-4 font-bold">Period End</th>
                  <th class="py-3 px-4 font-bold">Checkpoint Status</th>
                  <th class="py-3 px-4 font-bold text-right">Valued Holdings</th>
                  <th class="py-3 px-4 font-bold text-right">Total Portfolio Value</th>
                  <th
                    v-for="acc in (analysisStore.data?.investments_series[0]?.accounts || [])"
                    :key="acc.account_id"
                    class="py-3 px-4 font-bold text-right whitespace-nowrap"
                  >
                    {{ acc.account_name }}
                  </th>
                </tr>
              </thead>
              <tbody class="divide-y divide-black/5 dark:divide-white/5 tabular-nums">
                <tr
                  v-for="ib in (analysisStore.data?.investments_series || [])"
                  :key="ib.key"
                  class="hover:bg-black/[0.02] dark:hover:bg-white/[0.02]"
                >
                  <td class="py-2.5 px-4 font-semibold text-brand-forest dark:text-brand-cream whitespace-nowrap">
                    {{ ib.label }} <span class="text-[10px] text-brand-muted">({{ ib.date }})</span>
                  </td>
                  <td class="py-2.5 px-4 whitespace-nowrap">
                    <span
                      v-if="!ib.is_available"
                      class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-500/15 text-brand-muted"
                    >
                      Unavailable
                    </span>
                    <span
                      v-else-if="ib.is_carried_forward"
                      class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/15 text-amber-600 dark:text-amber-400"
                    >
                      Carried forward (from {{ ib.carried_forward_date }})
                    </span>
                    <span
                      v-else
                      class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                    >
                      Checkpoint ({{ ib.valuation_date }})
                    </span>
                  </td>
                  <td class="py-2.5 px-4 text-right text-brand-muted">
                    {{ ib.valued_count }} / {{ ib.holdings_count }}
                  </td>
                  <td class="py-2.5 px-4 text-right font-bold text-brand-forest dark:text-brand-cream">
                    {{ ib.formatted_total_valuation }}
                  </td>
                  <td
                    v-for="acc in ib.accounts"
                    :key="acc.account_id"
                    class="py-2.5 px-4 text-right whitespace-nowrap"
                  >
                    {{ acc.formatted_valuation }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue';
import { useRoute } from 'vue-router';
import { useAnalysisStore } from '../stores/analysis';
import { useAccountsStore } from '../stores/accounts';
import SharedFilterToolbar from '../components/SharedFilterToolbar.vue';
import type { AnalysisExportReportType, AnalysisExportFormat } from '../types';
import {
  computeNiceScale,
  formatAxisCurrency,
  formatTooltipCurrency,
  computeTooltipCoords,
  buildSvgPath,
  buildSegmentedPaths,
} from '../utils/chartEngine';

const route = useRoute();
const analysisStore = useAnalysisStore();
const accountsStore = useAccountsStore();

const sections = [
  { id: 'overview', label: 'Overview & Cash Flow' },
  { id: 'spending', label: 'Spending' },
  { id: 'networth', label: 'Balances & Net Worth' },
  { id: 'investments', label: 'Investments' },
];

// Mobile Toolbar State
const isMobileControlsExpanded = ref<boolean>(false);

const activeSectionLabel = computed(() => {
  const sec = sections.find(s => s.id === analysisStore.activeSection);
  return sec ? sec.label : 'Overview';
});

const shortRangeLabel = computed(() => {
  if (!analysisStore.data) return '';
  const r = analysisStore.data.range_info;
  if (analysisStore.selectedPreset === 'all') return 'All Time';
  if (analysisStore.selectedPreset === 'custom') return `${r.start_date} – ${r.end_date}`;
  return r.preset.toUpperCase();
});

const activeFilterCount = computed(() => analysisStore.activeFilterChips.length);

function handleSharedPresetChange(preset: string) {
  analysisStore.savePreferences();
  if (preset !== 'custom') {
    analysisStore.loadAnalysis({ preset, offset: 0, interval: undefined });
  }
}

function handleSharedRefresh() {
  analysisStore.savePreferences();
  analysisStore.loadAnalysis();
}

// Export Menu State
const openExportMenu = ref<string | null>(null);

function toggleExportMenu(menuId: string) {
  openExportMenu.value = openExportMenu.value === menuId ? null : menuId;
}

async function triggerExport(reportType: AnalysisExportReportType, format: AnalysisExportFormat) {
  openExportMenu.value = null;
  await analysisStore.exportReport(reportType, format);
}

// Interactive Chart Hover State
const hoveredCumulativeIdx = ref<number | null>(null);
const hoveredDonutIdx = ref<number | null>(null);
const hoveredStackedIdx = ref<number | null>(null);
const hoveredSpendLineIdx = ref<number | null>(null);
const hoveredNwIdx = ref<number | null>(null);
const hoveredInvestmentsIdx = ref<number | null>(null);

function navigateChartPoint(
  currentIdx: number,
  direction: -1 | 1,
  totalPoints: number,
  setter: (idx: number) => void
) {
  const nextIdx = Math.max(0, Math.min(totalPoints - 1, currentIdx + direction));
  setter(nextIdx);
}

function getCumulativeTooltipStyle(pt: any) {
  if (!pt) return {};
  const y = getCumulativeTooltipY(pt);
  const { left, top } = computeTooltipCoords(pt.x, y, cumulativeChartData.value.width, cumulativeChartData.value.height, 220, 110);
  return { left: `${left}px`, top: `${top}px` };
}

function getSpendTooltipStyle(pt: any) {
  if (!pt) return {};
  const { left, top } = computeTooltipCoords(pt.x, pt.totalY, spendingLineChartData.value.width, spendingLineChartData.value.height, 240, 140);
  return { left: `${left}px`, top: `${top}px` };
}

function getNetWorthTooltipStyle(pt: any) {
  if (!pt) return {};
  const { left, top } = computeTooltipCoords(pt.x, pt.y, netWorthChartData.value.width, netWorthChartData.value.height, 250, 150);
  return { left: `${left}px`, top: `${top}px` };
}

function getInvestmentsTooltipStyle(pt: any) {
  if (!pt) return {};
  const { left, top } = computeTooltipCoords(pt.x, pt.y, investmentsChartData.value.width, investmentsChartData.value.height, 240, 120);
  return { left: `${left}px`, top: `${top}px` };
}

// Cumulative Series Visibility Toggles
const showCumulativeIncome = ref(true);
const showCumulativeSpending = ref(true);
const showCumulativeNetSavings = ref(true);

function closeFilterPopovers() {
  openExportMenu.value = null;
}

function handleDocumentClick(e: MouseEvent) {
  if (openExportMenu.value) {
    const insideMenu = (e.target as HTMLElement | null)?.closest('[data-export-menu]');
    if (!insideMenu) {
      openExportMenu.value = null;
    }
  }
}

function formatPence(pence: number): string {
  const sym = analysisStore.data?.currency_symbol || '£';
  const sign = pence < 0 ? '-' : '';
  return `${sign}${sym}${(Math.abs(pence) / 100).toFixed(2)}`;
}

// Account Color Lookup
function getAccountColor(accountId: number): string {
  const fromSeries = analysisStore.data?.net_worth_series[0]?.account_balances.find(a => a.account_id === accountId);
  if (fromSeries?.color) return fromSeries.color;
  const fromAvailable = analysisStore.data?.available_accounts.find(a => a.id === accountId);
  if (fromAvailable?.color) return fromAvailable.color;
  return '#64748B';
}

// Balances & Net Worth: Table ordered newest period first (Requirement 5)
const sortedNetWorthSeries = computed(() => {
  return [...(analysisStore.data?.net_worth_series || [])].reverse();
});

const latestNetWorthBucket = computed(() => {
  const s = analysisStore.data?.net_worth_series || [];
  return s.length > 0 ? s[s.length - 1] : null;
});

const hasAnyInferredBalances = computed(() => {
  return (analysisStore.data?.net_worth_series || []).some(b => b.has_inferred_balances);
});

// Redesigned Spending Trajectory Computeds & Helpers (Requirement 4)
const spendingFocusCategory = computed(() => {
  if (analysisStore.spendingFocusCategoryId === null) return null;
  if (analysisStore.spendingFocusCategoryId === 0) {
    return { id: 0, name: 'Uncategorised', color: '#94A3B8', default_nature: 'unclassified' };
  }
  return analysisStore.data?.available_categories.find(c => c.id === analysisStore.spendingFocusCategoryId) || null;
});

const spendingTrajectoryBars = computed(() => {
  const series = analysisStore.data?.time_series || [];
  const focusCatId = analysisStore.spendingFocusCategoryId;
  const fallbackColors = [
    '#3B82F6', '#10B981', '#F59E0B', '#EC4899', '#8B5CF6',
    '#14B8A6', '#F97316', '#6366F1', '#84CC16', '#06B6D4'
  ];

  return series.map((b, idx) => {
    let amountPence = 0;
    let formattedAmount = '';
    let categorySegments: Array<{ name: string; color: string; pct: number }> = [];
    let topMovers: Array<{ name: string; isPositive: boolean; formattedDelta: string }> = [];

    if (focusCatId === null) {
      amountPence = b.expenses_pence;
      formattedAmount = b.formatted_expenses;
      const details = b.category_spending_details || [];
      if (details.length > 0 && amountPence > 0) {
        const sorted = [...details].sort((x, y) => y.amount_pence - x.amount_pence);
        categorySegments = sorted.map((seg, sIdx) => ({
          name: seg.category_name,
          color: seg.category_color || fallbackColors[sIdx % fallbackColors.length],
          pct: Math.max(1, Math.round((seg.amount_pence / amountPence) * 100)),
        }));
      } else if (amountPence > 0) {
        categorySegments = [{ name: 'Spend', color: '#8B5CF6', pct: 100 }];
      }

      // Compute top movers vs previous bucket
      if (idx > 0) {
        const prevB = series[idx - 1];
        const prevDetails = prevB.category_spending_details || [];
        const prevMap = new Map<string, number>();
        for (const pd of prevDetails) {
          prevMap.set(pd.category_name, pd.amount_pence);
        }
        const deltas: Array<{ name: string; delta: number }> = [];
        for (const curr of details) {
          const prevVal = prevMap.get(curr.category_name) || 0;
          deltas.push({ name: curr.category_name, delta: curr.amount_pence - prevVal });
        }
        for (const prev of prevDetails) {
          if (!details.some(d => d.category_name === prev.category_name)) {
            deltas.push({ name: prev.category_name, delta: -prev.amount_pence });
          }
        }
        deltas.sort((x, y) => Math.abs(y.delta) - Math.abs(x.delta));
        topMovers = deltas.slice(0, 3).map(d => ({
          name: d.name,
          isPositive: d.delta > 0,
          formattedDelta: `${d.delta > 0 ? '+' : '-'}${formatPence(Math.abs(d.delta))}`,
        }));
      }
    } else {
      const item = b.category_spending_details?.find(c => (c.category_id ?? 0) === focusCatId);
      amountPence = item?.amount_pence || 0;
      formattedAmount = item ? item.formatted_amount : formatPence(0);
      const catColor = item?.category_color || spendingFocusCategory.value?.color || '#8B5CF6';
      const catName = item?.category_name || spendingFocusCategory.value?.name || 'Category';
      categorySegments = amountPence > 0 ? [{ name: catName, color: catColor, pct: 100 }] : [];
    }

    // Delta vs previous bucket
    let deltaPct: number | null = null;
    let deltaPence: number | null = null;
    if (idx > 0) {
      let prevAmount = 0;
      const prevB = series[idx - 1];
      if (focusCatId === null) {
        prevAmount = prevB.expenses_pence;
      } else {
        const prevItem = prevB.category_spending_details?.find(c => (c.category_id ?? 0) === focusCatId);
        prevAmount = prevItem?.amount_pence || 0;
      }
      deltaPence = amountPence - prevAmount;
      if (prevAmount > 0) {
        deltaPct = Math.round(((amountPence - prevAmount) / prevAmount) * 100);
      } else if (amountPence > 0) {
        deltaPct = 100;
      } else {
        deltaPct = 0;
      }
    }

    return {
      key: b.key,
      label: b.label,
      start_date: b.start_date,
      end_date: b.end_date,
      amount_pence: amountPence,
      formatted_amount: formattedAmount,
      delta_pct: deltaPct,
      delta_pence: deltaPence,
      category_segments: categorySegments,
      top_movers: topMovers,
    };
  });
});

const spendingTrajectoryMaxPence = computed(() => {
  const bars = spendingTrajectoryBars.value;
  if (bars.length === 0) return 1000;
  return Math.max(...bars.map(b => b.amount_pence), 1000);
});

const spendingTrajectoryAveragePence = computed(() => {
  const bars = spendingTrajectoryBars.value;
  if (bars.length === 0) return 0;
  const sum = bars.reduce((acc, b) => acc + b.amount_pence, 0);
  return Math.round(sum / bars.length);
});

const spendingTrajectoryStats = computed(() => {
  const bars = spendingTrajectoryBars.value;
  const sym = analysisStore.data?.currency_symbol || '£';
  if (bars.length === 0) {
    return {
      formattedTotal: `${sym}0.00`,
      totalSharePct: 0,
      formattedAverage: `${sym}0.00`,
      peakLabel: '—',
      peakAmount: `${sym}0.00`,
    };
  }

  const totalPence = bars.reduce((acc, b) => acc + b.amount_pence, 0);
  let peak = bars[0];
  for (const b of bars) {
    if (b.amount_pence > peak.amount_pence) {
      peak = b;
    }
  }

  let totalSharePct = 100;
  if (analysisStore.spendingFocusCategoryId !== null && analysisStore.data?.totals.expenses_pence) {
    totalSharePct = Math.round((totalPence / analysisStore.data.totals.expenses_pence) * 100);
  }

  return {
    formattedTotal: formatPence(totalPence),
    totalSharePct,
    formattedAverage: formatPence(spendingTrajectoryAveragePence.value),
    peakLabel: peak.label,
    peakAmount: peak.formatted_amount,
  };
});

function getPeriodCategoryLedgerUrl(b: { start_date?: string; end_date?: string }, categoryId?: number | null): string {
  const params = new URLSearchParams();
  if (b.start_date) params.set('start_date', b.start_date);
  if (b.end_date) params.set('end_date', b.end_date);
  if (analysisStore.selectedAccountId !== null) {
    params.set('account_id', String(analysisStore.selectedAccountId));
  }
  if (categoryId !== undefined && categoryId !== null) {
    if (categoryId === 0) {
      params.set('uncategorized_only', 'true');
    } else {
      params.set('category_id', String(categoryId));
    }
  } else if (analysisStore.selectedCategoryId !== null) {
    if (analysisStore.selectedCategoryId === 0) {
      params.set('uncategorized_only', 'true');
    } else {
      params.set('category_id', String(analysisStore.selectedCategoryId));
    }
  }
  return `/ledger?${params.toString()}`;
}

// Axis & Chart Helpers
function getAxisLabelParts(label: string, dateStr?: string): { line1: string; line2: string } {
  if (!label) return { line1: '', line2: '' };
  if (dateStr) {
    const parts = dateStr.split('-');
    if (parts.length === 3) {
      const year = parts[0];
      const monthIdx = parseInt(parts[1], 10) - 1;
      const day = parseInt(parts[2], 10);
      const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      const monthName = monthNames[monthIdx] || '';

      if (label.match(/^\d{1,2}\s+[A-Za-z]+/)) {
        return { line1: String(day), line2: monthName };
      }
      if (label.includes('–') || label.includes('-')) {
        const chunks = label.split(/[–-]/);
        if (chunks.length === 2) {
          return { line1: chunks[0].trim(), line2: chunks[1].trim() };
        }
      }
      if (label.match(/^[A-Za-z]{3}\s+\d{4}$/)) {
        return { line1: monthName, line2: year };
      }
      if (label.startsWith('Q')) {
        const qParts = label.split(' ');
        return { line1: qParts[0], line2: qParts[1] || year };
      }
    }
  }
  const spaceParts = label.split(' ');
  if (spaceParts.length === 2) {
    return { line1: spaceParts[0], line2: spaceParts[1] };
  }
  return { line1: label, line2: '' };
}

function shouldShowTick(index: number, total: number): boolean {
  if (total <= 7) return true;
  if (total <= 14) return index % 2 === 0 || index === total - 1;
  if (total <= 31) return index % 4 === 0 || index === total - 1;
  if (total <= 60) return index % 7 === 0 || index === total - 1;
  if (total <= 120) return index % 14 === 0 || index === total - 1;
  return index % 25 === 0 || index === total - 1;
}

function getBarHeight(valPence: number): number {
  if (!analysisStore.data || analysisStore.data.time_series.length === 0) return 0;
  const maxVal = Math.max(
    ...analysisStore.data.time_series.map(b => Math.max(b.income_pence, b.expenses_pence)),
    1
  );
  return Math.max(4, Math.min(100, (valPence / maxVal) * 100));
}

function getCumulativeSvgWidth(): number {
  const count = analysisStore.data?.time_series.length || 0;
  return Math.max(640, count * 36);
}

function getNetWorthSvgWidth(): number {
  const count = analysisStore.data?.net_worth_series.length || 0;
  return Math.max(640, count * 36);
}

function getInvestmentsSvgWidth(): number {
  const count = analysisStore.data?.investments_series.length || 0;
  return Math.max(640, count * 36);
}

// Spending Multi-Series Line Chart Calculation
const spendingLineChartData = computed(() => {
  const series = analysisStore.data?.time_series || [];
  const count = series.length;
  const width = Math.max(640, count * 36);
  const height = 230;
  const paddingTop = 24;
  const paddingBottom = 44;
  const paddingLeft = 70;
  const paddingRight = 24;
  const plotWidth = width - paddingLeft - paddingRight;
  const plotHeight = height - paddingTop - paddingBottom;
  const sym = analysisStore.data?.currency_symbol || '£';
  const currency = analysisStore.data?.currency || 'GBP';

  if (count === 0) {
    const scale = computeNiceScale(0, 0, plotHeight, paddingTop, { currency, currencySymbol: sym, forceZero: true });
    return {
      width,
      height,
      zeroY: scale.zeroY,
      paddingLeft,
      paddingRight,
      paddingTop,
      formattedMax: `${sym}0`,
      totalLinePath: '',
      totalAreaPath: '',
      totalSolidPaths: [],
      totalDashedPaths: [],
      categoryLines: [],
      natureLines: [],
      points: [],
      scale,
      isEmpty: true,
      isSinglePoint: false,
    };
  }

  // Collect values across all active series to compute scale
  const allValues: number[] = [0];
  if (analysisStore.showTotalSpendLine) {
    for (const b of series) allValues.push(b.expenses_pence || 0);
  }

  if (analysisStore.spendingGroupingMode === 'nature') {
    if (analysisStore.showNatureLines.fixed) {
      for (const b of series) allValues.push(b.fixed_expenses_pence || 0);
    }
    if (analysisStore.showNatureLines.variable) {
      for (const b of series) allValues.push(b.variable_expenses_pence || 0);
    }
    if (analysisStore.showNatureLines.unclassified) {
      for (const b of series) allValues.push(b.unclassified_expenses_pence || 0);
    }
  } else {
    for (const catId of analysisStore.selectedCategoryLineIds) {
      for (const b of series) {
        const item = b.category_spending_details?.find(c => c.category_id === catId);
        if (item) allValues.push(item.amount_pence || 0);
      }
    }
  }

  const minPence = Math.min(...allValues);
  const maxPence = Math.max(...allValues);

  const scale = computeNiceScale(minPence, maxPence, plotHeight, paddingTop, {
    currency,
    currencySymbol: sym,
    forceZero: true,
  });

  const getY = scale.getY;
  const zeroY = scale.zeroY;

  const points = series.map((b, i) => {
    const x = paddingLeft + (count === 1 ? plotWidth / 2 : (i / (count - 1)) * plotWidth);
    const exp = b.expenses_pence || 0;
    const totalY = getY(exp);
    const isPlanned = !!(b.is_planned || (b.planned_expenses_pence && b.planned_expenses_pence > 0));

    // Category items details for tooltip
    const categoryItems = (analysisStore.selectedCategoryLineIds || []).map(catId => {
      const catMeta = analysisStore.data?.available_categories.find(c => c.id === catId);
      const item = b.category_spending_details?.find(c => c.category_id === catId);
      const amt = item?.amount_pence || 0;
      return {
        id: catId,
        name: catMeta?.name || 'Category',
        color: catMeta?.color || '#8B5CF6',
        amount_pence: amt,
        formattedAmount: item?.formatted_amount || formatTooltipCurrency(amt, currency, sym),
        y: getY(amt),
      };
    });

    return {
      x,
      totalY,
      label: b.label,
      start_date: b.start_date,
      end_date: b.end_date,
      is_planned: isPlanned,
      formattedTotal: b.formatted_expenses || formatTooltipCurrency(exp, currency, sym),
      expenses_pence: exp,
      formattedFixed: formatTooltipCurrency(b.fixed_expenses_pence || 0, currency, sym),
      formattedVariable: formatTooltipCurrency(b.variable_expenses_pence || 0, currency, sym),
      formattedUnclassified: formatTooltipCurrency(b.unclassified_expenses_pence || 0, currency, sym),
      categoryItems,
      fixedY: getY(b.fixed_expenses_pence || 0),
      variableY: getY(b.variable_expenses_pence || 0),
      unclassifiedY: getY(b.unclassified_expenses_pence || 0),
      accessibilityLabel: `${b.label}: Total Spend ${b.formatted_expenses || formatTooltipCurrency(exp, currency, sym)}${isPlanned ? ' (Planned)' : ''}`,
    };
  });

  // Total line segmented paths
  const totalSeg = buildSegmentedPaths(points.map(p => ({ x: p.x, y: p.totalY, isDashed: p.is_planned })));
  const totalLinePath = buildSvgPath(points.map(p => ({ x: p.x, y: p.totalY })));
  let totalAreaPath = '';
  if (points.length > 0) {
    totalAreaPath = `M ${points[0].x} ${zeroY} L ${points[0].x} ${points[0].totalY} `;
    for (let i = 1; i < points.length; i++) {
      totalAreaPath += `L ${points[i].x} ${points[i].totalY} `;
    }
    totalAreaPath += `L ${points[points.length - 1].x} ${zeroY} Z`;
  }

  // Category Lines
  const categoryLines: Array<{ id: number; name: string; color: string; path: string; solidPaths: string[]; dashedPaths: string[] }> = [];
  if (analysisStore.spendingGroupingMode === 'category') {
    for (const catId of analysisStore.selectedCategoryLineIds) {
      const catMeta = analysisStore.data?.available_categories.find(c => c.id === catId);
      const color = catMeta?.color || '#8B5CF6';
      const name = catMeta?.name || 'Category';
      const catPts = points.map(p => {
        const it = p.categoryItems.find(c => c.id === catId);
        return { x: p.x, y: it?.y ?? zeroY, isDashed: p.is_planned };
      });
      const seg = buildSegmentedPaths(catPts);
      const path = buildSvgPath(catPts);
      categoryLines.push({ id: catId, name, color, path, solidPaths: seg.solidPaths, dashedPaths: seg.dashedPaths });
    }
  }

  // Nature Lines
  const natureLines: Array<{ nature: string; label: string; color: string; strokeDasharray: string; path: string; solidPaths: string[]; dashedPaths: string[] }> = [];
  if (analysisStore.spendingGroupingMode === 'nature') {
    if (analysisStore.showNatureLines.fixed) {
      const fixedPts = points.map(p => ({ x: p.x, y: p.fixedY, isDashed: p.is_planned }));
      const seg = buildSegmentedPaths(fixedPts);
      natureLines.push({ nature: 'fixed', label: 'Fixed', color: '#6366F1', strokeDasharray: 'none', path: buildSvgPath(fixedPts), solidPaths: seg.solidPaths, dashedPaths: seg.dashedPaths });
    }
    if (analysisStore.showNatureLines.variable) {
      const varPts = points.map(p => ({ x: p.x, y: p.variableY, isDashed: p.is_planned }));
      const seg = buildSegmentedPaths(varPts);
      natureLines.push({ nature: 'variable', label: 'Variable', color: '#F59E0B', strokeDasharray: '6 4', path: buildSvgPath(varPts), solidPaths: seg.solidPaths, dashedPaths: seg.dashedPaths });
    }
    if (analysisStore.showNatureLines.unclassified) {
      const uncPts = points.map(p => ({ x: p.x, y: p.unclassifiedY, isDashed: p.is_planned }));
      const seg = buildSegmentedPaths(uncPts);
      natureLines.push({ nature: 'unclassified', label: 'Unclassified', color: '#94A3B8', strokeDasharray: '2 3', path: buildSvgPath(uncPts), solidPaths: seg.solidPaths, dashedPaths: seg.dashedPaths });
    }
  }

  return {
    width,
    height,
    zeroY,
    paddingLeft,
    paddingRight,
    paddingTop,
    scale,
    formattedMax: formatAxisCurrency(scale.maxPence, currency, sym),
    formattedMin: formatAxisCurrency(scale.minPence, currency, sym),
    totalLinePath: totalLinePath.trim(),
    totalAreaPath: totalAreaPath.trim(),
    totalSolidPaths: totalSeg.solidPaths,
    totalDashedPaths: totalSeg.dashedPaths,
    categoryLines,
    natureLines,
    points,
    isEmpty: false,
    isSinglePoint: count === 1,
  };
});

// Spending Matrix Computed & Drilldown Helpers
const matrixPeriods = computed(() => analysisStore.data?.spending_matrix?.periods || []);
const matrixRows = computed(() => analysisStore.data?.spending_matrix?.rows || []);

function getCellAmountPence(row: any, col: any): number {
  const cell = row?.cells?.[col.key];
  return cell ? cell.amount_pence : 0;
}

function appendActiveAccountAndCategoryParams(params: URLSearchParams, includeCategory = true) {
  if (analysisStore.selectedAccountIds.length > 1) {
    params.set('account_ids', analysisStore.selectedAccountIds.join(','));
  } else if (analysisStore.selectedAccountId !== null) {
    params.set('account_id', String(analysisStore.selectedAccountId));
  }
  if (includeCategory) {
    if (analysisStore.selectedCategoryIds.length > 1) {
      params.set('category_ids', analysisStore.selectedCategoryIds.join(','));
    } else if (analysisStore.selectedCategoryId !== null) {
      if (analysisStore.selectedCategoryId === 0) {
        params.set('uncategorized_only', 'true');
      } else {
        params.set('category_id', String(analysisStore.selectedCategoryId));
      }
    }
  }
}

function getScopeLedgerUrl(): string {
  const params = new URLSearchParams();
  if (analysisStore.data?.range_info.start_date) params.set('start_date', analysisStore.data.range_info.start_date);
  if (analysisStore.data?.range_info.end_date) params.set('end_date', analysisStore.data.range_info.end_date);
  appendActiveAccountAndCategoryParams(params, true);
  return `/ledger?${params.toString()}`;
}

function getBucketLedgerUrl(b: { start_date: string; end_date: string }): string {
  const params = new URLSearchParams();
  if (b.start_date) params.set('start_date', b.start_date);
  if (b.end_date) params.set('end_date', b.end_date);
  appendActiveAccountAndCategoryParams(params, true);
  return `/ledger?${params.toString()}`;
}

function getCellDrilldownUrl(row: any, col: any): string {
  const params = new URLSearchParams();
  if (row.is_uncategorized || row.category_id === null || row.category_id === undefined) {
    params.set('uncategorized_only', 'true');
  } else {
    params.set('category_id', String(row.category_id));
  }
  if (col.start_date) params.set('start_date', col.start_date);
  if (col.end_date) params.set('end_date', col.end_date);
  appendActiveAccountAndCategoryParams(params, false);
  return `/ledger?${params.toString()}`;
}

function getRowDrilldownUrl(row: any): string {
  const params = new URLSearchParams();
  if (row.is_uncategorized || row.category_id === null || row.category_id === undefined) {
    params.set('uncategorized_only', 'true');
  } else {
    params.set('category_id', String(row.category_id));
  }
  if (analysisStore.data?.range_info.start_date) params.set('start_date', analysisStore.data.range_info.start_date);
  if (analysisStore.data?.range_info.end_date) params.set('end_date', analysisStore.data.range_info.end_date);
  appendActiveAccountAndCategoryParams(params, false);
  return `/ledger?${params.toString()}`;
}

function getColumnDrilldownUrl(col: any): string {
  const params = new URLSearchParams();
  if (col.start_date) params.set('start_date', col.start_date);
  if (col.end_date) params.set('end_date', col.end_date);
  appendActiveAccountAndCategoryParams(params, true);
  return `/ledger?${params.toString()}`;
}

function getGrandTotalDrilldownUrl(): string {
  return getScopeLedgerUrl();
}

// Donut Chart Calculation (Composition in Selected Range)
const donutChartData = computed(() => {
  const sym = analysisStore.data?.currency_symbol || '£';
  if (!analysisStore.data) return { segments: [], totalPence: 0, formattedTotal: `${sym}0.00` };
  const cats = analysisStore.data.categories.filter(c => c.total_pence > 0);
  const fallbackColors = [
    '#3B82F6', '#10B981', '#F59E0B', '#EC4899', '#8B5CF6',
    '#14B8A6', '#F97316', '#6366F1', '#84CC16', '#06B6D4'
  ];

  const totalPence = cats.reduce((sum, c) => sum + c.total_pence, 0);
  if (totalPence <= 0) return { segments: [], totalPence: 0, formattedTotal: `${sym}0.00` };

  let currentAngle = -Math.PI / 2;
  const cx = 100;
  const cy = 100;
  const outerR = 80;
  const innerR = 52;

  const segments = cats.map((cat, idx) => {
    const fraction = cat.total_pence / totalPence;
    const angleDelta = fraction * 2 * Math.PI;
    const startAngle = currentAngle;
    const endAngle = currentAngle + Math.min(angleDelta, 2 * Math.PI - 0.0001);
    currentAngle += angleDelta;

    const x1_out = cx + outerR * Math.cos(startAngle);
    const y1_out = cy + outerR * Math.sin(startAngle);
    const x2_out = cx + outerR * Math.cos(endAngle);
    const y2_out = cy + outerR * Math.sin(endAngle);

    const x1_in = cx + innerR * Math.cos(startAngle);
    const y1_in = cy + innerR * Math.sin(startAngle);
    const x2_in = cx + innerR * Math.cos(endAngle);
    const y2_in = cy + innerR * Math.sin(endAngle);

    const largeArc = angleDelta > Math.PI ? 1 : 0;
    const path = `M ${x1_out} ${y1_out} A ${outerR} ${outerR} 0 ${largeArc} 1 ${x2_out} ${y2_out} L ${x2_in} ${y2_in} A ${innerR} ${innerR} 0 ${largeArc} 0 ${x1_in} ${y1_in} Z`;
    const color = cat.category_color || fallbackColors[idx % fallbackColors.length];

    return {
      category_id: cat.category_id,
      category_name: cat.category_name,
      category_color: color,
      expense_nature: cat.expense_nature,
      total_pence: cat.total_pence,
      formatted_total: cat.formatted_total,
      percentage: cat.percentage,
      transaction_count: cat.transaction_count,
      path,
    };
  });

  return {
    segments,
    totalPence,
    formattedTotal: analysisStore.data.totals.formatted_expenses,
  };
});

function getCumulativeTooltipY(pt: any): number {
  if (!pt) return 50;
  const visibleYs: number[] = [];
  if (showCumulativeIncome.value) visibleYs.push(pt.yIncome);
  if (showCumulativeSpending.value) visibleYs.push(pt.ySpending);
  if (showCumulativeNetSavings.value) visibleYs.push(pt.yNetSavings);
  return visibleYs.length > 0 ? Math.min(...visibleYs) : 50;
}

const cumulativeChartData = computed(() => {
  const series = analysisStore.data?.time_series || [];
  const count = series.length;
  const width = getCumulativeSvgWidth();
  const height = 240;
  const paddingTop = 24;
  const paddingBottom = 44;
  const paddingLeft = 70;
  const paddingRight = 24;
  const plotWidth = width - paddingLeft - paddingRight;
  const plotHeight = height - paddingTop - paddingBottom;
  const sym = analysisStore.data?.currency_symbol || '£';
  const currency = analysisStore.data?.currency || 'GBP';

  if (count === 0) {
    const scale = computeNiceScale(0, 0, plotHeight, paddingTop, { currency, currencySymbol: sym, forceZero: true });
    return {
      width,
      height,
      zeroY: scale.zeroY,
      paddingTop,
      paddingLeft,
      paddingRight,
      bottomY: paddingTop + plotHeight,
      incomeLinePath: '',
      spendingLinePath: '',
      netSavingsLinePath: '',
      incomeSolidPaths: [],
      incomeDashedPaths: [],
      spendingSolidPaths: [],
      spendingDashedPaths: [],
      netSavingsSolidPaths: [],
      netSavingsDashedPaths: [],
      points: [],
      scale,
      formattedMax: `${sym}0`,
      formattedMin: `${sym}0`,
      hasNegativeMin: false,
      isEmpty: true,
      isSinglePoint: false,
    };
  }

  const visibleValues: number[] = [0];
  if (showCumulativeIncome.value) {
    for (const b of series) visibleValues.push(b.cumulative_income_pence ?? 0);
  }
  if (showCumulativeSpending.value) {
    for (const b of series) visibleValues.push(b.cumulative_expenses_pence ?? 0);
  }
  if (showCumulativeNetSavings.value) {
    for (const b of series) {
      visibleValues.push(b.cumulative_net_savings_pence ?? ((b.cumulative_income_pence ?? 0) - (b.cumulative_expenses_pence ?? 0)));
    }
  }

  const minVal = Math.min(...visibleValues);
  const maxVal = Math.max(...visibleValues);

  const scale = computeNiceScale(minVal, maxVal, plotHeight, paddingTop, {
    currency,
    currencySymbol: sym,
    forceZero: true,
  });

  const getY = scale.getY;
  const zeroY = scale.zeroY;

  // Build points directly from actual series
  const points: any[] = [];
  for (let i = 0; i < count; i++) {
    const b = series[i];
    const x = paddingLeft + (count === 1 ? plotWidth / 2 : (i / (count - 1)) * plotWidth);
    const inc = b.cumulative_income_pence ?? 0;
    const exp = b.cumulative_expenses_pence ?? 0;
    const net = b.cumulative_net_savings_pence ?? (inc - exp);
    const isPlanned = !!(b.is_planned || (b.planned_income_pence && b.planned_income_pence > 0) || (b.planned_expenses_pence && b.planned_expenses_pence > 0));

    points.push({
      x,
      yIncome: getY(inc),
      ySpending: getY(exp),
      yNetSavings: getY(net),
      label: b.label,
      start_date: b.start_date,
      end_date: b.end_date,
      is_planned: isPlanned,
      income_pence: inc,
      expenses_pence: exp,
      net_savings_pence: net,
      formatted_income: b.formatted_cumulative_income || formatTooltipCurrency(inc, currency, sym),
      formatted_expenses: b.formatted_cumulative_expenses || formatTooltipCurrency(exp, currency, sym),
      formatted_net_savings: b.formatted_cumulative_net_savings || formatTooltipCurrency(net, currency, sym),
      accessibilityLabel: `${b.label}: Cum. Income ${b.formatted_cumulative_income || formatTooltipCurrency(inc, currency, sym)}, Cum. Spending ${b.formatted_cumulative_expenses || formatTooltipCurrency(exp, currency, sym)}, Net ${b.formatted_cumulative_net_savings || formatTooltipCurrency(net, currency, sym)}${isPlanned ? ' (Planned Forecast)' : ''}`,
    });
  }

  const incomeSeg = buildSegmentedPaths(points.map(p => ({ x: p.x, y: p.yIncome, isDashed: p.is_planned })));
  const spendingSeg = buildSegmentedPaths(points.map(p => ({ x: p.x, y: p.ySpending, isDashed: p.is_planned })));
  const netSavingsSeg = buildSegmentedPaths(points.map(p => ({ x: p.x, y: p.yNetSavings, isDashed: p.is_planned })));

  const incomeLinePath = buildSvgPath(points.map(p => ({ x: p.x, y: p.yIncome })));
  const spendingLinePath = buildSvgPath(points.map(p => ({ x: p.x, y: p.ySpending })));
  const netSavingsLinePath = buildSvgPath(points.map(p => ({ x: p.x, y: p.yNetSavings })));

  return {
    width,
    height,
    zeroY,
    paddingTop,
    paddingLeft,
    paddingRight,
    bottomY: paddingTop + plotHeight,
    incomeLinePath,
    spendingLinePath,
    netSavingsLinePath,
    incomeSolidPaths: incomeSeg.solidPaths,
    incomeDashedPaths: incomeSeg.dashedPaths,
    spendingSolidPaths: spendingSeg.solidPaths,
    spendingDashedPaths: spendingSeg.dashedPaths,
    netSavingsSolidPaths: netSavingsSeg.solidPaths,
    netSavingsDashedPaths: netSavingsSeg.dashedPaths,
    points,
    scale,
    formattedMax: formatAxisCurrency(scale.maxPence, currency, sym),
    formattedMin: formatAxisCurrency(scale.minPence, currency, sym),
    hasNegativeMin: scale.minPence < 0,
    isEmpty: false,
    isSinglePoint: count === 1,
  };
});

const netWorthChartData = computed(() => {
  const series = analysisStore.data?.net_worth_series || [];
  const count = series.length;
  const width = getNetWorthSvgWidth();
  const height = 240;
  const paddingTop = 24;
  const paddingBottom = 44;
  const paddingLeft = 70;
  const paddingRight = 24;
  const plotWidth = width - paddingLeft - paddingRight;
  const plotHeight = height - paddingTop - paddingBottom;
  const sym = analysisStore.data?.currency_symbol || '£';
  const currency = analysisStore.data?.currency || 'GBP';

  if (count === 0) {
    const scale = computeNiceScale(0, 0, plotHeight, paddingTop, { currency, currencySymbol: sym, forceZero: true });
    return {
      width,
      height,
      zeroY: scale.zeroY,
      paddingLeft,
      paddingRight,
      paddingTop,
      scale,
      linePath: '',
      areaPath: '',
      assetsLinePath: '',
      debtLinePath: '',
      solidNetWorthPaths: [],
      inferredNetWorthPaths: [],
      accountLines: [],
      points: [],
      isEmpty: true,
      isSinglePoint: false,
    };
  }

  const nwValues = series.map(b => b.net_worth_pence || 0);
  const assetValues = series.map(b => b.total_assets_pence || 0);
  const debtValues = series.map(b => b.total_debt_pence || 0);
  const allAccountValues: number[] = [];
  if (analysisStore.selectedBalanceAccountIds.length > 0) {
    for (const b of series) {
      for (const aid of analysisStore.selectedBalanceAccountIds) {
        const ab = b.account_balances?.find(a => a.account_id === aid);
        if (ab) allAccountValues.push(ab.balance_pence || 0);
      }
    }
  }

  const minVal = Math.min(0, ...nwValues, ...debtValues.map(d => -d), ...allAccountValues);
  const maxVal = Math.max(0, ...nwValues, ...assetValues, ...allAccountValues);

  const scale = computeNiceScale(minVal, maxVal, plotHeight, paddingTop, {
    currency,
    currencySymbol: sym,
    forceZero: true,
  });

  const getY = scale.getY;
  const zeroY = scale.zeroY;

  const points = series.map((b, i) => {
    const x = paddingLeft + (count === 1 ? plotWidth / 2 : (i / (count - 1)) * plotWidth);
    const nw = b.net_worth_pence || 0;
    const assets = b.total_assets_pence || 0;
    const debt = b.total_debt_pence || 0;
    const y = getY(nw);
    const yAssets = getY(assets);
    const yDebt = getY(-debt);

    const accounts = analysisStore.selectedBalanceAccountIds.map(aid => {
      const ab = b.account_balances?.find(a => a.account_id === aid);
      const bal = ab?.balance_pence || 0;
      const accY = getY(bal);
      return {
        id: aid,
        name: ab?.account_name || 'Account',
        color: getAccountColor(aid),
        y: accY,
        balance_pence: bal,
        formatted_balance: ab?.formatted_balance || formatTooltipCurrency(bal, currency, sym),
      };
    });

    return {
      x,
      y,
      yAssets,
      yDebt,
      label: b.label,
      date: b.date,
      has_inferred: !!b.has_inferred_balances,
      net_worth_pence: nw,
      formatted_nw: b.formatted_net_worth || formatTooltipCurrency(nw, currency, sym),
      formatted_assets: b.formatted_total_assets || formatTooltipCurrency(assets, currency, sym),
      formatted_debt: b.formatted_total_debt || formatTooltipCurrency(debt, currency, sym),
      accounts,
      accessibilityLabel: `${b.label} (${b.date}): Net Worth ${b.formatted_net_worth || formatTooltipCurrency(nw, currency, sym)}, Assets ${b.formatted_total_assets || formatTooltipCurrency(assets, currency, sym)}, Liabilities ${b.formatted_total_debt || formatTooltipCurrency(debt, currency, sym)}${b.has_inferred_balances ? ' (Inferred Pre-Anchor)' : ' (Confirmed Anchor)'}`,
    };
  });

  const nwSeg = buildSegmentedPaths(points.map(p => ({ x: p.x, y: p.y, isDashed: p.has_inferred })));
  const linePath = buildSvgPath(points.map(p => ({ x: p.x, y: p.y })));
  const areaPath = `${linePath} L ${points[points.length - 1].x} ${zeroY} L ${points[0].x} ${zeroY} Z`;
  const assetsLinePath = buildSvgPath(points.map(p => ({ x: p.x, y: p.yAssets })));
  const debtLinePath = buildSvgPath(points.map(p => ({ x: p.x, y: p.yDebt })));

  const accountLines: Array<{ id: number; name: string; color: string; path: string }> = [];
  for (const aid of analysisStore.selectedBalanceAccountIds) {
    const name = series[0]?.account_balances?.find(a => a.account_id === aid)?.account_name || 'Account';
    const color = getAccountColor(aid);
    const accPts = points.map(p => {
      const a = p.accounts.find(ac => ac.id === aid);
      return { x: p.x, y: a?.y ?? zeroY };
    });
    accountLines.push({ id: aid, name, color, path: buildSvgPath(accPts) });
  }

  return {
    width,
    height,
    zeroY,
    paddingLeft,
    paddingRight,
    paddingTop,
    scale,
    linePath,
    areaPath,
    assetsLinePath,
    debtLinePath,
    solidNetWorthPaths: nwSeg.solidPaths,
    inferredNetWorthPaths: nwSeg.dashedPaths,
    accountLines,
    points,
    isEmpty: false,
    isSinglePoint: count === 1,
  };
});

const investmentsChartData = computed(() => {
  const series = analysisStore.data?.investments_series || [];
  const count = series.length;
  const width = getInvestmentsSvgWidth();
  const height = 240;
  const paddingTop = 24;
  const paddingBottom = 44;
  const paddingLeft = 70;
  const paddingRight = 24;
  const plotWidth = width - paddingLeft - paddingRight;
  const plotHeight = height - paddingTop - paddingBottom;
  const sym = analysisStore.data?.currency_symbol || '£';
  const currency = analysisStore.data?.currency || 'GBP';

  const validValues = series.filter(b => b.is_available && b.total_valuation_pence !== null).map(b => b.total_valuation_pence as number);
  const maxPence = validValues.length > 0 ? Math.max(...validValues) : 0;

  const scale = computeNiceScale(0, maxPence, plotHeight, paddingTop, {
    currency,
    currencySymbol: sym,
    forceZero: true,
  });

  const getY = scale.getY;
  const zeroY = scale.zeroY;

  if (count === 0 || validValues.length === 0) {
    return {
      width,
      height,
      zeroY,
      paddingLeft,
      paddingRight,
      paddingTop,
      scale,
      linePath: '',
      areaPath: '',
      freshPaths: [],
      carriedForwardPaths: [],
      points: [],
      isEmpty: true,
      isSinglePoint: false,
    };
  }

  const points = series.map((b, i) => {
    const x = paddingLeft + (count === 1 ? plotWidth / 2 : (i / (count - 1)) * plotWidth);
    const isAvail = !!(b.is_available && b.total_valuation_pence !== null);
    const valPence = isAvail ? (b.total_valuation_pence as number) : 0;
    const y = isAvail ? getY(valPence) : zeroY;
    const isCf = !!b.is_carried_forward;

    return {
      x,
      y,
      label: b.label,
      date: b.date,
      is_available: isAvail,
      is_carried_forward: isCf,
      val_date: b.valuation_date,
      cf_date: b.carried_forward_date,
      valuation_pence: valPence,
      formatted: b.formatted_total_valuation || (isAvail ? formatTooltipCurrency(valPence, currency, sym) : 'Unavailable'),
      valued_count: b.valued_count,
      holdings_count: b.holdings_count,
      accessibilityLabel: `${b.label} (${b.date}): ${isAvail ? `Total Valuation ${b.formatted_total_valuation || formatTooltipCurrency(valPence, currency, sym)}` : 'Unavailable'}${isCf ? ` (Carried forward from ${b.carried_forward_date})` : ''}`,
    };
  });

  const seg = buildSegmentedPaths(points.map(p => ({
    x: p.x,
    y: p.y,
    isAvailable: p.is_available,
    isDashed: p.is_carried_forward,
  })));

  let legacyLinePath = '';
  let inSub = false;
  for (const pt of points) {
    if (!pt.is_available) {
      inSub = false;
      continue;
    }
    if (!inSub) {
      legacyLinePath += `M ${pt.x.toFixed(1)} ${pt.y.toFixed(1)} `;
      inSub = true;
    } else {
      legacyLinePath += `L ${pt.x.toFixed(1)} ${pt.y.toFixed(1)} `;
    }
  }

  return {
    width,
    height,
    zeroY,
    paddingLeft,
    paddingRight,
    paddingTop,
    scale,
    linePath: legacyLinePath.trim(),
    areaPath: '',
    freshPaths: seg.solidPaths,
    carriedForwardPaths: seg.dashedPaths,
    points,
    isEmpty: false,
    isSinglePoint: validValues.length === 1,
  };
});

function formatRangeLabel(startStr: string, endStr: string): string {
  try {
    const s = new Date(startStr);
    const e = new Date(endStr);
    const opt: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short', year: 'numeric' };
    return `${s.toLocaleDateString('en-GB', opt)} – ${e.toLocaleDateString('en-GB', opt)}`;
  } catch {
    return `${startStr} – ${endStr}`;
  }
}

onMounted(() => {
  document.addEventListener('click', handleDocumentClick);
  if (accountsStore.accounts.length === 0) {
    accountsStore.loadData();
  }
  analysisStore.initFromRouteOrPreferences(route.query);
  analysisStore.loadAnalysis();
});

onBeforeUnmount(() => {
  document.removeEventListener('click', handleDocumentClick);
});

watch(() => route.query, (newQuery) => {
  if (newQuery) {
    analysisStore.initFromRouteOrPreferences(newQuery);
  }
}, { deep: true });
</script>
