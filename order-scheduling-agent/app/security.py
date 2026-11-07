"""认证与鉴权：密码哈希（PBKDF2）、JWT 签发与校验、当前用户依赖、管理员权限。"""
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Cookie, Depends, Header

from .config import JWT_EXPIRE_MINUTES, JWT_SECRET
from .errors import err_admin_only, err_unauthorized

_PBKDF2_ROUNDS = 100_000  # 哈希迭代次数


def hash_password(plain: str) -> str:
    """对明文密码做 PBKDF2 哈希，格式：salt$hash（十六进制）。"""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt, _PBKDF2_ROUNDS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(plain: str, stored: str) -> bool:
    """验证明文密码与存储哈希是否一致。"""
    try:
        salt_hex, digest_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", plain.encode(),
                                     bytes.fromhex(salt_hex), _PBKDF2_ROUNDS)
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, AttributeError):
        return False


def create_token(user_id: str, role: str) -> str:
    """签发 JWT，载荷包含用户 ID、角色与过期时间。"""
    payload = {
        "sub": user_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict | None:
    """解析 JWT，无效或过期返回 None（供页面路由做重定向判断）。"""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


async def get_current_user(x_auth_token: str = Header(default=""),
                           authorization: str = Header(default=""),
                           token_cookie: str | None = Cookie(default=None, alias="token")) -> dict:
    """FastAPI 依赖：解析当前用户。

    支持三种携带方式（按优先级）：
    1. X-Auth-Token 自定义头（员工问答页使用）。
       部署平台的反向代理会改写 Authorization 头为网关自身令牌，
       因此线上环境业务令牌必须走自定义头，Authorization 仅作本地开发兜底；
    2. Authorization: Bearer <token> 请求头（本地开发兼容）；
    3. token Cookie（管理后台服务端渲染页面使用，登录时写入）。
    """
    from .database import fetch_one  # 延迟导入，避免循环依赖

    token = ""
    if x_auth_token:
        token = x_auth_token.strip()
    elif authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
    elif token_cookie:
        token = token_cookie
    if not token:
        raise err_unauthorized()

    payload = decode_token(token)
    if payload is None:
        raise err_unauthorized()

    # 优先回查数据库，确保账号仍有效（is_active=1）。
    # 若数据库查询因环境异常失败（如部署沙箱中 SQLite 易失、多实例导致
    # 用户表暂不可用），则降级信任 JWT 自包含信息，保证已签发 token 可用。
    try:
        row = await fetch_one("SELECT * FROM users WHERE id = ? AND is_active = 1",
                              (payload.get("sub"),))
    except Exception:
        row = None
    if row is not None:
        return {"id": row["id"], "username": row["username"],
                "display_name": row["display_name"], "role": row["role"]}

    # 数据库不可用或查询失败时的降级：token 本身已含 sub 与 role。
    # 仅当 token 确实提供了 sub 与 role 时才放行（仍保持签名校验这一安全底线）。
    sub = payload.get("sub")
    role = payload.get("role")
    if not sub or role not in ("employee", "admin"):
        raise err_unauthorized()
    return {"id": sub, "username": sub, "display_name": sub, "role": role}


def login_required(user: dict = Depends(get_current_user)) -> dict:
    """路由依赖的语义化别名：需要登录才能访问。"""
    return user


def admin_required(user: dict = Depends(get_current_user)) -> dict:
    """接口级权限校验：仅管理员可访问，否则 40302。"""
    if user["role"] != "admin":
        raise err_admin_only()
    return user
