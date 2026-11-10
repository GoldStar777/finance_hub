<template>
  <div class="space-y-6 animate-fadeIn pb-16">

    <!-- Header Banner -->
    <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
      <div>
        <div class="flex flex-wrap items-center gap-2.5">
          <h1 class="text-xl font-bold tracking-tight text-slate-900 dark:text-white">
            Data Quality &amp; Review
          </h1>
          <span
            v-if="reviewStore.activeCount > 0"
            data-testid="review-active-count-badge"
            class="px-2.5 py-0.5 rounded-full text-xs font-mono font-semibold bg-indigo-100 dark:bg-indigo-950/70 text-indigo-800 dark:text-indigo-200 border border-indigo-200 dark:border-indigo-800">
            {{ reviewStore.activeCount }} item{{ reviewStore.activeCount === 1 ? '' : 's' }} to review
          </span>
          <span
            v-else-if="!reviewStore.loading && reviewStore.report"
            class="px-2.5 py-0.5 rounded-full text-xs font-mono font-semibold bg-emerald-100 dark:bg-emerald-950/70 text-emerald-800 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">
            All clear
          </span>
        </div>
        <p class="text-xs text-slate-500 dark:text-slate-400 mt-1">
          Offline review suggestions and structural hygiene checks for this workspace. Scanning never changes financial records; updates happen only when you confirm.
        </p>
      </div>

      <div class="flex flex-wrap items-center gap-2 shrink-0">
        <button
          v-if="reviewStore.summary.dismissed_count > 0"
          type="button"
          data-testid="toggle-dismissed-btn"
          @click="toggleIncludeDismissed"
          class="px-3 py-1.5 rounded-full border text-xs font-semibold transition"
          :class="reviewStore.includeDismissed
            ? 'border-indigo-400 bg-indigo-50 text-indigo-800 dark:border-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-200'
            : 'border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'">
          {{ reviewStore.includeDismissed ? 'Hide' : 'Show' }} hidden ({{ reviewStore.summary.dismissed_count }})
        </button>

        <button
          v-if="reviewStore.summary.dismissed_count > 0"
          type="button"
          data-testid="restore-all-dismissed-btn"
          :disabled="reviewStore.actionLoading"
          @click="handleRestoreAllDismissed"
          class="px-3 py-1.5 rounded-full border border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface text-xs font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition disabled:opacity-50">
          Restore all hidden
        </button>

        <button
          type="button"
          data-testid="refresh-review-scan-btn"
          :disabled="reviewStore.loading"
          @click="reviewStore.loadFindings()"
          class="px-3.5 py-1.5 rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 text-xs font-semibold hover:opacity-90 transition shadow-xs disabled:opacity-50">
          {{ reviewStore.loading ? 'Scanning...' : 'Refresh Scan' }}
        </button>
      </div>
    </div>

    <!-- Workspace Overview & Severity Strip -->
    <section
      data-testid="review-summary-cards"
      aria-label="Review overview summary"
      class="rounded-2xl border border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface p-4 shadow-xs space-y-3">
      <div class="flex flex-wrap items-center justify-between gap-2 text-xs">
        <div class="flex flex-wrap items-center gap-2">
          <span class="font-semibold text-slate-700 dark:text-slate-200">
            Scanned {{ reviewStore.summary.scanned_transactions_count }} ledger transactions &amp; {{ reviewStore.summary.scanned_staging_count }} queued items
          </span>
          <span class="text-slate-300 dark:text-slate-700">&middot;</span>
          <span
            v-if="(reviewStore.summary.by_severity?.integrity || 0) > 0"
            class="px-2 py-0.5 rounded-full text-[11px] font-mono font-semibold bg-rose-100 text-rose-800 dark:bg-rose-950/70 dark:text-rose-300">
            {{ reviewStore.summary.by_severity.integrity }} integrity check{{ reviewStore.summary.by_severity.integrity === 1 ? '' : 's' }}
          </span>
          <span class="px-2 py-0.5 rounded-full text-[11px] font-mono font-semibold bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300">
            {{ reviewStore.summary.by_severity?.review || 0 }} need review
          </span>
          <span class="px-2 py-0.5 rounded-full text-[11px] font-mono font-semibold bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300">
            {{ reviewStore.summary.by_severity?.suggestion || 0 }} suggestion{{ (reviewStore.summary.by_severity?.suggestion || 0) === 1 ? '' : 's' }}
          </span>
        </div>

        <div v-if="reviewStore.report" class="text-[11px] font-mono text-slate-500 dark:text-slate-400">
          Confidence: Cat={{ reviewStore.report.confidence_settings.category }}, Acc={{ reviewStore.report.confidence_settings.account }} &middot; TZ={{ reviewStore.report.app_timezone }}
        </div>
      </div>

      <!-- Category Filter Cards -->
      <div data-testid="review-category-cards" class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
        <button
          v-for="catOpt in categoryCardOptions"
          :key="catOpt.value"
          type="button"
          :data-testid="`review-cat-card-${catOpt.value}`"
          :aria-pressed="reviewStore.selectedFindingType === catOpt.value"
          @click="selectCategoryCard(catOpt.value)"
          class="p-2.5 rounded-xl border text-left transition flex flex-col justify-between gap-1"
          :class="reviewStore.selectedFindingType === catOpt.value
            ? 'border-indigo-500 bg-indigo-50/70 dark:bg-indigo-950/40 text-indigo-900 dark:text-indigo-100 shadow-xs'
            : 'border-brand-border dark:border-brand-darkborder bg-white/70 dark:bg-slate-900/40 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800/60'">
          <div class="text-[11px] font-semibold leading-tight">{{ catOpt.label }}</div>
          <div class="flex items-center justify-between">
            <span class="text-base font-mono font-bold">{{ catOpt.count }}</span>
            <span
              v-if="catOpt.value === 'integrity_issue' && catOpt.count > 0"
              class="w-2 h-2 rounded-full bg-rose-500"></span>
          </div>
        </button>
      </div>
    </section>

    <!-- Search & Filter Controls -->
    <section
      data-testid="review-filters-bar"
      aria-label="Filter review findings"
      class="rounded-2xl border border-brand-border dark:border-brand-darkborder bg-slate-100/80 dark:bg-slate-900/60 p-3.5 space-y-3">
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-2.5 items-end text-xs">
        <div class="lg:col-span-2">
          <label class="block text-[10px] font-mono uppercase font-semibold text-slate-500 mb-1">
            Search merchant, notes, or evidence
          </label>
          <input
            v-model="reviewStore.searchQuery"
            type="search"
            data-testid="review-search-input"
            placeholder="e.g. Tesco, duplicate, transfer..."
            @input="debouncedReload"
            class="w-full rounded-xl border border-brand-border dark:border-brand-darkborder bg-white dark:bg-brand-darksurface px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none focus:border-slate-400" />
        </div>

        <div>
          <label class="block text-[10px] font-mono uppercase font-semibold text-slate-500 mb-1">
            Finding Type
          </label>
          <select
            v-model="reviewStore.selectedFindingType"
            data-testid="review-type-select"
            @change="reviewStore.loadFindings()"
            class="w-full rounded-xl border border-brand-border dark:border-brand-darkborder bg-white dark:bg-brand-darksurface px-2.5 py-2 text-xs text-slate-900 dark:text-white focus:outline-none">
            <option value="all">All types</option>
            <option v-for="opt in findingTypeOptions" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </option>
          </select>
        </div>

        <div>
          <label class="block text-[10px] font-mono uppercase font-semibold text-slate-500 mb-1">
            Severity
          </label>
          <select
            v-model="reviewStore.selectedSeverity"
            data-testid="review-severity-select"
            @change="reviewStore.loadFindings()"
            class="w-full rounded-xl border border-brand-border dark:border-brand-darkborder bg-white dark:bg-brand-darksurface px-2.5 py-2 text-xs text-slate-900 dark:text-white focus:outline-none">
            <option value="all">All levels</option>
            <option value="integrity">Integrity checks</option>
            <option value="review">Needs review</option>
            <option value="suggestion">Suggestions</option>
          </select>
        </div>

        <div>
          <label class="block text-[10px] font-mono uppercase font-semibold text-slate-500 mb-1">
            Account
          </label>
          <select
            v-model="reviewStore.selectedAccountFilter"
            data-testid="review-account-select"
            @change="reviewStore.loadFindings()"
            class="w-full rounded-xl border border-brand-border dark:border-brand-darkborder bg-white dark:bg-brand-darksurface px-2.5 py-2 text-xs text-slate-900 dark:text-white focus:outline-none">
            <option value="">All accounts</option>
            <option value="unassigned">Unassigned</option>
            <option v-for="acc in allAccounts" :key="acc.id" :value="String(acc.id)">
              {{ acc.name }}{{ acc.is_active === false ? ' (Archived)' : '' }}
            </option>
          </select>
        </div>

        <div>
          <label class="block text-[10px] font-mono uppercase font-semibold text-slate-500 mb-1">
            Category
          </label>
          <select
            v-model="reviewStore.selectedCategoryFilter"
            data-testid="review-category-select"
            @change="reviewStore.loadFindings()"
            class="w-full rounded-xl border border-brand-border dark:border-brand-darkborder bg-white dark:bg-brand-darksurface px-2.5 py-2 text-xs text-slate-900 dark:text-white focus:outline-none">
            <option value="">All categories</option>
            <option value="uncategorized">Uncategorised</option>
            <option v-for="cat in allCategories" :key="cat.id" :value="String(cat.id)">
              {{ cat.name }}{{ cat.is_active === false ? ' (Archived)' : '' }}
            </option>
          </select>
        </div>
      </div>

      <div class="flex flex-wrap items-center justify-between gap-2 text-xs">
        <div class="flex flex-wrap items-center gap-2">
          <span class="text-[11px] font-mono uppercase text-slate-500">Date window:</span>
          <input
            v-model="reviewStore.startDate"
            type="date"
            data-testid="review-start-date"
            @change="reviewStore.loadFindings()"
            class="rounded-lg border border-brand-border dark:border-brand-darkborder bg-white dark:bg-brand-darksurface px-2.5 py-1 text-xs text-slate-900 dark:text-white" />
          <span class="text-slate-400">to</span>
          <input
            v-model="reviewStore.endDate"
            type="date"
            data-testid="review-end-date"
            @change="reviewStore.loadFindings()"
            class="rounded-lg border border-brand-border dark:border-brand-darkborder bg-white dark:bg-brand-darksurface px-2.5 py-1 text-xs text-slate-900 dark:text-white" />
        </div>

        <button
          v-if="hasActiveFilters"
          type="button"
          data-testid="review-reset-filters-btn"
          @click="handleResetFilters"
          class="px-3 py-1 rounded-full border border-brand-border dark:border-brand-darkborder bg-white dark:bg-brand-darksurface text-xs font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800 transition">
          Reset filters
        </button>
      </div>
    </section>

    <!-- Error Banner -->
    <div
      v-if="reviewStore.error"
      role="alert"
      class="p-3.5 rounded-xl border border-rose-200 dark:border-rose-900 bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 text-xs flex items-center justify-between">
      <span>{{ reviewStore.error }}</span>
      <button type="button" @click="reviewStore.error = null" class="font-bold px-2">&times;</button>
    </div>

    <!-- Loading State -->
    <div
      v-if="reviewStore.loading && !reviewStore.report"
      data-testid="review-loading-state"
      role="status"
      class="rounded-2xl border border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface p-10 text-center space-y-2">
      <div class="inline-block w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin"></div>
      <p class="text-xs font-semibold text-slate-700 dark:text-slate-200">Scanning workspace transactions and queue...</p>
    </div>

    <!-- Empty State -->
    <div
      v-else-if="reviewStore.findings.length === 0"
      data-testid="review-empty-state"
      class="rounded-2xl border border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface p-12 text-center space-y-3">
      <div class="w-10 h-10 rounded-full bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 mx-auto flex items-center justify-center font-bold">
        ✓
      </div>
      <template v-if="hasActiveFilters">
        <p class="text-sm font-bold text-slate-900 dark:text-white">No review findings match your current filters</p>
        <p class="text-xs text-slate-500 dark:text-slate-400">Try clearing one or more filters to view other items in this workspace.</p>
        <button
          type="button"
          @click="handleResetFilters"
          class="px-4 py-1.5 rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 text-xs font-semibold hover:opacity-90 transition">
          Clear Filters
        </button>
      </template>
      <template v-else>
        <p class="text-sm font-bold text-slate-900 dark:text-white">Your workspace looks clean</p>
        <p class="text-xs text-slate-500 dark:text-slate-400 max-w-md mx-auto">
          No uncategorised transactions, unassigned accounts, probable duplicates, unpaired transfers, archived link issues, or integrity gaps were detected.
        </p>
      </template>
    </div>

    <!-- Master-Detail Review Split View -->
    <div v-else class="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">

      <!-- Left: Findings List -->
      <div
        data-testid="review-findings-list"
        class="lg:col-span-5 space-y-2 max-h-[680px] overflow-y-auto pr-0.5">
        <button
          v-for="item in reviewStore.findings"
          :key="item.id"
          type="button"
          :data-testid="`review-finding-item-${item.id}`"
          :aria-pressed="reviewStore.selectedFinding?.id === item.id"
          @click="selectFinding(item)"
          class="w-full text-left p-3.5 rounded-xl border transition space-y-1.5"
          :class="reviewStore.selectedFinding?.id === item.id
            ? 'border-indigo-500 bg-indigo-50/60 dark:bg-indigo-950/30 shadow-xs'
            : 'border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface hover:bg-slate-50 dark:hover:bg-slate-800/40'">
          <div class="flex items-center justify-between gap-2">
            <div class="flex items-center gap-1.5 flex-wrap">
              <span class="px-2 py-0.5 rounded-md text-[10px] font-mono uppercase font-semibold" :class="severityBadgeClass(item.severity)">
                {{ severityLabel(item.severity) }}
              </span>
              <span class="text-[10px] font-mono text-slate-500 dark:text-slate-400">
                {{ findingTypeLabel(item.finding_type) }}
              </span>
              <span v-if="item.is_dismissed" class="px-1.5 py-0.5 rounded text-[10px] bg-slate-200 dark:bg-slate-800 text-slate-600 dark:text-slate-400">
                Hidden
              </span>
            </div>
            <span v-if="item.formatted_amount" class="text-xs font-mono font-bold text-slate-900 dark:text-white shrink-0">
              {{ item.formatted_amount }}
            </span>
          </div>

          <div class="text-xs font-bold text-slate-900 dark:text-white line-clamp-1">
            {{ item.title }}
          </div>
          <div class="text-[11px] text-slate-500 dark:text-slate-400 line-clamp-2">
            {{ item.summary }}
          </div>
          <div class="flex items-center justify-between text-[10px] font-mono text-slate-400 pt-0.5">
            <span>{{ item.date || 'No date' }}</span>
            <span>{{ item.account_name || 'Unassigned' }}</span>
          </div>
        </button>
      </div>

      <!-- Right: Detail Inspection & Safe Actions Panel -->
      <div
        v-if="reviewStore.selectedFinding"
        data-testid="review-detail-panel"
        class="lg:col-span-7 rounded-2xl border border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface p-5 shadow-xs space-y-4">

        <!-- Detail Header -->
        <div class="flex flex-wrap items-start justify-between gap-3 pb-3 border-b border-brand-border dark:border-brand-darkborder">
          <div class="space-y-1">
            <div class="flex flex-wrap items-center gap-2">
              <span class="px-2 py-0.5 rounded-md text-[10px] font-mono uppercase font-semibold" :class="severityBadgeClass(reviewStore.selectedFinding.severity)">
                {{ severityLabel(reviewStore.selectedFinding.severity) }}
              </span>
              <span class="px-2 py-0.5 rounded-md text-[10px] font-mono bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                {{ findingTypeLabel(reviewStore.selectedFinding.finding_type) }}
              </span>
              <span class="text-[10px] font-mono text-slate-400">
                Confidence: {{ reviewStore.selectedFinding.confidence }}
              </span>
            </div>
            <h2 class="text-sm font-bold text-slate-900 dark:text-white">
              {{ reviewStore.selectedFinding.title }}
            </h2>
            <p class="text-xs text-slate-500 dark:text-slate-400">
              {{ reviewStore.selectedFinding.summary }}
            </p>
          </div>

          <!-- Reversible Hide / Restore button -->
          <div class="shrink-0">
            <button
              v-if="reviewStore.selectedFinding.can_dismiss && !reviewStore.selectedFinding.is_dismissed"
              type="button"
              data-testid="review-dismiss-btn"
              :disabled="reviewStore.actionLoading"
              @click="reviewStore.dismissFinding(reviewStore.selectedFinding.id)"
              class="px-3 py-1.5 rounded-full border border-brand-border dark:border-brand-darkborder text-xs font-semibold text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition disabled:opacity-50"
              title="Reversibly hide this suggestion for this workspace">
              Hide suggestion
            </button>
            <button
              v-else-if="reviewStore.selectedFinding.is_dismissed"
              type="button"
              data-testid="review-restore-btn"
              :disabled="reviewStore.actionLoading"
              @click="reviewStore.restoreDismissed(reviewStore.selectedFinding.id)"
              class="px-3 py-1.5 rounded-full border border-indigo-300 dark:border-indigo-700 bg-indigo-50 dark:bg-indigo-950/60 text-xs font-semibold text-indigo-700 dark:text-indigo-200 hover:opacity-90 transition disabled:opacity-50">
              Restore suggestion
            </button>
            <span
              v-else
              class="text-[10px] font-mono text-slate-400">
              Cannot hide integrity check
            </span>
          </div>
        </div>

        <!-- Record Metadata Grid -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 rounded-xl bg-slate-50/70 dark:bg-slate-900/50 border border-brand-border/70 dark:border-brand-darkborder p-3 text-xs">
          <div>
            <div class="text-[10px] font-mono uppercase text-slate-400">Date</div>
            <div class="font-mono font-semibold text-slate-900 dark:text-white mt-0.5">{{ reviewStore.selectedFinding.date || 'Not recorded' }}</div>
          </div>
          <div>
            <div class="text-[10px] font-mono uppercase text-slate-400">Amount</div>
            <div class="font-mono font-semibold text-slate-900 dark:text-white mt-0.5">{{ reviewStore.selectedFinding.formatted_amount || 'N/A' }}</div>
          </div>
          <div>
            <div class="text-[10px] font-mono uppercase text-slate-400">Account</div>
            <div class="font-medium text-slate-900 dark:text-white mt-0.5 truncate">{{ reviewStore.selectedFinding.account_name || 'Unassigned' }}</div>
          </div>
          <div>
            <div class="text-[10px] font-mono uppercase text-slate-400">Source</div>
            <div class="font-mono text-slate-700 dark:text-slate-300 mt-0.5 capitalize">{{ reviewStore.selectedFinding.source }} ({{ reviewStore.selectedFinding.subtype }})</div>
          </div>
        </div>

        <!-- Comparison Side-by-Side (Duplicates & Transfers) -->
        <div v-if="reviewStore.selectedFinding.comparison" class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
          <div
            v-if="comparisonLeft"
            class="p-3 rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50/50 dark:bg-slate-900/40 space-y-1">
            <div class="flex items-center justify-between text-[11px] font-semibold text-slate-600 dark:text-slate-300">
              <span>{{ comparisonLeftTitle }}</span>
              <span class="font-mono font-bold">{{ comparisonLeft.formatted_amount }}</span>
            </div>
            <div class="font-bold text-slate-900 dark:text-white">{{ comparisonLeft.merchant || 'Merchant not recorded' }}</div>
            <div class="text-[11px] text-slate-500">
              {{ comparisonLeft.date }} &middot; {{ comparisonLeft.account_name || 'Unassigned' }}
            </div>
            <div v-if="comparisonLeft.source_filename" class="text-[10px] text-slate-400 truncate">
              File: {{ comparisonLeft.source_filename }}
            </div>
          </div>

          <div
            v-if="comparisonRight"
            class="p-3 rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50/50 dark:bg-slate-900/40 space-y-1">
            <div class="flex items-center justify-between text-[11px] font-semibold text-slate-600 dark:text-slate-300">
              <span>{{ comparisonRightTitle }}</span>
              <span class="font-mono font-bold">{{ comparisonRight.formatted_amount }}</span>
            </div>
            <div class="font-bold text-slate-900 dark:text-white">{{ comparisonRight.merchant || 'Merchant not recorded' }}</div>
            <div class="text-[11px] text-slate-500">
              {{ comparisonRight.date }} &middot; {{ comparisonRight.account_name || 'Unassigned' }}
            </div>
            <div v-if="comparisonRight.source_filename" class="text-[10px] text-slate-400 truncate">
              File: {{ comparisonRight.source_filename }}
            </div>
          </div>
        </div>

        <!-- Explainable Evidence List -->
        <div class="space-y-1.5">
          <div class="text-[11px] font-mono uppercase font-semibold text-slate-500">
            Why this was flagged
          </div>
          <ul data-testid="review-detail-reasons" class="space-y-1 text-xs text-slate-700 dark:text-slate-300">
            <li
              v-for="(reason, idx) in reviewStore.selectedFinding.reasons"
              :key="idx"
              class="flex items-start gap-2">
              <span class="text-indigo-500 mt-0.5">&bull;</span>
              <span>{{ reason }}</span>
            </li>
          </ul>
        </div>

        <!-- Safe Explicit Correction Controls -->
        <div class="rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50/60 dark:bg-slate-900/50 p-4 space-y-3">
          <div class="text-[11px] font-mono uppercase font-semibold text-slate-500">
            Safe Review Actions
          </div>

          <!-- Assign Category (Uncategorised or Archived Category) -->
          <div
            v-if="canAssignCategory"
            class="space-y-2">
            <div v-if="reviewStore.selectedFinding.suggested_category_name" class="text-[11px] text-indigo-700 dark:text-indigo-300 font-medium">
              Advisory suggestion from approved history: <strong>{{ reviewStore.selectedFinding.suggested_category_name }}</strong> (not applied until you click Assign Category)
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <select
                v-model="targetCategoryId"
                data-testid="review-assign-category-select"
                class="flex-1 min-w-44 rounded-xl border border-brand-border dark:border-brand-darkborder bg-white dark:bg-brand-darksurface px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none">
                <option :value="null" disabled>
                  Select an active {{ findingCategoryPurpose || 'matching' }} category...
                </option>
                <option v-for="cat in assignableCategories" :key="cat.id" :value="cat.id">
                  {{ cat.name }}
                </option>
              </select>
              <button
                type="button"
                data-testid="review-apply-category-btn"
                :disabled="!targetCategoryId || reviewStore.actionLoading"
                @click="applyCategoryFix"
                class="px-4 py-2 rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 text-xs font-semibold hover:opacity-90 transition disabled:opacity-50">
                Assign Category
              </button>
            </div>
          </div>

          <!-- Assign Account (Unassigned or Archived Account) -->
          <div
            v-if="canAssignAccount"
            class="flex flex-wrap items-center gap-2">
            <select
              v-model="targetAccountId"
              data-testid="review-assign-account-select"
              class="flex-1 min-w-44 rounded-xl border border-brand-border dark:border-brand-darkborder bg-white dark:bg-brand-darksurface px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none">
              <option :value="null" disabled>Select an active account...</option>
              <option v-for="acc in activeAccounts" :key="acc.id" :value="acc.id">
                {{ acc.name }} ({{ acc.currency }})
              </option>
            </select>
            <button
              type="button"
              data-testid="review-apply-account-btn"
              :disabled="!targetAccountId || reviewStore.actionLoading"
              @click="applyAccountFix"
              class="px-4 py-2 rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 text-xs font-semibold hover:opacity-90 transition disabled:opacity-50">
              Assign Account
            </button>
          </div>

          <!-- Action Explanation + Preserved Links & Confirmed Destructive/Merge Actions -->
          <p v-if="reviewStore.selectedFinding.action_explanation" class="text-[11px] text-slate-600 dark:text-slate-400">
            {{ reviewStore.selectedFinding.action_explanation }}
          </p>

          <div class="flex flex-wrap items-center gap-2 pt-1">
            <!-- Confirm Staging Duplicate Exclusion -->
            <button
              v-if="reviewStore.selectedFinding.suggested_action === 'exclude_duplicate_staging' && reviewStore.selectedFinding.staging_id"
              type="button"
              data-testid="review-confirm-duplicate-btn"
              :disabled="reviewStore.actionLoading"
              @click="openConfirmModal('exclude_staging_dup')"
              class="px-3.5 py-1.5 rounded-full bg-rose-600 text-white hover:bg-rose-500 text-xs font-semibold transition disabled:opacity-50">
              Exclude Staging Candidate...
            </button>

            <!-- Confirm Ledger Duplicate Soft-Deletion -->
            <button
              v-if="reviewStore.selectedFinding.suggested_action === 'delete_duplicate_ledger' && reviewStore.selectedFinding.transaction_id"
              type="button"
              data-testid="review-delete-ledger-dup-btn"
              :disabled="reviewStore.actionLoading"
              @click="openConfirmModal('delete_ledger_dup')"
              class="px-3.5 py-1.5 rounded-full bg-rose-600 text-white hover:bg-rose-500 text-xs font-semibold transition disabled:opacity-50">
              Move Duplicate (#{{ reviewStore.selectedFinding.transaction_id }}) to Recently Deleted...
            </button>

            <!-- Confirm Transfer Pairing -->
            <button
              v-if="reviewStore.selectedFinding.suggested_action === 'pair_transfer' && reviewStore.selectedFinding.comparison?.source_record && reviewStore.selectedFinding.comparison?.destination_record"
              type="button"
              data-testid="review-pair-transfer-btn"
              :disabled="reviewStore.actionLoading"
              @click="openConfirmModal('pair_transfer')"
              class="px-3.5 py-1.5 rounded-full bg-indigo-600 text-white hover:bg-indigo-500 text-xs font-semibold transition disabled:opacity-50">
              Pair as Dual-Account Transfer...
            </button>

            <!-- Direct Preserved-Filter Links -->
            <router-link
              v-if="reviewStore.selectedFinding.ledger_url"
              :to="reviewStore.selectedFinding.ledger_url"
              data-testid="review-open-ledger-link"
              class="px-3.5 py-1.5 rounded-full border border-brand-border dark:border-brand-darkborder bg-white dark:bg-brand-darksurface text-xs font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition">
              Open in Ledger &rarr;
            </router-link>

            <router-link
              v-if="reviewStore.selectedFinding.queue_url"
              :to="reviewStore.selectedFinding.queue_url"
              data-testid="review-open-queue-link"
              class="px-3.5 py-1.5 rounded-full border border-brand-border dark:border-brand-darkborder bg-white dark:bg-brand-darksurface text-xs font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition">
              Open in Queue &rarr;
            </router-link>
          </div>
        </div>
      </div>
    </div>

    <!-- Confirmation Dialog for Material Alterations (Exclude, Delete, Merge Transfer) -->
    <div
      v-if="pendingConfirmAction"
      class="fixed inset-0 z-50 bg-slate-950/40 backdrop-blur-sm flex items-center justify-center p-4"
      @click.self="pendingConfirmAction = null">
      <section
        role="dialog"
        aria-modal="true"
        data-testid="review-confirm-modal"
        class="bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4">
        <h3 class="text-sm font-bold text-slate-900 dark:text-white">
          {{ confirmModalTitle }}
        </h3>
        <p class="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
          {{ confirmModalDescription }}
        </p>
        <div class="flex items-center justify-end gap-2.5 pt-2 border-t border-brand-border dark:border-brand-darkborder">
          <button
            type="button"
            @click="pendingConfirmAction = null"
            class="px-4 py-1.5 rounded-full border border-brand-border dark:border-brand-darkborder text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition">
            Cancel
          </button>
          <button
            type="button"
            data-testid="review-confirm-execute-btn"
            :disabled="reviewStore.actionLoading"
            @click="executeConfirmedAction"
            class="px-4 py-1.5 rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 text-xs font-semibold hover:opacity-90 transition disabled:opacity-50">
            {{ reviewStore.actionLoading ? 'Applying...' : 'Confirm & Apply' }}
          </button>
        </div>
      </section>
    </div>

    <!-- Floating Undo Toast (Reuses Existing Ledger Undo Pattern) -->
    <div
      v-if="txStore.undoToastMessage"
      role="status"
      data-testid="review-undo-toast"
      class="fixed bottom-5 right-5 z-50 flex items-center gap-3 px-4 py-3 rounded-xl bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 shadow-2xl border border-slate-700 dark:border-slate-300 text-xs">
      <span>{{ txStore.undoToastMessage }}</span>
      <button
        type="button"
        @click="handleUndoDelete"
        class="px-2.5 py-1 rounded-lg bg-emerald-500 text-white font-semibold hover:bg-emerald-400 transition">
        Undo
      </button>
      <button type="button" @click="txStore.dismissUndoToast()" class="opacity-70 hover:opacity-100 px-1">&times;</button>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { api } from '../api/client';
import { useReviewStore } from '../stores/review';
import { useTransactionsStore } from '../stores/transactions';
import { useProfilesStore } from '../stores/profiles';
import { filterCategoriesForTransactionType, isCategoryCompatibleWithTransaction } from '../utils/categoryPurpose';
import type { Account, Category, DataQualityFinding, DataQualityFindingType, DataQualitySeverity } from '../types';

const reviewStore = useReviewStore();
const txStore = useTransactionsStore();
const profilesStore = useProfilesStore();

const workspaceAccounts = ref<Account[]>([]);
const workspaceCategories = ref<Category[]>([]);
const targetCategoryId = ref<number | null>(null);
const targetAccountId = ref<number | null>(null);
const pendingConfirmAction = ref<'exclude_staging_dup' | 'delete_ledger_dup' | 'pair_transfer' | null>(null);

const findingTypeOptions: Array<{ value: DataQualityFindingType; label: string }> = [
  { value: 'uncategorised', label: 'Uncategorised' },
  { value: 'unassigned_account', label: 'Unassigned Account' },
  { value: 'potential_duplicate', label: 'Potential Duplicates' },
  { value: 'possible_transfer', label: 'Possible Transfers' },
  { value: 'uncertain_import', label: 'Uncertain Imports' },
  { value: 'archived_reference', label: 'Archived References' },
  { value: 'integrity_issue', label: 'Integrity Checks' },
];

const categoryCardOptions = computed(() => [
  { value: 'all' as const, label: 'All Findings', count: reviewStore.summary.total_active || 0 },
  ...findingTypeOptions.map((opt) => ({
    value: opt.value,
    label: opt.label,
    count: reviewStore.summary.by_type?.[opt.value] || 0,
  })),
]);

const allAccounts = computed(() => workspaceAccounts.value);
const activeAccounts = computed(() => workspaceAccounts.value.filter((a) => a.is_active !== false));
const allCategories = computed(() => workspaceCategories.value);
const activeCategories = computed(() => workspaceCategories.value.filter((c) => c.is_active !== false));
const findingCategoryPurpose = computed(() => {
  const f = reviewStore.selectedFinding;
  if (!f) return null;
  if (f.expected_category_type) return f.expected_category_type;
  if (f.transaction_type === 'income' || f.transaction_type === 'expense') return f.transaction_type;
  return 'expense';
});
const assignableCategories = computed(() =>
  filterCategoriesForTransactionType(workspaceCategories.value, findingCategoryPurpose.value)
);

const hasActiveFilters = computed(() =>
  Boolean(
    reviewStore.selectedFindingType !== 'all' ||
      reviewStore.selectedSeverity !== 'all' ||
      reviewStore.searchQuery.trim() ||
      reviewStore.selectedAccountFilter ||
      reviewStore.selectedCategoryFilter ||
      reviewStore.startDate ||
      reviewStore.endDate
  )
);

const canAssignCategory = computed(() => {
  const f = reviewStore.selectedFinding;
  if (!f || !f.transaction_id) return false;
  return f.suggested_action === 'assign_category' || f.suggested_action === 'reassign_category';
});

const canAssignAccount = computed(() => {
  const f = reviewStore.selectedFinding;
  if (!f || !f.transaction_id) return false;
  return f.suggested_action === 'assign_account';
});

const comparisonLeft = computed(() => {
  const comp = reviewStore.selectedFinding?.comparison;
  if (!comp) return null;
  return comp.record_a || comp.source_record || null;
});

const comparisonRight = computed(() => {
  const comp = reviewStore.selectedFinding?.comparison;
  if (!comp) return null;
  return comp.record_b || comp.destination_record || null;
});

const comparisonLeftTitle = computed(() => {
  const comp = reviewStore.selectedFinding?.comparison;
  if (!comp) return '';
  if (comp.source_record) return `Outflow (${comp.source_record.kind === 'ledger' ? 'Ledger #' : 'Staging #'}${comp.source_record.id})`;
  return comp.record_a?.kind === 'staging' ? `Candidate in Queue (#${comp.record_a.id})` : `Ledger #${comp.record_a?.id}`;
});

const comparisonRightTitle = computed(() => {
  const comp = reviewStore.selectedFinding?.comparison;
  if (!comp) return '';
  if (comp.destination_record) return `Inflow (${comp.destination_record.kind === 'ledger' ? 'Ledger #' : 'Staging #'}${comp.destination_record.id})`;
  return comp.record_b?.kind === 'staging' ? `Queue Item (#${comp.record_b.id})` : `Ledger #${comp.record_b?.id}`;
});

const confirmModalTitle = computed(() => {
  if (pendingConfirmAction.value === 'exclude_staging_dup') return 'Confirm Staging Duplicate Exclusion';
  if (pendingConfirmAction.value === 'delete_ledger_dup') return 'Move Duplicate Entry to Recently Deleted';
  return 'Confirm Dual-Account Transfer Pairing';
});

const confirmModalDescription = computed(() => {
  const f = reviewStore.selectedFinding;
  if (!f) return '';
  if (pendingConfirmAction.value === 'exclude_staging_dup') {
    return `This will discard Staging #${f.staging_id} from the review queue as a duplicate while preserving source files needed by pending siblings.`;
  }
  if (pendingConfirmAction.value === 'delete_ledger_dup') {
    return `This will move Ledger #${f.transaction_id} (${f.formatted_amount || ''}) to Recently Deleted. You can undo immediately or restore it later from the Ledger.`;
  }
  return f.action_explanation || 'This will convert the paired entries into a single dual-account Transfer with stored provenance so you can unpair later if needed.';
});

watch(
  () => reviewStore.selectedFinding,
  (f) => {
    const sugId = f?.suggested_category_id || null;
    const purpose = f?.expected_category_type || f?.transaction_type || 'expense';
    targetCategoryId.value =
      sugId && isCategoryCompatibleWithTransaction(activeCategories.value, sugId, purpose)
        ? sugId
        : null;
    targetAccountId.value = null;
  },
  { immediate: true }
);

function selectFinding(item: DataQualityFinding) {
  reviewStore.selectedFindingId = item.id;
}

function selectCategoryCard(val: DataQualityFindingType | 'all') {
  reviewStore.selectedFindingType = val;
  reviewStore.loadFindings();
}

let searchTimer: any = null;
function debouncedReload() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    reviewStore.loadFindings();
  }, 220);
}

function toggleIncludeDismissed() {
  reviewStore.includeDismissed = !reviewStore.includeDismissed;
  reviewStore.loadFindings();
}

function handleResetFilters() {
  reviewStore.resetFilters();
  reviewStore.loadFindings();
}

async function applyCategoryFix() {
  const f = reviewStore.selectedFinding;
  if (!f?.transaction_id || !targetCategoryId.value) return;
  await reviewStore.assignCategory(f.transaction_id, targetCategoryId.value);
}

async function applyAccountFix() {
  const f = reviewStore.selectedFinding;
  if (!f?.transaction_id || !targetAccountId.value) return;
  await reviewStore.assignAccount(f.transaction_id, targetAccountId.value);
}

function openConfirmModal(action: 'exclude_staging_dup' | 'delete_ledger_dup' | 'pair_transfer') {
  pendingConfirmAction.value = action;
}

async function executeConfirmedAction() {
  const f = reviewStore.selectedFinding;
  const action = pendingConfirmAction.value;
  if (!f || !action) return;

  try {
    if (action === 'exclude_staging_dup' && f.staging_id) {
      await reviewStore.confirmExcludeStagingDuplicate(f.staging_id, f.id);
    } else if (action === 'delete_ledger_dup' && f.transaction_id) {
      await reviewStore.confirmSoftDeleteLedgerDuplicate(f.transaction_id);
    } else if (action === 'pair_transfer' && f.comparison?.source_record && f.comparison?.destination_record) {
      await reviewStore.confirmPairTransfer(
        f.comparison.source_record.id,
        f.comparison.source_record.kind,
        f.comparison.destination_record.id,
        f.comparison.destination_record.kind,
        f.id
      );
    }
    pendingConfirmAction.value = null;
  } catch {
    pendingConfirmAction.value = null;
  }
}

async function handleRestoreAllDismissed() {
  await reviewStore.restoreDismissed(undefined, true);
}

async function handleUndoDelete() {
  await txStore.undoLastDelete();
  await reviewStore.loadFindings();
}

function severityLabel(sev: DataQualitySeverity): string {
  if (sev === 'integrity') return 'Integrity check';
  if (sev === 'review') return 'Needs review';
  return 'Suggestion';
}

function severityBadgeClass(sev: DataQualitySeverity): string {
  if (sev === 'integrity') {
    return 'bg-rose-100 text-rose-800 dark:bg-rose-950/70 dark:text-rose-300';
  }
  if (sev === 'review') {
    return 'bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300';
  }
  return 'bg-slate-200/80 text-slate-700 dark:bg-slate-800 dark:text-slate-300';
}

function findingTypeLabel(t: DataQualityFindingType): string {
  const found = findingTypeOptions.find((o) => o.value === t);
  return found ? found.label : t;
}

async function loadReferenceLists() {
  try {
    const [accs, cats] = await Promise.all([api.getAccounts(true), api.getCategories(true)]);
    workspaceAccounts.value = accs;
    workspaceCategories.value = cats;
  } catch {
    // ignore background reference fetch error
  }
}

watch(
  () => profilesStore.activeProfile?.id,
  async () => {
    await loadReferenceLists();
  }
);

onMounted(async () => {
  await Promise.allSettled([
    reviewStore.loadFindings(),
    loadReferenceLists(),
  ]);
});
</script>
