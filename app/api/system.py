from pathlib import Path
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db, get_current_profile
from app.core.profiles import ProfileMetadata
from app.config import BACKUP_DIR
from app.schemas import (
    SystemSettingsResponse,
    SystemSettingsUpdate,
    BackupArchiveInfo,
    BackupCreationResponse,
    SystemConfigResponse,
    CurrencySpecResponse,
)
from app.core.currency import get_base_currency_spec, SUPPORTED_CURRENCIES
from app.core.timezone import get_app_timezone
from app.core.backup import (
    generate_backup_bundle,
    list_existing_backups,
    evaluate_backup_schedule,
    set_system_setting,
    get_system_setting
)

router = APIRouter(prefix="/system")

@router.get("/config", response_model=SystemConfigResponse)
def get_system_config(db: Session = Depends(get_db)):
    """Returns base currency code, symbol, precision, display name, and supported currency specs."""
    spec = get_base_currency_spec(db)
    supported = {
        code: CurrencySpecResponse(
            code=c.code,
            symbol=c.symbol,
            precision=c.precision,
            name=c.name,
            can_be_base=(c.precision == 2)
        )
        for code, c in SUPPORTED_CURRENCIES.items()
    }
    return SystemConfigResponse(
        base_currency=spec.code,
        base_currency_symbol=spec.symbol,
        base_currency_decimals=spec.precision,
        base_currency_name=spec.name,
        supported_currencies=supported,
        app_timezone=get_app_timezone(db)
    )

@router.get("/settings", response_model=SystemSettingsResponse)
@router.get("/backup-status", response_model=SystemSettingsResponse)
def get_system_settings(db: Session = Depends(get_db), profile: ProfileMetadata = Depends(get_current_profile)):
    """
    Returns system settings, backup automation status, and per-profile import confidence thresholds.
    """
    return evaluate_backup_schedule(
        db,
        backup_dir=profile.backups_dir,
        staging_receipts_dir=profile.staging_receipts_dir,
        archive_receipts_dir=profile.receipts_dir
    )

@router.put("/settings", response_model=SystemSettingsResponse)
def update_system_settings(
    payload: SystemSettingsUpdate,
    db: Session = Depends(get_db),
    profile: ProfileMetadata = Depends(get_current_profile)
):
    """Updates backup automation and suggestion confidence preferences in SQLite."""
    if payload.backup_automation_enabled is not None:
        set_system_setting(db, "backup_automation_enabled", "true" if payload.backup_automation_enabled else "false")
    if payload.backup_frequency_days is not None:
        set_system_setting(db, "backup_frequency_days", str(payload.backup_frequency_days))
    if payload.import_confidence_category is not None:
        set_system_setting(db, "import_confidence_category", payload.import_confidence_category)
    if payload.import_confidence_account is not None:
        set_system_setting(db, "import_confidence_account", payload.import_confidence_account)

    return evaluate_backup_schedule(
        db,
        backup_dir=profile.backups_dir,
        staging_receipts_dir=profile.staging_receipts_dir,
        archive_receipts_dir=profile.receipts_dir
    )

@router.post("/backup", response_model=BackupCreationResponse, status_code=status.HTTP_201_CREATED)
def create_backup_now(
    db: Session = Depends(get_db),
    profile: ProfileMetadata = Depends(get_current_profile)
):
    """Triggers an immediate validated on-demand backup."""
    try:
        res = generate_backup_bundle(
            db,
            backup_dir=profile.backups_dir,
            staging_receipts_dir=profile.staging_receipts_dir,
            archive_receipts_dir=profile.receipts_dir
        )
        return BackupCreationResponse(
            success=True,
            filename=res["filename"],
            filepath=res["filepath"],
            size_formatted=res["size_formatted"],
            created_at=res["created_at"],
            manifest=res["manifest"]
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backup generation failed: {str(e)}"
        )

@router.get("/backups", response_model=List[BackupArchiveInfo])
def get_backup_archives(profile: ProfileMetadata = Depends(get_current_profile)):
    """Lists all valid dated backups in the archive directory."""
    backups = list_existing_backups(profile.backups_dir)
    return [
        BackupArchiveInfo(
            filename=b["filename"],
            filepath=b["filepath"],
            created_at=b["created_at"],
            size_bytes=b["size_bytes"],
            size_formatted=b["size_formatted"],
            manifest=b["manifest"]
        )
        for b in backups
    ]

@router.get("/backups/{filename}/download")
def download_backup_archive(filename: str, profile: ProfileMetadata = Depends(get_current_profile)):
    """Securely downloads a specific backup archive ZIP."""
    # Prevent directory traversal
    clean_name = Path(filename).name
    file_path = profile.backups_dir / clean_name
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backup archive '{clean_name}' not found."
        )

    return FileResponse(
        path=file_path,
        filename=clean_name,
        media_type="application/zip"
    )
