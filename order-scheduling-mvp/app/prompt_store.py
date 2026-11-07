"""提示词模板存储：存数据库、默认模板种子、编辑立即生效（短缓存）、版本回滚。"""
import time

from .database import connect, fetch_all, fetch_one, new_id, now_iso
from .errors import err_bad_prompt, err_prompt_not_found

# 默认系统提示词（仅作为首次初始化的种子数据写入数据库，运行期一律读库）
DEFAULT_TEMPLATE = (
    "你是公司订单排产与设备异常智能助手，只根据提供的制度条文回答，"
    "不确定时明确说“制度中未找到”，回答末尾附引用来源，不得编造报销标准。"
    "\n\n【制度条文】\n{{制度条文}}"
)

# 生效模板短缓存：避免每次问答都查库，修改后最多 5 秒内全量生效
_cache: dict = {"content": None, "ts": 0.0}
CACHE_TTL = 5.0


async def seed_default_template():
    """首次启动：若模板表为空，写入默认模板并置为生效。"""
    row = await fetch_one("SELECT COUNT(*) AS n FROM prompt_templates")
    if row["n"] == 0:
        await _insert(DEFAULT_TEMPLATE, None)


async def _insert(content: str, user_id: str | None) -> int:
    """插入新版本并置为唯一生效，返回版本号。"""
    db = await connect()
    try:
        cur = await db.execute("SELECT COALESCE(MAX(version),0) AS v FROM prompt_templates")
        version = (await cur.fetchone())["v"] + 1
        await db.execute("UPDATE prompt_templates SET is_active = 0")  # 旧版全部停用（保留历史）
        await db.execute(
            "INSERT INTO prompt_templates(id, content, version, is_active, updated_by, created_at)"
            " VALUES(?,?,?,1,?,?)",
            (new_id(), content, version, user_id, now_iso()))
        await db.commit()
    finally:
        await db.close()
    _cache["content"] = None  # 清缓存，立即生效
    return version


async def get_active() -> dict:
    """读取当前生效模板（带 5 秒缓存）。"""
    if _cache["content"] is not None and time.time() - _cache["ts"] < CACHE_TTL:
        return {"content": _cache["content"]}
    row = await fetch_one(
        "SELECT p.*, u.display_name AS updater FROM prompt_templates p"
        " LEFT JOIN users u ON u.id = p.updated_by WHERE p.is_active = 1")
    if row is None:
        # 兜底：无生效模板时使用默认模板
        return {"id": None, "content": DEFAULT_TEMPLATE, "version": 0,
                "updater": None, "created_at": None}
    _cache.update(content=row["content"], ts=time.time())
    return dict(row)


async def render(sources: list[dict]) -> str:
    """渲染运行时系统提示词：把 {{制度条文}} 占位符替换为检索结果。

    模板未含占位符时，制度条文自动追加到末尾。
    """
    template = (await get_active())["content"]
    if sources:
        kb_text = "\n".join(
            f"{i}. 来源《{s['doc_name']}》：{s['snippet']}"
            for i, s in enumerate(sources, 1))
    else:
        kb_text = "（本次未检索到相关制度片段。）"
    if "{{制度条文}}" in template:
        return template.replace("{{制度条文}}", kb_text)
    return template + "\n\n【制度条文】\n" + kb_text


async def create_version(content: str, user_id: str) -> int:
    """管理员保存新模板：校验后立即生效。"""
    content = content.strip()
    if not content or len(content) > 8000:
        raise err_bad_prompt()
    return await _insert(content, user_id)


async def activate_version(prompt_id: str):
    """回滚：把指定历史版本重新置为生效。"""
    row = await fetch_one("SELECT id FROM prompt_templates WHERE id = ?", (prompt_id,))
    if row is None:
        raise err_prompt_not_found()
    db = await connect()
    try:
        await db.execute("UPDATE prompt_templates SET is_active = 0")
        await db.execute("UPDATE prompt_templates SET is_active = 1 WHERE id = ?", (prompt_id,))
        await db.commit()
    finally:
        await db.close()
    _cache["content"] = None


async def list_versions() -> list[dict]:
    """历史版本列表（新的在前）。"""
    rows = await fetch_all(
        "SELECT p.id, p.version, p.is_active, p.content, p.created_at,"
        " u.display_name AS updater FROM prompt_templates p"
        " LEFT JOIN users u ON u.id = p.updated_by ORDER BY p.version DESC")
    return [dict(r) for r in rows]
