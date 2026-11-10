from datetime import datetime, timezone
from typing import Dict, Any, Optional
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, case
from app.models import (
    Account, AccountType, Transaction, TransactionType, AccountSnapshot, AssetSnapshot, AccountBalanceAnchor
)
from app.core.currency import format_pence, pence_to_pounds, get_effective_base_currency, get_currency_spec
from app.core.timezone import get_app_timezone, get_today_local, get_now_utc, get_end_of_day_utc

class LedgerEngine:
    @staticmethod
    def get_account_balance(
        db: Session,
        account_id: int,
        as_of: Optional[datetime] = None,
        include_planned: bool = False
    ) -> int:
        """
        Calculates exact ledger balance deterministically in integer pence using balance anchors.
        Formula: Anchor Balance + sum(Transactions occurring strictly after the Anchor cutoff up to as_of).
        Transactions on or before the anchor cutoff do not adjust the anchor balance.
        By default (as_of is None and include_planned is False), bounds the calculation to current UTC time (now),
        ensuring future-dated / planned transactions do not affect current balances before their effective date.
        """
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            raise ValueError(f"Account with ID {account_id} not found.")

        # If it's an investment account, balance is strictly derived from active holdings rollup
        if account.account_type == AccountType.INVESTMENT:
            from app.core.investments import get_account_holdings_breakdown
            breakdown = get_account_holdings_breakdown(db, account_id, as_of_date=as_of)
            return breakdown["total_pence"]

        effective_dt_col = func.coalesce(Transaction.effective_timestamp, Transaction.transaction_date)

        # 1. Query anchors
        anchors_query = db.query(AccountBalanceAnchor).filter(
            AccountBalanceAnchor.account_id == account_id
        )

        app_tz = get_app_timezone(db)
        today_local = get_today_local(app_tz)
        end_of_today_utc = get_end_of_day_utc(today_local, tz_str=app_tz)
        effective_as_of = as_of if as_of is not None else (None if include_planned else end_of_today_utc)

        target_anchor = None
        is_retrospective = False

        if effective_as_of is None:
            # Most recent anchor overall (when explicitly including planned activity across all time)
            target_anchor = anchors_query.order_by(
                AccountBalanceAnchor.anchor_date.desc(),
                AccountBalanceAnchor.id.desc()
            ).first()
        else:
            # Most recent anchor on or before effective_as_of
            target_anchor = anchors_query.filter(
                AccountBalanceAnchor.anchor_date <= effective_as_of
            ).order_by(
                AccountBalanceAnchor.anchor_date.desc(),
                AccountBalanceAnchor.id.desc()
            ).first()

            if not target_anchor:
                # effective_as_of is before earliest anchor -> retrospective inference
                earliest_anchor = anchors_query.order_by(
                    AccountBalanceAnchor.anchor_date.asc(),
                    AccountBalanceAnchor.id.asc()
                ).first()
                if earliest_anchor:
                    target_anchor = earliest_anchor
                    is_retrospective = True

        # Check if any incoming paired transfers to this account have a distinct destination-leg timestamp
        from app.core.review_suggestions import get_transfer_provenance_map
        from app.core.timezone import ensure_utc
        prov_map = get_transfer_provenance_map(db)
        paired_tx_ids = [int(k) for k in prov_map.keys() if str(k).isdigit()]
        incoming_paired_txs = []
        if paired_tx_ids:
            incoming_paired_txs = db.query(Transaction).filter(
                Transaction.deleted_at.is_(None),
                Transaction.id.in_(paired_tx_ids),
                Transaction.destination_account_id == account_id,
                Transaction.transaction_type == TransactionType.TRANSFER
            ).all()
        incoming_paired_ids = [t.id for t in incoming_paired_txs]

        incoming_transfer_cond = (
            (Transaction.destination_account_id == account_id)
            & (Transaction.transaction_type == TransactionType.TRANSFER)
        )
        if incoming_paired_ids:
            incoming_transfer_cond = incoming_transfer_cond & (~Transaction.id.in_(incoming_paired_ids))

        # Compute net delta via SQL aggregation
        delta_case = case(
            # Positive additions to this account:
            (
                (Transaction.account_id == account_id) & (Transaction.transaction_type == TransactionType.INCOME),
                Transaction.amount_pence
            ),
            (
                incoming_transfer_cond,
                Transaction.amount_pence
            ),
            (
                (Transaction.account_id == account_id) & (Transaction.transaction_type == TransactionType.ADJUSTMENT) & (Transaction.notes.like("%[Positive adjustment]%")),
                Transaction.amount_pence
            ),
            # Negative deductions from this account:
            (
                (Transaction.account_id == account_id) & (Transaction.transaction_type == TransactionType.EXPENSE),
                -Transaction.amount_pence
            ),
            (
                (Transaction.account_id == account_id) & (Transaction.transaction_type == TransactionType.TRANSFER),
                -Transaction.amount_pence
            ),
            (
                (Transaction.account_id == account_id) & (Transaction.transaction_type == TransactionType.ADJUSTMENT) & (~Transaction.notes.like("%[Positive adjustment]%")),
                -Transaction.amount_pence
            ),
            else_=0
        )

        tx_filter = [
            Transaction.deleted_at.is_(None),
            or_(
                Transaction.account_id == account_id,
                Transaction.destination_account_id == account_id
            )
        ]

        if target_anchor:
            if not is_retrospective:
                tx_filter.append(effective_dt_col > target_anchor.anchor_date)
                if effective_as_of is not None:
                    tx_filter.append(effective_dt_col <= effective_as_of)
            else:
                tx_filter.append(effective_dt_col > effective_as_of)
                tx_filter.append(effective_dt_col <= target_anchor.anchor_date)
        else:
            if effective_as_of is not None:
                tx_filter.append(effective_dt_col <= effective_as_of)

        net_delta = db.query(func.coalesce(func.sum(delta_case), 0)).filter(*tx_filter).scalar() or 0

        # Evaluate incoming paired transfers against destination_leg's effective timestamp
        if incoming_paired_txs:
            anchor_utc = ensure_utc(target_anchor.anchor_date) if target_anchor else None
            as_of_utc = ensure_utc(effective_as_of) if effective_as_of is not None else None
            for t in incoming_paired_txs:
                prov = prov_map.get(str(t.id)) or {}
                dest_leg = prov.get("destination_leg") or {}
                raw_dest_ts = dest_leg.get("effective_timestamp") or dest_leg.get("transaction_date")
                dest_eff_utc = None
                if raw_dest_ts:
                    try:
                        dest_eff_utc = ensure_utc(datetime.fromisoformat(str(raw_dest_ts)))
                    except Exception:
                        dest_eff_utc = None
                if dest_eff_utc is None:
                    dest_eff_utc = ensure_utc(t.effective_timestamp or t.transaction_date)

                include_leg = False
                if anchor_utc is not None:
                    if not is_retrospective:
                        if dest_eff_utc > anchor_utc and (as_of_utc is None or dest_eff_utc <= as_of_utc):
                            include_leg = True
                    else:
                        if as_of_utc is not None and dest_eff_utc > as_of_utc and dest_eff_utc <= anchor_utc:
                            include_leg = True
                else:
                    if as_of_utc is None or dest_eff_utc <= as_of_utc:
                        include_leg = True

                if include_leg:
                    net_delta += (t.amount_pence or 0)

        if target_anchor:
            if not is_retrospective:
                return target_anchor.balance_pence + net_delta
            else:
                return target_anchor.balance_pence - net_delta
        else:
            return account.starting_balance_pence + net_delta

    @staticmethod
    def get_account_balance_info(db: Session, account_id: int, as_of: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Returns full anchor & balance metadata:
        - current_balance_pence
        - anchor_id, anchor_date, anchor_balance_pence
        - is_opening, is_retrospective, delta_since_anchor_pence
        - anchor_label (e.g. 'Ledger balance · anchored as of 21/10/2026')
        """
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            raise ValueError(f"Account with ID {account_id} not found.")

        bal_pence = LedgerEngine.get_account_balance(db, account_id, as_of=as_of, include_planned=False)
        projected_bal_pence = LedgerEngine.get_account_balance(db, account_id, as_of=as_of, include_planned=True)
        planned_delta_pence = projected_bal_pence - bal_pence

        curr_spec = get_currency_spec(account.currency)
        app_tz = get_app_timezone(db)

        if account.account_type == AccountType.INVESTMENT:
            from app.core.investments import get_account_holdings_breakdown
            breakdown = get_account_holdings_breakdown(db, account_id, as_of_date=as_of)
            if breakdown["holdings_count"] == 0:
                anchor_label = "Holdings balance · No holdings"
            elif breakdown["valued_count"] == 0:
                anchor_label = "Holdings balance · Unvalued"
            elif breakdown["has_unvalued_holdings"]:
                anchor_label = f"Holdings balance · {breakdown['valued_count']} of {breakdown['holdings_count']} valued"
            else:
                anchor_label = f"Holdings balance · {breakdown['valued_count']} active holdings"

            return {
                "account_id": account_id,
                "current_balance_pence": bal_pence,
                "current_balance_pounds": pence_to_pounds(bal_pence),
                "formatted_balance": format_pence(bal_pence, currency_symbol=curr_spec.symbol),
                "projected_balance_pence": projected_bal_pence,
                "formatted_projected_balance": format_pence(projected_bal_pence, currency_symbol=curr_spec.symbol),
                "planned_delta_pence": planned_delta_pence,
                "formatted_planned_delta": format_pence(planned_delta_pence, currency_symbol=curr_spec.symbol),
                "anchor_id": None,
                "anchor_date": None,
                "anchor_balance_pence": bal_pence,
                "is_opening": True,
                "delta_since_anchor_pence": 0,
                "anchor_label": anchor_label,
            }

        # Get latest anchor
        anchors_query = db.query(AccountBalanceAnchor).filter(
            AccountBalanceAnchor.account_id == account_id
        )
        if as_of is None:
            anchor = anchors_query.order_by(
                AccountBalanceAnchor.anchor_date.desc(),
                AccountBalanceAnchor.id.desc()
            ).first()
        else:
            anchor = anchors_query.filter(
                AccountBalanceAnchor.anchor_date <= as_of
            ).order_by(
                AccountBalanceAnchor.anchor_date.desc(),
                AccountBalanceAnchor.id.desc()
            ).first()

        anchor_label = "Ledger balance · unanchored"
        anchor_date_val = None
        anchor_balance_val = None
        anchor_id_val = None
        is_opening_val = True
        delta_val = 0

        if anchor:
            anchor_id_val = anchor.id
            anchor_date_val = anchor.anchor_date
            anchor_balance_val = anchor.balance_pence
            is_opening_val = anchor.is_opening
            delta_val = bal_pence - anchor.balance_pence

            # Format anchor_label in app timezone
            try:
                tz = ZoneInfo(app_tz)
                local_dt = anchor.anchor_date.astimezone(tz) if anchor.anchor_date.tzinfo else anchor.anchor_date.replace(tzinfo=timezone.utc).astimezone(tz)
                today_local = get_today_local(app_tz)
                if local_dt.date() == today_local:
                    anchor_label = f"Ledger balance · anchored as of {local_dt.strftime('%H:%M')} today"
                else:
                    anchor_label = f"Ledger balance · anchored as of {local_dt.strftime('%d/%m/%Y')}"
            except Exception:
                anchor_label = f"Ledger balance · anchored as of {anchor.anchor_date.strftime('%d/%m/%Y')}"

        return {
            "account_id": account_id,
            "current_balance_pence": bal_pence,
            "current_balance_pounds": pence_to_pounds(bal_pence),
            "formatted_balance": format_pence(bal_pence, currency_symbol=curr_spec.symbol),
            "projected_balance_pence": projected_bal_pence,
            "formatted_projected_balance": format_pence(projected_bal_pence, currency_symbol=curr_spec.symbol),
            "planned_delta_pence": planned_delta_pence,
            "formatted_planned_delta": format_pence(planned_delta_pence, currency_symbol=curr_spec.symbol),
            "anchor_id": anchor_id_val,
            "anchor_date": anchor_date_val,
            "anchor_balance_pence": anchor_balance_val,
            "is_opening": is_opening_val,
            "delta_since_anchor_pence": delta_val,
            "anchor_label": anchor_label,
        }

    @staticmethod
    def record_transfer(
        db: Session,
        source_account_id: int,
        dest_account_id: int,
        amount_pence: int,
        date: datetime,
        notes: str = ""
    ) -> Transaction:
        """Records an internal transfer between two distinct accounts."""
        if source_account_id == dest_account_id:
            raise ValueError("Source and destination accounts must be distinct.")
        if amount_pence <= 0:
            raise ValueError("Transfer amount must be strictly positive.")

        source_acc = db.query(Account).filter(Account.id == source_account_id).first()
        dest_acc = db.query(Account).filter(Account.id == dest_account_id).first()
        if not source_acc or not dest_acc:
            raise ValueError("Source and destination accounts must exist.")

        base_curr = get_effective_base_currency(db)
        if source_acc.currency != base_curr or dest_acc.currency != base_curr:
            raise ValueError(f"Transfers are only supported between accounts using the base currency ({base_curr}).")

        tx = Transaction(
            transaction_date=date,
            effective_timestamp=get_now_utc() if date is None else date,
            created_at=get_now_utc(),
            transaction_type=TransactionType.TRANSFER,
            amount_pence=amount_pence,
            merchant="Internal Transfer",
            notes=notes,
            account_id=source_account_id,
            destination_account_id=dest_account_id,
            entry_method="manual"
        )
        db.add(tx)
        db.commit()
        db.refresh(tx)
        return tx

    @staticmethod
    def get_dashboard_summary(db: Session) -> Dict[str, Any]:
        """
        Calculates executive metrics:
        - Liquid holdings (Current & Savings)
        - Credit liabilities (Credit Card debt)
        - Investment valuations (ISAs, pensions, portfolios)
        - Net Worth = Liquid + Invested - Credit Debt
        """
        base_curr = get_effective_base_currency(db)
        base_spec = get_currency_spec(base_curr)

        # Strictly include only accounts denominated in the configured base currency.
        # Any non-base account balances are never aggregated into base net worth without conversion.
        accounts = db.query(Account).filter(Account.is_active == True, Account.currency == base_curr).all()

        total_liquid_pence = 0
        total_debt_pence = 0
        total_invested_pence = 0

        for acc in accounts:
            bal = LedgerEngine.get_account_balance(db, acc.id)
            if acc.account_type in (AccountType.CURRENT, AccountType.SAVINGS, AccountType.CASH):
                total_liquid_pence += bal
            elif acc.account_type == AccountType.CREDIT_CARD:
                if bal < 0:
                    total_debt_pence += abs(bal)
            elif acc.account_type == AccountType.INVESTMENT:
                total_invested_pence += bal

        net_worth_pence = total_liquid_pence + total_invested_pence - total_debt_pence

        app_tz = get_app_timezone(db)
        today_local = get_today_local(app_tz)
        end_of_today_utc = get_end_of_day_utc(today_local, tz_str=app_tz)

        effective_dt_col = func.coalesce(Transaction.effective_timestamp, Transaction.transaction_date)
        acc_ids = [acc.id for acc in accounts]

        planned_income_pence = 0
        planned_expenses_pence = 0
        planned_count = 0

        if acc_ids:
            planned_txs = db.query(Transaction).filter(
                Transaction.deleted_at.is_(None),
                effective_dt_col > end_of_today_utc,
                or_(
                    Transaction.account_id.in_(acc_ids),
                    Transaction.destination_account_id.in_(acc_ids),
                    Transaction.account_id.is_(None)
                )
            ).all()

            planned_count = len(planned_txs)
            for pt in planned_txs:
                amt = pt.amount_pence or 0
                if pt.transaction_type == TransactionType.INCOME:
                    planned_income_pence += amt
                elif pt.transaction_type == TransactionType.EXPENSE:
                    planned_expenses_pence += amt

        planned_net_pence = planned_income_pence - planned_expenses_pence

        return {
            "net_worth_pence": net_worth_pence,
            "net_worth_pounds": pence_to_pounds(net_worth_pence),
            "formatted_net_worth": format_pence(net_worth_pence, currency_symbol=base_spec.symbol),
            
            "total_liquid_pence": total_liquid_pence,
            "total_liquid_pounds": pence_to_pounds(total_liquid_pence),
            "formatted_total_liquid": format_pence(total_liquid_pence, currency_symbol=base_spec.symbol),

            "total_debt_pence": total_debt_pence,
            "total_debt_pounds": pence_to_pounds(total_debt_pence),
            "formatted_total_debt": format_pence(total_debt_pence, currency_symbol=base_spec.symbol),

            "total_invested_pence": total_invested_pence,
            "total_invested_pounds": pence_to_pounds(total_invested_pence),
            "formatted_total_invested": format_pence(total_invested_pence, currency_symbol=base_spec.symbol),

            "planned_income_pence": planned_income_pence,
            "planned_expenses_pence": planned_expenses_pence,
            "planned_net_pence": planned_net_pence,
            "planned_count": planned_count,
            "formatted_planned_net": format_pence(planned_net_pence, currency_symbol=base_spec.symbol),
        }
