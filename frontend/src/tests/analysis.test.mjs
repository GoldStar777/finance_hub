import { test, describe } from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC_DIR = path.resolve(__dirname, '..');

describe('Finance Hub Analysis Overhaul Contract Tests', () => {
  const routerContent = fs.readFileSync(path.join(SRC_DIR, 'router/index.ts'), 'utf-8');
  const headerContent = fs.readFileSync(path.join(SRC_DIR, 'components/CommandHeader.vue'), 'utf-8');
  const analysisViewContent = fs.readFileSync(path.join(SRC_DIR, 'views/AnalysisView.vue'), 'utf-8');
  const sharedToolbarContent = fs.readFileSync(path.join(SRC_DIR, 'components/SharedFilterToolbar.vue'), 'utf-8');
  const filtersStoreContent = fs.readFileSync(path.join(SRC_DIR, 'stores/filters.ts'), 'utf-8');
  const storeContent = fs.readFileSync(path.join(SRC_DIR, 'stores/analysis.ts'), 'utf-8');
  const typesContent = fs.readFileSync(path.join(SRC_DIR, 'types/index.ts'), 'utf-8');
  const clientContent = fs.readFileSync(path.join(SRC_DIR, 'api/client.ts'), 'utf-8');
  const combinedToolbarSurface = `${analysisViewContent}\n${sharedToolbarContent}\n${filtersStoreContent}`;

  test('1. Product structure and navigation', () => {
    assert.ok(headerContent.includes('to="/analysis"'), 'Header must contain link to /analysis');
    assert.ok(headerContent.includes('Analysis'), 'Header must display Analysis label');

    assert.ok(routerContent.includes("path: '/analysis'"), 'Router must define /analysis route');
    assert.ok(routerContent.includes("path: '/cashflow'"), 'Router must preserve /cashflow route');
    assert.ok(routerContent.includes("redirect: '/analysis?section=spending'"), '/cashflow must redirect to analysis spending section');
    assert.ok(routerContent.includes("path: '/spending'"), 'Router must define /spending route');

    assert.ok(analysisViewContent.includes("'overview'"), 'Analysis must have Overview section');
    assert.ok(analysisViewContent.includes("'spending'"), 'Analysis must have Spending section');
    assert.ok(analysisViewContent.includes("'networth'"), 'Analysis must have Balances & Net Worth section');
    assert.ok(analysisViewContent.includes("'investments'"), 'Analysis must have Investments section');
  });

  test('2. Persistent, usable sticky analysis toolbar and searchable multi-select filters', () => {
    // Sticky toolbar remains accessible while scrolling positioned below the global header (top-16)
    assert.ok(analysisViewContent.includes('data-testid="analysis-sticky-toolbar"'), 'Must render persistent sticky analysis toolbar');
    assert.ok(analysisViewContent.includes('sticky top-16'), 'Toolbar must be sticky below the global header (top-16)');

    // Mobile compact summary strip & collapsible controls
    assert.ok(analysisViewContent.includes('isMobileControlsExpanded'), 'Must support mobile controls expand/collapse');
    assert.ok(analysisViewContent.includes('activeSectionLabel'), 'Must display active section label on mobile');
    assert.ok(analysisViewContent.includes('shortRangeLabel'), 'Must display short range label on mobile');

    // Presets: Day, Week, Month, 3M, 6M, Year, 5Y, All, Custom
    const expectedPresets = ['day', 'week', 'month', '3m', '6m', 'year', '5y', 'all', 'custom'];
    for (const p of expectedPresets) {
      assert.ok(combinedToolbarSurface.includes(`value: '${p}'`), `Presets must include ${p}`);
    }

    // Group-by interval options
    assert.ok(combinedToolbarSurface.includes('Group by'), 'Toolbar must include Group by interval control');
    const expectedIntervals = ['day', 'week', 'month', 'quarter', 'year'];
    for (const intv of expectedIntervals) {
      assert.ok(combinedToolbarSurface.includes(`value: '${intv}'`), `Intervals must include ${intv}`);
    }

    // Previous/Next period navigation disabled at valid boundaries
    assert.ok(analysisViewContent.includes('navigatePeriod(-1)'), 'Must provide previous period navigation');
    assert.ok(analysisViewContent.includes('navigatePeriod(1)'), 'Must provide next period navigation');
    assert.ok(analysisViewContent.includes('can_navigate_previous'), 'Previous button must honor boundary');
    assert.ok(analysisViewContent.includes('can_navigate_next'), 'Next button must honor boundary');

    // Searchable multi-select Account filter
    assert.ok(combinedToolbarSurface.includes('data-testid="account-multiselect-trigger"'), 'Must provide multi-select account filter trigger');
    assert.ok(combinedToolbarSurface.includes('Search accounts...'), 'Account filter must be searchable');
    assert.ok(storeContent.includes('selectedAccountIds'), 'Store must track multi-select account IDs');
    assert.ok(storeContent.includes('toggleAccountFilter'), 'Store must support toggling multiple accounts');

    // Searchable multi-select Category filter (including Uncategorised)
    assert.ok(combinedToolbarSurface.includes('data-testid="category-multiselect-trigger"'), 'Must provide multi-select category filter trigger');
    assert.ok(combinedToolbarSurface.includes('Search categories...'), 'Category filter must be searchable');
    assert.ok(combinedToolbarSurface.includes('Uncategorised'), 'Category filter must include Uncategorised option');
    assert.ok(storeContent.includes('selectedCategoryIds'), 'Store must track multi-select category IDs');
    assert.ok(storeContent.includes('toggleCategoryFilter'), 'Store must support toggling multiple categories');

    // Active filter chips and one-click reset
    assert.ok(combinedToolbarSurface.includes('data-testid="active-filter-chips-bar"'), 'Must display active filter chips bar');
    assert.ok(combinedToolbarSurface.includes('data-testid="reset-all-filters-btn"'), 'Must provide one-click reset all filters button');
    assert.ok(storeContent.includes('activeFilterChips'), 'Store must compute removable filter chips');
    assert.ok(storeContent.includes('resetAllFilters'), 'Store must implement resetAllFilters action');
  });

  test('3. Spending Matrix and local profile-scoped CSV & XLSX exports via unified menu', () => {
    // Primary View: Category Spending Matrix by Period
    assert.ok(analysisViewContent.includes('Category Spending Matrix by Period'), 'Must render Category Spending Matrix as primary comparison view');
    assert.ok(analysisViewContent.includes('matrixPeriods'), 'Matrix table must use grouped periods as columns');
    assert.ok(analysisViewContent.includes('matrixRows'), 'Matrix table must use categories as rows');
    assert.ok(analysisViewContent.includes('sticky left-0'), 'Matrix table must have sticky category column');
    assert.ok(analysisViewContent.includes('sticky right-0'), 'Matrix table must have sticky row totals');
    assert.ok(analysisViewContent.includes('sticky bottom-0'), 'Matrix table must have sticky period totals footer');
    assert.ok(analysisViewContent.includes('getCellDrilldownUrl'), 'Matrix table cells must drill down to ledger');
    assert.ok(analysisViewContent.includes('getRowDrilldownUrl'), 'Matrix table row totals must drill down to ledger');
    assert.ok(analysisViewContent.includes('getColumnDrilldownUrl'), 'Matrix table column totals must drill down to ledger');
    assert.ok(analysisViewContent.includes('getGrandTotalDrilldownUrl'), 'Matrix table grand total must drill down to ledger');

    // Single unified Export menu triggers across all Analysis tables
    assert.ok(analysisViewContent.includes('data-testid="export-spending-matrix-menu-trigger"'), 'Spending matrix must have export menu trigger');
    assert.ok(analysisViewContent.includes('data-testid="export-overview-menu-trigger"'), 'Overview table must have export menu trigger');
    assert.ok(analysisViewContent.includes('data-testid="export-categories-menu-trigger"'), 'Categories table must have export menu trigger');
    assert.ok(analysisViewContent.includes('data-testid="export-networth-menu-trigger"'), 'Net worth table must have export menu trigger');
    assert.ok(analysisViewContent.includes('data-testid="export-investments-menu-trigger"'), 'Investments table must have export menu trigger');

    // CSV and XLSX export actions inside the dropdown menus
    assert.ok(analysisViewContent.includes('data-testid="export-spending-matrix-csv"'), 'Spending matrix must have CSV export option');
    assert.ok(analysisViewContent.includes('data-testid="export-spending-matrix-xlsx"'), 'Spending matrix must have XLSX export option');
    assert.ok(analysisViewContent.includes('data-testid="export-overview-csv"'), 'Overview cashflow table must have CSV export option');
    assert.ok(analysisViewContent.includes('data-testid="export-overview-xlsx"'), 'Overview cashflow table must have XLSX export option');
    assert.ok(analysisViewContent.includes('data-testid="export-networth-csv"'), 'Net worth table must have CSV export option');
    assert.ok(analysisViewContent.includes('data-testid="export-networth-xlsx"'), 'Net worth table must have XLSX export option');
    assert.ok(analysisViewContent.includes('data-testid="export-investments-csv"'), 'Investments table must have CSV export option');
    assert.ok(analysisViewContent.includes('data-testid="export-investments-xlsx"'), 'Investments table must have XLSX export option');

    // API client & store export support with X-Profile-ID header
    assert.ok(clientContent.includes('downloadAnalysisExport'), 'API client must implement downloadAnalysisExport');
    assert.ok(clientContent.includes('/analytics/export'), 'API client must call /analytics/export endpoint');
    assert.ok(storeContent.includes('exportReport'), 'Analysis store must expose exportReport action');
  });

  test('4. Redesigned Spending Trajectory Over Time', () => {
    // Keep Category Spending Mix (composition) and Spending Trajectory Over Time (temporal trend)
    assert.ok(analysisViewContent.includes('Category Spending Mix'), 'Must retain Category Spending Mix for composition');
    assert.ok(analysisViewContent.includes('donutChartData'), 'Must compute donut chart composition data');
    assert.ok(analysisViewContent.includes('Spending Trajectory Over Time'), 'Must retain Spending Trajectory Over Time for temporal changes');
    assert.ok(analysisViewContent.includes('spendingTrajectoryBars'), 'Must compute spending trajectory period bars data');
    assert.ok(analysisViewContent.includes('spendingTrajectoryStats'), 'Must compute trajectory summary stats banner');

    // Focused Category mode
    assert.ok(storeContent.includes('spendingFocusCategoryId'), 'Store must track spendingFocusCategoryId');
    assert.ok(storeContent.includes('setSpendingFocusCategory'), 'Store must expose setSpendingFocusCategory');
    assert.ok(analysisViewContent.includes('All Categories (Total Spend)'), 'Must allow viewing all categories total spend');

    // Redundant Allocation Waterfall chart removed
    assert.ok(!analysisViewContent.includes('Allocation Waterfall'), 'Redundant Allocation Waterfall chart must be removed');

    // Every visualization explicitly states the question it answers
    assert.ok(analysisViewContent.includes('Question answered:'), 'Visualizations must explicitly state what question they answer');
  });

  test('5. Balances & Net Worth enhancements (interactive plotting & newest period first)', () => {
    // Interactive account selection for Net Worth chart
    assert.ok(storeContent.includes('selectedBalanceAccountIds'), 'Store must track selectedBalanceAccountIds');
    assert.ok(storeContent.includes('toggleBalanceAccount'), 'Store must expose toggleBalanceAccount');
    assert.ok(analysisViewContent.includes('Plot Individual Accounts on Chart:'), 'Must provide UI control to plot individual accounts on net worth chart');
    assert.ok(analysisViewContent.includes('netWorthChartData.accountLines'), 'Net worth chart must render plotted account SVG lines');

    // Balances table ordered newest period first
    assert.ok(analysisViewContent.includes('sortedNetWorthSeries'), 'Net worth table must render sortedNetWorthSeries');
    assert.ok(analysisViewContent.includes('v-for="nw in sortedNetWorthSeries"'), 'Net worth table rows must iterate sortedNetWorthSeries');
  });

  test('6. Profile-isolated persistent Analysis preferences', () => {
    // Storage prefix and isolation
    assert.ok(storeContent.includes('finance_hub_analysis_prefs_'), 'Store must prefix analysis preferences with profile isolation key');
    assert.ok(storeContent.includes('loadSavedPreferences'), 'Store must implement loadSavedPreferences');
    assert.ok(storeContent.includes('savePreferences'), 'Store must implement savePreferences');
    assert.ok(storeContent.includes('initFromRouteOrPreferences'), 'Store must implement initFromRouteOrPreferences');

    // Reload preferences on profile switch
    assert.ok(storeContent.includes('reset'), 'Store must have reset function');
    assert.ok(analysisViewContent.includes('initFromRouteOrPreferences'), 'View must initialize from route or saved preferences on mount and route change');
  });

  test('5. Financial correctness & profile isolation safeguards', () => {
    // Transfers = £0 cash impact, adjustments separated
    assert.ok(analysisViewContent.includes('Transfer Impact'), 'Must explicitly highlight £0 transfer impact');
    assert.ok(analysisViewContent.includes('formatted_transfers_volume'), 'Must display transfers volume');
    assert.ok(analysisViewContent.includes('formatted_adjustments_net'), 'Must display separated reconciliation adjustments');

    // Pre-anchor inferred balances flagged
    assert.ok(analysisViewContent.includes('hasAnyInferredBalances'), 'Must detect pre-anchor inferred balances');
    assert.ok(analysisViewContent.includes('Inferred Pre-Anchor'), 'Must badge inferred pre-anchor periods');

    // Investments: carried-forward checkpoint labels, Unavailable gaps, and explicit non-IRR notice
    assert.ok(analysisViewContent.includes('Not IRR or Investment Returns'), 'Must explicitly disclaim IRR / investment returns');
    assert.ok(analysisViewContent.includes('Carried forward (from'), 'Must label carried-forward checkpoints with source date');
    assert.ok(analysisViewContent.includes('Unavailable'), 'Must show Unavailable for missing checkpoints');

    // Profile isolation in store reset
    assert.ok(storeContent.includes('selectedAccountIds.value = []'), 'Store reset must clear selectedAccountIds on profile switch');
    assert.ok(storeContent.includes('selectedCategoryIds.value = []'), 'Store reset must clear selectedCategoryIds on profile switch');
    assert.ok(typesContent.includes('AnalysisExportReportType'), 'Types must define AnalysisExportReportType');
  });
});
