# AI微服务设计

AI 微服务用于承载 TrailSnap 的 AI 能力（如 OCR、人脸识别、场景分类、图片内容分析等），由后端任务系统按需调用。

## 运行方式

- Docker Compose 部署时，会包含 `trailsnap-ai` 服务。
- 默认通过内网地址被后端访问：`AI_API_URL=http://ai:8001`

## LLM 托管

AI 服务支持本地 LLM 服务托管与代理能力：

- 支持通过 llama.cpp 原生编译的 llama-server 二进制运行 LLM 服务
- 支持自定义模型路径、服务端口和空闲超时时间
- 自动处理模型下载、服务启停与空闲资源回收
- 提供 OpenAI 格式的 LLM 代理路由，透明转发请求到本地 llama.cpp 服务

多模态模型使用 MiniCPM-V-4_6-Q4_K_M，支持图片内容理解、标签生成等视觉任务。

## 常见接口

- Swagger 文档：`http://<host>:8801/docs`（以 docker 端口映射为准）

## 常见问题

- AI 服务无法访问：检查 `AI_API_URL` 配置与容器网络是否一致
- 识别任务无进度：在应用内"任务管理"查看任务状态与错误信息