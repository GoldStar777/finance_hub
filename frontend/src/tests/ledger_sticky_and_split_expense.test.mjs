import { test, describe } from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';

function readFile(relPath) {
  return fs.readFileSync(path.resolve(process.cwd(), 'src', relPath), 'utf8');
}

describe('Finance Hub Usability: Ledger Sticky Controls & Manual Expense Splitting', () => {
  const ledgerViewContent = readFile('views/LedgerView.vue');
  const sharedToolbarContent = readFile('components/SharedFilterToolbar.vue');
  const splitModalContent = readFile('components/SplitExpenseModal.vue');
  const importModalContent = readFile('components/UnifiedImportModal.vue');
  const stagingViewContent = readFile('views/StagingView.vue');
  const typesContent = readFile('types/index.ts');
  const clientContent = readFile('api/client.ts');
  const stagingStoreContent = readFile('stores/staging.ts');

  test('1. LedgerView sticky toolbar layout, non-clipping containing block, and mobile expand/collapse', () => {
    // Must declare data-testid="ledger-sticky-toolbar"
    assert.ok(
      ledgerViewContent.includes('data-testid="ledger-sticky-toolbar"'),
      'LedgerView must declare data-testid="ledger-sticky-toolbar"'
    );

    // Must be sticky below header with top-16 and z-30
    assert.ok(
      ledgerViewContent.includes('sticky top-16 z-30'),
      'Ledger sticky toolbar must pin below global header using sticky top-16 z-30'
    );

    // Must not have overflow-x-hidden on the sticky toolbar or root view container
    assert.ok(
      !ledgerViewContent.includes('overflow-x-hidden') && !sharedToolbarContent.includes('overflow-x-hidden'),
      'LedgerView and SharedFilterToolbar must not introduce overflow-x-hidden containing block traps that break sticky or clip popovers'
    );

    // Mobile compact summary strip (< md) with expand/collapse toggle
    assert.ok(
      ledgerViewContent.includes('isMobileFiltersOpen'),
      'LedgerView must track isMobileFiltersOpen for compact mobile layout'
    );
    assert.ok(
      ledgerViewContent.includes('activeFilterCount'),
      'LedgerView must calculate activeFilterCount for badge indication'
    );
    assert.ok(
      ledgerViewContent.includes('handlePageSizeSelect'),
      'LedgerView must provide mobile page size select handler in the compact strip'
    );

    // Popovers inside sticky toolbar have z-50 to float above table
    assert.ok(
      sharedToolbarContent.includes('isAccountPopoverOpen') && sharedToolbarContent.includes('z-50'),
      'Account popover must have z-50 for high stacking order above table content'
    );
    assert.ok(
      sharedToolbarContent.includes('isCategoryPopoverOpen') && sharedToolbarContent.includes('z-50'),
      'Category popover must have z-50 for high stacking order above table content'
    );
  });

  test('2. Ledger sticky toolbar keeps page size selector and export accessible while scrolling', () => {
    // Toolbar contains page size buttons [25, 50, 100, 200]
    assert.ok(
      ledgerViewContent.includes('changePageSize(size)'),
      'Sticky toolbar must provide quick access to changePageSize'
    );

    // Toolbar contains matching count badge
    assert.ok(
      ledgerViewContent.includes('{{ txStore.total }} matching'),
      'Sticky toolbar must show live count of matching transactions'
    );

    // Toolbar contains export trigger
    assert.ok(
      ledgerViewContent.includes('isExportOpen = !isExportOpen'),
      'Sticky toolbar must provide export trigger to keep exports accessible while scrolling'
    );
  });

  test('3. TypeScript contracts declare split request, split row, and split response', () => {
    assert.ok(typesContent.includes('interface StagingSplitRow'), 'types must declare StagingSplitRow');
    assert.ok(typesContent.includes('amount_pence: number;'), 'StagingSplitRow must define amount_pence in minor units');
    assert.ok(typesContent.includes('interface StagingSplitRequest'), 'types must declare StagingSplitRequest');
    assert.ok(typesContent.includes('splits: StagingSplitRow[];'), 'StagingSplitRequest must define splits array');
    assert.ok(typesContent.includes('commit_to_ledger?: boolean;'), 'StagingSplitRequest must support commit_to_ledger');
    assert.ok(typesContent.includes('interface StagingSplitResponse'), 'types must declare StagingSplitResponse');
    assert.ok(typesContent.includes('is_split?: boolean;'), 'StagingItem must include is_split property');
    assert.ok(typesContent.includes('split_parent_id?: number | null;'), 'StagingItem must include split_parent_id property');
  });

  test('4. API client and Staging store expose splitStagingItem and splitItem', () => {
    assert.ok(
      clientContent.includes('splitStagingItem:'),
      'api client must expose splitStagingItem method'
    );
    assert.ok(
      clientContent.includes('/staging/items/${id}/split') || clientContent.includes('/staging/${id}/split'),
      'splitStagingItem must call split endpoint'
    );
    assert.ok(
      stagingStoreContent.includes('splitItem'),
      'staging store must expose splitItem method'
    );
  });

  test('5. SplitExpenseModal implements allocation math, minimum rows, category nature default, and actions', () => {
    // Minimum 2 split rows
    assert.ok(
      splitModalContent.includes('rows.value.length <= 2'),
      'SplitExpenseModal must enforce at least two split rows'
    );

    // Live allocation math & exact sum validation
    assert.ok(
      splitModalContent.includes('receiptTotalPence'),
      'SplitExpenseModal must track original receipt total in pence'
    );
    assert.ok(
      splitModalContent.includes('allocatedPence'),
      'SplitExpenseModal must compute allocatedPence from split rows'
    );
    assert.ok(
      splitModalContent.includes('remainingPence'),
      'SplitExpenseModal must compute remaining unallocated pence'
    );
    assert.ok(
      splitModalContent.includes('isExactMatch'),
      'SplitExpenseModal must verify exact allocation match before enabling submission'
    );

    // Default expense nature from category
    assert.ok(
      splitModalContent.includes('default_expense_nature'),
      'SplitExpenseModal must default row expense nature from selected category'
    );

    // Accounting allocation notice
    assert.ok(
      splitModalContent.includes('Multiple accounting allocations'),
      'SplitExpenseModal must clarify that rows are multiple allocations of a single payment'
    );

    // Both actions supported: Queue and Approve
    assert.ok(
      splitModalContent.includes('Save Splits to Queue'),
      'SplitExpenseModal must offer Save Splits to Queue action'
    );
    assert.ok(
      splitModalContent.includes('Approve Split to Ledger'),
      'SplitExpenseModal must offer Approve Split to Ledger action'
    );
  });

  test('6. UnifiedImportModal and StagingView provide Split action for eligible expense receipts', () => {
    // UnifiedImportModal provides Split button
    assert.ok(
      importModalContent.includes('openSplitModal'),
      'UnifiedImportModal must provide openSplitModal handler'
    );
    assert.ok(
      importModalContent.includes('<SplitExpenseModal'),
      'UnifiedImportModal must embed SplitExpenseModal component'
    );
    assert.ok(
      importModalContent.includes('handleSplitSuccess'),
      'UnifiedImportModal must handle splitSuccess to replace candidate with split rows'
    );

    // StagingView provides Split button
    assert.ok(
      stagingViewContent.includes('openSplitModal(item)'),
      'StagingView must provide Split action button on expense items'
    );
    assert.ok(
      stagingViewContent.includes('<SplitExpenseModal'),
      'StagingView must embed SplitExpenseModal component'
    );
  });
});

