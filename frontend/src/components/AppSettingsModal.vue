<template>
  <div 
    v-if="isOpen" 
    class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4 backdrop-blur-sm overflow-y-auto" 
    @click.self="$emit('close')">
    <section 
      role="dialog" 
      aria-modal="true" 
      aria-labelledby="settings-title" 
      class="w-full max-w-xl space-y-5 rounded-2xl border border-brand-border bg-white p-6 shadow-2xl dark:border-brand-darkborder dark:bg-brand-darksurface my-8 transition-all">
      
      <!-- Modal Header -->
      <div class="flex items-center justify-between border-b border-brand-border pb-3 dark:border-brand-darkborder">
        <div>
          <h2 id="settings-title" class="font-bold text-slate-900 dark:text-white">Settings</h2>
          <p class="mt-0.5 text-xs text-slate-500 dark:text-slate-400">Configure preferences, appearance, and backup automation.</p>
        </div>
        <button 
          @click="$emit('close')" 
          class="text-xl text-slate-400 hover:text-slate-700 dark:hover:text-white transition" 
          aria-label="Close settings">
          &times;
        </button>
      </div>

      <!-- Settings Tabs -->
      <div class="flex rounded-xl bg-slate-100 p-1 border border-brand-border dark:border-brand-darkborder dark:bg-slate-800/80">
        <button
          type="button"
          @click="activeTab = 'general'"
          class="flex-1 py-1.5 text-xs font-semibold rounded-lg transition"
          :class="activeTab === 'general'
            ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm'
            : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'">
          General & Appearance
        </button>
        <button
          type="button"
          @click="activeTab = 'backups'"
          class="flex-1 py-1.5 text-xs font-semibold rounded-lg transition flex items-center justify-center space-x-1.5"
          :class="activeTab === 'backups'
            ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm'
            : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'">
          <span>Backups & Data Safety</span>
          <span 
            v-if="systemStore.settings?.is_backup_overdue && !systemStore.settings?.backup_automation_enabled" 
            class="w-2 h-2 rounded-full bg-amber-500" 
            title="Backup recommended">
          </span>
        </button>
      </div>

      <!-- Tab 1: General & Appearance -->
      <div v-if="activeTab === 'general'" class="space-y-5">
        <!-- App Title Autosave Field -->
        <div class="p-3.5 rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50/60 dark:bg-slate-800/40">
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
            <div class="flex items-center space-x-2 shrink-0">
              <label for="app-name" class="text-xs font-bold text-slate-900 dark:text-white">
                App Title
              </label>
              <span 
                v-if="titleStatus === 'saved'" 
                class="text-[10px] font-mono font-semibold text-emerald-600 dark:text-emerald-400 animate-fadeIn">
                ✓ Saved
              </span>
              <span 
                v-else-if="titleStatus === 'saving'" 
                class="text-[10px] font-mono text-slate-400 animate-pulse">
                Saving...
              </span>
            </div>
            <input 
              id="app-name" 
              v-model="name" 
              @input="onTitleInput"
              @blur="onTitleBlur"
              maxlength="40" 
              placeholder="Finance Hub"
              class="w-full sm:max-w-xs rounded-xl border border-brand-border bg-white px-3 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-slate-400 dark:border-brand-darkborder dark:bg-slate-800 dark:text-white transition" />
          </div>
        </div>

        <!-- Display & Privacy Preferences -->
        <div class="space-y-3 pt-3 border-t border-brand-border dark:border-brand-darkborder">
          <h3 class="font-mono text-xs uppercase tracking-wider font-bold text-slate-500 dark:text-slate-400">
            Appearance & Privacy
          </h3>

          <!-- Theme: Two-Option Segmented Control -->
          <div class="p-3.5 rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50/60 dark:bg-slate-800/40 space-y-2.5">
            <div>
              <span class="text-xs font-bold text-slate-900 dark:text-white">Interface Theme</span>
              <p class="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                Select your preferred color scheme across all views.
              </p>
            </div>

            <!-- Segmented Control with clear highlighting -->
            <div 
              role="radiogroup" 
              aria-label="Interface theme" 
              class="flex rounded-xl bg-slate-200/80 dark:bg-slate-900/80 p-1 border border-brand-border dark:border-brand-darkborder">
              <button
                type="button"
                role="radio"
                :aria-checked="!themeStore.isDark"
                @click="themeStore.setTheme(false)"
                class="flex-1 py-1.5 px-3 text-xs font-bold rounded-lg transition-all flex items-center justify-center space-x-1.5 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                :class="!themeStore.isDark
                  ? 'bg-white text-slate-900 shadow-sm border border-black/5 dark:bg-slate-700 dark:text-white'
                  : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'">
                <span class="text-sm">☀️</span>
                <span>Light mode</span>
              </button>

              <button
                type="button"
                role="radio"
                :aria-checked="themeStore.isDark"
                @click="themeStore.setTheme(true)"
                class="flex-1 py-1.5 px-3 text-xs font-bold rounded-lg transition-all flex items-center justify-center space-x-1.5 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                :class="themeStore.isDark
                  ? 'bg-slate-900 text-white shadow-sm border border-white/10 dark:bg-slate-700 dark:text-white'
                  : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'">
                <span class="text-sm">🌙</span>
                <span>Dark mode</span>
              </button>
            </div>
          </div>

          <!-- Stealth Mode (Fully Clickable Card) -->
          <div 
            role="button"
            tabindex="0"
            @click="stealthStore.toggleStealth()"
            @keydown.enter.prevent="stealthStore.toggleStealth()"
            @keydown.space.prevent="stealthStore.toggleStealth()"
            class="flex items-center justify-between p-3.5 rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50/60 dark:bg-slate-800/40 hover:bg-slate-100/80 dark:hover:bg-slate-800/80 cursor-pointer transition focus:outline-none focus:ring-2 focus:ring-emerald-500"
            :class="{'border-emerald-300 dark:border-emerald-700 bg-emerald-50/20': stealthStore.isStealth}">
            <div class="pr-2">
              <div class="flex items-center space-x-2">
                <span 
                  class="w-2 h-2 rounded-full" 
                  :class="stealthStore.isStealth ? 'bg-emerald-500 animate-pulse' : 'bg-slate-400'">
                </span>
                <span class="text-xs font-bold text-slate-900 dark:text-white">Stealth Mode</span>
              </div>
              <p class="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                Blurs account balances and transaction values across the interface to protect privacy.
              </p>
            </div>
            <div 
              class="px-3.5 py-1.5 text-xs font-semibold rounded-full border border-brand-border dark:border-brand-darkborder transition shadow-xs shrink-0 select-none pointer-events-none"
              :class="stealthStore.isStealth 
                ? 'bg-emerald-50 border-emerald-300 text-emerald-800 dark:bg-emerald-950 dark:border-emerald-700 dark:text-emerald-300 font-bold' 
                : 'bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-200'">
              {{ stealthStore.isStealth ? 'Enabled' : 'Disabled' }}
            </div>
          </div>

          <!-- Header Date & Time (Fully Clickable Card) -->
          <div 
            role="button"
            tabindex="0"
            @click="toggleDateTimeDisplay"
            @keydown.enter.prevent="toggleDateTimeDisplay"
            @keydown.space.prevent="toggleDateTimeDisplay"
            class="flex items-center justify-between p-3.5 rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50/60 dark:bg-slate-800/40 hover:bg-slate-100/80 dark:hover:bg-slate-800/80 cursor-pointer transition focus:outline-none focus:ring-2 focus:ring-emerald-500"
            :class="{'border-emerald-300 dark:border-emerald-700 bg-emerald-50/20': showDateTime}">
            <div class="pr-2">
              <div class="flex items-center space-x-2">
                <span class="text-base">🕒</span>
                <span class="text-xs font-bold text-slate-900 dark:text-white">Header Date & Time</span>
              </div>
              <p class="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                Display live date and time in the header on widescreen viewports.
              </p>
            </div>
            <div 
              class="px-3.5 py-1.5 text-xs font-semibold rounded-full border border-brand-border dark:border-brand-darkborder transition shadow-xs shrink-0 select-none pointer-events-none"
              :class="showDateTime 
                ? 'bg-emerald-50 border-emerald-300 text-emerald-800 dark:bg-emerald-950 dark:border-emerald-700 dark:text-emerald-300 font-bold' 
                : 'bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-200'">
              {{ showDateTime ? 'Shown' : 'Hidden' }}
            </div>
          </div>
        </div>

        <!-- Import Suggestions & Matching Preferences (Per-Workspace) -->
        <div class="space-y-3 pt-3 border-t border-brand-border dark:border-brand-darkborder">
          <div class="flex items-center justify-between">
            <div>
              <div class="flex items-center space-x-2">
                <h3 class="font-mono text-xs uppercase tracking-wider font-bold text-slate-500 dark:text-slate-400">
                  Import Suggestions & Matching
                </h3>
                <span 
                  v-if="confidenceStatus === 'saved'" 
                  class="text-[10px] font-mono font-semibold text-emerald-600 dark:text-emerald-400 animate-fadeIn">
                  ✓ Saved
                </span>
                <span 
                  v-else-if="confidenceStatus === 'saving'" 
                  class="text-[10px] font-mono text-slate-400 animate-pulse">
                  Saving...
                </span>
              </div>
              <p class="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                Configure how confident the offline engine must be before pre-filling categories and accounts.
              </p>
            </div>
            <span class="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-500 shrink-0">
              Workspace-Scoped
            </span>
          </div>

          <!-- Category Matching Threshold -->
          <div class="p-3.5 rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50/60 dark:bg-slate-800/40 space-y-2.5">
            <div class="flex items-center justify-between">
              <div>
                <span class="text-xs font-bold text-slate-900 dark:text-white">Category Matching</span>
                <p class="text-[11px] text-slate-500 dark:text-slate-400">
                  Control how strictly receipt evidence and past history are matched to categories.
                </p>
              </div>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-3 gap-2">
              <button
                type="button"
                @click="setCategoryConfidence('cautious')"
                class="p-2.5 rounded-xl border text-left transition flex flex-col justify-between"
                :class="categoryConfidence === 'cautious' 
                  ? 'border-indigo-600 bg-indigo-50/70 dark:bg-indigo-950/40 text-indigo-950 dark:text-indigo-200 shadow-xs' 
                  : 'border-brand-border dark:border-brand-darkborder bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:border-slate-400'">
                <div class="flex items-center justify-between w-full mb-1">
                  <span class="text-xs font-bold">Very cautious</span>
                  <span v-if="categoryConfidence === 'cautious'" class="text-indigo-600 text-xs font-bold">✓</span>
                </div>
                <p class="text-[10px] text-slate-500 dark:text-slate-400 leading-tight">
                  Prefill only high-confidence matches from past history or exact names.
                </p>
              </button>

              <button
                type="button"
                @click="setCategoryConfidence('balanced')"
                class="p-2.5 rounded-xl border text-left transition flex flex-col justify-between"
                :class="categoryConfidence === 'balanced' 
                  ? 'border-indigo-600 bg-indigo-50/70 dark:bg-indigo-950/40 text-indigo-950 dark:text-indigo-200 shadow-xs' 
                  : 'border-brand-border dark:border-brand-darkborder bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:border-slate-400'">
                <div class="flex items-center justify-between w-full mb-1">
                  <span class="text-xs font-bold">Balanced</span>
                  <span v-if="categoryConfidence === 'balanced'" class="text-indigo-600 text-xs font-bold">✓</span>
                </div>
                <p class="text-[10px] text-slate-500 dark:text-slate-400 leading-tight">
                  Use clear, reasonably strong matches from history and receipt context.
                </p>
              </button>

              <button
                type="button"
                @click="setCategoryConfidence('permissive')"
                class="p-2.5 rounded-xl border text-left transition flex flex-col justify-between"
                :class="categoryConfidence === 'permissive' 
                  ? 'border-indigo-600 bg-indigo-50/70 dark:bg-indigo-950/40 text-indigo-950 dark:text-indigo-200 shadow-xs' 
                  : 'border-brand-border dark:border-brand-darkborder bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:border-slate-400'">
                <div class="flex items-center justify-between w-full mb-1">
                  <span class="text-xs font-bold">More suggestions</span>
                  <span v-if="categoryConfidence === 'permissive'" class="text-indigo-600 text-xs font-bold">✓</span>
                </div>
                <p class="text-[10px] text-slate-500 dark:text-slate-400 leading-tight">
                  Allow weaker semantic matches, clearly marked for manual review.
                </p>
              </button>
            </div>
          </div>

          <!-- Account Matching Threshold -->
          <div class="p-3.5 rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50/60 dark:bg-slate-800/40 space-y-2.5">
            <div class="flex items-center justify-between">
              <div>
                <span class="text-xs font-bold text-slate-900 dark:text-white">Account Matching</span>
                <p class="text-[11px] text-slate-500 dark:text-slate-400">
                  Control how strictly card clues and account names are matched to accounts.
                </p>
              </div>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-3 gap-2">
              <button
                type="button"
                @click="setAccountConfidence('cautious')"
                class="p-2.5 rounded-xl border text-left transition flex flex-col justify-between"
                :class="accountConfidence === 'cautious' 
                  ? 'border-indigo-600 bg-indigo-50/70 dark:bg-indigo-950/40 text-indigo-950 dark:text-indigo-200 shadow-xs' 
                  : 'border-brand-border dark:border-brand-darkborder bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:border-slate-400'">
                <div class="flex items-center justify-between w-full mb-1">
                  <span class="text-xs font-bold">Very cautious</span>
                  <span v-if="accountConfidence === 'cautious'" class="text-indigo-600 text-xs font-bold">✓</span>
                </div>
                <p class="text-[10px] text-slate-500 dark:text-slate-400 leading-tight">
                  Prefill only confirmed associations or exact card last-4 digits.
                </p>
              </button>

              <button
                type="button"
                @click="setAccountConfidence('balanced')"
                class="p-2.5 rounded-xl border text-left transition flex flex-col justify-between"
                :class="accountConfidence === 'balanced' 
                  ? 'border-indigo-600 bg-indigo-50/70 dark:bg-indigo-950/40 text-indigo-950 dark:text-indigo-200 shadow-xs' 
                  : 'border-brand-border dark:border-brand-darkborder bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:border-slate-400'">
                <div class="flex items-center justify-between w-full mb-1">
                  <span class="text-xs font-bold">Balanced</span>
                  <span v-if="accountConfidence === 'balanced'" class="text-indigo-600 text-xs font-bold">✓</span>
                </div>
                <p class="text-[10px] text-slate-500 dark:text-slate-400 leading-tight">
                  Use clear card evidence and strong distinctive token overlap.
                </p>
              </button>

              <button
                type="button"
                @click="setAccountConfidence('permissive')"
                class="p-2.5 rounded-xl border text-left transition flex flex-col justify-between"
                :class="accountConfidence === 'permissive' 
                  ? 'border-indigo-600 bg-indigo-50/70 dark:bg-indigo-950/40 text-indigo-950 dark:text-indigo-200 shadow-xs' 
                  : 'border-brand-border dark:border-brand-darkborder bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:border-slate-400'">
                <div class="flex items-center justify-between w-full mb-1">
                  <span class="text-xs font-bold">More suggestions</span>
                  <span v-if="accountConfidence === 'permissive'" class="text-indigo-600 text-xs font-bold">✓</span>
                </div>
                <p class="text-[10px] text-slate-500 dark:text-slate-400 leading-tight">
                  Suggest accounts with broader token overlap, clearly marked for review.
                </p>
              </button>
            </div>
          </div>
        </div>

        <!-- Financial Workspaces Management (Fully Clickable Card) -->
        <div class="space-y-3 pt-3 border-t border-brand-border dark:border-brand-darkborder">
          <div class="flex items-center justify-between">
            <h3 class="font-mono text-xs uppercase tracking-wider font-bold text-slate-500 dark:text-slate-400">
              Financial Workspace
            </h3>
            <span class="text-[11px] text-slate-400">
              Active: <strong class="text-slate-800 dark:text-slate-200">{{ profilesStore.activeProfile?.name || 'Default' }}</strong>
            </span>
          </div>

          <div 
            role="button"
            tabindex="0"
            @click="handleOpenProfiles"
            @keydown.enter.prevent="handleOpenProfiles"
            @keydown.space.prevent="handleOpenProfiles"
            class="p-3.5 rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50/60 dark:bg-slate-800/40 hover:bg-slate-100/80 dark:hover:bg-slate-800/80 cursor-pointer transition flex items-center justify-between gap-3 focus:outline-none focus:ring-2 focus:ring-indigo-500 group">
            <div class="min-w-0 pr-2">
              <div class="flex items-center space-x-2">
                <span class="text-base">📁</span>
                <span class="text-xs font-bold text-slate-900 dark:text-white group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">
                  Manage Financial Workspaces
                </span>
                <span class="px-2 py-0.5 rounded-full text-[10px] font-mono bg-indigo-100 dark:bg-indigo-950/80 text-indigo-700 dark:text-indigo-300 font-bold">
                  {{ profilesStore.profiles.length }} available
                </span>
              </div>
              <p class="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                Switch workspaces, create new isolated databases, rename profiles, or archive old ledgers.
              </p>
            </div>
            <div 
              class="px-3.5 py-1.5 text-xs font-semibold rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 transition shadow-xs shrink-0 flex items-center space-x-1 select-none pointer-events-none">
              <span>Workspaces</span>
              <span>&rarr;</span>
            </div>
          </div>
        </div>

        <!-- Accounts & Categories Management (Fully Clickable Card) -->
        <div class="space-y-3 pt-3 border-t border-brand-border dark:border-brand-darkborder">
          <h3 class="font-mono text-xs uppercase tracking-wider font-bold text-slate-500 dark:text-slate-400">
            Accounts & Categories
          </h3>

          <div 
            role="button"
            tabindex="0"
            @click="handleOpenManage"
            @keydown.enter.prevent="handleOpenManage"
            @keydown.space.prevent="handleOpenManage"
            class="p-3.5 rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50/60 dark:bg-slate-800/40 hover:bg-slate-100/80 dark:hover:bg-slate-800/80 cursor-pointer transition flex items-center justify-between gap-3 focus:outline-none focus:ring-2 focus:ring-emerald-500 group">
            <div class="min-w-0 pr-2">
              <div class="flex items-center space-x-2">
                <span class="text-base">💳</span>
                <span class="text-xs font-bold text-slate-900 dark:text-white group-hover:text-emerald-600 dark:group-hover:text-emerald-400 transition-colors">
                  Manage Accounts & Categories
                </span>
              </div>
              <p class="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                View, create, edit, archive, and delete bank accounts, credit cards, investment portfolios, and expense categories.
              </p>
            </div>
            <div 
              class="px-3.5 py-1.5 text-xs font-semibold rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 transition shadow-xs shrink-0 flex items-center space-x-1 select-none pointer-events-none">
              <span>Open Management</span>
              <span>&rarr;</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Tab 2: Backups & Data Safety -->
      <div v-else-if="activeTab === 'backups'" class="space-y-4 max-h-[60vh] overflow-y-auto pr-1">
        
        <!-- Overdue Reminder Banner (When Automation is OFF) -->
        <div 
          v-if="systemStore.settings?.is_backup_overdue && !systemStore.settings?.backup_automation_enabled"
          class="p-3 rounded-xl border border-amber-300 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/40 text-amber-900 dark:text-amber-200 text-xs flex items-start justify-between gap-3">
          <div>
            <span class="font-bold block mb-0.5">⚠️ Backup Recommended</span>
            <p class="text-[11px] text-amber-800 dark:text-amber-300">
              {{ systemStore.settings?.overdue_message || 'Your last backup was created over 30 days ago.' }}
            </p>
          </div>
          <button 
            @click="handleCreateBackup"
            :disabled="systemStore.creatingBackup"
            class="shrink-0 px-3 py-1 rounded-full bg-amber-600 text-white font-semibold text-[11px] hover:bg-amber-700 transition disabled:opacity-50">
            {{ systemStore.creatingBackup ? 'Creating...' : 'Backup Now' }}
          </button>
        </div>

        <!-- Success/Error Banners for Backups -->
        <div 
          v-if="systemStore.successMessage" 
          class="p-3 rounded-xl border border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-950/40 text-emerald-800 dark:text-emerald-300 text-xs flex items-center justify-between">
          <span>{{ systemStore.successMessage }}</span>
          <button @click="systemStore.successMessage = null" class="text-emerald-600 text-base leading-none">&times;</button>
        </div>

        <div 
          v-if="systemStore.error" 
          class="p-3 rounded-xl border border-rose-200 dark:border-rose-900 bg-rose-50 dark:bg-rose-950/40 text-rose-600 dark:text-rose-400 text-xs flex items-center justify-between">
          <span>{{ systemStore.error }}</span>
          <button @click="systemStore.error = null" class="text-rose-600 text-base leading-none">&times;</button>
        </div>

        <!-- Card: On-Demand Backup Creation -->
        <div class="p-4 rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50 dark:bg-slate-800/40 space-y-3">
          <div class="flex items-center justify-between">
            <div>
              <h3 class="text-xs font-bold text-slate-900 dark:text-white">Create On-Demand Backup</h3>
              <p class="text-[11px] text-slate-500 dark:text-slate-400">
                Generates a clean SQLite backup archive with all receipts, statements, and attachments into data/backups/.
              </p>
            </div>
            <button 
              @click="handleCreateBackup"
              :disabled="systemStore.creatingBackup"
              class="px-4 py-1.5 rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 text-xs font-semibold hover:opacity-90 transition disabled:opacity-50 flex items-center space-x-1 shrink-0">
              <span v-if="systemStore.creatingBackup" class="animate-spin w-3 h-3 border-2 border-slate-500 border-t-transparent rounded-full"></span>
              <span>{{ systemStore.creatingBackup ? 'Creating...' : '+ Create Backup' }}</span>
            </button>
          </div>

          <div v-if="systemStore.settings?.last_successful_backup_at" class="text-[10px] text-slate-400 font-mono">
            Last backup created on: {{ formatDate(systemStore.settings.last_successful_backup_at) }}
          </div>
        </div>

        <!-- Card: Backup Automation & Schedule -->
        <div class="p-4 rounded-xl border border-brand-border dark:border-brand-darkborder bg-slate-50 dark:bg-slate-800/40 space-y-3">
          <div class="flex items-center justify-between">
            <div>
              <h3 class="text-xs font-bold text-slate-900 dark:text-white">Scheduled Backup Automation</h3>
              <p class="text-[11px] text-slate-500 dark:text-slate-400">
                Automatically checks backup freshness when the server starts and at daily intervals.
              </p>
            </div>
            <button 
              @click="toggleAutomation"
              class="px-3 py-1 rounded-full text-xs font-semibold transition"
              :class="isAutomationEnabled 
                ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-800' 
                : 'bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300'">
              {{ isAutomationEnabled ? 'Enabled' : 'Disabled' }}
            </button>
          </div>

          <!-- Schedule cadence selection -->
          <div v-if="isAutomationEnabled" class="flex items-center justify-between pt-2 border-t border-brand-border dark:border-brand-darkborder">
            <label class="text-xs text-slate-600 dark:text-slate-300 font-medium">
              Backup Cadence
            </label>
            <select 
              v-model="frequencyDays" 
              @change="handleFrequencyChange"
              class="bg-white dark:bg-slate-700 border border-brand-border dark:border-brand-darkborder rounded-lg px-3 py-1.5 text-xs text-slate-900 dark:text-white focus:outline-none">
              <option :value="14">Bi-weekly (Every 14 days)</option>
              <option :value="30">Monthly (1 calendar month) — Default</option>
              <option :value="90">Quarterly (3 calendar months)</option>
            </select>
          </div>

          <p class="text-[10px] text-slate-400">
            Note: Checks are throttled to at most once every 24 hours. When automation is off, overdue checks show a reminder without writing automated files.
          </p>
        </div>

        <!-- Card: Dated Backup Archives List -->
        <div class="space-y-2">
          <div class="flex items-center justify-between">
            <h3 class="font-mono text-xs uppercase tracking-wider font-bold text-slate-500">
              Backup Archives ({{ systemStore.archives.length }})
            </h3>
            <button 
              @click="systemStore.loadArchives"
              class="text-[11px] text-slate-500 hover:text-slate-800 dark:hover:text-slate-200">
              Refresh
            </button>
          </div>

          <div v-if="systemStore.loading && systemStore.archives.length === 0" class="p-6 text-center text-xs text-slate-400 animate-pulse">
            Loading archives...
          </div>

          <div v-else-if="systemStore.archives.length === 0" class="p-6 rounded-xl border border-brand-border dark:border-brand-darkborder text-center text-xs text-slate-400">
            No backup archives found in data/backups/. Create one above to establish your recovery point.
          </div>

          <div v-else class="space-y-2">
            <div 
              v-for="arc in systemStore.archives" 
              :key="arc.filename"
              class="flex items-center justify-between p-3 rounded-xl border border-brand-border dark:border-brand-darkborder bg-white dark:bg-brand-darksurface hover:border-slate-300 dark:hover:border-slate-700 transition">
              <div class="min-w-0 pr-2">
                <div class="flex items-center space-x-2">
                  <span class="text-xs font-bold text-slate-900 dark:text-white truncate">
                    {{ arc.filename }}
                  </span>
                  <span class="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 shrink-0 font-semibold">
                    {{ arc.size_formatted }}
                  </span>
                </div>
                <div class="flex items-center space-x-2 text-[10px] text-slate-400 font-mono mt-0.5">
                  <span>{{ formatDate(arc.created_at) }}</span>
                  <template v-if="arc.manifest">
                    <span>&bull;</span>
                    <span>{{ arc.manifest.counts.transactions }} txs</span>
                    <span>&bull;</span>
                    <span>{{ arc.manifest.counts.accounts }} accs</span>
                  </template>
                </div>
              </div>

              <a
                :href="api.getBackupDownloadUrl(arc.filename)"
                download
                class="px-3 py-1.5 rounded-full border border-brand-border dark:border-brand-darkborder hover:bg-slate-100 dark:hover:bg-slate-800 text-[11px] font-semibold text-slate-700 dark:text-slate-200 transition shrink-0 flex items-center space-x-1"
                title="Download portable ZIP archive">
                <span>Download</span>
                <span>&darr;</span>
              </a>
            </div>
          </div>
        </div>

        <!-- Offline Restore Documentation Box -->
        <div class="p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 text-[11px] text-slate-500 dark:text-slate-400 space-y-1.5">
          <span class="font-bold text-slate-700 dark:text-slate-300 block">Offline Database Restoration:</span>
          <p>
            To prevent database corruption, restoration is strictly an offline utility. Run the following command with the server stopped:
          </p>
          <code class="block font-mono text-[10px] bg-white dark:bg-slate-800 p-2 rounded border border-slate-200 dark:border-slate-700 text-slate-800 dark:text-slate-200">
            python -m app.restore data/backups/finance_hub_backup_YYYY-MM-DD_HHMMSS.zip
          </code>
          <p class="text-[10px]">
            The utility checks for active locks, creates an automatic pre-restore safety copy, verifies database integrity, and safely clears stale WAL journals before file replacement.
          </p>
        </div>

      </div>

      <!-- Modal Footer -->
      <div class="flex justify-end gap-2 border-t border-brand-border pt-4 dark:border-brand-darkborder">
        <button 
          @click="$emit('close')" 
          class="rounded-full border border-brand-border px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 dark:border-brand-darkborder dark:text-slate-300 dark:hover:bg-slate-800 transition">
          Close
        </button>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue';
import { useSystemStore } from '../stores/system';
import { useThemeStore } from '../stores/theme';
import { useStealthStore } from '../stores/stealth';
import { useProfilesStore } from '../stores/profiles';
import { api } from '../api/client';

const props = withDefaults(defineProps<{ 
  isOpen: boolean; 
  appName: string;
  showDateTime?: boolean;
}>(), {
  showDateTime: true
});

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'save', name: string): void;
  (e: 'open-manage'): void;
  (e: 'open-profiles'): void;
  (e: 'update:showDateTime', val: boolean): void;
}>();

const systemStore = useSystemStore();
const themeStore = useThemeStore();
const stealthStore = useStealthStore();
const profilesStore = useProfilesStore();

const activeTab = ref<'general' | 'backups'>('general');
const name = ref(props.appName);
const titleStatus = ref<'idle' | 'saving' | 'saved'>('idle');
let titleDebounceTimeout: any = null;

const isAutomationEnabled = ref(false);
const frequencyDays = ref(30);

const categoryConfidence = ref<'cautious' | 'balanced' | 'permissive'>('balanced');
const accountConfidence = ref<'cautious' | 'balanced' | 'permissive'>('balanced');
const confidenceStatus = ref<'idle' | 'saving' | 'saved'>('idle');

async function setCategoryConfidence(level: 'cautious' | 'balanced' | 'permissive') {
  categoryConfidence.value = level;
  confidenceStatus.value = 'saving';
  try {
    await systemStore.updateSettings({
      import_confidence_category: level,
      import_confidence_account: accountConfidence.value
    });
    confidenceStatus.value = 'saved';
    setTimeout(() => {
      if (confidenceStatus.value === 'saved') confidenceStatus.value = 'idle';
    }, 2000);
  } catch {
    confidenceStatus.value = 'idle';
  }
}

async function setAccountConfidence(level: 'cautious' | 'balanced' | 'permissive') {
  accountConfidence.value = level;
  confidenceStatus.value = 'saving';
  try {
    await systemStore.updateSettings({
      import_confidence_category: categoryConfidence.value,
      import_confidence_account: level
    });
    confidenceStatus.value = 'saved';
    setTimeout(() => {
      if (confidenceStatus.value === 'saved') confidenceStatus.value = 'idle';
    }, 2000);
  } catch {
    confidenceStatus.value = 'idle';
  }
}

function triggerTitleSave() {
  const trimmed = name.value.trim();
  if (!trimmed || trimmed === props.appName) {
    titleStatus.value = 'idle';
    return;
  }
  titleStatus.value = 'saving';
  emit('save', trimmed);
  setTimeout(() => {
    titleStatus.value = 'saved';
    setTimeout(() => {
      if (titleStatus.value === 'saved') {
        titleStatus.value = 'idle';
      }
    }, 2000);
  }, 200);
}

function onTitleInput() {
  titleStatus.value = 'saving';
  if (titleDebounceTimeout) clearTimeout(titleDebounceTimeout);
  titleDebounceTimeout = setTimeout(() => {
    triggerTitleSave();
  }, 600);
}

function onTitleBlur() {
  if (titleDebounceTimeout) clearTimeout(titleDebounceTimeout);
  triggerTitleSave();
}

function toggleDateTimeDisplay() {
  emit('update:showDateTime', !props.showDateTime);
}

function handleOpenManage() {
  emit('open-manage');
}

function handleOpenProfiles() {
  emit('open-profiles');
}

watch(() => [props.isOpen, props.appName], () => { 
  name.value = props.appName;
  if (props.isOpen) {
    systemStore.loadBackupStatus().then(() => {
      if (systemStore.settings) {
        isAutomationEnabled.value = systemStore.settings.backup_automation_enabled;
        frequencyDays.value = systemStore.settings.backup_frequency_days || 30;
        categoryConfidence.value = systemStore.settings.import_confidence_category || 'balanced';
        accountConfidence.value = systemStore.settings.import_confidence_account || 'balanced';
      }
    });
    systemStore.loadArchives();
  }
});

onMounted(() => {
  systemStore.initSystem();
});

async function handleCreateBackup() {
  try {
    await systemStore.createBackup();
  } catch (err) {
    // Error is set in store
  }
}

async function toggleAutomation() {
  isAutomationEnabled.value = !isAutomationEnabled.value;
  await systemStore.updateSettings({
    backup_automation_enabled: isAutomationEnabled.value,
    backup_frequency_days: frequencyDays.value
  });
}

async function handleFrequencyChange() {
  await systemStore.updateSettings({
    backup_automation_enabled: isAutomationEnabled.value,
    backup_frequency_days: frequencyDays.value
  });
}

function formatDate(dateStr: string): string {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });
}
</script>
