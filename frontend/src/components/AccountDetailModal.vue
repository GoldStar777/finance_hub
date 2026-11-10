<template>
  <div 
    v-if="isOpen" 
    class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fadeIn" 
    @keydown.esc="handleClose"
    data-testid="account-detail-modal"
  >
    <div class="bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder rounded-2xl w-full max-w-3xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
      
      <!-- Modal Header -->
      <div class="px-6 py-4 border-b border-brand-border dark:border-brand-darkborder flex items-center justify-between shrink-0 bg-slate-50/50 dark:bg-slate-900/20">
        <div class="flex items-center space-x-3">
          <div 
            class="w-4 h-4 rounded-full shrink-0" 
            :style="{ backgroundColor: breakdown?.color || '#3B82F6' }">
          </div>
          <div>
            <div class="flex items-center space-x-2">
              <h3 class="text-base sm:text-lg font-bold text-slate-900 dark:text-white truncate">
                {{ breakdown?.account_name || 'Account Detail' }}
              </h3>
              <span 
                v-if="breakdown" 
                class="text-[10px] font-mono px-2 py-0.5 rounded-full font-semibold"
                :class="getGroupBadgeClass(breakdown.account_group)">
                {{ breakdown.account_group }}
              </span>
              <span 
                v-if="breakdown && !breakdown.is_active" 
                class="text-[9px] font-mono px-1.5 py-0.5 rounded bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300 font-semibold uppercase">
                Archived
              </span>
            </div>
            <p class="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5 flex items-center space-x-2">
              <span>Currency: <strong>{{ breakdown?.currency }} ({{ breakdown?.currency_symbol }})</strong></span>
              <span>·</span>
              <span>Timezone: <strong>{{ breakdown?.app_timezone }}</strong></span>
            </p>
          </div>
        </div>

        <div class="flex items-center space-x-2">
          <button 
            v-if="breakdown"
            type="button" 
            @click="handleEdit" 
            class="px-3 py-1 rounded-lg border border-slate-300 dark:border-slate-700 text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition">
            Edit
          </button>
          <button 
            @click="handleClose" 
            type="button"
            class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 text-xl font-semibold leading-none p-1">
            &times;
          </button>
        </div>
      </div>

      <!-- Loading State -->
      <div v-if="isLoading" class="p-12 text-center space-y-3 flex-1 flex flex-col items-center justify-center">
        <div class="animate-spin w-8 h-8 border-3 border-brand-primary border-t-transparent rounded-full"></div>
        <p class="text-xs text-slate-500 font-medium">Loading account breakdown and ground-truth history...</p>
      </div>

      <!-- Error State -->
      <div v-else-if="errorMessage" class="p-8 text-center space-y-4 flex-1">
        <div class="p-4 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 text-xs text-rose-700 dark:text-rose-300">
          <strong>Failed to load account breakdown:</strong> {{ errorMessage }}
        </div>
        <button 
          @click="loadBreakdown"
          type="button" 
          class="px-4 py-2 rounded-lg bg-slate-900 text-white dark:bg-white dark:text-slate-900 text-xs font-semibold">
          Retry
        </button>
      </div>

      <!-- Modal Body (Loaded) -->
      <div v-else-if="breakdown" class="p-6 overflow-y-auto space-y-6 flex-1">
        
        <!-- Primary Balance & Provenance Hero Card -->
        <div class="p-5 rounded-2xl border border-brand-border dark:border-brand-darkborder bg-slate-50 dark:bg-slate-900/40 space-y-4">
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <span class="text-[10px] font-mono uppercase tracking-wider text-slate-400 block mb-1">
                {{ breakdown.account_type === 'credit_card' && breakdown.current_balance_pence < 0 ? 'Current Balance (Liability Owed)' : 'Current Calculated Balance' }}
              </span>
              <div 
                class="text-3xl font-extrabold font-mono sensitive"
                :class="breakdown.current_balance_pence < 0 ? 'text-rose-600 dark:text-rose-400' : 'text-slate-900 dark:text-white'">
                {{ breakdown.formatted_current_balance }}
              </div>
            </div>

            <!-- Ground-Truth Anchor Status Pill -->
            <div class="text-left sm:text-right">
              <span class="text-[10px] font-mono uppercase tracking-wider text-slate-400 block mb-1">
                Ground-Truth Anchor Status
              </span>
              <span 
                class="inline-flex items-center space-x-1.5 px-3 py-1 rounded-full text-xs font-semibold"
                :class="breakdown.anchor.has_anchor 
                  ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800' 
                  : 'bg-amber-50 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800'">
                <span>{{ breakdown.anchor.has_anchor ? (breakdown.anchor.is_opening ? '⚓ Opening Balance Anchor' : '⚓ Confirmed Anchor') : '⚠️ Unanchored' }}</span>
                <span>·</span>
                <span class="text-[11px]">{{ breakdown.anchor.has_anchor ? breakdown.anchor.anchor_date_local : 'From Opening Balance' }}</span>
              </span>
            </div>
          </div>

          <!-- CREDIT CARD LIABILITY EXPLANATION -->
          <div 
            v-if="breakdown.liability" 
            class="p-3.5 rounded-xl bg-rose-50/70 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900/60 flex items-start space-x-2.5 text-xs text-rose-950 dark:text-rose-200"
            data-testid="credit-card-liability-box"
          >
            <span class="text-base shrink-0">💳</span>
            <div class="space-y-1">
              <div class="font-bold flex items-center space-x-2">
                <span>Credit Liability Owed:</span>
                <span class="font-mono text-sm font-extrabold text-rose-700 dark:text-rose-300">{{ breakdown.liability.formatted_amount_owed }}</span>
              </div>
              <p class="text-[11px] text-rose-800 dark:text-rose-300/90 leading-relaxed">
                {{ breakdown.liability.explanation }}
              </p>
            </div>
          </div>

          <!-- INVESTMENT HOLDINGS BREAKDOWN -->
          <div 
            v-if="breakdown.investment" 
            class="p-3.5 rounded-xl bg-indigo-50/70 dark:bg-indigo-950/40 border border-indigo-200 dark:border-indigo-900/60 flex items-start space-x-2.5 text-xs text-indigo-950 dark:text-indigo-200"
            data-testid="investment-holdings-box"
          >
            <span class="text-base shrink-0">📈</span>
            <div class="space-y-1.5 flex-1">
              <div class="flex items-center justify-between">
                <span class="font-bold">Valuation Derivation: Active Holdings</span>
                <span class="font-mono text-[11px] px-2 py-0.5 rounded bg-indigo-100 dark:bg-indigo-900/60 text-indigo-800 dark:text-indigo-200">
                  {{ breakdown.investment.holdings_count }} Holdings ({{ breakdown.investment.valued_count }} valued)
                </span>
              </div>
              <p class="text-[11px] text-indigo-800 dark:text-indigo-300/90 leading-relaxed">
                {{ breakdown.investment.explanation }}
              </p>
              <div v-if="breakdown.investment.latest_valuation_date_formatted" class="text-[10px] font-mono text-indigo-700 dark:text-indigo-300">
                Latest security valuation recorded on: <strong>{{ breakdown.investment.latest_valuation_date_formatted }}</strong>
              </div>
            </div>
          </div>

          <!-- GROUND-TRUTH MOVEMENT EQUATION -->
          <div v-if="!breakdown.investment" class="p-3.5 rounded-xl bg-white dark:bg-brand-darksurface border border-brand-border dark:border-brand-darkborder space-y-3">
            <span class="font-mono text-[10px] uppercase font-bold text-slate-400 tracking-wider block">
              Ground-Truth Balance Equation
            </span>

            <!-- Mathematical Equation Bar -->
            <div class="flex flex-wrap items-center gap-2 font-mono text-xs sm:text-sm">
              <div class="px-2.5 py-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200">
                <span class="text-[10px] text-slate-400 block font-sans">
                  {{ breakdown.anchor.has_anchor ? (breakdown.anchor.is_opening ? 'Opening Anchor' : 'Anchor Balance') : 'Opening Balance' }}
                </span>
                <span class="font-bold">
                  {{ breakdown.anchor.has_anchor ? breakdown.anchor.formatted_balance : breakdown.formatted_starting_balance }}
                </span>
              </div>

              <span class="text-slate-400 font-bold text-base">+</span>

              <div 
                class="px-2.5 py-1.5 rounded-lg text-slate-800 dark:text-slate-200"
                :class="breakdown.movement.net_movement_pence >= 0 ? 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-800 dark:text-emerald-300' : 'bg-rose-50 dark:bg-rose-950/40 text-rose-800 dark:text-rose-300'">
                <span class="text-[10px] text-slate-400 block font-sans">Post-Anchor Movement</span>
                <span class="font-bold font-mono">{{ breakdown.movement.formatted_net_movement }}</span>
              </div>

              <span class="text-slate-400 font-bold text-base">=</span>

              <div class="px-2.5 py-1.5 rounded-lg bg-indigo-50 dark:bg-indigo-950/50 text-indigo-900 dark:text-indigo-200 border border-indigo-200 dark:border-indigo-800 font-bold">
                <span class="text-[10px] text-indigo-400 block font-sans">Current Balance</span>
                <span class="font-bold">{{ breakdown.formatted_current_balance }}</span>
              </div>
            </div>

            <!-- Inflows / Outflows Summary Grid -->
            <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-slate-100 dark:border-slate-800 text-xs">
              <div>
                <span class="text-[10px] text-slate-400 block">Inflows</span>
                <span class="font-mono font-bold text-emerald-600 dark:text-emerald-400">+{{ breakdown.movement.formatted_inflows }}</span>
              </div>
              <div>
                <span class="text-[10px] text-slate-400 block">Transfers In</span>
                <span class="font-mono font-bold text-emerald-600 dark:text-emerald-400">+{{ breakdown.movement.formatted_transfers_in }}</span>
              </div>
              <div>
                <span class="text-[10px] text-slate-400 block">Outflows</span>
                <span class="font-mono font-bold text-rose-600 dark:text-rose-400">-{{ breakdown.movement.formatted_outflows }}</span>
              </div>
              <div>
                <span class="text-[10px] text-slate-400 block">Transfers Out</span>
                <span class="font-mono font-bold text-rose-600 dark:text-rose-400">-{{ breakdown.movement.formatted_transfers_out }}</span>
              </div>
            </div>
            
            <div class="text-[10px] text-slate-400 font-mono flex items-center justify-between pt-1">
              <span>{{ breakdown.movement.transaction_count }} transaction{{ breakdown.movement.transaction_count === 1 ? '' : 's' }} recorded after anchor</span>
              <span v-if="breakdown.anchor.notes" class="italic">"{{ breakdown.anchor.notes }}"</span>
            </div>
          </div>

          <!-- PLANNED UPCOMING ACTIVITY & PROJECTED BALANCE -->
          <div 
            v-if="breakdown.planned_movement && breakdown.planned_movement.transaction_count > 0"
            data-testid="account-planned-breakdown"
            class="p-3.5 rounded-xl bg-amber-50/60 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-900/60 space-y-2.5">
            <div class="flex items-center justify-between">
              <span class="font-mono text-[10px] uppercase font-bold text-amber-800 dark:text-amber-400 tracking-wider flex items-center gap-1.5">
                <span>📅</span>
                <span>Planned Upcoming Activity (Excluded from Current Balance)</span>
              </span>
              <span class="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-300">
                {{ breakdown.planned_movement.transaction_count }} planned
              </span>
            </div>

            <div class="flex flex-wrap items-center gap-2 font-mono text-xs sm:text-sm">
              <div class="px-2.5 py-1.5 rounded-lg bg-white dark:bg-slate-800 border border-amber-200 dark:border-amber-900/40 text-slate-800 dark:text-slate-200">
                <span class="text-[10px] text-slate-400 block font-sans">Current Balance</span>
                <span class="font-bold">{{ breakdown.formatted_current_balance }}</span>
              </div>

              <span class="text-amber-500 font-bold text-base">+</span>

              <div 
                class="px-2.5 py-1.5 rounded-lg text-slate-800 dark:text-slate-200 bg-white dark:bg-slate-800 border border-amber-200 dark:border-amber-900/40">
                <span class="text-[10px] text-slate-400 block font-sans">Planned Net Delta</span>
                <span 
                  class="font-bold font-mono"
                  :class="breakdown.planned_movement.net_movement_pence >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'">
                  {{ breakdown.planned_movement.formatted_net_movement }}
                </span>
              </div>

              <span class="text-amber-500 font-bold text-base">=</span>

              <div class="px-2.5 py-1.5 rounded-lg bg-amber-100 dark:bg-amber-900/40 text-amber-900 dark:text-amber-100 border border-amber-300 dark:border-amber-700 font-bold">
                <span class="text-[10px] text-amber-600 dark:text-amber-400 block font-sans">Projected Balance</span>
                <span class="font-bold">{{ breakdown.formatted_projected_balance }}</span>
              </div>
            </div>

            <p class="text-[11px] text-amber-800/80 dark:text-amber-300/80">
              These future-dated transactions will begin reducing or increasing your account balance automatically on their effective date.
            </p>
          </div>
        </div>

        <!-- Section Navigation Tabs -->
        <div class="border-b border-brand-border dark:border-brand-darkborder flex items-center space-x-4 text-xs font-semibold">
          <button 
            type="button"
            @click="activeTab = 'activity'"
            class="pb-2.5 transition border-b-2"
            :class="activeTab === 'activity' 
              ? 'border-brand-primary text-brand-primary dark:text-white' 
              : 'border-transparent text-slate-400 hover:text-slate-600 dark:hover:text-slate-300'">
            Recent Activity ({{ breakdown.recent_transactions.length }})
          </button>

          <button 
            type="button"
            @click="activeTab = 'history'"
            class="pb-2.5 transition border-b-2"
            :class="activeTab === 'history' 
              ? 'border-brand-primary text-brand-primary dark:text-white' 
              : 'border-transparent text-slate-400 hover:text-slate-600 dark:hover:text-slate-300'">
            Reconciliation & Anchors History
          </button>
        </div>

        <!-- TAB 1: RECENT ACTIVITY -->
        <div v-if="activeTab === 'activity'" class="space-y-3" data-testid="account-recent-activity">
          <div v-if="breakdown.recent_transactions.length === 0" class="p-8 text-center text-xs text-slate-400 border border-brand-border dark:border-brand-darkborder rounded-xl">
            No transactions recorded for this account yet.
          </div>

          <div v-else class="border border-brand-border dark:border-brand-darkborder rounded-xl overflow-hidden divide-y divide-brand-border dark:divide-brand-darkborder">
            <div 
              v-for="tx in breakdown.recent_transactions" 
              :key="tx.id"
              class="p-3 flex items-center justify-between text-xs bg-white dark:bg-brand-darksurface hover:bg-slate-50 dark:hover:bg-slate-800/40 transition"
            >
              <div class="space-y-0.5">
                <div class="font-semibold text-slate-900 dark:text-white flex items-center space-x-2">
                  <span>{{ tx.merchant || 'Transaction' }}</span>
                  <span 
                    v-if="tx.category_name" 
                    class="text-[10px] font-medium px-2 py-0.2 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                    {{ tx.category_name }}
                  </span>
                  <span 
                    v-if="tx.is_planned" 
                    data-testid="account-tx-planned-badge"
                    class="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border border-amber-300 dark:border-amber-800">
                    Planned
                  </span>
                </div>
                <div class="text-[11px] text-slate-400 flex items-center space-x-2">
                  <span>{{ formatDate(tx.transaction_date) }}</span>
                  <span class="capitalize">· {{ tx.transaction_type }}</span>
                  <span v-if="tx.notes" class="italic">· "{{ tx.notes }}"</span>
                </div>
              </div>

              <div 
                class="font-mono font-bold text-sm"
                :class="tx.transaction_type === 'income' ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-900 dark:text-white'">
                {{ tx.transaction_type === 'income' ? '+' : '' }}{{ tx.formatted_amount }}
              </div>
            </div>
          </div>
        </div>

        <!-- TAB 2: RECONCILIATION & ANCHORS HISTORY -->
        <div v-if="activeTab === 'history'" class="space-y-6" data-testid="account-reconciliation-history">
          
          <!-- Ground-Truth Anchors Section -->
          <div class="space-y-2.5">
            <div class="flex items-center justify-between">
              <h4 class="text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300 flex items-center space-x-1.5">
                <span>⚓</span>
                <span>Ground-Truth Balance Anchors</span>
              </h4>
              <span class="text-[11px] text-slate-400">
                Anchors reset the running ledger calculation
              </span>
            </div>

            <div v-if="breakdown.anchors.length === 0" class="p-4 rounded-xl border border-dashed border-slate-200 dark:border-slate-800 text-xs text-slate-400 text-center">
              No ground-truth anchors recorded.
            </div>

            <div v-else class="border border-brand-border dark:border-brand-darkborder rounded-xl overflow-hidden divide-y divide-brand-border dark:divide-brand-darkborder">
              <div 
                v-for="anc in breakdown.anchors" 
                :key="anc.id"
                class="p-3 flex items-center justify-between text-xs bg-white dark:bg-brand-darksurface"
              >
                <div>
                  <div class="font-semibold text-slate-900 dark:text-white flex items-center space-x-2">
                    <span class="px-1.5 py-0.5 rounded text-[10px] font-mono" :class="anc.is_opening ? 'bg-slate-100 dark:bg-slate-800 text-slate-500' : 'bg-emerald-50 dark:bg-emerald-950/50 text-emerald-700 dark:text-emerald-300 font-bold'">
                      {{ anc.is_opening ? 'Opening' : 'Confirmed Checkpoint' }}
                    </span>
                    <span>{{ formatDate(anc.anchor_date) }}</span>
                  </div>
                  <div v-if="anc.notes" class="text-[11px] text-slate-400 mt-0.5">
                    "{{ anc.notes }}"
                  </div>
                </div>

                <div class="font-mono font-bold text-slate-900 dark:text-white">
                  {{ anc.formatted_balance }}
                </div>
              </div>
            </div>
          </div>

          <!-- Observational Reconciliation Snapshots Section -->
          <div class="space-y-2.5">
            <div class="flex items-center justify-between">
              <h4 class="text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300 flex items-center space-x-1.5">
                <span>⚖️</span>
                <span>Observational Reconciliation Snapshots</span>
              </h4>
              <span class="text-[11px] text-slate-400">
                Audited checks comparing actual statement vs calculated ledger
              </span>
            </div>

            <div v-if="breakdown.snapshots.length === 0" class="p-4 rounded-xl border border-dashed border-slate-200 dark:border-slate-800 text-xs text-slate-400 text-center">
              No reconciliation snapshots recorded yet.
            </div>

            <div v-else class="border border-brand-border dark:border-brand-darkborder rounded-xl overflow-hidden divide-y divide-brand-border dark:divide-brand-darkborder">
              <div 
                v-for="snap in breakdown.snapshots" 
                :key="snap.id"
                class="p-3 flex items-center justify-between text-xs bg-white dark:bg-brand-darksurface"
              >
                <div>
                  <div class="font-semibold text-slate-900 dark:text-white flex items-center space-x-2">
                    <span>{{ formatDate(snap.snapshot_date) }}</span>
                    <span 
                      class="text-[10px] font-mono px-1.5 py-0.2 rounded font-semibold"
                      :class="snap.discrepancy_pence === 0 
                        ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300' 
                        : 'bg-amber-50 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300'">
                      {{ snap.discrepancy_pence === 0 ? 'Exact Match (0.00)' : `Discrepancy: ${snap.formatted_discrepancy}` }}
                    </span>
                  </div>
                  <div class="text-[11px] text-slate-400 flex items-center space-x-2 mt-0.5 font-mono">
                    <span>Statement: {{ snap.formatted_actual_balance }}</span>
                    <span>·</span>
                    <span>Calculated: {{ snap.formatted_calculated_balance }}</span>
                    <span v-if="snap.notes" class="font-sans italic">· "{{ snap.notes }}"</span>
                  </div>
                </div>

                <div 
                  class="font-mono font-bold text-xs"
                  :class="snap.discrepancy_pence === 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400'">
                  {{ snap.formatted_discrepancy }}
                </div>
              </div>
            </div>
          </div>

        </div>

      </div>

      <!-- Modal Footer -->
      <div class="px-6 py-4 border-t border-brand-border dark:border-brand-darkborder flex items-center justify-between shrink-0 bg-slate-50/50 dark:bg-slate-900/20">
        <button 
          v-if="breakdown && breakdown.account_type !== 'investment'"
          type="button" 
          @click="handleReconcile"
          class="px-4 py-2 rounded-full border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 transition shadow-xs flex items-center space-x-1.5">
          <span>⚖️</span>
          <span>Reconcile Balance</span>
        </button>
        <div v-else></div>

        <button 
          type="button" 
          @click="handleClose"
          class="px-5 py-2 rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 text-xs font-semibold hover:opacity-90 transition">
          Close
        </button>
      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { api } from '../api/client';
import type { Account, AccountBreakdownResponse } from '../types';

const props = defineProps<{
  isOpen: boolean;
  accountId: number | null;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'edit', account: Account): void;
  (e: 'reconcile', account: Account): void;
}>();

const isLoading = ref(false);
const errorMessage = ref<string | null>(null);
const breakdown = ref<AccountBreakdownResponse | null>(null);
const activeTab = ref<'activity' | 'history'>('activity');

watch([() => props.isOpen, () => props.accountId], ([open, id]) => {
  if (open && id) {
    loadBreakdown();
  } else {
    breakdown.value = null;
    errorMessage.value = null;
  }
}, { immediate: true });

async function loadBreakdown() {
  if (!props.accountId) return;
  isLoading.value = true;
  errorMessage.value = null;

  try {
    breakdown.value = await api.getAccountBreakdown(props.accountId);
  } catch (err: any) {
    errorMessage.value = err.message || 'Failed to load account breakdown.';
  } finally {
    isLoading.value = false;
  }
}

function handleClose() {
  emit('close');
}

function handleEdit() {
  if (!breakdown.value) return;
  // Construct a minimal Account object to pass to edit modal
  const acc: any = {
    id: breakdown.value.account_id,
    name: breakdown.value.account_name,
    account_type: breakdown.value.account_type,
    currency: breakdown.value.currency,
    color: breakdown.value.color,
    is_active: breakdown.value.is_active,
    starting_balance_pence: breakdown.value.starting_balance_pence,
    formatted_balance: breakdown.value.formatted_current_balance,
    current_balance_pence: breakdown.value.current_balance_pence,
    valuation_mode: breakdown.value.investment?.valuation_mode || 'snapshot'
  };
  emit('edit', acc);
}

function handleReconcile() {
  if (!breakdown.value) return;
  const acc: any = {
    id: breakdown.value.account_id,
    name: breakdown.value.account_name,
    account_type: breakdown.value.account_type,
    currency: breakdown.value.currency,
    color: breakdown.value.color,
    is_active: breakdown.value.is_active,
    starting_balance_pence: breakdown.value.starting_balance_pence,
    formatted_balance: breakdown.value.formatted_current_balance,
    current_balance_pence: breakdown.value.current_balance_pence
  };
  emit('reconcile', acc);
}

function getGroupBadgeClass(group: string): string {
  switch (group) {
    case 'Depository Accounts':
      return 'bg-blue-50 dark:bg-blue-950/60 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-900/40';
    case 'Cash Accounts':
      return 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-900/40';
    case 'Credit Liabilities':
      return 'bg-rose-50 dark:bg-rose-950/60 text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-900/40';
    case 'Investment Portfolios':
      return 'bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-900/40';
    default:
      return 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300';
  }
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' });
  } catch {
    return String(iso);
  }
}
</script>

