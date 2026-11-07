"""全局配置：全部支持环境变量覆盖，方便切换部署环境与模型供应商。"""
import os
from pathlib import Path

# 项目根目录（app 的上一级）
BASE_DIR = Path(__file__).resolve().parent.parent

# SQLite 数据库文件路径
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "data" / "chat.db"))

# 制度知识库目录（.md / .txt 文档）
KB_DIR = Path(os.getenv("KB_DIR", str(BASE_DIR / "knowledge_base")))

# ---------- 大模型配置（OpenAI 兼容协议，可替换供应商） ----------
# 默认接入「通义千问」，OpenAI 兼容端点。如需切换供应商，改环境变量即可：
#   例：通义千问  LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
#   例：DeepSeek  LLM_BASE_URL=https://api.deepseek.com/v1
#   例：OpenAI    LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY = os.getenv("LLM_API_KEY", "")  # 阿里云百炼 API Key（DASHSCOPE_API_KEY）
LLM_BASE_URL = os.getenv(
    "LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1").rstrip("/")
# qwen-plus 通用对话性价比高；需要更强推理可换 qwen-max / qwen3.7-max 等
LLM_MODEL = os.getenv("LLM_MODEL", "qwen-plus")

# 未配置 Key 时自动进入 Mock 模式（本地演示用，返回模拟流式回答）
LLM_MOCK = os.getenv("LLM_MOCK", "auto")  # auto / true / false

# 智能体执行循环是否用真实大模型做「工具决策」（function calling 式）。
# true  → 用 LLMDecisionEngine（模型决定下一步调哪个工具，白名单+状态机兜底）
# false → 用 RuleDecisionEngine（本地规则，无需模型）
# auto  → 配置了 LLM_API_KEY 则用真实模型，否则回退规则引擎
LLM_DECIDE = os.getenv("LLM_DECIDE", "auto")  # auto / true / false

# ---------- 登录令牌配置 ----------
# 固定 JWT 密钥（不依赖环境变量）：部署沙箱可能多实例运行，
# 若各实例密钥不一致，会出现「登录签发的 token 在另一实例鉴权时签名失败」。
# 固定密钥可确保所有实例签发/验证一致。生产环境如需更强安全性，可改为环境变量注入。
JWT_SECRET = "order-scheduling-agent-jwt-secret-fixed-2026"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "720"))  # 令牌有效期（分钟）

# 每次请求携带的最近历史轮数（1 轮 = 1 问 1 答）
HISTORY_ROUNDS = 6
