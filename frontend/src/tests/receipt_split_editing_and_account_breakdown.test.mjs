import { test, describe } from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';

describe('Finance Hub Receipt Split Shared-Field Editing & Account Balance Breakdown Contract Tests', () => {
  const rootDir = path.resolve(process.cwd());

  test('1. Split Expense modal provides shared-field editing, account preservation, and approval confirmation', () => {
    const splitModalPath = path.join(rootDir, 'src/components/SplitExpenseModal.vue');
    const content = fs.readFileSync(splitModalPath, 'utf8');

    // Shared field inputs
    assert.ok(
      content.includes('data-testid="split-shared-merchant-input"'),
      'SplitExpenseModal must have editable shared merchant input'
    );
    assert.ok(
      content.includes('data-testid="split-shared-date-input"'),
      'SplitExpenseModal must have editable shared transaction date input'
    );
    assert.ok(
      content.includes('data-testid="split-shared-account-select"'),
      'SplitExpenseModal must have editable shared payment account dropdown'
    );
    assert.ok(
      content.includes('data-testid="split-shared-notes-input"'),
      'SplitExpenseModal must have editable shared notes input'
    );

    // Unassigned account notice and confirmation support
    assert.ok(
      content.includes('Account unassigned'),
      'SplitExpenseModal must make unassigned account clearly visible'
    );
    assert.ok(
      content.includes('Unassigned (No account)'),
      'SplitExpenseModal must support approving unassigned expenses'
    );

    // Confirmation step before ledger approval
    assert.ok(
      content.includes('isConfirmingApproval'),
      'SplitExpenseModal must provide a confirmation view before approving to ledger'
    );
    assert.ok(
      content.includes('data-testid="split-confirmation-view"'),
      'SplitExpenseModal must render split-confirmation-view showing provenance and allocations'
    );
    assert.ok(
      content.includes('data-testid="split-confirm-approve-btn"'),
      'SplitExpenseModal must require explicit confirmation to approve into ledger'
    );
    assert.ok(
      content.includes('data-testid="split-back-btn"'),
      'SplitExpenseModal must allow going back to edit allocations from confirmation view'
    );

    // Payload includes edited shared values
    assert.ok(
      content.includes('account_id: sharedAccountId.value'),
      'Split payload must pass user-selected shared account_id'
    );
    assert.ok(
      content.includes('merchant: sharedMerchant.value'),
      'Split payload must pass user-edited shared merchant'
    );
  });

  test('2. UnifiedImportModal and StagingView integrate shared account and provenance preservation', () => {
    const unifiedModalPath = path.join(rootDir, 'src/components/UnifiedImportModal.vue');
    const stagingViewPath = path.join(rootDir, 'src/views/StagingView.vue');
    const uContent = fs.readFileSync(unifiedModalPath, 'utf8');
    const sContent = fs.readFileSync(stagingViewPath, 'utf8');

    // Both pass accounts to SplitExpenseModal
    assert.ok(
      uContent.includes(':accounts="accountsStore.accounts"'),
      'UnifiedImportModal must pass accounts to SplitExpenseModal'
    );
    assert.ok(
      sContent.includes(':accounts="accountsStore.accounts"'),
      'StagingView must pass accounts to SplitExpenseModal'
    );

    // UnifiedImportModal updates review items with resolved account and merchant on queue
    assert.ok(
      uContent.includes('resolvedAccountId'),
      'UnifiedImportModal must preserve edited shared account when queuing splits'
    );
    assert.ok(
      uContent.includes('resolvedMerchant'),
      'UnifiedImportModal must preserve edited shared merchant when queuing splits'
    );
  });

  test('3. AccountCard provides accessible inspect trigger while isolating Edit and Reconcile', () => {
    const cardPath = path.join(rootDir, 'src/components/AccountCard.vue');
    const content = fs.readFileSync(cardPath, 'utf8');

    // Click and keyboard interaction on card root
    assert.ok(
      content.includes("@click=\"$emit('inspect', account)\""),
      'AccountCard must emit inspect on card click'
    );
    assert.ok(
      content.includes('role="button"'),
      'AccountCard root must have role="button"'
    );
    assert.ok(
      content.includes('tabindex="0"'),
      'AccountCard root must be keyboard focusable (tabindex="0")'
    );
    assert.ok(
      content.includes("@keydown.enter.self=\"$emit('inspect', account)\""),
      'AccountCard must handle Enter key to inspect'
    );

    // Edit and Reconcile click.stop isolation
    assert.ok(
      content.includes("@click.stop=\"$emit('edit', account)\""),
      'AccountCard Edit button must stop click propagation'
    );
    assert.ok(
      content.includes("@click.stop=\"$emit('reconcile', account)\""),
      'AccountCard Reconcile button must stop click propagation'
    );

    // Credit card liability visual tag
    assert.ok(
      content.includes("account.account_type === 'credit_card'"),
      'AccountCard must visually identify credit cards as liabilities'
    );
  });

  test('4. DashboardView groups accounts into semantic groups and hosts AccountDetailModal', () => {
    const dashPath = path.join(rootDir, 'src/views/DashboardView.vue');
    const content = fs.readFileSync(dashPath, 'utf8');

    // Account groups
    assert.ok(
      content.includes('data-testid="dashboard-account-groups"'),
      'DashboardView must render grouped accounts container'
    );
    assert.ok(
      content.includes('Depository Accounts'),
      'DashboardView must group depository accounts'
    );
    assert.ok(
      content.includes('Credit Liabilities'),
      'DashboardView must group credit liabilities'
    );
    assert.ok(
      content.includes('Investment Portfolios'),
      'DashboardView must group investment portfolios'
    );

    // Account detail modal integration
    assert.ok(
      content.includes('AccountDetailModal'),
      'DashboardView must import AccountDetailModal'
    );
    assert.ok(
      content.includes(':account-id="selectedDetailAccountId"'),
      'DashboardView must pass selectedDetailAccountId to AccountDetailModal'
    );
    assert.ok(
      content.includes('@inspect="openAccountDetailModal"'),
      'DashboardView must handle @inspect event from AccountCard'
    );
  });

  test('5. AccountDetailModal displays ground-truth balance equation, liability notes, and reconciliation history', () => {
    const detailModalPath = path.join(rootDir, 'src/components/AccountDetailModal.vue');
    const content = fs.readFileSync(detailModalPath, 'utf8');

    // Ground-truth equation
    assert.ok(
      content.includes('Ground-Truth Balance Equation'),
      'AccountDetailModal must display ground-truth balance equation'
    );
    assert.ok(
      content.includes('Post-Anchor Movement'),
      'AccountDetailModal must show post-anchor movement'
    );
    assert.ok(
      content.includes('formatted_net_movement'),
      'AccountDetailModal must display net movement'
    );

    // Credit card liability explanation
    assert.ok(
      content.includes('data-testid="credit-card-liability-box"'),
      'AccountDetailModal must render credit liability box'
    );
    assert.ok(
      content.includes('formatted_amount_owed'),
      'AccountDetailModal must show formatted amount owed for credit cards'
    );

    // Investment holdings derivation
    assert.ok(
      content.includes('data-testid="investment-holdings-box"'),
      'AccountDetailModal must render investment holdings box'
    );
    assert.ok(
      content.includes('holdings_count'),
      'AccountDetailModal must show holdings count'
    );

    // Separation of Ground-Truth Anchors vs Observational Snapshots
    assert.ok(
      content.includes('Ground-Truth Balance Anchors'),
      'AccountDetailModal must explicitly identify ground-truth anchors'
    );
    assert.ok(
      content.includes('Observational Reconciliation Snapshots'),
      'AccountDetailModal must explicitly separate observational reconciliation snapshots'
    );

    // Recent activity list
    assert.ok(
      content.includes('data-testid="account-recent-activity"'),
      'AccountDetailModal must render recent activity tab'
    );
  });

  test('6. TypeScript types and API client declare full AccountBreakdown contract', () => {
    const typesPath = path.join(rootDir, 'src/types/index.ts');
    const clientPath = path.join(rootDir, 'src/api/client.ts');
    const typesContent = fs.readFileSync(typesPath, 'utf8');
    const clientContent = fs.readFileSync(clientPath, 'utf8');

    // Type declarations
    assert.ok(
      typesContent.includes('export interface AccountBreakdownResponse'),
      'types/index.ts must export AccountBreakdownResponse'
    );
    assert.ok(
      typesContent.includes('export interface AccountBreakdownAnchor'),
      'types/index.ts must export AccountBreakdownAnchor'
    );
    assert.ok(
      typesContent.includes('export interface AccountBreakdownMovement'),
      'types/index.ts must export AccountBreakdownMovement'
    );
    assert.ok(
      typesContent.includes('export interface AccountBreakdownLiability'),
      'types/index.ts must export AccountBreakdownLiability'
    );
    assert.ok(
      typesContent.includes('export interface AccountBreakdownInvestment'),
      'types/index.ts must export AccountBreakdownInvestment'
    );

    // StagingSplitRequest updated
    assert.ok(
      typesContent.includes('account_id?: number | null;'),
      'StagingSplitRequest must declare optional account_id'
    );
    assert.ok(
      typesContent.includes('merchant?: string | null;'),
      'StagingSplitRequest must declare optional merchant'
    );

    // API client exposes breakdown
    assert.ok(
      clientContent.includes('getAccountBreakdown:'),
      'api in client.ts must expose getAccountBreakdown method'
    );
    assert.ok(
      clientContent.includes('/accounts/${id}/breakdown'),
      'getAccountBreakdown must target /accounts/${id}/breakdown'
    );
  });
});

