---
outline: [2, 3]
---

# Agent Skills

TrailSnap CLI 可以作为 Agent 工具（Skill）被无缝集成到各种 AI 编码助手或 Agent 平台中，例如 Claude Code、OpenClaw / Roo Code 等。通过让 Agent 调用 CLI，AI 能够直接获取、分析和查询您的相册数据，实现基于个人图库的智能问答。

## 1. Claude Code

[Claude Code](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview) 是直接在终端运行的 AI 助手。只要在环境中安装了 `trailsnap-cli`，Claude 就能自主调用命令。

**使用步骤：**

1. 全局安装 `trailsnap-cli` 并完成配置：
   ```bash
   npm install -g trailsnap-cli
   trailsnap config set --url <你的API地址> --token <你的Token>
   ```
2. 启动 Claude Code：
   ```bash
   claude
   ```
3. 直接通过自然语言让 Claude 查询相册：
   > "帮我使用 trailsnap 命令，查一下最近在西安拍的照片有哪些？"
   > "调用 trailsnap 获取我的相册列表，并总结一下。"

Claude 会自动在后台执行 `trailsnap` 相关命令，读取 JSON 输出并为您总结结果。

## 2. OpenClaw / Roo Code 等 IDE Agent

对于 OpenClaw、Roo Code (原 Cline) 等基于 IDE 的 Agent 插件，它们同样具备执行终端命令的能力。

**使用步骤：**

1. 确保您的终端环境已安装并配置好工具：
   ```bash
   pip install trailsnap-cli
   trailsnap config set --url <你的API地址> --token <你的Token>
   ```
2. （可选）在 Agent 的自定义指令（Custom Instructions / System Prompt）中，添加对 TrailSnap CLI 的说明，例如：
   ```text
   你可以使用 `trailsnap` 命令行工具来查询用户的照片、相册和位置数据。
   常用命令包括：`trailsnap photos list`、`trailsnap locations list` 等。
   如果需要查照片，请主动使用该命令获取数据。
   ```
3. 在对话框中直接提问：
   > "请使用 trailsnap 查询一下我标记为'已隐藏'的人物面孔有哪些？"

## 3. 其它 Agent 平台集成

如果您正在使用 Dify、Coze、FastGPT 或自研 Agent 框架，您可以将 CLI 包装为系统级工具（Tool）：

1. 创建一个**执行脚本命令**的工具节点。
2. 将命令固定为 `trailsnap <命令> [参数]`，由大模型传入具体参数。
3. 由于 CLI 输出的是标准格式的 JSON 数据，大模型可以直接解析这些数据并进行下一步的推理。