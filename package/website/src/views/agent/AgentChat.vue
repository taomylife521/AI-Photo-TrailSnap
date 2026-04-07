<template>
  <div v-if="modelValue" :class="['agent-chat-overlay', { 'is-fullscreen': isFullscreen }]" @click.self="handleClose">
    <div :class="['agent-chat-container', { 'is-fullscreen': isFullscreen, 'has-sidebar': isSidebarOpen }]">
      
      <!-- Sidebar for Sessions -->
      <div v-if="isSidebarOpen" class="agent-sidebar">
        <div class="sidebar-header">
          <span class="font-semibold text-slate-800 dark:text-white text-sm">历史会话</span>
          <button @click="createNewSession" class="text-indigo-600 hover:text-indigo-700 dark:text-indigo-400 dark:hover:text-indigo-300 dark:bg-slate-800 p-1 rounded-md" title="新建会话">
            <Plus class="w-5 h-5" />
          </button>
        </div>
        <div class="sidebar-content">
          <div 
            v-for="session in sortedSessions" 
            :key="session.id"
            @click="switchSession(session)"
            :class="['session-item group', { 'active': currentSession?.id === session.id }]"
          >
            <MessageSquare class="w-4 h-4 mr-2 text-slate-400 shrink-0" />
            <div class="flex-1 truncate text-sm text-slate-700 dark:text-slate-300 dark:bg-slate-800 p-1 rounded-md">{{ session.title || '新会话' }}</div>
            
            <div class="session-actions hidden group-hover:flex items-center">
              <div @click.stop>
                <el-dropdown trigger="click" @command="(cmd: string) => handleSessionCommand(cmd, session)">
                  <button class="text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300 dark:bg-slate-800 p-1 rounded-md transition-colors" title="更多操作">
                    <MoreHorizontal class="w-4 h-4" />
                  </button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="pin">
                        <Pin class="w-4 h-4 mr-2" />
                        {{ session.is_pinned ? '取消置顶' : '置顶会话' }}
                      </el-dropdown-item>
                      <el-dropdown-item command="delete" class="text-red-500">
                        <Trash2 class="w-4 h-4 mr-2" />
                        删除会话
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </div>
            <Pin v-if="session.is_pinned" class="w-4 h-4 text-yellow-500 ml-auto shrink-0 group-hover:hidden" />
          </div>
          <div v-if="sessions.length === 0" class="text-center text-slate-400 text-sm mt-4">
            暂无历史会话
          </div>
        </div>
      </div>

      <!-- Main Chat Area -->
      <div class="agent-main">
        <!-- Header -->
        <div class="agent-chat-header">
          <div class="flex items-center gap-3">
            <button @click="isSidebarOpen = !isSidebarOpen" class="text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 transition-colors dark:bg-slate-800 p-1 rounded-md">
              <Menu class="w-5 h-5" />
            </button>
            <div class="w-8 h-8 rounded-full bg-indigo-100 dark:bg-indigo-900/50 flex items-center justify-center hidden sm:flex">
              <Bot class="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
            </div>
            <div class="flex flex-col">
              <div class="flex items-center gap-2">
                <h3 class="font-semibold text-slate-800 dark:text-white text-sm m-0">TrailSnap</h3>
                <el-select
                  v-model="selectedModelValue"
                  size="small"
                  class="w-36"
                  placeholder="选择模型"
                  v-if="availableModels.length > 0 || isModelsLoading"
                  :loading="isModelsLoading"
                >
                  <el-option
                    v-for="m in availableModels"
                    :key="m.conn_id + '|' + m.model"
                    :label="m.label"
                    :value="m.conn_id + '|' + m.model"
                  />
                </el-select>
              </div>
              <p class="text-xs text-slate-500 dark:text-slate-400 m-0 hidden sm:block">您的智能相册管家</p>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <!-- 批量删除状态下显示的操作按钮 -->
            <template v-if="isSelectionMode">
              <button v-if="selectedMessages.length > 0" @click="deleteSelectedMessages" class="text-red-500 hover:text-red-600 dark:text-red-400 dark:hover:text-red-300 text-sm font-medium ml-1 transition-colors">
                删除 ({{ selectedMessages.length }})
              </button>
              <button @click="isSelectionMode = false" class="text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 text-sm ml-2 transition-colors">
                取消
              </button>
            </template>
            
            <div class="w-px h-4 bg-slate-200 dark:bg-slate-700 mx-1"></div>

            <button @click="isFullscreen = !isFullscreen" class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors dark:bg-slate-800 p-1 rounded-md" :title="isFullscreen ? '退出全屏' : '全屏'">
              <Minimize2 v-if="isFullscreen" class="w-5 h-5" />
              <Maximize2 v-else class="w-5 h-5" />
            </button>
            <button @click="handleClose" class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors dark:bg-slate-800 p-1 rounded-md">
              <X class="w-5 h-5" />
            </button>
          </div>
        </div>

        <!-- Messages -->
        <div class="agent-chat-messages" ref="messagesContainer">
          <div class="w-full max-w-4xl mx-auto flex flex-col space-y-6 pb-2">
            <div 
              v-for="(msg, index) in messages" 
              :key="msg.id || index"
              class="flex w-full group relative"
            >
            <!-- Checkbox for selection mode -->
            <div v-if="isSelectionMode" class="flex-shrink-0 w-8 flex justify-center pb-2 items-end">
              <el-checkbox :model-value="selectedMessages.includes(msg.id!)" @change="toggleSelectMessage(msg.id)" :disabled="msg.id === undefined" />
            </div>

            <div class="message-wrapper flex-1" :class="msg.role === 'user' ? 'justify-end' : 'justify-start'">
              <div v-if="msg.role === 'assistant'" class="message-avatar assistant">
                <Bot class="w-4 h-4" />
              </div>

              <div class="flex flex-col gap-1 max-w-[85%]" :class="msg.role === 'user' ? 'items-end' : 'items-start'">
                <div class="message-bubble" :class="[msg.role, { 'opacity-60': isSelectionMode && !selectedMessages.includes(msg.id!) }]">
                  <div v-if="msg.isMarkdown" class="markdown-body" v-html="renderMarkdown(msg.content)"></div>
                  <div v-else class="whitespace-pre-wrap break-words">{{ msg.content }}</div>
                </div>
                
                <!-- Message Actions Space Placeholder -->
                <div v-if="!isSelectionMode" class="h-7 w-full flex items-center gap-1 text-slate-400 dark:text-slate-500 mt-0.5 px-1" :class="msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'">
                  <!-- Message Actions -->
                  <div class="message-actions items-center gap-1 transition-opacity duration-200" 
                       :class="[
                         msg.role === 'user' ? 'flex-row-reverse' : 'flex-row',
                         activeDropdownIndex === index ? 'flex opacity-100' : 'hidden group-hover:flex opacity-0 group-hover:opacity-100'
                       ]">
                    <button @click="copyMessage(msg.content)" class="bg-transparent hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 transition-colors p-1 rounded-md" title="复制">
                      <Copy class="w-4 h-4"/>
                    </button>
                    
                    <!-- 重新生成按钮：只在最后一条助手消息显示 -->
                    <button v-if="msg.role === 'assistant' && isLastAssistantMessage(index)" @click="handleRegenerate(msg, index)" class="bg-transparent hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 transition-colors p-1 rounded-md" title="重新生成">
                      <RefreshCw class="w-4 h-4"/>
                    </button>
                    
                    <!-- 编辑按钮：只在最后一条用户消息显示 -->
                    <button v-if="msg.role === 'user' && isLastUserMessage(index)" @click="handleEditMessage(msg, index)" class="bg-transparent hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 transition-colors p-1 rounded-md" title="编辑">
                      <Edit2 class="w-4 h-4"/>
                    </button>

                    <div @click.stop>
                      <el-dropdown trigger="click" @command="(cmd: string) => handleMessageCommand(cmd, msg, index)" @visible-change="(visible: boolean) => handleDropdownVisibleChange(visible, index)">
                        <button class="bg-transparent hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 transition-colors p-1 rounded-md" title="更多">
                          <MoreHorizontal class="w-4 h-4"/>
                        </button>
                        <template #dropdown>
                          <el-dropdown-menu>
                            <el-dropdown-item command="delete" class="text-red-500">
                              <Trash2 class="w-4 h-4 mr-2" />
                              删除消息
                            </el-dropdown-item>
                          </el-dropdown-menu>
                        </template>
                      </el-dropdown>
                    </div>
                  </div>
                </div>
              </div>

              <div v-if="msg.role === 'user'" class="message-avatar user">
                <User class="w-4 h-4" />
              </div>
            </div>
          </div>

          <div v-if="isLoading" class="message-wrapper justify-start">
            <div class="message-avatar assistant">
              <Bot class="w-4 h-4" />
            </div>
            <div class="message-bubble assistant flex items-center gap-2 py-3">
              <Loader2 class="w-4 h-4 animate-spin text-indigo-500" />
              <span class="text-sm text-slate-500">思考中...</span>
            </div>
          </div>
          </div>
        </div>

        <!-- Input Area -->
        <div class="agent-chat-input-area">
          <div class="w-full max-w-4xl mx-auto">
            <form @submit.prevent="sendMessage" class="relative">
              <input
                v-model="inputMessage"
                type="text"
                placeholder="问问我关于您的照片或行程..."
                class="agent-input"
                :disabled="isLoading || isSelectionMode"
              />
              <button 
                type="submit" 
                class="agent-send-btn"
                :disabled="!inputMessage.trim() || isLoading || isSelectionMode"
              >
                <Send class="w-4 h-4" />
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>

    <!-- 引入全屏图片预览组件 -->
    <PhotoLightbox
      :visible="isLightboxOpen"
      :image="currentPhotoSrc"
      :hasPrev="currentPhotoIndex > 0"
      :hasNext="currentPhotoIndex < allPhotos.length - 1"
      @close="isLightboxOpen = false"
      @prev="() => { if (currentPhotoIndex > 0) { currentPhotoIndex--; currentPhotoSrc = allPhotos[currentPhotoIndex]; } }"
      @next="() => { if (currentPhotoIndex < allPhotos.length - 1) { currentPhotoIndex++; currentPhotoSrc = allPhotos[currentPhotoIndex]; } }"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Bot, User, X, Loader2, Send, Menu, Maximize2, Minimize2, Plus, Trash2, Pin, MessageSquare, ListChecks, Copy, MoreHorizontal, RefreshCw, Edit2 } from 'lucide-vue-next';
import { agentApi, type AgentSession, type AgentMessage } from '@/api/agent';
import { settingsApi } from '@/api/settings';
import MarkdownIt from 'markdown-it';
import DOMPurify from 'dompurify';
import PhotoLightbox from '@/components/PhotoLightbox.vue';

const props = defineProps<{
  modelValue: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void;
}>();

// Lightbox 状态
const isLightboxOpen = ref(false);
const currentPhotoSrc = ref<any>(null);
const currentPhotoIndex = ref(0);
const allPhotos = ref<any[]>([]);

// Layout & UI 状态
const isFullscreen = ref(false);
const isSidebarOpen = ref(false);

// Models & Connections state
const availableModels = ref<Array<{ conn_id: string, model: string, label: string }>>([]);
const selectedModelValue = ref('');
const isModelsLoading = ref(false);

const loadModels = async () => {
  isModelsLoading.value = true;
  try {
    const res = await settingsApi.getModels();
    const list: Array<{ conn_id: string, model: string, label: string }> = [];
    if (res && res.connections) {
      res.connections.forEach((conn: any) => {
        if (conn.models && conn.models.length > 0) {
          conn.models.forEach((m: string) => {
            list.push({
              conn_id: conn.id,
              model: m,
              label: `${m} (${conn.api_base || conn.id})`
            });
          });
        }
      });
    }
    availableModels.value = list;
    if (res.chat_connection_id && res.chat_model_name) {
      selectedModelValue.value = `${res.chat_connection_id}|${res.chat_model_name}`;
    } else if (res.analysis_connection_id && res.analysis_model_name) {
      selectedModelValue.value = `${res.analysis_connection_id}|${res.analysis_model_name}`;
    } else if (list.length > 0) {
      selectedModelValue.value = `${list[0].conn_id}|${list[0].model}`;
    }
  } catch (e) {
    console.error('Failed to load models', e);
  } finally {
    isModelsLoading.value = false;
  }
};

// 会话管理
const sessions = ref<AgentSession[]>([]);
const currentSession = ref<AgentSession | null>(null);

const sortedSessions = computed(() => {
  return [...sessions.value].sort((a, b) => {
    if (a.is_pinned && !b.is_pinned) return -1;
    if (!a.is_pinned && b.is_pinned) return 1;
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  });
});

// 消息管理
interface MessageItem {
  id?: number;
  role: 'user' | 'assistant';
  content: string;
  isMarkdown?: boolean;
}

const activeDropdownIndex = ref<number | null>(null);

const handleDropdownVisibleChange = (visible: boolean, index: number) => {
  if (visible) {
    activeDropdownIndex.value = index;
  } else {
    if (activeDropdownIndex.value === index) {
      activeDropdownIndex.value = null;
    }
  }
};

const defaultWelcomeMessage: MessageItem = {
  role: 'assistant',
  content: '你好！我是 TrailSnap 智能相册助手。你可以问我：\n- "帮我整理一下最近拍的照片，写一段朋友圈文案"\n- "今年国庆节去了哪些地方？"\n- "找几张在海边的照片"',
  isMarkdown: false
};

const messages = ref<MessageItem[]>([ { ...defaultWelcomeMessage } ]);
const inputMessage = ref('');
const isLoading = ref(false);
const messagesContainer = ref<HTMLElement | null>(null);

// 批量选择
const isSelectionMode = ref(false);
const selectedMessages = ref<number[]>([]);

const toggleSelectMessage = (id?: number) => {
  if (id === undefined) return;
  const index = selectedMessages.value.indexOf(id);
  if (index > -1) {
    selectedMessages.value.splice(index, 1);
  } else {
    selectedMessages.value.push(id);
  }
};

const deleteSelectedMessages = async () => {
  if (selectedMessages.value.length === 0 || !currentSession.value) return;
  
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selectedMessages.value.length} 条消息吗？`, '提示', {
      type: 'warning',
      confirmButtonText: '确定',
      cancelButtonText: '取消'
    });
    
    await agentApi.deleteMessages(currentSession.value.id, selectedMessages.value);
    ElMessage.success('删除成功');
    isSelectionMode.value = false;
    selectedMessages.value = [];
    await loadMessages(currentSession.value.id);
  } catch (e) {
    // cancelled or error
  }
};

// 消息操作功能
const copyMessage = async (content: string) => {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(content);
      ElMessage.success('已复制到剪贴板');
    } else {
      // Fallback for non-secure contexts
      const textArea = document.createElement("textarea");
      textArea.value = content;
      textArea.style.position = "fixed";
      textArea.style.left = "-999999px";
      textArea.style.top = "-999999px";
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      
      try {
        document.execCommand('copy');
        ElMessage.success('已复制到剪贴板');
      } catch (err) {
        ElMessage.error('复制失败');
      } finally {
        textArea.remove();
      }
    }
  } catch (err) {
    ElMessage.error('复制失败');
  }
};

const handleMessageCommand = (command: string, msg: MessageItem, index: number) => {
  if (command === 'delete') {
    isSelectionMode.value = true;
    selectedMessages.value = [];
    
    if (msg.id !== undefined) {
      selectedMessages.value.push(msg.id);
    }
    
    if (msg.role === 'assistant' && index > 0) {
      const prevMsg = messages.value[index - 1];
      if (prevMsg.role === 'user' && prevMsg.id !== undefined) {
        selectedMessages.value.push(prevMsg.id);
      }
    } else if (msg.role === 'user' && index < messages.value.length - 1) {
      const nextMsg = messages.value[index + 1];
      if (nextMsg.role === 'assistant' && nextMsg.id !== undefined) {
        selectedMessages.value.push(nextMsg.id);
      }
    }
  }
};

const isLastAssistantMessage = (index: number) => {
  return index === messages.value.length - 1;
};

const isLastUserMessage = (index: number) => {
  if (index === messages.value.length - 1) return true;
  if (index === messages.value.length - 2 && messages.value[index + 1].role === 'assistant') return true;
  return false;
};

const handleRegenerate = async (msg: MessageItem, index: number) => {
  if (index === 0) return;
  const prevMsg = messages.value[index - 1];
  if (prevMsg.role !== 'user') return;
  
  const userText = prevMsg.content;
  const idsToDelete = [];
  if (msg.id !== undefined) idsToDelete.push(msg.id);
  if (prevMsg.id !== undefined) idsToDelete.push(prevMsg.id);
  
  if (idsToDelete.length > 0 && currentSession.value) {
    try {
      await agentApi.deleteMessages(currentSession.value.id, idsToDelete);
    } catch (e) {
      ElMessage.error('重新生成失败');
      return;
    }
  }
  
  messages.value.splice(index - 1, 2);
  inputMessage.value = userText;
  await sendMessage();
};

const handleEditMessage = async (msg: MessageItem, index: number) => {
  try {
    const { value } = await ElMessageBox.prompt('编辑消息', '编辑', {
      confirmButtonText: '重新发送',
      cancelButtonText: '取消',
      inputValue: msg.content,
      inputType: 'textarea',
      customStyle: { maxWidth: '90vw' }
    });
    
    if (value && value.trim() !== '' && value.trim() !== msg.content) {
      const idsToDelete = [];
      if (msg.id !== undefined) idsToDelete.push(msg.id);
      
      let deleteCount = 1;
      if (index < messages.value.length - 1) {
        const nextMsg = messages.value[index + 1];
        if (nextMsg.role === 'assistant' && nextMsg.id !== undefined) {
          idsToDelete.push(nextMsg.id);
          deleteCount = 2;
        }
      }
      
      if (idsToDelete.length > 0 && currentSession.value) {
        await agentApi.deleteMessages(currentSession.value.id, idsToDelete);
      }
      
      messages.value.splice(index, deleteCount);
      inputMessage.value = value.trim();
      await sendMessage();
    }
  } catch (e) {
    // cancelled
  }
};

// Markdown 解析器配置
const md = new MarkdownIt({
  html: true,
  breaks: true,
  linkify: true,
});

// 自定义图片渲染以支持九宫格样式和前端代理路径
const getCorrectImageUrl = (src: string) => {
  if (!src) return '';
  if (src.startsWith('http') || src.startsWith('data:')) return src;

  let baseUrl = import.meta.env.VITE_API_BASE_URL || '';
  if (baseUrl.endsWith('/')) {
    baseUrl = baseUrl.slice(0, -1);
  }

  if (!baseUrl) {
    if (src.startsWith('/medias')) return '/api' + src;
    if (src.startsWith('/api/')) return src;
    return '/api' + (src.startsWith('/') ? src : '/' + src);
  } else {
    if (src.startsWith('/api/medias')) return baseUrl + src.replace('/api/', '/');
    if (src.startsWith('/medias')) return baseUrl + src;
    return baseUrl + (src.startsWith('/') ? src : '/' + src);
  }
};

md.renderer.rules.image = (tokens, idx, options, env, self) => {
  const token = tokens[idx];
  const originalSrc = token.attrGet('src') || '';
  const alt = token.content || '';
  
  let src = getCorrectImageUrl(originalSrc);

  if (src.startsWith('http') && src.includes('//api/')) {
    src = src.replace('//api/', '/api/');
  }

  const fullSrc = src.replace('/thumbnail', '/file');

  return `<agent-image data-src="${src}?size=medium" data-full-src="${fullSrc}" data-alt="${alt}"></agent-image>`;
};

const defaultRender = md.renderer.rules.paragraph_open || function(tokens, idx, options, env, self) {
  return self.renderToken(tokens, idx, options);
};

md.renderer.rules.paragraph_open = function(tokens, idx, options, env, self) {
  return defaultRender(tokens, idx, options, env, self);
};

const defaultParagraphClose = md.renderer.rules.paragraph_close || function(tokens, idx, options, env, self) {
  return self.renderToken(tokens, idx, options);
};

md.renderer.rules.paragraph_close = function(tokens, idx, options, env, self) {
  return defaultParagraphClose(tokens, idx, options, env, self);
};

const scrollToBottom = async (force: boolean = false) => {
  await nextTick();
  if (messagesContainer.value) {
    const { scrollTop, scrollHeight, clientHeight } = messagesContainer.value;
    const isNearBottom = scrollHeight - scrollTop - clientHeight < 150;
    if (force || isNearBottom) {
      messagesContainer.value.scrollTop = scrollHeight;
    }
  }
};

const handleClose = () => {
  emit('update:modelValue', false);
};

const renderMarkdown = (content: string) => {
  let rawHtml = md.render(content);
  
  rawHtml = rawHtml.replace(/<p>((?:\s*<agent-image[^>]*><\/agent-image>\s*)+)<\/p>/g, (match, p1) => {
    const imgs = p1.replace(/<agent-image data-src="([^"]+)" data-full-src="([^"]+)" data-alt="([^"]*)"><\/agent-image>/g, 
      '<div class="agent-gallery-item"><img src="$1" alt="$3" class="agent-gallery-image" data-full-src="$2" /></div>'
    );
    return `<div class="agent-gallery-grid">${imgs}</div>`;
  });

  rawHtml = rawHtml.replace(/<agent-image data-src="([^"]+)" data-full-src="([^"]+)" data-alt="([^"]*)"><\/agent-image>/g, 
      '<img src="$1" alt="$3" class="agent-gallery-image inline-image max-h-[200px]" data-full-src="$2" />'
  );

  rawHtml = rawHtml.replace(/<p>\s*<\/p>/g, '');

  return DOMPurify.sanitize(rawHtml, { 
    ADD_TAGS: ['img', 'div'], 
    ADD_ATTR: ['target', 'class', 'src', 'alt', 'data-full-src'] 
  });
};

const setupImageClick = () => {
  if (messagesContainer.value) {
    const images = messagesContainer.value.querySelectorAll('.agent-gallery-image');
    images.forEach(img => {
      const clone = img.cloneNode(true);
      if(img.parentNode) {
        img.parentNode.replaceChild(clone, img);
      }
      clone.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const target = e.target as HTMLImageElement;
        
        let originalSrc = target.getAttribute('data-full-src') || target.src.replace('/thumbnail', '');
        
        const imgElements = messagesContainer.value?.querySelectorAll('.agent-gallery-image');
        if (imgElements && imgElements.length > 0) {
          allPhotos.value = Array.from(imgElements).map((el, index) => {
            let photoSrc = el.getAttribute('data-full-src') || (el as HTMLImageElement).src.replace('/thumbnail', '');
            
            let realId = `agent-img-${index}`;
            const idMatch = photoSrc.match(/\/medias\/([a-f0-9\-]{36})/i);
            if (idMatch && idMatch[1]) {
              realId = idMatch[1];
            }
            
            if (!photoSrc.startsWith('http') && !photoSrc.startsWith('data:')) {
               photoSrc = window.location.origin + (photoSrc.startsWith('/') ? photoSrc : '/' + photoSrc);
            }

            if (!photoSrc.includes('/thumbnail') && !photoSrc.includes('/file')) {
                const match = photoSrc.match(/(\/medias\/[a-f0-9\-]{36})$/i);
                if (match) {
                    photoSrc = photoSrc + '/file';
                }
            }

            return { 
              id: realId, 
              url: photoSrc, 
              preview: photoSrc, 
              file_type: 'image' 
            };
          });
          const clickedIndex = Array.from(imgElements).indexOf(target);
          currentPhotoIndex.value = clickedIndex !== -1 ? clickedIndex : 0;
          currentPhotoSrc.value = allPhotos.value[currentPhotoIndex.value];
          isLightboxOpen.value = true;
        } else {
          let fallbackSrc = originalSrc;
          let realId = 'agent-img-0';
          const idMatch = fallbackSrc.match(/\/medias\/([a-f0-9\-]{36})/i);
          if (idMatch && idMatch[1]) {
            realId = idMatch[1];
          }
          if (!fallbackSrc.startsWith('http') && !fallbackSrc.startsWith('data:')) {
             fallbackSrc = window.location.origin + (fallbackSrc.startsWith('/') ? fallbackSrc : '/' + fallbackSrc);
          }
          
          if (!fallbackSrc.includes('/thumbnail') && !fallbackSrc.includes('/file')) {
              const match = fallbackSrc.match(/(\/medias\/[a-f0-9\-]{36})$/i);
              if (match) {
                  fallbackSrc = fallbackSrc + '/file';
              }
          }
          
          const singleImg = { id: realId, url: fallbackSrc, preview: fallbackSrc, file_type: 'image' };
          allPhotos.value = [singleImg];
          currentPhotoIndex.value = 0;
          currentPhotoSrc.value = singleImg;
          isLightboxOpen.value = true;
        }
      });
    });
  }
};

// API 交互逻辑
const loadSessions = async () => {
  try {
    const res = await agentApi.getSessions();
    sessions.value = res.data;
  } catch (error) {
    console.error('Failed to load sessions', error);
  }
};

const createNewSession = () => {
  currentSession.value = null;
  messages.value = [ { ...defaultWelcomeMessage } ];
  isSelectionMode.value = false;
  selectedMessages.value = [];
  if (window.innerWidth < 640) {
    isSidebarOpen.value = false;
  }
};

const switchSession = async (session: AgentSession) => {
  if (currentSession.value?.id === session.id) return;
  currentSession.value = session;
  isSelectionMode.value = false;
  selectedMessages.value = [];
  await loadMessages(session.id);
  if (window.innerWidth < 640) {
    isSidebarOpen.value = false;
  }
};

const loadMessages = async (sessionId: string, showLoading: boolean = true) => {
  if (showLoading) isLoading.value = true;
  try {
    const res = await agentApi.getSessionMessages(sessionId);
    if (res.data.length === 0) {
      messages.value = [ { ...defaultWelcomeMessage } ];
    } else {
      messages.value = res.data.map(m => ({
        id: m.id,
        role: m.role as 'user' | 'assistant',
        content: m.content,
        isMarkdown: m.role === 'assistant'
      }));
    }
    await scrollToBottom(true);
    setTimeout(setupImageClick, 100);
  } catch (error) {
    ElMessage.error('加载消息失败');
  } finally {
    if (showLoading) isLoading.value = false;
  }
};

const deleteSession = async (sessionId: string) => {
  try {
    await ElMessageBox.confirm('确定删除该会话吗？', '提示', { type: 'warning' });
    await agentApi.deleteSession(sessionId);
    ElMessage.success('删除成功');
    if (currentSession.value?.id === sessionId) {
      createNewSession();
    }
    await loadSessions();
  } catch (e) {
    // cancelled
  }
};

const togglePin = async (session: AgentSession) => {
  try {
    await agentApi.pinSession(session.id, !session.is_pinned);
    await loadSessions();
  } catch (error) {
    ElMessage.error('操作失败');
  }
};

const handleSessionCommand = (command: string, session: AgentSession) => {
  if (command === 'pin') {
    togglePin(session);
  } else if (command === 'delete') {
    deleteSession(session.id);
  }
};

const sendMessage = async () => {
  if (!inputMessage.value.trim() || isLoading.value) return;

  const userText = inputMessage.value.trim();
  messages.value.push({ role: 'user', content: userText });
  inputMessage.value = '';
  isLoading.value = true;
  await scrollToBottom(true);

  try {
    let aiMessageIndex = -1;
    let sessionIdReceived = false;

    const [conn_id, model] = selectedModelValue.value.split('|');

    await agentApi.chatStream(
      {
        message: userText,
        session_id: currentSession.value?.id || undefined,
        connection_id: conn_id || undefined,
        model_name: model || undefined
      },
      (content) => {
        if (aiMessageIndex === -1) {
          // 首次收到响应，关闭加载状态并创建 AI 消息对象
          isLoading.value = false;
          aiMessageIndex = messages.value.length;
          messages.value.push({ role: 'assistant', content: content, isMarkdown: true });
        } else {
          // 追加内容
          messages.value[aiMessageIndex].content += content;
        }
        scrollToBottom();
      },
      async (sessionId) => {
        if (!sessionIdReceived && (!currentSession.value || currentSession.value.id !== sessionId)) {
          sessionIdReceived = true;
          await loadSessions();
          const newSession = sessions.value.find(s => s.id === sessionId);
          if (newSession) {
            currentSession.value = newSession;
          }
        }
      },
      (title) => {
        // 更新当前会话的标题
        if (currentSession.value) {
          currentSession.value.title = title;
        }
        // 同步更新列表中对应的会话标题
        const sessionInList = sessions.value.find(s => s.id === currentSession.value?.id);
        if (sessionInList) {
          sessionInList.title = title;
        }
      }
    );

    // 流结束后更新 DOM
    if (currentSession.value) {
      await loadMessages(currentSession.value.id, false);
    } else {
      nextTick(() => {
        setupImageClick();
      });
    }

  } catch (error: any) {
    let errorMsg = '对话失败，请重试';
    if (error.response?.data?.detail) {
      errorMsg = error.response.data.detail;
    } else if (error.message) {
      errorMsg = error.message;
    }
    ElMessage.error(errorMsg);
    messages.value.push({ 
      role: 'assistant', 
      content: `❌ ${errorMsg}` 
    });
  } finally {
    isLoading.value = false;
    nextTick(() => {
      scrollToBottom();
    });
  }
};

watch(() => props.modelValue, (newVal) => {
  if (newVal) {
    loadModels();
    loadSessions();
    scrollToBottom(true);
  }
});

onMounted(() => {
  if (props.modelValue) {
    loadModels();
    loadSessions();
    scrollToBottom();
  }
});
</script>

<style scoped>
.agent-chat-overlay {
  @apply fixed inset-0 z-[100] flex items-end sm:items-center justify-center bg-black/20 backdrop-blur-sm sm:p-4 transition-all duration-300;
}

.agent-chat-overlay.is-fullscreen {
  @apply sm:p-0;
}

.agent-chat-container {
  @apply w-full sm:w-[450px] h-[85vh] sm:h-[600px] max-h-screen bg-white dark:bg-slate-900 sm:rounded-2xl shadow-2xl flex overflow-hidden sm:border border-slate-200 dark:border-slate-800 transition-all duration-300;
  animation: slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

.agent-chat-container.has-sidebar {
  @apply sm:w-[706px];
}

.agent-chat-container.is-fullscreen {
  @apply sm:w-full sm:h-full sm:rounded-none sm:border-none sm:p-0;
}

@keyframes slideUp {
  from { transform: translateY(100%); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}

.agent-sidebar {
  @apply absolute sm:relative z-20 w-64 h-full border-r border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 flex flex-col shrink-0 shadow-xl sm:shadow-none;
}

.sidebar-header {
  @apply px-4 py-3 flex justify-between items-center border-b border-slate-200 dark:border-slate-800;
}

.sidebar-content {
  @apply flex-1 overflow-y-auto p-2 space-y-1;
}

.session-item {
  @apply flex items-center px-3 py-2.5 rounded-lg cursor-pointer transition-colors;
}

.session-item:hover {
  @apply bg-slate-200/50 dark:bg-slate-800;
}

.session-item.active {
  @apply bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400;
}

.agent-main {
  @apply flex-1 flex flex-col min-w-0 bg-white dark:bg-slate-900 h-full;
}

.agent-chat-header {
  @apply px-4 py-3 border-b border-slate-100 dark:border-slate-800 flex justify-between items-center bg-white/80 dark:bg-slate-900/80 backdrop-blur-md z-10;
}

.agent-chat-messages {
  @apply flex-1 overflow-y-auto p-4 scroll-smooth;
}

.message-wrapper {
  @apply flex items-end gap-2 w-full;
}

.message-avatar {
  @apply w-7 h-7 rounded-full flex items-center justify-center shrink-0 mb-1;
}

.message-avatar.assistant {
  @apply bg-indigo-100 text-indigo-600 dark:bg-indigo-900/50 dark:text-indigo-400;
}

.message-avatar.user {
  @apply bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400;
}

.message-bubble {
  @apply rounded-2xl px-4 py-2.5 text-sm shadow-sm transition-opacity duration-200;
}

.message-bubble.user {
  @apply bg-indigo-600 text-white rounded-br-sm;
}

.message-bubble.assistant {
  @apply bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-200 border border-slate-100 dark:border-slate-700 rounded-bl-sm;
}

.message-checkbox {
  @apply flex items-center justify-center;
}

.agent-chat-input-area {
  @apply p-4 bg-white dark:bg-slate-900 border-t border-slate-100 dark:border-slate-800;
}

.agent-input {
  @apply w-full pl-4 pr-12 py-3 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-sm text-slate-800 dark:text-white placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 transition-all disabled:opacity-50 disabled:cursor-not-allowed;
}

.agent-send-btn {
  @apply absolute right-2 top-1/2 -translate-y-1/2 p-2 bg-indigo-600 dark:bg-indigo-500 text-white rounded-lg hover:bg-indigo-700 dark:hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors;
}

/* Markdown Styles */
:deep(.markdown-body) {
  @apply text-sm leading-relaxed;
}

:deep(.markdown-body p) {
  @apply mb-2 last:mb-0;
}

:deep(.markdown-body strong) {
  @apply font-semibold text-slate-900 dark:text-white;
}

:deep(.markdown-body ul) {
  @apply list-disc pl-5 mb-2;
}

/* Custom Gallery Layout for AI returned images (CSS Grid 布局) */
:deep(.agent-gallery-grid) {
  display: grid !important;
  grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
  gap: 4px !important;
  margin: 12px 0 !important;
  padding: 0 !important;
  background-color: transparent !important;
  width: 100%;
  box-sizing: border-box;
}

:deep(.agent-gallery-item) {
  position: relative;
  width: 100%;
  padding-bottom: 100%; 
  overflow: hidden;
  border-radius: 6px;
  background-color: rgb(241 245 249);
}

:deep(.dark .agent-gallery-item) {
  background-color: rgb(30 41 59);
}

:deep(.agent-gallery-image) {
  position: absolute;
  top: 0;
  left: 0;
  width: 100% !important;
  height: 100% !important;
  object-fit: cover !important;
  margin: 0 !important;
  padding: 0 !important;
  display: block !important;
  cursor: pointer;
  border: none !important;
  transition: filter 0.2s ease;
}

:deep(.agent-gallery-image.inline-image) {
  position: relative;
  width: auto !important;
  max-width: 100% !important;
  height: auto !important;
  border-radius: 8px;
}

:deep(.agent-gallery-item:hover .agent-gallery-image) {
  filter: brightness(0.85);
}
</style>
