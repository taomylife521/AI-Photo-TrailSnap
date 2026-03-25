# TrailSnap 行影集

TrailSnap 是一个智能化的 AI 相册应用，致力于帮助用户轻松记录、整理和回顾自己的出行经历。通过强大的 AI 处理能力，让每一张照片和每一段旅程都成为值得珍藏的记忆。

我相信未来每个人（至少每个家庭）都有一个属于自己的 AI 数据中心，而相册是数据中心的一个重要数据来源，它留存了你生活中的很多瞬间，而 AI 相册则是将这些瞬间转化为有价值的记忆，它可以帮你默默地记录下相册里的车票、景点门票，可以帮你记录旅行中的所见所闻，可以帮你自动整理出可以发朋友圈的照片（甚至帮你准备好文案），可以帮你剪一段15s的短视频······。

所以，我给这个项目命名为 **《行影集》**，在这里你的数据才 “真正属于你”。

<br/>
  <a href="https://trailsnap.cn">
    <img src="doc/image/demo.png" title="Main Screenshot">
  </a>
<br/>

## ✨ 核心特色

- **📷 智能相册**: 人物识别、智能分类、OCR识别。
- **🚆 行程记录**: 特有的火车票、行程、景区/演唱会门票管理功能，自动识别票据信息。（正在开发中）
- **🤖 AI 赋能**: 一句话让AI帮你生成旅行日记。（待开发）
  - AI自动剪视频生成VLOG
  - AI修图，自动识别高质量照片

## 🧭 功能概览

| 功能 | 实现情况 | 描述 |
| --- | --- | --- |
| 上传并查看照片和视频 | √ | 支持上传本地照片和视频文件，查看和播放。 |
| 添加外部文件夹 | √ | 可以添加外部文件夹作为数据源，TrailSnap 会自动扫描并索引其中的照片和视频。 |
| live photo | √ | 支持iphone、vivo、oppo、小米等手机 |
| **时间轴** | √ | 丝滑的时间轴滚动效果。 |
| 在地图上查看照片 | √ | 可以在地图上查看所有上传的照片，点击照片可以查看详情，也可以按省、市、区单独查看（支持列表视图和地图视图）。 |
| **点亮的城市** | √ | 查看所有上传的照片中出现的城市，点击城市可以查看该城市的所有照片。 |
| **去过的景区** | √ | 统计去过的5A级景区，点击景区可以查看该景区的所有照片，也可以自定义景区位置，自动筛选在景区范围内的照片。 |
| 人脸识别 | √ | 支持识别照片中的人物，自动添加人物标签。 |
| 场景智能分类 | √ | 支持根据照片中的场景自动分类，例如：夜景、宠物、美食、自拍等。 |
| 智能搜索 | √ | 支持根据照片中的人物、画面内容、时间等进行搜索。 |
| 标签 | √ | 支持手动添加和删除标签，也可以根据 AI 识别结果自动添加标签。 |
| 条件相册 | √ | 支持根据标签、场景、人物、地点等条件筛选照片，生成自定义相册。 |
| 智能相册 | √ | 支持根据照片中的内容自动生成相册，例如：“我和女朋友在海边的自拍”等。 |
| **车票识别** | √ | 支持识别照片中的火车票和行程单，自动提取行程信息。 |
| **年度报告** | √ | 自动生成2025年的出行统计报告，包括照片墙、出行城市、出行景点、行程时间轴、线路里程等。 |
| **AI分析** | √ | 使用大模型分析照片内容，生成描述和评分，做成电子画廊。|
| **那年今日** | √ | 查看往年今天的照片，按图片评分排序、自动播放往年值得回忆的照片。|
| **旅行日志** | 待开发 | 支持用户手动输入或 AI 识别出的行程信息，生成旅行日志。 |

## 2025 年度报告

2025 相册年度报告

[查看预览版](https://siyuan.ink/annual-report)

![年度报告](./doc/image/年度报告.jpg)

## 🚀 快速开始

### docker一键启动

1. 确保已安装 Docker 和 Docker Compose。

2. docker-compose

docker-compose.yml 配置文件（注意修改挂载路径为本地路径，不然无法扫描本地照片目录）
```yml
version: '3.8'

services:
  postgres:
    image: pgvector/pgvector:pg18-trixie
    container_name: postgres_container
    restart: always
    environment:
      TZ: Asia/Shanghai
      POSTGRES_DB: trailsnap
      POSTGRES_USER: trailsnap
      POSTGRES_PASSWORD: trailsnap
      POSTGRES_INITDB_ARGS: "--encoding=UTF8 --lc-collate=C --lc-ctype=C"
      PGDATA: /var/lib/postgresql/data/pgdata
    networks: [ app-network ]
    ports:
      - "5532:5432"
    volumes:
      - ./pg_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U trailsnap -d trailsnap -p 5432"]
      interval: 5s
      timeout: 5s
      retries: 5
      start_period: 10s

  server:
    image: siyuan044/trailsnap-server:latest
    restart: always
    expose: [ "8000" ]
    ports: [ "8800:8000" ]
    networks: [ app-network ]
    volumes:
      - ./data:/app/data        # 挂载数据目录
      - F:\Photos:/app/Photos/  # 挂载本地照片目录
    environment:
      - TZ=Asia/Shanghai
      - DB_URL=postgresql://trailsnap:trailsnap@postgres:5432/trailsnap
      - RAILWAY_DB_URL=postgresql://trailsnap:trailsnap@postgres:5432/railway
      - AI_API_URL=http://ai:8001
    depends_on:
      postgres:
        condition: service_healthy
        restart: true

  ai:
    image: siyuan044/trailsnap-ai:latest
    restart: always
    expose: [ "8001" ]
    ports: [ "8801:8001" ]
    networks: [ app-network ]
    volumes:
      - ./data:/app/data        # 挂载数据目录
    environment:
      - TZ: Asia/Shanghai

  frontend:
    image: siyuan044/trailsnap-frontend:latest
    restart: always
    ports: [ "8082:80" ]
    depends_on: [ server ]
    networks: [ app-network ]
    environment:
      - TZ: Asia/Shanghai

networks:
  app-network:
    driver: bridge
```

3. 启动服务

```bash
docker-compose up -d
```

### 源码部署

[源码部署](http://localhost:5173/docs/dev/guide.html)


## 📂 目录结构

```
TrailSnap/
├── package/
│   ├── server/      # 后端 FastAPI 服务
│   └── website/     # 前端 Vue 应用
│   └── ai/          # AI 微服务 (OCR/Face)
├── doc/             # 项目技术文档
└── ...
```

## 📚 文档

更多详细技术文档请参阅 `doc/` 目录：
- [架构设计文档](doc/architecture_design.md)
- [前端框架分析](doc/frontend_analysis.md)
- [后端框架分析](doc/backend_analysis.md)
- [开发者文档](doc/developer_guide.md)
- [用户指南](doc/user_guide.md)

## 🔍 其他

### QQ交流群

![QQ群](./doc/image/QQ1.jpg)

### 相关项目

- [InkTime](https://github.com/dai-hongtao/InkTime) InkTime 是一个可自托管的墨水屏电子相框。它用AI分析你的照片库，按值得回忆度打分，并按“历史上的今天”自动生成每日最具回忆价值的照片，让沉睡的记忆重新被看见。
