"""SQLite 数据访问层：建表、种子数据与通用增删查封装。"""
import uuid
from datetime import datetime, timezone

import aiosqlite

from .config import DB_PATH
from .security import hash_password


def now_iso() -> str:
    """当前 UTC 时间的 ISO 字符串，统一作为时间字段格式。"""
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    """生成 UUID 主键。"""
    return str(uuid.uuid4())


async def connect() -> aiosqlite.Connection:
    """打开数据库连接（调用方负责关闭）。"""
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row  # 查询结果可按列名访问
    await db.execute("PRAGMA foreign_keys = ON")  # 开启外键约束
    return db


async def init_db():
    """初始化表结构（沿用阶段 1 设计）并写入预置账号。"""
    db = await connect()
    try:
        await db.executescript("""
        -- 用户表：员工 / 管理员两种角色
        CREATE TABLE IF NOT EXISTS users (
            id            TEXT PRIMARY KEY,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name  TEXT NOT NULL,
            role          TEXT NOT NULL CHECK(role IN ('employee','admin')),
            is_active     INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT NOT NULL
        );

        -- 会话表：归属某个用户
        CREATE TABLE IF NOT EXISTS conversations (
            id         TEXT PRIMARY KEY,
            user_id    TEXT NOT NULL REFERENCES users(id),
            title      TEXT NOT NULL,
            status     TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        -- 消息表：user / assistant / tool 三类
        CREATE TABLE IF NOT EXISTS messages (
            id              TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL REFERENCES conversations(id),
            role            TEXT NOT NULL,
            content         TEXT NOT NULL,
            tool_calls      TEXT,           -- JSON 字符串（预留）
            kb_refs         TEXT,           -- JSON 字符串：引用的制度片段
            token_usage     TEXT,           -- JSON 字符串：token 用量
            created_at      TEXT NOT NULL
        );

        -- 常用查询索引
        CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id, updated_at);
        CREATE INDEX IF NOT EXISTS idx_msg_conv  ON messages(conversation_id, created_at);

        -- 制度文档表：管理后台上传的制度原文件元数据
        CREATE TABLE IF NOT EXISTS kb_documents (
            id          TEXT PRIMARY KEY,
            doc_name    TEXT NOT NULL,          -- 原始文件名
            doc_type    TEXT NOT NULL,          -- md / pdf
            version     TEXT NOT NULL DEFAULT '1.0',
            file_path   TEXT NOT NULL,          -- 原文件存储路径
            status      TEXT NOT NULL DEFAULT 'active',  -- active / deleted
            uploaded_by TEXT REFERENCES users(id),
            created_at  TEXT NOT NULL
        );

        -- 制度切片表：切片正文 + 向量（JSON 字符串）
        CREATE TABLE IF NOT EXISTS kb_chunks (
            id          TEXT PRIMARY KEY,
            document_id TEXT NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL,
            content     TEXT NOT NULL,
            embedding   TEXT,                   -- JSON 数组：离线哈希向量
            created_at  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_chunk_doc ON kb_chunks(document_id);

        -- 提示词模板表：is_active=1 的为当前生效版本
        CREATE TABLE IF NOT EXISTS prompt_templates (
            id         TEXT PRIMARY KEY,
            content    TEXT NOT NULL,
            version    INTEGER NOT NULL,
            is_active  INTEGER NOT NULL DEFAULT 0,
            updated_by TEXT REFERENCES users(id),
            created_at TEXT NOT NULL
        );

        -- 审计日志表：管理操作追加式留痕，不提供修改/删除
        CREATE TABLE IF NOT EXISTS audit_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_id    TEXT,
            action      TEXT NOT NULL,          -- 如 kb.upload / prompt.update / audit.flag
            target_type TEXT,
            target_id   TEXT,
            detail      TEXT,                   -- JSON 摘要
            created_at  TEXT NOT NULL
        );
        """)

        # conversations 表增量列：疑似违规报销标记（会话级）
        cursor = await db.execute("PRAGMA table_info(conversations)")
        cols = {r[1] for r in await cursor.fetchall()}
        if "is_flagged" not in cols:
            await db.execute(
                "ALTER TABLE conversations ADD COLUMN is_flagged INTEGER NOT NULL DEFAULT 0")
        if "flag_remark" not in cols:
            await db.execute("ALTER TABLE conversations ADD COLUMN flag_remark TEXT")

        # 预置两个演示账号（已存在则跳过），密码均为 123456
        for username, name, role in [("employee", "演示员工", "employee"),
                                     ("admin", "演示管理员", "admin")]:
            cursor = await db.execute("SELECT id FROM users WHERE username = ?", (username,))
            if await cursor.fetchone() is None:
                await db.execute(
                    "INSERT INTO users(id, username, password_hash, display_name, role, created_at)"
                    " VALUES(?,?,?,?,?,?)",
                    (new_id(), username, hash_password("123456"), name, role, now_iso()))
        await db.commit()
    finally:
        await db.close()


async def fetch_one(sql: str, params: tuple = ()):
    """查询单条记录，返回 Row 或 None。"""
    db = await connect()
    try:
        cursor = await db.execute(sql, params)
        return await cursor.fetchone()
    finally:
        await db.close()


async def fetch_all(sql: str, params: tuple = ()):
    """查询多条记录，返回 Row 列表。"""
    db = await connect()
    try:
        cursor = await db.execute(sql, params)
        return await cursor.fetchall()
    finally:
        await db.close()


async def execute(sql: str, params: tuple = ()):
    """执行写操作并提交。"""
    db = await connect()
    try:
        await db.execute(sql, params)
        await db.commit()
    finally:
        await db.close()
