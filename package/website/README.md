# TrailSnap Frontend

TrailSnap 的前端应用，基于 Vue 3 + TypeScript + Vite 构建。

## 技术栈

- **框架**: Vue 3
- **语言**: TypeScript
- **构建工具**: Vite
- **UI 库**: Element Plus
- **CSS 框架**: TailwindCSS
- **状态管理**: Pinia
- **路由**: Vue Router

## 环境要求

- Node.js v18+ (推荐 v20 或 v22)
- pnpm (推荐) 或 npm/yarn

## 快速开始

### 1. 安装依赖

```bash
cd package/website

# 安装 pnpm
npm install -g pnpm

# 安装项目依赖
pnpm install
```

### 2. 运行开发服务器

```bash
pnpm run dev
```

启动后访问: http://localhost:5176

### 3. 构建生产版本

```bash
pnpm run build
```

构建产物将输出到 `dist` 目录。

## 环境变量（暂不需要）

在根目录下创建 `.env` 或 `.env.local` 文件来配置环境变量：

```env
# 后端 API 地址 (开发环境通常由 Vite 代理转发)
VITE_API_BASE_URL=/api
```

## 目录结构

- `src/`
  - `api/`: API 请求封装
  - `assets/`: 静态资源
  - `components/`: 通用组件
  - `composables/`: 组合式函数 (Hooks)
  - `layouts/`: 布局组件
  - `router/`: 路由配置
  - `stores/`: Pinia 状态管理
  - `types/`: TS 类型定义
  - `views/`: 页面视图
