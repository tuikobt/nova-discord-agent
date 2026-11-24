# Sửa lỗi tin nhắn riêng không gọi được AI

## Nguyên nhân đã xác minh

Bot nhận được tin Discord và gửi “NOVA đang xử lý…”, nhưng log báo
`agent_turn_failed / APIConnectionError`. Preflight vẫn đạt vì chỉ xác thực
cấu hình/database, không gọi OpenAI.

Phép thử HTTP không dùng API key tới endpoint models trong môi trường hạn chế
mạng thất bại với ConnectError/ConnectionRefusedError (Windows 1225), có biến
proxy. Chạy cùng phép thử ngoài môi trường đó nhận HTTP 401: endpoint kết nối
được, 401 là phản hồi dự kiến khi chưa cung cấp key.

Sau đó chạy toàn bộ lượt hỏi chỉ đọc qua AgentOrchestrator với cấu hình hiện
có, ngoài môi trường hạn chế mạng: OpenAI gọi `get_today_overview` thành công,
không tạo proposal hay ghi dữ liệu công việc. Không in nội dung phản hồi, token,
key hoặc nội dung riêng tư; usage/reservation được ghi theo quota hiện có.

## Xử lý

- Dừng bot cũ có kiểm soát, nhận bot_stopped; kiểm tra không còn tiến trình
  app.main trước khi khởi động một bot ngoài môi trường hạn chế mạng.
- Bot mới sync 4 commands và có bot_online lúc **2026-11-24 21:37:55 Việt Nam**.
- Thêm `app/agent/failures.py`, dùng trong `agent_controller.py`: phân biệt lỗi
  kết nối, timeout, xác thực, quyền, hạn mức, rate limit, request và lỗi dịch vụ.
  Chỉ hiển thị thông báo cố định, không lấy HTTP body/request/prompt làm nội dung
  gửi cho owner. Log error_type/error_code; không log nguyên exception.
- Không tự retry thao tác ghi. Khi lỗi, nhắc kiểm tra đề xuất đang có trước khi
  gửi lại. Giữ nguyên owner guards, pending approval và quota.
- Không đổi .env, API key, model, schema, migrations hoặc dữ liệu nghiệp vụ.

## Kiểm thử

- `python -m pytest -q --disable-warnings --maxfail=2`: **803 passed in 70.85s**.
- `ruff check` đạt; `ruff format --check`: 142 files đúng format; compileall đạt.
- Tests mới kiểm tra thông báo cho từng nhóm lỗi, không phản chiếu HTTP payload
  riêng tư, và lỗi kết nối qua DM không tạo task hoặc pending action.
- Preflight config/AI/integrity/FK/revision/owner/settings đều OK.
- Phép kiểm tra OpenAI thật ở trên là smoke test riêng; unit tests vẫn chặn mạng.

Owner thử lại bằng tin chỉ đọc: **“Hôm nay có việc gì?”**. Chưa dùng lại lệnh
tạo/sửa trước khi kiểm tra các đề xuất đang có từ lượt trước.

## Vận hành

Bot cần truy cập được cả Discord và `https://api.openai.com/v1`. Bot online
trên Discord không đủ chứng minh kết nối AI hoạt động. Khi chạy từ công cụ có
sandbox/proxy, cần quyền mạng phù hợp; không sửa code để bỏ qua proxy/TLS hay
tự tắt chính sách bảo vệ. Nếu chạy trên máy cá nhân, dùng terminal thông thường
đã có quyền mạng và tránh khởi động hai bot cùng lúc.
