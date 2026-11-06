"""服务端渲染页面路由：登录页 + 管理后台各页面（页面级角色校验）。"""
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from .database import fetch_one
from .security import decode_token

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(include_in_schema=False)


async def page_user(request: Request) -> dict | None:
    """从 Cookie 解析页面访问者身份；未登录或失效返回 None。"""
    token = request.cookies.get("token")
    if not token:
        return None
    payload = decode_token(token)
    if payload is None:
        return None
    row = await fetch_one("SELECT * FROM users WHERE id = ? AND is_active = 1",
                          (payload.get("sub"),))
    if row is None:
        return None
    return {"display_name": row["display_name"], "role": row["role"]}


@router.get("/login")
async def login_page(request: Request):
    """登录页（公开）。"""
    return templates.TemplateResponse(request, "login.html")


async def _render_admin(request: Request, template: str, active: str):
    """管理页统一入口：未登录跳登录页，员工跳问答页，管理员正常渲染。"""
    user = await page_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=302)
    if user["role"] != "admin":
        return RedirectResponse("/", status_code=302)  # 员工无权进入后台
    # 新版 Starlette 签名：TemplateResponse(request, 模板名, 上下文)
    return templates.TemplateResponse(request, template, {
        "user": user, "active": active})


@router.get("/admin")
async def admin_dashboard(request: Request):
    """后台首页（概览统计）。"""
    return await _render_admin(request, "dashboard.html", "dashboard")


@router.get("/admin/kb")
async def admin_kb(request: Request):
    """制度知识库管理页。"""
    return await _render_admin(request, "kb.html", "kb")


@router.get("/admin/prompts")
async def admin_prompts(request: Request):
    """提示词模板管理页。"""
    return await _render_admin(request, "prompts.html", "prompts")


@router.get("/admin/audit")
async def admin_audit(request: Request):
    """对话审计页。"""
    return await _render_admin(request, "audit.html", "audit")
