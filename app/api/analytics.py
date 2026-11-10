from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import CashFlowSummaryResponse, ComprehensiveAnalysisResponse
from app.core.cashflow import get_cashflow_summary
from app.core.analysis import get_comprehensive_analysis, generate_analysis_export

router = APIRouter(prefix="/analytics")


def _parse_id_list_param(raw: Optional[str]) -> Optional[List[int]]:
    if not raw:
        return None
    result: List[int] = []
    for part in str(raw).split(","):
        p = part.strip()
        if not p:
            continue
        try:
            val = int(p)
            if val not in result:
                result.append(val)
        except ValueError:
            continue
    return result if result else None


@router.get("/comprehensive", response_model=ComprehensiveAnalysisResponse)
@router.get("/analysis", response_model=ComprehensiveAnalysisResponse)
def get_analysis(
    preset: Optional[str] = Query("month", description="Date preset (day, week, month, 3m, 6m, year, 5y, all, custom)"),
    start_date: Optional[str] = Query(None, description="Custom start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Custom end date (YYYY-MM-DD)"),
    interval: Optional[str] = Query(None, description="Grouping interval (day, week, month, quarter, year)"),
    currency: Optional[str] = Query(None, description="Currency filter, e.g. 'GBP'"),
    account_id: Optional[int] = Query(None, description="Optional single account filter"),
    account_ids: Optional[str] = Query(None, description="Optional comma-separated account IDs for multi-select filter"),
    category_id: Optional[int] = Query(None, description="Optional single category filter"),
    category_ids: Optional[str] = Query(None, description="Optional comma-separated category IDs (0 = Uncategorised)"),
    offset: Optional[int] = Query(0, description="Optional period navigation offset"),
    db: Session = Depends(get_db)
):
    """
    Computes multidimensional financial analysis across Overview, Cash Flow, Spending,
    Balances & Net Worth, and Investment portfolio values.
    """
    try:
        parsed_account_ids = _parse_id_list_param(account_ids)
        parsed_category_ids = _parse_id_list_param(category_ids)
        return get_comprehensive_analysis(
            db=db,
            preset=preset,
            custom_start=start_date,
            custom_end=end_date,
            interval=interval,
            currency_param=currency,
            account_id=account_id,
            category_id=category_id,
            offset=offset,
            account_ids=parsed_account_ids,
            category_ids=parsed_category_ids,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/export")
def export_analysis_table(
    report_type: Optional[str] = Query("spending_matrix", description="Report table: spending_matrix, overview_cashflow, spending_categories, net_worth, investments"),
    format: Optional[str] = Query("xlsx", description="Export format: csv or xlsx"),
    preset: Optional[str] = Query("month", description="Date preset (day, week, month, 3m, 6m, year, 5y, all, custom)"),
    start_date: Optional[str] = Query(None, description="Custom start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Custom end date (YYYY-MM-DD)"),
    interval: Optional[str] = Query(None, description="Grouping interval (day, week, month, quarter, year)"),
    currency: Optional[str] = Query(None, description="Currency filter, e.g. 'GBP'"),
    account_id: Optional[int] = Query(None, description="Optional single account filter"),
    account_ids: Optional[str] = Query(None, description="Optional comma-separated account IDs for multi-select filter"),
    category_id: Optional[int] = Query(None, description="Optional single category filter"),
    category_ids: Optional[str] = Query(None, description="Optional comma-separated category IDs (0 = Uncategorised)"),
    offset: Optional[int] = Query(0, description="Optional period navigation offset"),
    db: Session = Depends(get_db),
):
    """
    Exports a profile-scoped CSV or XLSX spreadsheet for the requested Analysis table,
    reflecting the full current date range, group-by interval, and account/category filters.
    """
    try:
        parsed_account_ids = _parse_id_list_param(account_ids)
        parsed_category_ids = _parse_id_list_param(category_ids)
        file_bytes, filename, media_type = generate_analysis_export(
            db=db,
            report_type=report_type or "spending_matrix",
            export_format=format or "xlsx",
            preset=preset,
            custom_start=start_date,
            custom_end=end_date,
            interval=interval,
            currency_param=currency,
            account_id=account_id,
            category_id=category_id,
            offset=offset,
            account_ids=parsed_account_ids,
            category_ids=parsed_category_ids,
        )
        return Response(
            content=file_bytes,
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
            },
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/cashflow", response_model=CashFlowSummaryResponse)
def get_monthly_cashflow(
    month: Optional[str] = Query(None, description="Target month in YYYY-MM format, e.g. '2026-10'"),
    currency: Optional[str] = Query(None, description="Currency filter, e.g. 'GBP'"),
    account_id: Optional[int] = Query(None, description="Optional account ID filter"),
    db: Session = Depends(get_db)
):
    """
    Computes cash flow analytics for a selected month and currency:
    - Inflow (Income) from external sources
    - Fixed, Variable, and Unclassified expense breakdowns (respecting per-transaction overrides)
    - Net surplus/deficit and guarded savings rate
    - Spending by category
    - Trailing 6-month historical trajectory
    - Transfers strictly contribute £0 to income and expenses
    - Reconciliation adjustments separated and attributed
    """
    try:
        summary = get_cashflow_summary(
            db=db,
            month_str=month,
            currency_param=currency,
            account_id=account_id
        )
        return summary
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


