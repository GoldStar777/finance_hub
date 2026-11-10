import { test, describe } from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';

function readFile(relPath) {
  return fs.readFileSync(path.resolve(process.cwd(), 'src', relPath), 'utf8');
}

describe('Finance Hub Usability Enhancements: Analysis Sticky, Ledger Filters & Exports, Review Queue Suggestions', () => {
  const analysisViewContent = readFile('views/AnalysisView.vue');
  const ledgerViewContent = readFile('views/LedgerView.vue');
  const sharedToolbarContent = readFile('components/SharedFilterToolbar.vue');
  const filtersStoreContent = readFile('stores/filters.ts');
  const stagingViewContent = readFile('views/StagingView.vue');
  const typesContent = readFile('types/index.ts');
  const clientContent = readFile('api/client.ts');
  const stagingStoreContent = readFile('stores/staging.ts');
  const txStoreContent = readFile('stores/transactions.ts');
  const ledgerToolbarCombined = `${ledgerViewContent}\n${sharedToolbarContent}\n${filtersStoreContent}`;

  test('1. Analysis sticky toolbar root container does not trap position:sticky with overflow-x-hidden', () => {
    // Root container in AnalysisView.vue must NOT have overflow-x-hidden which creates a non-scrolling containing block
    assert.ok(
      !analysisViewContent.includes('overflow-x-hidden'),
      'AnalysisView root container must not contain overflow-x-hidden that breaks position:sticky'
    );
    // Control panel toolbar remains sticky below app header
    assert.ok(
      analysisViewContent.includes('sticky top-16') || analysisViewContent.includes('top-16 z-30 sticky'),
      'AnalysisView controls toolbar must declare sticky positioning below the global header'
    );
  });

  test('2. LedgerView provides date presets, multi-select account & category popovers, unified export menu, and page size selector', () => {
    // Date presets (now powered by SharedFilterToolbar + useSharedFiltersStore)
    assert.ok(filtersStoreContent.includes('SHARED_PRESET_OPTIONS'), 'Must define shared date presets');
    assert.ok(sharedToolbarContent.includes('handleSelectPreset'), 'SharedFilterToolbar must provide preset handler');
    assert.ok(sharedToolbarContent.includes('applyCustomDates'), 'SharedFilterToolbar must allow applying custom date ranges');

    // Multi-select accounts
    assert.ok(ledgerViewContent.includes('effectiveSelectedAccountIds'), 'LedgerView must track multi-account selection');
    assert.ok(ledgerToolbarCombined.includes('handleToggleAccount'), 'Shared toolbar must provide account toggle handler');
    assert.ok(ledgerToolbarCombined.includes('handleSelectAllAccounts'), 'Shared toolbar must provide select-all accounts');
    assert.ok(ledgerToolbarCombined.includes('handleClearAccounts'), 'Shared toolbar must provide clear-accounts');

    // Multi-select categories
    assert.ok(ledgerViewContent.includes('effectiveSelectedCategoryIds'), 'LedgerView must track multi-category selection');
    assert.ok(ledgerToolbarCombined.includes('handleToggleCategory'), 'Shared toolbar must provide category toggle handler');
    assert.ok(ledgerToolbarCombined.includes('handleSelectAllCategories'), 'Shared toolbar must provide select-all categories');
    assert.ok(ledgerToolbarCombined.includes('handleClearCategories') && ledgerViewContent.includes('clearCategoryFilter'), 'Must provide clear categories action');

    // Single export menu (CSV + XLSX)
    assert.ok(ledgerViewContent.includes('handleExport'), 'LedgerView must provide handleExport action');
    assert.ok(ledgerViewContent.includes("handleExport('csv')"), 'Export menu must offer CSV export');
    assert.ok(ledgerViewContent.includes("handleExport('xlsx')"), 'Export menu must offer XLSX export');
    assert.ok(ledgerViewContent.includes('txStore.total'), 'Export menu button must show matching item count');

    // Page size selector [25, 50, 100, 200]
    assert.ok(ledgerViewContent.includes('[25, 50, 100, 200]'), 'LedgerView must offer standard page sizes [25, 50, 100, 200]');
    assert.ok(ledgerViewContent.includes('changePageSize'), 'LedgerView must provide changePageSize action');
  });

  test('3. Transactions store supports multi-filter parameters, per-profile page size persistence, and ledger export download', () => {
    assert.ok(txStoreContent.includes('getSavedPageSize'), 'Transactions store must retrieve saved page size');
    assert.ok(txStoreContent.includes('finance_hub_ledger_limit_'), 'Transactions store must scope page size key per profile');
    assert.ok(txStoreContent.includes('setPageSize'), 'Transactions store must provide setPageSize method');
    assert.ok(txStoreContent.includes('exportLedger'), 'Transactions store must provide exportLedger method');
    assert.ok(clientContent.includes('downloadTransactionsExport'), 'API client must expose downloadTransactionsExport');
  });

  test('4. Review Queue Advisory Refinement Suggestions types and API client contracts', () => {
    // Types
    assert.ok(typesContent.includes('interface ReviewSuggestionRecord'), 'Types must declare ReviewSuggestionRecord');
    assert.ok(typesContent.includes('interface ReviewDuplicateSuggestion'), 'Types must declare ReviewDuplicateSuggestion');
    assert.ok(typesContent.includes('interface ReviewTransferSuggestion'), 'Types must declare ReviewTransferSuggestion');
    assert.ok(typesContent.includes('interface ReviewSuggestionsResponse'), 'Types must declare ReviewSuggestionsResponse');

    // API client
    assert.ok(clientContent.includes('getReviewSuggestions'), 'API client must expose getReviewSuggestions');
    assert.ok(clientContent.includes('confirmDuplicateSuggestion'), 'API client must expose confirmDuplicateSuggestion');
    assert.ok(clientContent.includes('confirmTransferSuggestion'), 'API client must expose confirmTransferSuggestion');
    assert.ok(clientContent.includes('dismissReviewSuggestion'), 'API client must expose dismissReviewSuggestion');
  });

  test('5. Staging store and StagingView provide explainable duplicate exclusion and transfer pairing', () => {
    // Staging Store
    assert.ok(stagingStoreContent.includes('duplicateSuggestions'), 'Staging store must hold duplicate suggestions');
    assert.ok(stagingStoreContent.includes('transferSuggestions'), 'Staging store must hold transfer suggestions');
    assert.ok(stagingStoreContent.includes('fetchSuggestions'), 'Staging store must provide fetchSuggestions action');
    assert.ok(stagingStoreContent.includes('confirmDuplicate'), 'Staging store must provide confirmDuplicate action');
    assert.ok(stagingStoreContent.includes('confirmTransfer'), 'Staging store must provide confirmTransfer action');
    assert.ok(stagingStoreContent.includes('dismissSuggestion'), 'Staging store must provide dismissSuggestion action');

    // Staging View
    assert.ok(stagingViewContent.includes('Advisory Refinement Suggestions'), 'StagingView must render Advisory Refinement Suggestions panel');
    assert.ok(stagingViewContent.includes('handleConfirmDuplicate'), 'StagingView must wire handleConfirmDuplicate');
    assert.ok(stagingViewContent.includes('handleConfirmTransfer'), 'StagingView must wire handleConfirmTransfer');
    assert.ok(stagingViewContent.includes('handleDismissSuggestion'), 'StagingView must wire handleDismissSuggestion');
    assert.ok(stagingViewContent.includes('sug.action_explanation'), 'StagingView must display action_explanation for transfer suggestions');
  });

  test('6. Automatic suggestion refresh on manual ledger actions and header indicator', () => {
    const headerContent = readFile('components/CommandHeader.vue');
    assert.ok(typesContent.includes('action_explanation?: string | null;'), 'ReviewTransferSuggestion must include action_explanation');
    assert.ok(txStoreContent.includes('stagingStore.fetchSuggestions()'), 'Transactions store must refresh Review Queue suggestions after manual create/update/delete/bulk actions');
    assert.ok(headerContent.includes('stagingStore.fetchSuggestions()'), 'CommandHeader must fetch Review Queue suggestions on mount');
    assert.ok(headerContent.includes('stagingStore.suggestionsCount'), 'CommandHeader must display suggestions badge on Queue navigation item');
  });
});
