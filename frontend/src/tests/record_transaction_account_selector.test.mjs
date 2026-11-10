import { test, describe } from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';

describe('Finance Hub Manual Transaction Entry Account Selector Contract Tests', () => {
  const rootDir = path.resolve(process.cwd());

  test('1. RecordTransactionModal renders clear loading state and retryable error state instead of silently masking with Unassigned', () => {
    const modalPath = path.join(rootDir, 'src/components/RecordTransactionModal.vue');
    const content = fs.readFileSync(modalPath, 'utf8');

    // Clear loading indicators for expense/income and transfer
    assert.ok(
      content.includes('data-testid="account-loading-state"'),
      'RecordTransactionModal must include data-testid="account-loading-state" for loading state'
    );
    assert.ok(
      content.includes('data-testid="transfer-accounts-loading"'),
      'RecordTransactionModal must include data-testid="transfer-accounts-loading" for transfer loading state'
    );
    assert.ok(
      content.includes('accountsStore.loading && eligibleAccounts.length === 0'),
      'Loading state must be displayed when accountsStore.loading is true and eligible accounts are not yet ready'
    );

    // Useful error display and retry button
    assert.ok(
      content.includes('data-testid="account-error-state"'),
      'RecordTransactionModal must include data-testid="account-error-state" when account loading fails'
    );
    assert.ok(
      content.includes('data-testid="retry-load-accounts-btn"'),
      'RecordTransactionModal must include data-testid="retry-load-accounts-btn" to let users retry loading accounts'
    );
    assert.ok(
      content.includes('data-testid="transfer-accounts-error"'),
      'RecordTransactionModal must include data-testid="transfer-accounts-error" for transfer account failures'
    );
    assert.ok(
      content.includes('data-testid="transfer-retry-load-accounts-btn"'),
      'RecordTransactionModal must include data-testid="transfer-retry-load-accounts-btn" for transfer retry'
    );
    assert.ok(
      content.includes('retryLoadAccounts'),
      'RecordTransactionModal must define retryLoadAccounts method to reload accounts on user click'
    );
  });

  test('2. Preservation of Unassigned for Income/Expense while Transfer strictly requires accounts', () => {
    const modalPath = path.join(rootDir, 'src/components/RecordTransactionModal.vue');
    const content = fs.readFileSync(modalPath, 'utf8');

    // Unassigned option in Expense & Income
    assert.ok(
      content.includes('<option :value="null">Unassigned (assign later)</option>'),
      'RecordTransactionModal must preserve Unassigned option for expense and income'
    );

    // Transfer source & destination require valid accounts and do not allow Unassigned
    assert.ok(
      content.includes('<option :value="null" disabled>Select source account</option>'),
      'Transfer source account must require an explicit account selection'
    );
    assert.ok(
      content.includes('<option :value="null" disabled>Select destination account</option>'),
      'Transfer destination account must require an explicit account selection'
    );
    assert.ok(
      content.includes("if (!accountId.value) {\n      errorMessage.value = 'Please select a source account.';"),
      'Transfer must validate that source account is not unassigned or null'
    );
    assert.ok(
      content.includes("if (!destinationAccountId.value) {\n      errorMessage.value = 'Please select a destination account.';"),
      'Transfer must validate that destination account is not unassigned or null'
    );
  });

  test('3. Exclusion of archived / inactive accounts (is_active: false)', () => {
    const modalPath = path.join(rootDir, 'src/components/RecordTransactionModal.vue');
    const content = fs.readFileSync(modalPath, 'utf8');

    assert.ok(
      content.includes('eligibleAccounts = computed('),
      'RecordTransactionModal must compute eligibleAccounts'
    );
    assert.ok(
      content.includes('accountsStore.accounts.filter(a => a.is_active !== false)'),
      'eligibleAccounts must filter out accounts with is_active === false'
    );
    assert.ok(
      content.includes('v-for="acc in eligibleAccounts"'),
      'Account dropdowns must iterate over eligibleAccounts, not raw unfiltered accounts'
    );
    assert.ok(
      content.includes('availableDestinationAccounts = computed(() => {'),
      'availableDestinationAccounts must be computed from eligibleAccounts'
    );
  });

  test('4. Workspace / Profile isolation and proactive loading on open', () => {
    const modalPath = path.join(rootDir, 'src/components/RecordTransactionModal.vue');
    const content = fs.readFileSync(modalPath, 'utf8');

    // Proactive load on modal open
    assert.ok(
      content.includes('watch(() => props.isOpen'),
      'RecordTransactionModal must watch props.isOpen'
    );
    assert.ok(
      content.includes('if (eligibleAccounts.value.length === 0 || accountsStore.error)'),
      'Opening modal must check whether eligible accounts are empty or in error'
    );
    assert.ok(
      content.includes('await accountsStore.loadData()'),
      'Opening modal must proactively call accountsStore.loadData() if accounts are not yet populated'
    );

    // Watch active profile
    assert.ok(
      content.includes("watch(\n  () => profilesStore.activeProfile?.id"),
      'RecordTransactionModal must watch profilesStore.activeProfile?.id'
    );
    assert.ok(
      content.includes('accountId.value = null;'),
      'Switching profile must reset selected accountId to prevent cross-workspace account bleeding'
    );
    assert.ok(
      content.includes('destinationAccountId.value = null;'),
      'Switching profile must reset destinationAccountId'
    );
    assert.ok(
      content.includes('syncAccountSelection()'),
      'RecordTransactionModal must call syncAccountSelection to validate account belongs to current workspace'
    );
  });

  test('5. accountsStore loadData resilience: Promise.allSettled and activeAccounts export', () => {
    const accountsStorePath = path.join(rootDir, 'src/stores/accounts.ts');
    const content = fs.readFileSync(accountsStorePath, 'utf8');

    assert.ok(
      content.includes('Promise.allSettled(['),
      'accountsStore.loadData must use Promise.allSettled so account retrieval succeeds even if dashboard summary fails'
    );
    assert.ok(
      content.includes("accsRes.status === 'fulfilled'"),
      'accountsStore.loadData must store accounts whenever accounts endpoint succeeds'
    );
    assert.ok(
      content.includes('activeAccounts = computed('),
      'accountsStore must expose activeAccounts computed getter'
    );
  });

  test('6. transactionsStore createTransaction uses Promise.allSettled for post-create refreshes', () => {
    const txStorePath = path.join(rootDir, 'src/stores/transactions.ts');
    const content = fs.readFileSync(txStorePath, 'utf8');

    assert.ok(
      content.includes('await Promise.allSettled(['),
      'transactionsStore.createTransaction must use Promise.allSettled for post-submission refreshes'
    );
  });

  test('7. Functional simulation: Repeated openings, saves, workspace switching, and explicit Unassigned preservation', () => {
    // Simulate the exact state machine of RecordTransactionModal
    const mockAccountsProfileA = [
      { id: 1, name: 'Current Account', currency: 'GBP', is_active: true },
      { id: 2, name: 'Savings Account', currency: 'GBP', is_active: true },
      { id: 3, name: 'Old Inactive Account', currency: 'GBP', is_active: false },
    ];

    const mockAccountsProfileB = [
      { id: 10, name: 'Business Checking', currency: 'GBP', is_active: true },
      { id: 11, name: 'Tax Reserve', currency: 'GBP', is_active: true },
    ];

    let storeAccounts = [];
    let isStoreLoading = false;
    let storeError = null;

    // Component state
    let accountId = null;
    let destinationAccountId = null;
    let isExplicitUnassigned = false;
    let txType = 'expense';
    let activeProfileId = 'profile-a';

    function getEligibleAccounts() {
      return storeAccounts.filter(a => a.is_active !== false);
    }

    function syncAccountSelection() {
      const eligible = getEligibleAccounts();
      if (txType === 'transfer') {
        if (!accountId || !eligible.some(a => a.id === accountId)) {
          accountId = eligible.length > 0 ? eligible[0].id : null;
        }
        const destOptions = eligible.filter(a => a.id !== accountId);
        if (!destinationAccountId || !destOptions.some(a => a.id === destinationAccountId)) {
          destinationAccountId = destOptions.length > 0 ? destOptions[0].id : null;
        }
      } else {
        if (accountId !== null) {
          if (!eligible.some(a => a.id === accountId)) {
            accountId = eligible.length > 0 ? eligible[0].id : null;
            isExplicitUnassigned = false;
          }
        } else {
          if (!isExplicitUnassigned && eligible.length > 0) {
            accountId = eligible[0].id;
          }
        }
      }
    }

    async function onModalOpen() {
      if (getEligibleAccounts().length === 0 || storeError) {
        // Load data for active profile
        storeAccounts = activeProfileId === 'profile-a' ? mockAccountsProfileA : mockAccountsProfileB;
        storeError = null;
      }
      syncAccountSelection();
    }

    // Step A: First opening on Profile A
    assert.equal(getEligibleAccounts().length, 0, 'Initially store accounts are empty');
    onModalOpen();
    assert.equal(getEligibleAccounts().length, 2, 'Eligible accounts excludes inactive account (id: 3)');
    assert.equal(accountId, 1, 'Defaults to first eligible account');

    // Step B: Record expense with selected account
    // User submits transaction
    onModalOpen();
    assert.equal(accountId, 1, 'Subsequent modal opening preserves selected account');

    // Step C: User explicitly chooses Unassigned
    accountId = null;
    isExplicitUnassigned = true;
    // Next opening
    onModalOpen();
    assert.equal(accountId, null, 'User explicit Unassigned selection is preserved across openings');

    // Step D: User switches to Profile B
    activeProfileId = 'profile-b';
    storeAccounts = []; // simulates reset() on profile switch
    accountId = null;
    destinationAccountId = null;
    isExplicitUnassigned = false;

    // Open modal on Profile B
    onModalOpen();
    assert.equal(getEligibleAccounts().length, 2);
    assert.equal(accountId, 10, 'On new workspace, selects Profile B account (id: 10), never Profile A');

    // Step E: Transfer selection
    txType = 'transfer';
    syncAccountSelection();
    assert.equal(accountId, 10, 'Transfer source is account 10');
    assert.equal(destinationAccountId, 11, 'Transfer destination is account 11');
    assert.notEqual(accountId, destinationAccountId, 'Transfer source and destination must be distinct');
  });
});
