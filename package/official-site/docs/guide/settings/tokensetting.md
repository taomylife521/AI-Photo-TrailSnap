# 设置 Token 与 trailsnap-cli工具使用

::: info Token 设置
使用token可以让第三方应用访问TrailSnap的后端API，你可以从TrailSnap后端获取一个Token。
:::

## 获取 Token

打开 “设置” -> “令牌管理” -> “新增令牌”，输入令牌名称和过期时间，验证账号登录密码之后即可获取到Token。

token示例：`ts_hV5nsCZJDheBvvmcd5L248IiAUnIwwZAn`

## API URL

TrailSnap API URL 为 `http://<TrailSnap 主机IP>:8800/`（取决于docker端口映射）。

```yaml
  server:
    image: siyuan044/trailsnap-server:latest
    restart: always
    expose: [ "8000" ]
    ports: [ "8800:8000" ]
```

这里的 `8800` 是TrailSnap的端口号，你可以根据实际情况修改。

## trailsnap-cli工具使用

### 安装 trailsnap-cli工具

你可以通过以下三种方式下载安装trailsnap-cli工具：

1. pip 安装

```bash
pip install trailsnap-cli

# 验证安装是否成功
trailsnap -v
```

2. npm 安装

```bash
npm install -g trailsnap-cli

# 验证安装是否成功
trailsnap -v
```

3. 从GitHub获取二进制文件

从GitHub获取二进制文件，然后添加到环境变量中。
下载地址：[https://github.com/LC044/TrailSnap/releases](https://github.com/LC044/TrailSnap/releases)

### 使用 trailsnap-cli工具

首次使用需要配置TrailSnap的API URL和Token（替换 `<url>` 和 `<token>` 为实际的URL和Token）。

```bash
trailsnap config set --url <url> --token <token>
```

配置完成之后使用简单查询命令验证是否成功。

```bash
trailsnap photos list --limit 5
```