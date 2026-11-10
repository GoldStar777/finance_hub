<template>
  <div class="space-y-6 animate-fadeIn pb-16">
    
    <!-- Top Action Bar -->
    <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
      <div>
        <h1 class="text-xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center space-x-2.5">
          <span>Portfolio Desk</span>
          <span 
            v-if="investmentsStore.summary" 
            class="px-2 py-0.5 rounded-full text-xs font-mono font-semibold bg-indigo-100 dark:bg-indigo-950 text-indigo-800 dark:text-indigo-300">
            {{ totalHoldingsCount }} holdings
          </span>
        </h1>
        <p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
          Provider-agnostic portfolio management, fractional units, and dated valuation checkpoints.
        </p>
      </div>

      <!-- Action Buttons -->
      <div class="flex items-center space-x-2.5 shrink-0">
        <button
          @click="openAddHoldingModal"
          class="px-4 py-1.5 rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 text-xs font-semibold hover:opacity-90 transition shadow-sm flex items-center space-x-1.5">
          <span>+ Add Holding</span>
        </button>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="investmentsStore.loading && !investmentsStore.summary" class="h-48 rounded-2xl bg-slate-100 dark:bg-slate-800/40 animate-pulse"></div>

    <!-- Error State -->
    <div v-else-if="investmentsStore.error" class="p-4 rounded-xl border border-rose-200 dark:border-rose-900 bg-rose-50 dark:bg-rose-950/40 text-rose-600 dark:text-rose-400 text-xs">
      {{ investmentsStore.error }}
    </div>

    <!-- Main Content -->
    <template v-else-if="investmentsStore.summary">
      
      <!-- Top Hero Metrics & Asset Class Breakdown -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        <!-- Total Invested Assets Card -->
        <div class="relative overflow-hidden rounded-2xl border border-indigo-200 dark:border-indigo-800/50 bg-gradient-to-br from-indigo-50/70 via-white to-indigo-100/40 dark:from-brand-darksurface dark:via-brand-darksurface dark:to-indigo-950/40 p-6 shadow-sm">
          <div class="flex items-center justify-between">
            <span class="font-mono text-[11px] uppercase tracking-wider text-slate-500 dark:text-slate-400 font-semibold">
              Total Invested Value
            </span>
            <span class="text-xs px-2.5 py-0.5 rounded-full font-mono bg-indigo-200/60 dark:bg-indigo-950 text-indigo-900 dark:text-indigo-300 font-medium">
              {{ investmentsStore.summary.accounts.length }} Portfolios
            </span>
          </div>
          <div class="text-3xl font-extrabold tracking-tight sensitive text-slate-900 dark:text-white mt-3 font-mono">
            {{ displayedTotalInvested }}
          </div>
          <p class="text-xs text-slate-500 dark:text-slate-400 mt-1.5">
            {{ selectedAccount ? `Valuation for ${selectedAccount.account_name} (${selectedAccount.currency})` : 'Consolidated valuation across all investment accounts' }}
          </p>
        </div>

        <!-- Asset Allocation Card -->
        <div class="lg:col-span-2 rounded-2xl border border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface p-6 shadow-sm space-y-3">
          <div class="flex items-center justify-between">
            <h2 class="font-mono text-xs uppercase tracking-wider font-bold text-slate-500 dark:text-slate-400">
              Asset Class Allocation
            </h2>
            <span class="text-xs text-slate-400 font-mono">
              {{ investmentsStore.summary.asset_allocation.length }} classes
            </span>
          </div>

          <!-- Allocation Pills / Badges -->
          <div v-if="investmentsStore.summary.asset_allocation.length > 0" class="flex flex-wrap gap-2.5 pt-1">
            <div 
              v-for="item in investmentsStore.summary.asset_allocation" 
              :key="item.asset_class"
              class="px-3 py-1.5 rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50 dark:bg-slate-800/60 flex items-center space-x-2">
              <span class="w-2 h-2 rounded-full" :class="getAssetClassColor(item.asset_class)"></span>
              <span class="text-xs font-medium text-slate-700 dark:text-slate-300">{{ formatAssetClass(item.asset_class) }}</span>
              <span class="text-xs font-mono font-bold text-slate-900 dark:text-white">{{ item.percentage }}%</span>
              <span class="text-[10px] font-mono text-slate-400 sensitive">£{{ (item.total_pounds).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}</span>
            </div>
          </div>
          <div v-else class="text-xs text-slate-400 italic py-2">
            No asset classes recorded yet. Add holdings with valuations to view portfolio allocation.
          </div>
        </div>
      </div>

      <!-- Account Selector Tabs -->
      <div class="flex items-center space-x-2 overflow-x-auto pb-1 scrollbar-none">
        <button
          @click="investmentsStore.selectedAccountId = null"
          class="px-4 py-2 rounded-xl text-xs font-semibold whitespace-nowrap transition flex items-center space-x-2 border"
          :class="investmentsStore.selectedAccountId === null
            ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-950 border-slate-900 dark:border-white shadow-xs'
            : 'border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'">
          <span>All Accounts</span>
          <span class="text-[10px] font-mono px-1.5 py-0.5 rounded-full" :class="investmentsStore.selectedAccountId === null ? 'bg-slate-800 dark:bg-slate-200 text-slate-200 dark:text-slate-800' : 'bg-slate-100 dark:bg-slate-800 text-slate-500'">
            {{ totalHoldingsCount }}
          </span>
        </button>

        <button
          v-for="acc in investmentsStore.summary.accounts"
          :key="acc.account_id"
          @click="investmentsStore.selectedAccountId = acc.account_id"
          class="px-4 py-2 rounded-xl text-xs font-semibold whitespace-nowrap transition flex items-center space-x-2 border"
          :class="investmentsStore.selectedAccountId === acc.account_id
            ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-950 border-slate-900 dark:border-white shadow-xs'
            : 'border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'">
          <span class="w-2 h-2 rounded-full" :style="{ backgroundColor: acc.color || '#3B82F6' }"></span>
          <span>{{ acc.account_name }}</span>
          <span class="text-[10px] font-mono font-bold sensitive">{{ acc.formatted_balance }}</span>
          <span 
            v-if="acc.has_unvalued_holdings" 
            class="w-1.5 h-1.5 rounded-full bg-amber-500" 
            title="Contains unvalued holdings"></span>
        </button>
      </div>

      <!-- Specific Account Context Ribbon (When single account selected) -->
      <div 
        v-if="selectedAccount" 
        class="p-4 rounded-2xl border border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface flex flex-col md:flex-row md:items-center justify-between gap-4">
        
        <div class="flex items-center space-x-3.5">
          <div class="w-3.5 h-3.5 rounded-full" :style="{ backgroundColor: selectedAccount.color || '#3B82F6' }"></div>
          <div>
            <div class="flex items-center space-x-2">
              <h2 class="font-bold text-sm text-slate-900 dark:text-white">{{ selectedAccount.account_name }}</h2>
              <span class="text-[10px] font-mono px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 font-semibold">
                {{ selectedAccount.currency }}
              </span>
              <span 
                class="text-[10px] font-mono px-2 py-0.5 rounded-full font-semibold bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-900/50">
                {{ selectedAccount.holdings_count }} {{ selectedAccount.holdings_count === 1 ? 'holding' : 'holdings' }}
              </span>
            </div>
            <p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              Balance dynamically derived from active holding valuations.
            </p>
          </div>
        </div>
      </div>

      <!-- Warning Alert: Unvalued Holdings Detected -->
      <div 
        v-if="selectedAccount && selectedAccount.has_unvalued_holdings" 
        class="p-4 rounded-xl border border-amber-200 dark:border-amber-900/50 bg-amber-50 dark:bg-amber-950/30 flex items-start space-x-3 text-amber-800 dark:text-amber-300 text-xs">
        <span class="text-base shrink-0">⚠️</span>
        <div>
          <span class="font-bold">Unvalued Holdings Detected:</span>
          <span> This account has {{ selectedAccount.unvalued_count }} holding(s) without any recorded valuation. Their values are treated as missing and contribute £0.00 to the rollup until a valuation is entered.</span>
        </div>
      </div>

      <!-- Holdings Filter & Search -->
      <div class="flex items-center justify-between gap-4">
        <div class="relative max-w-xs w-full">
          <input 
            v-model="searchQuery"
            type="text"
            placeholder="Search holdings by name or ticker..."
            class="w-full bg-brand-surface dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder rounded-xl px-3.5 py-2 text-xs text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:border-slate-400 dark:focus:border-slate-600" />
        </div>
        <div class="text-xs font-mono text-slate-400">
          Showing {{ displayedHoldings.length }} holding(s)
        </div>
      </div>

      <!-- Holdings Table -->
      <div class="border border-brand-border dark:border-brand-darkborder rounded-2xl bg-brand-surface dark:bg-brand-darksurface overflow-hidden shadow-xs">
        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs border-collapse">
            <thead>
              <tr class="border-b border-brand-border dark:border-brand-darkborder bg-slate-50/60 dark:bg-slate-800/40 text-slate-500 dark:text-slate-400 font-mono text-[11px] uppercase tracking-wider">
                <th class="py-3 px-4 font-semibold">Holding & Ticker</th>
                <th class="py-3 px-3 font-semibold">Account</th>
                <th class="py-3 px-3 font-semibold">Asset Class</th>
                <th class="py-3 px-4 font-semibold text-right">Quantity</th>
                <th class="py-3 px-4 font-semibold text-right">Unit Price</th>
                <th class="py-3 px-4 font-semibold text-right">Total Valuation</th>
                <th class="py-3 px-3 font-semibold text-center">Last Updated</th>
                <th class="py-3 px-4 font-semibold text-right">Actions</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-brand-border dark:divide-brand-darkborder">
              
              <!-- Empty State -->
              <tr v-if="displayedHoldings.length === 0">
                <td colspan="8" class="py-12 text-center text-slate-400">
                  <div class="space-y-2">
                    <p class="font-medium text-slate-600 dark:text-slate-300">No holdings found</p>
                    <p class="text-xs text-slate-400 max-w-sm mx-auto">
                      {{ searchQuery ? 'No holdings match your search query.' : 'Add your first stock, ETF, mutual fund, crypto, or uninvested cash position to this account.' }}
                    </p>
                    <button 
                      @click="openAddHoldingModal"
                      class="mt-2 px-4 py-1.5 text-xs font-semibold rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 hover:opacity-90 transition">
                      + Add First Holding
                    </button>
                  </div>
                </td>
              </tr>

              <!-- Holding Rows -->
              <tr 
                v-for="item in displayedHoldings" 
                :key="item.holding.id"
                class="hover:bg-slate-50/80 dark:hover:bg-slate-800/30 transition-colors">
                
                <!-- Name & Ticker -->
                <td class="py-3 px-4">
                  <div class="font-semibold text-slate-900 dark:text-white flex items-center space-x-2">
                    <span>{{ item.holding.name }}</span>
                    <span 
                      v-if="item.holding.ticker" 
                      class="px-1.5 py-0.5 rounded font-mono text-[10px] bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 font-bold">
                      {{ item.holding.ticker }}
                    </span>
                    <span 
                      v-if="!item.holding.is_active" 
                      class="px-1.5 py-0.5 rounded font-mono text-[10px] bg-rose-100 dark:bg-rose-950 text-rose-700 dark:text-rose-300">
                      Archived
                    </span>
                  </div>
                  <div v-if="item.holding.notes" class="text-[11px] text-slate-400 truncate max-w-xs mt-0.5">
                    {{ item.holding.notes }}
                  </div>
                </td>

                <!-- Account -->
                <td class="py-3 px-3">
                  <div class="flex items-center space-x-1.5">
                    <span class="w-2 h-2 rounded-full" :style="{ backgroundColor: item.accountColor || '#3B82F6' }"></span>
                    <span class="text-slate-700 dark:text-slate-300 truncate max-w-[120px]">{{ item.accountName }}</span>
                  </div>
                </td>

                <!-- Asset Class -->
                <td class="py-3 px-3">
                  <span class="px-2 py-0.5 rounded-full text-[10px] font-mono font-medium border border-brand-border dark:border-brand-darkborder bg-slate-50 dark:bg-slate-800/60 text-slate-600 dark:text-slate-300">
                    {{ formatAssetClass(item.holding.asset_class) }}
                  </span>
                </td>

                <!-- Quantity (Fractional Precision Safe) -->
                <td class="py-3 px-4 text-right font-mono text-slate-800 dark:text-slate-200">
                  <span v-if="item.holding.is_valued && item.holding.latest_quantity !== undefined">
                    {{ formatQuantity(item.holding.latest_quantity) }}
                  </span>
                  <span v-else class="text-slate-400">-</span>
                </td>

                <!-- Unit Price -->
                <td class="py-3 px-4 text-right font-mono text-slate-700 dark:text-slate-300">
                  <span v-if="item.holding.is_valued && item.holding.formatted_unit_price">
                    {{ item.holding.formatted_unit_price }}
                  </span>
                  <span v-else class="text-slate-400">-</span>
                </td>

                <!-- Total Valuation -->
                <td class="py-3 px-4 text-right font-mono font-bold sensitive">
                  <template v-if="item.holding.is_valued">
                    <span :class="item.holding.latest_valuation_pence === 0 ? 'text-slate-400' : 'text-slate-900 dark:text-white'">
                      {{ item.holding.formatted_valuation }}
                    </span>
                  </template>
                  <template v-else>
                    <span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-100 dark:bg-amber-950/60 text-amber-800 dark:text-amber-300 border border-amber-200 dark:border-amber-900/40">
                      Unvalued
                    </span>
                  </template>
                </td>

                <!-- Last Updated Date -->
                <td class="py-3 px-3 text-center text-slate-500 font-mono text-[11px]">
                  <span v-if="item.holding.last_valuation_date">
                    {{ formatDate(item.holding.last_valuation_date) }}
                  </span>
                  <span v-else class="text-slate-400 italic">Never</span>
                </td>

                <!-- Actions -->
                <td class="py-3 px-4 text-right space-x-1.5 whitespace-nowrap">
                  <button
                    @click="openValuationModal(item.holding, item.accountCurrency)"
                    class="px-2.5 py-1 rounded-lg border border-brand-border dark:border-brand-darkborder hover:bg-slate-100 dark:hover:bg-slate-800 transition text-[11px] font-semibold text-slate-800 dark:text-slate-200"
                    title="Log dated valuation checkpoint">
                    + Value
                  </button>

                  <button
                    @click="openHistoryModal(item.holding, item.accountCurrency)"
                    class="px-2.5 py-1 rounded-lg border border-brand-border dark:border-brand-darkborder hover:bg-slate-100 dark:hover:bg-slate-800 transition text-[11px] font-semibold text-slate-600 dark:text-slate-400"
                    title="View valuation history">
                    History
                  </button>

                  <button
                    @click="openEditHoldingModal(item.holding)"
                    class="p-1 rounded text-slate-400 hover:text-slate-700 dark:hover:text-white transition"
                    title="Edit holding details">
                    ✎
                  </button>

                  <button
                    @click="confirmDeleteHolding(item.holding)"
                    class="p-1 rounded text-slate-400 hover:text-rose-600 dark:hover:text-rose-400 transition"
                    title="Delete holding">
                    🗑
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <!-- ================= MODALS ================= -->

    <!-- Add Holding Modal -->
    <div 
      v-if="isAddHoldingOpen"
      class="fixed inset-0 z-50 bg-slate-950/40 backdrop-blur-sm flex items-center justify-center p-4"
      @click.self="isAddHoldingOpen = false">
      <section 
        role="dialog" 
        aria-modal="true" 
        aria-labelledby="add-holding-title"
        class="bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-4">
        
        <div class="flex items-center justify-between pb-3 border-b border-brand-border dark:border-brand-darkborder">
          <div>
            <h2 id="add-holding-title" class="font-bold text-slate-900 dark:text-white">Add Investment Holding</h2>
            <p class="text-xs text-slate-500">Record an individual security, fund, crypto, or uninvested cash position.</p>
          </div>
          <button @click="isAddHoldingOpen = false" class="text-slate-400 hover:text-slate-600 text-lg">&times;</button>
        </div>

        <form @submit.prevent="submitAddHolding" class="space-y-4">
          <div v-if="formError" class="p-3 rounded-lg bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 text-rose-600 dark:text-rose-400 text-xs">
            {{ formError }}
          </div>

          <!-- Account Selector -->
          <div>
            <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">Target Account</label>
            <select 
              v-model="newHoldingForm.account_id" 
              required
              class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none">
              <option v-for="acc in investmentAccounts" :key="acc.account_id" :value="acc.account_id">
                {{ acc.account_name }} ({{ acc.currency }})
              </option>
            </select>
          </div>

          <!-- Name & Ticker -->
          <div class="grid grid-cols-3 gap-3">
            <div class="col-span-2">
              <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">Holding Name</label>
              <input 
                v-model="newHoldingForm.name"
                type="text"
                required
                placeholder="e.g. Vanguard FTSE All-World ETF"
                class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none" />
            </div>
            <div>
              <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">Ticker / Symbol</label>
              <input 
                v-model="newHoldingForm.ticker"
                type="text"
                placeholder="e.g. VWRP"
                class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs font-mono uppercase text-slate-900 dark:text-white focus:outline-none" />
            </div>
          </div>

          <!-- Asset Class & Currency -->
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">Asset Class</label>
              <select 
                v-model="newHoldingForm.asset_class"
                class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none">
                <option value="equity">Equity (Individual Stock)</option>
                <option value="etf">ETF (Exchange Traded Fund)</option>
                <option value="fund">Mutual Fund / Index Fund</option>
                <option value="bond">Bond / Fixed Income</option>
                <option value="crypto">Cryptocurrency</option>
                <option value="cash">Uninvested Cash</option>
                <option value="commodity">Commodity</option>
                <option value="real_estate">Real Estate</option>
                <option value="portfolio">Portfolio Valuation / Lump Sum</option>
                <option value="other">Other</option>
              </select>
            </div>
            <div>
              <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">Currency</label>
              <input 
                :value="targetAccountCurrency"
                disabled
                class="w-full bg-slate-100 dark:bg-slate-800/40 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs font-mono text-slate-500 cursor-not-allowed" />
            </div>
          </div>

          <!-- Optional Initial Position -->
          <div class="p-3.5 rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50/50 dark:bg-slate-800/30 space-y-3">
            <div class="flex items-center justify-between">
              <label class="flex items-center space-x-2 text-xs font-semibold text-slate-800 dark:text-slate-200">
                <input type="checkbox" v-model="hasInitialPosition" class="rounded border-slate-300 text-slate-900" />
                <span>Record initial position valuation now</span>
              </label>
              <button
                v-if="hasInitialPosition"
                type="button"
                @click="setLumpSumInitialPosition"
                class="text-[10px] font-semibold text-indigo-600 dark:text-indigo-400 hover:underline">
                Set Qty = 1 (Lump Sum)
              </button>
            </div>

            <div v-if="hasInitialPosition" class="space-y-3 pt-1">
              <p v-if="newHoldingForm.initial_quantity === 1" class="text-[10px] text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-slate-800 px-2.5 py-1.5 rounded-lg">
                💡 Whole-account / lump-sum position: Quantity is 1 and Total Valuation will be the unit valuation.
              </p>
              <div class="grid grid-cols-2 gap-3">
                <div>
                  <label class="block text-[10px] font-mono uppercase text-slate-400 mb-1">Quantity (Units/Shares)</label>
                  <input 
                    v-model.number="newHoldingForm.initial_quantity"
                    type="number"
                    step="any"
                    min="0"
                    required
                    placeholder="e.g. 15.4820"
                    class="w-full bg-white dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-lg px-2.5 py-1.5 text-xs font-mono text-slate-900 dark:text-white" />
                </div>
                <div>
                  <label class="block text-[10px] font-mono uppercase text-slate-400 mb-1">Total Valuation ({{ targetAccountCurrency }})</label>
                  <input 
                    v-model.number="newHoldingForm.initial_valuation"
                    type="number"
                    step="0.01"
                    min="0"
                    placeholder="e.g. 1250.00"
                    class="w-full bg-white dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-lg px-2.5 py-1.5 text-xs font-mono text-slate-900 dark:text-white" />
                </div>
              </div>
              <div>
                <label class="block text-[10px] font-mono uppercase text-slate-400 mb-1">Effective Date</label>
                <input 
                  v-model="newHoldingForm.initial_effective_date"
                  type="date"
                  class="w-full bg-white dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-lg px-2.5 py-1.5 text-xs font-mono text-slate-900 dark:text-white" />
              </div>
            </div>
          </div>

          <!-- Notes -->
          <div>
            <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">Notes (Optional)</label>
            <input 
              v-model="newHoldingForm.notes"
              type="text"
              placeholder="e.g. Purchased via monthly direct debit"
              class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none" />
          </div>

          <!-- Actions -->
          <div class="flex items-center justify-end space-x-2 pt-2">
            <button 
              type="button" 
              @click="isAddHoldingOpen = false"
              class="px-4 py-2 rounded-xl text-xs font-medium text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800">
              Cancel
            </button>
            <button 
              type="submit"
              :disabled="investmentsStore.loading"
              class="px-4 py-2 rounded-xl text-xs font-semibold bg-slate-900 text-white dark:bg-white dark:text-slate-900 shadow-sm hover:opacity-90 transition">
              {{ investmentsStore.loading ? 'Adding...' : 'Add Holding' }}
            </button>
          </div>
        </form>
      </section>
    </div>

    <!-- Edit Holding Modal -->
    <div 
      v-if="isEditHoldingOpen && editingHolding"
      class="fixed inset-0 z-50 bg-slate-950/40 backdrop-blur-sm flex items-center justify-center p-4"
      @click.self="isEditHoldingOpen = false">
      <section 
        role="dialog" 
        aria-modal="true" 
        aria-labelledby="edit-holding-title"
        class="bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-4">
        
        <div class="flex items-center justify-between pb-3 border-b border-brand-border dark:border-brand-darkborder">
          <div>
            <h2 id="edit-holding-title" class="font-bold text-slate-900 dark:text-white">Edit Holding Details</h2>
            <p class="text-xs text-slate-500">Update holding metadata or reassign to another investment account.</p>
          </div>
          <button @click="isEditHoldingOpen = false" class="text-slate-400 hover:text-slate-600 text-lg">&times;</button>
        </div>

        <form @submit.prevent="submitEditHolding" class="space-y-4">
          <!-- Account Selector -->
          <div>
            <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">Linked Investment Account</label>
            <select 
              v-model="editHoldingForm.account_id" 
              required
              class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none">
              <option v-for="acc in investmentAccounts" :key="acc.account_id" :value="acc.account_id">
                {{ acc.account_name }} ({{ acc.currency }})
              </option>
            </select>
            <span v-if="editHoldingForm.account_id !== editingHolding.account_id" class="text-[10px] text-amber-600 dark:text-amber-400 mt-1 block">
              Moving this holding preserves all valuation history and updates both account totals immediately.
            </span>
          </div>

          <!-- Name & Ticker -->
          <div class="grid grid-cols-3 gap-3">
            <div class="col-span-2">
              <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">Holding Name</label>
              <input 
                v-model="editHoldingForm.name"
                type="text"
                required
                placeholder="e.g. Vanguard FTSE All-World ETF"
                class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none" />
            </div>
            <div>
              <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">Ticker / Symbol</label>
              <input 
                v-model="editHoldingForm.ticker"
                type="text"
                placeholder="e.g. VWRP"
                class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs font-mono uppercase text-slate-900 dark:text-white focus:outline-none" />
            </div>
          </div>

          <!-- Asset Class -->
          <div>
            <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">Asset Class</label>
            <select 
              v-model="editHoldingForm.asset_class"
              class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none">
              <option value="equity">Equity (Individual Stock)</option>
              <option value="etf">ETF (Exchange Traded Fund)</option>
              <option value="fund">Mutual Fund / Index Fund</option>
              <option value="bond">Bond / Fixed Income</option>
              <option value="crypto">Cryptocurrency</option>
              <option value="cash">Uninvested Cash</option>
              <option value="commodity">Commodity</option>
              <option value="real_estate">Real Estate</option>
              <option value="portfolio">Portfolio Valuation / Lump Sum</option>
              <option value="other">Other</option>
            </select>
          </div>

          <!-- Notes -->
          <div>
            <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">Notes (Optional)</label>
            <input 
              v-model="editHoldingForm.notes"
              type="text"
              placeholder="e.g. Purchased via monthly direct debit"
              class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none" />
          </div>

          <!-- Actions -->
          <div class="flex items-center justify-end space-x-2 pt-2">
            <button 
              type="button" 
              @click="isEditHoldingOpen = false"
              class="px-4 py-2 rounded-xl text-xs font-medium text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800">
              Cancel
            </button>
            <button 
              type="submit"
              :disabled="investmentsStore.loading"
              class="px-4 py-2 rounded-xl text-xs font-semibold bg-slate-900 text-white dark:bg-white dark:text-slate-900 shadow-sm hover:opacity-90 transition">
              {{ investmentsStore.loading ? 'Saving...' : 'Save Changes' }}
            </button>
          </div>
        </form>
      </section>
    </div>

    <!-- Record Valuation Modal -->
    <div 
      v-if="isValuationModalOpen && targetValuationHolding"
      class="fixed inset-0 z-50 bg-slate-950/40 backdrop-blur-sm flex items-center justify-center p-4"
      @click.self="isValuationModalOpen = false">
      <section 
        role="dialog" 
        aria-modal="true" 
        class="bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4">
        
        <div class="flex items-center justify-between pb-3 border-b border-brand-border dark:border-brand-darkborder">
          <div>
            <h2 class="font-bold text-slate-900 dark:text-white">Record Position Valuation</h2>
            <p class="text-xs text-slate-500">{{ targetValuationHolding.name }} ({{ targetValuationCurrency }})</p>
          </div>
          <button @click="isValuationModalOpen = false" class="text-slate-400 hover:text-slate-600 text-lg">&times;</button>
        </div>

        <form @submit.prevent="submitRecordValuation" class="space-y-4">
          <div v-if="valuationFormError" class="p-3 rounded-lg bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 text-rose-600 dark:text-rose-400 text-xs">
            {{ valuationFormError }}
          </div>

          <!-- Date -->
          <div>
            <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
              Effective Date (Supports Backdating)
            </label>
            <input 
              v-model="valuationForm.effective_date"
              type="date"
              required
              class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs font-mono text-slate-900 dark:text-white focus:outline-none" />
          </div>

          <!-- Quantity -->
          <div>
            <div class="flex items-center justify-between mb-1">
              <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500">
                Current Quantity (Shares / Units, >= 0)
              </label>
              <button
                type="button"
                @click="setLumpSumValuation"
                class="text-[10px] font-semibold text-indigo-600 dark:text-indigo-400 hover:underline">
                Set Qty = 1 (Lump Sum)
              </button>
            </div>
            <input 
              v-model.number="valuationForm.quantity"
              type="number"
              step="any"
              min="0"
              required
              @input="handleValuationQuantityChange"
              placeholder="e.g. 15.4820"
              class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs font-mono text-slate-900 dark:text-white focus:outline-none" />
            <p v-if="valuationForm.quantity === 1" class="text-[10px] text-slate-500 dark:text-slate-400 mt-1">
              💡 Lump-sum mode: Total Value and Unit Price are equivalent.
            </p>
          </div>

          <!-- Unit Price or Total Value (Linked) -->
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
                Unit Price ({{ targetValuationCurrency }})
              </label>
              <input 
                v-model.number="valuationForm.unit_price"
                type="number"
                step="any"
                min="0"
                @input="handleUnitPriceChange"
                placeholder="e.g. 85.12"
                class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs font-mono text-slate-900 dark:text-white focus:outline-none" />
            </div>

            <div>
              <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">
                Total Value ({{ targetValuationCurrency }})
              </label>
              <input 
                v-model.number="valuationForm.valuation"
                type="number"
                step="0.01"
                min="0"
                @input="handleTotalValuationChange"
                placeholder="e.g. 1317.88"
                class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs font-mono font-bold text-slate-900 dark:text-white focus:outline-none" />
            </div>
          </div>

          <!-- Notes -->
          <div>
            <label class="block text-[11px] font-mono uppercase font-semibold text-slate-500 mb-1">Notes / Reason</label>
            <input 
              v-model="valuationForm.notes"
              type="text"
              placeholder="e.g. Monthly statement check, dividend reinvestment"
              class="w-full bg-slate-50 dark:bg-slate-800 border border-brand-border dark:border-brand-darkborder rounded-xl px-3 py-2 text-xs text-slate-900 dark:text-white focus:outline-none" />
          </div>

          <!-- Actions -->
          <div class="flex items-center justify-end space-x-2 pt-2">
            <button 
              type="button" 
              @click="isValuationModalOpen = false"
              class="px-4 py-2 rounded-xl text-xs font-medium text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800">
              Cancel
            </button>
            <button 
              type="submit"
              class="px-4 py-2 rounded-xl text-xs font-semibold bg-slate-900 text-white dark:bg-white dark:text-slate-900 shadow-sm hover:opacity-90 transition">
              Save Valuation
            </button>
          </div>
        </form>
      </section>
    </div>

    <!-- Valuation History Modal -->
    <div 
      v-if="isHistoryModalOpen && investmentsStore.activeHolding"
      class="fixed inset-0 z-50 bg-slate-950/40 backdrop-blur-sm flex items-center justify-center p-4"
      @click.self="isHistoryModalOpen = false">
      <section 
        role="dialog" 
        aria-modal="true" 
        class="bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder rounded-2xl max-w-2xl w-full p-6 shadow-2xl space-y-4 max-h-[85vh] flex flex-col">
        
        <div class="flex items-center justify-between pb-3 border-b border-brand-border dark:border-brand-darkborder shrink-0">
          <div>
            <h2 class="font-bold text-slate-900 dark:text-white">Valuation History</h2>
            <p class="text-xs text-slate-500">
              {{ investmentsStore.activeHolding.name }} 
              <span v-if="investmentsStore.activeHolding.ticker" class="font-mono font-bold">({{ investmentsStore.activeHolding.ticker }})</span>
            </p>
          </div>
          <button @click="isHistoryModalOpen = false" class="text-slate-400 hover:text-slate-600 text-lg">&times;</button>
        </div>

        <!-- History Content -->
        <div class="overflow-y-auto flex-1 pr-1">
          <div v-if="investmentsStore.valuationsLoading" class="py-8 text-center text-xs text-slate-400">
            Loading valuation records...
          </div>
          <div v-else-if="investmentsStore.activeValuations.length === 0" class="py-8 text-center text-xs text-slate-400">
            No valuation checkpoints recorded for this position yet.
          </div>
          <div v-else class="space-y-2.5">
            <div 
              v-for="v in investmentsStore.activeValuations" 
              :key="v.id"
              class="p-3.5 rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50/50 dark:bg-slate-800/30 flex items-center justify-between gap-3 text-xs">
              
              <div>
                <div class="flex items-center space-x-2">
                  <span class="font-mono font-bold text-slate-900 dark:text-white">{{ formatDate(v.effective_date) }}</span>
                  <span class="font-mono text-slate-600 dark:text-slate-300">{{ formatQuantity(v.quantity) }} units</span>
                  <span v-if="v.formatted_unit_price" class="text-slate-400 font-mono">@ {{ v.formatted_unit_price }}</span>
                </div>
                <div v-if="v.notes" class="text-[11px] text-slate-400 mt-0.5">{{ v.notes }}</div>
              </div>

              <div class="flex items-center space-x-3 shrink-0">
                <span class="font-mono font-bold text-slate-900 dark:text-white sensitive text-sm">
                  {{ v.formatted_valuation }}
                </span>
                
                <button 
                  @click="promptDeleteValuation(v)"
                  class="text-rose-500 hover:text-rose-700 text-xs px-2 py-1 rounded hover:bg-rose-50 dark:hover:bg-rose-950/40 transition"
                  title="Delete this valuation record">
                  Delete
                </button>
              </div>
            </div>
          </div>
        </div>

        <div class="pt-3 border-t border-brand-border dark:border-brand-darkborder flex justify-end shrink-0">
          <button 
            @click="isHistoryModalOpen = false"
            class="px-4 py-2 rounded-xl text-xs font-semibold bg-slate-900 text-white dark:bg-white dark:text-slate-900">
            Close
          </button>
        </div>
      </section>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useInvestmentsStore } from '../stores/investments';
import { useAccountsStore } from '../stores/accounts';
import type { Holding, HoldingValuation } from '../types';

const emit = defineEmits(['open-add-account']);
const investmentsStore = useInvestmentsStore();
const accountsStore = useAccountsStore();

const searchQuery = ref('');
const isAddHoldingOpen = ref(false);
const isEditHoldingOpen = ref(false);
const isValuationModalOpen = ref(false);
const isHistoryModalOpen = ref(false);

const editingHolding = ref<Holding | null>(null);
const targetValuationHolding = ref<Holding | null>(null);
const targetValuationCurrency = ref('GBP');

const formError = ref<string | null>(null);
const valuationFormError = ref<string | null>(null);
const hasInitialPosition = ref(false);

const editHoldingForm = ref({
  name: '',
  ticker: '',
  asset_class: 'equity',
  account_id: 0,
  notes: ''
});

const newHoldingForm = ref({
  account_id: 0,
  name: '',
  ticker: '',
  asset_class: 'equity',
  notes: '',
  initial_quantity: undefined as number | undefined,
  initial_unit_price: undefined as number | undefined,
  initial_valuation: undefined as number | undefined,
  initial_effective_date: new Date().toISOString().substring(0, 10),
});

const valuationForm = ref({
  effective_date: new Date().toISOString().substring(0, 10),
  quantity: 0,
  unit_price: undefined as number | undefined,
  valuation: undefined as number | undefined,
  notes: '',
});

const investmentAccounts = computed(() => {
  if (investmentsStore.summary?.accounts && investmentsStore.summary.accounts.length > 0) {
    return investmentsStore.summary.accounts;
  }
  return accountsStore.accounts
    .filter(a => a.account_type === 'investment' && a.is_active)
    .map(a => ({
      account_id: a.id,
      account_name: a.name,
      currency: a.currency,
      color: a.color,
      valuation_mode: (a.valuation_mode || 'holdings') as 'snapshot' | 'holdings',
      balance_pence: a.current_balance_pence,
      balance_pounds: a.current_balance_pounds,
      formatted_balance: a.formatted_balance,
      holdings_count: a.holdings_count || 0,
      valued_count: 0,
      unvalued_count: 0,
      has_unvalued_holdings: a.has_unvalued_holdings || false
    }));
});

watch(investmentAccounts, (accs) => {
  if (accs.length > 0) {
    if (!newHoldingForm.value.account_id || !accs.some(a => a.account_id === newHoldingForm.value.account_id)) {
      newHoldingForm.value.account_id = selectedAccount.value ? selectedAccount.value.account_id : accs[0].account_id;
    }
  }
}, { immediate: true });

onMounted(async () => {
  await Promise.all([
    investmentsStore.loadAllData(),
    accountsStore.loadData()
  ]);
  if (investmentAccounts.value.length > 0) {
    newHoldingForm.value.account_id = investmentAccounts.value[0].account_id;
  }
});

const selectedAccount = computed(() => {
  if (!investmentsStore.summary || investmentsStore.selectedAccountId === null) return null;
  return investmentsStore.summary.accounts.find(a => a.account_id === investmentsStore.selectedAccountId) || null;
});

const targetAccountCurrency = computed(() => {
  const acc = investmentAccounts.value.find(a => a.account_id === newHoldingForm.value.account_id);
  return acc ? acc.currency : 'GBP';
});

const totalHoldingsCount = computed(() => {
  let count = 0;
  for (const accId in investmentsStore.accountHoldings) {
    count += investmentsStore.accountHoldings[accId]?.holdings_count || 0;
  }
  return count;
});

const displayedTotalInvested = computed(() => {
  if (selectedAccount.value) {
    return selectedAccount.value.formatted_balance;
  }
  return investmentsStore.summary?.formatted_total_invested || '£0.00';
});

interface HoldingRowItem {
  holding: Holding;
  accountId: number;
  accountName: string;
  accountCurrency: string;
  accountColor: string;
}

const displayedHoldings = computed<HoldingRowItem[]>(() => {
  const rows: HoldingRowItem[] = [];
  const accounts = investmentsStore.summary?.accounts || [];

  for (const acc of accounts) {
    if (investmentsStore.selectedAccountId !== null && acc.account_id !== investmentsStore.selectedAccountId) {
      continue;
    }
    const accData = investmentsStore.accountHoldings[acc.account_id];
    if (accData && accData.holdings) {
      for (const h of accData.holdings) {
        if (searchQuery.value) {
          const q = searchQuery.value.toLowerCase();
          const matchName = h.name.toLowerCase().includes(q);
          const matchTicker = (h.ticker || '').toLowerCase().includes(q);
          if (!matchName && !matchTicker) continue;
        }
        rows.push({
          holding: h,
          accountId: acc.account_id,
          accountName: acc.account_name,
          accountCurrency: acc.currency,
          accountColor: acc.color,
        });
      }
    }
  }
  return rows;
});

function getAssetClassColor(assetClass: string): string {
  switch (assetClass.toLowerCase()) {
    case 'equity': return 'bg-blue-500';
    case 'etf': return 'bg-indigo-500';
    case 'fund': return 'bg-violet-500';
    case 'bond': return 'bg-emerald-500';
    case 'crypto': return 'bg-amber-500';
    case 'cash': return 'bg-teal-500';
    case 'real_estate': return 'bg-orange-500';
    case 'portfolio': return 'bg-cyan-500';
    case 'commodity': return 'bg-yellow-500';
    default: return 'bg-slate-400';
  }
}

function formatAssetClass(assetClass: string): string {
  if (!assetClass) return 'Other';
  const lower = assetClass.toLowerCase();
  if (lower === 'portfolio') return 'Portfolio Valuation';
  if (lower === 'real_estate') return 'Real Estate';
  if (lower === 'etf') return 'ETF';
  return assetClass.charAt(0).toUpperCase() + assetClass.slice(1);
}

function setLumpSumInitialPosition() {
  newHoldingForm.value.initial_quantity = 1.0;
  if (!newHoldingForm.value.asset_class || newHoldingForm.value.asset_class === 'equity') {
    newHoldingForm.value.asset_class = 'portfolio';
  }
}

function setLumpSumValuation() {
  valuationForm.value.quantity = 1.0;
  if (valuationForm.value.valuation !== undefined) {
    valuationForm.value.unit_price = valuationForm.value.valuation;
  } else if (valuationForm.value.unit_price !== undefined) {
    valuationForm.value.valuation = valuationForm.value.unit_price;
  }
}

function formatQuantity(qty: number): string {
  if (qty === undefined || qty === null) return '-';
  // Avoid scientific notation and trim trailing zeroes beyond 6 decimals
  return Number(qty.toFixed(6)).toString();
}

function formatDate(dateStr: string): string {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return d.toISOString().substring(0, 10);
}

function openAddHoldingModal() {
  formError.value = null;
  hasInitialPosition.value = false;
  const initialAccId = selectedAccount.value
    ? selectedAccount.value.account_id
    : (investmentAccounts.value[0]?.account_id || 0);
  newHoldingForm.value = {
    account_id: initialAccId,
    name: '',
    ticker: '',
    asset_class: 'equity',
    notes: '',
    initial_quantity: undefined,
    initial_unit_price: undefined,
    initial_valuation: undefined,
    initial_effective_date: new Date().toISOString().substring(0, 10),
  };
  isAddHoldingOpen.value = true;
}

async function submitAddHolding() {
  formError.value = null;
  try {
    await investmentsStore.createHolding(newHoldingForm.value.account_id, {
      name: newHoldingForm.value.name,
      ticker: newHoldingForm.value.ticker || undefined,
      asset_class: newHoldingForm.value.asset_class,
      notes: newHoldingForm.value.notes || undefined,
      initial_quantity: hasInitialPosition.value ? newHoldingForm.value.initial_quantity : undefined,
      initial_valuation: hasInitialPosition.value ? newHoldingForm.value.initial_valuation : undefined,
      initial_effective_date: hasInitialPosition.value ? newHoldingForm.value.initial_effective_date : undefined,
    });
    isAddHoldingOpen.value = false;
  } catch (err: any) {
    formError.value = err.message || 'Failed to create holding.';
  }
}

function openValuationModal(holding: Holding, currency: string) {
  valuationFormError.value = null;
  targetValuationHolding.value = holding;
  targetValuationCurrency.value = currency;
  valuationForm.value.effective_date = new Date().toISOString().substring(0, 10);
  valuationForm.value.quantity = holding.latest_quantity !== undefined ? holding.latest_quantity : 0;
  valuationForm.value.unit_price = holding.latest_unit_price_pounds;
  valuationForm.value.valuation = holding.latest_valuation_pounds;
  valuationForm.value.notes = '';
  isValuationModalOpen.value = true;
}

function handleValuationQuantityChange() {
  const qty = valuationForm.value.quantity;
  if (qty > 0 && valuationForm.value.unit_price) {
    valuationForm.value.valuation = Number((qty * valuationForm.value.unit_price).toFixed(2));
  }
}

function handleUnitPriceChange() {
  const qty = valuationForm.value.quantity;
  const up = valuationForm.value.unit_price;
  if (qty > 0 && up !== undefined) {
    valuationForm.value.valuation = Number((qty * up).toFixed(2));
  }
}

function handleTotalValuationChange() {
  const qty = valuationForm.value.quantity;
  const val = valuationForm.value.valuation;
  if (qty > 0 && val !== undefined) {
    valuationForm.value.unit_price = Number((val / qty).toFixed(4));
  }
}

async function submitRecordValuation() {
  if (!targetValuationHolding.value) return;
  valuationFormError.value = null;
  try {
    await investmentsStore.recordValuation(
      targetValuationHolding.value.id,
      targetValuationHolding.value.account_id,
      {
        effective_date: valuationForm.value.effective_date ? new Date(valuationForm.value.effective_date).toISOString() : undefined,
        quantity: valuationForm.value.quantity,
        unit_price: valuationForm.value.unit_price,
        valuation: valuationForm.value.valuation,
        notes: valuationForm.value.notes || undefined,
      }
    );
    isValuationModalOpen.value = false;
  } catch (err: any) {
    valuationFormError.value = err.message || 'Failed to record valuation.';
  }
}

function openHistoryModal(holding: Holding, currency: string) {
  targetValuationCurrency.value = currency;
  investmentsStore.loadValuations(holding);
  isHistoryModalOpen.value = true;
}

async function promptDeleteValuation(val: HoldingValuation) {
  const confirmed = window.confirm(
    `Are you sure you want to delete this historical valuation from ${formatDate(v_effective(val))}?\n\nIf this was the latest valuation, the position will revert to the previous recorded valuation.`
  );
  if (!confirmed || !investmentsStore.activeHolding) return;
  await investmentsStore.deleteValuation(
    val.id, 
    investmentsStore.activeHolding.id, 
    investmentsStore.activeHolding.account_id
  );
}

function v_effective(v: HoldingValuation): string {
  return v.effective_date;
}

function openEditHoldingModal(holding: Holding) {
  editingHolding.value = holding;
  editHoldingForm.value = {
    name: holding.name,
    ticker: holding.ticker || '',
    asset_class: holding.asset_class || 'equity',
    account_id: holding.account_id,
    notes: holding.notes || ''
  };
  isEditHoldingOpen.value = true;
}

async function submitEditHolding() {
  if (!editingHolding.value || !editHoldingForm.value.name.trim()) return;
  try {
    await investmentsStore.updateHolding(
      editingHolding.value.id,
      editingHolding.value.account_id,
      {
        name: editHoldingForm.value.name.trim(),
        ticker: editHoldingForm.value.ticker.trim() || undefined,
        asset_class: editHoldingForm.value.asset_class,
        account_id: editHoldingForm.value.account_id,
        notes: editHoldingForm.value.notes ? editHoldingForm.value.notes.trim() : undefined,
      }
    );
    isEditHoldingOpen.value = false;
    editingHolding.value = null;
  } catch (err: any) {
    alert(err.message || 'Failed to update holding.');
  }
}

async function confirmDeleteHolding(holding: Holding) {
  const confirmed = window.confirm(
    `Are you sure you want to delete "${holding.name}"?\n\nThis will permanently delete this holding and all of its historical valuation records.`
  );
  if (!confirmed) return;
  await investmentsStore.deleteHolding(holding.id, holding.account_id);
}
</script>

