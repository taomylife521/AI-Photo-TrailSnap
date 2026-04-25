#!/usr/bin/env python
# -*- coding: utf-8 -*-

import asyncio
import logging
import os
from dotenv import load_dotenv

# 使用当前脚本所在目录作为基准路径，确保无论在哪执行都能找到 package/server/data/.env
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')

if not os.path.exists(DATA_DIR):
    os.mkdir(DATA_DIR)
load_dotenv(os.path.join(DATA_DIR, '.env'))

from app.api.mcp import mcp_server

# 简单配置日志，防止日志污染标准输出导致 MCP 客户端解析失败
logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

if __name__ == "__main__":
    mcp_server.run()
