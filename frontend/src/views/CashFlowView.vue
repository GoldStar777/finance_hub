<template>
  <div class="space-y-6 animate-fadeIn pb-16">
    
    <!-- Top Action & Navigation Bar -->
    <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
      <div>
        <h1 class="text-xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center space-x-2.5">
          <span>Cash Flow Analytics</span>
          <span 
            v-if="cashflowStore.summary" 
            class="px-2 py-0.5 rounded-full text-xs font-mono font-semibold bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300">
            {{ cashflowStore.summary.currency }} ({{ cashflowStore.summary.currency_symbol }})
          </span>
        </h1>
        <p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
          Monthly income, fixed vs variable expense distribution, savings velocity, and 6-month trajectory.
        </p>
      </div>

      <!-- Controls: Month Navigation, Currency & Account Filters -->
      <div class="flex flex-wrap items-center gap-2 shrink-0">
        
        <!-- Month Stepper (< Dropdown >) -->
        <div class="flex items-center rounded-full border border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface p-0.5 shadow-sm">
          <button
            @click="cashflowStore.goToPrevMonth()"
            class="w-7 h-7 rounded-full flex items-center justify-center text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition text-xs font-bold"
            title="Previous Month">
            ‹
          </button>

          <select
            v-if="cashflowStore.summary"
            :value="cashflowStore.summary.selected_month"
            @change="onMonthSelect(($event.target as HTMLSelectElement).value)"
            class="bg-transparent text-xs font-semibold font-mono text-slate-800 dark:text-slate-200 px-2 py-1 focus:outline-none cursor-pointer">
            <option 
              v-for="m in cashflowStore.summary.available_months" 
              :key="m" 
              :value="m"
              class="bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-200">
              {{ formatMonthOption(m) }}
            </option>
          </select>

          <button
            @click="cashflowStore.goToNextMonth()"
            class="w-7 h-7 rounded-full flex items-center justify-center text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition text-xs font-bold"
            title="Next Month">
            ›
          </button>
        </div>

        <!-- Currency Selector (if multiple) -->
        <div 
          v-if="cashflowStore.summary && cashflowStore.summary.available_currencies.length > 1"
          class="rounded-full border border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface px-3 py-1 shadow-sm">
          <select
            :value="cashflowStore.summary.currency"
            @change="onCurrencySelect(($event.target as HTMLSelectElement).value)"
            class="bg-transparent text-xs font-semibold font-mono text-slate-800 dark:text-slate-200 focus:outline-none cursor-pointer">
            <option 
              v-for="curr in cashflowStore.summary.available_currencies" 
              :key="curr" 
              :value="curr"
              class="bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-200">
              {{ curr }}
            </option>
          </select>
        </div>

        <!-- Account Filter -->
        <div 
          v-if="accountsStore.accounts.length > 0"
          class="rounded-full border border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface px-3 py-1 shadow-sm">
          <select
            :value="cashflowStore.selectedAccountId || ''"
            @change="onAccountSelect(($event.target as HTMLSelectElement).value)"
            class="bg-transparent text-xs font-semibold text-slate-800 dark:text-slate-200 focus:outline-none cursor-pointer">
            <option value="" class="bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-200">
              All Accounts
            </option>
            <option 
              v-for="acc in accountsStore.accounts" 
              :key="acc.id" 
              :value="acc.id"
              class="bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-200">
              {{ acc.name }} ({{ acc.currency }})
            </option>
          </select>
        </div>

      </div>
    </div>

    <!-- Loading Skeleton -->
    <div v-if="cashflowStore.loading && !cashflowStore.summary" class="h-64 rounded-2xl bg-slate-100 dark:bg-slate-800/40 animate-pulse"></div>

    <!-- Error State -->
    <div v-else-if="cashflowStore.error" class="p-4 rounded-xl border border-rose-200 dark:border-rose-900 bg-rose-50 dark:bg-rose-950/40 text-rose-600 dark:text-rose-400 text-xs">
      {{ cashflowStore.error }}
    </div>

    <!-- Main Analytics Content -->
    <template v-else-if="cashflowStore.summary">

      <!-- Informative Audit Banners -->
      <div v-if="cashflowStore.summary.transfers_count > 0 || cashflowStore.summary.adjustments_count > 0" class="space-y-2">
        <!-- Transfers Notice -->
        <div v-if="cashflowStore.summary.transfers_count > 0" class="p-3 rounded-xl border border-blue-200 dark:border-blue-900/60 bg-blue-50/70 dark:bg-blue-950/30 flex items-center justify-between text-xs text-blue-900 dark:text-blue-300">
          <div class="flex items-center space-x-2">
            <span>ℹ️</span>
            <span>
              <strong>Internal Transfers:</strong> {{ cashflowStore.summary.formatted_transfers_volume }} across {{ cashflowStore.summary.transfers_count }} transfer{{ cashflowStore.summary.transfers_count > 1 ? 's' : '' }}.
              Transfers between your own accounts contribute <strong>{{ cashflowStore.summary.currency_symbol }}0</strong> to cash flow totals.
            </span>
          </div>
          <span class="font-mono text-[11px] font-semibold text-blue-700 dark:text-blue-400">Strictly Excluded</span>
        </div>

        <!-- Adjustments Notice -->
        <div v-if="cashflowStore.summary.adjustments_count > 0" class="p-3 rounded-xl border border-amber-200 dark:border-amber-900/60 bg-amber-50/70 dark:bg-amber-950/30 flex items-center justify-between text-xs text-amber-900 dark:text-amber-300">
          <div class="flex items-center space-x-2">
            <span>⚖️</span>
            <span>
              <strong>Reconciliation Adjustments:</strong> Net <span class="sensitive font-mono font-semibold">{{ cashflowStore.summary.formatted_adjustments_net }}</span>
              (credits: +{{ formatAmount(cashflowStore.summary.adjustments_inflow_pence) }}, debits: -{{ formatAmount(cashflowStore.summary.adjustments_outflow_pence) }}) across {{ cashflowStore.summary.adjustments_count }} adjustment{{ cashflowStore.summary.adjustments_count > 1 ? 's' : '' }}.
            </span>
          </div>
          <span class="font-mono text-[11px] font-semibold text-amber-700 dark:text-amber-400">Reconciled in Net Surplus</span>
        </div>
      </div>

      <!-- KPI Executive Summary Cards -->
      <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3.5">
        
        <!-- Total Inflow Card -->
        <div class="rounded-2xl border border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface p-4 shadow-sm space-y-2">
          <div class="flex items-center justify-between">
            <span class="font-mono text-[10px] uppercase tracking-wider text-slate-500 dark:text-slate-400 font-semibold">
              Income / Inflow
            </span>
            <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
          </div>
          <div class="text-xl font-extrabold tracking-tight sensitive text-emerald-600 dark:text-emerald-400 font-mono">
            {{ cashflowStore.summary.formatted_income }}
          </div>
          <div class="text-[11px] text-slate-500 dark:text-slate-400">
            {{ cashflowStore.summary.income_count }} inflow transaction{{ cashflowStore.summary.income_count === 1 ? '' : 's' }}
          </div>
        </div>

        <!-- Fixed Expenses Card -->
        <div class="rounded-2xl border border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface p-4 shadow-sm space-y-2">
          <div class="flex items-center justify-between">
            <span class="font-mono text-[10px] uppercase tracking-wider text-slate-500 dark:text-slate-400 font-semibold">
              Fixed Outflow
            </span>
            <span class="w-2 h-2 rounded-full bg-indigo-500"></span>
          </div>
          <div class="text-xl font-extrabold tracking-tight sensitive text-slate-900 dark:text-white font-mono">
            {{ cashflowStore.summary.formatted_fixed_expenses }}
          </div>
          <div class="text-[11px] text-slate-500 dark:text-slate-400">
            {{ cashflowStore.summary.fixed_percentage }}% of spend ({{ cashflowStore.summary.fixed_expenses_count }} txs)
          </div>
        </div>

        <!-- Variable Expenses Card -->
        <div class="rounded-2xl border border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface p-4 shadow-sm space-y-2">
          <div class="flex items-center justify-between">
            <span class="font-mono text-[10px] uppercase tracking-wider text-slate-500 dark:text-slate-400 font-semibold">
              Variable Outflow
            </span>
            <span class="w-2 h-2 rounded-full bg-amber-500"></span>
          </div>
          <div class="text-xl font-extrabold tracking-tight sensitive text-slate-900 dark:text-white font-mono">
            {{ cashflowStore.summary.formatted_variable_expenses }}
          </div>
          <div class="text-[11px] text-slate-500 dark:text-slate-400">
            {{ cashflowStore.summary.variable_percentage }}% of spend ({{ cashflowStore.summary.variable_expenses_count }} txs)
          </div>
        </div>

        <!-- Total Outflow Card -->
        <div class="rounded-2xl border border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface p-4 shadow-sm space-y-2">
          <div class="flex items-center justify-between">
            <span class="font-mono text-[10px] uppercase tracking-wider text-slate-500 dark:text-slate-400 font-semibold">
              Total Expenses
            </span>
            <span class="w-2 h-2 rounded-full bg-rose-500"></span>
          </div>
          <div class="text-xl font-extrabold tracking-tight sensitive text-rose-600 dark:text-rose-400 font-mono">
            {{ cashflowStore.summary.formatted_total_expenses }}
          </div>
          <div class="text-[11px] text-slate-500 dark:text-slate-400">
            {{ cashflowStore.summary.expenses_count }} expense transaction{{ cashflowStore.summary.expenses_count === 1 ? '' : 's' }}
          </div>
        </div>

        <!-- Net Surplus / Deficit Card -->
        <div 
          class="rounded-2xl border p-4 shadow-sm space-y-2"
          :class="cashflowStore.summary.net_surplus_pence >= 0 
            ? 'border-emerald-200 dark:border-emerald-900/60 bg-emerald-50/40 dark:bg-emerald-950/20' 
            : 'border-rose-200 dark:border-rose-900/60 bg-rose-50/40 dark:bg-rose-950/20'">
          <div class="flex items-center justify-between">
            <span class="font-mono text-[10px] uppercase tracking-wider text-slate-500 dark:text-slate-400 font-semibold">
              Net Surplus / Deficit
            </span>
            <span 
              class="text-[10px] font-bold font-mono px-1.5 py-0.5 rounded"
              :class="cashflowStore.summary.net_surplus_pence >= 0 ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-300' : 'bg-rose-100 text-rose-800 dark:bg-rose-900 dark:text-rose-300'">
              {{ cashflowStore.summary.net_surplus_pence >= 0 ? 'Surplus' : 'Deficit' }}
            </span>
          </div>
          <div 
            class="text-xl font-extrabold tracking-tight sensitive font-mono"
            :class="cashflowStore.summary.net_surplus_pence >= 0 ? 'text-emerald-700 dark:text-emerald-300' : 'text-rose-700 dark:text-rose-300'">
            {{ cashflowStore.summary.formatted_net_surplus }}
          </div>
          <div class="text-[11px] text-slate-500 dark:text-slate-400">
            Operating: <span class="sensitive font-mono">{{ cashflowStore.summary.formatted_operating_surplus }}</span>
          </div>
        </div>

        <!-- Savings Rate Card -->
        <div class="rounded-2xl border border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface p-4 shadow-sm space-y-2">
          <div class="flex items-center justify-between">
            <span class="font-mono text-[10px] uppercase tracking-wider text-slate-500 dark:text-slate-400 font-semibold">
              Savings Rate
            </span>
            <span class="text-xs">🎯</span>
          </div>
          <div 
            class="text-xl font-extrabold tracking-tight sensitive font-mono"
            :class="cashflowStore.summary.is_savings_rate_applicable && cashflowStore.summary.savings_rate >= 20 ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-900 dark:text-white'">
            {{ cashflowStore.summary.formatted_savings_rate }}
          </div>
          <div class="text-[11px] text-slate-500 dark:text-slate-400">
            {{ cashflowStore.summary.is_savings_rate_applicable ? 'Surplus ÷ Inflow' : 'Zero income recorded' }}
          </div>
        </div>

      </div>

      <!-- Cash Flow Allocation / Waterfall Visualization -->
      <div class="rounded-2xl border border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface p-6 shadow-sm space-y-4">
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <h2 class="font-mono text-xs uppercase tracking-wider font-bold text-slate-500 dark:text-slate-400">
              Cash Flow Allocation Waterfall
            </h2>
            <p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              Proportional distribution of incoming funds across fixed commitments, discretionary spend, and retained surplus.
            </p>
          </div>
          <div class="flex items-center space-x-3 text-xs">
            <span class="flex items-center space-x-1">
              <span class="w-2.5 h-2.5 rounded-sm bg-indigo-500"></span>
              <span class="text-slate-600 dark:text-slate-300">Fixed</span>
            </span>
            <span class="flex items-center space-x-1">
              <span class="w-2.5 h-2.5 rounded-sm bg-amber-500"></span>
              <span class="text-slate-600 dark:text-slate-300">Variable</span>
            </span>
            <span v-if="cashflowStore.summary.unclassified_expenses_pence > 0" class="flex items-center space-x-1">
              <span class="w-2.5 h-2.5 rounded-sm bg-slate-400"></span>
              <span class="text-slate-600 dark:text-slate-300">Unclassified</span>
            </span>
            <span class="flex items-center space-x-1">
              <span class="w-2.5 h-2.5 rounded-sm bg-emerald-500"></span>
              <span class="text-slate-600 dark:text-slate-300">Retained Surplus</span>
            </span>
          </div>
        </div>

        <!-- Proportional Allocation Bar -->
        <div v-if="allocationSegments.length > 0" class="w-full h-7 rounded-xl overflow-hidden flex bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700/60">
          <div
            v-for="seg in allocationSegments"
            :key="seg.label"
            :style="{ width: `${seg.percentage}%`, backgroundColor: seg.color }"
            :title="`${seg.label}: ${seg.formatted} (${seg.percentage}%)`"
            class="h-full transition-all duration-300 relative group flex items-center justify-center text-[10px] font-mono font-bold text-white overflow-hidden px-1">
            <span v-if="seg.percentage >= 8" class="truncate">{{ seg.label }} {{ seg.percentage }}%</span>
          </div>
        </div>

        <div v-else class="text-xs text-slate-400 italic py-2">
          No income or expense activity recorded for {{ cashflowStore.summary.month_name }}.
        </div>

        <!-- Legend / Breakdown Pills -->
        <div v-if="allocationSegments.length > 0" class="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-1 text-xs">
          <div 
            v-for="seg in allocationSegments" 
            :key="seg.label"
            class="p-2.5 rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50/50 dark:bg-slate-800/40 space-y-1">
            <div class="flex items-center justify-between text-slate-500 dark:text-slate-400 text-[11px]">
              <span class="flex items-center space-x-1.5">
                <span class="w-2 h-2 rounded-full" :style="{ backgroundColor: seg.color }"></span>
                <span class="font-medium">{{ seg.label }}</span>
              </span>
              <span class="font-mono font-bold">{{ seg.percentage }}%</span>
            </div>
            <div class="font-mono font-bold text-slate-900 dark:text-white sensitive text-sm">
              {{ seg.formatted }}
            </div>
          </div>
        </div>
      </div>

      <!-- Main Two-Column Analytics Layout -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">

        <!-- Left 2 Cols: Category Spending Breakdown -->
        <div class="lg:col-span-2 rounded-2xl border border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface p-6 shadow-sm space-y-4">
          <div class="flex items-center justify-between">
            <div>
              <h2 class="font-mono text-xs uppercase tracking-wider font-bold text-slate-500 dark:text-slate-400">
                Spending by Category ({{ cashflowStore.summary.categories.length }})
              </h2>
              <p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                Breakdown of outflow categorized by merchant intent, ranked by total volume.
              </p>
            </div>
            <span class="font-mono text-xs font-semibold text-slate-500 sensitive">
              Total: {{ cashflowStore.summary.formatted_total_expenses }}
            </span>
          </div>

          <!-- Category List -->
          <div v-if="cashflowStore.summary.categories.length > 0" class="space-y-3 pt-2">
            <div
              v-for="cat in cashflowStore.summary.categories"
              :key="cat.category_name"
              class="p-3 rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50/40 dark:bg-slate-800/30 hover:bg-slate-50 dark:hover:bg-slate-800/60 transition space-y-2">
              
              <div class="flex items-center justify-between text-xs">
                <div class="flex items-center space-x-2">
                  <span 
                    class="w-3 h-3 rounded-full shrink-0" 
                    :style="{ backgroundColor: cat.category_color }"></span>
                  <span class="font-bold text-slate-900 dark:text-white">{{ cat.category_name }}</span>
                  <span 
                    v-if="cat.expense_nature"
                    class="px-1.5 py-0.2 text-[10px] rounded uppercase font-mono font-semibold"
                    :class="cat.expense_nature === 'fixed' ? 'bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-300' : 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300'">
                    {{ cat.expense_nature }}
                  </span>
                </div>
                
                <div class="flex items-center space-x-3 font-mono">
                  <span class="text-slate-400 text-[11px]">{{ cat.transaction_count }} tx{{ cat.transaction_count === 1 ? '' : 's' }}</span>
                  <span class="font-bold text-slate-900 dark:text-white sensitive">{{ cat.formatted_total }}</span>
                  <span class="text-slate-500 dark:text-slate-400 w-12 text-right font-semibold">{{ cat.percentage }}%</span>
                </div>
              </div>

              <!-- Progress bar -->
              <div class="w-full h-1.5 rounded-full bg-slate-200 dark:bg-slate-700/50 overflow-hidden">
                <div
                  class="h-full rounded-full transition-all duration-300"
                  :style="{ width: `${cat.percentage}%`, backgroundColor: cat.category_color }"></div>
              </div>

            </div>
          </div>

          <!-- Empty Categories State -->
          <div v-else class="text-center py-8 text-xs text-slate-400 italic">
            No categorized expenses recorded in {{ cashflowStore.summary.month_name }}.
          </div>
        </div>

        <!-- Right 1 Col: Expense Nature Breakdown & Rules -->
        <div class="space-y-6">
          
          <!-- Expense Nature Distribution Card -->
          <div class="rounded-2xl border border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface p-6 shadow-sm space-y-4">
            <h2 class="font-mono text-xs uppercase tracking-wider font-bold text-slate-500 dark:text-slate-400">
              Expense Nature Distribution
            </h2>

            <div class="space-y-3">
              <!-- Fixed row -->
              <div class="p-3 rounded-xl border border-indigo-100 dark:border-indigo-900/50 bg-indigo-50/50 dark:bg-indigo-950/20 space-y-1">
                <div class="flex items-center justify-between text-xs">
                  <span class="font-semibold text-indigo-900 dark:text-indigo-300 flex items-center space-x-1.5">
                    <span class="w-2 h-2 rounded-full bg-indigo-500"></span>
                    <span>Fixed / Committed</span>
                  </span>
                  <span class="font-mono font-bold text-indigo-900 dark:text-indigo-300">{{ cashflowStore.summary.fixed_percentage }}%</span>
                </div>
                <div class="flex items-center justify-between text-xs font-mono">
                  <span class="text-slate-500 text-[11px]">{{ cashflowStore.summary.fixed_expenses_count }} transactions</span>
                  <span class="font-bold text-slate-900 dark:text-white sensitive">{{ cashflowStore.summary.formatted_fixed_expenses }}</span>
                </div>
              </div>

              <!-- Variable row -->
              <div class="p-3 rounded-xl border border-amber-100 dark:border-amber-900/50 bg-amber-50/50 dark:bg-amber-950/20 space-y-1">
                <div class="flex items-center justify-between text-xs">
                  <span class="font-semibold text-amber-900 dark:text-amber-300 flex items-center space-x-1.5">
                    <span class="w-2 h-2 rounded-full bg-amber-500"></span>
                    <span>Variable / Discretionary</span>
                  </span>
                  <span class="font-mono font-bold text-amber-900 dark:text-amber-300">{{ cashflowStore.summary.variable_percentage }}%</span>
                </div>
                <div class="flex items-center justify-between text-xs font-mono">
                  <span class="text-slate-500 text-[11px]">{{ cashflowStore.summary.variable_expenses_count }} transactions</span>
                  <span class="font-bold text-slate-900 dark:text-white sensitive">{{ cashflowStore.summary.formatted_variable_expenses }}</span>
                </div>
              </div>

              <!-- Unclassified row -->
              <div 
                v-if="cashflowStore.summary.unclassified_expenses_pence > 0"
                class="p-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-800/30 space-y-1">
                <div class="flex items-center justify-between text-xs">
                  <span class="font-semibold text-slate-700 dark:text-slate-300 flex items-center space-x-1.5">
                    <span class="w-2 h-2 rounded-full bg-slate-400"></span>
                    <span>Unclassified</span>
                  </span>
                  <span class="font-mono font-bold text-slate-700 dark:text-slate-300">{{ cashflowStore.summary.unclassified_percentage }}%</span>
                </div>
                <div class="flex items-center justify-between text-xs font-mono">
                  <span class="text-slate-500 text-[11px]">{{ cashflowStore.summary.unclassified_expenses_count }} transactions</span>
                  <span class="font-bold text-slate-900 dark:text-white sensitive">{{ cashflowStore.summary.formatted_unclassified_expenses }}</span>
                </div>
              </div>
            </div>

            <!-- Explanatory note -->
            <p class="text-[11px] text-slate-400 dark:text-slate-500 pt-1 border-t border-brand-border dark:border-brand-darkborder">
              Expense nature honors per-transaction overrides over category defaults.
            </p>
          </div>

          <!-- Accounting Rules Card -->
          <div class="rounded-2xl border border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface p-5 shadow-sm space-y-2.5 text-xs text-slate-600 dark:text-slate-400">
            <h3 class="font-mono text-xs uppercase tracking-wider font-bold text-slate-700 dark:text-slate-300">
              Cash Flow Accounting Rules
            </h3>
            <ul class="space-y-1.5 text-[11px]">
              <li class="flex items-start space-x-1.5">
                <span class="text-emerald-500 font-bold shrink-0">✓</span>
                <span><strong>Zero Transfers:</strong> Internal movements contribute £0 to cash flow totals.</span>
              </li>
              <li class="flex items-start space-x-1.5">
                <span class="text-emerald-500 font-bold shrink-0">✓</span>
                <span><strong>Multi-Currency Isolation:</strong> Currencies are evaluated independently without unverified fx conversion.</span>
              </li>
              <li class="flex items-start space-x-1.5">
                <span class="text-emerald-500 font-bold shrink-0">✓</span>
                <span><strong>Guarded Savings:</strong> Months with zero income safely evaluate to N/A.</span>
              </li>
              <li class="flex items-start space-x-1.5">
                <span class="text-emerald-500 font-bold shrink-0">✓</span>
                <span><strong>Reconciled Adjustments:</strong> Positive credit adjustments add to net surplus; negative debits deduct.</span>
              </li>
            </ul>
          </div>

        </div>

      </div>

      <!-- Trailing 6-Month Trajectory Section -->
      <div class="rounded-2xl border border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface p-6 shadow-sm space-y-6">
        <div>
          <h2 class="font-mono text-xs uppercase tracking-wider font-bold text-slate-500 dark:text-slate-400">
            Historical Cash Flow Trajectory (Trailing 6 Months)
          </h2>
          <p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Month-over-month trend of external income, operational outflow, and net savings surplus.
          </p>
        </div>

        <!-- Native SVG / CSS Bar Chart Visualization -->
        <div class="pt-2 pb-4">
          <div class="h-44 flex items-end justify-between gap-2 sm:gap-6 border-b border-slate-200 dark:border-slate-800 px-2 sm:px-6">
            <div
              v-for="trend in cashflowStore.summary.historical_trend"
              :key="trend.month"
              class="flex-1 flex flex-col items-center justify-end h-full group relative cursor-pointer"
              @click="cashflowStore.setMonth(trend.month)">
              
              <!-- Hover Tooltip -->
              <div class="opacity-0 group-hover:opacity-100 transition-opacity absolute -top-12 z-20 pointer-events-none bg-slate-900 text-white dark:bg-white dark:text-slate-900 text-[10px] font-mono px-2 py-1 rounded shadow-lg whitespace-nowrap">
                {{ trend.month_name }}: In: {{ trend.formatted_income }} | Out: {{ trend.formatted_total_expenses }}
              </div>

              <!-- Pair of Bars: Income (emerald) & Outflow (rose) -->
              <div class="w-full max-w-16 flex items-end justify-center gap-1 sm:gap-2 h-full">
                <!-- Income bar -->
                <div 
                  class="w-1/2 max-w-5 rounded-t bg-emerald-500 hover:bg-emerald-400 transition-all duration-300"
                  :style="{ height: `${calculateBarHeight(trend.income_pence)}%` }"
                  :title="`Income: ${trend.formatted_income}`">
                </div>

                <!-- Expenses bar -->
                <div 
                  class="w-1/2 max-w-5 rounded-t bg-rose-500 hover:bg-rose-400 transition-all duration-300"
                  :style="{ height: `${calculateBarHeight(trend.total_expenses_pence)}%` }"
                  :title="`Outflow: ${trend.formatted_total_expenses}`">
                </div>
              </div>

              <!-- Month Label -->
              <div 
                class="mt-2 text-[11px] font-mono font-medium transition"
                :class="trend.month === cashflowStore.summary.selected_month ? 'text-indigo-600 dark:text-indigo-400 font-bold underline' : 'text-slate-500 dark:text-slate-400'">
                {{ trend.month_name }}
              </div>

            </div>
          </div>
          
          <!-- Legend under chart -->
          <div class="flex items-center justify-center space-x-6 pt-3 text-xs text-slate-500">
            <span class="flex items-center space-x-1.5">
              <span class="w-3 h-3 rounded-sm bg-emerald-500"></span>
              <span>Income</span>
            </span>
            <span class="flex items-center space-x-1.5">
              <span class="w-3 h-3 rounded-sm bg-rose-500"></span>
              <span>Total Outflow</span>
            </span>
          </div>
        </div>

        <!-- Trajectory Table -->
        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs">
            <thead>
              <tr class="border-b border-brand-border dark:border-brand-darkborder text-[11px] font-mono uppercase text-slate-400 font-bold">
                <th class="py-2.5 px-3">Month</th>
                <th class="py-2.5 px-3 text-right">Income</th>
                <th class="py-2.5 px-3 text-right">Fixed</th>
                <th class="py-2.5 px-3 text-right">Variable</th>
                <th class="py-2.5 px-3 text-right">Total Outflow</th>
                <th class="py-2.5 px-3 text-right">Net Surplus</th>
                <th class="py-2.5 px-3 text-right">Savings Rate</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-brand-border dark:divide-brand-darkborder font-mono">
              <tr
                v-for="trend in cashflowStore.summary.historical_trend"
                :key="trend.month"
                @click="cashflowStore.setMonth(trend.month)"
                class="hover:bg-slate-50 dark:hover:bg-slate-800/40 cursor-pointer transition"
                :class="trend.month === cashflowStore.summary.selected_month ? 'bg-indigo-50/30 dark:bg-indigo-950/20' : ''">
                
                <td class="py-3 px-3 font-semibold text-slate-900 dark:text-white flex items-center space-x-2">
                  <span>{{ trend.month_name }}</span>
                  <span 
                    v-if="trend.month === cashflowStore.summary.selected_month" 
                    class="px-1.5 py-0.2 rounded text-[10px] bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-300">
                    Selected
                  </span>
                </td>
                <td class="py-3 px-3 text-right sensitive text-emerald-600 dark:text-emerald-400 font-bold">
                  {{ trend.formatted_income }}
                </td>
                <td class="py-3 px-3 text-right sensitive text-slate-600 dark:text-slate-300">
                  {{ formatAmount(trend.fixed_expenses_pence) }}
                </td>
                <td class="py-3 px-3 text-right sensitive text-slate-600 dark:text-slate-300">
                  {{ formatAmount(trend.variable_expenses_pence) }}
                </td>
                <td class="py-3 px-3 text-right sensitive text-rose-600 dark:text-rose-400 font-bold">
                  {{ trend.formatted_total_expenses }}
                </td>
                <td 
                  class="py-3 px-3 text-right sensitive font-bold"
                  :class="trend.net_surplus_pence >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'">
                  {{ trend.formatted_net_surplus }}
                </td>
                <td class="py-3 px-3 text-right sensitive font-semibold">
                  {{ trend.is_savings_rate_applicable ? `${trend.savings_rate.toFixed(1)}%` : 'N/A' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

      </div>

    </template>

  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue';
import { useCashflowStore } from '../stores/cashflow';
import { useAccountsStore } from '../stores/accounts';

const cashflowStore = useCashflowStore();
const accountsStore = useAccountsStore();

onMounted(async () => {
  if (accountsStore.accounts.length === 0) {
    accountsStore.loadData();
  }
  await cashflowStore.loadCashFlow();
});

function formatAmount(pence: number): string {
  const sym = cashflowStore.summary?.currency_symbol || '£';
  const pounds = Math.abs(pence) / 100;
  const formatted = pounds.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (pence < 0) {
    return `-${sym}${formatted}`;
  }
  return `${sym}${formatted}`;
}

function formatMonthOption(monthStr: string): string {
  const parts = monthStr.split('-');
  if (parts.length === 2) {
    const y = parseInt(parts[0], 10);
    const m = parseInt(parts[1], 10);
    const dt = new Date(Date.UTC(y, m - 1, 1));
    return dt.toLocaleDateString('en-GB', { month: 'short', year: 'numeric', timeZone: 'UTC' });
  }
  return monthStr;
}

function onMonthSelect(val: string) {
  if (val) {
    cashflowStore.setMonth(val);
  }
}

function onCurrencySelect(val: string) {
  if (val) {
    cashflowStore.setCurrency(val);
  }
}

function onAccountSelect(val: string) {
  const accountId = val ? parseInt(val, 10) : null;
  cashflowStore.setAccount(accountId);
}

// Proportional segments for waterfall visualization
const allocationSegments = computed(() => {
  const s = cashflowStore.summary;
  if (!s || (s.income_pence === 0 && s.total_expenses_pence === 0)) {
    return [];
  }

  // Base denominator: Income or Total Spend, whichever is higher
  const denominator = Math.max(s.income_pence, s.total_expenses_pence);
  if (denominator <= 0) return [];

  const segments = [];

  if (s.fixed_expenses_pence > 0) {
    const pct = Math.round((s.fixed_expenses_pence / denominator) * 100);
    segments.push({
      label: 'Fixed',
      percentage: pct,
      color: '#6366F1', // indigo-500
      formatted: s.formatted_fixed_expenses,
    });
  }

  if (s.variable_expenses_pence > 0) {
    const pct = Math.round((s.variable_expenses_pence / denominator) * 100);
    segments.push({
      label: 'Variable',
      percentage: pct,
      color: '#F59E0B', // amber-500
      formatted: s.formatted_variable_expenses,
    });
  }

  if (s.unclassified_expenses_pence > 0) {
    const pct = Math.round((s.unclassified_expenses_pence / denominator) * 100);
    segments.push({
      label: 'Unclassified',
      percentage: pct,
      color: '#94A3B8', // slate-400
      formatted: s.formatted_unclassified_expenses,
    });
  }

  if (s.net_surplus_pence > 0) {
    const pct = Math.round((s.net_surplus_pence / denominator) * 100);
    segments.push({
      label: 'Surplus',
      percentage: pct,
      color: '#10B981', // emerald-500
      formatted: s.formatted_net_surplus,
    });
  }

  return segments;
});

// Helper for dynamic bar chart height
function calculateBarHeight(pence: number): number {
  if (!cashflowStore.summary?.historical_trend || pence <= 0) return 2;
  const maxVal = Math.max(
    ...cashflowStore.summary.historical_trend.map(t => Math.max(t.income_pence, t.total_expenses_pence)),
    1
  );
  const pct = Math.round((pence / maxVal) * 100);
  return Math.max(pct, 4); // Minimum 4% height for visibility
}
</script>
