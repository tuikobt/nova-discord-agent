"""Explain provider failures without exposing their HTTP bodies or request data."""

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)

from app.domain.errors import DomainError


def explain_failure(error):
    if isinstance(error, DomainError):
        return error.code, str(error)
    if isinstance(error, (APITimeoutError, TimeoutError)):
        code, message = (
            "timeout",
            "Dịch vụ AI phản hồi quá lâu. Bạn có thể thử lại sau hoặc dùng /menu.",
        )
    elif isinstance(error, APIConnectionError):
        code, message = (
            "network_error",
            (
                "NOVA đã nhận tin nhắn nhưng chưa kết nối được dịch vụ AI. "
                "Cần kiểm tra mạng/proxy trên máy chạy bot; bạn vẫn dùng được /menu."
            ),
        )
    elif isinstance(error, AuthenticationError):
        code, message = (
            "authentication_error",
            (
                "Dịch vụ AI từ chối khóa truy cập. Kiểm tra cấu hình OpenAI trên máy chạy bot; "
                "không gửi API key trong chat. Bạn vẫn dùng được /menu."
            ),
        )
    elif isinstance(error, PermissionDeniedError):
        code, message = (
            "permission_denied",
            (
                "Tài khoản AI chưa có quyền thực hiện yêu cầu này. "
                "Kiểm tra quyền dùng model đang cấu hình; bạn vẫn dùng được /menu."
            ),
        )
    elif isinstance(error, RateLimitError):
        if error.code == "insufficient_quota":
            code, message = (
                "insufficient_quota",
                (
                    "Dịch vụ AI báo hết hạn mức API. "
                    "Kiểm tra hạn mức/thanh toán trong tài khoản OpenAI; "
                    "bạn vẫn dùng được /menu."
                ),
            )
        else:
            code, message = (
                "rate_limited",
                "Dịch vụ AI đang giới hạn lượt gọi. Hãy đợi rồi thử lại hoặc dùng /menu.",
            )
    elif isinstance(error, (BadRequestError, NotFoundError)):
        code, message = (
            "invalid_request",
            (
                "Model hoặc yêu cầu gửi đến AI chưa hợp lệ. "
                "Cần kiểm tra cấu hình/tích hợp trên máy chạy bot; bạn vẫn dùng được /menu."
            ),
        )
    elif isinstance(error, APIStatusError):
        code, message = (
            "provider_error",
            "Dịch vụ AI đang báo lỗi. Bạn có thể thử lại sau hoặc dùng /menu.",
        )
    else:
        code, message = "unknown_error", "AI chưa xử lý được yêu cầu. Dùng /menu hoặc thử lại."
    return code, message + " Nếu đang tạo/sửa dữ liệu, kiểm tra đề xuất đang có trước khi gửi lại."
