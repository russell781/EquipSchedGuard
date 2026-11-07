"""智能体工具状态的存储层。

第一阶段同时提供内存实现（单元测试）与 SQLite 实现（服务运行）。
所有实体都以 JSON 文档保存，服务层负责状态机与凭证校验，避免把业务规则散落在 SQL 中。
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from .config import DB_PATH


class InMemoryAgentRepository:
    """进程内存仓储：供单元测试使用，不保证重启后数据保留。"""

    def __init__(self) -> None:
        self._objects: dict[tuple[str, str], dict[str, Any]] = {}
        self._idempotency: dict[str, dict[str, str]] = {}
        self._audits: list[dict[str, Any]] = []
        self._decision_logs: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    def initialize(self) -> None:
        """内存仓储无需建表，保留统一接口。"""

    def put_object(self, kind: str, entity: dict[str, Any]) -> None:
        """按实体类型与 ID 覆盖保存。"""
        with self._lock:
            self._objects[(kind, entity["id"])] = json.loads(json.dumps(entity, ensure_ascii=False))

    def get_object(self, kind: str, entity_id: str) -> dict[str, Any] | None:
        """读取实体；不存在时返回 None。"""
        with self._lock:
            entity = self._objects.get((kind, entity_id))
            return json.loads(json.dumps(entity, ensure_ascii=False)) if entity else None

    def list_objects(self, kind: str) -> list[dict[str, Any]]:
        """按实体类型列出全部对象（时间倒序）。"""
        with self._lock:
            items = [v for (k, v) in self._objects.items() if k[0] == kind]
            items.sort(key=lambda x: x.get("updated_at") or x.get("created_at") or "",
                       reverse=True)
            return json.loads(json.dumps(items, ensure_ascii=False))

    def find_idempotency(self, key: str) -> dict[str, str] | None:
        """按幂等键查找已创建的实体。"""
        with self._lock:
            item = self._idempotency.get(key)
            return dict(item) if item else None

    def put_idempotency(self, key: str, kind: str, entity_id: str, actor_id: str) -> None:
        """记录幂等键与实体的映射。"""
        with self._lock:
            self._idempotency[key] = {"kind": kind, "id": entity_id, "actor_id": actor_id}

    def append_audit(self, record: dict[str, Any]) -> None:
        """追加工具调用审计。"""
        with self._lock:
            self._audits.append(json.loads(json.dumps(record, ensure_ascii=False)))

    def list_audits(self, actor_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """查询最近审计记录，可按操作人过滤。"""
        with self._lock:
            items = [x for x in self._audits if actor_id is None or x.get("actor_id") == actor_id]
            return json.loads(json.dumps(items[-limit:][::-1], ensure_ascii=False))

    def append_decision_log(self, record: dict[str, Any]) -> None:
        """追加执行循环的决策日志（每轮一条）。"""
        with self._lock:
            self._decision_logs.append(json.loads(json.dumps(record, ensure_ascii=False)))

    def list_decision_logs(self, actor_id: str | None = None,
                           limit: int = 100) -> list[dict[str, Any]]:
        """按时间倒序读取决策日志，可按操作人过滤。"""
        with self._lock:
            items = [x for x in self._decision_logs
                     if actor_id is None or x.get("actor_id") == actor_id]
            return json.loads(json.dumps(items[-limit:][::-1], ensure_ascii=False))


class SQLiteAgentRepository:
    """SQLite 仓储：通用对象表 + 幂等表 + 追加式工具审计表。"""

    def __init__(self, db_path: str = DB_PATH) -> None:
        self.db_path = db_path
        self._lock = threading.RLock()

    def _connect(self) -> sqlite3.Connection:
        """创建短连接；SQLite 对短事务写入足够支撑当前单机试点。"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def initialize(self) -> None:
        """创建智能体工具链所需的增量表。"""
        with self._lock, self._connect() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS agent_objects (
                kind       TEXT NOT NULL,
                entity_id  TEXT NOT NULL,
                actor_id   TEXT,
                state      TEXT,
                payload    TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(kind, entity_id)
            );
            CREATE INDEX IF NOT EXISTS idx_agent_objects_actor
                ON agent_objects(kind, actor_id, updated_at);

            CREATE TABLE IF NOT EXISTS agent_idempotency (
                idem_key   TEXT PRIMARY KEY,
                kind       TEXT NOT NULL,
                entity_id  TEXT NOT NULL,
                actor_id   TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agent_tool_audits (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_id    TEXT NOT NULL,
                session_id  TEXT,
                tool_name   TEXT NOT NULL,
                status      TEXT NOT NULL,
                target_id   TEXT,
                detail      TEXT,
                created_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_agent_audit_actor
                ON agent_tool_audits(actor_id, created_at);

            CREATE TABLE IF NOT EXISTS agent_decision_logs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id      TEXT NOT NULL,
                actor_id    TEXT NOT NULL,
                session_id  TEXT,
                round_no    INTEGER NOT NULL,
                tool_name   TEXT NOT NULL,
                arguments   TEXT NOT NULL,
                duration_ms INTEGER NOT NULL,
                status      TEXT NOT NULL,
                summary     TEXT NOT NULL,
                created_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_agent_decision_actor
                ON agent_decision_logs(actor_id, created_at);
            """)

    def put_object(self, kind: str, entity: dict[str, Any]) -> None:
        """插入或更新实体，状态字段同时冗余为一列便于排查。"""
        state = str(entity.get("state") or entity.get("status") or "")
        payload = json.dumps(entity, ensure_ascii=False, sort_keys=True)
        now = str(entity.get("updated_at") or entity.get("created_at") or "")
        with self._lock, self._connect() as conn:
            conn.execute("""
                INSERT INTO agent_objects(kind, entity_id, actor_id, state, payload, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(kind, entity_id) DO UPDATE SET
                    actor_id = excluded.actor_id,
                    state = excluded.state,
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
            """, (kind, entity["id"], entity.get("actor_id"), state, payload,
                  str(entity.get("created_at") or now), now))

    def get_object(self, kind: str, entity_id: str) -> dict[str, Any] | None:
        """读取实体并反序列化 JSON。"""
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM agent_objects WHERE kind = ? AND entity_id = ?",
                (kind, entity_id)).fetchone()
        return json.loads(row[0]) if row else None

    def list_objects(self, kind: str) -> list[dict[str, Any]]:
        """按实体类型列出全部对象（updated_at 倒序）。"""
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM agent_objects WHERE kind = ? ORDER BY updated_at DESC",
                (kind,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def find_idempotency(self, key: str) -> dict[str, str] | None:
        """查询幂等键映射。"""
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT kind, entity_id, actor_id FROM agent_idempotency WHERE idem_key = ?",
                (key,)).fetchone()
        return {"kind": row[0], "id": row[1], "actor_id": row[2]} if row else None

    def put_idempotency(self, key: str, kind: str, entity_id: str, actor_id: str) -> None:
        """保存幂等键；重复键由主键约束保护。"""
        from .database import now_iso

        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO agent_idempotency(idem_key, kind, entity_id, actor_id, created_at)"
                " VALUES(?,?,?,?,?)",
                (key, kind, entity_id, actor_id, now_iso()))

    def append_audit(self, record: dict[str, Any]) -> None:
        """追加工具调用审计，不提供更新与删除。"""
        with self._lock, self._connect() as conn:
            conn.execute("""
                INSERT INTO agent_tool_audits(actor_id, session_id, tool_name, status, target_id, detail, created_at)
                VALUES(?,?,?,?,?,?,?)
            """, (record.get("actor_id"), record.get("session_id"), record.get("tool_name"),
                  record.get("status"), record.get("target_id"),
                  json.dumps(record.get("detail", {}), ensure_ascii=False),
                  record.get("created_at")))

    def list_audits(self, actor_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """读取最近工具审计。"""
        sql = """
            SELECT actor_id, session_id, tool_name, status, target_id, detail, created_at
            FROM agent_tool_audits
        """
        params: tuple[Any, ...] = ()
        if actor_id:
            sql += " WHERE actor_id = ?"
            params = (actor_id,)
        sql += " ORDER BY id DESC LIMIT ?"
        params += (limit,)
        with self._lock, self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [{
            "actor_id": r[0], "session_id": r[1], "tool_name": r[2], "status": r[3],
            "target_id": r[4], "detail": json.loads(r[5] or "{}"), "created_at": r[6],
        } for r in rows]

    def append_decision_log(self, record: dict[str, Any]) -> None:
        """追加执行循环决策日志，不提供更新与删除。"""
        with self._lock, self._connect() as conn:
            conn.execute("""
                INSERT INTO agent_decision_logs
                    (run_id, actor_id, session_id, round_no, tool_name, arguments,
                     duration_ms, status, summary, created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)
            """, (record.get("run_id"), record.get("actor_id"), record.get("session_id"),
                  record.get("round_no"), record.get("tool_name"),
                  json.dumps(record.get("arguments", {}), ensure_ascii=False),
                  record.get("duration_ms"), record.get("status"), record.get("summary"),
                  record.get("created_at")))

    def list_decision_logs(self, actor_id: str | None = None,
                           limit: int = 100) -> list[dict[str, Any]]:
        """读取最近决策日志。"""
        sql = """
            SELECT run_id, actor_id, session_id, round_no, tool_name, arguments,
                   duration_ms, status, summary, created_at
            FROM agent_decision_logs
        """
        params: tuple[Any, ...] = ()
        if actor_id:
            sql += " WHERE actor_id = ?"
            params = (actor_id,)
        sql += " ORDER BY id DESC LIMIT ?"
        params += (limit,)
        with self._lock, self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [{
            "run_id": r[0], "actor_id": r[1], "session_id": r[2], "round_no": r[3],
            "tool_name": r[4], "arguments": json.loads(r[5] or "{}"),
            "duration_ms": r[6], "status": r[7], "summary": r[8], "created_at": r[9],
        } for r in rows]
