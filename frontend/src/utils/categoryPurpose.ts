import type { Category, CategoryType, TransactionType } from '../types';

/**
 * Returns the category purpose required for a given transaction type,
 * or null for transfers and adjustments which do not use categories.
 */
export function expectedCategoryTypeForTransaction(
  txType: TransactionType | string | null | undefined
): CategoryType | null {
  const norm = String(txType || '').trim().toLowerCase();
  if (norm === 'expense') return 'expense';
  if (norm === 'income') return 'income';
  return null;
}

/**
 * Returns the effective purpose of a category, defaulting deterministically to 'expense'.
 */
export function getCategoryPurpose(
  cat: Pick<Category, 'category_type'> | { category_type?: string | null } | null | undefined
): CategoryType {
  return String(cat?.category_type || 'expense').trim().toLowerCase() === 'income'
    ? 'income'
    : 'expense';
}

/**
 * Filters a category list so only categories matching the target transaction type appear.
 */
export function filterCategoriesForTransactionType<
  T extends { is_active?: boolean; category_type?: string | null }
>(
  categories: T[],
  txType: TransactionType | string | null | undefined,
  includeInactive = false
): T[] {
  const expected = expectedCategoryTypeForTransaction(txType);
  if (!expected) return [];
  return categories.filter((c) => {
    if (!includeInactive && c.is_active === false) return false;
    return getCategoryPurpose(c) === expected;
  });
}

/**
 * Returns true if the supplied category ID exists in `categories` and matches `txType`.
 */
export function isCategoryCompatibleWithTransaction(
  categories: Array<Pick<Category, 'id' | 'category_type'>>,
  categoryId: number | null | undefined,
  txType: TransactionType | string | null | undefined
): boolean {
  if (categoryId === null || categoryId === undefined) return true;
  const expected = expectedCategoryTypeForTransaction(txType);
  if (!expected) return false;
  const cat = categories.find((c) => c.id === categoryId);
  if (!cat) return false;
  return getCategoryPurpose(cat) === expected;
}
