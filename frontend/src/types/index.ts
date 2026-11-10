export type AccountType = 'current' | 'savings' | 'cash' | 'credit_card' | 'investment';
export type CategoryType = 'expense' | 'income';
export type ExpenseNature = 'fixed' | 'variable' | 'unclassified';
export type TransactionType = 'income' | 'expense' | 'transfer' | 'adjustment';

export interface Account {
  id: number;
  name: string;
  account_type: AccountType;
  currency: string;
  color: string;
  is_active: boolean;
  valuation_mode?: 'snapshot' | 'holdings';
  holdings_count?: number;
  has_unvalued_holdings?: boolean;
  last_reconciled_at?: string | null;
  last_reconciled_discrepancy_pence?: number | null;
  starting_balance_pence: number;
  starting_balance_pounds: number;
  current_balance_pence: number;
  current_balance_pounds: number;
  formatted_balance: string;
  anchor_label?: string;
  anchor_date?: string;
  anchor_balance_pence?: number;
  delta_since_anchor_pence?: number;
  is_opening_anchor?: boolean;
  projected_balance_pence?: number;
  formatted_projected_balance?: string;
  planned_delta_pence?: number;
  formatted_planned_delta?: string;
  created_at?: string;
}

export interface AccountCreatePayload {
  name: string;
  account_type: AccountType;
  currency?: string;
  color?: string;
  starting_balance: number;
  as_of_mode?: 'now' | 'date';
  as_of_date?: string;
  valuation_mode?: 'snapshot' | 'holdings';
}

export interface AccountBalanceAnchor {
  id: number;
  account_id: number;
  balance_pence: number;
  balance_pounds: number;
  formatted_balance: string;
  anchor_date: string;
  is_opening: boolean;
  notes?: string | null;
  created_at: string;
}

export interface AccountBalanceAnchorCreatePayload {
  balance: number;
  as_of_mode: 'now' | 'date';
  as_of_date?: string;
  notes?: string;
}

export interface DashboardSummary {
  net_worth_pence: number;
  net_worth_pounds: number;
  formatted_net_worth: string;

  total_liquid_pence: number;
  total_liquid_pounds: number;
  formatted_total_liquid: string;

  total_debt_pence: number;
  total_debt_pounds: number;
  formatted_total_debt: string;

  total_invested_pence: number;
  total_invested_pounds: number;
  formatted_total_invested: string;

  planned_income_pence?: number;
  planned_expenses_pence?: number;
  planned_net_pence?: number;
  planned_count?: number;
  formatted_planned_net?: string;
}

export interface Category {
  id: number;
  name: string;
  category_type: CategoryType;
  color: string;
  default_expense_nature: ExpenseNature;
  is_active: boolean;
  description?: string | null;
  transaction_count?: number;
}

export interface CategoryCreatePayload {
  name: string;
  category_type?: CategoryType;
  color?: string;
  default_expense_nature?: ExpenseNature;
  description?: string | null;
}

export interface CategoryUpdatePayload {
  name?: string;
  category_type?: CategoryType;
  reassign_existing_to_id?: number | null;
  color?: string;
  default_expense_nature?: ExpenseNature;
  is_active?: boolean;
  description?: string | null;
}

export interface AccountUpdatePayload {
  name?: string;
  account_type?: AccountType;
  color?: string;
  is_active?: boolean;
  valuation_mode?: 'snapshot' | 'holdings';
  starting_balance?: number;
  as_of_mode?: 'now' | 'date';
  as_of_date?: string;
}

export interface AccountDeletionImpact {
  account_id: number;
  account_name: string;
  currency: string;
  transaction_count: number;
  transfer_count: number;
  snapshot_count: number;
  holding_count: number;
  holding_valuation_count: number;
}

export interface CategoryDeletionImpact {
  category_id: number;
  category_name: string;
  category_type?: CategoryType;
  transaction_count: number;
}

export interface Transaction {
  id: number;
  transaction_date: string;
  effective_timestamp?: string | null;
  created_at?: string | null;
  transaction_type: TransactionType;
  amount_pence: number;
  amount_pounds: number;
  formatted_amount: string;
  merchant?: string | null;
  display_merchant?: string;
  notes?: string | null;
  entry_method: string;
  receipt_path?: string | null;
  account_id?: number | null;
  account_name?: string | null;
  account_color?: string | null;
  is_unassigned?: boolean;
  destination_account_id?: number | null;
  destination_account_name?: string | null;
  destination_account_color?: string | null;
  category_id?: number | null;
  category_name?: string | null;
  category_color?: string | null;
  category_type?: CategoryType | null;
  expense_nature: ExpenseNature;
  original_amount?: number | null;
  original_currency?: string | null;
  exchange_rate?: number | null;
  formatted_original_amount?: string | null;
  is_implied_rate?: boolean;
  implied_effective_rate_label?: string | null;
  is_planned?: boolean;
  deleted_at?: string | null;
  deletion_batch_id?: string | null;
  is_deleted?: boolean;
  repeat_series_id?: string | null;
}

export type RepeatFrequency = 'weekly' | 'biweekly' | 'monthly' | 'quarterly' | 'yearly';
export type RepeatEndMode = 'end_date' | 'count';

export interface RepeatTransactionCreatePayload {
  transaction_type: TransactionType;
  amount?: number;
  merchant?: string | null;
  account_id?: number | null;
  destination_account_id?: number | null;
  category_id?: number | null;
  expense_nature?: ExpenseNature | null;
  notes?: string;
  original_amount?: number | null;
  original_currency?: string | null;
  exchange_rate?: number | null;
  frequency: RepeatFrequency;
  first_date: string;
  end_mode: RepeatEndMode;
  last_date?: string;
  occurrence_count?: number;
  idempotency_key?: string;
}

export interface RepeatTransactionCreateResponse {
  series_id: string;
  idempotency_key: string;
  frequency: RepeatFrequency;
  first_date: string;
  last_date: string;
  end_mode: RepeatEndMode;
  created_count: number;
  idempotent_replay: boolean;
  message: string;
  items: Transaction[];
}

export interface TransactionCreatePayload {
  transaction_type: TransactionType;
  amount?: number;
  merchant?: string | null;
  account_id?: number | null;
  destination_account_id?: number | null;
  category_id?: number | null;
  expense_nature?: ExpenseNature | null;
  transaction_date?: string;
  notes?: string;
  original_amount?: number | null;
  original_currency?: string | null;
  exchange_rate?: number | null;
}

export interface TransactionUpdatePayload {
  transaction_type?: TransactionType;
  amount?: number;
  merchant?: string | null;
  account_id?: number | null;
  destination_account_id?: number | null;
  category_id?: number | null;
  expense_nature?: ExpenseNature | null;
  transaction_date?: string;
  notes?: string;
  original_amount?: number | null;
  original_currency?: string | null;
  exchange_rate?: number | null;
}

export interface TransactionListResponse {
  items: Transaction[];
  total: number;
  limit: number;
  offset: number;
  range_start_date?: string | null;
  range_end_date?: string | null;
  can_navigate_previous?: boolean | null;
  can_navigate_next?: boolean | null;
}

export interface MatchingTransactionIdsResponse {
  ids: number[];
  total: number;
}

export interface BulkTransactionUpdatePayload {
  transaction_ids: number[];
  update_transaction_type?: boolean;
  transaction_type?: 'income' | 'expense' | null;
  update_category?: boolean;
  category_id?: number | null;
  update_account?: boolean;
  account_id?: number | null;
}

export interface BulkTransactionUpdateResult {
  updated_count: number;
  message: string;
  affected_ids: number[];
}

export interface BulkTransactionDeletePayload {
  transaction_ids: number[];
}

export interface BulkTransactionDeleteResult {
  deleted_count: number;
  deletion_batch_id: string;
  affected_transfers_count: number;
  affected_receipts_count: number;
}

export interface RestoreTransactionsPayload {
  transaction_ids?: number[];
  batch_id?: string;
}

export interface RestoreTransactionsResult {
  restored_count: number;
  restored_ids: number[];
}

export interface RecentlyDeletedSummary {
  total_deleted: number;
  total_pence: number;
  formatted_total: string;
  transfers_count: number;
  receipts_count: number;
}

export interface TransactionFilters {
  accountId?: number | string | null;
  accountIds?: (number | string)[];
  unassignedOnly?: boolean;
  categoryId?: number | string | null;
  categoryIds?: (number | string)[];
  uncategorizedOnly?: boolean;
  transactionType?: TransactionType | null;
  transactionTypes?: string[];
  expenseNature?: ExpenseNature | null;
  q?: string;
  datePreset?: string;
  dateOffset?: number;
  interval?: string;
  startDate?: string;
  endDate?: string;
  status?: 'all' | 'actual' | 'planned' | string | null;
  sortBy?: 'date' | 'amount' | 'category' | 'account' | string;
  sortOrder?: 'asc' | 'desc';
  sort_by?: 'date' | 'amount' | 'category' | 'account' | string;
  sort_order?: 'asc' | 'desc';
  limit?: number;
  offset?: number;
}

export interface SystemSettings {
  backup_automation_enabled: boolean;
  backup_frequency_days: number;
  last_backup_check_at?: string | null;
  last_successful_backup_at?: string | null;
  next_backup_due_at?: string | null;
  is_backup_overdue: boolean;
  overdue_message?: string | null;
  import_confidence_category?: 'cautious' | 'balanced' | 'permissive';
  import_confidence_account?: 'cautious' | 'balanced' | 'permissive';
}

export interface SystemSettingsUpdatePayload {
  backup_automation_enabled?: boolean;
  backup_frequency_days?: number;
  import_confidence_category?: 'cautious' | 'balanced' | 'permissive';
  import_confidence_account?: 'cautious' | 'balanced' | 'permissive';
}

export interface BackupArchiveInfo {
  filename: string;
  filepath: string;
  created_at: string;
  size_bytes: number;
  size_formatted: string;
  manifest?: {
    backup_timestamp: string;
    app_version: string;
    schema_revision: string;
    counts: {
      accounts: number;
      transactions: number;
      categories: number;
      asset_snapshots: number;
      receipt_files: number;
    };
    sha256: Record<string, string>;
  } | null;
}

export interface BackupCreationResponse {
  success: boolean;
  filename: string;
  filepath: string;
  size_formatted: string;
  created_at: string;
  manifest: any;
}

// --- Staging Review & Statement Intake Types ---

export interface DuplicateMatchInfo {
  id: number;
  transaction_date: string;
  amount_pence: number;
  merchant: string;
  account_id: number;
  account_name: string;
  transaction_type: string;
  match_reasons: string[];
}

export interface StagingItem {
  id: number;
  created_at: string;
  status: 'pending' | 'approved' | 'rejected';
  extracted_amount_pence?: number | null;
  amount_pounds?: number | null;
  formatted_amount?: string | null;
  extracted_date?: string | null;
  extracted_merchant?: string | null;
  suggested_category_name?: string | null;
  suggested_account_id?: number | null;
  suggested_account_name?: string | null;
  suggested_account_color?: string | null;
  suggested_expense_nature: ExpenseNature;
  source_type: string;
  temp_file_path?: string | null;
  receipt_url?: string | null;

  transaction_type: string;
  destination_account_id?: number | null;
  destination_account_name?: string | null;
  notes?: string | null;
  currency: string;
  original_amount?: number | null;
  original_currency?: string | null;
  exchange_rate?: number | null;
  formatted_original_amount?: string | null;
  requires_base_amount?: boolean;
  currency_conflict: boolean;
  currency_conflict_message?: string | null;
  is_potential_duplicate: boolean;
  duplicate_matches: DuplicateMatchInfo[];
  source_filename?: string | null;
  line_number?: number | null;
  ocr_confidence?: number | null;
  ocr_error?: string | null;
  anchor_status?: string | null;
  anchor_explanation?: string | null;
  anchor_mode?: string | null;
  effective_timestamp?: string | null;
  is_split?: boolean;
  split_parent_id?: number | null;
  split_index?: number | null;
  split_total?: number | null;
}

export interface StagingSplitRow {
  amount_pence: number;
  category_id?: number | null;
  category_name?: string | null;
  expense_nature?: ExpenseNature;
  notes?: string | null;
}

export interface StagingSplitRequest {
  splits: StagingSplitRow[];
  commit_to_ledger?: boolean;
  account_id?: number | null;
  transaction_date?: string | null;
  merchant?: string | null;
  notes?: string | null;
}

export interface StagingSplitResponse {
  success: boolean;
  action: 'queued' | 'approved';
  parent_id: number;
  created_item_ids: number[];
  created_items: StagingItem[];
  transaction_ids: number[];
  message: string;
}

export interface StagingItemUpdatePayload {
  merchant?: string;
  amount?: number;
  original_amount?: number | null;
  original_currency?: string | null;
  exchange_rate?: number | null;
  transaction_date?: string;
  account_id?: number;
  destination_account_id?: number | null;
  transaction_type?: TransactionType;
  category_id?: number | null;
  category_name?: string | null;
  expense_nature?: ExpenseNature;
  notes?: string | null;
  anchor_mode?: string;
  effective_timestamp?: string;
}

export interface ReviewSuggestionRecord {
  id: number;
  kind: 'staging' | 'ledger';
  date: string;
  amount_pence: number;
  formatted_amount: string;
  merchant: string;
  account_name?: string | null;
  account_id?: number | null;
  category_name?: string | null;
  direction?: string | null;
  source_type?: string | null;
  source_filename?: string | null;
}

export interface ReviewDuplicateSuggestion {
  id: string;
  type: 'duplicate';
  subtype: string;
  reasons: string[];
  record_a: ReviewSuggestionRecord;
  record_b: ReviewSuggestionRecord;
}

export interface ReviewTransferSuggestion {
  id: string;
  type: 'transfer';
  subtype: string;
  reasons: string[];
  action_explanation?: string | null;
  source_record: ReviewSuggestionRecord;
  destination_record: ReviewSuggestionRecord;
}

export interface ReviewSuggestionsSummary {
  duplicates_count: number;
  transfers_count: number;
}

export interface ReviewSuggestionsResponse {
  duplicate_suggestions: ReviewDuplicateSuggestion[];
  transfer_suggestions: ReviewTransferSuggestion[];
  summary: ReviewSuggestionsSummary;
}


export interface CurrencySpecInfo {
  code: string;
  symbol: string;
  precision: number;
  name: string;
  can_be_base: boolean;
}

export interface SystemConfig {
  base_currency: string;
  base_currency_symbol: string;
  base_currency_decimals: number;
  base_currency_name: string;
  supported_currencies?: Record<string, CurrencySpecInfo>;
  app_timezone: string;
}

export interface AccountBreakdownMovement {
  inflows_pence: number;
  formatted_inflows: string;
  outflows_pence: number;
  formatted_outflows: string;
  transfers_in_pence: number;
  formatted_transfers_in: string;
  transfers_out_pence: number;
  formatted_transfers_out: string;
  adjustments_net_pence: number;
  formatted_adjustments_net: string;
  net_movement_pence: number;
  formatted_net_movement: string;
  transaction_count: number;
}

export interface AccountBreakdownAnchor {
  has_anchor: boolean;
  anchor_id?: number | null;
  balance_pence?: number | null;
  formatted_balance?: string | null;
  anchor_date?: string | null;
  anchor_date_local?: string | null;
  is_opening: boolean;
  notes?: string | null;
  label: string;
}

export interface AccountBreakdownLiability {
  is_liability: boolean;
  amount_owed_pence: number;
  formatted_amount_owed: string;
  explanation: string;
}

export interface AccountBreakdownInvestment {
  is_investment: boolean;
  valuation_mode: string;
  holdings_count: number;
  valued_count: number;
  unvalued_count: number;
  has_unvalued_holdings: boolean;
  latest_valuation_date?: string | null;
  latest_valuation_date_formatted?: string | null;
  explanation: string;
}

export interface AccountBreakdownRecentTx {
  id: number;
  transaction_date: string;
  effective_timestamp?: string | null;
  transaction_type: string;
  amount_pence: number;
  formatted_amount: string;
  merchant?: string | null;
  notes?: string | null;
  category_name?: string | null;
  category_color?: string | null;
  is_planned?: boolean;
}

export interface AccountBreakdownResponse {
  account_id: number;
  account_name: string;
  account_type: string;
  account_group: string;
  currency: string;
  currency_symbol: string;
  color: string;
  is_active: boolean;
  current_balance_pence: number;
  formatted_current_balance: string;
  current_balance_pounds: number;
  projected_balance_pence?: number;
  formatted_projected_balance?: string;
  starting_balance_pence: number;
  formatted_starting_balance: string;
  anchor: AccountBreakdownAnchor;
  movement: AccountBreakdownMovement;
  planned_movement?: AccountBreakdownMovement | null;
  liability?: AccountBreakdownLiability | null;
  investment?: AccountBreakdownInvestment | null;
  recent_transactions: AccountBreakdownRecentTx[];
  anchors: AccountBalanceAnchor[];
  snapshots: AccountSnapshotItem[];
  app_timezone: string;
}

export interface StatementMappingConfig {
  delimiter?: string;
  has_header: boolean;
  skip_rows: number;
  date_column: string | number;
  date_format?: string;
  merchant_column: string | number;
  notes_column?: string | number | null;
  category_column?: string | number | null;
  amount_mode: 'single_standard' | 'single_inverted' | 'dual_debit_credit';
  amount_column?: string | number | null;
  debit_column?: string | number | null;
  credit_column?: string | number | null;
}

export interface StatementMappingProfile {
  id: string;
  name: string;
  version: number;
  config: StatementMappingConfig;
  default_account_id?: number | null;
  created_at?: string;
  updated_at?: string;
}

export interface StatementMappingProfileCreatePayload {
  name: string;
  config: StatementMappingConfig;
  default_account_id?: number | null;
}

export interface SkippedRowInfo {
  line_number: number;
  reason: string;
  raw: string;
}

export interface CSVImportResponse {
  batch_id: string;
  source_filename: string;
  total_rows: number;
  staged_count: number;
  skipped_count: number;
  skipped_rows: SkippedRowInfo[];
}

export interface StagingBatchApprovePayload {
  item_ids?: number[];
  include_duplicates: boolean;
}

export interface StagingBatchApproveResponse {
  approved_count: number;
  excluded_duplicates_count: number;
  error_count: number;
  errors: Array<{ id: number; error: string }>;
}

export interface StagingCountResponse {
  pending_count: number;
}

export interface UnifiedImportItem {
  id: number;
  batch_id: string;
  line_number: number;
  extracted_date: string | null;
  extracted_amount_pence: number | null;
  extracted_amount_pounds: number | null;
  extracted_merchant: string | null;
  suggested_account_id: number | null;
  suggested_account_name?: string | null;
  suggested_account_match_reason?: string | null;
  suggested_category_id?: number | null;
  suggested_category_name: string | null;
  suggested_expense_nature: ExpenseNature;
  transaction_type: TransactionType;
  currency: string;
  original_amount?: number | null;
  original_currency?: string | null;
  currency_conflict: boolean;
  currency_conflict_message?: string | null;
  is_potential_duplicate: boolean;
  duplicate_matches: any[];
  missing_fields: string[];
  source_type: string;
  temp_file_path?: string | null;
  notes?: string | null;
  date_uncertain?: boolean;
  merchant_uncertain?: boolean;
  direction_uncertain?: boolean;
  direction_evidence?: string | null;
  category_match_reason?: string | null;
}

export interface DirectionSummary {
  expense_count: number;
  income_count: number;
  uncertain_count: number;
  evidence_type: string;
  evidence_description: string;
}

export interface UnifiedImportResponse {
  batch_id: string;
  filename: string;
  file_hash?: string;
  file_size_bytes: number;
  mime_type: string;
  document_type: 'receipt' | 'statement' | 'statement_screenshot' | 'unsupported' | 'unreadable';
  document_type_label: string;
  summary: string;
  direction_summary?: DirectionSummary | null;
  items: UnifiedImportItem[];
}

export interface StagingItemUpdateWithId {
  id: number;
  merchant?: string | null;
  amount?: number | null;
  original_amount?: number | null;
  original_currency?: string | null;
  exchange_rate?: number | null;
  transaction_date?: string | null;
  account_id?: number | null;
  destination_account_id?: number | null;
  transaction_type?: TransactionType;
  category_id?: number | null;
  category_name?: string | null;
  expense_nature?: ExpenseNature;
  notes?: string | null;
}

export interface UnifiedImportCommitPayload {
  batch_id: string;
  action: 'approve_all' | 'approve_selected' | 'queue_all' | 'discard_all';
  items: StagingItemUpdateWithId[];
}

export interface UnifiedImportCommitResponse {
  action: string;
  batch_id: string;
  approved_count: number;
  queued_count: number;
  discarded_count: number;
  already_committed_count?: number;
  transaction_ids: number[];
  errors?: any[];
  message?: string;
}

// --- Investments & Portfolio Types ---

export interface Holding {
  id: number;
  account_id: number;
  name: string;
  ticker?: string;
  asset_class: string;
  currency: string;
  is_active: boolean;
  notes?: string;
  created_at?: string;
  is_valued: boolean;
  latest_quantity?: number;
  latest_unit_price_pounds?: number;
  formatted_unit_price?: string;
  latest_valuation_pence?: number;
  latest_valuation_pounds?: number;
  formatted_valuation?: string;
  last_valuation_date?: string;
}

export interface HoldingValuation {
  id: number;
  holding_id: number;
  effective_date: string;
  quantity: number;
  unit_price_pence?: number;
  unit_price_pounds?: number;
  formatted_unit_price?: string;
  valuation_pence: number;
  valuation_pounds: number;
  formatted_valuation: string;
  currency: string;
  notes?: string;
  created_at?: string;
}

export interface PortfolioAccountSummary {
  account_id: number;
  account_name: string;
  currency: string;
  color: string;
  valuation_mode: string;
  balance_pence: number;
  balance_pounds: number;
  formatted_balance: string;
  holdings_count: number;
  valued_count: number;
  unvalued_count: number;
  has_unvalued_holdings: boolean;
}

export interface AssetAllocationItem {
  asset_class: string;
  total_pence: number;
  total_pounds: number;
  percentage: number;
}

export interface PortfolioSummary {
  total_invested_pence: number;
  total_invested_pounds: number;
  formatted_total_invested: string;
  accounts: PortfolioAccountSummary[];
  asset_allocation: AssetAllocationItem[];
}

export interface AccountHoldingsResponse {
  account_id: number;
  account_name: string;
  currency: string;
  valuation_mode: string;
  total_valuation_pence: number;
  total_valuation_pounds: number;
  formatted_total_valuation: string;
  holdings_count: number;
  valued_count: number;
  unvalued_count: number;
  has_unvalued_holdings: boolean;
  holdings: Holding[];
}

export interface HoldingCreatePayload {
  name: string;
  ticker?: string;
  asset_class?: string;
  currency?: string;
  notes?: string;
  initial_quantity?: number;
  initial_unit_price?: number;
  initial_valuation?: number;
  initial_effective_date?: string;
}

export interface HoldingUpdatePayload {
  name?: string;
  ticker?: string;
  asset_class?: string;
  account_id?: number;
  is_active?: boolean;
  notes?: string;
}

export interface HoldingValuationCreatePayload {
  effective_date?: string;
  quantity: number;
  unit_price?: number;
  valuation?: number;
  notes?: string;
}

export interface CheckpointSyncResponse {
  snapshot_id: number;
  account_id: number;
  effective_date: string;
  valuation_pence: number;
  valuation_pounds: number;
  formatted_valuation: string;
  notes?: string;
}

// --- Cash Flow & Analytics Types ---

export interface CategorySpendingItem {
  category_id: number | null;
  category_name: string;
  category_color: string;
  category_type?: CategoryType;
  expense_nature: ExpenseNature | null;
  total_pence: number;
  total_pounds: number;
  formatted_total: string;
  transaction_count: number;
  percentage: number;
}

export interface MonthlyCashFlowTrendItem {
  month: string;
  month_name: string;
  income_pence: number;
  income_pounds: number;
  formatted_income: string;
  fixed_expenses_pence: number;
  variable_expenses_pence: number;
  unclassified_expenses_pence: number;
  total_expenses_pence: number;
  total_expenses_pounds: number;
  formatted_total_expenses: string;
  net_surplus_pence: number;
  net_surplus_pounds: number;
  formatted_net_surplus: string;
  savings_rate: number;
  is_savings_rate_applicable: boolean;
}

export interface CashFlowSummaryResponse {
  selected_month: string;
  month_name: string;
  prev_month: string;
  next_month: string;
  currency: string;
  currency_symbol: string;
  available_currencies: string[];
  available_months: string[];
  account_id: number | null;
  account_name: string | null;

  income_pence: number;
  income_pounds: number;
  formatted_income: string;
  income_count: number;

  fixed_expenses_pence: number;
  fixed_expenses_pounds: number;
  formatted_fixed_expenses: string;
  fixed_expenses_count: number;
  fixed_percentage: number;

  variable_expenses_pence: number;
  variable_expenses_pounds: number;
  formatted_variable_expenses: string;
  variable_expenses_count: number;
  variable_percentage: number;

  unclassified_expenses_pence: number;
  unclassified_expenses_pounds: number;
  formatted_unclassified_expenses: string;
  unclassified_expenses_count: number;
  unclassified_percentage: number;

  total_expenses_pence: number;
  total_expenses_pounds: number;
  formatted_total_expenses: string;
  expenses_count: number;

  transfers_volume_pence: number;
  transfers_volume_pounds: number;
  formatted_transfers_volume: string;
  transfers_count: number;

  adjustments_inflow_pence: number;
  adjustments_outflow_pence: number;
  adjustments_net_pence: number;
  adjustments_net_pounds: number;
  formatted_adjustments_net: string;
  adjustments_count: number;

  operating_surplus_pence: number;
  operating_surplus_pounds: number;
  formatted_operating_surplus: string;

  net_surplus_pence: number;
  net_surplus_pounds: number;
  formatted_net_surplus: string;

  savings_rate: number;
  is_savings_rate_applicable: boolean;
  formatted_savings_rate: string;

  categories: CategorySpendingItem[];
  historical_trend: MonthlyCashFlowTrendItem[];

  total_transactions_count: number;
  has_data: boolean;
}

// --- Account Reconciliation Types ---

export interface AccountSnapshotItem {
  id: number;
  account_id: number;
  snapshot_date: string;
  actual_balance_pence: number;
  actual_balance_pounds: number;
  formatted_actual_balance: string;
  calculated_balance_pence: number;
  calculated_balance_pounds: number;
  formatted_calculated_balance: string;
  discrepancy_pence: number;
  discrepancy_pounds: number;
  formatted_discrepancy: string;
  discrepancy_direction: 'exact' | 'actual_higher' | 'actual_lower';
  notes?: string | null;
}

export interface ReconciliationSummaryResponse {
  account_id: number;
  account_name: string;
  account_type: AccountType;
  currency: string;
  currency_symbol: string;
  calculated_balance_pence: number;
  calculated_balance_pounds: number;
  formatted_calculated_balance: string;
  last_reconciled_at?: string | null;
  last_snapshot?: AccountSnapshotItem | null;
  last_anchor?: AccountBalanceAnchor | null;
  snapshots_count: number;
  app_timezone?: string;
}

export interface MissingTransactionPayload {
  transaction_type: 'expense' | 'income';
  amount: number;
  merchant: string;
  category_id?: number | null;
  transaction_date?: string;
  notes?: string;
}

export interface ReconciliationSnapshotCreatePayload {
  actual_balance: number;
  as_of_mode?: 'now' | 'date';
  as_of_date?: string;
  snapshot_date?: string;
  notes?: string;
  missing_transaction?: MissingTransactionPayload;
  create_adjustment?: boolean;
  adjustment_notes?: string;
}

export interface ReconciliationResultResponse {
  snapshot: AccountSnapshotItem;
  anchor: AccountBalanceAnchor;
  explanation: string;
  missing_transaction_created: boolean;
  missing_transaction_id?: number | null;
  adjustment_created: boolean;
  adjustment_transaction_id?: number | null;
  new_calculated_balance_pence: number;
  new_calculated_balance_pounds: number;
  formatted_new_calculated_balance: string;
}

// --- Analysis & Multidimensional Reporting Types ---

export interface DateRangeInfo {
  preset: string;
  interval: string;
  start_date: string;
  end_date: string;
  app_timezone: string;
  available_presets: string[];
  available_intervals: string[];
  offset: number;
  can_navigate_previous: boolean;
  can_navigate_next: boolean;
}

export interface AnalysisTimeSeriesBucket {
  key: string;
  label: string;
  start_date: string;
  end_date: string;
  is_partial: boolean;
  partial_label?: string | null;
  income_pence: number;
  income_pounds: number;
  formatted_income: string;
  expenses_pence: number;
  expenses_pounds: number;
  formatted_expenses: string;
  net_savings_pence: number;
  net_savings_pounds: number;
  formatted_net_savings: string;
  cumulative_net_savings_pence: number;
  cumulative_net_savings_pounds: number;
  formatted_cumulative_net_savings: string;
  cumulative_income_pence: number;
  cumulative_income_pounds: number;
  formatted_cumulative_income: string;
  cumulative_expenses_pence: number;
  cumulative_expenses_pounds: number;
  formatted_cumulative_expenses: string;
  cumulative_net_flow_pence: number;
  cumulative_net_flow_pounds: number;
  formatted_cumulative_net_flow: string;
  savings_rate: number;
  is_savings_rate_applicable: boolean;
  transfers_volume_pence: number;
  formatted_transfers_volume: string;
  adjustments_net_pence: number;
  formatted_adjustments_net: string;
  fixed_expenses_pence: number;
  variable_expenses_pence: number;
  unclassified_expenses_pence: number;
  planned_income_pence?: number;
  planned_expenses_pence?: number;
  planned_net_pence?: number;
  is_planned?: boolean;
  category_spending: Record<string, number>;
  category_spending_details?: CategoryBucketSpendingItem[];
  nature_spending_details?: NatureBucketSpendingItem[];
}

export interface CategoryBucketSpendingItem {
  category_id?: number | null;
  category_name: string;
  category_color: string;
  expense_nature: string;
  amount_pence: number;
  amount_pounds: number;
  formatted_amount: string;
  percentage: number;
  transaction_count: number;
}

export interface NatureBucketSpendingItem {
  nature: string;
  label: string;
  color: string;
  amount_pence: number;
  amount_pounds: number;
  formatted_amount: string;
  percentage: number;
}

export interface AnalysisTotals {
  income_pence: number;
  income_pounds: number;
  formatted_income: string;
  expenses_pence: number;
  expenses_pounds: number;
  formatted_expenses: string;
  net_savings_pence: number;
  net_savings_pounds: number;
  formatted_net_savings: string;
  cumulative_net_savings_pence: number;
  cumulative_net_savings_pounds: number;
  formatted_cumulative_net_savings: string;
  cumulative_income_pence: number;
  cumulative_income_pounds: number;
  formatted_cumulative_income: string;
  cumulative_expenses_pence: number;
  cumulative_expenses_pounds: number;
  formatted_cumulative_expenses: string;
  cumulative_net_flow_pence: number;
  cumulative_net_flow_pounds: number;
  formatted_cumulative_net_flow: string;
  savings_rate: number;
  is_savings_rate_applicable: boolean;
  fixed_expenses_pence: number;
  formatted_fixed_expenses: string;
  fixed_percentage: number;
  variable_expenses_pence: number;
  formatted_variable_expenses: string;
  variable_percentage: number;
  unclassified_expenses_pence: number;
  formatted_unclassified_expenses: string;
  unclassified_percentage: number;
  transfers_volume_pence: number;
  formatted_transfers_volume: string;
  transfers_count: number;
  adjustments_inflow_pence: number;
  adjustments_outflow_pence: number;
  adjustments_net_pence: number;
  formatted_adjustments_net: string;
  adjustments_count: number;
}

export interface AccountBalanceSnapshotItem {
  account_id: number;
  account_name: string;
  account_type: string;
  color: string;
  balance_pence: number;
  balance_pounds: number;
  formatted_balance: string;
  is_inferred: boolean;
  inferred_warning?: string | null;
  reconciliation_discrepancy_pence?: number | null;
  reconciliation_actual_pence?: number | null;
}

export interface NetWorthBucket {
  key: string;
  label: string;
  date: string;
  is_partial: boolean;
  partial_label?: string | null;
  total_assets_pence: number;
  total_assets_pounds: number;
  formatted_total_assets: string;
  total_debt_pence: number;
  total_debt_pounds: number;
  formatted_total_debt: string;
  net_worth_pence: number;
  net_worth_pounds: number;
  formatted_net_worth: string;
  account_balances: AccountBalanceSnapshotItem[];
  has_inferred_balances: boolean;
}

export interface InvestmentAccountSummary {
  account_id: number;
  account_name: string;
  is_available: boolean;
  is_carried_forward: boolean;
  valuation_date?: string | null;
  carried_forward_date?: string | null;
  valuation_pence?: number | null;
  valuation_pounds?: number | null;
  formatted_valuation: string;
  holdings_count: number;
  valued_count: number;
  unvalued_count: number;
}

export interface PortfolioValueBucket {
  key: string;
  label: string;
  date: string;
  is_partial: boolean;
  partial_label?: string | null;
  is_available: boolean;
  is_carried_forward: boolean;
  valuation_date?: string | null;
  carried_forward_date?: string | null;
  total_valuation_pence?: number | null;
  total_valuation_pounds?: number | null;
  formatted_total_valuation: string;
  holdings_count: number;
  valued_count: number;
  unvalued_count: number;
  has_unvalued_holdings: boolean;
  accounts: InvestmentAccountSummary[];
}

export interface FilterOptionAccount {
  id: number;
  name: string;
  currency: string;
  account_type: string;
  color?: string;
}

export interface FilterOptionCategory {
  id: number;
  name: string;
  color: string;
  default_nature: string;
  category_type?: CategoryType;
}

export interface SpendingMatrixCell {
  amount_pence: number;
  amount_pounds: number;
  formatted_amount: string;
  transaction_count: number;
}

export interface SpendingMatrixRow {
  category_id?: number | null;
  category_name: string;
  category_color: string;
  category_type?: CategoryType;
  expense_nature: string;
  is_uncategorized?: boolean;
  row_total_pence: number;
  row_total_pounds: number;
  formatted_row_total: string;
  percentage: number;
  transaction_count: number;
  cells: Record<string, SpendingMatrixCell>;
}

export interface SpendingMatrixColumn {
  key: string;
  label: string;
  start_date: string;
  end_date: string;
  is_partial: boolean;
  partial_label?: string | null;
  period_total_pence: number;
  period_total_pounds: number;
  formatted_period_total: string;
}

export interface SpendingMatrixResponse {
  periods: SpendingMatrixColumn[];
  rows: SpendingMatrixRow[];
  grand_total_pence: number;
  grand_total_pounds: number;
  formatted_grand_total: string;
}

export interface ComprehensiveAnalysisResponse {
  range_info: DateRangeInfo;
  currency: string;
  currency_symbol: string;
  available_currencies: string[];
  account_id?: number | null;
  account_name?: string | null;
  account_ids?: number[];
  account_names?: string[];
  category_id?: number | null;
  category_name?: string | null;
  category_ids?: number[];
  category_names?: string[];
  available_accounts: FilterOptionAccount[];
  available_categories: FilterOptionCategory[];
  totals: AnalysisTotals;
  time_series: AnalysisTimeSeriesBucket[];
  categories: CategorySpendingItem[];
  spending_matrix?: SpendingMatrixResponse;
  income_categories?: CategorySpendingItem[];
  income_matrix?: SpendingMatrixResponse;
  net_worth_series: NetWorthBucket[];
  investments_series: PortfolioValueBucket[];
  is_investments_sparse: boolean;
  investments_sparse_explanation?: string | null;
  forecast?: ForecastPlannedActivity | null;
}

export interface ForecastPlannedActivityItem {
  id: number;
  date: string;
  transaction_type: string;
  merchant: string;
  account_name: string;
  category_name: string;
  expense_nature: string;
  amount_pence: number;
  amount_pounds: number;
  formatted_amount: string;
  notes: string;
}

export interface ForecastPlannedActivity {
  has_planned_activity: boolean;
  planned_income_pence: number;
  planned_income_pounds: number;
  formatted_planned_income: string;
  planned_expenses_pence: number;
  planned_expenses_pounds: number;
  formatted_planned_expenses: string;
  planned_net_pence: number;
  planned_net_pounds: number;
  formatted_planned_net: string;
  planned_transactions_count: number;
  items: ForecastPlannedActivityItem[];
}

export interface AnalysisQueryParams {
  preset?: string;
  start_date?: string;
  end_date?: string;
  interval?: string;
  currency?: string;
  account_id?: number | null;
  account_ids?: number[];
  category_id?: number | null;
  category_ids?: number[];
  offset?: number;
}

export type AnalysisExportReportType =
  | 'spending_matrix'
  | 'income_matrix'
  | 'overview_cashflow'
  | 'spending_categories'
  | 'income_categories'
  | 'net_worth'
  | 'investments';

export type AnalysisExportFormat = 'csv' | 'xlsx';

export interface ProfileMetadata {
  id: string;
  name: string;
  created_at: string;
  is_archived: boolean;
  is_default: boolean;
  is_active: boolean;
}

export interface ProfileCreatePayload {
  name: string;
}

export interface ProfileUpdatePayload {
  name?: string;
  is_archived?: boolean;
}

export interface ProfileImpactResponse {
  profile_id: string;
  profile_name: string;
  is_active: boolean;
  is_default: boolean;
  can_delete: boolean;
  blocking_reason?: string | null;
  accounts_count: number;
  transactions_count: number;
  categories_count: number;
  holdings_count: number;
  staging_items_count: number;
  receipt_files_count: number;
  backup_files_count: number;
  disk_usage_bytes: number;
  disk_usage_formatted: string;
}

export interface ProfileDeletePayload {
  confirm_name: string;
}

// --- Data Quality & Review Types ---

export type DataQualityFindingType =
  | 'uncategorised'
  | 'unassigned_account'
  | 'potential_duplicate'
  | 'possible_transfer'
  | 'uncertain_import'
  | 'archived_reference'
  | 'integrity_issue';

export type DataQualitySeverity = 'integrity' | 'review' | 'suggestion';

export interface DataQualitySummary {
  total_active: number;
  dismissed_count: number;
  by_type: Record<string, number>;
  by_severity: Record<string, number>;
  scanned_transactions_count: number;
  scanned_staging_count: number;
}

export interface DataQualityComparisonBlock {
  record_a?: ReviewSuggestionRecord;
  record_b?: ReviewSuggestionRecord;
  source_record?: ReviewSuggestionRecord;
  destination_record?: ReviewSuggestionRecord;
}

export interface DataQualityFinding {
  id: string;
  finding_type: DataQualityFindingType;
  severity: DataQualitySeverity;
  confidence: string;
  title: string;
  summary: string;
  reasons: string[];
  source: string;
  subtype: string;
  record_kind: string;
  transaction_id?: number | null;
  related_transaction_id?: number | null;
  staging_id?: number | null;
  transaction_type?: string | null;
  date?: string | null;
  amount_pence?: number | null;
  formatted_amount?: string | null;
  merchant?: string | null;
  account_id?: number | null;
  destination_account_id?: number | null;
  account_name?: string | null;
  category_id?: number | null;
  category_name?: string | null;
  category_type?: CategoryType | null;
  expected_category_type?: CategoryType | null;
  can_dismiss: boolean;
  is_dismissed: boolean;
  ledger_url?: string | null;
  queue_url?: string | null;
  suggested_action?: string | null;
  suggested_category_id?: number | null;
  suggested_category_name?: string | null;
  action_explanation?: string | null;
  comparison?: DataQualityComparisonBlock | null;
}

export interface DataQualityReportResponse {
  profile_id: string;
  app_timezone: string;
  base_currency: string;
  confidence_settings: {
    category: string;
    account: string;
  };
  summary: DataQualitySummary;
  filtered_count: number;
  findings: DataQualityFinding[];
}

export interface DataQualityFindingsQuery {
  finding_type?: string;
  severity?: string;
  q?: string;
  account_id?: string | number | null;
  category_id?: string | number | null;
  start_date?: string;
  end_date?: string;
  include_dismissed?: boolean;
}











