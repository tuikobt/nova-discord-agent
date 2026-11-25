"""Fixed public errors; provider bodies and credentials never become exception text."""

from app.domain.errors import DomainError

MESSAGES = {
    "missing_credential": "Chưa có GITHUB_READ_TOKEN trên máy chạy bot; "
    "không dán token vào Discord.",
    "authentication_error": "GitHub từ chối token; kiểm tra cấu hình trên máy chạy bot.",
    "forbidden": "GitHub chưa cấp quyền đọc loại dữ liệu này trong repo đã chọn.",
    "not_found": "Không tìm thấy tài nguyên GitHub hoặc token chưa được cấp quyền đọc.",
    "rate_limited": "Đã chạm giới hạn đọc GitHub; chờ rồi thử lại, không tự gửi lại yêu cầu.",
    "timeout": "GitHub phản hồi quá lâu; chưa đọc được dữ liệu.",
    "network_error": "Chưa kết nối được GitHub; kiểm tra mạng/proxy trên máy chạy bot.",
    "redirect_blocked": "GitHub chuyển hướng tài nguyên; kiểm tra lại repo và duyệt phạm vi mới.",
    "invalid_response": "GitHub trả dữ liệu không đúng định dạng; chưa hiển thị kết quả.",
    "content_too_large": "Dữ liệu vượt giới hạn đọc; chọn file nhỏ hơn hoặc trang khác.",
    "unsupported_file": "Chỉ đọc từng tài liệu UTF-8 nhỏ; "
    "không đọc binary, thư mục hoặc submodule.",
    "unknown_error": "Chưa đọc được GitHub; hãy thử lại sau.",
}


class IntegrationError(DomainError):
    def __init__(self, code):
        self.code = code if code in MESSAGES else "unknown_error"
        super().__init__(MESSAGES[self.code])
