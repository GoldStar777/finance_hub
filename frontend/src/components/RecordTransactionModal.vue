<template>
  <div 
    v-if="isOpen" 
    class="fixed inset-0 z-50 bg-slate-950/40 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto"
    @click.self="$emit('close')">
    <section 
      role="dialog" 
      aria-modal="true" 
      aria-labelledby="record-tx-title"
      class="bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder rounded-2xl w-full p-6 shadow-2xl space-y-5 transition-all my-8"
      :class="(isRepeat || isRepeatPreviewStep) ? 'max-w-2xl' : 'max-w-lg'">
      
      <!-- Modal Header -->
      <div class="flex items-center justify-between pb-3 border-b border-brand-border dark:border-brand-darkborder">
        <div>
          <h2 id="record-tx-title" class="font-bold text-slate-900 dark:text-white">
            {{ isRepeatPreviewStep ? `Review Repeat Schedule (${repeatPreview.totalCount} occurrences)` : 'Record Transaction' }}
          </h2>
          <p class="text-xs text-slate-500 dark:text-slate-400">
            {{ isRepeatPreviewStep ? 'Confirm the exact dates below before creating these independent transactions.' : 'Log an expense, income receipt, or account transfer.' }}
          </p>
        </div>
        <button 
          @click="$emit('close')" 
          class="text-slate-400 hover:text-slate-600 dark:hover:text-white text-lg"
          aria-label="Close dialog">
          &times;
        </button>
      </div>

      <!-- Step 1: Type Switcher & Main Form -->
      <template v-if="!isRepeatPreviewStep">
        <!-- Type Switcher -->
        <div class="flex rounded-xl bg-slate-100 dark:bg-slate-800/80 p-1 border border-brand-border dark:border-brand-darkborder">
        <button
          type="button"
          @click="setTxType('expense')"
          class="flex-1 py-1.5 text-xs font-semibold rounded-lg transition"
          :class="txType === 'expense' 
            ? 'bg-white dark:bg-slate-700 text-rose-600 dark:text-rose-400 shadow-sm' 
            : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'">
          Expense
        </button>
        <button
          type="button"
          @click="setTxType('income')"
          class="flex-1 py-1.5 text-xs font-semibold rounded-lg transition"
          :class="txType === 'income' 
            ? 'bg-white dark:bg-slate-700 text-emerald-600 dark:text-emerald-400 shadow-sm' 
            : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'">
          Income
        </button>
        <button
          type="button"
          @click="setTxType('transfer')"
          class="flex-1 py-1.5 text-xs font-semibold rounded-lg transition"
          :class="txType === 'transfer' 
            ? 'bg-white dark:bg-slate-700 text-indigo-600 dark:text-indigo-400 shadow-sm' 
            : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'">
          Transfer
        </button>
      </div>

      <form @submit.prevent="handleSubmit" class="space-y-4">
        <!-- Error Banner -->
        <div v-if="errorMessage" class="p-3 rounded-lg bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 text-rose-600 dark:text-rose-400 text-xs">
          {{ errorMessage }}
        </div>

        <!-- Amount and Date Grid -->
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
              Amount ({{ baseCurrencySymbol }})
            </label>
            <div class="relative">
              <span class="absolute left-3.5 top-2.5 text-sm font-bold text-slate-400">{{ baseCurrencySymbol }}</span>
              <input 
                v-model.number="amount" 
                type="number" 
                step="0.01" 
                min="0.01" 
                required 
                placeholder="0.00" 
                @input="onBaseAmountInput"
                class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl pl-8 pr-3.5 py-2.5 text-sm font-mono font-bold text-slate-900 dark:text-white focus:outline-none focus:border-slate-400 dark:focus:border-slate-600" />
            </div>
          </div>

          <div>
            <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
              {{ isRepeat ? 'First Occurrence Date' : 'Date' }}
            </label>
            <input 
              v-model="transactionDate" 
              type="date" 
              required 
              class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3.5 py-2.5 text-xs text-slate-900 dark:text-white focus:outline-none focus:border-slate-400 dark:focus:border-slate-600" />
          </div>
        </div>

        <!-- Planned Future Activity Notice (Single entry only) -->
        <div 
          v-if="isPlanned && !isRepeat" 
          data-testid="planned-activity-notice"
          class="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-800 dark:text-amber-300 text-xs flex items-start gap-2.5">
          <svg class="w-4 h-4 text-amber-500 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
          <div>
            <div class="font-semibold">Planned Future Activity</div>
            <div class="text-[11px] opacity-90 mt-0.5">
              This transaction is dated in the future ({{ transactionDate }}). It will be saved as planned activity and will not reduce your current account balance until its effective date arrives.
            </div>
          </div>
        </div>

        <!-- Repeat Transaction Section -->
        <div 
          data-testid="repeat-transaction-section"
          class="rounded-xl border border-brand-border dark:border-brand-darkborder p-3.5 bg-slate-50/50 dark:bg-slate-800/40 space-y-3">
          <div class="flex items-center justify-between gap-2">
            <label class="flex items-center space-x-2 cursor-pointer select-none">
              <input 
                type="checkbox" 
                v-model="isRepeat"
                data-testid="repeat-transaction-toggle"
                class="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 w-4 h-4" />
              <span class="text-xs font-semibold text-slate-700 dark:text-slate-300">
                Repeat transaction
              </span>
            </label>
            <span class="text-[10px] font-mono text-slate-400">
              {{ isRepeat ? 'Creates separate dated transactions up front' : 'Optional multi-date series' }}
            </span>
          </div>

          <div v-if="isRepeat" class="space-y-3 pt-2.5 border-t border-brand-border/60 dark:border-brand-darkborder/60">
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
                  Frequency
                </label>
                <select 
                  v-model="repeatFrequency"
                  data-testid="repeat-frequency-select"
                  class="w-full bg-white dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none">
                  <option v-for="opt in REPEAT_FREQUENCY_OPTIONS" :key="opt.value" :value="opt.value">
                    {{ opt.label }}
                  </option>
                </select>
              </div>

              <div>
                <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
                  Create Until
                </label>
                <div class="flex rounded-xl bg-slate-100 dark:bg-slate-900/60 p-0.5 border border-brand-border dark:border-brand-darkborder">
                  <button
                    type="button"
                    data-testid="repeat-end-mode-count"
                    @click="setRepeatEndMode('count')"
                    class="flex-1 py-1.5 px-2 text-[11px] font-semibold rounded-lg transition"
                    :class="repeatEndMode === 'count' 
                      ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm' 
                      : 'text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'">
                    Fixed count
                  </button>
                  <button
                    type="button"
                    data-testid="repeat-end-mode-end-date"
                    @click="setRepeatEndMode('end_date')"
                    class="flex-1 py-1.5 px-2 text-[11px] font-semibold rounded-lg transition"
                    :class="repeatEndMode === 'end_date' 
                      ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm' 
                      : 'text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'">
                    End date
                  </button>
                </div>
              </div>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 items-start">
              <div v-if="repeatEndMode === 'count'">
                <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
                  Number of Occurrences
                </label>
                <input
                  v-model.number="repeatCount"
                  type="number"
                  min="2"
                  :max="MAX_REPEAT_OCCURRENCES"
                  required
                  data-testid="repeat-count-input"
                  class="w-full bg-white dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs font-mono font-semibold text-slate-900 dark:text-white focus:outline-none" />
                <p class="text-[10px] text-slate-400 mt-1">
                  Includes the first occurrence (between 2 and {{ MAX_REPEAT_OCCURRENCES }}).
                </p>
              </div>
              <div v-else>
                <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
                  Last Occurrence Date
                </label>
                <input
                  v-model="repeatLastDate"
                  type="date"
                  :min="transactionDate"
                  required
                  data-testid="repeat-last-date-input"
                  class="w-full bg-white dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none" />
                <p class="text-[10px] text-slate-400 mt-1">
                  Creates occurrences from {{ transactionDate }} up to and including {{ repeatLastDate || '...' }}.
                </p>
              </div>

              <!-- Live Inline Schedule Summary -->
              <div 
                data-testid="repeat-inline-summary"
                class="rounded-xl border p-2.5 text-xs"
                :class="repeatPreview.error 
                  ? 'bg-rose-50/70 dark:bg-rose-950/30 border-rose-200 dark:border-rose-900 text-rose-700 dark:text-rose-300' 
                  : 'bg-white dark:bg-slate-900/50 border-brand-border dark:border-brand-darkborder text-slate-700 dark:text-slate-300'">
                <template v-if="repeatPreview.error">
                  <div class="font-semibold text-[11px]">Schedule needs adjustment</div>
                  <div class="text-[11px] mt-0.5">{{ repeatPreview.error }}</div>
                </template>
                <template v-else>
                  <div class="flex items-center justify-between gap-2">
                    <span class="font-semibold text-slate-900 dark:text-white">
                      {{ repeatPreview.totalCount }} occurrence{{ repeatPreview.totalCount === 1 ? '' : 's' }}
                    </span>
                    <span class="text-[10px] font-mono text-slate-500">
                      {{ repeatPreview.dates[0]?.date }} → {{ repeatPreview.dates[repeatPreview.dates.length - 1]?.date }}
                    </span>
                  </div>
                  <div class="text-[11px] text-slate-500 dark:text-slate-400 mt-1 flex flex-wrap gap-x-2 gap-y-0.5">
                    <span>{{ repeatPreview.activeCount }} active (past/today)</span>
                    <span>&middot;</span>
                    <span :class="repeatPreview.plannedCount > 0 ? 'text-amber-600 dark:text-amber-400 font-medium' : ''">
                      {{ repeatPreview.plannedCount }} planned (future)
                    </span>
                  </div>
                </template>
              </div>
            </div>

            <!-- Month-End & Leap-Year Rule Explanation -->
            <div 
              v-if="repeatPreview.monthEndRuleText"
              data-testid="repeat-month-end-rule"
              class="p-2.5 rounded-lg bg-indigo-50/70 dark:bg-indigo-950/30 border border-indigo-200/80 dark:border-indigo-900/60 text-[11px] text-indigo-900 dark:text-indigo-200 leading-relaxed">
              {{ repeatPreview.monthEndRuleText }}
            </div>
          </div>
        </div>

        <!-- Foreign Currency Toggle & Configuration (Expense/Income only) -->
        <div v-if="txType !== 'transfer'" class="rounded-xl border border-brand-border dark:border-brand-darkborder p-3 bg-slate-50/50 dark:bg-slate-800/40 space-y-3">
          <div class="flex items-center justify-between">
            <label class="flex items-center space-x-2 cursor-pointer select-none">
              <input 
                type="checkbox" 
                v-model="isForeign" 
                class="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 w-4 h-4" />
              <span class="text-xs font-semibold text-slate-700 dark:text-slate-300">
                Foreign Currency Transaction
              </span>
            </label>
            <span v-if="isForeign" class="text-[10px] font-mono text-slate-400">
              Preserves original provenance
            </span>
          </div>

          <!-- Foreign Details (Expanded when checked) -->
          <div v-if="isForeign" class="space-y-3 pt-2 border-t border-brand-border/60 dark:border-brand-darkborder/60">
            <!-- Currency & Original Amount Grid -->
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
                  Original Currency
                </label>
                <select 
                  v-model="origCurrency"
                  @change="handleOrigCurrencyChange"
                  class="w-full bg-white dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none">
                  <option 
                    v-for="c in foreignCurrencyOptions" 
                    :key="c.code" 
                    :value="c.code">
                    {{ c.code }} - {{ c.name }} ({{ c.symbol }})
                  </option>
                </select>
              </div>

              <div>
                <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
                  Original Amount ({{ selectedCurrencySpec.symbol }})
                </label>
                <div class="relative">
                  <span class="absolute left-3 top-2 text-xs font-mono font-bold text-slate-400">
                    {{ selectedCurrencySpec.symbol }}
                  </span>
                  <input 
                    v-model.number="origAmount" 
                    type="number" 
                    :step="selectedCurrencyStep"
                    min="0.0001" 
                    required 
                    @input="onOrigAmountInput"
                    placeholder="0.00" 
                    class="w-full bg-white dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl pl-8 pr-3 py-2 text-xs font-mono font-bold text-slate-900 dark:text-white focus:outline-none" />
                </div>
              </div>
            </div>

            <!-- Mode Selector: Bank Charge vs Rate -->
            <div class="space-y-1.5">
              <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500">
                Conversion Method
              </label>
              <div class="flex flex-col sm:flex-row gap-2">
                <button
                  type="button"
                  @click="setForeignMode('actual')"
                  class="flex-1 px-3 py-2 text-xs rounded-xl border text-left transition"
                  :class="foreignMode === 'actual' 
                    ? 'border-indigo-500 bg-indigo-50/50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 font-semibold' 
                    : 'border-brand-border dark:border-brand-darkborder text-slate-600 dark:text-slate-400 hover:bg-white dark:hover:bg-slate-800'">
                  <div>Actual bank charge ({{ baseCurrencyCode }})</div>
                  <div class="text-[10px] font-normal opacity-80 mt-0.5">Enter the exact amount billed to your account</div>
                </button>
                <button
                  type="button"
                  @click="setForeignMode('rate')"
                  class="flex-1 px-3 py-2 text-xs rounded-xl border text-left transition"
                  :class="foreignMode === 'rate' 
                    ? 'border-indigo-500 bg-indigo-50/50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 font-semibold' 
                    : 'border-brand-border dark:border-brand-darkborder text-slate-600 dark:text-slate-400 hover:bg-white dark:hover:bg-slate-800'">
                  <div>Exchange rate</div>
                  <div class="text-[10px] font-normal opacity-80 mt-0.5">Calculate {{ baseCurrencyCode }} amount using rate</div>
                </button>
              </div>
            </div>

            <!-- Exchange Rate Input (When Mode is 'rate') -->
            <div v-if="foreignMode === 'rate'">
              <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
                Exchange Rate ({{ baseCurrencyCode }} per 1 {{ origCurrency }})
              </label>
              <input 
                v-model.number="exchangeRate" 
                type="number" 
                step="0.00000001" 
                min="0.00000001" 
                required
                @input="onRateInput"
                placeholder="e.g. 0.78500000" 
                class="w-full bg-white dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs font-mono text-slate-900 dark:text-white focus:outline-none" />
            </div>

            <!-- Implied Effective Rate Badge (When Mode is 'actual') -->
            <div v-if="foreignMode === 'actual' && impliedRate" class="p-2.5 rounded-lg bg-indigo-50/70 dark:bg-indigo-950/30 border border-indigo-200 dark:border-indigo-900/60 text-[11px] text-indigo-900 dark:text-indigo-300 font-mono flex items-center justify-between">
              <span>Implied Effective Rate:</span>
              <span class="font-bold">1 {{ origCurrency }} = {{ impliedRate }} {{ baseCurrencyCode }}</span>
            </div>
            <p v-if="foreignMode === 'actual' && impliedRate" class="text-[10px] text-slate-400">
              * The posted {{ baseCurrencyCode }} amount is permanent in the ledger; this rate is derived, not a market rate.
            </p>
          </div>
        </div>

        <!-- Expense & Income Fields -->
        <template v-if="txType === 'expense' || txType === 'income'">
          <div>
            <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
              {{ txType === 'expense' ? 'Merchant / Payee (Optional)' : 'Source / Payer (Optional)' }}
            </label>
            <input 
              v-model="merchant" 
              type="text" 
              :placeholder="txType === 'expense' ? 'e.g. Waitrose (leave blank if unrecorded)' : 'e.g. Acme Corp (leave blank if unrecorded)'" 
              class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3.5 py-2.5 text-xs text-slate-900 dark:text-white focus:outline-none focus:border-slate-400 dark:focus:border-slate-600" />
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <div class="flex items-center justify-between mb-1">
                <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500">
                  Account (Optional)
                </label>
                <span v-if="accountsStore.loading && eligibleAccounts.length > 0" class="text-[10px] text-indigo-500 font-mono flex items-center gap-1">
                  <span class="inline-block w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse"></span>
                  Updating...
                </span>
              </div>

              <!-- Loading State (when no accounts loaded yet) -->
              <div 
                v-if="accountsStore.loading && eligibleAccounts.length === 0" 
                data-testid="account-loading-state"
                class="flex items-center space-x-2 text-xs text-slate-500 dark:text-slate-400 py-2.5 px-3.5 bg-slate-50 dark:bg-slate-800 rounded-xl border border-brand-border dark:border-brand-darkborder animate-pulse"
                role="status">
                <svg class="animate-spin h-3.5 w-3.5 text-indigo-500 shrink-0" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <span>Loading workspace accounts...</span>
              </div>

              <!-- Error State (when loading failed and no accounts available) -->
              <div 
                v-else-if="accountsStore.error && eligibleAccounts.length === 0" 
                data-testid="account-error-state"
                class="p-2.5 rounded-xl bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900 text-amber-800 dark:text-amber-300 text-xs flex items-center justify-between gap-2"
                role="alert">
                <div class="truncate text-[11px]">
                  <span class="font-semibold">Accounts failed to load:</span>
                  <span class="ml-1 opacity-90 truncate">{{ accountsStore.error }}</span>
                </div>
                <button 
                  type="button" 
                  @click="retryLoadAccounts" 
                  data-testid="retry-load-accounts-btn"
                  class="px-2.5 py-1 text-[11px] font-semibold bg-amber-200 dark:bg-amber-800 text-amber-900 dark:text-amber-100 rounded-lg hover:opacity-90 transition shrink-0">
                  Retry
                </button>
              </div>

              <!-- Normal Select Dropdown -->
              <select 
                v-else
                v-model="accountId" 
                @change="onAccountChange"
                data-testid="record-tx-account-select"
                class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2.5 text-xs text-slate-900 dark:text-white focus:outline-none">
                <option :value="null">Unassigned (assign later)</option>
                <option v-for="acc in eligibleAccounts" :key="acc.id" :value="acc.id">
                  {{ acc.name }} ({{ acc.currency }})
                </option>
              </select>
            </div>

            <div>
              <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
                Category
              </label>
              <select 
                v-model="categoryId" 
                @change="handleCategoryChange"
                class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2.5 text-xs text-slate-900 dark:text-white focus:outline-none">
                <option :value="null">Uncategorised</option>
                <option v-for="cat in compatibleCategories" :key="cat.id" :value="cat.id">
                  {{ cat.name }}
                </option>
              </select>
              <p v-if="categoryClearedNotice" class="text-[10px] text-amber-600 dark:text-amber-400 mt-1">
                {{ categoryClearedNotice }}
              </p>
            </div>
          </div>

          <!-- Expense Nature (Only for Expense) -->
          <div v-if="txType === 'expense'" class="space-y-1.5">
            <div class="flex items-center justify-between">
              <label class="text-[11px] font-mono uppercase font-semibold text-slate-500">
                Budget Behaviour
              </label>
              <span v-if="isNatureInherited" class="text-[10px] text-slate-400 font-mono">
                (Default for selected category)
              </span>
            </div>
            <div class="flex items-center space-x-2">
              <button
                type="button"
                @click="setExpenseNature('fixed')"
                class="px-3 py-1.5 rounded-lg text-xs font-semibold border transition"
                :class="expenseNature === 'fixed'
                  ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300'
                  : 'border-brand-border dark:border-brand-darkborder text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800'">
                Fixed
              </button>
              <button
                type="button"
                @click="setExpenseNature('variable')"
                class="px-3 py-1.5 rounded-lg text-xs font-semibold border transition"
                :class="expenseNature === 'variable'
                  ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300'
                  : 'border-brand-border dark:border-brand-darkborder text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800'">
                Variable
              </button>
              <button
                type="button"
                @click="setExpenseNature('unclassified')"
                class="px-3 py-1.5 rounded-lg text-xs font-semibold border transition"
                :class="expenseNature === 'unclassified'
                  ? 'border-slate-500 bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300'
                  : 'border-brand-border dark:border-brand-darkborder text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800'">
                Unclassified
              </button>
            </div>
          </div>
        </template>

        <!-- Transfer Fields -->
        <template v-else-if="txType === 'transfer'">
          <!-- Loading State for Transfers -->
          <div 
            v-if="accountsStore.loading && eligibleAccounts.length === 0" 
            data-testid="transfer-accounts-loading"
            class="p-4 rounded-xl bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder flex items-center justify-center space-x-2 text-xs text-slate-500 dark:text-slate-400 animate-pulse"
            role="status">
            <svg class="animate-spin h-4 w-4 text-indigo-500 shrink-0" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <span>Loading workspace accounts for transfer...</span>
          </div>

          <!-- Error State for Transfers -->
          <div 
            v-else-if="accountsStore.error && eligibleAccounts.length === 0" 
            data-testid="transfer-accounts-error"
            class="p-3 rounded-xl bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900 text-amber-800 dark:text-amber-300 text-xs flex items-center justify-between gap-2"
            role="alert">
            <div class="truncate text-[11px]">
              <span class="font-semibold">Failed to load accounts for transfer:</span>
              <span class="ml-1 opacity-90 truncate">{{ accountsStore.error }}</span>
            </div>
            <button 
              type="button" 
              @click="retryLoadAccounts" 
              data-testid="transfer-retry-load-accounts-btn"
              class="px-2.5 py-1 text-[11px] font-semibold bg-amber-200 dark:bg-amber-800 text-amber-900 dark:text-amber-100 rounded-lg hover:opacity-90 transition shrink-0">
              Retry
            </button>
          </div>

          <div v-else class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
                From (Source Account)
              </label>
              <select 
                v-model="accountId" 
                @change="onAccountChange"
                required 
                data-testid="transfer-source-account-select"
                class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2.5 text-xs text-slate-900 dark:text-white focus:outline-none">
                <option :value="null" disabled>Select source account</option>
                <option v-for="acc in eligibleAccounts" :key="acc.id" :value="acc.id">
                  {{ acc.name }}
                </option>
              </select>
            </div>

            <div>
              <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
                To (Destination Account)
              </label>
              <select 
                v-model="destinationAccountId" 
                required 
                data-testid="transfer-dest-account-select"
                class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2.5 text-xs text-slate-900 dark:text-white focus:outline-none">
                <option :value="null" disabled>Select destination account</option>
                <option 
                  v-for="acc in availableDestinationAccounts" 
                  :key="acc.id" 
                  :value="acc.id">
                  {{ acc.name }}
                </option>
              </select>
            </div>
          </div>

          <div>
            <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
              Transfer Description (Optional)
            </label>
            <input 
              v-model="merchant" 
              type="text" 
              placeholder="e.g. Monthly savings transfer" 
              class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3.5 py-2.5 text-xs text-slate-900 dark:text-white focus:outline-none focus:border-slate-400 dark:focus:border-slate-600" />
          </div>
        </template>

        <!-- Notes Field -->
        <div>
          <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
            Notes (Optional)
          </label>
          <textarea 
            v-model="notes" 
            rows="2" 
            placeholder="Add any extra context or transaction details..." 
            class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3.5 py-2 text-xs text-slate-900 dark:text-white focus:outline-none focus:border-slate-400 dark:focus:border-slate-600 resize-none">
          </textarea>
        </div>

        <!-- Action Buttons -->
        <div class="flex items-center justify-end space-x-3 pt-3 border-t border-brand-border dark:border-brand-darkborder">
          <button 
            type="button" 
            @click="$emit('close')" 
            class="px-4 py-2 text-xs font-semibold rounded-full border border-brand-border dark:border-brand-darkborder hover:bg-slate-100 dark:hover:bg-slate-800 transition text-slate-700 dark:text-slate-300">
            Cancel
          </button>
          <button 
            type="submit" 
            :disabled="isSubmitting || (isRepeat && (!!repeatPreview.error || repeatPreview.totalCount === 0))"
            :data-testid="isRepeat ? 'repeat-preview-trigger' : 'single-submit-btn'"
            class="px-5 py-2 text-xs font-semibold rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 hover:opacity-90 transition shadow-sm disabled:opacity-50">
            {{ submitButtonText }}
          </button>
        </div>
      </form>
      </template>

      <!-- Step 2: Explicit Preview & Confirmation Before Saving Repeat Series -->
      <div v-else data-testid="repeat-preview-step" class="space-y-4">
        <div v-if="errorMessage" class="p-3 rounded-lg bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 text-rose-600 dark:text-rose-400 text-xs">
          {{ errorMessage }}
        </div>

        <!-- Shared Details Summary -->
        <div class="rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50/60 dark:bg-slate-800/40 p-4 space-y-2.5 text-xs">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="flex items-center gap-2">
              <span class="px-2 py-0.5 rounded-md text-[10px] font-mono uppercase font-bold"
                :class="txType === 'expense'
                  ? 'bg-rose-100 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300'
                  : txType === 'income'
                    ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300'
                    : 'bg-indigo-100 text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300'">
                {{ txType }}
              </span>
              <span class="font-bold text-slate-900 dark:text-white text-sm">
                {{ perOccurrenceAmountLabel }} &times; {{ repeatPreview.totalCount }}
              </span>
            </div>
            <div class="text-right font-mono text-xs text-slate-600 dark:text-slate-300">
              Combined total: <strong class="text-slate-900 dark:text-white">{{ totalSeriesAmountLabel }}</strong>
            </div>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1.5 text-[11px] text-slate-600 dark:text-slate-300 pt-1 border-t border-brand-border/60 dark:border-brand-darkborder/60">
            <div><span class="text-slate-400">Merchant / Desc:</span> <span class="font-medium text-slate-900 dark:text-white">{{ previewMerchantLabel }}</span></div>
            <div><span class="text-slate-400">Account:</span> <span class="font-medium text-slate-900 dark:text-white">{{ previewAccountLabel }}</span></div>
            <div v-if="txType !== 'transfer'"><span class="text-slate-400">Category:</span> <span class="font-medium text-slate-900 dark:text-white">{{ previewCategoryLabel }}</span></div>
            <div v-if="txType === 'expense'"><span class="text-slate-400">Nature:</span> <span class="font-medium capitalize text-slate-900 dark:text-white">{{ expenseNature }}</span></div>
            <div><span class="text-slate-400">Schedule:</span> <span class="font-medium text-slate-900 dark:text-white">{{ selectedFrequencyLabel }}</span></div>
            <div><span class="text-slate-400">Timezone:</span> <span class="font-mono text-slate-900 dark:text-white">{{ activeProfileTimezone }}</span></div>
            <div v-if="isForeign && txType !== 'transfer'" class="sm:col-span-2">
              <span class="text-slate-400">Origin currency:</span>
              <span class="font-mono font-medium text-slate-900 dark:text-white">
                {{ selectedCurrencySpec.symbol }}{{ origAmount }} {{ origCurrency }} per entry
              </span>
            </div>
            <div v-if="notes.trim()" class="sm:col-span-2">
              <span class="text-slate-400">Notes:</span>
              <span class="text-slate-800 dark:text-slate-200">{{ notes.trim() }}</span>
            </div>
          </div>
        </div>

        <!-- Exact Dates Table / Preview List -->
        <div class="space-y-1.5">
          <div class="flex items-center justify-between text-[11px] font-mono uppercase font-semibold text-slate-500">
            <span>Exact Dates to Create ({{ repeatPreview.totalCount }})</span>
            <span>{{ repeatPreview.activeCount }} Active &middot; {{ repeatPreview.plannedCount }} Planned</span>
          </div>
          <div 
            data-testid="repeat-preview-dates-list"
            class="max-h-60 overflow-y-auto rounded-xl border border-brand-border dark:border-brand-darkborder divide-y divide-brand-border/60 dark:divide-brand-darkborder/60 bg-white dark:bg-slate-900/40">
            <div 
              v-for="occ in repeatPreview.dates" 
              :key="occ.index"
              class="px-3.5 py-2 flex items-center justify-between gap-2 text-xs">
              <div class="flex items-center gap-2.5">
                <span class="text-[11px] font-mono text-slate-400 w-7">#{{ occ.index }}</span>
                <span class="font-mono font-semibold text-slate-900 dark:text-white">{{ occ.date }}</span>
                <span class="text-[11px] text-slate-500">{{ occ.weekday }}</span>
                <span 
                  v-if="occ.isClamped && occ.clampReason"
                  class="px-1.5 py-0.5 rounded bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 text-[10px] font-medium">
                  {{ occ.clampReason }}
                </span>
              </div>
              <span
                class="px-2 py-0.5 rounded-full text-[10px] font-semibold"
                :class="occ.status === 'planned'
                  ? 'bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300'
                  : 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300'">
                {{ occ.status === 'planned' ? 'Planned (future)' : occ.status === 'today' ? 'Active (today)' : 'Active (past)' }}
              </span>
            </div>
          </div>
        </div>

        <!-- Independent Lifecycle & Duplicate Protection Notice -->
        <div 
          data-testid="repeat-protection-notice"
          class="p-3 rounded-xl bg-slate-100/80 dark:bg-slate-800/60 border border-brand-border dark:border-brand-darkborder text-[11px] text-slate-600 dark:text-slate-300 space-y-1 leading-relaxed">
          <div>
            <strong>Independent transactions:</strong> Only the {{ repeatPreview.totalCount }} dates shown above are created. Editing or deleting one entry later will never silently modify other occurrences.
          </div>
          <div>
            <strong>Duplicate &amp; retry protection:</strong> All occurrences save in one atomic transaction using a unique submission key, so double-clicking or retrying after a timeout will not create duplicates.
          </div>
        </div>

        <!-- Preview Action Buttons -->
        <div class="flex flex-wrap items-center justify-end gap-2.5 pt-3 border-t border-brand-border dark:border-brand-darkborder">
          <button
            type="button"
            @click="$emit('close')"
            class="px-4 py-2 text-xs font-semibold rounded-full border border-brand-border dark:border-brand-darkborder hover:bg-slate-100 dark:hover:bg-slate-800 transition text-slate-700 dark:text-slate-300">
            Cancel
          </button>
          <button
            type="button"
            data-testid="repeat-edit-pattern-btn"
            :disabled="isSubmitting"
            @click="returnToPatternEdit"
            class="px-4 py-2 text-xs font-semibold rounded-full border border-slate-300 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800 transition text-slate-800 dark:text-slate-200 disabled:opacity-50">
            Edit Pattern
          </button>
          <button
            type="button"
            data-testid="repeat-confirm-submit-btn"
            :disabled="isSubmitting || repeatPreview.totalCount === 0"
            @click="confirmRepeatSubmit"
            class="px-5 py-2 text-xs font-semibold rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 hover:opacity-90 transition shadow-sm disabled:opacity-50">
            {{ isSubmitting ? 'Creating series...' : `Create ${repeatPreview.totalCount} Transaction${repeatPreview.totalCount === 1 ? '' : 's'}` }}
          </button>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useAccountsStore } from '../stores/accounts';
import { useTransactionsStore } from '../stores/transactions';
import { useSystemStore } from '../stores/system';
import { useProfilesStore } from '../stores/profiles';
import {
  REPEAT_FREQUENCY_OPTIONS,
  MAX_REPEAT_OCCURRENCES,
  generateRepeatPreview,
  suggestDefaultEndDate,
  formatDateInTimeZone,
  createSubmissionKey,
} from '../utils/repeatDates';
import {
  filterCategoriesForTransactionType,
  isCategoryCompatibleWithTransaction,
} from '../utils/categoryPurpose';
import type {
  TransactionType,
  ExpenseNature,
  TransactionCreatePayload,
  RepeatFrequency,
  RepeatEndMode,
  RepeatTransactionCreatePayload,
} from '../types';

const props = defineProps<{
  isOpen: boolean;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'recorded'): void;
}>();

const accountsStore = useAccountsStore();
const txStore = useTransactionsStore();
const systemStore = useSystemStore();
const profilesStore = useProfilesStore();

const txType = ref<TransactionType>('expense');
const amount = ref<number | ''>('');
const merchant = ref('');
const accountId = ref<number | null>(null);
const destinationAccountId = ref<number | null>(null);
const isExplicitUnassigned = ref(false);
const categoryId = ref<number | null>(null);
const categoryClearedNotice = ref<string | null>(null);
const expenseNature = ref<ExpenseNature>('unclassified');
const isNatureInherited = ref(true);

const compatibleCategories = computed(() =>
  filterCategoriesForTransactionType(txStore.categories, txType.value)
);
const activeProfileTimezone = computed(() => systemStore.config?.app_timezone || 'Europe/London');
const todayLocal = computed(() => formatDateInTimeZone(new Date(), systemStore.config?.app_timezone));
const transactionDate = ref(formatDateInTimeZone(new Date()));
const notes = ref('');

// Repeat Transaction State
const isRepeat = ref(false);
const repeatFrequency = ref<RepeatFrequency>('monthly');
const repeatEndMode = ref<RepeatEndMode>('count');
const repeatCount = ref<number | ''>(3);
const repeatLastDate = ref('');
const isRepeatPreviewStep = ref(false);
const repeatIdempotencyKey = ref<string | null>(null);

// Foreign Currency State
const isForeign = ref(false);
const origCurrency = ref('USD');
const origAmount = ref<number | ''>('');
const foreignMode = ref<'actual' | 'rate'>('actual');
const exchangeRate = ref<number | ''>('');

const errorMessage = ref<string | null>(null);
const isSubmitting = ref(false);

const baseCurrencyCode = computed(() => systemStore.config?.base_currency || 'GBP');
const baseCurrencySymbol = computed(() => systemStore.config?.base_currency_symbol || '£');

const foreignCurrencyOptions = computed(() => {
  if (systemStore.config?.supported_currencies) {
    return Object.values(systemStore.config.supported_currencies)
      .filter(c => c.code !== baseCurrencyCode.value)
      .map(c => ({
        code: c.code,
        symbol: c.symbol,
        name: c.name,
        precision: c.precision,
      }));
  }
  return [
    { code: 'USD', symbol: '$', name: 'US Dollar', precision: 2 },
    { code: 'EUR', symbol: '€', name: 'Euro', precision: 2 },
    { code: 'CAD', symbol: 'CA$', name: 'Canadian Dollar', precision: 2 },
    { code: 'AUD', symbol: 'A$', name: 'Australian Dollar', precision: 2 },
    { code: 'JPY', symbol: '¥', name: 'Japanese Yen', precision: 0 },
    { code: 'CHF', symbol: 'CHF', name: 'Swiss Franc', precision: 2 },
  ];
});

const selectedCurrencySpec = computed(() => {
  const found = foreignCurrencyOptions.value.find(c => c.code === origCurrency.value);
  return found || { code: origCurrency.value, symbol: origCurrency.value, precision: 2, name: origCurrency.value };
});

const selectedCurrencyStep = computed(() => {
  const p = selectedCurrencySpec.value.precision;
  if (p === 0) return '1';
  if (p === 3) return '0.001';
  return '0.01';
});

const impliedRate = computed(() => {
  if (!isForeign.value || !origAmount.value || !amount.value) return null;
  const o = Number(origAmount.value);
  const b = Number(amount.value);
  if (o <= 0 || b <= 0) return null;
  return (b / o).toFixed(6);
});

function handleOrigCurrencyChange() {
  if (foreignMode.value === 'rate') {
    recalculateFromRate();
  }
}

function setForeignMode(mode: 'actual' | 'rate') {
  foreignMode.value = mode;
  if (mode === 'rate') {
    if (impliedRate.value && !exchangeRate.value) {
      exchangeRate.value = Number(impliedRate.value);
    }
    recalculateFromRate();
  }
}

function onOrigAmountInput() {
  if (foreignMode.value === 'rate') {
    recalculateFromRate();
  }
}

function onRateInput() {
  if (foreignMode.value === 'rate') {
    recalculateFromRate();
  }
}

function onBaseAmountInput() {
  if (foreignMode.value === 'rate') {
    if (origAmount.value && Number(origAmount.value) > 0 && amount.value && Number(amount.value) > 0) {
      exchangeRate.value = Number((Number(amount.value) / Number(origAmount.value)).toFixed(8));
    }
  }
}

function recalculateFromRate() {
  if (origAmount.value && exchangeRate.value) {
    const o = Number(origAmount.value);
    const r = Number(exchangeRate.value);
    if (o > 0 && r > 0) {
      amount.value = Number((o * r).toFixed(2));
    }
  }
}

const eligibleAccounts = computed(() => {
  return accountsStore.accounts.filter(a => a.is_active !== false);
});

const availableDestinationAccounts = computed(() => {
  return eligibleAccounts.value.filter(a => a.id !== accountId.value);
});

const isPlanned = computed(() => {
  if (!transactionDate.value) return false;
  return transactionDate.value > todayLocal.value;
});

const repeatPreview = computed(() => {
  return generateRepeatPreview({
    firstDate: transactionDate.value,
    frequency: repeatFrequency.value,
    endMode: repeatEndMode.value,
    lastDate: repeatLastDate.value,
    occurrenceCount: repeatCount.value,
    todayLocalIso: todayLocal.value,
    minCount: repeatEndMode.value === 'count' ? 2 : 1,
  });
});

const selectedAccountCurrencySymbol = computed(() => {
  const source = eligibleAccounts.value.find(a => a.id === accountId.value);
  if (source && systemStore.config?.supported_currencies?.[source.currency]) {
    return systemStore.config.supported_currencies[source.currency].symbol;
  }
  return baseCurrencySymbol.value;
});

const perOccurrenceAmountLabel = computed(() => {
  const num = Number(amount.value || 0);
  return `${selectedAccountCurrencySymbol.value}${num.toFixed(2)}`;
});

const totalSeriesAmountLabel = computed(() => {
  const num = Number(amount.value || 0) * repeatPreview.value.totalCount;
  return `${selectedAccountCurrencySymbol.value}${num.toFixed(2)}`;
});

const previewMerchantLabel = computed(() => {
  const trimmed = merchant.value.trim();
  if (trimmed) return trimmed;
  if (txType.value === 'transfer') {
    const dest = eligibleAccounts.value.find(a => a.id === destinationAccountId.value);
    return dest ? `Transfer to ${dest.name}` : 'Internal Transfer';
  }
  return 'Not specified';
});

const previewAccountLabel = computed(() => {
  const src = eligibleAccounts.value.find(a => a.id === accountId.value);
  if (txType.value === 'transfer') {
    const dest = eligibleAccounts.value.find(a => a.id === destinationAccountId.value);
    return `${src?.name || 'Source'} → ${dest?.name || 'Destination'}`;
  }
  return src ? `${src.name} (${src.currency})` : 'Unassigned';
});

const previewCategoryLabel = computed(() => {
  if (!categoryId.value) return 'Uncategorised';
  return txStore.categories.find(c => c.id === categoryId.value)?.name || 'Uncategorised';
});

const selectedFrequencyLabel = computed(() => {
  return REPEAT_FREQUENCY_OPTIONS.find(o => o.value === repeatFrequency.value)?.label || repeatFrequency.value;
});

function setRepeatEndMode(mode: RepeatEndMode) {
  repeatEndMode.value = mode;
  if (mode === 'end_date' && (!repeatLastDate.value || repeatLastDate.value < transactionDate.value)) {
    const fallbackCount = Number(repeatCount.value) >= 2 ? Number(repeatCount.value) : 3;
    repeatLastDate.value = suggestDefaultEndDate(transactionDate.value, repeatFrequency.value, fallbackCount);
  }
}

const submitButtonText = computed(() => {
  if (isSubmitting.value) return 'Saving...';
  if (isRepeat.value) {
    if (repeatPreview.value.totalCount > 0) {
      return `Preview ${repeatPreview.value.totalCount} Occurrence${repeatPreview.value.totalCount === 1 ? '' : 's'}`;
    }
    return 'Preview Repeat Schedule';
  }
  if (isPlanned.value) {
    if (txType.value === 'expense') return 'Plan Expense';
    if (txType.value === 'income') return 'Plan Income';
    return 'Schedule Transfer';
  }
  if (txType.value === 'expense') return 'Record Expense';
  if (txType.value === 'income') return 'Record Income';
  return 'Execute Transfer';
});

function onAccountChange() {
  if (txType.value !== 'transfer') {
    if (accountId.value === null) {
      isExplicitUnassigned.value = true;
    } else {
      isExplicitUnassigned.value = false;
    }
  } else {
    if (destinationAccountId.value === accountId.value) {
      const remaining = eligibleAccounts.value.filter(a => a.id !== accountId.value);
      destinationAccountId.value = remaining.length > 0 ? remaining[0].id : null;
    }
  }
}

function syncAccountSelection() {
  const eligible = eligibleAccounts.value;

  if (txType.value === 'transfer') {
    if (!accountId.value || !eligible.some(a => a.id === accountId.value)) {
      accountId.value = eligible.length > 0 ? eligible[0].id : null;
    }
    const destOptions = eligible.filter(a => a.id !== accountId.value);
    if (!destinationAccountId.value || !destOptions.some(a => a.id === destinationAccountId.value)) {
      destinationAccountId.value = destOptions.length > 0 ? destOptions[0].id : null;
    }
  } else {
    if (accountId.value !== null) {
      if (!eligible.some(a => a.id === accountId.value)) {
        accountId.value = eligible.length > 0 ? eligible[0].id : null;
        isExplicitUnassigned.value = false;
      }
    } else {
      if (!isExplicitUnassigned.value && eligible.length > 0) {
        accountId.value = eligible[0].id;
      }
    }
  }
}

async function retryLoadAccounts() {
  await accountsStore.loadData();
  syncAccountSelection();
}

function setTxType(type: TransactionType) {
  txType.value = type;
  errorMessage.value = null;
  if (
    categoryId.value !== null &&
    !isCategoryCompatibleWithTransaction(txStore.categories, categoryId.value, type)
  ) {
    categoryId.value = null;
    expenseNature.value = 'unclassified';
    isNatureInherited.value = true;
    categoryClearedNotice.value =
      type === 'transfer'
        ? 'Previous category was cleared because transfers do not use categories.'
        : `Cleared previous category because ${type} entries require an ${type} category.`;
  } else {
    categoryClearedNotice.value = null;
  }
  if (type !== 'expense') {
    expenseNature.value = 'unclassified';
  }
  if (type === 'transfer') {
    isForeign.value = false;
    syncAccountSelection();
  } else {
    syncAccountSelection();
  }
}

function setExpenseNature(nature: ExpenseNature) {
  expenseNature.value = nature;
  isNatureInherited.value = false;
}

function handleCategoryChange() {
  categoryClearedNotice.value = null;
  if (categoryId.value && txType.value === 'expense') {
    const selected = txStore.categories.find(c => c.id === categoryId.value);
    if (selected) {
      expenseNature.value = selected.default_expense_nature;
      isNatureInherited.value = true;
    }
  }
}

watch(() => props.isOpen, async (newVal) => {
  if (newVal) {
    errorMessage.value = null;
    isSubmitting.value = false;
    isRepeatPreviewStep.value = false;
    repeatIdempotencyKey.value = null;
    // Load accounts if empty or error
    if (eligibleAccounts.value.length === 0 || accountsStore.error) {
      await accountsStore.loadData();
    }
    syncAccountSelection();
    // Load categories if needed
    if (txStore.categories.length === 0) {
      txStore.loadCategories();
    }
    if (!systemStore.config) {
      await systemStore.loadConfig();
    }
    if (!transactionDate.value) {
      transactionDate.value = todayLocal.value;
    }
  } else {
    isRepeatPreviewStep.value = false;
    repeatIdempotencyKey.value = null;
  }
});

watch(
  [
    txType,
    amount,
    merchant,
    accountId,
    destinationAccountId,
    categoryId,
    expenseNature,
    transactionDate,
    notes,
    isForeign,
    origCurrency,
    origAmount,
    foreignMode,
    exchangeRate,
    isRepeat,
    repeatFrequency,
    repeatEndMode,
    repeatCount,
    repeatLastDate,
  ],
  () => {
    // Rotate idempotency key if user edits any transaction or schedule field
    if (!isRepeatPreviewStep.value) {
      repeatIdempotencyKey.value = null;
    }
  }
);

watch(isRepeat, (enabled) => {
  if (enabled && (!repeatLastDate.value || repeatLastDate.value < transactionDate.value)) {
    const countVal = Number(repeatCount.value) >= 2 ? Number(repeatCount.value) : 3;
    repeatLastDate.value = suggestDefaultEndDate(transactionDate.value || todayLocal.value, repeatFrequency.value, countVal);
  }
});

watch(eligibleAccounts, () => {
  if (props.isOpen) {
    syncAccountSelection();
  }
});

watch(
  () => profilesStore.activeProfile?.id,
  async (newProfileId, oldProfileId) => {
    if (newProfileId && newProfileId !== oldProfileId) {
      accountId.value = null;
      destinationAccountId.value = null;
      isExplicitUnassigned.value = false;
      if (props.isOpen) {
        await accountsStore.loadData();
        syncAccountSelection();
      }
    }
  }
);

onMounted(() => {
  if (txStore.categories.length === 0) {
    txStore.loadCategories();
  }
  if (!systemStore.config) {
    systemStore.loadConfig();
  }
  if (accountsStore.accounts.length === 0) {
    accountsStore.loadData();
  }
});

function validateSharedFields(): boolean {
  if (amount.value === '' || Number(amount.value) <= 0) {
    errorMessage.value = 'Please enter a valid positive amount.';
    return false;
  }

  if (txType.value === 'transfer') {
    if (!accountId.value) {
      errorMessage.value = 'Please select a source account.';
      return false;
    }
    if (!destinationAccountId.value) {
      errorMessage.value = 'Please select a destination account.';
      return false;
    }
    if (accountId.value === destinationAccountId.value) {
      errorMessage.value = 'Source and destination accounts must be distinct.';
      return false;
    }
  }

  if (isForeign.value && txType.value !== 'transfer') {
    if (!origAmount.value || Number(origAmount.value) <= 0) {
      errorMessage.value = 'Please enter a valid original amount for the foreign transaction.';
      return false;
    }
    if (foreignMode.value === 'rate' && (!exchangeRate.value || Number(exchangeRate.value) <= 0)) {
      errorMessage.value = 'Please enter a valid positive exchange rate.';
      return false;
    }
  }

  return true;
}

function resetModalFields() {
  amount.value = '';
  merchant.value = '';
  notes.value = '';
  isForeign.value = false;
  origAmount.value = '';
  origCurrency.value = 'USD';
  exchangeRate.value = '';
  foreignMode.value = 'actual';
  transactionDate.value = todayLocal.value;
  isRepeat.value = false;
  repeatFrequency.value = 'monthly';
  repeatEndMode.value = 'count';
  repeatCount.value = 3;
  repeatLastDate.value = '';
  isRepeatPreviewStep.value = false;
  repeatIdempotencyKey.value = null;
}

function returnToPatternEdit() {
  if (isSubmitting.value) return;
  errorMessage.value = null;
  isRepeatPreviewStep.value = false;
}

async function handleSubmit() {
  if (isSubmitting.value) return;
  errorMessage.value = null;

  if (!validateSharedFields()) {
    return;
  }

  if (isRepeat.value) {
    if (repeatPreview.value.error || repeatPreview.value.totalCount === 0) {
      errorMessage.value = repeatPreview.value.error || 'Repeat schedule must produce at least one occurrence.';
      return;
    }
    if (!repeatIdempotencyKey.value) {
      repeatIdempotencyKey.value = createSubmissionKey();
    }
    isRepeatPreviewStep.value = true;
    return;
  }

  isSubmitting.value = true;

  try {
    const payloadDate = transactionDate.value 
      ? new Date(transactionDate.value + 'T12:00:00Z').toISOString() 
      : new Date().toISOString();

    const payload: TransactionCreatePayload = {
      transaction_type: txType.value,
      amount: Number(amount.value),
      merchant: merchant.value.trim() || undefined,
      account_id: accountId.value,
      destination_account_id: txType.value === 'transfer' ? destinationAccountId.value : null,
      category_id: txType.value !== 'transfer' ? categoryId.value : null,
      expense_nature: txType.value === 'expense' ? expenseNature.value : null,
      transaction_date: payloadDate,
      notes: notes.value.trim() || undefined,
    };

    if (isForeign.value && txType.value !== 'transfer' && origAmount.value && origCurrency.value) {
      payload.original_amount = Number(origAmount.value);
      payload.original_currency = origCurrency.value;
      if (foreignMode.value === 'rate' && exchangeRate.value) {
        payload.exchange_rate = Number(exchangeRate.value);
      }
    }

    await txStore.createTransaction(payload);

    resetModalFields();
    emit('recorded');
    emit('close');
  } catch (err: any) {
    errorMessage.value = err.message || 'Failed to record transaction.';
  } finally {
    isSubmitting.value = false;
  }
}

async function confirmRepeatSubmit() {
  if (isSubmitting.value) return;
  errorMessage.value = null;

  if (!validateSharedFields()) {
    isRepeatPreviewStep.value = false;
    return;
  }
  if (repeatPreview.value.error || repeatPreview.value.totalCount === 0) {
    errorMessage.value = repeatPreview.value.error || 'Repeat schedule is invalid.';
    isRepeatPreviewStep.value = false;
    return;
  }

  if (!repeatIdempotencyKey.value) {
    repeatIdempotencyKey.value = createSubmissionKey();
  }

  isSubmitting.value = true;
  try {
    const payload: RepeatTransactionCreatePayload = {
      transaction_type: txType.value,
      amount: Number(amount.value),
      merchant: merchant.value.trim() || undefined,
      account_id: accountId.value,
      destination_account_id: txType.value === 'transfer' ? destinationAccountId.value : null,
      category_id: txType.value !== 'transfer' ? categoryId.value : null,
      expense_nature: txType.value === 'expense' ? expenseNature.value : null,
      notes: notes.value.trim() || undefined,
      frequency: repeatFrequency.value,
      first_date: transactionDate.value,
      end_mode: repeatEndMode.value,
      last_date: repeatEndMode.value === 'end_date' ? repeatLastDate.value : undefined,
      occurrence_count: repeatEndMode.value === 'count' ? Number(repeatCount.value) : undefined,
      idempotency_key: repeatIdempotencyKey.value,
    };

    if (isForeign.value && txType.value !== 'transfer' && origAmount.value && origCurrency.value) {
      payload.original_amount = Number(origAmount.value);
      payload.original_currency = origCurrency.value;
      if (foreignMode.value === 'rate' && exchangeRate.value) {
        payload.exchange_rate = Number(exchangeRate.value);
      }
    }

    await txStore.createRepeatTransactions(payload);

    resetModalFields();
    emit('recorded');
    emit('close');
  } catch (err: any) {
    // Keep isRepeatPreviewStep = true and keep the SAME repeatIdempotencyKey so retrying after
    // a timeout replays safely without creating duplicate occurrences.
    errorMessage.value = err.message || 'Failed to create repeat transactions.';
  } finally {
    isSubmitting.value = false;
  }
}
</script>

