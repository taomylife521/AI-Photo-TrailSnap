<template>
  <div class="relative pl-4 sm:pl-8 space-y-8">
    <div class="absolute left-4 sm:left-8 top-2 bottom-0 w-0.5 bg-slate-200 dark:bg-slate-700 -translate-x-1/2"></div>

    <div v-for="group in groupedTickets" :key="group.year" class="relative">
      
      <div class="sticky top-20 z-20 mb-6 -ml-10 sm:-ml-14 flex items-center">
        <div class="bg-primary-500 text-white text-sm font-bold px-3 py-1 rounded-full shadow-md border-2 border-white dark:border-slate-800">
          {{ group.year }}
        </div>
      </div>

      <div class="space-y-8">
        <div 
          v-for="(ticket, index) in group.tickets" 
          :key="ticket.id"
          class="relative group"
        >
          <div class="absolute left-0 sm:left-0 top-6 w-3 h-3 -ml-[1.6rem] sm:-ml-[2.1rem] rounded-full border-2 border-white dark:border-slate-800 z-10 transition-colors duration-300"
               :class="getDotColorClass(ticket.trainCode, ticket.type)">
          </div>

          <div class="absolute left-0 sm:left-0 top-[1.9rem] w-4 sm:w-6 -ml-[1.4rem] sm:-ml-[1.9rem] h-px bg-slate-200 dark:bg-slate-700"></div>

          <div class="pl-2 sm:pl-4 transition-transform duration-300 hover:translate-x-1">
            <div class="relative">
                <div class="text-xs font-semibold text-slate-400 mb-1 ml-1">
                   {{ formatDateShort(ticket.date) }} <span class="mx-1">·</span> {{ ticket.time }}
                </div>
                
                <TicketCard
                  :ticket="ticket"
                  :selected-ticket-ids="selectedTicketIds"
                  :current-theme="currentTheme"
                  @toggle-select="$emit('toggle-select', ticket.id)"
                  @edit="$emit('edit', ticket)"
                  @delete="$emit('delete', ticket.id)"
                  @view-paper="$emit('view-paper', ticket)"
                  @view-photo="$emit('view-photo', ticket)"
                />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { TicketFrontend } from '@/types/ticket';
import TicketCard from '@/components/TicketCard.vue';
import type { ThemeColor } from '@/composables/useTheme';

interface Props {
  tickets: TicketFrontend[];
  selectedTicketIds: (number | string)[];
  currentTheme: ThemeColor;
}

const props = defineProps<Props>();

const emit = defineEmits<{
  (e: 'toggle-select', id: number | string): void;
  (e: 'edit', ticket: TicketFrontend): void;
  (e: 'delete', id: number | string): void;
  (e: 'view-paper', ticket: TicketFrontend): void;
  (e: 'view-photo', ticket: TicketFrontend): void;
}>();

// --- 辅助逻辑 ---

// 1. 数据分组逻辑：按年份降序，组内按日期降序
const groupedTickets = computed(() => {
  const groups: Record<string, TicketFrontend[]> = {};
  
  // 分组
  props.tickets.forEach(ticket => {
    const year = ticket.date.split('-')[0]; // "2023-10-01" -> "2023"
    if (!groups[year]) {
      groups[year] = [];
    }
    groups[year].push(ticket);
  });

  // 排序年份
  const sortedYears = Object.keys(groups).sort((a, b) => Number(b) - Number(a));

  return sortedYears.map(year => ({
    year,
    tickets: groups[year] // 假设传入的 tickets 已经是排序好的，如果不是，这里需要再 sort 一次
  }));
});

// 2. 根据车次类型返回圆点颜色
const getDotColorClass = (code: string, type: 'train' | 'flight' = 'train') => {
  if (type === 'flight') {
      return 'bg-blue-500 shadow-[0_0_0_4px_rgba(59,130,246,0.2)]'; // 飞机色
  }
  const firstChar = code.charAt(0).toUpperCase();
  if (['G', 'D', 'C'].includes(firstChar)) {
    return 'bg-primary-500 shadow-[0_0_0_4px_rgba(var(--primary-rgb),0.2)]'; // 高铁色
  }
  return 'bg-slate-400 dark:bg-slate-500'; // 普速色
};

// 3. 格式化短日期 (10月01日)
const formatDateShort = (dateStr: string) => {
  const date = new Date(dateStr);
  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
};
</script>

<style scoped>
/* 可以添加一些进场动画 */
</style>