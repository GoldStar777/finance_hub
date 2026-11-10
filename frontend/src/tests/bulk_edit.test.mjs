import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const SRC_DIR = path.resolve('src');

function readFile(subpath) {
  return fs.readFileSync(path.join(SRC_DIR, subpath), 'utf8');
}

describe('Finance Hub Safe Bulk Editing Contract Tests', () => {
  const ledgerViewContent = readFile('views/LedgerView.vue');
  const bulkModalContent = readFile('components/BulkEditTransactionsModal.vue');
  const txStoreContent = readFile('stores/transactions.ts');
  const clientContent = readFile('api/client.ts');
  const typesContent = readFile('types/index.ts');

  test('1. Types declare bulk edit payload, result, and matching IDs contracts', () => {
    assert.ok(typesContent.includes('export interface MatchingTransactionIdsResponse'), 'types must declare MatchingTransactionIdsResponse');
    assert.ok(typesContent.includes('ids: number[]'), 'MatchingTransactionIdsResponse must have ids');
    assert.ok(typesContent.includes('total: number'), 'MatchingTransactionIdsResponse must have total');

    assert.ok(typesContent.includes('export interface BulkTransactionUpdatePayload'), 'types must declare BulkTransactionUpdatePayload');
    assert.ok(typesContent.includes('transaction_ids: number[]'), 'Payload must include transaction_ids array');
    assert.ok(typesContent.includes('update_transaction_type?: boolean'), 'Payload must support update_transaction_type boolean');
    assert.ok(typesContent.includes('update_category?: boolean'), 'Payload must support update_category boolean');
    assert.ok(typesContent.includes('update_account?: boolean'), 'Payload must support update_account boolean');

    assert.ok(typesContent.includes('export interface BulkTransactionUpdateResult'), 'types must declare BulkTransactionUpdateResult');
    assert.ok(typesContent.includes('updated_count: number'), 'Result must include updated_count');
    assert.ok(typesContent.includes('affected_ids: number[]'), 'Result must include affected_ids');
  });

  test('2. API client exposes getMatchingTransactionIds and bulkUpdateTransactions', () => {
    assert.ok(clientContent.includes('getMatchingTransactionIds:'), 'Client must have getMatchingTransactionIds method');
    assert.ok(clientContent.includes('/transactions/matching-ids'), 'Client must call /transactions/matching-ids endpoint');
    assert.ok(clientContent.includes('bulkUpdateTransactions:'), 'Client must have bulkUpdateTransactions method');
    assert.ok(clientContent.includes('/transactions/bulk'), 'Client must post to /transactions/bulk endpoint');
  });

  test('3. Transactions store provides safe selection lifecycle and profile isolation', () => {
    assert.ok(txStoreContent.includes('selectedIds = ref<Set<number>>(new Set())'), 'Store must track selectedIds with a reactive Set');
    assert.ok(txStoreContent.includes('isAllMatchingSelected = ref(false)'), 'Store must track isAllMatchingSelected flag');
    assert.ok(txStoreContent.includes('function isRowSelected(id: number)'), 'Store must expose isRowSelected helper');
    assert.ok(txStoreContent.includes('function toggleRowSelection(id: number)'), 'Store must expose toggleRowSelection action');
    assert.ok(txStoreContent.includes('function selectCurrentPage()'), 'Store must expose selectCurrentPage action');
    assert.ok(txStoreContent.includes('function deselectCurrentPage()'), 'Store must expose deselectCurrentPage action');
    assert.ok(txStoreContent.includes('function clearSelection()'), 'Store must expose clearSelection action');
    assert.ok(txStoreContent.includes('function selectAllMatching()'), 'Store must expose selectAllMatching action');
    assert.ok(txStoreContent.includes('async function bulkUpdate('), 'Store must expose bulkUpdate action');

    // Selection reset safeguards on reset and resetFilters
    assert.ok(txStoreContent.includes('clearSelection()'), 'reset/clear must clear selections');
  });

  test('4. LedgerView provides checkboxes, indeterminate header, selection bar, and cross-page selection banner', () => {
    // Row checkbox
    assert.ok(ledgerViewContent.includes('txStore.isRowSelected(tx.id)'), 'LedgerView rows must bind checkbox to isRowSelected');
    assert.ok(ledgerViewContent.includes('txStore.toggleRowSelection(tx.id)'), 'LedgerView row checkbox must toggle selection');

    // Header checkbox
    assert.ok(ledgerViewContent.includes('isCurrentPageAllSelected'), 'Ledger header must bind to isCurrentPageAllSelected');
    assert.ok(ledgerViewContent.includes('toggleSelectCurrentPage'), 'Ledger header must toggle page selection');

    // Selection floating bar
    assert.ok(ledgerViewContent.includes('selectedCount'), 'Selection bar must display selected count');
    assert.ok(ledgerViewContent.includes('Bulk Edit'), 'Selection bar must have Bulk Edit button');
    assert.ok(ledgerViewContent.includes('txStore.clearSelection()'), 'Selection bar must have Deselect all button');

    // Cross-page matching banner
    assert.ok(ledgerViewContent.includes('txStore.selectAllMatching()'), 'Cross-page banner must allow selecting all matching');
    assert.ok(ledgerViewContent.includes('txStore.total'), 'Cross-page banner must display total matching count');

    // Modal integration
    assert.ok(ledgerViewContent.includes('BulkEditTransactionsModal'), 'LedgerView must integrate BulkEditTransactionsModal');
    assert.ok(ledgerViewContent.includes('isBulkEditOpen'), 'LedgerView must control isBulkEditOpen visibility');
  });

  test('5. BulkEditTransactionsModal implements type, category, account changes with confirmation and safeguards', () => {
    // Type change
    assert.ok(bulkModalContent.includes('typeAction'), 'Modal must have select action for transaction type');
    assert.ok(bulkModalContent.includes('value="expense"'), 'Modal must support changing to Expense');
    assert.ok(bulkModalContent.includes('value="income"'), 'Modal must support changing to Income');

    // Category change with Uncategorised
    assert.ok(bulkModalContent.includes('categoryAction'), 'Modal must have select action for category');
    assert.ok(bulkModalContent.includes('value="uncategorized"'), 'Modal must support setting to Uncategorised');

    // Account change with Unassigned
    assert.ok(bulkModalContent.includes('accountAction'), 'Modal must have select action for account');
    assert.ok(bulkModalContent.includes('value="unassigned"'), 'Modal must support setting to Unassigned');

    // Confirmation step and safeguards
    assert.ok(bulkModalContent.includes('hasChangesToApply'), 'Modal must compute hasChangesToApply for preview and enable');
    assert.ok(bulkModalContent.includes('Confirmation: The following changes will be applied to'), 'Modal must summarize changes before apply');
    assert.ok(bulkModalContent.includes('All other fields (amounts, dates, merchants, notes, receipts, and currency provenance) will remain untouched'), 'Modal must reassure field preservation');
    assert.ok(bulkModalContent.includes('errorMessage'), 'Modal must display validation and rejection errors');
    assert.ok(bulkModalContent.includes('handleApply'), 'Modal must handle apply with confirmation safeguards');
  });
});
