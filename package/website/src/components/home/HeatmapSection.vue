<template>
  <div class="w-full">
    <!-- Header -->
    <div class="flex justify-between items-center mb-5">
      <div class="flex items-baseline gap-2">
        <span class="text-gray-600 dark:text-gray-300 text-sm">{{ selectedYear ? `在 ${selectedYear} 年` : '过去一年' }}共拍摄</span>
        <span class="text-2xl font-bold text-gray-800 dark:text-gray-100">{{ data?.total_photos || 0 }}</span>
        <span class="text-gray-600 dark:text-gray-300 text-sm">张照片</span>
      </div>
      <div class="flex items-center gap-4 text-sm text-gray-500">
        <span class="hidden sm:inline">累计拍摄天数: <span class="font-medium text-gray-700 dark:text-gray-200">{{ data?.total_days || 0 }}</span></span>
        <span class="hidden sm:inline">连续拍摄: <span class="font-medium text-gray-700 dark:text-gray-200">{{ data?.max_consecutive_days || 0 }}</span></span>
        <el-select v-model="selectedYear" size="default" class="w-28 ml-2" @change="fetchData" placeholder="过去一年">
          <el-option label="过去一年" :value="undefined" />
          <el-option v-for="year in availableYears" :key="year" :label="`${year}年`" :value="year" />
        </el-select>
      </div>
    </div>
    
    <div class="flex sm:hidden items-center gap-4 text-xs text-gray-500 mb-4">
      <span>累计拍摄天数: {{ data?.total_days || 0 }}</span>
      <span>连续拍摄: {{ data?.max_consecutive_days || 0 }}</span>
    </div>

    <!-- Heatmap Grid -->
    <div class="overflow-x-auto pb-6 scrollbar-thin scrollbar-thumb-gray-200 dark:scrollbar-thumb-gray-700" ref="scrollContainer">
      <div class="flex gap-[2px] sm:gap-[3px] xl:gap-[4px] w-full min-w-[600px]">
        <div v-for="(col, colIndex) in gridColumns" :key="colIndex" class="flex-1 flex flex-col gap-[2px] sm:gap-[3px] xl:gap-[4px] relative">
           <template v-for="(day, rowIndex) in col" :key="`${colIndex}-${rowIndex}`">
              <el-tooltip
                v-if="day.count !== -1"
                :content="`${day.displayDate} 拍摄了 ${day.count} 张照片`"
                placement="top"
                effect="dark"
                :show-after="100"
              >
                <div class="w-full aspect-square rounded-[2px] sm:rounded-[3px] cursor-pointer hover:ring-1 hover:ring-gray-400 dark:hover:ring-gray-500 transition-all"
                     :class="getColorClass(day.count)">
                </div>
              </el-tooltip>
              <div v-else class="w-full aspect-square bg-transparent"></div>
           </template>
           
           <!-- Month labels -->
           <div v-if="monthLabelMap[colIndex]" class="absolute -bottom-5 left-0 text-[10px] sm:text-[12px] text-gray-400 whitespace-nowrap">
             {{ monthLabelMap[colIndex] }}
           </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, nextTick } from 'vue';
import { dashboardApi, HeatmapResponse } from '@/api/dashboard';
import { format, subDays, startOfYear, endOfYear, eachDayOfInterval, getDay } from 'date-fns';
import { ElMessage } from 'element-plus';

const selectedYear = ref<number | undefined>(undefined);
const data = ref<HeatmapResponse | null>(null);
const availableYears = ref<number[]>([]);
const scrollContainer = ref<HTMLElement | null>(null);

const gridColumns = ref<{date: string, displayDate: string, count: number}[][]>([]);
const monthLabels = ref<{text: string, index: number}[]>([]);

const monthLabelMap = computed(() => {
  const map: Record<number, string> = {};
  monthLabels.value.forEach(label => {
    map[label.index] = label.text;
  });
  return map;
});

const getColorClass = (count: number) => {
  if (count === -1) return 'bg-transparent';
  if (count === 0) return 'bg-[#ebedf0] dark:bg-[#161b22]';
  if (count < 5) return 'bg-[#9be9a8] dark:bg-[#0e4429]';
  if (count < 15) return 'bg-[#40c463] dark:bg-[#006d32]';
  if (count < 30) return 'bg-[#30a14e] dark:bg-[#26a641]';
  return 'bg-[#216e39] dark:bg-[#39d353]';
};

const buildGrid = (heatmapData: {date: string, count: number}[]) => {
  const dataMap = heatmapData.reduce((acc, item) => {
    acc[item.date] = item.count;
    return acc;
  }, {} as Record<string, number>);

  const today = new Date();
  let startDate: Date;
  let endDate: Date;

  if (selectedYear.value) {
    startDate = startOfYear(new Date(selectedYear.value, 0, 1));
    endDate = endOfYear(new Date(selectedYear.value, 0, 1));
  } else {
    endDate = today;
    startDate = subDays(today, 364);
  }

  const days = eachDayOfInterval({ start: startDate, end: endDate });
  const firstDayOfWeek = getDay(startDate);
  
  const paddedDays: (Date | null)[] = Array(firstDayOfWeek).fill(null).concat(days);
  
  const columns = [];
  const labels: {text: string, index: number}[] = [];
  let currentMonth = -1;

  for (let i = 0; i < paddedDays.length; i += 7) {
    const colDays = paddedDays.slice(i, i + 7);
    // Pad end if necessary
    while (colDays.length < 7) {
      colDays.push(null);
    }
    
    columns.push(colDays.map(date => {
      if (!date) return { date: '', displayDate: '', count: -1 };
      const dateStr = format(date, 'yyyy-MM-dd');
      const displayDateStr = format(date, 'yyyy年MM月dd日');
      return {
        date: dateStr,
        displayDate: displayDateStr,
        count: dataMap[dateStr] || 0
      };
    }));

    // Find the first valid day in this column to determine month
    const firstValidDay = colDays.find(d => d !== null);
    if (firstValidDay) {
      const month = firstValidDay.getMonth();
      if (month !== currentMonth) {
        labels.push({ text: `${month + 1}月`, index: columns.length - 1 });
        currentMonth = month;
      }
    }
  }
  
  gridColumns.value = columns;
  monthLabels.value = labels;
  
  // Scroll to end (right) when showing past year or current year
  if (!selectedYear.value || selectedYear.value === today.getFullYear()) {
    nextTick(() => {
      if (scrollContainer.value) {
        scrollContainer.value.scrollLeft = scrollContainer.value.scrollWidth;
      }
    });
  }
};

const fetchData = async () => {
  try {
    const res = await dashboardApi.getHeatmap(selectedYear.value || undefined);
    data.value = res;
    if (res.available_years) {
      availableYears.value = res.available_years;
    }
    buildGrid(res.data);
  } catch (error) {
    console.error('Failed to fetch heatmap data:', error);
    ElMessage.error('加载拍摄情况失败');
  }
};

onMounted(() => {
  fetchData();
});
</script>

<style scoped>
/* Tooltip styling if needed, but native title is usually fine for simple cases */
</style>
