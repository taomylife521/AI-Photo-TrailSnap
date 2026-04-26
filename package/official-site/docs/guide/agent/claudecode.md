# Claude Code

> 在 Claude Code 中使用 MiniMax-M2.7 模型进行 AI 编程。

## 安装 Claude Code

可参考 [Claude Code 文档](https://code.claude.com/docs/en/setup) 进行安装。

## 安装 trailsnap-cli skill

:::tabs
== Agent 自动安装

请将以下提示词复制给你的AI Agent（OpenClaw、Claude Code、Cursor、MaxClaw、AutoClaw、KimiClaw、TRAE、OpenCode等）, 它会引导你添加API Key并完成安装：

```text
帮我安装 trailsnap-cli 和 skill：https://trailsnap.cn/install.md
我的api url 是 http://localhost:8000
我的token 是 sk-cp-xxxxx
```

== 手动安装

根据环境选择安装方式（选择其中一种即可）：

- Node.js 安装：npm/npx 安装
- Python 安装：pip 安装

#### npm/npx 安装

```shell
# 安装 CLI
npm install -g trailsnap-cli

# 安装 CLI SKILL（必需）
npx skills add lc044/trailsnap  -y -g
```

#### pip 安装

```shell
# 安装 CLI
pip install trailsnap-cli

# 安装 CLI SKILL（必需）
npx skills add lc044/trailsnap  -y -g
```

#### 配置api url和 token

```shell
trailsnap config set --url <url> --token <token>
```

#### 验证

```shell
trailsnap photos list --limit 1
```
:::

## 使用skill

使用示例：

```
帮我查一下最近去了哪些地方
```

