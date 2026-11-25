"""Connection consent wording without raw credentials or provider error bodies."""

from app.discord_bot.renderers.core import safe
from app.discord_bot.renderers.personal import when
from app.domain.connections import PROVIDERS
from app.integrations.errors import MESSAGES

STATES = {
    "configured": "Đã lưu phạm vi, chưa xác minh",
    "verified": "Đã kiểm tra quyền đọc",
    "disconnected": "Đã ngắt trong NOVA",
}
CHECK_MESSAGES = {
    **MESSAGES,
    "verified": "Kiểm tra dịch vụ và phạm vi đọc thành công.",
    "adapter_pending": "Đã có khóa trên máy. Chức năng kiểm tra/đọc dịch vụ này "
    "chưa sẵn sàng ở bản hiện tại; chưa xác minh kết nối.",
    "missing_credential": "Chưa có khóa cho dịch vụ này trên máy chạy bot. "
    "Cấu hình khóa trong .env hoặc secret manager; không dán khóa vào Discord.",
    "disconnected": "Kết nối đã ngắt trong NOVA. Không gọi dịch vụ hoặc đọc tài liệu.",
    "authentication_error": "Dịch vụ từ chối khóa truy cập; kiểm tra khóa trên máy chạy bot.",
    "forbidden": "Dịch vụ chưa cấp quyền cho tài nguyên đã chọn.",
    "not_found": "Không tìm thấy tài nguyên được chọn hoặc chưa có quyền đọc.",
    "timeout": "Dịch vụ phản hồi quá lâu; chưa xác minh kết nối.",
    "network_error": "Chưa kết nối được dịch vụ; kiểm tra mạng/proxy trên máy chạy bot.",
    "rate_limited": "Dịch vụ đang giới hạn lượt gọi; thử lại sau.",
    "unknown_error": "Chưa kiểm tra được dịch vụ. "
    "Không có nội dung riêng tư nào được hiển thị trong lỗi.",
}


def scope_text(record):
    return f"{PROVIDERS[record['provider']]} • {safe(record['label'], 200)}\n" + "\n".join(
        f"• {safe(resource, 400)}" for resource in record["resources"]
    )


def connection_preview(proposal):
    plan = proposal["preview"]
    change = plan["changes"][0]
    lines = [
        "ĐỀ XUẤT KẾT NỐI — CHƯA LƯU",
        f"Duyệt trước {when(proposal['expires_at'], plan['timezone'])}",
    ]
    if plan["connection_kind"] == "disconnect_connection":
        lines.extend(
            [
                "\nNgắt kết nối trong NOVA:",
                scope_text(change["before"]),
                "\nSau khi duyệt, NOVA không được dùng phạm vi này. "
                "Token tại nhà cung cấp không bị tự thu hồi; bạn có thể thu hồi riêng nếu cần.",
            ]
        )
    else:
        if change["before"]:
            lines.extend(["\nPhạm vi hiện tại:", scope_text(change["before"])])
        lines.extend(
            [
                "\nPhạm vi sau khi duyệt:",
                scope_text(change["after"]),
                "\nQuyền cho phép trong NOVA: chỉ đọc. "
                "Chưa xác minh quyền thực tế tại nhà cung cấp.",
                "Đồng ý lưu phạm vi không tự đọc tài liệu hoặc bật hành động bên ngoài.",
            ]
        )
    lines.append("\nĐọc kỹ rồi bấm Duyệt để lưu, hoặc Hủy đề xuất.")
    return "\n".join(lines)
