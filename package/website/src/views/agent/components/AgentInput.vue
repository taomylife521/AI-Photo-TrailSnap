<template>
  <div class="agent-chat-input-area">
    <div class="w-full max-w-4xl mx-auto">
      <form @submit.prevent="emit('send')" class="relative">
        <input
          :value="modelValue"
          @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
          type="text"
          placeholder="问问我关于您的照片或行程..."
          class="agent-input"
          :disabled="isLoading || isSelectionMode"
        />
        <button 
          type="submit" 
          class="agent-send-btn"
          :disabled="!modelValue.trim() || isLoading || isSelectionMode"
        >
          <Send class="w-4 h-4" />
        </button>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Send } from 'lucide-vue-next';

defineProps<{
  modelValue: string;
  isLoading: boolean;
  isSelectionMode: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void;
  (e: 'send'): void;
}>();
</script>

<style scoped>
.agent-chat-input-area {
  @apply p-4 bg-white dark:bg-slate-900 border-t border-slate-100 dark:border-slate-800;
}

.agent-input {
  @apply w-full pl-4 pr-12 py-3 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-sm text-slate-800 dark:text-white placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 transition-all disabled:opacity-50 disabled:cursor-not-allowed;
}

.agent-send-btn {
  @apply absolute right-2 top-1/2 -translate-y-1/2 p-2 bg-indigo-600 dark:bg-indigo-500 text-white rounded-lg hover:bg-indigo-700 dark:hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors;
}
</style>
