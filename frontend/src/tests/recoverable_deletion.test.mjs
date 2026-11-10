import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const srcDir = path.resolve(__dirname, '..');

test('Finance Hub Safe Bulk Deletion and Recoverable Deletion Contract Tests', async (t) => {
  const typesContent = fs.readFileSync(path.join(srcDir, 'types/index.ts'), 'utf-8');
  const clientContent = fs.readFileSync(path.join(srcDir, 'api/client.ts'), 'utf-8');
  const txStoreContent = fs.readFileSync(path.join(srcDir, 'stores/transactions.ts'), 'utf-8');
  const ledgerViewContent = fs.readFileSync(path.join(srcDir, 'views/LedgerView.vue'), 'utf-8');
  const modalContent = fs.readFileSync(path.join(srcDir, 'components/BulkDeleteConfirmationModal.vue'), 'utf-8');

  await t.test('1. TypeScript contracts declare soft delete fields and bulk delete/restore payloads', () => {
    // Transaction soft-delete attributes
    assert.ok(typesContent.includes('deleted_at?: string | null;'), 'Transaction must have optional deleted_at');
    assert.ok(typesContent.includes('deletion_batch_id?: string | null;'), 'Transaction must have optional deletion_batch_id');
    assert.ok(typesContent.includes('is_deleted?: boolean;'), 'Transaction must have optional is_deleted');

    // Bulk Delete & Restore payload/result contracts
    assert.ok(typesContent.includes('export interface BulkTransactionDeletePayload'), 'Must export BulkTransactionDeletePayload');
    assert.ok(typesContent.includes('export interface BulkTransactionDeleteResult'), 'Must export BulkTransactionDeleteResult');
    assert.ok(typesContent.includes('export interface RestoreTransactionsPayload'), 'Must export RestoreTransactionsPayload');
    assert.ok(typesContent.includes('export interface RestoreTransactionsResult'), 'Must export RestoreTransactionsResult');
    assert.ok(typesContent.includes('export interface RecentlyDeletedSummary'), 'Must export RecentlyDeletedSummary');
  });

  await t.test('2. API client exposes bulk-delete, restore, undo, and deleted listing endpoints', () => {
    assert.ok(clientContent.includes('bulkDeleteTransactions:'), 'API client must expose bulkDeleteTransactions');
    assert.ok(clientContent.includes('/transactions/bulk-delete'), 'API client must call /transactions/bulk-delete');
    assert.ok(clientContent.includes('restoreTransactions:'), 'API client must expose restoreTransactions');
    assert.ok(clientContent.includes('/transactions/restore'), 'API client must call /transactions/restore');
    assert.ok(clientContent.includes('undoDeleteTransactions:'), 'API client must expose undoDeleteTransactions');
    assert.ok(clientContent.includes('/transactions/undo-delete'), 'API client must call /transactions/undo-delete');
    assert.ok(clientContent.includes('getDeletedTransactions:'), 'API client must expose getDeletedTransactions');
    assert.ok(clientContent.includes('/transactions/deleted'), 'API client must call /transactions/deleted');
    assert.ok(clientContent.includes('getDeletedSummary:'), 'API client must expose getDeletedSummary');
    assert.ok(clientContent.includes('/transactions/deleted/summary'), 'API client must call /transactions/deleted/summary');
  });

  await t.test('3. Transactions store provides safe bulk deletion, restore, and floating undo state', () => {
    assert.ok(txStoreContent.includes('async function bulkDelete('), 'Store must provide bulkDelete');
    assert.ok(txStoreContent.includes('async function restoreTransactions('), 'Store must provide restoreTransactions');
    assert.ok(txStoreContent.includes('async function undoLastDelete()'), 'Store must provide undoLastDelete');
    assert.ok(txStoreContent.includes('async function loadDeletedTransactions('), 'Store must provide loadDeletedTransactions');
    assert.ok(txStoreContent.includes('async function loadDeletedSummary()'), 'Store must provide loadDeletedSummary');
    assert.ok(txStoreContent.includes('undoToastMessage'), 'Store must expose undoToastMessage');
    assert.ok(txStoreContent.includes('activeLedgerTab'), 'Store must track activeLedgerTab');
    assert.ok(txStoreContent.includes('deletedTransactions'), 'Store must hold deletedTransactions');
    assert.ok(txStoreContent.includes('deletedSelectedIds'), 'Store must track deletedSelectedIds');
  });

  await t.test('4. LedgerView provides tab switcher, Bulk Delete action, Recently Deleted table, and floating Undo toast', () => {
    // Tab switcher between Active and Recently Deleted
    assert.ok(ledgerViewContent.includes('switchTab(\'active\')'), 'Must have switchTab for active view');
    assert.ok(ledgerViewContent.includes('switchTab(\'deleted\')'), 'Must have switchTab for deleted view');
    assert.ok(ledgerViewContent.includes('Recently Deleted'), 'Must show Recently Deleted label');

    // Bulk Delete action in Bulk Selection Bar
    assert.ok(ledgerViewContent.includes('openBulkDeleteModal'), 'Must trigger openBulkDeleteModal');
    assert.ok(ledgerViewContent.includes('Bulk Delete ({{ selectedCount }})'), 'Must show Bulk Delete button with count');

    // Recently Deleted table and restore actions
    assert.ok(ledgerViewContent.includes('handleSingleRestore(tx)'), 'Must support single row restore');
    assert.ok(ledgerViewContent.includes('handleBulkRestore'), 'Must support bulk restore of selected deleted items');
    assert.ok(ledgerViewContent.includes('handleDeletedSearch'), 'Must support searching deleted items');

    // Floating Undo notification banner
    assert.ok(ledgerViewContent.includes('txStore.undoToastMessage'), 'Must conditionally render floating undo notification');
    assert.ok(ledgerViewContent.includes('txStore.undoLastDelete()'), 'Undo button must trigger txStore.undoLastDelete');
  });

  await t.test('5. BulkDeleteConfirmationModal clarifies scope, paired transfer impact, and receipt retention', () => {
    assert.ok(modalContent.includes('Selection Scope'), 'Must explain selection scope');
    assert.ok(modalContent.includes('Paired Transfers'), 'Must explain paired transfer impact');
    assert.ok(modalContent.includes('Receipt Attachment Preservation'), 'Must explain receipt file preservation');
    assert.ok(modalContent.includes('Reversible & Safe'), 'Must explain that deletion is reversible');
    assert.ok(modalContent.includes('Recently Deleted'), 'Must reference Recently Deleted tab');
    assert.ok(modalContent.includes('Move {{ countLabel }} to Recently Deleted'), 'Confirm button must be explicit');
  });
});
