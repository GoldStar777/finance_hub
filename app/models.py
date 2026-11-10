import enum
from typing import Optional
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Enum, Boolean, Text, CheckConstraint, Numeric
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class AccountType(str, enum.Enum):
    CURRENT = "current"
    SAVINGS = "savings"
    CASH = "cash"
    CREDIT_CARD = "credit_card"
    INVESTMENT = "investment"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            val_clean = value.strip().lower()
            if val_clean in ("checking", "current"):
                return cls.CURRENT
            if val_clean in ("savings", "saving"):
                return cls.SAVINGS
            if val_clean in ("cash", "wallet", "petty_cash", "petty cash"):
                return cls.CASH
            if val_clean in ("credit_card", "creditcard", "credit"):
                return cls.CREDIT_CARD
            if val_clean in ("investment", "portfolio", "isa", "sipp"):
                return cls.INVESTMENT
        return super()._missing_(value)


class CategoryType(str, enum.Enum):
    EXPENSE = "expense"
    INCOME = "income"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            val_clean = value.strip().lower()
            if val_clean == "expense":
                return cls.EXPENSE
            if val_clean == "income":
                return cls.INCOME
        return super()._missing_(value)

class TransactionType(str, enum.Enum):
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"
    ADJUSTMENT = "adjustment"

class ExpenseNature(str, enum.Enum):
    FIXED = "fixed"
    VARIABLE = "variable"
    UNCLASSIFIED = "unclassified"

class StagingStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

def _get_default_base_currency() -> str:
    import os
    return os.getenv("BASE_CURRENCY", "GBP").strip().upper()

class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    account_type = Column(Enum(AccountType), nullable=False)
    starting_balance_pence = Column(Integer, default=0, nullable=True)
    currency = Column(String(3), default=_get_default_base_currency, nullable=False)
    color = Column(String(20), default="#3B82F6")
    is_active = Column(Boolean, default=True, nullable=False)
    valuation_mode = Column(String(20), default="snapshot", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    balance_anchors = relationship(
        "AccountBalanceAnchor",
        back_populates="account",
        cascade="all, delete-orphan",
        order_by="AccountBalanceAnchor.anchor_date.asc(), AccountBalanceAnchor.id.asc()"
    )
    transactions = relationship(
        "Transaction", 
        foreign_keys="[Transaction.account_id]", 
        back_populates="account",
        cascade="all, delete-orphan"
    )
    snapshots = relationship(
        "AccountSnapshot", 
        back_populates="account",
        cascade="all, delete-orphan"
    )
    asset_snapshots = relationship(
        "AssetSnapshot", 
        back_populates="account",
        cascade="all, delete-orphan"
    )
    holdings = relationship(
        "Holding",
        back_populates="account",
        cascade="all, delete-orphan"
    )

    def __init__(self, **kwargs):
        has_starting_pence = "starting_balance_pence" in kwargs
        has_starting_date = "starting_balance_date" in kwargs
        starting_pence = kwargs.pop("starting_balance_pence", 0)
        if starting_pence is None:
            starting_pence = 0
        starting_date = kwargs.pop("starting_balance_date", None)
        super().__init__(starting_balance_pence=starting_pence, **kwargs)
        if has_starting_pence or has_starting_date:
            from datetime import timedelta
            anchor_dt = starting_date or (datetime.now(timezone.utc) - timedelta(seconds=1))
            self.balance_anchors.append(
                AccountBalanceAnchor(
                    balance_pence=starting_pence,
                    anchor_date=anchor_dt,
                    is_opening=True,
                    notes="Opening balance anchor"
                )
            )

    @property
    def opening_anchor(self) -> Optional["AccountBalanceAnchor"]:
        return next((a for a in self.balance_anchors if a.is_opening), None) or (self.balance_anchors[0] if self.balance_anchors else None)

    @property
    def latest_anchor(self) -> Optional["AccountBalanceAnchor"]:
        if not self.balance_anchors:
            return None
        return max(self.balance_anchors, key=lambda a: (a.anchor_date, a.id or 0))

    @property
    def starting_balance_date(self) -> Optional[datetime]:
        anchor = self.opening_anchor
        return anchor.anchor_date if anchor else None

class AccountBalanceAnchor(Base):
    __tablename__ = "account_balance_anchors"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    balance_pence = Column(Integer, nullable=False)
    anchor_date = Column(DateTime(timezone=True), nullable=False, index=True)
    is_opening = Column(Boolean, default=False, nullable=False)
    notes = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now())

    account = relationship("Account", back_populates="balance_anchors")

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    category_type = Column(Enum(CategoryType), default=CategoryType.EXPENSE, nullable=False)
    color = Column(String(20), default="#8B5CF6")
    default_expense_nature = Column(Enum(ExpenseNature), default=ExpenseNature.UNCLASSIFIED, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    transactions = relationship("Transaction", back_populates="category")

class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount_pence >= 0", name="check_positive_amount"),
    )

    id = Column(Integer, primary_key=True, index=True)
    transaction_date = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    effective_timestamp = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=True, default=lambda: datetime.now(timezone.utc))
    transaction_type = Column(Enum(TransactionType), nullable=False)
    amount_pence = Column(Integer, nullable=False)
    merchant = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    entry_method = Column(String(50), default="manual")
    receipt_path = Column(String(500), nullable=True)

    # Foreign origin provenance metadata (nullable for native base transactions)
    original_amount = Column(Numeric(18, 4), nullable=True)
    original_currency = Column(String(3), nullable=True)
    exchange_rate = Column(Numeric(18, 8), nullable=True)

    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    destination_account_id = Column(Integer, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    expense_nature = Column(Enum(ExpenseNature), default=ExpenseNature.UNCLASSIFIED, nullable=False)

    # Recoverable soft deletion & batch undo tracking
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    deletion_batch_id = Column(String(50), nullable=True, index=True)

    # Optional provenance link for transactions created in a single repeat-entry batch (never a live rule)
    repeat_series_id = Column(String(50), nullable=True, index=True)

    account = relationship("Account", foreign_keys=[account_id], back_populates="transactions")
    destination_account = relationship("Account", foreign_keys=[destination_account_id])
    category = relationship("Category", back_populates="transactions")

class AccountSnapshot(Base):
    __tablename__ = "account_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    snapshot_date = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    actual_balance_pence = Column(Integer, nullable=False)
    calculated_balance_pence = Column(Integer, nullable=False)
    discrepancy_pence = Column(Integer, nullable=False)
    notes = Column(String(255), nullable=True)

    account = relationship("Account", back_populates="snapshots")

class AssetSnapshot(Base):
    __tablename__ = "asset_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    valuation_pence = Column(Integer, nullable=False)
    effective_date = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    notes = Column(String(255), nullable=True)

    account = relationship("Account", back_populates="asset_snapshots")

class StagingItem(Base):
    __tablename__ = "staging_items"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now())
    status = Column(Enum(StagingStatus), default=StagingStatus.PENDING, nullable=False)

    extracted_amount_pence = Column(Integer, nullable=True)
    extracted_date = Column(DateTime(timezone=True), nullable=True)
    extracted_merchant = Column(String(255), nullable=True)

    suggested_category_name = Column(String(100), nullable=True)
    suggested_account_id = Column(Integer, nullable=True)
    suggested_expense_nature = Column(Enum(ExpenseNature), default=ExpenseNature.UNCLASSIFIED, nullable=False)

    source_type = Column(String(50), nullable=False)
    temp_file_path = Column(String(500), nullable=True)
    raw_payload_json = Column(Text, nullable=True)

    effective_timestamp = Column(DateTime(timezone=True), nullable=True)
    anchor_mode = Column(String(20), default="auto")

class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class Holding(Base):
    __tablename__ = "holdings"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    ticker = Column(String(30), nullable=True)
    asset_class = Column(String(50), default="equity", nullable=False)
    currency = Column(String(3), default="GBP", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    account = relationship("Account", back_populates="holdings")
    valuations = relationship(
        "HoldingValuation",
        back_populates="holding",
        cascade="all, delete-orphan",
        order_by="desc(HoldingValuation.effective_date), desc(HoldingValuation.id)"
    )

class HoldingValuation(Base):
    __tablename__ = "holding_valuations"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="check_positive_quantity"),
        CheckConstraint("valuation_pence >= 0", name="check_positive_holding_valuation"),
    )

    id = Column(Integer, primary_key=True, index=True)
    holding_id = Column(Integer, ForeignKey("holdings.id", ondelete="CASCADE"), nullable=False, index=True)
    effective_date = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    quantity = Column(Numeric(18, 8), nullable=False)
    unit_price_pence = Column(Numeric(14, 4), nullable=True)
    valuation_pence = Column(Integer, nullable=False)
    notes = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    holding = relationship("Holding", back_populates="valuations")


class RepeatSeriesBatch(Base):
    """
    Records atomic repeat-entry batch metadata strictly for idempotent retry protection
    and optional provenance grouping. Transactions created in the batch remain ordinary
    independent rows with no dependency on this table.
    """
    __tablename__ = "repeat_series_batches"

    id = Column(Integer, primary_key=True, index=True)
    series_id = Column(String(50), unique=True, nullable=False, index=True)
    idempotency_key = Column(String(128), unique=True, nullable=False, index=True)
    request_hash = Column(String(64), nullable=False)
    occurrence_count = Column(Integer, nullable=False)
    transaction_ids_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


