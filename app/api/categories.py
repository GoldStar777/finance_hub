from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.categories import (
    get_category_description,
    save_category_description,
    delete_category_description,
)
from app.database import get_db
from app.models import Category, CategoryType, ExpenseNature, Transaction
from app.schemas import CategoryCreate, CategoryUpdate, CategoryResponse, CategoryDeletionImpact

router = APIRouter(prefix="/categories")

def _to_category_response(db: Session, cat: Category) -> CategoryResponse:
    tx_count = db.query(Transaction).filter(Transaction.category_id == cat.id).count()
    desc = get_category_description(db, cat.id, getattr(cat, "description", None))
    cat_type = getattr(cat, "category_type", None) or CategoryType.EXPENSE
    nature = ExpenseNature.UNCLASSIFIED if cat_type == CategoryType.INCOME else cat.default_expense_nature
    return CategoryResponse(
        id=cat.id,
        name=cat.name,
        category_type=cat_type,
        color=cat.color,
        default_expense_nature=nature,
        is_active=cat.is_active,
        description=desc,
        transaction_count=tx_count,
    )

@router.get("", response_model=List[CategoryResponse])
def list_categories(
    include_inactive: bool = False,
    category_type: Optional[CategoryType] = None,
    db: Session = Depends(get_db),
):
    """List categories with their purpose, default expense nature, and transaction counts."""
    query = db.query(Category)
    if not include_inactive:
        query = query.filter(Category.is_active == True)
    if category_type is not None:
        query = query.filter(Category.category_type == category_type)
    cats = query.order_by(Category.name.asc()).all()
    return [_to_category_response(db, c) for c in cats]

@router.get("/{category_id}", response_model=CategoryResponse)
def get_category(category_id: int, db: Session = Depends(get_db)):
    """Retrieves a single category by ID with its usage count."""
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")
    return _to_category_response(db, cat)

@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(payload: CategoryCreate, db: Session = Depends(get_db)):
    """Creates a new expense or income category (or reactivates a matching archived one)."""
    clean_name = payload.name.strip()
    target_type = payload.category_type or CategoryType.EXPENSE
    target_nature = (
        ExpenseNature.UNCLASSIFIED
        if target_type == CategoryType.INCOME
        else payload.default_expense_nature
    )

    existing = db.query(Category).filter(Category.name.ilike(clean_name)).first()
    if existing:
        existing_type = existing.category_type or CategoryType.EXPENSE
        if not existing.is_active:
            if existing_type != target_type:
                tx_count = db.query(Transaction).filter(Transaction.category_id == existing.id).count()
                if tx_count > 0:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Archived category '{existing.name}' is an {existing_type.value} category "
                            f"referenced by {tx_count} historical transaction(s) and cannot be recreated "
                            f"as {target_type.value}. Reactivate it or choose a different name."
                        ),
                    )
                existing.category_type = target_type
            existing.is_active = True
            if payload.color:
                existing.color = payload.color
            existing.default_expense_nature = target_nature
            db.commit()
            db.refresh(existing)
            if payload.description is not None:
                save_category_description(db, existing.id, payload.description)
            return _to_category_response(db, existing)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Category '{clean_name}' already exists as an {existing_type.value} category."
        )

    cat = Category(
        name=clean_name,
        category_type=target_type,
        color=payload.color,
        default_expense_nature=target_nature,
        is_active=True
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    if payload.description is not None:
        save_category_description(db, cat.id, payload.description)
    return _to_category_response(db, cat)

@router.put("/{category_id}", response_model=CategoryResponse)
def update_category(category_id: int, payload: CategoryUpdate, db: Session = Depends(get_db)):
    """Updates category name, purpose, color, default expense nature, or active status."""
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")

    if payload.name is not None:
        clean_name = payload.name.strip()
        existing = db.query(Category).filter(Category.name.ilike(clean_name), Category.id != category_id).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Category '{clean_name}' already exists."
            )
        cat.name = clean_name

    old_type = cat.category_type or CategoryType.EXPENSE
    if payload.category_type is not None and payload.category_type != old_type:
        tx_count = db.query(Transaction).filter(Transaction.category_id == category_id).count()
        if tx_count > 0:
            if payload.reassign_existing_to_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Cannot change '{cat.name}' from {old_type.value} to {payload.category_type.value} "
                        f"because {tx_count} transaction(s) reference it. Reassign those transactions to "
                        f"another active {old_type.value} category first."
                    ),
                )
            if payload.reassign_existing_to_id == category_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot reassign transactions to the category being updated.",
                )
            target_cat = db.query(Category).filter(Category.id == payload.reassign_existing_to_id).first()
            if not target_cat:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Reassignment category with ID {payload.reassign_existing_to_id} not found.",
                )
            if not target_cat.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Reassignment category '{target_cat.name}' is archived. Please choose an active {old_type.value} category.",
                )
            target_cat_type = target_cat.category_type or CategoryType.EXPENSE
            if target_cat_type != old_type:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Reassignment category '{target_cat.name}' is an {target_cat_type.value} category, "
                        f"so it cannot receive historical {old_type.value} transactions."
                    ),
                )
            db.query(Transaction).filter(Transaction.category_id == category_id).update(
                {"category_id": payload.reassign_existing_to_id}, synchronize_session=False
            )
        cat.category_type = payload.category_type

    if payload.color is not None:
        cat.color = payload.color

    effective_type = cat.category_type or CategoryType.EXPENSE
    if effective_type == CategoryType.INCOME:
        cat.default_expense_nature = ExpenseNature.UNCLASSIFIED
    elif payload.default_expense_nature is not None:
        cat.default_expense_nature = payload.default_expense_nature

    if payload.is_active is not None:
        cat.is_active = payload.is_active

    if payload.description is not None:
        save_category_description(db, cat.id, payload.description)

    db.commit()
    db.refresh(cat)
    return _to_category_response(db, cat)

@router.get("/{category_id}/deletion-impact", response_model=CategoryDeletionImpact)
def get_category_deletion_impact(category_id: int, db: Session = Depends(get_db)):
    """Computes transaction usage impact before category deletion."""
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")
    tx_count = db.query(Transaction).filter(Transaction.category_id == category_id).count()
    return CategoryDeletionImpact(
        category_id=cat.id,
        category_name=cat.name,
        category_type=cat.category_type or CategoryType.EXPENSE,
        transaction_count=tx_count,
    )

@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: int, 
    permanent: bool = False, 
    reassign_to_id: Optional[int] = None, 
    db: Session = Depends(get_db)
):
    """Soft-deletes (archives) or permanently deletes a category.
    
    If permanent deletion is requested and the category is in use,
    transactions must be explicitly reassigned to another active category
    to protect audit history integrity.
    """
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")

    if not permanent:
        cat.is_active = False
        db.commit()
        return None

    # Permanent deletion flow
    tx_count = db.query(Transaction).filter(Transaction.category_id == category_id).count()
    if tx_count > 0:
        if reassign_to_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Category '{cat.name}' is currently used by {tx_count} transaction(s). Reassign them to another active category before permanent deletion, or archive it instead."
            )
        if reassign_to_id == category_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot reassign transactions to the category being deleted."
            )
        target_cat = db.query(Category).filter(Category.id == reassign_to_id).first()
        if not target_cat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Destination category with ID {reassign_to_id} not found."
            )
        if not target_cat.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Destination category '{target_cat.name}' is archived. Please choose an active category."
            )
        source_type = cat.category_type or CategoryType.EXPENSE
        target_type = target_cat.category_type or CategoryType.EXPENSE
        if target_type != source_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Destination category '{target_cat.name}' is an {target_type.value} category "
                    f"and cannot receive transactions from {source_type.value} category '{cat.name}'."
                ),
            )

        # Reassign all referencing transactions atomically
        db.query(Transaction).filter(Transaction.category_id == category_id).update(
            {"category_id": reassign_to_id}, synchronize_session=False
        )

    try:
        db.delete(cat)
        delete_category_description(db, category_id)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to permanently delete category: {str(exc)}"
        )
    return None

