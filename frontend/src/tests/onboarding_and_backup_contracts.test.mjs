import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC_DIR = path.resolve(__dirname, '..');

function readFile(subpath) {
  return fs.readFileSync(path.join(SRC_DIR, subpath), 'utf8');
}

describe('First-Run Onboarding, Currency/Timezone & Profile Backup Download Contracts', () => {
  const dashboardContent = readFile('views/DashboardView.vue');
  const summaryCardsContent = readFile('components/SummaryCards.vue');
  const settingsContent = readFile('components/AppSettingsModal.vue');
  const clientContent = readFile('api/client.ts');
  const importModalContent = readFile('components/UnifiedImportModal.vue');

  test('1. Dashboard empty state explains local storage, currency, timezone, and first-run steps', () => {
    assert.ok(dashboardContent.includes('No accounts configured yet'));
    assert.ok(dashboardContent.includes('./data'), 'Empty state must mention local ./data storage');
    assert.ok(dashboardContent.includes('1. Add an Account'));
    assert.ok(dashboardContent.includes('2. Add Categories'));
    assert.ok(dashboardContent.includes('3. Log or Import'));
    assert.ok(dashboardContent.includes('systemStore.config?.base_currency'));
    assert.ok(dashboardContent.includes('systemStore.config?.app_timezone'));
  });

  test('2. SummaryCards uses dynamic base currency symbol fallback instead of hardcoded £0.00', () => {
    assert.ok(summaryCardsContent.includes('useSystemStore'));
    assert.ok(summaryCardsContent.includes('zeroDisplay'));
    assert.ok(!summaryCardsContent.includes("|| '£0.00'"));
  });

  test('3. AppSettingsModal explains currency/timezone lock and uses X-Profile-ID backup download', () => {
    assert.ok(settingsContent.includes('Ledger Currency &amp; Timezone'));
    assert.ok(settingsContent.includes('BASE_CURRENCY'));
    assert.ok(settingsContent.includes('APP_TIMEZONE'));
    assert.ok(settingsContent.includes('handleDownloadBackup'));
    assert.ok(settingsContent.includes('activeBackupFolderLabel'));
    assert.ok(settingsContent.includes('restoreCommandHint'));
    assert.ok(settingsContent.includes('--profile "${prof.name}"'));
    assert.ok(!settingsContent.includes(':href="api.getBackupDownloadUrl'), 'Must not bypass X-Profile-ID via raw anchor href');
    assert.ok(clientContent.includes('downloadBackupArchive'));
    assert.ok(clientContent.includes("headers['X-Profile-ID'] = activeProfileId"));
  });

  test('4. UnifiedImportModal uses OS-neutral privacy wording', () => {
    assert.ok(!importModalContent.includes('on your Mac'), 'Avoid Mac-only copy on cross-platform UI');
    assert.ok(importModalContent.includes('on your computer'));
  });
});
