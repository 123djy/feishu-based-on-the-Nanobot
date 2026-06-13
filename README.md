# Nanobot 飞书智能客服

基于 [Nanobot](https://github.com/nanobot) agent + DeepSeek API 的飞书智能客服机器人，支持 FAQ 知识库检索、工单管理和异步消息处理。

## 技术栈

| 层级 | 技术 |
|------|------|
| Agent 框架 | Nanobot（本地 AI agent，类似 Claude Code） |
| LLM | DeepSeek API（deepseek-chat） |
| 即时通讯 | 飞书开放平台（长连接 WebSocket + Webhook） |
| 工单系统 | MCP Server + SQLite |
| Web 框架 | Flask（message_router 备选方案） |
| 运行环境 | Python 3.11+（conda 环境 `nanobot`） |
| 容器化 | Docker + Docker Compose |

## 项目结构

```
.nanobot/workspace/
├── config.json                  # Nanobot agent 配置（模型、工具、MCP、频道）
├── AGENTS.md                    # Agent 系统提示词（客服人设 + 工作流程）
├── SOUL.md                      # Agent 人格定义
├── USER.md                      # 用户画像与偏好配置
├── HEARTBEAT.md                 # 心跳定时任务注册文件
├── README.md                    # 项目文档
│
├── feishu_long_connection.py    # 飞书长连接消息接收器（主入口，推荐）
├── message_router.py            # Flask 多平台 webhook 版（备选方案）
│
├── knowledge_base/
│   ├── general.md               # FAQ：账号、注册、密码、项目、上传、个人信息
│   └── billing.md               # FAQ：收费、套餐、发票、退款、API 额度
│
├── skills/
│   ├── faq/SKILL.md             # FAQ 知识库查询技能
│   └── ticket/SKILL.md          # 工单管理技能
│
├── mcp_servers/
│   └── ticket_server.py         # MCP 工单服务（SQLite，JSON-RPC 2.0）
│
├── memory/
│   └── MEMORY.md                # 用户历史记录（长期记忆）
│
├── eval/
│   ├── eval_bot.py              # 客服机器人评测脚本（功能/工单/鲁棒性/冒烟）
│   ├── eval_http.py             # HTTP 端点评测脚本（/health, /webhook/feishu）
│   ├── run_eval.bat             # Windows 评测启动脚本
│   └── run_eval.sh              # Linux/Mac 评测启动脚本
│
├── Dockerfile                   # Docker 镜像构建文件
├── docker-compose.yml           # Docker Compose 部署配置
├── .env.example                 # 环境变量模板
└── .gitignore                   # Git 忽略规则
```

## 工作流程

```
用户在飞书发消息
  → 飞书 WebSocket 推送到 feishu_long_connection.py
  → 去重检查（已处理的消息跳过）
  → 后台线程调用 nanobot agent（DeepSeek）
  → Agent 按 AGENTS.md 工作流程执行：
      1. cat memory/MEMORY.md（查历史记录）
      2. 判断问题类型：
         - FAQ 类 → cat knowledge_base/general.md 和/或 billing.md
         - 工单类 → 通过 MCP ticket_server 工具操作
      3. 匹配知识库 Q&A → 生成回复
      4. 知识库无匹配 → 通过 MCP 创建工单转人工
      5. 更新 memory/MEMORY.md 用户记录
  → 回复发回飞书
```

## 快速开始

### 1. 环境准备

```bash
# 克隆仓库
git clone <your-repo-url>
cd nanobot-workspace

# 创建 conda 环境
conda create -n nanobot python=3.11
conda activate nanobot

# 安装依赖
pip install lark-oapi flask requests
```

### 2. 配置环境变量

```powershell
# 复制环境变量模板
cp .env.example .env

# 编辑 .env，填入你的真实密钥
# FEISHU_APP_ID=cli_xxxxxxxxxxxxxxxx
# FEISHU_APP_SECRET=your_secret
# DEEPSEEK_API_KEY=sk-your_key
```

或者在 PowerShell 中临时设置：

```powershell
$env:DEEPSEEK_API_KEY="你的key"
$env:FEISHU_APP_ID="你的飞书app_id"
$env:FEISHU_APP_SECRET="你的飞书app_secret"
```

### 3. 配置 Nanobot

编辑 `config.json`：

- `agents.defaults.model` — 模型名（deepseek-chat）
- `providers.deepseek.apiKey` — API key（可用 `${DEEPSEEK_API_KEY}` 环境变量）
- `tools.mcpServers.ticket_server` — MCP 工单服务配置
- `channels.feishu` — 飞书频道配置

### 4. 启动

**推荐方式 — 长连接模式：**

```powershell
conda activate nanobot
python feishu_long_connection.py
```

**备选方式 — Webhook 模式：**

```powershell
conda activate nanobot
python message_router.py
# 服务运行在 http://localhost:8080
# Webhook URL: http://your-server:8080/webhook/feishu
# Health Check: http://your-server:8080/health
```

## Docker 部署

```bash
# 构建并启动
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止
docker-compose down
```

## 知识库管理

FAQ 知识库使用 Markdown 格式，存储在 `knowledge_base/` 目录：

- **general.md** — 通用问题：账号注册、密码重置、团队管理、项目操作、文件上传、技术支持
- **billing.md** — 付费问题：套餐对比、升级降级、退款政策、发票下载、API 额度

### 添加新 FAQ

编辑对应的 `.md` 文件，按以下格式添加：

```markdown
## Q: 问题标题

答案内容...

---
```

## MCP 工单系统

`mcp_servers/ticket_server.py` 实现了完整的 JSON-RPC 2.0 MCP Server，提供以下工具：

| 工具 | 功能 | 必填参数 |
|------|------|----------|
| `create_ticket` | 创建工单 | title, description, user_id |
| `get_ticket` | 查询工单详情 | ticket_id |
| `list_user_tickets` | 查询用户所有工单 | user_id |
| `update_ticket` | 更新工单状态/备注 | ticket_id |

工单优先级：`low` / `medium` / `high` / `urgent`

工单状态流转：`open` → `in_progress` → `resolved` → `closed`

## 评测系统

### Bot 评测（eval_bot.py）

评测客服机器人的功能正确性、响应质量、延迟性能和鲁棒性：

```bash
# 运行全部评测
python eval/eval_bot.py

# 只跑冒烟测试
python eval/eval_bot.py --suite smoke

# 只跑工单评测
python eval/eval_bot.py --suite tickets

# 使用 agent 模式（含工具调用）
python eval/eval_bot.py --agent

# 输出 JSON 报告
python eval/eval_bot.py --output report.json
```

评测套件：

| 套件 | 说明 | 用例数 |
|------|------|--------|
| smoke | 冒烟测试 — 基本连通性 | 3 |
| functional | 功能测试 — 问答正确性 | 5 |
| tickets | 工单测试 — CRUD 操作 | 4 |
| robustness | 鲁棒性测试 — SQL注入/越权/乱码 | 4 |

### HTTP 端点评测（eval_http.py）

对已部署的 `message_router.py` 服务进行 HTTP 端点测试：

```bash
# 测试本地服务
python eval/eval_http.py

# 测试远程服务
python eval/eval_http.py --url http://your-server:8080

# 输出 JSON 报告
python eval/eval_http.py --output http_report.json
```

## Agent 行为定义

### AGENTS.md — 系统提示词

定义了客服 Agent 的完整行为规范：
- **身份**：专业产品客服专家
- **原则**：知识库优先、坦诚不知、记住用户、多语言适配、及时升级
- **回复风格**：简洁完整、关键信息加粗、结尾询问、共情处理
- **工作流程**：读记忆 → 判断类型 → 查知识库 → 回复 → 更新记忆

### SOUL.md — 人格定义

定义 Agent 的核心价值观和沟通风格。

### USER.md — 用户画像

定义目标用户的角色、技术栈、偏好，帮助 Agent 更好地适配回复风格。

## HEARTBEAT.md — 定时任务

通过 Nanobot cron 注册定时任务，Agent 会定期检查此文件并执行 `Active Tasks` 中列出的任务：

```
cron add --name heartbeat --schedule "every 30m" --message "Check HEARTBEAT.md"
```

## 环境变量

| 变量 | 说明 | 必填 |
|------|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | 是 |
| `FEISHU_APP_ID` | 飞书应用 ID | 是 |
| `FEISHU_APP_SECRET` | 飞书应用密钥 | 是 |

## 注意事项

- `.env` 文件包含真实密钥，**切勿提交到 Git**
- `tickets.db` 是 SQLite 数据库文件，已在 `.gitignore` 中排除
- `config.json` 中的 API key 支持 `${ENV_VAR}` 环境变量引用
- 飞书长连接模式（`feishu_long_connection.py`）比 Webhook 模式更稳定，推荐生产使用
