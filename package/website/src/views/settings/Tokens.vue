<template>
  <div class="">
    <div class="mb-4 md:mb-6 flex justify-between items-center">
      <h2 class="text-xl md:text-2xl font-bold text-gray-800 dark:text-white">令牌管理</h2>
      <el-button type="primary" @click="showCreateDialog = true">新增令牌</el-button>
    </div>

    <!-- Desktop View -->
    <div class="hidden md:block bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden">
      <el-table :data="tokens" style="width: 100%" v-loading="loading">
        <el-table-column prop="name" label="令牌名称" width="200" />
        <el-table-column label="令牌值" min-width="250">
          <template #default="{ row }">
            <div class="flex items-center gap-2">
              <span class="font-mono text-gray-500 dark:text-gray-400">
                {{ maskToken(row.token) }}
              </span>
              <el-button link type="primary" @click="copyToken(row.token)">
                <Copy class="w-4 h-4" />
              </el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="isExpired(row.expires_at) ? 'danger' : 'success'">
              {{ isExpired(row.expires_at) ? '已过期' : '有效' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="过期时间" width="180">
          <template #default="{ row }">
            {{ formatDate(row.expires_at) }}
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-popconfirm title="确定要删除这个令牌吗？删除后该令牌将失效！" @confirm="handleDelete(row.id)">
              <template #reference>
                <el-button type="danger" link>删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- Mobile View -->
    <div class="md:hidden space-y-4" v-loading="loading">
      <div v-if="tokens.length === 0 && !loading" class="text-center text-gray-500 py-8">
        暂无令牌数据
      </div>
      <div v-for="token in tokens" :key="token.id" class="bg-white dark:bg-gray-800 p-4 rounded-lg shadow space-y-3">
        <div class="flex justify-between items-start">
          <div class="font-bold text-gray-800 dark:text-white text-lg">{{ token.name }}</div>
          <el-tag :type="isExpired(token.expires_at) ? 'danger' : 'success'" size="small">
            {{ isExpired(token.expires_at) ? '已过期' : '有效' }}
          </el-tag>
        </div>
        
        <div>
          <div class="text-xs text-gray-500 mb-1">令牌值</div>
          <div class="flex items-center gap-2 bg-gray-50 dark:bg-gray-900 p-2 rounded">
            <span class="font-mono text-sm text-gray-600 dark:text-gray-300 break-all">
              {{ maskToken(token.token) }}
            </span>
            <el-button link type="primary" @click="copyToken(token.token)">
              <Copy class="w-4 h-4" />
            </el-button>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-2 text-xs text-gray-500">
          <div>
            <span class="block mb-0.5">创建时间</span>
            <span class="text-gray-700 dark:text-gray-300">{{ formatDate(token.created_at) }}</span>
          </div>
          <div>
            <span class="block mb-0.5">过期时间</span>
            <span class="text-gray-700 dark:text-gray-300">{{ formatDate(token.expires_at) }}</span>
          </div>
        </div>

        <div class="pt-3 border-t dark:border-gray-700 flex justify-end">
          <el-popconfirm title="确定要删除这个令牌吗？删除后该令牌将失效！" @confirm="handleDelete(token.id)">
            <template #reference>
              <el-button type="danger" size="small" plain>删除</el-button>
            </template>
          </el-popconfirm>
        </div>
      </div>
    </div>

    <!-- Create Token Dialog -->
    <el-dialog v-model="showCreateDialog" title="新增令牌" width="400px" style="max-width: 90%" :close-on-click-modal="false">
      <el-form ref="formRef" :model="formData" :rules="rules" label-width="100px">
        <el-form-item label="令牌名称" prop="name">
          <el-input v-model="formData.name" placeholder="请输入令牌名称" />
        </el-form-item>
        <el-form-item label="过期时间" prop="expires_at">
          <el-date-picker
            v-model="formData.expires_at"
            type="datetime"
            placeholder="选择过期时间"
            :disabled-date="disabledDate"
            :shortcuts="shortcuts"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="验证密码" prop="password">
          <el-input v-model="formData.password" type="password" show-password placeholder="请输入当前用户密码" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="showCreateDialog = false">取消</el-button>
          <el-button type="primary" :loading="creating" @click="handleCreate">确定</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { getTokens, createToken, deleteToken, type AgentToken } from '@/api/token'
import { Copy } from 'lucide-vue-next'

const tokens = ref<AgentToken[]>([])
const loading = ref(false)

const showCreateDialog = ref(false)
const creating = ref(false)
const formRef = ref<FormInstance>()

const formData = reactive({
  name: '',
  expires_at: '',
  password: ''
})

const shortcuts = [
  {
    text: '一天后',
    value: () => {
      const date = new Date()
      date.setTime(date.getTime() + 3600 * 1000 * 24)
      return date
    },
  },
  {
    text: '一周后',
    value: () => {
      const date = new Date()
      date.setTime(date.getTime() + 3600 * 1000 * 24 * 7)
      return date
    },
  },
  {
    text: '一个月后',
    value: () => {
      const date = new Date()
      date.setMonth(date.getMonth() + 1)
      return date
    },
  },
  {
    text: '一年后',
    value: () => {
      const date = new Date()
      date.setFullYear(date.getFullYear() + 1)
      return date
    },
  },
]

const rules = reactive<FormRules>({
  name: [
    { required: true, message: '请输入令牌名称', trigger: 'blur' },
    { min: 2, max: 20, message: '长度在 2 到 20 个字符', trigger: 'blur' }
  ],
  expires_at: [
    { required: true, message: '请选择过期时间', trigger: 'change' }
  ],
  password: [
    { required: true, message: '请输入密码验证身份', trigger: 'blur' }
  ]
})

const fetchTokens = async () => {
  loading.value = true
  try {
    const res = await getTokens()
    tokens.value = res.data
  } catch (error: any) {
    ElMessage.error(error.message || '获取令牌列表失败')
  } finally {
    loading.value = false
  }
}

const handleCreate = async () => {
  if (!formRef.value) return
  
  await formRef.value.validate(async (valid) => {
    if (valid) {
      creating.value = true
      try {
        const payload = {
          ...formData,
          expires_at: new Date(formData.expires_at).toISOString()
        }
        await createToken(payload)
        ElMessage.success('令牌创建成功')
        showCreateDialog.value = false
        formRef.value?.resetFields()
        fetchTokens()
      } catch (error: any) {
        ElMessage.error(error.message || '创建令牌失败，可能是密码错误')
      } finally {
        creating.value = false
      }
    }
  })
}

const handleDelete = async (id: string) => {
  try {
    await deleteToken(id)
    ElMessage.success('令牌已删除')
    fetchTokens()
  } catch (error: any) {
    ElMessage.error(error.message || '删除令牌失败')
  }
}

const disabledDate = (time: Date) => {
  return time.getTime() < Date.now()
}

const maskToken = (token: string) => {
  if (!token) return ''
  if (token.length <= 10) return '*'.repeat(token.length)
  return token.substring(0, 4) + '...'.padEnd(10, '*') + '...' + token.substring(token.length - 4)
}

const copyToken = async (token: string) => {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      // 现代浏览器，在安全上下文(https)中支持
      await navigator.clipboard.writeText(token)
    } else {
      // 降级方案，适用于http等非安全上下文
      const textArea = document.createElement('textarea')
      textArea.value = token
      // 将元素移出屏幕外，避免影响页面布局
      textArea.style.position = 'fixed'
      textArea.style.left = '-999999px'
      textArea.style.top = '-999999px'
      document.body.appendChild(textArea)
      textArea.focus()
      textArea.select()
      
      const successful = document.execCommand('copy')
      document.body.removeChild(textArea)
      
      if (!successful) {
        throw new Error('Fallback copy command failed')
      }
    }
    ElMessage.success('令牌已复制到剪贴板')
  } catch (err) {
    console.error('Copy failed:', err)
    ElMessage.error('复制失败，请手动选择复制')
  }
}

const isExpired = (dateStr: string) => {
  return new Date(dateStr).getTime() < Date.now()
}

const formatDate = (dateStr: string) => {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

onMounted(() => {
  fetchTokens()
})
</script>
