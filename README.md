# 🤖 飞书智能客服 Bot

基于 [Nanobot AI](https://pypi.org/project/nanobot-ai/) 学习learn_nanobot灵感, 构建飞书智能客服系统，具备意图识别、FAQ 知识库检索、工单管理等功能。
<img width="855" height="640" alt="image" src="https://github.com/user-attachments/assets/caae8d6c-ffaa-48c8-b5d2-2e38444da03f" />



---

## 架构概览

```
飞书消息 → Webhook → message_router.py (Flask :8080)
                        │
                        ├─ intent_recognizer.py（分层意图识别）
                        │   ├─ Layer 1: 关键词匹配（规则引擎，毫秒级）
                        │   └─ Layer 2: LLM 分类（DeepSeek API）
                        │
                        ├─ 闲聊 / 低置信度(unknown) → 本地直接回复
                        │
                        └─ 有效意图 → Nanobot Agent（subprocess 调用）
                                        │
                                        ├─ 知识库检索（knowledge_base/*.md）
                                        ├─ 工单管理（MCP ticket_server）
                                        └─ 生成回复 → 飞书消息 API 回复
```

---

## 意图分类体系

| 意图 | 触发条件 | 处理方式 | 消耗 Token |
|------|---------|---------|------------|
| `chitchat` | 你好/谢谢/在吗等 | 本地直接回复，不走 AI | ❌ 不消耗 |
| `general_faq` | 账号/注册/项目/上传等 | 读 `knowledge_base/general.md` | ✅ |
| `billing_faq` | 收费/套餐/发票/退款等 | 读 `knowledge_base/billing.md` | ✅ |
| `ticket` | 工单/转人工等 | MCP `ticket_server` 工具 | ✅ |
| `complaint` | 投诉/崩溃/数据丢失等 | 创建高优先级(urgent)工单 | ✅ |
| `unknown` | 意图模糊（confidence<0.6） | 反问用户澄清 | ❌ 不消耗 |

---

## 项目结构

```
.
├── message_router.py          # Flask 主服务，接收飞书 Webhook
├── intent_recognizer.py       # 分层意图识别（关键词正则 + LLM 语义分类）
├── bench.py                   # 线上评测脚本（15 条测试用例 + 并发测试）
├── config.json                # Nanobot 核心配置（模型/MCP/渠道）
├── Dockerfile                 # Docker 镜像
├── docker-compose.yml         # 容器编排
│
├── knowledge_base/            # FAQ 知识库（Markdown）
│   ├── general.md             # 通用问题（账号/密码/项目/上传/团队等）
│   └── billing.md             # 计费问题（套餐/发票/退款/API额度等）
│
├── skills/                    # Nanobot 技能定义
│   ├── faq/SKILL.md           # FAQ 查询技能
│   └── ticket/SKILL.md        # 工单管理技能
│
├── mcp_servers/               # MCP（Model Context Protocol）服务
│   └── ticket_server.py       # 工单 MCP Server（JSON-RPC + SQLite）
│
├── sessions/                  # 会话持久化（按用户隔离）
└── memory/                    # 用户记忆存储
```

---

## 核心流程详解

### 1. 消息接收（message_router.py）

Flask 服务监听 `http://0.0.0.0:8080`：

| 路由 | 方法 | 说明 |
|------|------|------|
| `/webhook/feishu` | POST | 飞书开放平台事件回调 |
| `/health` | GET | 健康检查（返回各平台可用状态） |

核心特性：
- **消息去重**：内存 Set 缓存 `message_id`，防止重复处理
- **删除消息过滤**：检测到 `"此消息已删除"` 等提示自动跳过

### 2. 意图识别（intent_recognizer.py）

三层识别策略，从上到下逐级降级：

```
Layer 1: 关键词正则匹配
  ├─ 命中 → confidence=1.0, source="rule", 返回意图
  └─ 未命中 ↓

Layer 2: DeepSeek LLM 语义分类
  ├─ temperature=0, max_tokens=200（极低成本）
  ├─ confidence≥0.6 → source="llm", 返回意图
  └─ confidence<0.6 ↓

Layer 3: 置信度门控
  └─ 反问澄清文案返回，不走 AI
```

### 3. Agent 处理

高置信度意图交给 Nanobot Agent 处理：

- 通过 `subprocess.run` 调用 `nanobot agent` 命令行
- Session 按 `feishu:{user_id}` 隔离，保持多轮对话上下文
- 携带路由提示（`INTENT_ROUTE_HINT`），让 Agent 直接执行对应操作，无需二次判断意图

Agent 内部工作流（由 AGENTS.md 定义）：
1. 读取用户记忆
2. 执行意图路由指令
3. 查找知识库答案
4. 禁止编造（未读知识库就回答视为违规）
5. 更新用户记忆

### 4. 工单系统（ticket_server.py）

标准 MCP Server，通过 JSON-RPC 2.0 over stdio 与 Nanobot 通信：

| 工具 | 参数 | 说明 |
|------|------|------|
| `create_ticket` | title, description, priority, user_id | 创建工单，自动生成 TK-xxxxxxxx ID |
| `get_ticket` | ticket_id | 查询单个工单详情 |
| `list_user_tickets` | user_id, status? | 查询用户历史工单，按时间倒序 |
| `update_ticket` | ticket_id, status?, comment? | 更新状态/添加备注，自动记录时间戳 |

数据持久化：SQLite（`tickets.db`），启动时自动建表。

### 5. 飞书回复

通过飞书开放平台 API 发送：
- 获取 `tenant_access_token`（app_id + app_secret）
- 调用 `POST /open-apis/im/v1/messages/{message_id}/reply`

---

## 快速开始

### 前置条件
- 安装nanobot
- Docker & Docker Compose
- DeepSeek API Key
- 飞书开放平台应用（App ID + App Secret）

### 配置环境变量

```bash
export DEEPSEEK_API_KEY=sk-your-key-here
export FEISHU_APP_ID=cli_xxxxxxxxxxxx
export FEISHU_APP_SECRET=your-app-secret
```

### 启动服务

```bash
docker-compose up -d
```

服务启动后：
- Webhook 接收：`http://localhost:8080/webhook/feishu`
- 健康检查：`http://localhost:8080/health`

### 配置飞书回调

在飞书开放平台 → 事件订阅中：
1. 请求地址配置为：`https://your-domain.com/webhook/feishu`
2. 订阅 `im.message.receive_v1` 事件
3. 飞书会自动发送 URL 验证请求，系统已内置处理

### 运行评测

```bash
python bench.py
```

---

## 技术栈

| 组件 | 技术 |
|------|------|
| Web 框架 | Flask |
| AI 引擎 | Nanobot AI |
| LLM | DeepSeek (deepseek-chat) |
| 意图识别 | 关键词正则 + LLM 语义分类 |
| 工单存储 | SQLite |
| MCP 协议 | JSON-RPC 2.0 over stdio |
| 部署 | Docker + Docker Compose |
| 消息渠道 | 飞书开放平台 |

---

## 扩展指南

### 接入更多平台

参考 `message_router.py` 的飞书实现，新增路由即可复用意图识别 + Agent 处理逻辑：

```python
@app.route("/webhook/dingtalk", methods=["POST"])
def dingtalk_webhook():
    # 1. 解析钉钉消息格式，提取 text + user_id
    # 2. 调用 intent_recognizer.recognize(text)
    # 3. 调用 NanobotBridge.send_to_nanobot(prompt, session_id)
    # 4. 调用钉钉回复 API
    ...
```

### 添加新的知识库

1. 在 `knowledge_base/` 下新建 `.md` 文件（Q&A 格式）
2. 在 `intent_recognizer.py` 中：
   - `KEYWORD_RULES` 添加关键词 → 新意图 ID
   - `INTENT_ROUTE_HINT` 添加意图 → 路由提示
   - `CLASSIFY_PROMPT` 中增加新类别说明
3. 在 `skills/faq/SKILL.md` 中补充读取指引

### 接入其他 LLM

修改 `config.json` 的 `providers` 配置即可，支持所有兼容 OpenAI API 协议的模型：

```json
"providers": {
  "openai": {
    "apiKey": "${OPENAI_API_KEY}",
    "apiBase": "https://api.openai.com",
    "apiType": "auto"
  }
}
```

---

## License

MIT
