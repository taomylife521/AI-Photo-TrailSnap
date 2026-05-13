<template>
  <UnifiedPhotoPage
    :loading="photoStore.loading"
    :error="photoStore.error"
    :photos="images"
    :timeline-items="photoStore.timelineStats?.timeline || []"
    :timeline-stats="photoStore.timelineStats"
    :has-more="photoStore.hasMore"
    :allow-upload="false"
    :delete-label="'删除'"
    :confirm-remove="true"
    :show-back="false"
    :store="photoStore"
    @load-more="photoStore.loadPhotos"
    @retry="photoStore.loadPhotos(true)"
    @upload="triggerUpload"
    @confirm-delete="handleConfirmDelete"
    @photo-update="handlePhotoUpdate"
  >
    <!-- Header Controls (Filter Button) -->
    <template #header-controls-start>
      <button 
        ref="filterButtonRef"
        @click="showFilterPanel = !showFilterPanel"
        class="p-2 text-gray-700 dark:text-gray-200 bg-white/80 dark:bg-gray-900/80 backdrop-blur-md hover:bg-white dark:hover:bg-gray-900 rounded-full shadow-sm border border-gray-200/50 dark:border-gray-700/50 transition-all"
        :class="{ 'bg-primary-50 text-primary-500 border-primary-200': showFilterPanel }"
        title="筛选"
      >
        <Filter class="w-5 h-5" />
      </button>
    </template>

    <!-- Filter Panel -->
    <template #header-extension>
      <Transition
        enter-active-class="transition duration-200 ease-out"
        enter-from-class="transform -translate-y-2 opacity-0"
        enter-to-class="transform translate-y-0 opacity-100"
        leave-active-class="transition duration-150 ease-in"
        leave-from-class="transform translate-y-0 opacity-100"
        leave-to-class="transform -translate-y-2 opacity-0"
      >
          <div v-if="showFilterPanel" class="absolute left-0 right-0 top-full mt-2 pointer-events-none px-4">
            <div class="max-w-7xl mx-auto flex justify-end">
              <div ref="filterPanelRef" class="bg-white/95 dark:bg-gray-900/95 backdrop-blur-md rounded-2xl shadow-xl border border-gray-100 dark:border-gray-800 overflow-hidden w-full max-w-md pointer-events-auto">
                 <FilterPanel />
              </div>
            </div>
          </div>
      </Transition>
    </template>

    <!-- Upload Modal -->
    <template #extra-modals>
        <Transition name="slide-up">
          <div v-if="showUploadModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
            <div class="bg-white dark:bg-gray-900 rounded-xl shadow-xl w-full max-w-2xl overflow-hidden flex flex-col max-h-[90vh] animate-in zoom-in-95 duration-200">
              <div class="p-4 border-b border-gray-100 dark:border-gray-800 flex justify-between items-center">
                <h3 class="font-bold text-lg text-gray-900 dark:text-white">上传照片</h3>
                <button @click="showUploadModal = false" class="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full dark:bg-gray-800"><X class="w-5 h-5" /></button>
              </div>
              <div class="p-6 overflow-y-auto">
                <MultiFileUpload :albumId="undefined" @upload-complete="handleUploadComplete" />
              </div>
            </div>
          </div>
        </Transition>
    </template>

  </UnifiedPhotoPage>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useAlbumStore } from '@/stores/albumStore'
import { usePhotoStore } from '@/stores/photoStore'
import { Filter, X } from 'lucide-vue-next'
import { onClickOutside } from '@vueuse/core'
import UnifiedPhotoPage from '@/components/UnifiedPhotoPage.vue'
import MultiFileUpload from '@/components/MultiFileUpload.vue'
import FilterPanel from '@/components/FilterPanel.vue'
import { ElMessage } from 'element-plus'

const store = useAlbumStore()
const photoStore = usePhotoStore()

// State
const images = computed(() => photoStore.images)
const showUploadModal = ref(false)
const showFilterPanel = ref(false)
const filterButtonRef = ref<HTMLElement | null>(null)
const filterPanelRef = ref<HTMLElement | null>(null)

onClickOutside(filterPanelRef, () => {
  showFilterPanel.value = false
}, {
  ignore: [filterButtonRef]
})

// Methods
const handleUploadComplete = () => {
  showUploadModal.value = false
  photoStore.loadPhotos(true)
  photoStore.fetchTimelineStats()
}

const triggerUpload = () => {
  showUploadModal.value = true
}

const handleConfirmDelete = async (ids: string[], callback: (success: boolean) => void) => {
  try {
    await photoStore.deletePhotos(ids)
    callback(true)
    // Refresh photos after delete
    photoStore.loadPhotos(true)
  } catch (e) {
    console.error(e)
    ElMessage.error('删除失败')
    callback(false)
  }
}

const handlePhotoUpdate = (event: { id: string, location?: string, tags?: string[] }) => {
  console.log('Update photo:', event)
}

onMounted(() => {
  photoStore.resetAll()
  // Initial Load
  photoStore.fetchAvailableFilters()
  store.fetchAlbums()
  photoStore.fetchTimelineStats()
  photoStore.loadPhotos(true)
})

onUnmounted(() => {
  photoStore.resetAll()
})
</script>

<style scoped>
.slide-up-enter-active, .slide-up-leave-active { transition: all 0.3s ease; }
.slide-up-enter-from, .slide-up-leave-to { transform: translateY(20px); opacity: 0; }
</style>
