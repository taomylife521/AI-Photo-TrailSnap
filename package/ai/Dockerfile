# 使用官方Python镜像作为基础镜像
# FROM python:3.12.12-alpine3.21
FROM python:3.12.12-slim

# 设置工作目录
WORKDIR /app

# 安装编译依赖（g++等），这是解决insightface编译失败的关键
RUN apt-get update && apt-get install -y --no-install-recommends --fix-missing \
    # insightface编译依赖
    build-essential \
    g++ \
    cmake \
    # OpenCV核心运行依赖（仅保留必需项）
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

# 先安装pip工具（确保能装wheel），再直接安装预编译的insightface
# RUN pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple \
#     # 优先尝试安装预编译版本（如果3.0.0不行，可换2.7.0等稳定版）
#     && pip install insightface==3.0.0 -f https://download.pytorch.org/whl/torch_stable.html -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制项目所有文件到工作目录
COPY . .

# 复制依赖文件并安装

RUN pip install uv -i https://pypi.tuna.tsinghua.edu.cn/simple
# RUN pip install -r requirements.txt

RUN uv sync --extra cpu

# 可选：清理编译依赖以减小镜像体积（如果对镜像体积敏感）
# RUN apt-get purge -y --auto-remove build-essential g++

# 暴露端口
EXPOSE 8001
# 核心：将虚拟环境的bin目录加入PATH
ENV PATH="/app/.venv/bin:$PATH"
# 运行应用
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]