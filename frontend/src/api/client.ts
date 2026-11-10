import type { 
  Account, 
  AccountCreatePayload, 
  AccountBreakdownResponse,
  DashboardSummary, 
  Category,
  CategoryType,
  CategoryCreatePayload,
  CategoryUpdatePayload,
  AccountUpdatePayload,
  AccountDeletionImpact,
  CategoryDeletionImpact,
  Transaction,
  TransactionCreatePayload,
  TransactionUpdatePayload,
  TransactionListResponse,
  RepeatTransactionCreatePayload,
  RepeatTransactionCreateResponse,
  TransactionFilters,
  MatchingTransactionIdsResponse,
  BulkTransactionUpdatePayload,
  BulkTransactionUpdateResult,
  BulkTransactionDeletePayload,
  BulkTransactionDeleteResult,
  RestoreTransactionsPayload,
  RestoreTransactionsResult,
  RecentlyDeletedSummary,
  SystemSettings,
  SystemSettingsUpdatePayload,
  BackupArchiveInfo,
  BackupCreationResponse,
  SystemConfig,
  StagingItem,
  StagingItemUpdatePayload,
  StagingSplitRequest,
  StagingSplitResponse,
  CSVImportResponse,
  StagingBatchApprovePayload,
  StagingBatchApproveResponse,
  StagingCountResponse,
  StatementMappingProfile,
  StatementMappingProfileCreatePayload,
  UnifiedImportResponse,
  UnifiedImportCommitPayload,
  UnifiedImportCommitResponse,
  PortfolioSummary,
  AccountHoldingsResponse,
  Holding,
  HoldingCreatePayload,
  HoldingUpdatePayload,
  HoldingValuation,
  HoldingValuationCreatePayload,
  CheckpointSyncResponse,
  CashFlowSummaryResponse,
  AccountSnapshotItem,
  ReconciliationSummaryResponse,
  ReconciliationSnapshotCreatePayload,
  ReconciliationResultResponse,
  ComprehensiveAnalysisResponse,
  AnalysisQueryParams,
  AnalysisExportReportType,
  AnalysisExportFormat,
  ProfileMetadata,
  ProfileCreatePayload,
  ProfileUpdatePayload,
  ProfileImpactResponse,
  ProfileDeletePayload,
  ReviewSuggestionsResponse,
  DataQualityReportResponse,
  DataQualityFindingsQuery
} from '../types';

const API_BASE = '/api';

export const PROFILE_STORAGE_KEY = 'finance_hub_active_profile_id';

function getStoredProfileId(): string | null {
  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      return window.localStorage.getItem(PROFILE_STORAGE_KEY);
    }
  } catch {
    // Ignore localStorage access restrictions
  }
  return null;
}

let currentProfileId: string | null = getStoredProfileId();

// Synchronize profile ID in memory across browser tabs via storage events
if (typeof window !== 'undefined' && window.addEventListener) {
  window.addEventListener('storage', (event: StorageEvent) => {
    if (event.key === PROFILE_STORAGE_KEY) {
      currentProfileId = event.newValue;
    }
  });
}

export function setActiveProfileId(id: string | null) {
  currentProfileId = id;
  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      if (id) {
        window.localStorage.setItem(PROFILE_STORAGE_KEY, id);
      } else {
        window.localStorage.removeItem(PROFILE_STORAGE_KEY);
      }
    }
  } catch {
    // Ignore localStorage access restrictions
  }
}

export function getActiveProfileId(): string | null {
  if (!currentProfileId) {
    currentProfileId = getStoredProfileId();
  }
  return currentProfileId;
}

async function request<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const headers: Record<string, string> = {};
  if (!(options?.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }
  const activeId = getActiveProfileId();
  currentProfileId = activeId;
  if (currentProfileId) {
    headers['X-Profile-ID'] = currentProfileId;
  }

  const response = await fetch(url, {
    ...options,
    headers: {
      ...headers,
      ...options?.headers,
    },
  });

  const contentType = response.headers.get('content-type') || '';

  if (!response.ok) {
    let errorMsg = `API Error (${response.status}): ${response.statusText}`;
    if (contentType.includes('application/json')) {
      try {
        const errData = await response.json();
        if (errData.detail) {
          errorMsg = errData.detail;
          if (
            response.status === 404 &&
            typeof errData.detail === 'string' &&
            errData.detail.toLowerCase().includes('profile') &&
            errData.detail.toLowerCase().includes('not found')
          ) {
            // Persisted profile is nonexistent/deleted on backend; clear invalid selection
            setActiveProfileId(null);
          }
        }
      } catch {
        // ignore
      }
    } else {
      try {
        const rawText = await response.text();
        if (rawText.includes('<!DOCTYPE html>') || contentType.includes('text/html')) {
          errorMsg = `API route not found on running server (${response.status} ${response.statusText}). If you recently added new backend routes, the application server needs to be restarted.`;
        }
      } catch {
        // ignore
      }
    }
    throw new Error(errorMsg);
  }

  if (response.status === 204) {
    return {} as T;
  }

  // Ensure content-type is JSON before parsing to prevent WebKit "String did not match the expected pattern"
  if (!contentType.includes('application/json')) {
    const rawText = await response.text();
    if (rawText.includes('<!DOCTYPE html>') || contentType.includes('text/html')) {
      throw new Error(`Server returned HTML instead of JSON for ${endpoint}. If new backend routes were recently added, the application server needs to be restarted.`);
    }
    throw new Error(`Expected JSON response from server but received: ${contentType || 'non-JSON content'}`);
  }

  try {
    return await response.json();
  } catch (err: any) {
    throw new Error(`Failed to parse server response as JSON: ${err.message}`);
  }
}

function buildTransactionFilterParams(filters: TransactionFilters = {}): URLSearchParams {
  const params = new URLSearchParams();

  // Multi-account or single account
  if (filters.accountIds && filters.accountIds.length > 0) {
    params.append('account_ids', filters.accountIds.join(','));
  } else if (filters.unassignedOnly || filters.accountId === 'unassigned') {
    params.append('unassigned_only', 'true');
  } else if (filters.accountId !== undefined && filters.accountId !== null) {
    params.append('account_id', filters.accountId.toString());
  }

  // Multi-category or single category
  if (filters.categoryIds && filters.categoryIds.length > 0) {
    params.append('category_ids', filters.categoryIds.join(','));
  } else if (filters.uncategorizedOnly || filters.categoryId === 'uncategorized' || filters.categoryId === 0 || filters.categoryId === '0') {
    params.append('uncategorized_only', 'true');
  } else if (filters.categoryId !== undefined && filters.categoryId !== null) {
    params.append('category_id', filters.categoryId.toString());
  }

  // Multi-type or single type
  if (filters.transactionTypes && filters.transactionTypes.length > 0) {
    params.append('transaction_types', filters.transactionTypes.join(','));
  } else if (filters.transactionType) {
    params.append('transaction_type', filters.transactionType);
  }

  if (filters.expenseNature) {
    params.append('expense_nature', filters.expenseNature);
  }
  if (filters.q && filters.q.trim()) {
    params.append('q', filters.q.trim());
  }
  if (filters.datePreset) {
    params.append('date_preset', filters.datePreset);
  }
  if (filters.dateOffset !== undefined && filters.dateOffset !== null && filters.dateOffset !== 0) {
    params.append('date_offset', String(filters.dateOffset));
  }
  if (filters.startDate) {
    params.append('start_date', filters.startDate);
  }
  if (filters.endDate) {
    params.append('end_date', filters.endDate);
  }
  if (filters.status && filters.status !== 'all') {
    params.append('status', filters.status);
  }
  const sortByVal = filters.sort_by || filters.sortBy;
  if (sortByVal) {
    params.append('sort_by', sortByVal);
  }
  const sortOrderVal = filters.sort_order || filters.sortOrder;
  if (sortOrderVal) {
    params.append('sort_order', sortOrderVal);
  }
  if (filters.limit !== undefined) {
    params.append('limit', filters.limit.toString());
  }
  if (filters.offset !== undefined) {
    params.append('offset', filters.offset.toString());
  }
  return params;
}

export const api = {
  // Accounts
  getAccounts: (includeInactive = false) =>
    request<Account[]>(`/accounts?include_inactive=${includeInactive}`),

  createAccount: (payload: AccountCreatePayload) =>
    request<Account>('/accounts', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  updateAccount: (id: number, payload: AccountUpdatePayload) =>
    request<Account>(`/accounts/${id}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  getAccountBreakdown: (id: number) =>
    request<AccountBreakdownResponse>(`/accounts/${id}/breakdown`),

  getAccountDeletionImpact: (id: number) =>
    request<AccountDeletionImpact>(`/accounts/${id}/deletion-impact`),

  deleteAccount: (id: number, permanent = false) =>
    request<void>(`/accounts/${id}?permanent=${permanent}`, {
      method: 'DELETE',
    }),

  // Summary
  getDashboardSummary: () =>
    request<DashboardSummary>('/dashboard/summary'),

  // Categories
  getCategories: (includeInactive = false, categoryType?: CategoryType) => {
    const params = new URLSearchParams({ include_inactive: String(includeInactive) });
    if (categoryType) {
      params.append('category_type', categoryType);
    }
    return request<Category[]>(`/categories?${params.toString()}`);
  },

  getCategory: (id: number) =>
    request<Category>(`/categories/${id}`),

  getCategoryDeletionImpact: (id: number) =>
    request<CategoryDeletionImpact>(`/categories/${id}/deletion-impact`),

  createCategory: (payload: CategoryCreatePayload) =>
    request<Category>('/categories', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  updateCategory: (id: number, payload: CategoryUpdatePayload) =>
    request<Category>(`/categories/${id}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  deleteCategory: (id: number, permanent = false, reassignToId?: number) => {
    const params = new URLSearchParams({ permanent: String(permanent) });
    if (reassignToId !== undefined && reassignToId !== null) {
      params.append('reassign_to_id', String(reassignToId));
    }
    return request<void>(`/categories/${id}?${params.toString()}`, {
      method: 'DELETE',
    });
  },

  // Transactions
  getTransactions: (filters: TransactionFilters = {}) => {
    const params = buildTransactionFilterParams(filters);
    const qs = params.toString();
    return request<TransactionListResponse>(`/transactions${qs ? `?${qs}` : ''}`);
  },

  downloadTransactionsExport: async (filters: TransactionFilters = {}, format: 'csv' | 'xlsx' = 'csv'): Promise<Blob> => {
    const params = buildTransactionFilterParams(filters);
    params.set('format', format);
    const activeId = getActiveProfileId();
    const headers: Record<string, string> = {};
    if (activeId) {
      headers['X-Profile-ID'] = activeId;
    }
    const qs = params.toString();
    const response = await fetch(`${API_BASE}/transactions/export${qs ? `?${qs}` : ''}`, {
      headers
    });
    if (!response.ok) {
      throw new Error(`Export failed (${response.status}): ${response.statusText}`);
    }
    return await response.blob();
  },

  getTransaction: (id: number) =>
    request<Transaction>(`/transactions/${id}`),

  createTransaction: (payload: TransactionCreatePayload) =>
    request<Transaction>('/transactions', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  createRepeatTransactions: (payload: RepeatTransactionCreatePayload) => {
    const headers: Record<string, string> = {};
    if (payload.idempotency_key) {
      headers['Idempotency-Key'] = payload.idempotency_key;
    }
    return request<RepeatTransactionCreateResponse>('/transactions/repeat', {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    });
  },

  updateTransaction: (id: number, payload: TransactionUpdatePayload) =>
    request<Transaction>(`/transactions/${id}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  deleteTransaction: (id: number) =>
    request<void>(`/transactions/${id}`, {
      method: 'DELETE',
    }),

  getMatchingTransactionIds: (filters: TransactionFilters = {}) => {
    const params = buildTransactionFilterParams(filters);
    const qs = params.toString();
    return request<MatchingTransactionIdsResponse>(`/transactions/matching-ids${qs ? `?${qs}` : ''}`);
  },

  bulkUpdateTransactions: (payload: BulkTransactionUpdatePayload) =>
    request<BulkTransactionUpdateResult>('/transactions/bulk', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  bulkDeleteTransactions: (payload: BulkTransactionDeletePayload) =>
    request<BulkTransactionDeleteResult>('/transactions/bulk-delete', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  restoreTransactions: (payload: RestoreTransactionsPayload) =>
    request<RestoreTransactionsResult>('/transactions/restore', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  undoDeleteTransactions: (batchId?: string) =>
    request<RestoreTransactionsResult>('/transactions/undo-delete', {
      method: 'POST',
      body: JSON.stringify(batchId ? { batch_id: batchId } : {}),
    }),

  getDeletedTransactions: (params?: { limit?: number; offset?: number; q?: string }) => {
    const searchParams = new URLSearchParams();
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.offset) searchParams.set('offset', String(params.offset));
    if (params?.q) searchParams.set('q', params.q);
    const qs = searchParams.toString();
    return request<TransactionListResponse>(`/transactions/deleted${qs ? `?${qs}` : ''}`);
  },

  getDeletedSummary: () =>
    request<RecentlyDeletedSummary>('/transactions/deleted/summary'),

  // System & Backups
  getBackupStatus: () =>
    request<SystemSettings>('/system/backup-status'),

  getSystemSettings: () =>
    request<SystemSettings>('/system/settings'),

  getSystemConfig: () =>
    request<SystemConfig>('/system/config'),

  updateSystemSettings: (payload: SystemSettingsUpdatePayload) =>
    request<SystemSettings>('/system/settings', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  createBackup: () =>
    request<BackupCreationResponse>('/system/backup', {
      method: 'POST',
    }),

  getBackupArchives: () =>
    request<BackupArchiveInfo[]>('/system/backups'),

  getBackupDownloadUrl: (filename: string) =>
    `${API_BASE}/system/backups/${encodeURIComponent(filename)}/download`,

  // Staging Review Queue & Statement Intake
  getStagingItems: (status: string = 'pending', sourceType?: string) => {
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    if (sourceType) params.append('source_type', sourceType);
    const qs = params.toString();
    return request<StagingItem[]>(`/staging${qs ? `?${qs}` : ''}`);
  },

  getStagingCount: () =>
    request<StagingCountResponse>('/staging/count'),

  getStagingItem: (id: number) =>
    request<StagingItem>(`/staging/${id}`),

  updateStagingItem: (id: number, payload: StagingItemUpdatePayload) =>
    request<StagingItem>(`/staging/${id}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  approveStagingItem: (id: number) =>
    request<{ success: boolean; transaction_id: number }>(`/staging/${id}/approve`, {
      method: 'POST',
    }),

  splitStagingItem: (id: number, payload: StagingSplitRequest) =>
    request<StagingSplitResponse>(`/staging/items/${id}/split`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  discardStagingItem: (id: number) =>
    request<void>(`/staging/${id}`, {
      method: 'DELETE',
    }),

  batchApproveStagingItems: (payload: StagingBatchApprovePayload) =>
    request<StagingBatchApproveResponse>('/staging/batch-approve', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  batchRejectStagingItems: (itemIds: number[]) =>
    request<{ rejected_count: number }>('/staging/batch-reject', {
      method: 'POST',
      body: JSON.stringify({ item_ids: itemIds }),
    }),

  importStatementCsv: (formData: FormData) =>
    request<CSVImportResponse>('/staging/import-csv', {
      method: 'POST',
      body: formData,
    }),

  importUnifiedFile: (formData: FormData) =>
    request<UnifiedImportResponse>('/staging/import-file', {
      method: 'POST',
      body: formData,
    }),

  commitUnifiedImport: (payload: UnifiedImportCommitPayload) =>
    request<UnifiedImportCommitResponse>('/staging/import-commit', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  uploadReceipt: (formData: FormData) =>
    request<StagingItem>('/staging/upload-receipt', {
      method: 'POST',
      body: formData,
    }),

  getMappingProfiles: () =>
    request<StatementMappingProfile[]>('/staging/profiles'),

  createMappingProfile: (payload: StatementMappingProfileCreatePayload) =>
    request<StatementMappingProfile>('/staging/profiles', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  deleteMappingProfile: (profileId: string) =>
    request<void>(`/staging/profiles/${encodeURIComponent(profileId)}`, {
      method: 'DELETE',
    }),

  getAccountAssociations: () =>
    request<any[]>('/staging/account-associations'),

  saveAccountAssociation: (cardLabel: string, accountId: number, last4?: string) => {
    const params = new URLSearchParams({
      card_label: cardLabel,
      account_id: accountId.toString(),
    });
    if (last4) params.append('last_4', last4);
    return request<void>(`/staging/account-associations?${params.toString()}`, {
      method: 'POST',
    });
  },

  deleteAccountAssociation: (label: string) =>
    request<void>(`/staging/account-associations/${encodeURIComponent(label)}`, {
      method: 'DELETE',
    }),

  // Review Queue Advisory Refinement Suggestions
  getReviewSuggestions: () =>
    request<ReviewSuggestionsResponse>('/staging/suggestions'),

  confirmDuplicateSuggestion: (duplicateStagingId: number, suggestionId?: string) =>
    request<{ success: boolean; discarded_id: number }>('/staging/suggestions/confirm-duplicate', {
      method: 'POST',
      body: JSON.stringify({ duplicate_staging_id: duplicateStagingId, suggestion_id: suggestionId }),
    }),

  confirmTransferSuggestion: (
    sourceId: number,
    sourceKind: string,
    destinationId: number,
    destinationKind: string,
    suggestionId?: string
  ) =>
    request<{ success: boolean; transaction_id: number }>('/staging/suggestions/confirm-transfer', {
      method: 'POST',
      body: JSON.stringify({
        source_id: sourceId,
        source_kind: sourceKind,
        destination_id: destinationId,
        destination_kind: destinationKind,
        suggestion_id: suggestionId,
      }),
    }),

  dismissReviewSuggestion: (suggestionId: string) =>
    request<{ success: boolean; dismissed_id: string }>('/staging/suggestions/dismiss', {
      method: 'POST',
      body: JSON.stringify({ suggestion_id: suggestionId }),
    }),

  // --- Data Quality & Review ---
  getDataQualityFindings: (filters: DataQualityFindingsQuery = {}) => {
    const params = new URLSearchParams();
    if (filters.finding_type) params.append('finding_type', filters.finding_type);
    if (filters.severity) params.append('severity', filters.severity);
    if (filters.q && filters.q.trim()) params.append('q', filters.q.trim());
    if (filters.account_id !== undefined && filters.account_id !== null && filters.account_id !== '') {
      params.append('account_id', String(filters.account_id));
    }
    if (filters.category_id !== undefined && filters.category_id !== null && filters.category_id !== '') {
      params.append('category_id', String(filters.category_id));
    }
    if (filters.start_date) params.append('start_date', filters.start_date);
    if (filters.end_date) params.append('end_date', filters.end_date);
    if (filters.include_dismissed) params.append('include_dismissed', 'true');
    const qs = params.toString();
    return request<DataQualityReportResponse>(`/review/findings${qs ? `?${qs}` : ''}`);
  },

  dismissDataQualityFinding: (findingId: string) =>
    request<{ success: boolean; dismissed_id: string }>('/review/dismiss', {
      method: 'POST',
      body: JSON.stringify({ finding_id: findingId }),
    }),

  restoreDismissedReviewFindings: (payload: { finding_id?: string; restore_all?: boolean }) =>
    request<{ success: boolean; restored_count: number; restored_id?: string }>('/review/restore-dismissed', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // Investments & Portfolios
  getPortfolioSummary: () =>
    request<PortfolioSummary>('/investments/summary'),

  getAccountHoldings: (accountId: number) =>
    request<AccountHoldingsResponse>(`/investments/accounts/${accountId}/holdings`),

  createHolding: (accountId: number, payload: HoldingCreatePayload) =>
    request<Holding>(`/investments/accounts/${accountId}/holdings`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  getHolding: (holdingId: number) =>
    request<Holding>(`/investments/holdings/${holdingId}`),

  updateHolding: (holdingId: number, payload: HoldingUpdatePayload) =>
    request<Holding>(`/investments/holdings/${holdingId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  deleteHolding: (holdingId: number) =>
    request<void>(`/investments/holdings/${holdingId}`, {
      method: 'DELETE',
    }),

  getHoldingValuations: (holdingId: number) =>
    request<HoldingValuation[]>(`/investments/holdings/${holdingId}/valuations`),

  recordHoldingValuation: (holdingId: number, payload: HoldingValuationCreatePayload) =>
    request<HoldingValuation>(`/investments/holdings/${holdingId}/valuations`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  updateHoldingValuation: (valuationId: number, payload: Partial<HoldingValuationCreatePayload>) =>
    request<HoldingValuation>(`/investments/valuations/${valuationId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  deleteHoldingValuation: (valuationId: number) =>
    request<void>(`/investments/valuations/${valuationId}`, {
      method: 'DELETE',
    }),

  updateValuationMode: (accountId: number, valuationMode: 'snapshot' | 'holdings') =>
    request<Account>(`/investments/accounts/${accountId}/valuation-mode`, {
      method: 'PUT',
      body: JSON.stringify({ valuation_mode: valuationMode }),
    }),

  syncCheckpoint: (accountId: number, payload?: { effective_date?: string; notes?: string }) =>
    request<CheckpointSyncResponse>(`/investments/accounts/${accountId}/checkpoints`, {
      method: 'POST',
      body: payload ? JSON.stringify(payload) : undefined,
    }),

  // Analytics & Cash Flow
  getAnalysis: (params?: AnalysisQueryParams) => {
    const qs = new URLSearchParams();
    if (params?.preset) qs.append('preset', params.preset);
    if (params?.start_date) qs.append('start_date', params.start_date);
    if (params?.end_date) qs.append('end_date', params.end_date);
    if (params?.interval) qs.append('interval', params.interval);
    if (params?.currency) qs.append('currency', params.currency);
    if (params?.account_ids && params.account_ids.length > 0) {
      qs.append('account_ids', params.account_ids.join(','));
    } else if (params?.account_id !== undefined && params?.account_id !== null) {
      qs.append('account_id', String(params.account_id));
    }
    if (params?.category_ids && params.category_ids.length > 0) {
      qs.append('category_ids', params.category_ids.join(','));
    } else if (params?.category_id !== undefined && params?.category_id !== null) {
      qs.append('category_id', String(params.category_id));
    }
    if (params?.offset !== undefined && params?.offset !== null) qs.append('offset', String(params.offset));
    const query = qs.toString();
    return request<ComprehensiveAnalysisResponse>(`/analytics/analysis${query ? `?${query}` : ''}`);
  },

  getAnalysisExportUrl: (
    reportType: AnalysisExportReportType,
    format: AnalysisExportFormat,
    params?: AnalysisQueryParams
  ) => {
    const qs = new URLSearchParams();
    qs.append('report_type', reportType);
    qs.append('format', format);
    if (params?.preset) qs.append('preset', params.preset);
    if (params?.start_date) qs.append('start_date', params.start_date);
    if (params?.end_date) qs.append('end_date', params.end_date);
    if (params?.interval) qs.append('interval', params.interval);
    if (params?.currency) qs.append('currency', params.currency);
    if (params?.account_ids && params.account_ids.length > 0) {
      qs.append('account_ids', params.account_ids.join(','));
    } else if (params?.account_id !== undefined && params?.account_id !== null) {
      qs.append('account_id', String(params.account_id));
    }
    if (params?.category_ids && params.category_ids.length > 0) {
      qs.append('category_ids', params.category_ids.join(','));
    } else if (params?.category_id !== undefined && params?.category_id !== null) {
      qs.append('category_id', String(params.category_id));
    }
    if (params?.offset !== undefined && params?.offset !== null) qs.append('offset', String(params.offset));
    return `${API_BASE}/analytics/export?${qs.toString()}`;
  },

  downloadAnalysisExport: async (
    reportType: AnalysisExportReportType,
    format: AnalysisExportFormat,
    params?: AnalysisQueryParams
  ) => {
    const qs = new URLSearchParams();
    qs.append('report_type', reportType);
    qs.append('format', format);
    if (params?.preset) qs.append('preset', params.preset);
    if (params?.start_date) qs.append('start_date', params.start_date);
    if (params?.end_date) qs.append('end_date', params.end_date);
    if (params?.interval) qs.append('interval', params.interval);
    if (params?.currency) qs.append('currency', params.currency);
    if (params?.account_ids && params.account_ids.length > 0) {
      qs.append('account_ids', params.account_ids.join(','));
    } else if (params?.account_id !== undefined && params?.account_id !== null) {
      qs.append('account_id', String(params.account_id));
    }
    if (params?.category_ids && params.category_ids.length > 0) {
      qs.append('category_ids', params.category_ids.join(','));
    } else if (params?.category_id !== undefined && params?.category_id !== null) {
      qs.append('category_id', String(params.category_id));
    }
    if (params?.offset !== undefined && params?.offset !== null) qs.append('offset', String(params.offset));

    const url = `${API_BASE}/analytics/export?${qs.toString()}`;
    const headers: Record<string, string> = {};
    const activeProfileId = getActiveProfileId();
    if (activeProfileId) {
      headers['X-Profile-ID'] = activeProfileId;
    }

    const res = await fetch(url, { headers });
    if (!res.ok) {
      throw new Error(`Export failed (${res.status})`);
    }
    const blob = await res.blob();
    const contentDisposition = res.headers.get('Content-Disposition') || '';
    const match = contentDisposition.match(/filename="([^"]+)"/);
    const filename = match ? match[1] : `finance_hub_${reportType}.${format}`;

    const blobUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = blobUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(() => URL.revokeObjectURL(blobUrl), 2000);
  },

  getCashFlowSummary: (month?: string, currency?: string, accountId?: number | null) => {
    const params = new URLSearchParams();
    if (month) params.append('month', month);
    if (currency) params.append('currency', currency);
    if (accountId !== undefined && accountId !== null) params.append('account_id', String(accountId));
    const qs = params.toString();
    return request<CashFlowSummaryResponse>(`/analytics/cashflow${qs ? `?${qs}` : ''}`);
  },

  // Account Reconciliation & Balance Verification
  getReconciliationSummary: (accountId: number) =>
    request<ReconciliationSummaryResponse>(`/accounts/${accountId}/reconciliation`),

  getReconciliationSnapshots: (accountId: number, limit: number = 50, offset: number = 0) =>
    request<AccountSnapshotItem[]>(`/accounts/${accountId}/reconciliation/snapshots?limit=${limit}&offset=${offset}`),

  recordReconciliationSnapshot: (accountId: number, payload: ReconciliationSnapshotCreatePayload) =>
    request<ReconciliationResultResponse>(`/accounts/${accountId}/reconciliation/snapshots`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  deleteReconciliationSnapshot: (accountId: number, snapshotId: number) =>
    request<void>(`/accounts/${accountId}/reconciliation/snapshots/${snapshotId}`, {
      method: 'DELETE',
    }),

  // Financial Workspace Profiles
  listProfiles: (includeArchived: boolean = true) =>
    request<ProfileMetadata[]>(`/profiles?include_archived=${includeArchived}`),

  getActiveProfile: () =>
    request<ProfileMetadata>('/profiles/active'),

  createProfile: (payload: ProfileCreatePayload) =>
    request<ProfileMetadata>('/profiles', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  selectProfile: (profileId: string) =>
    request<ProfileMetadata>(`/profiles/${profileId}/select`, {
      method: 'POST',
    }),

  updateProfile: (profileId: string, payload: ProfileUpdatePayload) =>
    request<ProfileMetadata>(`/profiles/${profileId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  getProfileImpact: (profileId: string) =>
    request<ProfileImpactResponse>(`/profiles/${profileId}/impact`),

  deleteProfile: (profileId: string, payload: ProfileDeletePayload) =>
    request<void>(`/profiles/${profileId}`, {
      method: 'DELETE',
      body: JSON.stringify(payload),
    }),
};

