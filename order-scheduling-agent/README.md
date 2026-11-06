# 订单排产与设备异常智能体系统 · 员工问答入口

FastAPI（异步）+ SQLite + 单页 HTML 的最小可运行版本。

## 功能

- `POST /api/v1/chat`：SSE 流式问答（meta / status / token / sources / done / error 六种事件帧）
- 会话与消息存 SQLite（沿用阶段 1 表结构），每次请求携带最近 6 轮历史
- 制度知识库检索（`knowledge_base/` 下的 .md/.txt，启动时加载切片）
- 单页聊天界面：打字机效果、"正在检索制度…"状态、回答底部制度来源卡片
- 登录鉴权（JWT）、会话列表、历史消息加载；统一错误码 + 中文错误信息

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

未配置 Key 时自动进入 **Mock 演示模式**（本地模拟流式回答，可完整演示检索与引用）。

接入真实模型（OpenAI 兼容协议，可换供应商）：

```bash
# Windows PowerShell 示例（通义千问）
$env:LLM_API_KEY="你的Key"
$env:LLM_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
$env:LLM_MODEL="qwen-plus"
uvicorn app.main:app --port 8000
```

DeepSeek 则设 `LLM_BASE_URL=https://api.deepseek.com/v1`、`LLM_MODEL=deepseek-chat`。

## 目录

```
app/
  main.py        # 应用入口、启动钩子
  config.py      # 环境变量配置
  database.py    # SQLite 建表与访问
  security.py    # JWT 与密码哈希
  schemas.py     # 请求校验
  errors.py      # 统一错误码与中文信息
  llm.py         # 大模型流式客户端（可替换供应商 / Mock）
  retrieval.py   # 制度文档加载与检索（可升级为向量检索）
  routes_chat.py # /chat、/sessions、/auth/login 路由
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
- 页面：概览 `/admin`、制度知识库 `/admin/kb`、提示词模板 `/admin/prompts`、对话审计 `/admin/audit`（Jinja2 服务端渲染，SaaS 布局）。
- 鉴权：JWT 双通道（接口 Bearer 头 / 页面 HttpOnly Cookie）；`/api/v1/admin/**` 接口级 `admin_required`，非管理员 40302；员工访问后台页面重定向问答页。
- 知识库：上传 .md/.pdf → 自动切片 → 离线向量化（bigram 哈希 512 维）入库 → 检索立即生效；支持删除、重新切片；原文件存 `data/kb_files/`。
- 提示词：存 `prompt_templates` 表，默认模板为种子数据；保存即生效（5 秒缓存），支持历史版本与回滚；`{{制度条文}}` 占位符运行时替换。
- 对话审计：按员工/时间/标记筛选，查看消息详情（含制度来源），会话级"疑似违规报销"标记/取消（含备注），管理操作写 `audit_logs` 追加式留痕。
- 新增错误码：40302 / 40010 / 40011 / 40012 / 40410 / 40411。
