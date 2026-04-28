# AI微服务设计

AI 微服务用于承载 TrailSnap 的 AI 能力（如 OCR、人脸识别、场景分类、图片内容分析等），由后端任务系统按需调用。

## 运行方式

- Docker Compose 部署时，会包含 `trailsnap-ai` 服务。
- 默认通过内网地址被后端访问：`AI_API_URL=http://ai:8001`

## 常见接口

- Swagger 文档：`http://<host>:8801/docs`（以 docker 端口映射为准）

## 常见问题

- AI 服务无法访问：检查 `AI_API_URL` 配置与容器网络是否一致
- 识别任务无进度：在应用内“任务管理”查看任务状态与错误信息
