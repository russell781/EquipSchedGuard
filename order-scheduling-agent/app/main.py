"""FastAPI 应用入口：注册路由、错误处理、静态页面，启动时初始化数据库与知识库。"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .database import init_db
from .errors import register_exception_handlers
from .kb_store import seed_from_files
from .prompt_store import seed_default_template
from .retrieval import load_documents
from .routes_admin import router as admin_router
from .routes_chat import router as chat_router
from .routes_pages import router as pages_router

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    """启动钩子：建库建表 → 默认提示词种子 → 制度文档种子 → 加载向量缓存。"""
    await init_db()
    await seed_default_template()   # 提示词表为空时写入默认模板
    await seed_from_files()         # 知识库为空时导入 knowledge_base/ 示例制度
    await load_documents()          # 从数据库加载切片向量到内存
    yield


app = FastAPI(title="订单排产与设备异常智能体系统",
              lifespan=lifespan)

# 统一错误格式（AppError / 参数校验 / 兜底异常）
register_exception_handlers(app)

# 业务路由：员工问答 / 管理后台 API / 服务端渲染页面
app.include_router(chat_router)
app.include_router(admin_router)
app.include_router(pages_router)


@app.get("/", include_in_schema=False)
async def index():
    """首页：员工问答单页界面。"""
    return FileResponse(STATIC_DIR / "index.html")


# 静态资源（如需拆分 css/js 文件可放入 static 目录）
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
