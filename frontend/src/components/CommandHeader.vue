<template>
  <header class="relative border-b border-brand-border dark:border-brand-darkborder bg-brand-surface/90 dark:bg-brand-darksurface/90 backdrop-blur-md sticky top-0 z-40 transition-colors">
    <div class="max-w-7xl w-full mx-auto px-4 sm:px-6 min-h-16 flex items-center justify-between gap-2 sm:gap-4">
      
      <!-- Left: Logo & Navigation Tabs -->
      <div class="flex items-center space-x-3 sm:space-x-5 shrink-0">
        <router-link to="/" class="flex items-center space-x-2.5 shrink-0" aria-label="Go to Finance Hub home">
          <span class="w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-sm shadow-emerald-500/50"></span>
          <span class="max-w-36 sm:max-w-48 truncate font-mono text-xs uppercase tracking-widest font-bold text-slate-900 dark:text-white" :title="appName">
            {{ appName }}
          </span>
        </router-link>

        <span class="text-brand-border dark:text-brand-darkborder font-thin hidden sm:inline">|</span>

        <!-- Desktop Nav Tabs (Visible when space permits) -->
        <nav class="hidden md:flex items-center space-x-1.5 text-xs font-semibold whitespace-nowrap" aria-label="Main Navigation">
          <router-link 
            to="/" 
            class="px-3.5 py-1.5 rounded-full transition"
            :class="$route.path === '/' 
              ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-950 shadow-sm' 
              : 'text-brand-muted hover:text-slate-900 dark:text-brand-darkmuted dark:hover:text-white'">
            Home
          </router-link>
          
          <router-link 
            to="/portfolios" 
            class="px-3.5 py-1.5 rounded-full transition"
            :class="$route.path.startsWith('/portfolios')
              ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-950 shadow-sm' 
              : 'text-brand-muted hover:text-slate-900 dark:text-brand-darkmuted dark:hover:text-white'">
            Portfolios
          </router-link>
          <router-link 
            to="/analysis" 
            class="px-3.5 py-1.5 rounded-full transition"
            :class="$route.path.startsWith('/analysis') || $route.path.startsWith('/cashflow')
              ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-950 shadow-sm' 
              : 'text-brand-muted hover:text-slate-900 dark:text-brand-darkmuted dark:hover:text-white'">
            Analysis
          </router-link>
          <router-link 
            to="/ledger" 
            class="px-3.5 py-1.5 rounded-full transition"
            :class="$route.path === '/ledger' 
              ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-950 shadow-sm' 
              : 'text-brand-muted hover:text-slate-900 dark:text-brand-darkmuted dark:hover:text-white'">
            Ledger
          </router-link>
          <router-link 
            to="/queue" 
            class="px-3.5 py-1.5 rounded-full transition flex items-center space-x-1.5"
            :class="$route.path.startsWith('/queue') || $route.path.startsWith('/staging')
              ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-950 shadow-sm' 
              : 'text-brand-muted hover:text-slate-900 dark:text-brand-darkmuted dark:hover:text-white'">
            <span>Queue</span>
            <span 
              v-if="stagingStore.pendingCount > 0" 
              class="px-1.5 py-0.2 text-[10px] font-mono rounded-full font-bold"
              :class="$route.path.startsWith('/queue')
                ? 'bg-emerald-500 text-white' 
                : 'bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300'"
              :title="`${stagingStore.pendingCount} pending review item(s)`">
              {{ stagingStore.pendingCount }}
            </span>
            <span 
              v-if="stagingStore.suggestionsCount > 0" 
              class="px-1.5 py-0.2 text-[10px] font-mono rounded-full font-bold"
              :class="$route.path.startsWith('/queue')
                ? 'bg-indigo-500 text-white' 
                : 'bg-indigo-100 dark:bg-indigo-950 text-indigo-800 dark:text-indigo-300'"
              :title="`${stagingStore.suggestionsCount} advisory suggestion(s)`">
              💡 {{ stagingStore.suggestionsCount }}
            </span>
          </router-link>
          <router-link 
            to="/review" 
            class="px-3.5 py-1.5 rounded-full transition flex items-center space-x-1.5"
            :class="$route.path.startsWith('/review') || $route.path.startsWith('/data-quality')
              ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-950 shadow-sm' 
              : 'text-brand-muted hover:text-slate-900 dark:text-brand-darkmuted dark:hover:text-white'">
            <span>Review</span>
            <span 
              v-if="reviewStore.activeCount > 0" 
              data-testid="header-review-badge"
              class="px-1.5 py-0.2 text-[10px] font-mono rounded-full font-bold"
              :class="$route.path.startsWith('/review')
                ? 'bg-amber-500 text-white' 
                : 'bg-amber-100 dark:bg-amber-950 text-amber-800 dark:text-amber-300'"
              :title="`${reviewStore.activeCount} data quality / review item(s)`">
              {{ reviewStore.activeCount }}
            </span>
          </router-link>
        </nav>

        <!-- Mobile / Narrow Screen Navigation Dropdown -->
        <div class="relative md:hidden nav-dropdown-container">
          <button
            type="button"
            @click="isNavMenuOpen = !isNavMenuOpen"
            class="px-3 py-1.5 rounded-full border border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface text-xs font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition flex items-center space-x-1.5"
            :aria-expanded="isNavMenuOpen"
            aria-label="Toggle navigation menu">
            <span>{{ activeNavLabel }}</span>
            <span 
              v-if="stagingStore.pendingCount > 0" 
              class="px-1.5 py-0.2 text-[10px] font-mono rounded-full font-bold bg-emerald-500 text-white">
              {{ stagingStore.pendingCount }}
            </span>
            <span 
              v-if="stagingStore.suggestionsCount > 0" 
              class="px-1.5 py-0.2 text-[10px] font-mono rounded-full font-bold bg-indigo-500 text-white">
              💡 {{ stagingStore.suggestionsCount }}
            </span>
            <svg class="w-3.5 h-3.5 transition-transform" :class="{'rotate-180': isNavMenuOpen}" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
            </svg>
          </button>

          <!-- Nav Menu Dropdown -->
          <div 
            v-if="isNavMenuOpen" 
            class="absolute left-0 top-10 z-50 w-48 rounded-xl border border-brand-border dark:border-brand-darkborder bg-white dark:bg-brand-darksurface p-1.5 shadow-xl space-y-1">
            <router-link
              to="/"
              @click="isNavMenuOpen = false"
              class="flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-lg transition"
              :class="$route.path === '/' 
                ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-950' 
                : 'text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'">
              <span>Home</span>
            </router-link>

            <router-link
              to="/portfolios"
              @click="isNavMenuOpen = false"
              class="flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-lg transition"
              :class="$route.path.startsWith('/portfolios') 
                ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-950' 
                : 'text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'">
              <span>Portfolios</span>
            </router-link>

            <router-link
              to="/analysis"
              @click="isNavMenuOpen = false"
              class="flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-lg transition"
              :class="$route.path.startsWith('/analysis') || $route.path.startsWith('/cashflow') 
                ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-950' 
                : 'text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'">
              <span>Analysis</span>
            </router-link>

            <router-link
              to="/ledger"
              @click="isNavMenuOpen = false"
              class="flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-lg transition"
              :class="$route.path === '/ledger' 
                ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-950' 
                : 'text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'">
              <span>Ledger</span>
            </router-link>

            <router-link
              to="/queue"
              @click="isNavMenuOpen = false"
              class="flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-lg transition"
              :class="$route.path.startsWith('/queue') || $route.path.startsWith('/staging')
                ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-950' 
                : 'text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'">
              <span>Queue</span>
              <div class="flex items-center space-x-1">
                <span 
                  v-if="stagingStore.pendingCount > 0" 
                  class="px-1.5 py-0.2 text-[10px] font-mono rounded-full font-bold bg-emerald-500 text-white">
                  {{ stagingStore.pendingCount }}
                </span>
                <span 
                  v-if="stagingStore.suggestionsCount > 0" 
                  class="px-1.5 py-0.2 text-[10px] font-mono rounded-full font-bold bg-indigo-500 text-white">
                  💡 {{ stagingStore.suggestionsCount }}
                </span>
              </div>
            </router-link>

            <router-link
              to="/review"
              @click="isNavMenuOpen = false"
              class="flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-lg transition"
              :class="$route.path.startsWith('/review') || $route.path.startsWith('/data-quality')
                ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-950' 
                : 'text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'">
              <span>Review</span>
              <span 
                v-if="reviewStore.activeCount > 0" 
                class="px-1.5 py-0.2 text-[10px] font-mono rounded-full font-bold bg-amber-500 text-white">
                {{ reviewStore.activeCount }}
              </span>
            </router-link>
          </div>
        </div>
      </div>

      <!-- Right: Action Buttons, Help, Settings & Clock -->
      <div class="ml-auto flex items-center space-x-2 sm:space-x-3 shrink-0 whitespace-nowrap">
        
        <!-- Unified "+ Transaction" Chooser -->
        <div class="relative add-tx-container">
          <button 
            type="button"
            @click="isAddTxChooserOpen = !isAddTxChooserOpen" 
            class="text-xs font-semibold px-3.5 sm:px-4 py-1.5 rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 hover:opacity-90 transition shadow-sm flex items-center space-x-1.5 cursor-pointer"
            :aria-expanded="isAddTxChooserOpen"
            aria-haspopup="menu"
            title="Add transaction (E for manual, I for import)">
            <span>+ Transaction</span>
            <svg class="w-3.5 h-3.5 transition-transform" :class="{'rotate-180': isAddTxChooserOpen}" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
            </svg>
          </button>

          <!-- Chooser Menu -->
          <div 
            v-if="isAddTxChooserOpen" 
            class="absolute right-0 top-11 z-50 w-80 sm:w-88 max-w-[calc(100vw-1.5rem)] rounded-xl border border-brand-border dark:border-brand-darkborder bg-white dark:bg-brand-darksurface p-2 shadow-2xl space-y-1.5 animate-fadeIn whitespace-normal">
            <button
              type="button"
              @click="chooseAction('record')"
              class="w-full text-left p-3 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800/80 transition flex items-start space-x-3 group whitespace-normal">
              <div class="w-7 h-7 rounded-lg bg-emerald-100 dark:bg-emerald-950/80 text-emerald-700 dark:text-emerald-300 flex items-center justify-center shrink-0 text-sm font-bold mt-0.5">
                ✏️
              </div>
              <div class="flex-1 min-w-0">
                <div class="flex items-center justify-between gap-2">
                  <span class="text-xs font-bold text-slate-900 dark:text-white group-hover:text-emerald-600 dark:group-hover:text-emerald-400 break-words">
                    Enter manually
                  </span>
                  <kbd class="text-[10px] font-mono px-1.5 py-0.5 rounded border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-500 shrink-0">
                    E
                  </kbd>
                </div>
                <p class="text-[11px] text-slate-500 dark:text-slate-400 mt-1 leading-relaxed break-words whitespace-normal">
                  Record single transaction with merchant, amount, category and date.
                </p>
              </div>
            </button>

            <button
              type="button"
              @click="chooseAction('import')"
              class="w-full text-left p-3 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800/80 transition flex items-start space-x-3 group whitespace-normal">
              <div class="w-7 h-7 rounded-lg bg-indigo-100 dark:bg-indigo-950/80 text-indigo-700 dark:text-indigo-300 flex items-center justify-center shrink-0 text-sm font-bold mt-0.5">
                📥
              </div>
              <div class="flex-1 min-w-0">
                <div class="flex items-center justify-between gap-2">
                  <span class="text-xs font-bold text-slate-900 dark:text-white group-hover:text-indigo-600 dark:group-hover:text-indigo-400 break-words">
                    Import a file or screenshot
                  </span>
                  <kbd class="text-[10px] font-mono px-1.5 py-0.5 rounded border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-500 shrink-0">
                    I
                  </kbd>
                </div>
                <p class="text-[11px] text-slate-500 dark:text-slate-400 mt-1 leading-relaxed break-words whitespace-normal">
                  Upload receipts, CSV/Excel bank statements, or mobile screenshots.
                </p>
              </div>
            </button>
          </div>
        </div>

        <!-- Help Icon Button (Shortcuts) -->
        <div class="relative help-container">
          <button
            type="button"
            @click="isHelpOpen = !isHelpOpen"
            class="w-8 h-8 rounded-full border border-brand-border dark:border-brand-darkborder text-xs font-semibold text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center justify-center transition"
            :aria-expanded="isHelpOpen"
            aria-label="Keyboard shortcuts and help"
            title="Keyboard shortcuts and help">
            <span class="font-bold">?</span>
          </button>

          <!-- Shortcuts Popup -->
          <div 
            v-if="isHelpOpen" 
            class="absolute right-0 top-10 z-50 w-64 rounded-xl border border-brand-border dark:border-brand-darkborder bg-white dark:bg-brand-darksurface p-4 shadow-xl animate-fadeIn">
            <h2 class="mb-3 text-xs font-bold uppercase tracking-wide text-slate-700 dark:text-slate-200">
              Keyboard shortcuts
            </h2>
            <dl class="space-y-2 text-xs text-slate-600 dark:text-slate-300">
              <div class="flex justify-between"><dt>Add transaction manually</dt><dd><kbd class="px-1.5 py-0.5 rounded border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 font-mono text-[10px]">E</kbd></dd></div>
              <div class="flex justify-between"><dt>Import file or screenshot</dt><dd><kbd class="px-1.5 py-0.5 rounded border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 font-mono text-[10px]">I</kbd></dd></div>
              <div class="flex justify-between"><dt>Manage accounts & categories</dt><dd><kbd class="px-1.5 py-0.5 rounded border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 font-mono text-[10px]">N</kbd></dd></div>
              <div class="flex justify-between"><dt>Toggle Stealth</dt><dd><kbd class="px-1.5 py-0.5 rounded border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 font-mono text-[10px]">S</kbd></dd></div>
              <div class="flex justify-between"><dt>Toggle theme</dt><dd><kbd class="px-1.5 py-0.5 rounded border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 font-mono text-[10px]">T</kbd></dd></div>
              <div class="flex justify-between"><dt>Close active dialog</dt><dd><kbd class="px-1.5 py-0.5 rounded border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 font-mono text-[10px]">Esc</kbd></dd></div>
            </dl>
          </div>
        </div>

        <!-- Settings Icon Button (Gear) -->
        <button
          type="button"
          @click="$emit('open-settings')"
          class="relative w-8 h-8 rounded-full border border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface hover:bg-slate-100 dark:hover:bg-slate-800 transition text-slate-700 dark:text-slate-300 flex items-center justify-center"
          aria-label="Application Settings"
          title="Settings">
          <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          <span 
            v-if="systemStore.settings?.is_backup_overdue && !systemStore.settings?.backup_automation_enabled"
            class="absolute top-1 right-1 w-2 h-2 rounded-full bg-amber-500 animate-pulse"
            title="Backup recommended">
          </span>
        </button>

        <!-- Date / Time Display (Rightmost) -->
        <div 
          v-if="showDateTime" 
          class="hidden xl:flex items-center text-[11px] font-mono text-brand-muted dark:text-brand-darkmuted px-3.5 py-1.5 rounded-full border border-brand-border dark:border-brand-darkborder bg-brand-surface dark:bg-brand-darksurface">
          {{ clockText }}
        </div>

      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useRoute } from 'vue-router';
import { useSystemStore } from '../stores/system';
import { useStagingStore } from '../stores/staging';
import { useReviewStore } from '../stores/review';

const emit = defineEmits<{
  (e: 'open-record-transaction'): void;
  (e: 'open-import'): void;
  (e: 'open-settings'): void;
}>();

withDefaults(defineProps<{ 
  appName: string;
  showDateTime?: boolean;
}>(), {
  showDateTime: true
});

const route = useRoute();
const systemStore = useSystemStore();
const stagingStore = useStagingStore();
const reviewStore = useReviewStore();

const isHelpOpen = ref(false);
const isAddTxChooserOpen = ref(false);
const isNavMenuOpen = ref(false);

const clockText = ref('--:--:--');
let clockInterval: any = null;

const activeNavLabel = computed(() => {
  const p = route.path;
  if (p === '/') return 'Home';
  if (p.startsWith('/portfolios')) return 'Portfolios';
  if (p.startsWith('/analysis') || p.startsWith('/cashflow')) return 'Analysis';
  if (p.startsWith('/ledger')) return 'Ledger';
  if (p.startsWith('/queue') || p.startsWith('/staging')) return 'Queue';
  if (p.startsWith('/review') || p.startsWith('/data-quality')) return 'Review';
  return 'Navigation';
});

function chooseAction(action: 'record' | 'import') {
  isAddTxChooserOpen.value = false;
  if (action === 'record') {
    emit('open-record-transaction');
  } else if (action === 'import') {
    emit('open-import');
  }
}

function handleDocumentClick(e: MouseEvent) {
  const target = e.target as HTMLElement;
  if (isHelpOpen.value && !target.closest('.help-container')) {
    isHelpOpen.value = false;
  }
  if (isAddTxChooserOpen.value && !target.closest('.add-tx-container')) {
    isAddTxChooserOpen.value = false;
  }
  if (isNavMenuOpen.value && !target.closest('.nav-dropdown-container')) {
    isNavMenuOpen.value = false;
  }
}

function updateClock() {
  const now = new Date();
  const days = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  clockText.value = `${days[now.getDay()]} ${now.getDate()} ${months[now.getMonth()]} at ` + now.toTimeString().split(' ')[0];
}

onMounted(() => {
  updateClock();
  clockInterval = setInterval(updateClock, 1000);
  window.addEventListener('click', handleDocumentClick);
  stagingStore.fetchCount();
  stagingStore.fetchSuggestions();
  reviewStore.loadFindings();
});

onUnmounted(() => {
  if (clockInterval) clearInterval(clockInterval);
  window.removeEventListener('click', handleDocumentClick);
});
</script>
