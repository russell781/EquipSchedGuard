# 订单排产与设备异常智能体系统 · 可演示 MVP

FastAPI（异步）+ SQLite + 单页 HTML 的**完整可演示版本**：员工自然语言发起排产建议 → 检索制度 → 生成草稿（人工确认）→ 管理员审批 → 生效为当日计划，全程审计留痕。

## 功能

- `POST /api/v1/chat`：SSE 流式问答（meta / status / token / sources / done / error 六种事件帧）
- 会话与消息存 SQLite（沿用阶段 1 表结构），每次请求携带最近 6 轮历史
- 制度知识库检索（`knowledge_base/` 下的 .md/.txt，启动时加载切片）
- 单页聊天界面：打字机效果、"正在检索制度…"状态、回答底部制度来源卡片
- 登录鉴权（JWT）、会话列表、历史消息加载；统一错误码 + 中文错误信息
- **受约束的智能体执行循环**：意图路由 → 决策循环（最多 5 轮）→ 建草稿前人工确认 → 提交审批
- **完整审批闭环**：管理员在后台「排产审批」页同意/拒绝，同意后自动生成「当日计划」生效版本
- 设备异常影响分析、决策日志、工具调用审计（追加式留痕）

## 主链路演示（可端到端跑通）

```text
员工问答页「帮我报插单导致的排单异常，订单 SO-1001，请求交期 2026-11-09，数量 120 件」
  → 智能体执行循环：查制度 → 取快照 → 输入校验
  → 【挂起，等待员工确认草稿】
  → 员工确认 → 仿真 → 结果校验 → 提交审批（PENDING_APPROVAL）
  → 管理员登录后台「🗓️ 排产审批」→ 点「同意」
  → 自动生成当日计划 → 在「📋 当日计划」页可见生效版本
```

护栏（均已验证）：模型无审批权、无生效权、无设备控制权；跳过校验直接建草稿会被状态机拒绝（409）；未确认不建草稿。

## 运行

```bash
cd order-scheduling-agent
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

浏览器打开 `http://localhost:8000`，演示账号：`employee / 123456`（管理员 `admin / 123456`）。

## 大模型配置

默认接入**通义千问**（OpenAI 兼容协议），未配置 Key 时自动进入 **Mock 演示模式**（本地模拟流式回答，可完整演示检索与引用）。

```bash
# Windows PowerShell 示例（通义千问）
$env:LLM_API_KEY="你的百炼API Key"          # 必填
$env:LLM_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"  # 默认已填，可不设
$env:LLM_MODEL="qwen-plus"                 # 默认已填，可不设
uvicorn app.main:app --port 8000
```

DeepSeek 则设 `LLM_BASE_URL=https://api.deepseek.com/v1`、`LLM_MODEL=deepseek-chat`。

### 智能体决策引擎开关

执行循环的「工具决策」可选择走真实大模型，或本地规则引擎：

| 环境变量 | 取值 | 含义 |
|---|---|---|
| `LLM_DECIDE` | `auto`（默认） | 配置了 `LLM_API_KEY` 就用真实模型决策，否则回退规则引擎 |
| `LLM_DECIDE` | `true` | 强制用真实模型做决策（需已配 Key） |
| `LLM_DECIDE` | `false` | 只用本地规则引擎，不调模型做决策 |

> 无论哪种模式，**工具白名单、凭证链、状态机校验、建草稿前人工确认**都是服务端硬约束，模型无法绕过。真实模型决策失败或返回越权工具时会自动回退规则引擎，系统始终可用。

完整环境变量见 `app/config.py`：`LLM_API_KEY / LLM_BASE_URL / LLM_MODEL / LLM_MOCK / LLM_DECIDE / JWT_SECRET / JWT_EXPIRE_MINUTES`。

## 目录

```
app/
  main.py        # 应用入口、启动钩子
  config.py      # 环境变量配置
  database.py    # SQLite 建表与访问
  security.py    # JWT 与密码哈希
  schemas.py     # 请求校验
  errors.py      # 统一错误码与中文信息
  llm.py         # 大模型流式客户端（可替换供应商 / Mock / 决策 JSON 调用）
  retrieval.py   # 制度文档加载与检索（可升级为向量检索）
  routes_chat.py # /chat、/sessions、/auth/login 路由
  agent_loop.py  # 受约束执行循环（RuleDecisionEngine / LLMDecisionEngine）
  agent_tools.py # Function Calling 工具规范 + Skill 白名单
static/index.html  # 单页聊天界面（原生 JS，SSE 解析 + 打字机）
knowledge_base/    # 制度文档（示例三份，可直接增删）
data/chat.db       # SQLite 数据文件（首次运行自动创建）
```

## 说明

- 当前检索为离线轻量实现（bigram 相似度），后续可在 `retrieval.py` 内替换为向量检索，接口不变。
- 生产部署前请修改 `JWT_SECRET`，并按需加限流（42901 已预留错误码）。

---

## 管理后台（新增）

- 入口：`http://localhost:5000/login`，管理员 `admin / 123456` 登录后进入 `/admin`；员工登录进入问答页 `/`。
- 页面：概览 `/admin`、**排产审批 `/admin/schedule`**、**当日计划 `/admin/plans`**、制度知识库 `/admin/kb`、提示词模板 `/admin/prompts`、对话审计 `/admin/audit`（Jinja2 服务端渲染，SaaS 布局）。
- 鉴权：JWT 双通道（接口 Bearer 头 / 页面 HttpOnly Cookie）；`/api/v1/admin/**` 接口级 `admin_required`，非管理员 40302；员工访问后台页面重定向问答页。
- 知识库：上传 .md/.pdf → 自动切片 → 离线向量化（bigram 哈希 512 维）入库 → 检索立即生效；支持删除、重新切片；原文件存 `data/kb_files/`。
- 提示词：存 `prompt_templates` 表，默认模板为种子数据；保存即生效（5 秒缓存），支持历史版本与回滚；`{{制度条文}}` 占位符运行时替换。
- 对话审计：按员工/时间/标记筛选，查看消息详情（含制度来源），会话级"疑似违规报销"标记/取消（含备注），管理操作写 `audit_logs` 追加式留痕。
- **排产审批与当日计划**：`/api/v1/agent/change-requests`（列表）、`/approve`（同意→生成当日计划）、`/reject`（拒绝）、`/daily-plans`（生效计划列表）。审批仅管理员可调，不注册给模型。
- 新增错误码：40302 / 40010 / 40011 / 40012 / 40410 / 40411。
