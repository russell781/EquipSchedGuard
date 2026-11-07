"""请求 / 响应的 Pydantic 模型与字段校验。"""
from pydantic import BaseModel, Field, field_validator

from .errors import err_bad_session, err_question_empty, err_question_too_long


class LoginIn(BaseModel):
    """登录请求体。"""
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class ChatIn(BaseModel):
    """问答请求体：session_id 可空（为空则自动创建新会话）。"""
    session_id: str | None = None
    question: str

    @field_validator("question")
    @classmethod
    def check_question(cls, v: str) -> str:
        """问题去空格后非空且不超过 2000 字。"""
        v = v.strip()
        if not v:
            raise err_question_empty()
        if len(v) > 2000:
            raise err_question_too_long()
        return v

    @field_validator("session_id")
    @classmethod
    def check_session_id(cls, v: str | None) -> str | None:
        """session_id 若提供，必须是合法 UUID 格式。"""
        if v is None or v == "":
            return None
        import uuid
        try:
            uuid.UUID(v)
        except ValueError:
            raise err_bad_session()
        return v
