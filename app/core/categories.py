import json
from typing import Dict, Optional
from sqlalchemy.orm import Session
from app.core.backup import get_system_setting, set_system_setting
from app.models import Category, CategoryType, TransactionType

CATEGORY_DESCRIPTIONS_SETTING_KEY = "category_descriptions"


class CategoryValidationError(ValueError):
    """Domain validation error carrying an appropriate HTTP status code for API callers."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def expected_category_type_for_transaction(tx_type: Optional[TransactionType]) -> Optional[CategoryType]:
    """Returns the required CategoryType for a transaction type, or None for transfers/adjustments."""
    if tx_type == TransactionType.EXPENSE:
        return CategoryType.EXPENSE
    if tx_type == TransactionType.INCOME:
        return CategoryType.INCOME
    return None


def validate_category_for_transaction_type(
    db: Session,
    category_id: Optional[int],
    tx_type: TransactionType,
) -> Optional[Category]:
    """Validates that category_id (if supplied) exists and matches tx_type's category purpose."""
    expected = expected_category_type_for_transaction(tx_type)
    if category_id is None:
        return None

    if expected is None:
        raise CategoryValidationError(
            f"Transactions of type '{tx_type.value}' cannot be assigned a category. Leave category empty.",
            status_code=400,
        )

    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise CategoryValidationError(f"Category with ID {category_id} not found.", status_code=404)

    actual = getattr(cat, "category_type", None) or CategoryType.EXPENSE
    if actual != expected:
        raise CategoryValidationError(
            f"{actual.value.capitalize()} category '{cat.name}' cannot be assigned to an {tx_type.value} transaction. "
            f"Clear it or choose an {expected.value} category.",
            status_code=400,
        )
    return cat

def get_category_descriptions(db: Session) -> Dict[int, str]:
    """
    Retrieves user-maintained category descriptions mapping category_id -> description.
    100% local, profile-isolated via system_settings.
    """
    raw = get_system_setting(db, CATEGORY_DESCRIPTIONS_SETTING_KEY, "{}")
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return {int(k): str(v) for k, v in data.items() if v and str(v).strip()}
        return {}
    except Exception:
        return {}

def get_category_description(db: Session, category_id: int, fallback: Optional[str] = None) -> Optional[str]:
    """
    Returns description for a specific category id.
    Checks column fallback first if present, then profile system_settings.
    """
    if fallback and str(fallback).strip():
        return str(fallback).strip()
    descs = get_category_descriptions(db)
    return descs.get(category_id)

def save_category_description(db: Session, category_id: int, description: Optional[str]) -> None:
    """
    Saves or deletes a description for a category in profile system_settings.
    """
    descs = get_category_descriptions(db)
    clean_desc = (description or "").strip()
    if clean_desc:
        descs[category_id] = clean_desc
    elif category_id in descs:
        del descs[category_id]
    set_system_setting(db, CATEGORY_DESCRIPTIONS_SETTING_KEY, json.dumps(descs, indent=2))

def delete_category_description(db: Session, category_id: int) -> None:
    """
    Removes description entry for a category when it is deleted.
    """
    descs = get_category_descriptions(db)
    if category_id in descs:
        del descs[category_id]
        set_system_setting(db, CATEGORY_DESCRIPTIONS_SETTING_KEY, json.dumps(descs, indent=2))

