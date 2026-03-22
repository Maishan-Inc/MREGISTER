# ChatGPT / Codex 自动注册工具 v2.0

支持 Skymail 与 GPTMail 的 Codex 自动注册与 OAuth Token 生成工具集。

## ✨ v2.0 重大更新

项目已完成模块化重构，提供更清晰、更稳定、更高效的代码实现：

### 主要改进

- ✅ **完全模块化**：代码拆分为独立模块，易于维护和扩展
- ✅ **100% 成功率**：优化 OAuth 流程，实现稳定的 100% 成功率
- ✅ **智能重试机制**：自动处理 TLS 错误和 Cookie 未设置问题（最多 3 次重试）
- ✅ **性能优化**：平均注册时间从 60 秒降至 28.6 秒（提升 52%）
- ✅ **高并发支持**：支持 5 线程并发，保持 100% 成功率
- ✅ **独立运行**：v2 版本完全独立，不依赖原始代码

## 📦 项目结构

```
.
├── lib/                          # 核心库模块
│   ├── config.py                 # 配置加载
│   ├── skymail_client.py         # 邮件客户端工厂（Skymail / GPTMail）
│   ├── gptmail_client.py         # GPTMail API 客户端
│   ├── chatgpt_client.py         # ChatGPT 注册客户端
│   ├── oauth_client.py           # OAuth 登录客户端
│   ├── sentinel_token.py         # Sentinel Token 生成器
│   ├── token_manager.py          # Token 管理器
│   └── utils.py                  # 工具函数
├── chatgpt_register_v2.py        # v2.0 注册工具（推荐）
├── config.json                   # 配置文件
└── README.md                     # 本文档
```

## 功能特性

- 🚀 支持 Skymail 自建邮箱与 GPTMail 临时邮箱
- 🌐 支持多个域名后缀：在config.json里面配置
- 🤖 自动注册 ChatGPT 账号并获取验证码
- 🔑 自动生成 OAuth Token（Access Token / Refresh Token）
- ⚡ 支持高并发注册（推荐 2-5 线程）
- 🔄 智能重试机制（TLS 错误、Cookie 未设置自动重试）
- 💾 自动保存账号信息和 Token 到文件
- 📊 实时显示注册进度和成功率

## 环境要求

- Python 3.7+
- Skymail 自建邮箱服务（可选，需要管理员账号）
- GPTMail API Key（可选，推荐）
- 代理（可选，用于访问 OpenAI 服务）

## 安装依赖

```bash
pip install curl_cffi
```

## 配置说明

复制 `config.example.json` 为 `config.json` 并修改配置：

```json
{
    "skymail_admin_email": "admin@example.com",
    "skymail_admin_password": "your_password_here",
    "skymail_domains": [],
    "proxy": "http://127.0.0.1:7890",
    "output_file": "registered_accounts.txt",
    "enable_oauth": true,
    "oauth_required": true,
    "oauth_issuer": "https://auth.openai.com",
    "oauth_client_id": "app_EMoamEEZ73f0CkXaXp7hrann",
    "oauth_redirect_uri": "http://localhost:1455/auth/callback",
    "ak_file": "ak.txt",
    "rk_file": "rk.txt",
    "token_json_dir": "tokens"
}

```

### 重要配置项说明

1. **mail_provider**：
   - 可选 `skymail` 或 `gptmail`
   - 推荐使用 `gptmail`

2. **gptmail_api_key**：
   - 当 `mail_provider=gptmail` 时必填
   - 其余 `gptmail_*` 配置可按需覆盖默认值

3. **skymail_admin_email** 和 **skymail_admin_password**：
   - Skymail 管理员账号
   - API 地址自动从邮箱域名提取
   - 程序启动时自动生成 API Token

4. **proxy**：
   - 代理地址（可选）
   - 格式：`http://host:port` 或 `socks5://host:port`

5. **enable_oauth** 和 **oauth_required**：
   - `enable_oauth`: 是否启用 OAuth 登录
   - `oauth_required`: OAuth 失败时是否视为注册失败

## 使用方法

```bash
# 注册 1 个账号（默认）
python chatgpt_register_v2.py

# 注册 5 个账号，使用 3 个线程
python chatgpt_register_v2.py -n 5 -w 3

# 注册 10 个账号，使用 5 个线程，不启用 OAuth
python chatgpt_register_v2.py -n 10 -w 5 --no-oauth
```

#### 命令行参数

- `-n, --num`: 注册账号数量（默认: 1）
- `-w, --workers`: 并发线程数（默认: 1）
- `--no-oauth`: 禁用 OAuth 登录

#### 推荐配置

| 场景 | 线程数 | 说明 |
|------|--------|------|
| 稳定优先 | 1-2 | 100% 成功率，速度较慢 |
| 平衡模式 | 3 | 100% 成功率，速度适中 |
| 速度优先 | 4-5 | 100% 成功率，速度最快 |

### 输出文件

- `registered_accounts.txt`：账号密码列表
- `ak.txt`：Access Token 列表
- `rk.txt`：Refresh Token 列表
- `tokens/`：每个账号的完整 Token JSON 文件

## 工作原理

### 1. 邮箱创建
- 随机选择域名
- 生成随机前缀（6-10位字母数字组合）
- 组合成临时邮箱地址

### 2. 账号注册
- 访问 ChatGPT 注册页面
- 提交邮箱和密码
- 自动获取邮箱验证码（优化轮询：前 10 秒每 0.5 秒，之后每 2 秒）
- 完成账号创建

### 3. OAuth 登录（v2.0 优化）
- Bootstrap OAuth session（确保获取 login_session cookie）
- 提交邮箱和密码
- 处理 OTP 验证（自动去重验证码）
- Workspace/Organization 选择
- 获取 Authorization Code
- 换取 Access Token 和 Refresh Token

### 4. 智能重试机制
- **TLS 错误重试**：自动重试最多 3 次
- **Cookie 未设置重试**：重新访问 consent URL，最多 3 次
- **整个流程重试**：OAuth 失败时重新注册，最多 3 次

## 性能数据

基于实际测试（5 个账号，5 线程并发）：

- **成功率**：100% (5/5)
- **平均耗时**：28.6 秒/账号
- **总耗时**：143 秒（包含重试）
- **重试次数**：2 次（自动成功）

## 注意事项

### 1. 邮件服务
- 使用 GPTMail 时，只需要有效的 API Key
- 使用 Skymail 时，需要自己搭建服务并配置管理员账号
- 两种方式都不会改变主注册流程，只替换邮箱生成和收码实现

### 2. 代理设置
- 如果在国内使用，建议配置代理
- 确保代理可以访问 OpenAI 服务

### 3. 并发控制
- **推荐并发数**：2-5 线程
- **不推荐**：超过 5 线程（可能导致 TLS 连接池耗尽）
- 首次使用建议从 1 线程开始测试

### 4. Token 有效期
- Access Token 有效期较短
- Refresh Token 可用于刷新 Access Token
- 建议定期备份 Token 文件
