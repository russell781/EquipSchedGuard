"""统一错误处理：所有错误均返回 {code, message(中文), detail?}。"""
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    """业务异常：携带错误码、中文信息与 HTTP 状态码。"""

    def __init__(self, http_status: int, code: int, message: str, detail: str | None = None):
        self.http_status = http_status
        self.code = code
        self.message = message
        self.detail = detail
        super().__init__(message)


# ---------- 常用错误快捷构造函数 ----------
def err_question_empty() -> AppError:
    return AppError(400, 40001, "问题不能为空")


def err_question_too_long() -> AppError:
    return AppError(400, 40002, "问题长度不能超过 2000 字")


def err_bad_session() -> AppError:
    return AppError(400, 40003, "session_id 格式不正确")


def err_unauthorized() -> AppError:
    return AppError(401, 40101, "登录已过期，请重新登录")


def err_forbidden() -> AppError:
    return AppError(403, 40301, "无权访问该会话")


def err_admin_only() -> AppError:
    return AppError(403, 40302, "无权限执行此操作")


def err_bad_file_type() -> AppError:
    return AppError(400, 40010, "文件格式不支持，仅支持 .md / .pdf")


def err_pdf_parse() -> AppError:
    return AppError(400, 40011, "PDF 文本提取失败，请检查文件是否损坏或为扫描件")


def err_bad_prompt() -> AppError:
    return AppError(400, 40012, "提示词不能为空且不超过 8000 字")


def err_doc_not_found() -> AppError:
    return AppError(404, 40410, "文档不存在或已删除")


def err_prompt_not_found() -> AppError:
    return AppError(404, 40411, "提示词版本不存在")


def err_session_not_found() -> AppError:
    return AppError(404, 40401, "会话不存在或已删除")


def err_llm() -> AppError:
    return AppError(500, 50001, "大模型服务暂时不可用，请稍后重试")


def err_retrieve() -> AppError:
    return AppError(500, 50002, "制度检索失败，请稍后重试")


def err_internal() -> AppError:
    return AppError(500, 50000, "服务器内部错误，请联系管理员")


def error_body(code: int, message: str, detail: str | None = None) -> dict:
    """组装统一错误响应体。"""
    body = {"code": code, "message": message}
    if detail:
        body["detail"] = detail
    return body


def register_exception_handlers(app):
    """把统一错误格式注册到 FastAPI 应用。"""

    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError):
        return JSONResponse(status_code=exc.http_status,
                            content=error_body(exc.code, exc.message, exc.detail))

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_: Request, exc: RequestValidationError):
        # 参数校验失败：取第一条错误信息，翻译为中文提示
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(x) for x in first.get("loc", []))
        return JSONResponse(status_code=400,
                            content=error_body(40001, f"请求参数不合法：{loc}",
                                               first.get("msg")))

    @app.exception_handler(Exception)
    async def handle_unknown(_: Request, exc: Exception):
        # 兜底异常：不暴露内部堆栈，仅返回通用中文提示
        return JSONResponse(status_code=500,
                            content=error_body(50000, "服务器内部错误，请联系管理员",
                                               str(exc)[:200]))
