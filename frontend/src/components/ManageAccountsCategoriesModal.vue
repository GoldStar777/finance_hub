<template>
  <div 
    v-if="isOpen" 
    class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4 backdrop-blur-sm overflow-y-auto animate-fadeIn" 
    @click.self="$emit('close')">
    <section 
      role="dialog" 
      aria-modal="true" 
      aria-labelledby="manage-title" 
      class="w-full max-w-3xl space-y-5 rounded-2xl border border-brand-border bg-white p-6 shadow-2xl dark:border-brand-darkborder dark:bg-brand-darksurface my-8 transition-all">
      
      <!-- Modal Header -->
      <div class="flex items-center justify-between border-b border-brand-border pb-3 dark:border-brand-darkborder">
        <div>
          <h2 id="manage-title" class="font-bold text-slate-900 dark:text-white text-base">
            Manage Accounts & Categories
          </h2>
          <p class="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
            View, add, edit, archive, and safely manage accounts and expense categories.
          </p>
        </div>
        <button 
          @click="$emit('close')" 
          class="text-xl text-slate-400 hover:text-slate-700 dark:hover:text-white transition" 
          aria-label="Close dialog">
          &times;
        </button>
      </div>

      <!-- Main Tabs -->
      <div class="flex rounded-xl bg-slate-100 p-1 border border-brand-border dark:border-brand-darkborder dark:bg-slate-800/80">
        <button
          type="button"
          @click="activeTab = 'accounts'"
          class="flex-1 py-1.5 text-xs font-semibold rounded-lg transition flex items-center justify-center space-x-1.5"
          :class="activeTab === 'accounts'
            ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm'
            : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'">
          <span>Accounts</span>
          <span class="px-1.5 py-0.2 text-[10px] font-mono rounded-full font-bold bg-slate-200 dark:bg-slate-600">
            {{ accountsStore.accounts.length }}
          </span>
        </button>
        <button
          type="button"
          @click="activeTab = 'categories'"
          class="flex-1 py-1.5 text-xs font-semibold rounded-lg transition flex items-center justify-center space-x-1.5"
          :class="activeTab === 'categories'
            ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm'
            : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'">
          <span>Categories</span>
          <span class="px-1.5 py-0.2 text-[10px] font-mono rounded-full font-bold bg-slate-200 dark:bg-slate-600">
            {{ categoriesList.length }}
          </span>
        </button>
      </div>

      <!-- Feedback Alerts -->
      <div 
        v-if="successMessage"
        class="p-3 rounded-xl border border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-950/40 text-emerald-800 dark:text-emerald-300 text-xs flex items-center justify-between">
        <span>{{ successMessage }}</span>
        <button @click="successMessage = null" class="text-emerald-600 text-base leading-none">&times;</button>
      </div>

      <div 
        v-if="errorMessage"
        class="p-3 rounded-xl border border-rose-200 dark:border-rose-900 bg-rose-50 dark:bg-rose-950/40 text-rose-600 dark:text-rose-400 text-xs flex items-center justify-between">
        <span>{{ errorMessage }}</span>
        <button @click="errorMessage = null" class="text-rose-600 text-base leading-none">&times;</button>
      </div>

      <!-- TAB 1: ACCOUNTS -->
      <div v-if="activeTab === 'accounts'" class="space-y-4 max-h-[62vh] overflow-y-auto pr-1">
        <!-- Controls Bar -->
        <div class="flex flex-wrap items-center justify-between gap-2.5">
          <div class="flex items-center space-x-2 flex-1 min-w-[200px]">
            <input 
              v-model="accountSearch" 
              type="text" 
              placeholder="Search accounts..." 
              class="w-full text-xs rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50 dark:bg-slate-800/80 px-3 py-1.5 text-slate-900 dark:text-white focus:outline-none" />
          </div>

          <div class="flex items-center space-x-2 shrink-0">
            <button
              type="button"
              @click="toggleShowArchivedAccounts"
              class="text-xs font-semibold px-2.5 py-1 rounded-full border transition text-[11px]"
              :class="accountsStore.showArchived 
                ? 'border-indigo-300 dark:border-indigo-700 bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300' 
                : 'border-brand-border dark:border-brand-darkborder text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'">
              {{ accountsStore.showArchived ? 'Hide Archived' : 'Show Archived' }}
            </button>
            <button
              type="button"
              @click="isAddAccountOpen = true"
              class="px-3.5 py-1 rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 text-xs font-semibold hover:opacity-90 transition shadow-sm flex items-center space-x-1">
              <span>+ New Account</span>
            </button>
          </div>
        </div>

        <!-- Accounts List -->
        <div v-if="accountsStore.loading && accountsStore.accounts.length === 0" class="p-6 text-center text-xs text-slate-400 animate-pulse">
          Loading accounts...
        </div>

        <div v-else-if="filteredAccounts.length === 0" class="p-6 rounded-xl border border-brand-border dark:border-brand-darkborder text-center text-xs text-slate-400">
          {{ accountSearch ? 'No accounts match your search filter.' : 'No accounts configured. Add one to start tracking balances.' }}
        </div>

        <div v-else class="space-y-2">
          <div
            v-for="acc in filteredAccounts"
            :key="acc.id"
            class="p-3.5 rounded-xl border border-brand-border dark:border-brand-darkborder bg-white dark:bg-brand-darksurface hover:border-slate-300 dark:hover:border-slate-700 transition flex items-center justify-between gap-3">
            
            <!-- Left Info -->
            <div class="flex items-center space-x-3 min-w-0 flex-1">
              <span class="w-3.5 h-3.5 rounded-full shrink-0 shadow-sm" :style="{ backgroundColor: acc.color || '#3B82F6' }"></span>
              <div class="min-w-0">
                <div class="flex items-center space-x-2">
                  <span class="text-xs font-bold text-slate-900 dark:text-white truncate">
                    {{ acc.name }}
                  </span>
                  <span 
                    v-if="!acc.is_active" 
                    class="text-[9px] font-mono px-1.5 py-0.5 rounded bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300 font-semibold uppercase">
                    Archived
                  </span>
                  <span class="text-[10px] font-mono px-1.5 py-0.2 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 font-semibold uppercase">
                    {{ formatAccountType(acc.account_type) }}
                  </span>
                  <span class="text-[10px] font-mono text-slate-400">
                    {{ acc.currency }}
                  </span>
                </div>

                <div class="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] text-slate-400 font-mono mt-1">
                  <!-- Balance -->
                  <span class="font-bold sensitive" :class="acc.current_balance_pence < 0 ? 'text-rose-500' : 'text-slate-700 dark:text-slate-300'">
                    {{ acc.formatted_balance }}
                  </span>
                  <span>&bull;</span>
                  <!-- Specific status tags -->
                  <span v-if="acc.account_type === 'investment'">
                    {{ acc.holdings_count === 0 ? 'No Holdings' : (acc.has_unvalued_holdings ? 'Unvalued Holdings' : `${acc.holdings_count} Holdings`) }}
                  </span>
                  <span v-else>
                    {{ acc.last_reconciled_at ? `Reconciled ${formatShortDate(acc.last_reconciled_at)}` : (acc.anchor_label || 'Ledger balance') }}
                  </span>
                </div>
              </div>
            </div>

            <!-- Action Buttons -->
            <div class="flex items-center space-x-1.5 shrink-0">
              <button
                type="button"
                @click="openEditAccount(acc)"
                class="px-2.5 py-1 text-xs font-semibold rounded-full border border-brand-border dark:border-brand-darkborder hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300 transition"
                title="Edit account details, currency, and name">
                Edit
              </button>
              
              <button
                v-if="acc.is_active"
                type="button"
                @click="handleArchiveAccount(acc)"
                class="px-2.5 py-1 text-xs font-semibold rounded-full border border-brand-border dark:border-brand-darkborder hover:bg-amber-50 hover:text-amber-700 hover:border-amber-200 dark:hover:bg-amber-950/40 dark:hover:text-amber-400 text-slate-500 transition"
                title="Archive account (preserves transaction history, hides from selectors)">
                Archive
              </button>

              <button
                v-else
                type="button"
                @click="handleReactivateAccount(acc)"
                class="px-2.5 py-1 text-xs font-semibold rounded-full bg-emerald-600 text-white hover:bg-emerald-500 transition"
                title="Reactivate archived account">
                Reactivate
              </button>

              <button
                type="button"
                @click="openDeleteAccount(acc)"
                class="px-2.5 py-1 text-xs font-semibold rounded-full border border-rose-200 dark:border-rose-900/60 hover:bg-rose-50 hover:text-rose-700 dark:hover:bg-rose-950/40 dark:hover:text-rose-400 text-slate-400 transition"
                title="Permanently delete account with 2-step safeguards and cascade analysis">
                Delete
              </button>
            </div>

          </div>
        </div>
      </div>

      <!-- TAB 2: CATEGORIES -->
      <div v-else-if="activeTab === 'categories'" class="space-y-4 max-h-[62vh] overflow-y-auto pr-1">
        <!-- Controls Bar -->
        <div class="flex flex-wrap items-center justify-between gap-2.5">
          <div class="flex items-center space-x-2 flex-1 min-w-[200px]">
            <input 
              v-model="categorySearch" 
              type="text" 
              placeholder="Search categories..." 
              class="w-full text-xs rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50 dark:bg-slate-800/80 px-3 py-1.5 text-slate-900 dark:text-white focus:outline-none" />
          </div>

          <div class="flex items-center space-x-2 shrink-0">
            <button
              type="button"
              @click="toggleShowArchivedCategories"
              class="text-xs font-semibold px-2.5 py-1 rounded-full border transition text-[11px]"
              :class="showArchivedCategories 
                ? 'border-indigo-300 dark:border-indigo-700 bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300' 
                : 'border-brand-border dark:border-brand-darkborder text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'">
              {{ showArchivedCategories ? 'Hide Archived' : 'Show Archived' }}
            </button>
            <button
              type="button"
              @click="openCreateCategory"
              class="px-3.5 py-1 rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 text-xs font-semibold hover:opacity-90 transition shadow-sm flex items-center space-x-1">
              <span>+ New Category</span>
            </button>
          </div>
        </div>

        <!-- Category Purpose View Filter -->
        <div class="flex items-center justify-between flex-wrap gap-2">
          <div class="inline-flex rounded-full bg-slate-100 dark:bg-slate-800 p-0.5 text-[11px] font-semibold">
            <button
              type="button"
              @click="categoryPurposeFilter = 'all'"
              :class="categoryPurposeFilter === 'all' ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm' : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'"
              class="px-3 py-1 rounded-full transition">
              All ({{ categoriesList.length }})
            </button>
            <button
              type="button"
              @click="categoryPurposeFilter = 'expense'"
              :class="categoryPurposeFilter === 'expense' ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm' : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'"
              class="px-3 py-1 rounded-full transition">
              Expense ({{ expenseCategoryCount }})
            </button>
            <button
              type="button"
              @click="categoryPurposeFilter = 'income'"
              :class="categoryPurposeFilter === 'income' ? 'bg-emerald-600 text-white shadow-sm' : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'"
              class="px-3 py-1 rounded-full transition">
              Income ({{ incomeCategoryCount }})
            </button>
          </div>
          <span class="text-[11px] text-slate-400">
            Income and Expense categories are kept separate across entry, import, and review.
          </span>
        </div>

        <!-- Inline Create / Edit Category Form -->
        <div v-if="isEditingCategory" class="p-4 rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50 dark:bg-slate-800/50 space-y-3">
          <div class="flex items-center justify-between pb-2 border-b border-brand-border dark:border-brand-darkborder">
            <span class="text-xs font-bold text-slate-900 dark:text-white">
              {{ categoryForm.id ? `Edit Category: ${categoryForm.name}` : 'Create New Category' }}
            </span>
            <button @click="cancelCategoryEdit" class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 text-sm">&times;</button>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
                Name
              </label>
              <input
                v-model="categoryForm.name"
                type="text"
                :placeholder="categoryForm.category_type === 'income' ? 'e.g. Salary, Dividends, Refunds' : 'e.g. Groceries, Transport'"
                class="w-full rounded-xl border border-brand-border bg-white dark:bg-slate-800 px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none" />
            </div>

            <div>
              <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
                Category Purpose
              </label>
              <div class="grid grid-cols-2 gap-1.5 rounded-xl bg-white dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder p-1">
                <button
                  type="button"
                  @click="categoryForm.category_type = 'expense'"
                  :class="categoryForm.category_type === 'expense' ? 'bg-rose-600 text-white shadow-sm' : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700'"
                  class="py-1.5 px-2 rounded-lg text-xs font-semibold transition">
                  Expense
                </button>
                <button
                  type="button"
                  @click="categoryForm.category_type = 'income'"
                  :class="categoryForm.category_type === 'income' ? 'bg-emerald-600 text-white shadow-sm' : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700'"
                  class="py-1.5 px-2 rounded-lg text-xs font-semibold transition">
                  Income
                </button>
              </div>
            </div>
          </div>

          <!-- Purpose change reassignment workflow if transactions already reference this category -->
          <div
            v-if="isChangingPurposeWithTransactions"
            class="p-3 rounded-xl border border-amber-300 dark:border-amber-800 bg-amber-50/70 dark:bg-amber-950/30 space-y-2 text-xs">
            <div class="font-semibold text-amber-900 dark:text-amber-200">
              {{ editingCategoryOriginalTxCount }} existing {{ editingCategoryOriginalType }} transaction(s) reference this category.
            </div>
            <p v-if="reassignmentTargetsForPurposeChange.length > 0" class="text-[11px] text-amber-800 dark:text-amber-300">
              To safely change purpose to {{ categoryForm.category_type }}, select an active {{ editingCategoryOriginalType }} category to receive those existing transactions:
            </p>
            <select
              v-if="reassignmentTargetsForPurposeChange.length > 0"
              v-model="categoryForm.reassign_existing_to_id"
              class="w-full rounded-xl border border-amber-300 dark:border-amber-800 bg-white dark:bg-slate-900 px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none">
              <option :value="null">-- Select Active {{ editingCategoryOriginalType === 'income' ? 'Income' : 'Expense' }} Category --</option>
              <option v-for="tcat in reassignmentTargetsForPurposeChange" :key="tcat.id" :value="tcat.id">
                {{ tcat.name }}
              </option>
            </select>
            <p v-else class="text-[11px] text-rose-700 dark:text-rose-300 font-medium">
              No other active {{ editingCategoryOriginalType }} category is available to reassign these transactions. Create another {{ editingCategoryOriginalType }} category first, or archive this one and create a new category.
            </p>
          </div>

          <div v-if="categoryForm.category_type === 'expense'">
            <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
              Default Expense Nature
            </label>
            <select
              v-model="categoryForm.default_expense_nature"
              class="w-full rounded-xl border border-brand-border bg-white dark:bg-slate-800 px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none">
              <option value="fixed">Fixed (Committed)</option>
              <option value="variable">Variable (Discretionary)</option>
              <option value="unclassified">Unclassified</option>
            </select>
          </div>
          <p v-else class="text-[11px] text-emerald-700 dark:text-emerald-300 bg-emerald-50/70 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-900/50 rounded-xl px-3 py-2">
            Income categories classify money received and do not use Fixed/Variable expense nature.
          </p>

          <!-- Description & Keywords -->
          <div>
            <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
              Description & Examples (Optional)
            </label>
            <input
              v-model="categoryForm.description"
              type="text"
              placeholder="e.g. haircuts, salons, barbering, hair grooming, parlour"
              class="w-full rounded-xl border border-brand-border bg-white dark:bg-slate-800 px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none" />
            <p class="text-[10px] text-slate-400 mt-0.5">Used by local OCR to suggest this category from receipt taglines and context.</p>
          </div>

          <!-- Color Chooser -->
          <div>
            <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
              Color Accent
            </label>
            <div class="flex items-center space-x-2">
              <input 
                v-model="categoryForm.color" 
                type="color" 
                class="w-8 h-8 p-0 rounded-lg border border-brand-border dark:border-brand-darkborder bg-transparent cursor-pointer" />
              <div class="flex space-x-1.5">
                <button 
                  v-for="c in categoryColors" 
                  :key="c" 
                  type="button" 
                  @click="categoryForm.color = c"
                  class="w-5 h-5 rounded-full border border-black/10 transition transform hover:scale-110"
                  :style="{ backgroundColor: c }">
                </button>
              </div>
            </div>
          </div>

          <div class="flex justify-end space-x-2 pt-2">
            <button
              type="button"
              @click="cancelCategoryEdit"
              class="px-3.5 py-1.5 text-xs font-semibold rounded-full border border-brand-border dark:border-brand-darkborder text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800">
              Cancel
            </button>
            <button
              type="button"
              @click="handleSaveCategory"
              :disabled="savingCategory || !categoryForm.name.trim() || (isChangingPurposeWithTransactions && !categoryForm.reassign_existing_to_id)"
              class="px-4 py-1.5 text-xs font-semibold rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 hover:opacity-90 disabled:opacity-50">
              {{ savingCategory ? 'Saving...' : 'Save Category' }}
            </button>
          </div>
        </div>

        <!-- Categories List -->
        <div v-if="loadingCategories && categoriesList.length === 0" class="p-6 text-center text-xs text-slate-400 animate-pulse">
          Loading categories...
        </div>

        <div v-else-if="filteredCategories.length === 0" class="p-6 rounded-xl border border-brand-border dark:border-brand-darkborder text-center text-xs text-slate-400">
          {{ categorySearch ? 'No categories match your search filter.' : 'No categories configured yet.' }}
        </div>

        <div v-else class="space-y-2">
          <div
            v-for="cat in filteredCategories"
            :key="cat.id"
            class="flex items-center justify-between p-3 rounded-xl border border-brand-border dark:border-brand-darkborder bg-white dark:bg-brand-darksurface hover:border-slate-300 dark:hover:border-slate-700 transition">
            
            <div class="flex items-center space-x-2.5 min-w-0 pr-2">
              <span class="w-3.5 h-3.5 rounded-full shrink-0 shadow-sm" :style="{ backgroundColor: cat.color || '#8B5CF6' }"></span>
              <div class="min-w-0">
                <div class="flex items-center space-x-2">
                  <span class="text-xs font-bold text-slate-900 dark:text-white truncate">
                    {{ cat.name }}
                  </span>
                  <span 
                    v-if="!cat.is_active" 
                    class="text-[9px] font-mono px-1.5 py-0.5 rounded bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300 font-semibold uppercase">
                    Archived
                  </span>
                </div>
                <div class="flex items-center space-x-2 text-[10px] text-slate-400 font-mono mt-0.5">
                  <span
                    class="px-1.5 py-0.5 rounded uppercase font-semibold text-[9px]"
                    :class="cat.category_type === 'income'
                      ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-900/40'
                      : 'bg-rose-50 dark:bg-rose-950/50 text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-900/40'">
                    {{ cat.category_type === 'income' ? 'Income' : 'Expense' }}
                  </span>
                  <span 
                    v-if="cat.category_type !== 'income'"
                    class="px-1.5 py-0.5 rounded uppercase font-semibold text-[9px]"
                    :class="cat.default_expense_nature === 'fixed' 
                      ? 'bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300' 
                      : cat.default_expense_nature === 'variable' 
                        ? 'bg-amber-50 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300' 
                        : 'bg-slate-100 dark:bg-slate-800 text-slate-500'">
                    {{ cat.default_expense_nature }}
                  </span>
                  <span>&bull;</span>
                  <span>{{ cat.transaction_count || 0 }} transactions</span>
                </div>
                <p v-if="cat.description" class="text-[11px] text-slate-500 dark:text-slate-400 mt-1 italic">
                  {{ cat.description }}
                </p>
              </div>
            </div>

            <!-- Action Buttons -->
            <div class="flex items-center space-x-1.5 shrink-0">
              <button
                type="button"
                @click="openEditCategory(cat)"
                class="px-2.5 py-1 text-xs font-semibold rounded-full border border-brand-border dark:border-brand-darkborder hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300 transition"
                title="Edit category details">
                Edit
              </button>
              
              <button
                v-if="cat.is_active"
                type="button"
                @click="promptArchiveCategory(cat)"
                class="px-2.5 py-1 text-xs font-semibold rounded-full border border-brand-border dark:border-brand-darkborder hover:bg-amber-50 hover:text-amber-700 hover:border-amber-200 dark:hover:bg-amber-950/40 dark:hover:text-amber-400 text-slate-500 transition"
                title="Archive category to hide from new transactions (preserves history)">
                Archive
              </button>

              <button
                v-else
                type="button"
                @click="handleReactivateCategory(cat)"
                class="px-2.5 py-1 text-xs font-semibold rounded-full bg-emerald-600 text-white hover:bg-emerald-500 transition"
                title="Reactivate archived category">
                Reactivate
              </button>

              <button
                type="button"
                @click="openDeleteCategory(cat)"
                class="px-2.5 py-1 text-xs font-semibold rounded-full border border-rose-200 dark:border-rose-900/60 hover:bg-rose-50 hover:text-rose-700 dark:hover:bg-rose-950/40 dark:hover:text-rose-400 text-slate-400 transition"
                title="Permanently delete category with safe reassignment">
                Delete
              </button>
            </div>

          </div>
        </div>
      </div>

      <!-- Modal Footer -->
      <div class="flex justify-end gap-2 border-t border-brand-border pt-3 dark:border-brand-darkborder">
        <button 
          @click="$emit('close')" 
          class="rounded-full border border-brand-border px-4 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 dark:border-brand-darkborder dark:text-slate-300 dark:hover:bg-slate-800 transition">
          Close
        </button>
      </div>

    </section>

    <!-- Sub-modals -->
    <AddAccountModal 
      :is-open="isAddAccountOpen" 
      @close="isAddAccountOpen = false" 
      @created="handleAccountCreated" />

    <EditAccountModal
      :is-open="isEditAccountOpen"
      :account="editingAccount"
      @close="isEditAccountOpen = false"
      @saved="handleAccountSaved"
      @delete="handleAccountDeleteFromEdit" />

    <DeleteAccountModal
      :is-open="isDeleteAccountOpen"
      :account="deletingAccount"
      @close="isDeleteAccountOpen = false"
      @deleted="handleAccountDeleted"
      @archived="handleAccountSaved" />

    <DeleteCategoryModal
      :is-open="isDeleteCategoryOpen"
      :category="deletingCategory"
      :all-categories="categoriesList"
      @close="isDeleteCategoryOpen = false"
      @deleted="handleCategoryDeleted"
      @archived="handleCategoryArchived" />

  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useAccountsStore } from '../stores/accounts';
import { useTransactionsStore } from '../stores/transactions';
import { useInvestmentsStore } from '../stores/investments';
import { api } from '../api/client';
import AddAccountModal from './AddAccountModal.vue';
import EditAccountModal from './EditAccountModal.vue';
import DeleteAccountModal from './DeleteAccountModal.vue';
import DeleteCategoryModal from './DeleteCategoryModal.vue';
import type { Account, Category, CategoryType, ExpenseNature, AccountCreatePayload, AccountType } from '../types';

const props = withDefaults(defineProps<{
  isOpen: boolean;
  initialTab?: 'accounts' | 'categories';
}>(), {
  initialTab: 'accounts'
});

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'account-created', acc: Account): void;
}>();

const accountsStore = useAccountsStore();
const txStore = useTransactionsStore();
const investmentsStore = useInvestmentsStore();

const activeTab = ref<'accounts' | 'categories'>(props.initialTab || 'accounts');
const successMessage = ref<string | null>(null);
const errorMessage = ref<string | null>(null);

// Accounts state
const accountSearch = ref('');
const isAddAccountOpen = ref(false);
const isEditAccountOpen = ref(false);
const editingAccount = ref<Account | null>(null);
const isDeleteAccountOpen = ref(false);
const deletingAccount = ref<Account | null>(null);

// Categories state
const categorySearch = ref('');
const categoryPurposeFilter = ref<'all' | 'expense' | 'income'>('all');
const categoryColors = [
  '#8B5CF6', '#3B82F6', '#10B981', '#EC4899', '#F59E0B', '#EF4444', '#14B8A6', '#64748B'
];
const categoriesList = ref<Category[]>([]);
const loadingCategories = ref(false);
const showArchivedCategories = ref(false);
const isEditingCategory = ref(false);
const savingCategory = ref(false);
const isDeleteCategoryOpen = ref(false);
const deletingCategory = ref<Category | null>(null);
const editingCategoryOriginalType = ref<CategoryType>('expense');
const editingCategoryOriginalTxCount = ref<number>(0);

const categoryForm = ref<{
  id: number | null;
  name: string;
  category_type: CategoryType;
  reassign_existing_to_id: number | null;
  color: string;
  default_expense_nature: ExpenseNature;
  description: string;
}>({
  id: null,
  name: '',
  category_type: 'expense',
  reassign_existing_to_id: null,
  color: '#8B5CF6',
  default_expense_nature: 'variable',
  description: '',
});

// Filtered items
const filteredAccounts = computed(() => {
  if (!accountSearch.value.trim()) return accountsStore.accounts;
  const q = accountSearch.value.toLowerCase().trim();
  return accountsStore.accounts.filter(acc => 
    acc.name.toLowerCase().includes(q) || 
    acc.account_type.toLowerCase().includes(q) ||
    acc.currency.toLowerCase().includes(q)
  );
});

const expenseCategoryCount = computed(() =>
  categoriesList.value.filter(c => (c.category_type || 'expense') === 'expense').length
);

const incomeCategoryCount = computed(() =>
  categoriesList.value.filter(c => c.category_type === 'income').length
);

const isChangingPurposeWithTransactions = computed(() =>
  Boolean(
    categoryForm.value.id &&
    editingCategoryOriginalTxCount.value > 0 &&
    categoryForm.value.category_type !== editingCategoryOriginalType.value
  )
);

const reassignmentTargetsForPurposeChange = computed(() =>
  categoriesList.value.filter(
    c =>
      c.is_active &&
      c.id !== categoryForm.value.id &&
      (c.category_type || 'expense') === editingCategoryOriginalType.value
  )
);

const filteredCategories = computed(() => {
  const q = categorySearch.value.toLowerCase().trim();
  return categoriesList.value.filter(cat => {
    const purpose = cat.category_type || 'expense';
    if (categoryPurposeFilter.value !== 'all' && purpose !== categoryPurposeFilter.value) {
      return false;
    }
    if (!q) return true;
    return (
      cat.name.toLowerCase().includes(q) ||
      purpose.includes(q) ||
      (purpose === 'expense' && cat.default_expense_nature.toLowerCase().includes(q)) ||
      (cat.description && cat.description.toLowerCase().includes(q))
    );
  });
});

// Loaders
async function loadCategories() {
  loadingCategories.value = true;
  try {
    categoriesList.value = await api.getCategories(showArchivedCategories.value);
  } catch (err: any) {
    errorMessage.value = err.message || 'Failed to load categories.';
  } finally {
    loadingCategories.value = false;
  }
}

function toggleShowArchivedAccounts() {
  accountsStore.toggleShowArchived();
}

function toggleShowArchivedCategories() {
  showArchivedCategories.value = !showArchivedCategories.value;
  loadCategories();
}

// Account actions
function openEditAccount(acc: Account) {
  editingAccount.value = acc;
  isEditAccountOpen.value = true;
}

function openDeleteAccount(acc: Account) {
  deletingAccount.value = acc;
  isDeleteAccountOpen.value = true;
}

function handleAccountDeleteFromEdit(acc: Account) {
  isEditAccountOpen.value = false;
  openDeleteAccount(acc);
}

async function handleAccountCreated(payload: AccountCreatePayload) {
  try {
    const newAcc = await accountsStore.createAccount(payload);
    await investmentsStore.loadAllData();
    isAddAccountOpen.value = false;
    successMessage.value = `Account '${newAcc.name}' created successfully.`;
    emit('account-created', newAcc);
  } catch (err: any) {
    errorMessage.value = err.message || 'Failed to create account.';
  }
}

async function handleAccountSaved() {
  isEditAccountOpen.value = false;
  successMessage.value = 'Account updated successfully.';
  await accountsStore.loadData();
  await investmentsStore.loadAllData();
}

async function handleArchiveAccount(acc: Account) {
  if (!confirm(`Are you sure you want to archive account "${acc.name}"? It will be hidden from routine selectors but historical records remain safe.`)) return;
  try {
    await accountsStore.archiveAccount(acc.id);
    successMessage.value = `Account '${acc.name}' archived successfully.`;
  } catch (err: any) {
    errorMessage.value = err.message || 'Failed to archive account.';
  }
}

async function handleReactivateAccount(acc: Account) {
  try {
    await accountsStore.unarchiveAccount(acc.id);
    successMessage.value = `Account '${acc.name}' reactivated successfully.`;
  } catch (err: any) {
    errorMessage.value = err.message || 'Failed to reactivate account.';
  }
}

async function handleAccountDeleted() {
  isDeleteAccountOpen.value = false;
  successMessage.value = 'Account permanently deleted.';
  await accountsStore.loadData();
  await investmentsStore.loadAllData();
}

// Category actions
function openCreateCategory() {
  const defaultType: CategoryType = categoryPurposeFilter.value === 'income' ? 'income' : 'expense';
  editingCategoryOriginalType.value = defaultType;
  editingCategoryOriginalTxCount.value = 0;
  categoryForm.value = {
    id: null,
    name: '',
    category_type: defaultType,
    reassign_existing_to_id: null,
    color: defaultType === 'income' ? '#10B981' : '#8B5CF6',
    default_expense_nature: 'variable',
    description: '',
  };
  isEditingCategory.value = true;
}

function openEditCategory(cat: Category) {
  const purpose: CategoryType = cat.category_type || 'expense';
  editingCategoryOriginalType.value = purpose;
  editingCategoryOriginalTxCount.value = cat.transaction_count || 0;
  categoryForm.value = {
    id: cat.id,
    name: cat.name,
    category_type: purpose,
    reassign_existing_to_id: null,
    color: cat.color || '#8B5CF6',
    default_expense_nature: purpose === 'income' ? 'unclassified' : cat.default_expense_nature,
    description: cat.description || '',
  };
  isEditingCategory.value = true;
}

function cancelCategoryEdit() {
  isEditingCategory.value = false;
  editingCategoryOriginalTxCount.value = 0;
  categoryForm.value = {
    id: null,
    name: '',
    category_type: 'expense',
    reassign_existing_to_id: null,
    color: '#8B5CF6',
    default_expense_nature: 'variable',
    description: '',
  };
}

async function handleSaveCategory() {
  if (!categoryForm.value.name.trim()) return;
  errorMessage.value = null;
  savingCategory.value = true;
  try {
    const cleanDesc = categoryForm.value.description.trim() || undefined;
    const isIncome = categoryForm.value.category_type === 'income';
    const naturePayload: ExpenseNature = isIncome ? 'unclassified' : categoryForm.value.default_expense_nature;
    if (categoryForm.value.id) {
      await api.updateCategory(categoryForm.value.id, {
        name: categoryForm.value.name.trim(),
        category_type: categoryForm.value.category_type,
        reassign_existing_to_id: isChangingPurposeWithTransactions.value
          ? categoryForm.value.reassign_existing_to_id
          : undefined,
        color: categoryForm.value.color,
        default_expense_nature: naturePayload,
        description: cleanDesc,
      });
      successMessage.value = `Category '${categoryForm.value.name.trim()}' updated successfully.`;
    } else {
      await api.createCategory({
        name: categoryForm.value.name.trim(),
        category_type: categoryForm.value.category_type,
        color: categoryForm.value.color,
        default_expense_nature: naturePayload,
        description: cleanDesc,
      });
      successMessage.value = `Category '${categoryForm.value.name.trim()}' created successfully.`;
    }

    isEditingCategory.value = false;
    await Promise.all([
      loadCategories(),
      txStore.loadCategories()
    ]);
  } catch (err: any) {
    errorMessage.value = err.message || 'Failed to save category.';
  } finally {
    savingCategory.value = false;
  }
}

async function promptArchiveCategory(cat: Category) {
  const count = cat.transaction_count || 0;
  const warningMsg = count > 0 
    ? `Category "${cat.name}" is used in ${count} historical transaction(s).\n\nArchiving it will hide it from future transaction entry dropdowns, but will NOT delete or alter any existing transactions.\n\nAre you sure you want to archive this category?`
    : `Are you sure you want to archive category "${cat.name}"?`;

  if (!confirm(warningMsg)) return;

  try {
    await api.deleteCategory(cat.id);
    successMessage.value = `Category '${cat.name}' has been archived.`;
    await Promise.all([
      loadCategories(),
      txStore.loadCategories()
    ]);
  } catch (err: any) {
    errorMessage.value = err.message || 'Failed to archive category.';
  }
}

async function handleReactivateCategory(cat: Category) {
  try {
    await api.updateCategory(cat.id, { is_active: true });
    successMessage.value = `Category '${cat.name}' has been reactivated.`;
    await Promise.all([
      loadCategories(),
      txStore.loadCategories()
    ]);
  } catch (err: any) {
    errorMessage.value = err.message || 'Failed to reactivate category.';
  }
}

function openDeleteCategory(cat: Category) {
  deletingCategory.value = cat;
  isDeleteCategoryOpen.value = true;
}

async function handleCategoryDeleted() {
  isDeleteCategoryOpen.value = false;
  successMessage.value = 'Category permanently deleted.';
  await Promise.all([
    loadCategories(),
    txStore.loadCategories()
  ]);
}

async function handleCategoryArchived() {
  isDeleteCategoryOpen.value = false;
  successMessage.value = 'Category archived successfully.';
  await Promise.all([
    loadCategories(),
    txStore.loadCategories()
  ]);
}

// Helpers
function formatAccountType(type: AccountType | string): string {
  switch (type) {
    case 'current': return 'Current';
    case 'savings': return 'Savings';
    case 'cash': return 'Cash';
    case 'credit_card': return 'Credit Card';
    case 'investment': return 'Investment';
    default: return type;
  }
}

function formatShortDate(dateStr: string): string {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
}

watch(() => props.isOpen, (newVal) => {
  if (newVal) {
    accountsStore.loadData();
    loadCategories();
    successMessage.value = null;
    errorMessage.value = null;
    if (props.initialTab) {
      activeTab.value = props.initialTab;
    }
  }
});

watch(() => props.initialTab, (newTab) => {
  if (newTab) activeTab.value = newTab;
});

onMounted(() => {
  if (props.isOpen) {
    accountsStore.loadData();
    loadCategories();
  }
});
</script>

