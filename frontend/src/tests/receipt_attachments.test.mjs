import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const frontendRoot = path.resolve(__dirname, '../..');
const repoRoot = path.resolve(frontendRoot, '..');

function readFrontendFile(relPath) {
  return fs.readFileSync(path.join(frontendRoot, relPath), 'utf-8');
}

function readRepoFile(relPath) {
  return fs.readFileSync(path.join(repoRoot, relPath), 'utf-8');
}

test('Receipt Attachment Contracts: LedgerView, StagingView, API client, and static exposure cleanup', async (t) => {
  const clientTs = readFrontendFile('src/api/client.ts');
  const typesTs = readFrontendFile('src/types/index.ts');
  const ledgerView = readFrontendFile('src/views/LedgerView.vue');
  const stagingView = readFrontendFile('src/views/StagingView.vue');
  const viteConfig = readFrontendFile('vite.config.ts');
  const mainPy = readRepoFile('app/main.py');

  await t.test('1. API client uses profile-scoped receipt endpoints and X-Profile-ID fetch instead of /static', () => {
    assert.ok(clientTs.includes('fetchReceiptAttachment'), 'client.ts must expose fetchReceiptAttachment');
    assert.ok(clientTs.includes('downloadReceiptAttachment'), 'client.ts must expose downloadReceiptAttachment');
    assert.ok(clientTs.includes('getTransactionReceiptUrl'), 'client.ts must expose getTransactionReceiptUrl');
    assert.ok(clientTs.includes("headers['X-Profile-ID'] = activeProfileId"), 'fetchAuthorizedFile must send X-Profile-ID header');
    assert.ok(!clientTs.includes('/static/'), 'client.ts must not reference broken /static paths');
    assert.ok(typesTs.includes('receipt_url?: string | null'), 'Transaction type must declare receipt_url');
    assert.ok(typesTs.includes('destination_receipt_url?: string | null'), 'Transaction type must declare destination_receipt_url');
  });

  await t.test('2. LedgerView exposes interactive receipt attachment actions for active, deleted, and paired transfer rows', () => {
    assert.ok(ledgerView.includes('data-testid="tx-receipt-btn"'), 'Active ledger rows must provide receipt attachment button');
    assert.ok(ledgerView.includes('data-testid="deleted-tx-receipt-btn"'), 'Recently Deleted rows must provide clickable receipt button');
    assert.ok(ledgerView.includes('openReceiptAttachment'), 'LedgerView must define openReceiptAttachment handler');
    assert.ok(ledgerView.includes('data-testid="receipt-attachment-modal"'), 'LedgerView must include receipt attachment preview/download modal');
    assert.ok(ledgerView.includes('Destination Leg Receipt'), 'LedgerView modal must support paired transfer destination receipts');
    assert.ok(ledgerView.includes('downloadActiveReceipt'), 'LedgerView must support downloading authorized receipts');
    assert.ok(ledgerView.includes('revokeReceiptPreviewUrl'), 'LedgerView must revoke blob URLs to prevent memory leaks');
  });

  await t.test('3. StagingView fetches receipt previews through authenticated client helper rather than unheadered <img> URLs', () => {
    assert.ok(!stagingView.includes('<img :src="item.receipt_url"'), 'StagingView must not load raw unauthenticated item.receipt_url directly in <img>');
    assert.ok(stagingView.includes('api.fetchReceiptAttachment(item.receipt_url)'), 'StagingView must fetch thumbnails via api.fetchReceiptAttachment with X-Profile-ID');
    assert.ok(stagingView.includes('openStagingReceiptPreview'), 'StagingView must open preview via openStagingReceiptPreview');
    assert.ok(stagingView.includes('revokeAllThumbUrls'), 'StagingView must revoke staged blob URLs on unmount');
  });

  await t.test('4. Unauthenticated /receipts_preview mount and Vite proxy are removed', () => {
    assert.ok(!mainPy.includes('/receipts_preview'), 'app/main.py must not mount unauthenticated /receipts_preview');
    assert.ok(!viteConfig.includes('/receipts_preview'), 'frontend/vite.config.ts must not proxy /receipts_preview');
  });
});
