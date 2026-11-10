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
  };
  globalThis.localStorage = mockLocalStorage;
}

describe('Finance Hub Income Categories and Cash Account Type Tests', () => {
  beforeEach(() => {
    installMockBrowserGlobals();
  });

  test('1. Runtime categoryPurpose utilities filter by transaction type and reject incompatible combinations', async () => {
    const mod = await import('../utils/categoryPurpose.ts');
    const categories = [
      { id: 1, name: 'Groceries', category_type: 'expense', is_active: true },
      { id: 2, name: 'Salary', category_type: 'income', is_active: true },
      { id: 3, name: 'Old Rent', category_type: 'expense', is_active: false },
      { id: 4, name: 'Legacy No-Type', is_active: true },
    ];

    assert.equal(mod.expectedCategoryTypeForTransaction('expense'), 'expense');
    assert.equal(mod.expectedCategoryTypeForTransaction('income'), 'income');
    assert.equal(mod.expectedCategoryTypeForTransaction('transfer'), null);
    assert.equal(mod.expectedCategoryTypeForTransaction('adjustment'), null);

    const expActive = mod.filterCategoriesForTransactionType(categories, 'expense');
    assert.deepEqual(expActive.map(c => c.name), ['Groceries', 'Legacy No-Type']);

    const incActive = mod.filterCategoriesForTransactionType(categories, 'income');
    assert.deepEqual(incActive.map(c => c.name), ['Salary']);

    const trfCats = mod.filterCategoriesForTransactionType(categories, 'transfer');
    assert.deepEqual(trfCats, []);

    assert.equal(mod.isCategoryCompatibleWithTransaction(categories, 1, 'expense'), true);
    assert.equal(mod.isCategoryCompatibleWithTransaction(categories, 1, 'income'), false);
    assert.equal(mod.isCategoryCompatibleWithTransaction(categories, 2, 'income'), true);
    assert.equal(mod.isCategoryCompatibleWithTransaction(categories, 2, 'expense'), false);
    assert.equal(mod.isCategoryCompatibleWithTransaction(categories, 2, 'transfer'), false);
    assert.equal(mod.isCategoryCompatibleWithTransaction(categories, null, 'income'), true);
  });

  test('2. API client and types expose Cash account_type, category_type, and income Analysis exports', async () => {
    const typesSrc = readFile('types/index.ts');
    assert.ok(typesSrc.includes("'cash'"));
    assert.ok(typesSrc.includes("export type CategoryType = 'expense' | 'income'"));
    assert.ok(typesSrc.includes('income_categories?: CategorySpendingItem[]'));
    assert.ok(typesSrc.includes('income_matrix?: SpendingMatrixResponse'));
    assert.ok(typesSrc.includes('expected_category_type?: CategoryType | null'));

    const clientSrc = readFile('api/client.ts');
    assert.ok(clientSrc.includes('category_type'));

    const requests = [];
    globalThis.fetch = async (url) => {
      requests.push(String(url));
      return {
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => [],
      };
    };
    const { api } = await import('../api/client.ts');
    await api.getCategories(false, 'income');
    assert.ok(requests[0].includes('/categories?include_inactive=false&category_type=income'));
  });

  test('3. Cash account type appears cleanly in creation, editing, cards, breakdown, filters, and reconciliation', () => {
    const addAcc = readFile('components/AddAccountModal.vue');
    assert.ok(addAcc.includes('<option value="cash">Cash</option>'));

    const editAcc = readFile('components/EditAccountModal.vue');
    assert.ok(editAcc.includes('<option value="cash">Cash</option>'));

    const card = readFile('components/AccountCard.vue');
    assert.ok(card.includes("case 'cash': return 'Cash Account'"));
    assert.ok(card.includes("account.account_type === 'cash'"));

    const dash = readFile('views/DashboardView.vue');
    assert.ok(dash.includes("a.account_type === 'cash'"));
    assert.ok(dash.includes("title: 'Cash Accounts'"));

    const detail = readFile('components/AccountDetailModal.vue');
    assert.ok(detail.includes("case 'Cash Accounts':"));

    const reconcile = readFile('components/ReconcileAccountModal.vue');
    assert.ok(reconcile.includes("case 'cash': return 'Cash Account'"));

    const toolbar = readFile('components/SharedFilterToolbar.vue');
    assert.ok(toolbar.includes("if (t === 'cash') return 'Cash'"));
    assert.ok(toolbar.includes("cat.category_type === 'income'"));
  });

  test('4. Category management & deletion separate Income vs Expense and support purpose reassignment', () => {
    const manage = readFile('components/ManageAccountsCategoriesModal.vue');
    assert.ok(manage.includes("categoryPurposeFilter = ref<'all' | 'expense' | 'income'>('all')"));
    assert.ok(manage.includes("categoryForm.category_type === 'expense'"));
    assert.ok(manage.includes('reassign_existing_to_id'));
    assert.ok(manage.includes("case 'cash': return 'Cash'"));

    const delModal = readFile('components/DeleteCategoryModal.vue');
    assert.ok(delModal.includes("(c.category_type || 'expense') === sourcePurpose"));
  });

  test('5. All transaction, bulk edit, split, import, queue, review & analysis views enforce category purpose', () => {
    const record = readFile('components/RecordTransactionModal.vue');
    assert.ok(record.includes('filterCategoriesForTransactionType'));
    assert.ok(record.includes('isCategoryCompatibleWithTransaction'));
    assert.ok(record.includes('categoryClearedNotice'));

    const editTx = readFile('components/EditTransactionModal.vue');
    assert.ok(editTx.includes("v-if=\"txType === 'expense' || txType === 'income'\""));
    assert.ok(editTx.includes('isCategoryCompatibleWithTransaction'));

    const bulkEdit = readFile('components/BulkEditTransactionsModal.vue');
    assert.ok(bulkEdit.includes('filterCategoriesForTransactionType'));
    assert.ok(bulkEdit.includes('categoryResetNotice'));

    const split = readFile('components/SplitExpenseModal.vue');
    assert.ok(split.includes("filterCategoriesForTransactionType(props.categories || [], 'expense')"));

    const uImport = readFile('components/UnifiedImportModal.vue');
    assert.ok(uImport.includes('reconcileCategoryForType'));
    assert.ok(uImport.includes('getCategoriesForType'));

    const staging = readFile('views/StagingView.vue');
    assert.ok(staging.includes('compatibleEditCategories'));
    assert.ok(staging.includes('editCategoryClearedNotice'));

    const dq = readFile('views/DataQualityView.vue');
    assert.ok(dq.includes('assignableCategories'));
    assert.ok(dq.includes('findingCategoryPurpose'));

    const analysis = readFile('views/AnalysisView.vue');
    assert.ok(analysis.includes('income-categories-card'));
    assert.ok(analysis.includes("triggerExport('income_categories'"));
    assert.ok(analysis.includes("triggerExport('income_matrix'"));
  });
});
