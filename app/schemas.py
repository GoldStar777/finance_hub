from datetime import datetime, date
from typing import Optional, List, Union, Dict, Any, Literal
from pydantic import BaseModel, ConfigDict, Field
from app.models import AccountType, CategoryType, ExpenseNature, TransactionType
from app.core.currency import pounds_to_pence, pence_to_pounds, format_pence

# --- Account Schemas ---
class AccountBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    account_type: AccountType
    currency: Optional[str] = Field(None, max_length=3)
    color: str = Field(default="#3B82F6", max_length=20)

class AccountCreate(AccountBase):
    starting_balance: float = Field(default=0.0)
    as_of_mode: Optional[str] = Field(default="now", description="'now' or 'date'")
    as_of_date: Optional[str] = Field(default=None, description="ISO date 'YYYY-MM-DD' when as_of_mode is 'date'")
    valuation_mode: Optional[str] = Field(default=None, pattern="^(snapshot|holdings)$")

    @property
    def starting_balance_pence(self) -> int:
        return pounds_to_pence(self.starting_balance)

class AccountUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    account_type: Optional[AccountType] = None
    currency: Optional[str] = Field(None, max_length=3)
    color: Optional[str] = Field(None, max_length=20)
    is_active: Optional[bool] = None
    valuation_mode: Optional[str] = Field(None, pattern="^(snapshot|holdings)$")
    starting_balance: Optional[float] = None
    as_of_mode: Optional[str] = None
    as_of_date: Optional[str] = None

class AccountResponse(AccountBase):
    id: int
    starting_balance_pence: int
    starting_balance_pounds: float
    current_balance_pence: int
    current_balance_pounds: float
    formatted_balance: str
    is_active: bool
    valuation_mode: str = "snapshot"
    holdings_count: int = 0
    has_unvalued_holdings: bool = False
    last_reconciled_at: Optional[datetime] = None
    last_reconciled_discrepancy_pence: Optional[int] = None
    created_at: Optional[datetime] = None
    anchor_label: Optional[str] = None
    anchor_date: Optional[datetime] = None
    anchor_balance_pence: Optional[int] = None
    delta_since_anchor_pence: int = 0
    is_opening_anchor: bool = True
    planned_delta_pence: int = 0
    formatted_planned_delta: str = "£0.00"
    projected_balance_pence: Optional[int] = None
    formatted_projected_balance: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class AccountBalanceAnchorCreate(BaseModel):
    balance: float = Field(..., description="Balance in major currency units (e.g. pounds)")
    as_of_mode: str = Field(default="now", description="'now' or 'date'")
    as_of_date: Optional[str] = Field(default=None, description="ISO date 'YYYY-MM-DD' when as_of_mode is 'date'")
    notes: Optional[str] = Field(default=None, max_length=255)

class AccountBalanceAnchorResponse(BaseModel):
    id: int
    account_id: int
    balance_pence: int
    balance_pounds: float
    formatted_balance: str
    anchor_date: datetime
    is_opening: bool
    notes: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class AccountDeletionImpact(BaseModel):
    account_id: int
    account_name: str
    currency: str
    transaction_count: int
    transfer_count: int
    snapshot_count: int
    holding_count: int
    holding_valuation_count: int

# --- Category Schemas ---
class CategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    category_type: CategoryType = CategoryType.EXPENSE
    color: str = Field(default="#8B5CF6", max_length=20)
    default_expense_nature: ExpenseNature = ExpenseNature.UNCLASSIFIED
    description: Optional[str] = Field(default=None, max_length=500)

class CategoryCreate(CategoryBase):
    pass

class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    category_type: Optional[CategoryType] = None
    reassign_existing_to_id: Optional[int] = Field(
        default=None,
        description="Optional active category ID of the previous purpose to safely reassign existing transactions before changing category_type."
    )
    color: Optional[str] = Field(None, max_length=20)
    default_expense_nature: Optional[ExpenseNature] = None
    is_active: Optional[bool] = None
    description: Optional[str] = Field(default=None, max_length=500)

class CategoryResponse(CategoryBase):
    id: int
    is_active: bool
    transaction_count: int = 0
    model_config = ConfigDict(from_attributes=True)

class CategoryDeletionImpact(BaseModel):
    category_id: int
    category_name: str
    category_type: CategoryType = CategoryType.EXPENSE
    transaction_count: int

# --- Dashboard Summary ---
class DashboardSummaryResponse(BaseModel):
    net_worth_pence: int
    net_worth_pounds: float
    formatted_net_worth: str

    total_liquid_pence: int
    total_liquid_pounds: float
    formatted_total_liquid: str

    total_debt_pence: int
    total_debt_pounds: float
    formatted_total_debt: str

    total_invested_pence: int
    total_invested_pounds: float
    formatted_total_invested: str

    planned_income_pence: int = 0
    planned_expenses_pence: int = 0
    planned_net_pence: int = 0
    planned_count: int = 0
    formatted_planned_net: str = "£0.00"

# --- Transaction Schemas ---
class TransactionCreate(BaseModel):
    transaction_type: TransactionType
    amount: Optional[float] = Field(None, gt=0, description="Amount in base currency")
    merchant: Optional[str] = Field(None, max_length=255)
    account_id: Optional[int] = None
    destination_account_id: Optional[int] = None
    category_id: Optional[int] = None
    expense_nature: Optional[ExpenseNature] = None
    transaction_date: Optional[datetime] = None
    effective_timestamp: Optional[datetime] = None
    notes: Optional[str] = None
    original_amount: Optional[float] = Field(None, gt=0, description="Amount in original foreign currency")
    original_currency: Optional[str] = Field(None, min_length=3, max_length=3, description="ISO 4217 original currency code")
    exchange_rate: Optional[float] = Field(None, gt=0, description="Base currency per 1 unit of original currency")

class TransactionUpdate(BaseModel):
    transaction_type: Optional[TransactionType] = None
    amount: Optional[float] = Field(None, gt=0, description="Amount in base currency")
    merchant: Optional[str] = Field(None, max_length=255)
    account_id: Optional[int] = None
    destination_account_id: Optional[int] = None
    category_id: Optional[int] = None
    expense_nature: Optional[ExpenseNature] = None
    transaction_date: Optional[datetime] = None
    effective_timestamp: Optional[datetime] = None
    notes: Optional[str] = None
    original_amount: Optional[float] = Field(None, gt=0)
    original_currency: Optional[str] = Field(None, min_length=3, max_length=3)
    exchange_rate: Optional[float] = Field(None, gt=0)

class TransactionResponse(BaseModel):
    id: int
    transaction_date: datetime
    effective_timestamp: Optional[datetime] = None
    created_at: Optional[datetime] = None
    transaction_type: TransactionType
    amount_pence: int
    amount_pounds: float
    formatted_amount: str
    merchant: Optional[str] = None
    display_merchant: str = "Merchant not recorded"
    notes: Optional[str] = None
    entry_method: str
    receipt_path: Optional[str] = None
    receipt_url: Optional[str] = None
    account_id: Optional[int] = None
    account_name: Optional[str] = None
    account_color: Optional[str] = None
    is_unassigned: bool = False
    destination_account_id: Optional[int] = None
    destination_account_name: Optional[str] = None
    destination_account_color: Optional[str] = None
    destination_transaction_date: Optional[datetime] = None
    destination_effective_timestamp: Optional[datetime] = None
    destination_merchant: Optional[str] = None
    destination_notes: Optional[str] = None
    destination_entry_method: Optional[str] = None
    destination_receipt_path: Optional[str] = None
    destination_receipt_url: Optional[str] = None
    transfer_provenance: Optional[Dict[str, Any]] = None
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    category_color: Optional[str] = None
    category_type: Optional[CategoryType] = None
    expense_nature: ExpenseNature
    original_amount: Optional[float] = None
    original_currency: Optional[str] = None
    exchange_rate: Optional[float] = None
    formatted_original_amount: Optional[str] = None
    is_implied_rate: bool = False
    implied_effective_rate_label: Optional[str] = None
    is_planned: bool = False
    deleted_at: Optional[datetime] = None
    deletion_batch_id: Optional[str] = None
    is_deleted: bool = False
    repeat_series_id: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

RepeatFrequency = Literal["weekly", "biweekly", "monthly", "quarterly", "yearly"]
RepeatEndMode = Literal["end_date", "count"]

class RepeatTransactionCreatePayload(BaseModel):
    transaction_type: TransactionType
    amount: Optional[float] = Field(None, gt=0, description="Amount in base currency")
    merchant: Optional[str] = Field(None, max_length=255)
    account_id: Optional[int] = None
    destination_account_id: Optional[int] = None
    category_id: Optional[int] = None
    expense_nature: Optional[ExpenseNature] = None
    notes: Optional[str] = None
    original_amount: Optional[float] = Field(None, gt=0, description="Amount in original foreign currency")
    original_currency: Optional[str] = Field(None, min_length=3, max_length=3, description="ISO 4217 original currency code")
    exchange_rate: Optional[float] = Field(None, gt=0, description="Base currency per 1 unit of original currency")

    frequency: RepeatFrequency
    first_date: date
    end_mode: RepeatEndMode
    last_date: Optional[date] = None
    occurrence_count: Optional[int] = Field(None, ge=1, le=366)
    idempotency_key: Optional[str] = Field(None, min_length=8, max_length=128)

class RepeatTransactionCreateResponse(BaseModel):
    series_id: str
    idempotency_key: str
    frequency: RepeatFrequency
    first_date: str
    last_date: str
    end_mode: RepeatEndMode
    created_count: int
    idempotent_replay: bool = False
    message: str
    items: List[TransactionResponse]

class TransactionListResponse(BaseModel):
    items: List[TransactionResponse]
    total: int
    limit: int
    offset: int
    range_start_date: Optional[str] = None
    range_end_date: Optional[str] = None
    can_navigate_previous: Optional[bool] = None
    can_navigate_next: Optional[bool] = None

class MatchingTransactionIdsResponse(BaseModel):
    ids: List[int]
    total: int

class BulkTransactionUpdatePayload(BaseModel):
    transaction_ids: List[int] = Field(..., min_length=1, description="List of transaction IDs to update")
    update_transaction_type: bool = Field(default=False, description="Whether to update transaction type")
    transaction_type: Optional[TransactionType] = Field(default=None, description="New transaction type ('income' or 'expense')")
    update_category: bool = Field(default=False, description="Whether to update category")
    category_id: Optional[int] = Field(default=None, description="New category ID, or None for Uncategorised")
    update_account: bool = Field(default=False, description="Whether to update account")
    account_id: Optional[int] = Field(default=None, description="New account ID, or None for Unassigned")

class BulkTransactionUpdateResult(BaseModel):
    updated_count: int
    message: str
    affected_ids: List[int]

class BulkTransactionDeletePayload(BaseModel):
    transaction_ids: List[int] = Field(..., min_length=1, description="List of transaction IDs to delete")

class BulkTransactionDeleteResult(BaseModel):
    deleted_count: int
    batch_id: str
    affected_transfers_count: int
    affected_receipts_count: int
    affected_ids: List[int]
    message: str

class RestoreTransactionsPayload(BaseModel):
    transaction_ids: Optional[List[int]] = Field(default=None, description="Optional specific IDs to restore")
    batch_id: Optional[str] = Field(default=None, description="Optional batch ID to restore")

class RestoreTransactionsResult(BaseModel):
    restored_count: int
    restored_ids: List[int]
    message: str

class RecentlyDeletedSummary(BaseModel):
    total_deleted: int
    total_pence: int
    formatted_total: str
    transfers_count: int
    receipts_count: int

# --- System Settings & Backup Schemas ---
class SystemSettingsResponse(BaseModel):
    backup_automation_enabled: bool = False
    backup_frequency_days: int = 30
    last_backup_check_at: Optional[datetime] = None
    last_successful_backup_at: Optional[datetime] = None
    next_backup_due_at: Optional[datetime] = None
    is_backup_overdue: bool = False
    overdue_message: Optional[str] = None
    import_confidence_category: str = "balanced"
    import_confidence_account: str = "balanced"

class SystemSettingsUpdate(BaseModel):
    backup_automation_enabled: Optional[bool] = None
    backup_frequency_days: Optional[int] = Field(None, ge=1, le=365)
    import_confidence_category: Optional[str] = Field(None, pattern="^(cautious|balanced|permissive)$")
    import_confidence_account: Optional[str] = Field(None, pattern="^(cautious|balanced|permissive)$")

class BackupArchiveInfo(BaseModel):
    filename: str
    filepath: str
    created_at: datetime
    size_bytes: int
    size_formatted: str
    manifest: Optional[dict] = None

class BackupCreationResponse(BaseModel):
    success: bool
    filename: str
    filepath: str
    size_formatted: str
    created_at: datetime
    manifest: dict

# --- Statement & Staging Review Schemas ---

class StatementMappingConfig(BaseModel):
    delimiter: Optional[str] = "auto"
    has_header: bool = True
    skip_rows: int = 0
    date_column: Union[str, int]
    date_format: Optional[str] = "auto"
    merchant_column: Union[str, int]
    notes_column: Optional[Union[str, int]] = None
    category_column: Optional[Union[str, int]] = None
    amount_mode: str = "single_standard"  # single_standard | single_inverted | dual_debit_credit
    amount_column: Optional[Union[str, int]] = None
    debit_column: Optional[Union[str, int]] = None
    credit_column: Optional[Union[str, int]] = None

class StatementMappingProfile(BaseModel):
    id: str
    name: str
    version: int = 1
    config: StatementMappingConfig
    default_account_id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class StatementMappingProfileCreate(BaseModel):
    name: str
    config: StatementMappingConfig
    default_account_id: Optional[int] = None

class SkippedRowInfo(BaseModel):
    line_number: int
    reason: str
    raw: str

class CSVImportResponse(BaseModel):
    batch_id: str
    source_filename: str
    total_rows: int
    staged_count: int
    skipped_count: int
    skipped_rows: List[SkippedRowInfo] = []

class StagingItemResponse(BaseModel):
    id: int
    created_at: Optional[datetime] = None
    status: str
    extracted_amount_pence: Optional[int] = None
    amount_pounds: Optional[float] = None
    formatted_amount: Optional[str] = None
    extracted_date: Optional[datetime] = None
    extracted_merchant: Optional[str] = None
    suggested_category_name: Optional[str] = None
    suggested_category_id: Optional[int] = None
    suggested_account_id: Optional[int] = None
    suggested_account_name: Optional[str] = None
    suggested_account_color: Optional[str] = None
    suggested_account_match_reason: Optional[str] = None
    suggested_expense_nature: ExpenseNature = ExpenseNature.UNCLASSIFIED
    source_type: str
    temp_file_path: Optional[str] = None
    receipt_url: Optional[str] = None
    
    # Extended fields deserialized from raw_payload_json
    transaction_type: str = "expense"
    destination_account_id: Optional[int] = None
    destination_account_name: Optional[str] = None
    notes: Optional[str] = None
    currency: str = "GBP"
    original_amount: Optional[float] = None
    original_currency: Optional[str] = None
    exchange_rate: Optional[float] = None
    formatted_original_amount: Optional[str] = None
    requires_base_amount: bool = False
    currency_conflict: bool = False
    currency_conflict_message: Optional[str] = None
    is_potential_duplicate: bool = False
    duplicate_matches: List[dict] = []
    source_filename: Optional[str] = None
    line_number: Optional[int] = None
    ocr_confidence: Optional[float] = None
    ocr_error: Optional[str] = None
    date_uncertain: bool = False
    merchant_uncertain: bool = False
    category_match_reason: Optional[str] = None

    anchor_status: Optional[str] = None
    anchor_explanation: Optional[str] = None
    anchor_mode: Optional[str] = "auto"
    effective_timestamp: Optional[datetime] = None

    is_split: bool = False
    split_parent_id: Optional[int] = None
    split_index: Optional[int] = None
    split_total: Optional[int] = None

class StagingSplitRow(BaseModel):
    amount_pence: int = Field(gt=0, description="Amount in minor units (pence)")
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    expense_nature: ExpenseNature = ExpenseNature.UNCLASSIFIED
    notes: Optional[str] = None

class StagingSplitRequest(BaseModel):
    splits: List[StagingSplitRow] = Field(min_length=2, description="Split rows (minimum 2)")
    commit_to_ledger: bool = Field(default=False, description="Whether to approve directly into the ledger")
    account_id: Optional[int] = Field(default=None, description="Shared destination account ID")
    transaction_date: Optional[datetime] = Field(default=None, description="Shared transaction date")
    merchant: Optional[str] = Field(default=None, description="Shared merchant name")
    notes: Optional[str] = Field(default=None, description="Shared notes")

class StagingSplitResponse(BaseModel):
    success: bool
    action: str
    parent_id: int
    created_item_ids: List[int] = []
    created_items: List[StagingItemResponse] = []
    transaction_ids: List[int] = []
    message: str

class StagingItemUpdate(BaseModel):
    merchant: Optional[str] = None
    amount: Optional[float] = None
    original_amount: Optional[float] = None
    original_currency: Optional[str] = None
    exchange_rate: Optional[float] = None
    transaction_date: Optional[datetime] = None
    account_id: Optional[int] = None
    destination_account_id: Optional[int] = None
    transaction_type: Optional[TransactionType] = None
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    expense_nature: Optional[ExpenseNature] = None
    notes: Optional[str] = None
    anchor_mode: Optional[str] = None
    effective_timestamp: Optional[datetime] = None

class CurrencySpecResponse(BaseModel):
    code: str
    symbol: str
    precision: int
    name: str
    can_be_base: bool

class SystemConfigResponse(BaseModel):
    base_currency: str
    base_currency_symbol: str
    base_currency_decimals: int
    base_currency_name: str
    supported_currencies: Dict[str, CurrencySpecResponse] = {}
    app_timezone: str = "Europe/London"

class StagingBatchApprovePayload(BaseModel):
    item_ids: Optional[List[int]] = None
    include_duplicates: bool = False

class StagingBatchRejectPayload(BaseModel):
    item_ids: List[int]

class StagingBatchApproveResponse(BaseModel):
    approved_count: int
    excluded_duplicates_count: int
    error_count: int
    errors: List[dict] = []

class StagingCountResponse(BaseModel):
    pending_count: int

class UnifiedImportItemResponse(BaseModel):
    id: int
    batch_id: str
    line_number: int
    extracted_date: Optional[datetime] = None
    extracted_amount_pence: Optional[int] = None
    extracted_amount_pounds: Optional[float] = None
    extracted_merchant: Optional[str] = None
    suggested_account_id: Optional[int] = None
    suggested_account_name: Optional[str] = None
    suggested_account_match_reason: Optional[str] = None
    suggested_category_id: Optional[int] = None
    suggested_category_name: Optional[str] = None
    suggested_expense_nature: str = "unclassified"
    transaction_type: str = "expense"
    currency: str = "GBP"
    original_amount: Optional[float] = None
    original_currency: Optional[str] = None
    currency_conflict: bool = False
    currency_conflict_message: Optional[str] = None
    is_potential_duplicate: bool = False
    duplicate_matches: List[dict] = []
    missing_fields: List[str] = []
    source_type: str
    temp_file_path: Optional[str] = None
    notes: Optional[str] = None
    date_uncertain: bool = False
    merchant_uncertain: bool = False
    direction_uncertain: bool = False
    direction_evidence: Optional[str] = None
    category_match_reason: Optional[str] = None

class DirectionSummary(BaseModel):
    expense_count: int
    income_count: int
    uncertain_count: int
    evidence_type: str
    evidence_description: str

class UnifiedImportResponse(BaseModel):
    batch_id: str
    filename: str
    file_hash: Optional[str] = None
    file_size_bytes: int
    mime_type: str
    document_type: str
    document_type_label: str
    summary: str
    direction_summary: Optional[DirectionSummary] = None
    items: List[UnifiedImportItemResponse]

class StagingItemUpdateWithId(StagingItemUpdate):
    id: int

class UnifiedImportCommitPayload(BaseModel):
    batch_id: str
    action: str  # 'approve_all', 'approve_selected', 'queue_all', 'discard_all'
    items: List[StagingItemUpdateWithId] = []

class UnifiedImportCommitResponse(BaseModel):
    action: str
    batch_id: str
    approved_count: int
    queued_count: int
    discarded_count: int
    already_committed_count: int = 0
    transaction_ids: List[int] = []
    errors: List[dict] = []
    message: Optional[str] = None


# --- Investment Holdings & Portfolio Schemas ---

class HoldingBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    ticker: Optional[str] = Field(None, max_length=30)
    asset_class: str = Field(default="equity", max_length=50)
    currency: Optional[str] = Field(None, max_length=3)
    notes: Optional[str] = None

class HoldingCreate(HoldingBase):
    initial_quantity: Optional[float] = Field(None, ge=0)
    initial_unit_price: Optional[float] = Field(None, ge=0)
    initial_valuation: Optional[float] = Field(None, ge=0)
    initial_effective_date: Optional[datetime] = None

class HoldingUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=150)
    ticker: Optional[str] = Field(None, max_length=30)
    asset_class: Optional[str] = Field(None, max_length=50)
    account_id: Optional[int] = Field(None, description="Reassign holding to another investment account")
    is_active: Optional[bool] = None
    notes: Optional[str] = None

class HoldingValuationCreate(BaseModel):
    effective_date: Optional[datetime] = None
    quantity: float = Field(..., ge=0, description="Quantity of units/shares, >= 0")
    unit_price: Optional[float] = Field(None, ge=0, description="Unit price in major currency units, e.g. £85.12")
    valuation: Optional[float] = Field(None, ge=0, description="Total valuation in major currency units, e.g. £1250.00")
    notes: Optional[str] = None

class HoldingValuationUpdate(BaseModel):
    effective_date: Optional[datetime] = None
    quantity: Optional[float] = Field(None, ge=0)
    unit_price: Optional[float] = Field(None, ge=0)
    valuation: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = None

class HoldingValuationResponse(BaseModel):
    id: int
    holding_id: int
    effective_date: datetime
    quantity: float
    unit_price_pence: Optional[float] = None
    unit_price_pounds: Optional[float] = None
    formatted_unit_price: Optional[str] = None
    valuation_pence: int
    valuation_pounds: float
    formatted_valuation: str
    currency: str
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)

class HoldingResponse(BaseModel):
    id: int
    account_id: int
    name: str
    ticker: Optional[str] = None
    asset_class: str
    currency: str
    is_active: bool
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    is_valued: bool
    latest_quantity: Optional[float] = None
    latest_unit_price_pounds: Optional[float] = None
    formatted_unit_price: Optional[str] = None
    latest_valuation_pence: Optional[int] = None
    latest_valuation_pounds: Optional[float] = None
    formatted_valuation: Optional[str] = None
    last_valuation_date: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)

class AccountValuationModeUpdate(BaseModel):
    valuation_mode: str = Field(..., pattern="^(snapshot|holdings)$")

class AccountHoldingsResponse(BaseModel):
    account_id: int
    account_name: str
    currency: str
    valuation_mode: str
    total_valuation_pence: int
    total_valuation_pounds: float
    formatted_total_valuation: str
    holdings_count: int
    valued_count: int
    unvalued_count: int
    has_unvalued_holdings: bool
    holdings: List[HoldingResponse]

class PortfolioAccountSummary(BaseModel):
    account_id: int
    account_name: str
    currency: str
    color: str
    valuation_mode: str
    balance_pence: int
    balance_pounds: float
    formatted_balance: str
    holdings_count: int
    valued_count: int
    unvalued_count: int
    has_unvalued_holdings: bool

class AssetAllocationItem(BaseModel):
    asset_class: str
    total_pence: int
    total_pounds: float
    percentage: float

class PortfolioSummaryResponse(BaseModel):
    total_invested_pence: int
    total_invested_pounds: float
    formatted_total_invested: str
    accounts: List[PortfolioAccountSummary]
    asset_allocation: List[AssetAllocationItem]

class CheckpointSyncRequest(BaseModel):
    effective_date: Optional[datetime] = None
    notes: Optional[str] = None

class CheckpointSyncResponse(BaseModel):
    snapshot_id: int
    account_id: int
    effective_date: datetime
    valuation_pence: int
    valuation_pounds: float
    formatted_valuation: str
    notes: Optional[str] = None


# --- Cash Flow & Analytics Schemas ---

class CategorySpendingItem(BaseModel):
    category_id: Optional[int] = None
    category_name: str
    category_color: str
    category_type: CategoryType = CategoryType.EXPENSE
    expense_nature: Optional[ExpenseNature] = None
    total_pence: int
    total_pounds: float
    formatted_total: str
    transaction_count: int
    percentage: float  # Percentage of total expenses or income in period

class MonthlyCashFlowTrendItem(BaseModel):
    month: str  # "YYYY-MM"
    month_name: str  # "Oct 2026"
    income_pence: int
    income_pounds: float
    formatted_income: str
    fixed_expenses_pence: int
    variable_expenses_pence: int
    unclassified_expenses_pence: int
    total_expenses_pence: int
    total_expenses_pounds: float
    formatted_total_expenses: str
    net_surplus_pence: int
    net_surplus_pounds: float
    formatted_net_surplus: str
    savings_rate: float
    is_savings_rate_applicable: bool

class CashFlowSummaryResponse(BaseModel):
    selected_month: str
    month_name: str
    prev_month: str
    next_month: str
    currency: str
    currency_symbol: str
    available_currencies: List[str]
    available_months: List[str]
    account_id: Optional[int] = None
    account_name: Optional[str] = None

    # Inflow
    income_pence: int
    income_pounds: float
    formatted_income: str
    income_count: int

    # Outflow by Nature
    fixed_expenses_pence: int
    fixed_expenses_pounds: float
    formatted_fixed_expenses: str
    fixed_expenses_count: int
    fixed_percentage: float

    variable_expenses_pence: int
    variable_expenses_pounds: float
    formatted_variable_expenses: str
    variable_expenses_count: int
    variable_percentage: float

    unclassified_expenses_pence: int
    unclassified_expenses_pounds: float
    formatted_unclassified_expenses: str
    unclassified_expenses_count: int
    unclassified_percentage: float

    total_expenses_pence: int
    total_expenses_pounds: float
    formatted_total_expenses: str
    expenses_count: int

    # Internal Transfers (Zero Effect)
    transfers_volume_pence: int
    transfers_volume_pounds: float
    formatted_transfers_volume: str
    transfers_count: int

    # Adjustments & Refunds
    adjustments_inflow_pence: int
    adjustments_outflow_pence: int
    adjustments_net_pence: int
    adjustments_net_pounds: float
    formatted_adjustments_net: str
    adjustments_count: int

    # Net metrics
    operating_surplus_pence: int
    operating_surplus_pounds: float
    formatted_operating_surplus: str

    net_surplus_pence: int
    net_surplus_pounds: float
    formatted_net_surplus: str

    # Savings Rate
    savings_rate: float
    is_savings_rate_applicable: bool
    formatted_savings_rate: str

    # Breakdowns
    categories: List[CategorySpendingItem]
    historical_trend: List[MonthlyCashFlowTrendItem]

    # Planned / Future activity in this month
    planned_income_pence: int = 0
    planned_expenses_pence: int = 0
    planned_net_pence: int = 0
    planned_count: int = 0
    formatted_planned_net: str = "£0.00"

    # Meta
    total_transactions_count: int
    has_data: bool


# --- Account Reconciliation Schemas ---

class AccountSnapshotItem(BaseModel):
    id: int
    account_id: int
    snapshot_date: datetime
    actual_balance_pence: int
    actual_balance_pounds: float
    formatted_actual_balance: str
    calculated_balance_pence: int
    calculated_balance_pounds: float
    formatted_calculated_balance: str
    discrepancy_pence: int
    discrepancy_pounds: float
    formatted_discrepancy: str
    discrepancy_direction: str  # "exact", "actual_higher", "actual_lower"
    notes: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class ReconciliationSummaryResponse(BaseModel):
    account_id: int
    account_name: str
    account_type: AccountType
    currency: str
    currency_symbol: str
    calculated_balance_pence: int
    calculated_balance_pounds: float
    formatted_calculated_balance: str
    last_reconciled_at: Optional[datetime] = None
    last_snapshot: Optional[AccountSnapshotItem] = None
    last_anchor: Optional[AccountBalanceAnchorResponse] = None
    snapshots_count: int
    app_timezone: str = "Europe/London"

class AccountBreakdownMovement(BaseModel):
    inflows_pence: int
    formatted_inflows: str
    outflows_pence: int
    formatted_outflows: str
    transfers_in_pence: int
    formatted_transfers_in: str
    transfers_out_pence: int
    formatted_transfers_out: str
    adjustments_net_pence: int
    formatted_adjustments_net: str
    net_movement_pence: int
    formatted_net_movement: str
    transaction_count: int

class AccountBreakdownAnchor(BaseModel):
    has_anchor: bool
    anchor_id: Optional[int] = None
    balance_pence: Optional[int] = None
    formatted_balance: Optional[str] = None
    anchor_date: Optional[datetime] = None
    anchor_date_local: Optional[str] = None
    is_opening: bool = False
    notes: Optional[str] = None
    label: str

class AccountBreakdownLiability(BaseModel):
    is_liability: bool
    amount_owed_pence: int
    formatted_amount_owed: str
    explanation: str

class AccountBreakdownInvestment(BaseModel):
    is_investment: bool
    valuation_mode: str
    holdings_count: int
    valued_count: int
    unvalued_count: int
    has_unvalued_holdings: bool
    latest_valuation_date: Optional[datetime] = None
    latest_valuation_date_formatted: Optional[str] = None
    explanation: str

class AccountBreakdownRecentTx(BaseModel):
    id: int
    transaction_date: datetime
    effective_timestamp: Optional[datetime] = None
    transaction_type: str
    amount_pence: int
    formatted_amount: str
    merchant: Optional[str] = None
    notes: Optional[str] = None
    category_name: Optional[str] = None
    category_color: Optional[str] = None
    is_planned: bool = False

class AccountBreakdownResponse(BaseModel):
    account_id: int
    account_name: str
    account_type: str
    account_group: str
    currency: str
    currency_symbol: str
    color: str
    is_active: bool
    current_balance_pence: int
    formatted_current_balance: str
    current_balance_pounds: float
    starting_balance_pence: int
    formatted_starting_balance: str
    anchor: AccountBreakdownAnchor
    movement: AccountBreakdownMovement
    planned_movement: Optional[AccountBreakdownMovement] = None
    projected_balance_pence: Optional[int] = None
    formatted_projected_balance: Optional[str] = None
    liability: Optional[AccountBreakdownLiability] = None
    investment: Optional[AccountBreakdownInvestment] = None
    recent_transactions: List[AccountBreakdownRecentTx] = []
    anchors: List[AccountBalanceAnchorResponse] = []
    snapshots: List[AccountSnapshotItem] = []
    app_timezone: str = "Europe/London"

class MissingTransactionPayload(BaseModel):
    transaction_type: TransactionType = TransactionType.EXPENSE
    amount: float = Field(..., gt=0, description="Amount in pounds")
    merchant: str = Field(default="Missing Transaction", max_length=255)
    category_id: Optional[int] = None
    transaction_date: Optional[Union[date, datetime, str]] = None
    notes: Optional[str] = Field(default=None, max_length=255)

class ReconciliationSnapshotCreate(BaseModel):
    actual_balance: float = Field(..., description="Confirmed statement balance in pounds")
    as_of_mode: str = Field(default="now", description="'now' or 'date'")
    as_of_date: Optional[str] = Field(default=None, description="ISO date 'YYYY-MM-DD' when as_of_mode is 'date'")
    snapshot_date: Optional[datetime] = Field(default=None, description="Explicit snapshot timestamp for direct API usage")
    notes: Optional[str] = Field(default=None, max_length=255, description="Optional discrepancy explanation note")
    missing_transaction: Optional[MissingTransactionPayload] = None
    create_adjustment: bool = False
    adjustment_notes: Optional[str] = None

class ReconciliationResultResponse(BaseModel):
    snapshot: AccountSnapshotItem
    anchor: AccountBalanceAnchorResponse
    explanation: str
    missing_transaction_created: bool = False
    missing_transaction_id: Optional[int] = None
    adjustment_created: bool = False
    adjustment_transaction_id: Optional[int] = None
    new_calculated_balance_pence: int
    new_calculated_balance_pounds: float
    formatted_new_calculated_balance: str


# --- Multidimensional Analysis Schemas ---

class DateRangeInfo(BaseModel):
    preset: str
    interval: str
    start_date: str
    end_date: str
    app_timezone: str
    available_presets: List[str]
    available_intervals: List[str]
    offset: int = 0
    can_navigate_previous: bool = True
    can_navigate_next: bool = False

class AnalysisTimeSeriesBucket(BaseModel):
    key: str
    label: str
    start_date: str
    end_date: str
    is_partial: bool
    partial_label: Optional[str] = None
    income_pence: int
    income_pounds: float
    formatted_income: str
    expenses_pence: int
    expenses_pounds: float
    formatted_expenses: str
    net_savings_pence: int
    net_savings_pounds: float
    formatted_net_savings: str
    cumulative_net_savings_pence: int = 0
    cumulative_net_savings_pounds: float = 0.0
    formatted_cumulative_net_savings: str = "£0.00"
    cumulative_income_pence: int = 0
    cumulative_income_pounds: float = 0.0
    formatted_cumulative_income: str = "£0.00"
    cumulative_expenses_pence: int = 0
    cumulative_expenses_pounds: float = 0.0
    formatted_cumulative_expenses: str = "£0.00"
    cumulative_net_flow_pence: int = 0
    cumulative_net_flow_pounds: float = 0.0
    formatted_cumulative_net_flow: str = "£0.00"
    savings_rate: float
    is_savings_rate_applicable: bool
    transfers_volume_pence: int
    formatted_transfers_volume: str
    adjustments_net_pence: int
    formatted_adjustments_net: str
    fixed_expenses_pence: int
    variable_expenses_pence: int
    unclassified_expenses_pence: int
    planned_income_pence: int = 0
    planned_expenses_pence: int = 0
    planned_net_pence: int = 0
    category_spending: Dict[str, int] = {}
    category_spending_details: List[dict] = []
    nature_spending_details: List[dict] = []

class AnalysisTotals(BaseModel):
    income_pence: int
    income_pounds: float
    formatted_income: str
    expenses_pence: int
    expenses_pounds: float
    formatted_expenses: str
    net_savings_pence: int
    net_savings_pounds: float
    formatted_net_savings: str
    cumulative_net_savings_pence: int = 0
    cumulative_net_savings_pounds: float = 0.0
    formatted_cumulative_net_savings: str = "£0.00"
    cumulative_income_pence: int = 0
    cumulative_income_pounds: float = 0.0
    formatted_cumulative_income: str = "£0.00"
    cumulative_expenses_pence: int = 0
    cumulative_expenses_pounds: float = 0.0
    formatted_cumulative_expenses: str = "£0.00"
    cumulative_net_flow_pence: int = 0
    cumulative_net_flow_pounds: float = 0.0
    formatted_cumulative_net_flow: str = "£0.00"
    savings_rate: float
    is_savings_rate_applicable: bool
    fixed_expenses_pence: int
    formatted_fixed_expenses: str
    fixed_percentage: float
    variable_expenses_pence: int
    formatted_variable_expenses: str
    variable_percentage: float
    unclassified_expenses_pence: int
    formatted_unclassified_expenses: str
    unclassified_percentage: float
    transfers_volume_pence: int
    formatted_transfers_volume: str
    transfers_count: int
    adjustments_inflow_pence: int
    adjustments_outflow_pence: int
    adjustments_net_pence: int
    formatted_adjustments_net: str
    adjustments_count: int

class AccountBalanceSnapshot(BaseModel):
    account_id: int
    account_name: str
    account_type: str
    color: str
    balance_pence: int
    balance_pounds: float
    formatted_balance: str
    is_inferred: bool = False
    inferred_warning: Optional[str] = None
    reconciliation_discrepancy_pence: Optional[int] = None
    reconciliation_actual_pence: Optional[int] = None

class NetWorthBucket(BaseModel):
    key: str
    label: str
    date: str
    is_partial: bool
    partial_label: Optional[str] = None
    total_assets_pence: int
    total_assets_pounds: float
    formatted_total_assets: str
    total_debt_pence: int
    total_debt_pounds: float
    formatted_total_debt: str
    net_worth_pence: int
    net_worth_pounds: float
    formatted_net_worth: str
    account_balances: List[AccountBalanceSnapshot] = []
    has_inferred_balances: bool = False

class InvestmentAccountSummary(BaseModel):
    account_id: int
    account_name: str
    is_available: bool = True
    is_carried_forward: bool = False
    valuation_date: Optional[str] = None
    carried_forward_date: Optional[str] = None
    valuation_pence: Optional[int] = None
    valuation_pounds: Optional[float] = None
    formatted_valuation: str
    holdings_count: int
    valued_count: int
    unvalued_count: int

class PortfolioValueBucket(BaseModel):
    key: str
    label: str
    date: str
    is_partial: bool
    partial_label: Optional[str] = None
    is_available: bool = True
    is_carried_forward: bool = False
    valuation_date: Optional[str] = None
    carried_forward_date: Optional[str] = None
    total_valuation_pence: Optional[int] = None
    total_valuation_pounds: Optional[float] = None
    formatted_total_valuation: str
    holdings_count: int
    valued_count: int
    unvalued_count: int
    has_unvalued_holdings: bool
    accounts: List[InvestmentAccountSummary] = []

class FilterOptionAccount(BaseModel):
    id: int
    name: str
    currency: str
    account_type: str
    color: str = "#6B7280"

class FilterOptionCategory(BaseModel):
    id: int
    name: str
    color: str
    default_nature: str
    category_type: str = "expense"

class SpendingMatrixCell(BaseModel):
    amount_pence: int = 0
    amount_pounds: float = 0.0
    formatted_amount: str = "£0.00"
    transaction_count: int = 0

class SpendingMatrixRow(BaseModel):
    category_id: Optional[int] = None
    category_name: str
    category_color: str
    category_type: str = "expense"
    expense_nature: str
    is_uncategorized: bool = False
    row_total_pence: int = 0
    row_total_pounds: float = 0.0
    formatted_row_total: str = "£0.00"
    percentage: float = 0.0
    transaction_count: int = 0
    cells: Dict[str, SpendingMatrixCell] = {}

class SpendingMatrixColumn(BaseModel):
    key: str
    label: str
    start_date: str
    end_date: str
    is_partial: bool
    partial_label: Optional[str] = None
    period_total_pence: int = 0
    period_total_pounds: float = 0.0
    formatted_period_total: str = "£0.00"

class SpendingMatrixResponse(BaseModel):
    periods: List[SpendingMatrixColumn] = []
    rows: List[SpendingMatrixRow] = []
    grand_total_pence: int = 0
    grand_total_pounds: float = 0.0
    formatted_grand_total: str = "£0.00"

class ForecastPlannedActivity(BaseModel):
    has_planned_activity: bool = False
    planned_income_pence: int = 0
    planned_income_pounds: float = 0.0
    formatted_planned_income: str = "£0.00"
    planned_expenses_pence: int = 0
    planned_expenses_pounds: float = 0.0
    formatted_planned_expenses: str = "£0.00"
    planned_net_pence: int = 0
    planned_net_pounds: float = 0.0
    formatted_planned_net: str = "£0.00"
    planned_transactions_count: int = 0
    items: List[Dict[str, Any]] = []

class ComprehensiveAnalysisResponse(BaseModel):
    range_info: DateRangeInfo
    currency: str
    currency_symbol: str
    available_currencies: List[str]
    account_id: Optional[int] = None
    account_name: Optional[str] = None
    account_ids: List[int] = []
    account_names: List[str] = []
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    category_ids: List[int] = []
    category_names: List[str] = []
    available_accounts: List[FilterOptionAccount] = []
    available_categories: List[FilterOptionCategory] = []
    totals: AnalysisTotals
    time_series: List[AnalysisTimeSeriesBucket] = []
    categories: List[CategorySpendingItem] = []
    spending_matrix: Optional[SpendingMatrixResponse] = None
    income_categories: List[CategorySpendingItem] = []
    income_matrix: Optional[SpendingMatrixResponse] = None
    net_worth_series: List[NetWorthBucket] = []
    investments_series: List[PortfolioValueBucket] = []
    is_investments_sparse: bool = False
    investments_sparse_explanation: Optional[str] = None
    forecast: Optional[ForecastPlannedActivity] = None

class ProfileResponse(BaseModel):
    id: str
    name: str
    created_at: str
    is_archived: bool = False
    is_default: bool = False
    is_active: bool = False

class ProfileCreate(BaseModel):
    name: str

class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    is_archived: Optional[bool] = None

class ProfileImpactResponse(BaseModel):
    profile_id: str
    profile_name: str
    is_active: bool
    is_default: bool
    can_delete: bool
    blocking_reason: Optional[str] = None
    accounts_count: int
    transactions_count: int
    categories_count: int
    holdings_count: int
    staging_items_count: int
    receipt_files_count: int
    backup_files_count: int
    disk_usage_bytes: int
    disk_usage_formatted: str

class ProfileDeleteRequest(BaseModel):
    confirm_name: str


class ReviewSuggestionRecord(BaseModel):
    id: int
    kind: str
    date: str
    amount_pence: int
    formatted_amount: str
    merchant: str
    account_name: Optional[str] = None
    account_id: Optional[int] = None
    category_name: Optional[str] = None
    direction: Optional[str] = None
    source_type: Optional[str] = None
    source_filename: Optional[str] = None


class ReviewDuplicateSuggestion(BaseModel):
    id: str
    type: str = "duplicate"
    subtype: str
    reasons: List[str]
    record_a: ReviewSuggestionRecord
    record_b: ReviewSuggestionRecord


class ReviewTransferSuggestion(BaseModel):
    id: str
    type: str = "transfer"
    subtype: str
    reasons: List[str]
    action_explanation: Optional[str] = None
    source_record: ReviewSuggestionRecord
    destination_record: ReviewSuggestionRecord


class ReviewSuggestionsSummary(BaseModel):
    duplicates_count: int
    transfers_count: int


class ReviewSuggestionsResponse(BaseModel):
    duplicate_suggestions: List[ReviewDuplicateSuggestion]
    transfer_suggestions: List[ReviewTransferSuggestion]
    summary: ReviewSuggestionsSummary


class ConfirmDuplicateSuggestionPayload(BaseModel):
    duplicate_staging_id: int
    suggestion_id: Optional[str] = None


class ConfirmTransferSuggestionPayload(BaseModel):
    source_id: int
    source_kind: str
    destination_id: int
    destination_kind: str
    suggestion_id: Optional[str] = None


class DismissSuggestionPayload(BaseModel):
    suggestion_id: str


# --- Data Quality & Review Schemas ---

DataQualityFindingType = Literal[
    "uncategorised",
    "unassigned_account",
    "potential_duplicate",
    "possible_transfer",
    "uncertain_import",
    "archived_reference",
    "integrity_issue",
]

DataQualitySeverity = Literal["integrity", "review", "suggestion"]


class DataQualitySummary(BaseModel):
    total_active: int
    dismissed_count: int
    by_type: Dict[str, int]
    by_severity: Dict[str, int]
    scanned_transactions_count: int
    scanned_staging_count: int


class DataQualityFindingResponse(BaseModel):
    id: str
    finding_type: DataQualityFindingType
    severity: DataQualitySeverity
    confidence: str
    title: str
    summary: str
    reasons: List[str]
    source: str
    subtype: str
    record_kind: str
    transaction_id: Optional[int] = None
    related_transaction_id: Optional[int] = None
    staging_id: Optional[int] = None
    transaction_type: Optional[str] = None
    date: Optional[str] = None
    amount_pence: Optional[int] = None
    formatted_amount: Optional[str] = None
    merchant: Optional[str] = None
    account_id: Optional[int] = None
    destination_account_id: Optional[int] = None
    account_name: Optional[str] = None
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    category_type: Optional[str] = None
    expected_category_type: Optional[str] = None
    can_dismiss: bool = True
    is_dismissed: bool = False
    ledger_url: Optional[str] = None
    queue_url: Optional[str] = None
    suggested_action: Optional[str] = None
    suggested_category_id: Optional[int] = None
    suggested_category_name: Optional[str] = None
    action_explanation: Optional[str] = None
    comparison: Optional[Dict[str, Any]] = None


class DataQualityReportResponse(BaseModel):
    profile_id: str
    app_timezone: str
    base_currency: str
    confidence_settings: Dict[str, str]
    summary: DataQualitySummary
    filtered_count: int
    findings: List[DataQualityFindingResponse]


class DataQualityDismissPayload(BaseModel):
    finding_id: str = Field(..., min_length=1, max_length=200)


class DataQualityRestorePayload(BaseModel):
    finding_id: Optional[str] = Field(None, min_length=1, max_length=200)
    restore_all: bool = False










