import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const SRC_DIR = path.resolve('src');

function readFile(subpath) {
  return fs.readFileSync(path.join(SRC_DIR, subpath), 'utf8');
}

describe('Finance Hub Uncategorised Filter and Confidence Settings Contract Tests', () => {
  const ledgerViewContent = readFile('views/LedgerView.vue');
  const sharedToolbarContent = readFile('components/SharedFilterToolbar.vue');
  const settingsModalContent = readFile('components/AppSettingsModal.vue');
  const typesContent = readFile('types/index.ts');
  const clientContent = readFile('api/client.ts');
  const unifiedImportContent = readFile('components/UnifiedImportModal.vue');

  test('1. LedgerView provides explicit Uncategorised category option and distinct All Categories option', () => {
    // Option in select
    assert.ok(ledgerViewContent.includes('<option value="uncategorized">Uncategorised</option>'), 'Must have explicit Uncategorised option');
    assert.ok(ledgerViewContent.includes('<option :value="null">All Categories</option>'), 'Must have distinct All Categories option');

    // Computed model
    assert.ok(ledgerViewContent.includes('selectedCategoryFilterValue'), 'Must bind select to selectedCategoryFilterValue computed model');
    assert.ok(ledgerViewContent.includes("return 'uncategorized';"), 'Must return uncategorized when uncategorizedOnly or categoryId is uncategorized');

    // Filter chip and clearing
    assert.ok(sharedToolbarContent.includes('getCategoryLabel(id: number | string)') && sharedToolbarContent.includes("return 'Uncategorised'"), 'Active shared filter chip must resolve Uncategorised label');
    assert.ok(ledgerViewContent.includes('clearCategoryFilter') && sharedToolbarContent.includes('handleClearCategories'), 'Must provide category clearing actions');
  });

  test('2. URL persistence: syncFiltersFromRoute and updateRouteQuery preserve category_id=uncategorized', () => {
    // URL parsing in syncFiltersFromRoute
    assert.ok(ledgerViewContent.includes("rawVal === 'uncategorised' || rawVal === 'uncategorized'"), 'Must recognize uncategorised/uncategorized query param');
    assert.ok(ledgerViewContent.includes("txStore.filters.categoryId = 'uncategorized'"), 'Must set categoryId to uncategorized on direct URL navigation');
    assert.ok(ledgerViewContent.includes('txStore.filters.uncategorizedOnly = true'), 'Must enable uncategorizedOnly flag');

    // URL updating in updateRouteQuery
    assert.ok(ledgerViewContent.includes('updateRouteQuery()'), 'Filter changes must call updateRouteQuery');
    assert.ok(ledgerViewContent.includes("nextQuery.category_id = 'uncategorized'"), 'Must serialize category_id=uncategorized into route query');
    assert.ok(ledgerViewContent.includes('router.replace({ query: nextQuery })'), 'Must update browser URL via router.replace');
  });

  test('3. AppSettingsModal provides separate Category and Account matching controls with understandable levels', () => {
    // Section headers & workspace scope
    assert.ok(settingsModalContent.includes('Import Suggestions & Matching'), 'Settings must include Import Suggestions & Matching section');
    assert.ok(settingsModalContent.includes('Workspace-Scoped'), 'Settings must clearly state workspace-scoped nature');

    // Category matching control
    assert.ok(settingsModalContent.includes('Category Matching'), 'Must have separate Category Matching control');
    assert.ok(settingsModalContent.includes("setCategoryConfidence('cautious')"), 'Must have Very cautious option for Category');
    assert.ok(settingsModalContent.includes("setCategoryConfidence('balanced')"), 'Must have Balanced option for Category');
    assert.ok(settingsModalContent.includes("setCategoryConfidence('permissive')"), 'Must have More suggestions option for Category');

    // Account matching control
    assert.ok(settingsModalContent.includes('Account Matching'), 'Must have separate Account Matching control');
    assert.ok(settingsModalContent.includes("setAccountConfidence('cautious')"), 'Must have Very cautious option for Account');
    assert.ok(settingsModalContent.includes("setAccountConfidence('balanced')"), 'Must have Balanced option for Account');
    assert.ok(settingsModalContent.includes("setAccountConfidence('permissive')"), 'Must have More suggestions option for Account');

    // User-facing explanations
    assert.ok(settingsModalContent.includes('Prefill only high-confidence matches'), 'Must explain cautious mode in plain English');
    assert.ok(settingsModalContent.includes('Use clear, reasonably strong matches'), 'Must explain balanced mode in plain English');
    assert.ok(settingsModalContent.includes('Allow weaker semantic matches'), 'Must explain permissive mode in plain English');
  });

  test('4. Settings update store and client contracts', () => {
    // SystemSettings types
    assert.ok(typesContent.includes("import_confidence_category?: 'cautious' | 'balanced' | 'permissive'"), 'SystemSettings must type import_confidence_category');
    assert.ok(typesContent.includes("import_confidence_account?: 'cautious' | 'balanced' | 'permissive'"), 'SystemSettings must type import_confidence_account');

    // SystemSettingsUpdatePayload types
    assert.ok(typesContent.includes("import_confidence_category?: 'cautious' | 'balanced' | 'permissive'"), 'UpdatePayload must type import_confidence_category');
    assert.ok(typesContent.includes("import_confidence_account?: 'cautious' | 'balanced' | 'permissive'"), 'UpdatePayload must type import_confidence_account');

    // API client
    assert.ok(clientContent.includes('getSystemSettings:'), 'API client must expose getSystemSettings');
    assert.ok(clientContent.includes("params.append('uncategorized_only', 'true')"), 'API client must map uncategorized to uncategorized_only parameter');
  });

  test('5. UnifiedImportModal shows clear reasons and supports manual override', () => {
    assert.ok(unifiedImportContent.includes('item.account_match_reason'), 'Import review must display account match reason');
    assert.ok(unifiedImportContent.includes('item.category_match_reason'), 'Import review must display category match reason');
    assert.ok(unifiedImportContent.includes('v-model="item.account_id"'), 'Import review must allow manual account override via select');
    assert.ok(unifiedImportContent.includes('v-model="item.category_id"'), 'Import review must allow manual category override via select');
    assert.ok(unifiedImportContent.includes('Unassigned (assign later)'), 'Account select must offer unassigned option');
    assert.ok(unifiedImportContent.includes('Uncategorised'), 'Category select must offer uncategorised option');
  });
});

