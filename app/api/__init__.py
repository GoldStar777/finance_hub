from fastapi import APIRouter, HTTPException, status
from app.api.health import router as health_router
from app.api.accounts import router as accounts_router
from app.api.categories import router as categories_router
from app.api.dashboard import router as dashboard_router
from app.api.transactions import router as transactions_router
from app.api.system import router as system_router
from app.api.staging import router as staging_router
from app.api.investments import router as investments_router
from app.api.analytics import router as analytics_router
from app.api.reconciliation import router as reconciliation_router
from app.api.profiles import router as profiles_router
from app.api.review import router as review_router

api_router = APIRouter(prefix="/api")
api_router.include_router(health_router, tags=["Health"])
api_router.include_router(profiles_router, tags=["Profiles"])
api_router.include_router(accounts_router, tags=["Accounts"])
api_router.include_router(reconciliation_router, tags=["Reconciliation"])
api_router.include_router(categories_router, tags=["Categories"])
api_router.include_router(dashboard_router, tags=["Dashboard"])
api_router.include_router(transactions_router, tags=["Transactions"])
api_router.include_router(system_router, tags=["System"])
api_router.include_router(staging_router, tags=["Staging"])
api_router.include_router(investments_router, tags=["Investments"])
api_router.include_router(analytics_router, tags=["Analytics"])
api_router.include_router(review_router, tags=["Data Quality & Review"])

@api_router.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def api_catch_all(path_name: str):
    """Guarantees unmapped /api routes return 404 JSON rather than falling through to SPA HTML."""
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"API endpoint not found: /api/{path_name}"
    )

