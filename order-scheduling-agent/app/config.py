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
# 例：通义千问  LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
# 例：DeepSeek  LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

# 未配置 Key 时自动进入 Mock 模式（本地演示用，返回模拟流式回答）
LLM_MOCK = os.getenv("LLM_MOCK", "auto")  # auto / true / false

# ---------- 登录令牌配置 ----------
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-please-change-in-production-32bytes")  # 生产环境务必修改
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "720"))  # 令牌有效期（分钟）

# 每次请求携带的最近历史轮数（1 轮 = 1 问 1 答）
HISTORY_ROUNDS = 6
