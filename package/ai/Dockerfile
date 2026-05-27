# ---- 阶段 1: 编译 llama.cpp (CPU) ----
FROM python:3.12.12-slim as llama-builder

# 安装编译依赖
RUN apt-get update && apt-get install -y git cmake build-essential

# 克隆并编译 llama.cpp
RUN git clone https://github.com/ggerganov/llama.cpp.git /llama.cpp && \
    cd /llama.cpp && \
    cmake -B build && \
    cmake --build build --config Release -j $(nproc) && \
    cmake --install build --prefix /opt/llama

# ---- 阶段 2: 最终运行环境 ----
FROM python:3.12.12-slim

WORKDIR /app

# 从 builder 拷贝编译好的 native llama-server 及其动态链接库
COPY --from=llama-builder /opt/llama /usr/local/
ENV LD_LIBRARY_PATH="/usr/local/lib:/usr/local/lib64:${LD_LIBRARY_PATH}"
RUN ldconfig

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

# 复制项目所有文件到工作目录
COPY . .

# 复制依赖文件并安装
RUN pip install uv
RUN uv sync --extra cpu

# 暴露端口
EXPOSE 8001
# 核心：将虚拟环境的bin目录加入PATH
ENV PATH="/app/.venv/bin:$PATH"
# 运行应用
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
