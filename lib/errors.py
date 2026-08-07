# lib/errors.py — 统一错误处理（无降级，中文分类错误信息）


class DashScopeError(Exception):
    """百炼 API 统一错误类"""

    def __init__(self, code: str, message: str, status_code: int = 500):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def parse_dashscope_error(status: int, body: dict) -> DashScopeError:
    """根据 HTTP 状态码和响应体解析百炼 API 错误"""
    if status == 401:
        return DashScopeError(
            "INVALID_API_KEY",
            "API Key 无效或已过期，请检查后重新输入",
            401,
        )
    elif status == 404:
        return DashScopeError(
            "MODEL_NOT_FOUND",
            "模型名称错误或不可用，请确认模型名正确",
            404,
        )
    elif status == 429:
        return DashScopeError(
            "RATE_LIMIT",
            "请求过于频繁，请稍后再试",
            429,
        )
    elif status in (500, 502, 503):
        return DashScopeError(
            "SERVER_ERROR",
            "百炼服务暂时不可用，请稍后重试",
            status,
        )
    else:
        msg = (
            body.get("message")
            or body.get("error", {}).get("message")
            or (body.get("errors", [{}])[0].get("message") if body.get("errors") else "")
            or "未知错误"
        )
        return DashScopeError("UNKNOWN", f"请求失败：{msg}", status)


def create_timeout_error(module: str) -> DashScopeError:
    """创建超时错误"""
    return DashScopeError(
        "TIMEOUT",
        f"{module}请求超时，请检查网络连接后重试",
        504,
    )
