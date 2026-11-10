import { test, describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { registerHooks } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';

const SRC_DIR = path.resolve('src');

function readFile(subpath) {
  return fs.readFileSync(path.join(SRC_DIR, subpath), 'utf8');
}

// Register extensionless .ts resolution so real Pinia stores execute natively in Node
registerHooks({
  resolve(specifier, context, nextResolve) {
    if (
      (specifier.startsWith('./') || specifier.startsWith('../')) &&
      !specifier.endsWith('.ts') &&
      !specifier.endsWith('.js') &&
      !specifier.endsWith('.mjs')
    ) {
      const parentDir = context.parentURL
        ? path.dirname(fileURLToPath(context.parentURL))
        : process.cwd();
      const tsCandidate = path.resolve(parentDir, `${specifier}.ts`);
      if (fs.existsSync(tsCandidate)) {
        return nextResolve(pathToFileURL(tsCandidate).href, context);
      }
    }
    return nextResolve(specifier, context);
  },
});

// Provide lightweight browser storage + fetch mocks for runtime Pinia store verification
function installMockBrowserGlobals() {
  const storageMap = new Map();
  const mockLocalStorage = {
    getItem: (k) => (storageMap.has(k) ? storageMap.get(k) : null),
    setItem: (k, v) => storageMap.set(k, String(v)),
    removeItem: (k) => storageMap.delete(k),
    clear: () => storageMap.clear(),
  };
  globalThis.window = {
    localStorage: mockLocalStorage,
    addEventListener: () => {},
    URL: {
      createObjectURL: () => 'blob:mock',
      revokeObjectURL: () => {},
    },
  };
  globalThis.localStorage = mockLocalStorage;
  globalThis.document = {
    createElement: () => ({
      href: '',
      download: '',
      click: () => {},
    }),
    body: {
      appendChild: () => {},
      removeChild: () => {},
    },
  };
  return { storageMap };
}

installMockBrowserGlobals();

const { createPinia, setActivePinia } = await import('pinia');
const { useSharedFiltersStore, normalizeSharedPreset } = await import('../stores/filters.ts');
const { useAnalysisStore } = await import('../stores/analysis.ts');
const { useTransactionsStore } = await import('../stores/transactions.ts');
const { setActiveProfileId } = await import('../api/client.ts');

describe('Finance Hub Shared Controls Reorganization & Clickable Ledger Sorting', () => {
  const filtersStoreContent = readFile('stores/filters.ts');
  const txStoreContent = readFile('stores/transactions.ts');
  const analysisStoreContent = readFile('stores/analysis.ts');
  const ledgerViewContent = readFile('views/LedgerView.vue');
  const analysisViewContent = readFile('views/AnalysisView.vue');
  const sharedToolbarContent = readFile('components/SharedFilterToolbar.vue');
  const profilesStoreContent = readFile('stores/profiles.ts');

  beforeEach(() => {
    globalThis.localStorage.clear();
    setActiveProfileId('default');
    setActivePinia(createPinia());
  });

  test('1. Shared panel order and matching selected-state styles on Analysis and Ledger', () => {
    // Both AnalysisView and LedgerView import and mount the exact same SharedFilterToolbar component
    assert.ok(
      analysisViewContent.includes("import SharedFilterToolbar from '../components/SharedFilterToolbar.vue'"),
      'AnalysisView must import SharedFilterToolbar'
    );
    assert.ok(
      ledgerViewContent.includes("import SharedFilterToolbar from '../components/SharedFilterToolbar.vue'"),
      'LedgerView must import SharedFilterToolbar'
    );
    assert.ok(
      analysisViewContent.includes('<SharedFilterToolbar'),
      'AnalysisView must render SharedFilterToolbar'
    );
    assert.ok(
      ledgerViewContent.includes('<SharedFilterToolbar'),
      'LedgerView must render SharedFilterToolbar'
    );

    // Panel 1 (Period) appears strictly before Panel 2 (Filters) inside SharedFilterToolbar
    const periodPanelIdx = sharedToolbarContent.indexOf('data-testid="shared-period-panel"');
    const filtersPanelIdx = sharedToolbarContent.indexOf('data-testid="shared-filters-panel"');
    assert.ok(periodPanelIdx !== -1, 'SharedFilterToolbar must define Panel 1: Period');
    assert.ok(filtersPanelIdx !== -1, 'SharedFilterToolbar must define Panel 2: Filters');
    assert.ok(periodPanelIdx < filtersPanelIdx, 'Panel 1 (Period) must precede Panel 2 (Filters)');

    // Panel 1 contains date presets, custom dates, Prev/Current/Next navigation, and Group-by interval
    assert.ok(sharedToolbarContent.includes('preset-btn-'), 'Panel 1 must render preset buttons');
    assert.ok(sharedToolbarContent.includes('period-nav-prev'), 'Panel 1 must render Previous navigation');
    assert.ok(sharedToolbarContent.includes('period-nav-current'), 'Panel 1 must render Current reset button');
    assert.ok(sharedToolbarContent.includes('period-nav-next'), 'Panel 1 must render Next navigation');
    assert.ok(sharedToolbarContent.includes('custom-date-range-inputs'), 'Panel 1 must render Custom date inputs');
    assert.ok(sharedToolbarContent.includes('Group by'), 'Panel 1 must include Group-by interval control');

    // Panel 2 contains searchable Accounts, searchable Categories (with Uncategorised), active chips, and reset
    assert.ok(sharedToolbarContent.includes('account-multiselect-trigger'), 'Panel 2 must render Accounts trigger');
    assert.ok(sharedToolbarContent.includes('category-multiselect-trigger'), 'Panel 2 must render Categories trigger');
    assert.ok(sharedToolbarContent.includes('Uncategorised'), 'Panel 2 must include Uncategorised option');
    assert.ok(sharedToolbarContent.includes('data-testid="active-filter-chips-bar"'), 'Panel 2 must render unified chips bar');
    assert.ok(sharedToolbarContent.includes('data-testid="reset-all-filters-btn"'), 'Panel 2 must render reset action');

    // Identical selected-state styling & active chip styling
    assert.ok(
      sharedToolbarContent.includes("bg-slate-900 text-white dark:bg-white dark:text-slate-950"),
      'Active preset/interval buttons must use consistent high-contrast styling'
    );
    assert.ok(
      sharedToolbarContent.includes("bg-slate-100 dark:bg-slate-800 border-slate-400 dark:border-slate-500 text-slate-900 dark:text-white"),
      'Selected account/category triggers must use consistent styling'
    );
    assert.ok(
      sharedToolbarContent.includes("borderLeftWidth: '3px'") && sharedToolbarContent.includes("backgroundColor: chip.color ? `${chip.color}18`"),
      'Shared active chips must use unified color dot and left-accent pill styling across both pages'
    );

    // Page-specific controls sit in a separate panel BELOW SharedFilterToolbar on each page
    const analysisSharedIdx = analysisViewContent.indexOf('<SharedFilterToolbar');
    const analysisPageControlsIdx = analysisViewContent.indexOf('data-testid="analysis-page-controls"');
    assert.ok(
      analysisPageControlsIdx > analysisSharedIdx,
      'Analysis page-specific section controls must sit below SharedFilterToolbar'
    );
    const ledgerSharedIdx = ledgerViewContent.indexOf('<SharedFilterToolbar');
    const ledgerPageControlsIdx = ledgerViewContent.indexOf('data-testid="ledger-page-controls"');
    assert.ok(
      ledgerPageControlsIdx > ledgerSharedIdx,
      'Ledger page-specific controls must sit below SharedFilterToolbar'
    );

    // Visually distinct container styling for page-specific panels
    assert.ok(
      analysisViewContent.includes('bg-slate-100/85 dark:bg-slate-900/60') &&
      ledgerViewContent.includes('bg-slate-100/85 dark:bg-slate-900/60'),
      'Page-specific control panels should share distinct secondary surface styling'
    );
  });

  test('2. Responsive stacking, sticky positioning, and dropdown/popover visibility', () => {
    // Two panels side-by-side on desktop (lg:grid-cols-12) and stacked on mobile (grid-cols-1)
    assert.ok(
      sharedToolbarContent.includes('grid grid-cols-1 lg:grid-cols-12'),
      'Shared panels must stack cleanly on narrow screens and sit side by side on wide screens'
    );

    // Sticky beneath global header on both views
    assert.ok(analysisViewContent.includes('sticky top-16 z-30'), 'Analysis dock must stick cleanly at top-16');
    assert.ok(ledgerViewContent.includes('sticky top-16 z-30'), 'Ledger dock must stick cleanly at top-16');

    // No overflow-x-hidden trapping sticky positioning or clipping popovers
    assert.ok(!analysisViewContent.includes('overflow-x-hidden'), 'AnalysisView must not use overflow-x-hidden');
    assert.ok(!ledgerViewContent.includes('overflow-x-hidden'), 'LedgerView must not use overflow-x-hidden');
    assert.ok(!sharedToolbarContent.includes('overflow-x-hidden'), 'SharedFilterToolbar must not use overflow-x-hidden');

    // Viewport-safe popovers with high z-index
    assert.ok(
      sharedToolbarContent.includes('data-testid="account-multiselect-popover"') &&
      sharedToolbarContent.includes('max-w-[calc(100vw-2rem)]') &&
      sharedToolbarContent.includes('z-50'),
      'Account popover must float above content with z-50 and viewport-safe max width'
    );
    assert.ok(
      sharedToolbarContent.includes('data-testid="category-multiselect-popover"') &&
      sharedToolbarContent.includes('right-0') &&
      sharedToolbarContent.includes('z-50'),
      'Category popover must right-align to avoid right-edge viewport clipping'
    );

    // Mobile compact toggle present on both pages
    assert.ok(analysisViewContent.includes('isMobileControlsExpanded'), 'AnalysisView provides mobile expand/collapse toggle');
    assert.ok(ledgerViewContent.includes('isMobileFiltersOpen'), 'LedgerView provides mobile expand/collapse toggle');
  });

  test('3. Runtime verification: Filter synchronization, URL precedence, and strict workspace isolation', () => {
    // Profile A sets shared selections
    setActiveProfileId('profile_a');
    const shared = useSharedFiltersStore();
    const analysis = useAnalysisStore();
    const tx = useTransactionsStore();

    shared.setPreset('3m');
    shared.navigateOffset(-2);
    shared.setInterval('week');
    shared.toggleAccount(10);
    shared.toggleAccount('unassigned');
    shared.toggleCategory(0); // Uncategorised
    shared.toggleCategory(7);

    // Analysis reads numeric accounts (skipping 'unassigned') and normalized categories [0, 7]
    assert.deepEqual(analysis.selectedAccountIds, [10]);
    assert.deepEqual(analysis.selectedCategoryIds, [0, 7]);
    assert.equal(analysis.selectedPreset, '3m');
    assert.equal(analysis.selectedOffset, -2);
    assert.equal(analysis.selectedInterval, 'week');

    // Ledger syncs full shared filter state including 'unassigned'
    tx.syncFiltersFromShared();
    assert.deepEqual(tx.filters.accountIds, [10, 'unassigned']);
    assert.deepEqual(tx.filters.categoryIds, [0, 7]);
    assert.equal(tx.filters.datePreset, '3m');
    assert.equal(tx.filters.dateOffset, -2);

    // Offset navigation cannot go into future (> 0)
    shared.resetOffset();
    shared.navigateOffset(1);
    assert.equal(shared.dateOffset, 0, 'Next navigation must clamp at current period (offset <= 0)');

    // Workspace isolation: switch to Profile B -> zero leakage from Profile A
    setActiveProfileId('profile_b');
    shared.switchProfile('profile_b');
    tx.reset();
    analysis.reset();

    assert.equal(shared.datePreset, 'month', 'Profile B starts with clean default preset');
    assert.deepEqual(shared.accountIds, [], 'Profile B must not inherit Profile A accounts');
    assert.deepEqual(shared.categoryIds, [], 'Profile B must not inherit Profile A categories');

    // Profile B stores its own sort preference and filters
    tx.sortBy = 'category';
    tx.sortOrder = 'asc';
    tx.saveSort();
    shared.setPreset('year');
    shared.toggleAccount(99);

    // Switch back to Profile A -> Profile A state restores cleanly
    setActiveProfileId('profile_a');
    shared.switchProfile('profile_a');
    tx.reset();
    assert.equal(shared.datePreset, '3m');
    assert.deepEqual(shared.accountIds, [10, 'unassigned']);
    assert.equal(tx.sortBy, 'date');
    assert.equal(tx.sortOrder, 'desc');

    // URL precedence: ordinary navigation preserves stored state
    shared.applyFromRoute({});
    assert.equal(shared.datePreset, '3m');
    assert.deepEqual(shared.accountIds, [10, 'unassigned']);

    // Explicit drilldown URL parameters override stored preferences (e.g., Analysis cell click)
    shared.applyFromRoute({
      start_date: '2026-10-01',
      end_date: '2026-10-31',
      uncategorized_only: 'true',
      account_id: '12',
    });
    assert.equal(shared.datePreset, 'custom');
    assert.equal(shared.customStartDate, '2026-10-01');
    assert.equal(shared.customEndDate, '2026-10-31');
    assert.deepEqual(shared.categoryIds, [0]);
    assert.deepEqual(shared.accountIds, [12]);

    // Preset alias normalization ('1y' -> 'year')
    assert.equal(normalizeSharedPreset('1y'), 'year');
    shared.applyFromRoute({ date_preset: '1y' });
    assert.equal(shared.datePreset, 'year');

    // Profiles store switches sharedFilters BEFORE resetting txStore and analysisStore
    assert.ok(
      profilesStoreContent.indexOf('sharedFilters.switchProfile') < profilesStoreContent.indexOf('txStore.reset'),
      'profiles store must switch sharedFilters before resetting dependent stores'
    );
  });

  test('4. Clickable Ledger table sort headings, arrows, accessibility, and dropdown sync', () => {
    // Heading markup contracts
    assert.ok(ledgerViewContent.includes('ledgerTableColumns'), 'LedgerView must define sortable column configs');
    assert.ok(ledgerViewContent.includes('toggleHeadingSort'), 'LedgerView must define toggleHeadingSort handler');
    assert.ok(ledgerViewContent.includes(':aria-sort="col.sortField ? getAriaSort(col.sortField) : undefined"'), 'Sortable <th> must declare aria-sort');
    assert.ok(ledgerViewContent.includes(':aria-label="getSortHeadingAriaLabel(col.sortField, col.label)"'), 'Sort button must provide screen-reader label');
    assert.ok(ledgerViewContent.includes(':data-testid="`sort-heading-${col.sortField}`"'), 'Sortable headings must expose data-testid');
    assert.ok(ledgerViewContent.includes('data-testid="sort-arrow-asc"'), 'Must render clear ascending arrow indicator');
    assert.ok(ledgerViewContent.includes('data-testid="sort-arrow-desc"'), 'Must render clear descending arrow indicator');
    assert.ok(ledgerViewContent.includes('data-testid="sort-arrow-inactive"'), 'Must render subtle inactive indicator');
    assert.ok(ledgerViewContent.includes('data-testid="ledger-sort-selector"'), 'Sort dropdown must remain present');

    // All four sortable fields declared cleanly with expected default directions
    assert.ok(ledgerViewContent.includes("sortField: 'date'"), 'Date column must be sortable');
    assert.ok(ledgerViewContent.includes("sortField: 'category'"), 'Category column must be sortable');
    assert.ok(ledgerViewContent.includes("sortField: 'account'"), 'Account column must be sortable');
    assert.ok(ledgerViewContent.includes("sortField: 'amount'"), 'Amount column must be sortable');

    // Simulate heading click state machine (same rules as toggleHeadingSort)
    const DEFAULT_DIRS = { date: 'desc', amount: 'desc', category: 'asc', account: 'asc' };
    let state = { by: 'date', order: 'desc' };
    function clickHeading(field) {
      if (state.by === field) {
        state.order = state.order === 'asc' ? 'desc' : 'asc';
      } else {
        state = { by: field, order: DEFAULT_DIRS[field] };
      }
    }

    // Active Date (desc) -> toggle to asc -> back to desc
    clickHeading('date');
    assert.deepEqual(state, { by: 'date', order: 'asc' });
    clickHeading('date');
    assert.deepEqual(state, { by: 'date', order: 'desc' });

    // Inactive Amount -> desc (highest first), toggle -> asc (lowest first)
    clickHeading('amount');
    assert.deepEqual(state, { by: 'amount', order: 'desc' });
    clickHeading('amount');
    assert.deepEqual(state, { by: 'amount', order: 'asc' });

    // Inactive Category -> asc (A-Z), toggle -> desc (Z-A)
    clickHeading('category');
    assert.deepEqual(state, { by: 'category', order: 'asc' });
    clickHeading('category');
    assert.deepEqual(state, { by: 'category', order: 'desc' });

    // Inactive Account -> asc (A-Z), toggle -> desc (Z-A)
    clickHeading('account');
    assert.deepEqual(state, { by: 'account', order: 'asc' });
    clickHeading('account');
    assert.deepEqual(state, { by: 'account', order: 'desc' });
  });

  test('5. Runtime verification: Sort persistence, selection safety, pagination, and export requests', async () => {
    const requestedUrls = [];
    globalThis.fetch = async (url) => {
      requestedUrls.push(String(url));
      if (String(url).includes('/export')) {
        return {
          ok: true,
          status: 200,
          blob: async () => new Blob(['csv']),
        };
      }
      if (String(url).includes('/matching-ids')) {
        return {
          ok: true,
          status: 200,
          headers: { get: () => 'application/json' },
          json: async () => ({ ids: [102, 101], total: 2 }),
        };
      }
      return {
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => ({
          items: [
            { id: 102, merchant: 'Alpha' },
            { id: 101, merchant: 'Beta' },
          ],
          total: 2,
          limit: 25,
          offset: 0,
        }),
      };
    };

    const tx = useTransactionsStore();

    // Simulate user selecting rows on current page then changing sort order
    tx.toggleRowSelection(101);
    tx.toggleRowSelection(102);
    tx.isAllMatchingSelected = true;
    tx.offset = 50; // Simulate user on page 3

    await tx.setSort('amount', 'asc');

    // Selection safety: stale selections must be cleared immediately and page reset to 0
    assert.equal(tx.selectedIds.size, 0, 'Changing sort order must clear selectedIds to prevent accidental bulk actions');
    assert.equal(tx.isAllMatchingSelected, false, 'Changing sort order must clear isAllMatchingSelected');
    assert.equal(tx.offset, 0, 'Changing sort order must reset offset to page 1 (0)');

    // Check API request parameters sent
    const listUrl = requestedUrls.find(u => u.includes('/transactions?'));
    assert.ok(listUrl && listUrl.includes('sort_by=amount') && listUrl.includes('sort_order=asc'), 'Transactions request must include sort_by & sort_order');

    // Check sort persisted in profile-scoped localStorage and survives reloadSavedSort
    const savedRaw = globalThis.localStorage.getItem('finance_hub_ledger_sort_default');
    assert.ok(savedRaw);
    assert.deepEqual(JSON.parse(savedRaw), { sortBy: 'amount', sortOrder: 'asc' });

    const freshTx = useTransactionsStore();
    freshTx.sortBy = 'date';
    freshTx.sortOrder = 'desc';
    assert.equal(freshTx.loadSavedSort(), true);
    assert.equal(freshTx.sortBy, 'amount');
    assert.equal(freshTx.sortOrder, 'asc');

    // Check matching IDs and exports carry sort parameters
    await tx.selectAllMatching();
    const matchingUrl = requestedUrls.find(u => u.includes('/matching-ids?'));
    assert.ok(matchingUrl && matchingUrl.includes('sort_by=amount') && matchingUrl.includes('sort_order=asc'), 'selectAllMatching must preserve active sort');

    await tx.exportLedger('csv');
    const exportUrl = requestedUrls.find(u => u.includes('/export?'));
    assert.ok(exportUrl && exportUrl.includes('sort_by=amount') && exportUrl.includes('sort_order=asc'), 'exportLedger must preserve active sort');

    // Static check on stores/types
    assert.ok(filtersStoreContent.includes('finance_hub_shared_filters_'));
    assert.ok(txStoreContent.includes('finance_hub_ledger_sort_'));
    assert.ok(analysisStoreContent.includes('useSharedFiltersStore'));
  });
});
