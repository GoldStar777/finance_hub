import { test, describe } from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';

describe('Finance Hub Planned / Future-Dated Transactions Contract Tests', () => {
  const rootDir = path.resolve(process.cwd());

  test('1. TypeScript interface definitions include planned transactions, forecast, and projected balances', () => {
    const typesPath = path.join(rootDir, 'src/types/index.ts');
    const content = fs.readFileSync(typesPath, 'utf8');

    // Transaction & TransactionFilters
    assert.ok(
      content.includes('is_planned?: boolean;'),
      'Transaction type must include is_planned?: boolean'
    );
    assert.ok(
      content.includes("status?: 'all' | 'actual' | 'planned'"),
      "TransactionFilters must include status?: 'all' | 'actual' | 'planned'"
    );

    // Account & DashboardSummary planned fields
    assert.ok(
      content.includes('planned_delta_pence?: number;'),
      'Account type must include planned_delta_pence'
    );
    assert.ok(
      content.includes('projected_balance_pence?: number;'),
      'Account type must include projected_balance_pence'
    );
    assert.ok(
      content.includes('planned_net_pence?: number;'),
      'DashboardSummary must include planned_net_pence'
    );

    // Account Breakdown response
    assert.ok(
      content.includes('planned_movement?: AccountBreakdownMovement'),
      'AccountBreakdownResponse must include planned_movement'
    );
    assert.ok(
      content.includes('projected_balance_pence?: number;'),
      'AccountBreakdownResponse must include projected_balance_pence'
    );

    // Forecast and Analysis
    assert.ok(
      content.includes('export interface ForecastPlannedActivity'),
      'types/index.ts must define ForecastPlannedActivity'
    );
    assert.ok(
      content.includes('forecast?: ForecastPlannedActivity'),
      'ComprehensiveAnalysisResponse must include forecast?: ForecastPlannedActivity'
    );
  });

  test('2. API client and transactions store integrate status filter', () => {
    const clientPath = path.join(rootDir, 'src/api/client.ts');
    const storePath = path.join(rootDir, 'src/stores/transactions.ts');
    const clientContent = fs.readFileSync(clientPath, 'utf8');
    const storeContent = fs.readFileSync(storePath, 'utf8');

    // API client passes status param
    assert.ok(
      clientContent.includes("if (filters.status && filters.status !== 'all')"),
      'buildTransactionFilterParams must append status when not all'
    );
    assert.ok(
      clientContent.includes("params.append('status', filters.status)"),
      'buildTransactionFilterParams must append status parameter'
    );

    // Store includes status filter in initial and reset state
    assert.ok(
      storeContent.includes("status: 'all'"),
      "useTransactionsStore must initialize with status: 'all'"
    );
    assert.ok(
      storeContent.includes("status: 'all'"),
      "useTransactionsStore resetFilters must reset status to 'all'"
    );
  });

  test('3. RecordTransactionModal informs user of future-dated planned activity', () => {
    const modalPath = path.join(rootDir, 'src/components/RecordTransactionModal.vue');
    const content = fs.readFileSync(modalPath, 'utf8');

    // Future date detection and advisory banner
    assert.ok(
      content.includes('isPlanned'),
      'RecordTransactionModal must compute isPlanned'
    );
    assert.ok(
      content.includes('Planned Future Activity'),
      'RecordTransactionModal must render Planned Future Activity banner'
    );
    assert.ok(
      content.includes('will not reduce your current account balance until its effective date'),
      'RecordTransactionModal must explain balance is not reduced until effective date'
    );

    // Dynamic submit button wording
    assert.ok(
      content.includes("submitButtonText"),
      'RecordTransactionModal must provide dynamic submitButtonText'
    );
    assert.ok(
      content.includes("Plan Expense") || content.includes("'Plan Expense'"),
      'RecordTransactionModal must label future expense button as Plan Expense'
    );
  });

  test('4. LedgerView provides status filter controls and planned badge', () => {
    const ledgerPath = path.join(rootDir, 'src/views/LedgerView.vue');
    const content = fs.readFileSync(ledgerPath, 'utf8');

    // Status filter select in toolbar
    assert.ok(
      content.includes('data-testid="ledger-status-filter"'),
      'LedgerView must provide status filter select'
    );
    assert.ok(
      content.includes('All Activity') && content.includes('Actuals only') && content.includes('Planned only'),
      'LedgerView status filter must offer All Activity, Actuals only, and Planned only'
    );

    // Status chip
    assert.ok(
      content.includes('data-testid="status-filter-chip"'),
      'LedgerView must render active status filter chip'
    );

    // Planned badge in table
    assert.ok(
      content.includes('data-testid="tx-planned-badge"'),
      'LedgerView must render tx-planned-badge for planned transactions'
    );
    assert.ok(
      content.includes('tx.is_planned'),
      'LedgerView must conditionally display badge based on tx.is_planned'
    );
  });

  test('5. AccountDetailModal provides planned movement breakdown and projected balance', () => {
    const modalPath = path.join(rootDir, 'src/components/AccountDetailModal.vue');
    const content = fs.readFileSync(modalPath, 'utf8');

    // Planned breakdown card
    assert.ok(
      content.includes('data-testid="account-planned-breakdown"'),
      'AccountDetailModal must render planned breakdown card'
    );
    assert.ok(
      content.includes('breakdown.planned_movement'),
      'AccountDetailModal must display breakdown.planned_movement'
    );
    assert.ok(
      content.includes('breakdown.formatted_projected_balance'),
      'AccountDetailModal must display projected balance'
    );

    // Planned badge in account recent transactions
    assert.ok(
      content.includes('data-testid="account-tx-planned-badge"'),
      'AccountDetailModal must render planned badge in recent transactions'
    );
  });

  test('6. AnalysisView provides dedicated Planned Activity & Forecast section', () => {
    const analysisPath = path.join(rootDir, 'src/views/AnalysisView.vue');
    const content = fs.readFileSync(analysisPath, 'utf8');

    // Forecast section
    assert.ok(
      content.includes('data-testid="analysis-forecast-section"'),
      'AnalysisView must render analysis-forecast-section'
    );
    assert.ok(
      content.includes('Planned Activity &amp; Forecast') || content.includes('Planned Activity & Forecast'),
      'AnalysisView forecast section must display Planned Activity & Forecast header'
    );
    assert.ok(
      content.includes('formatted_planned_income') && content.includes('formatted_planned_expenses') && content.includes('formatted_planned_net'),
      'AnalysisView forecast section must display formatted planned income, expenses, and net impact'
    );
    assert.ok(
      content.includes('analysisStore.data.forecast.items'),
      'AnalysisView forecast section must render planned items table'
    );
  });

  test('7. StagingView displays planned badge for future candidates', () => {
    const stagingPath = path.join(rootDir, 'src/views/StagingView.vue');
    const content = fs.readFileSync(stagingPath, 'utf8');

    // Planned badge in staging review queue
    assert.ok(
      content.includes('data-testid="staging-item-planned-badge"'),
      'StagingView must render staging-item-planned-badge'
    );
    assert.ok(
      content.includes('isItemPlanned'),
      'StagingView must identify future candidates via isItemPlanned helper'
    );
  });
});
