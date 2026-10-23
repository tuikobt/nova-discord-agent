# AGENTS.md — Quy ước cho Codex và AI coding agents

## 0. Đọc trước khi làm

Đọc lần lượt: `README.md`, `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/DATABASE.md`, `docs/DISCORD_UI.md`, `docs/AGENT_TOOLS.md`, `docs/ROADMAP.md`, `docs/SECURITY.md`. Nếu tài liệu có mâu thuẫn, **dừng thay đổi phần liên quan và ghi rõ xung đột**; dùng `docs/ROADMAP.md` làm nguồn chính về phase hiện tại.

## 1. Mục tiêu không được làm sai

- Bot Discord phục vụ **một chủ tài khoản**, chỉ owner có quyền sử dụng mọi chức năng chứa dữ liệu cá nhân.
- DM là điểm tương tác ngôn ngữ tự nhiên, dashboard là giao diện server qua **Discord message components**, không tự ý xây web frontend.
- Ưu tiên trải nghiệm **không cần nhớ nhiều slash commands**; nút bấm / select / modal có hướng dẫn.
- Tất cả dữ liệu thật từ database. Tuyệt đối không đưa số liệu ví dụ vào bot đang chạy như thể là dữ liệu thật.
- Bất kỳ đổi lịch đã xác nhận, xóa, bulk update hay hành động bên ngoài phải đi qua xác nhận rõ ràng.
- Mọi thời gian lưu dạng UTC timezone-aware; hiển thị và diễn giải thời gian theo `Asia/Ho_Chi_Minh` mặc định.

## 2. Stack và giới hạn

- Python 3.12+ (nếu có khác biệt, ghi trong README); `discord.py` phiên bản ổn định tương thích, SQLAlchemy 2.x, SQLite + `aiosqlite` ban đầu, APScheduler khi cần reminder, OpenAI Responses API ở Phase 5.
- Không thêm framework Agent nặng (LangChain/LangGraph) khi chưa có lý do kỹ thuật.
- Không đưa tính năng thuộc phase sau vào phase đang làm nếu người dùng chưa yêu cầu.
- Tách `discord` adapter khỏi business services, AI tools, repositories và scheduler.
- Repository và service phải dùng input đã xác thực, các lệnh đụng DB có transaction rõ ràng.

## 3. Phương pháp làm việc từng phase

1. Kiểm tra Git status, đọc tài liệu, xác nhận phase hiện tại.
2. Trình bày kế hoạch ngắn: file tạo/sửa, rủi ro, tests.
3. Triển khai trong phạm vi **một phase** theo `docs/ROADMAP.md`.
4. Viết test cho service và nghiệp vụ quan trọng. Mock Discord/OpenAI; test không gọi dịch vụ ngoài.
5. Chạy linter/tests khi được cài đặt; báo cáo chính xác lệnh và kết quả.
6. Cập nhật `docs/ROADMAP.md` và README **chỉ khi** điều kiện nghiệm thu đạt.
7. Kết thúc bằng tóm tắt: làm được gì, chưa làm gì, người dùng cần cấu hình gì; không tự chuyển phase.

## 4. Bảo mật và quyền

- Secret chỉ ở `.env` hoặc secret manager; commit `.env.example` với placeholder; `.gitignore` phải bao gồm `.env`, `*.db`, `__pycache__/`, `.venv/`.
- Không đọc/in/log Discord token, OpenAI key hoặc nội dung riêng tư không cần thiết.
- `DISCORD_OWNER_ID` lấy từ config, đối chiếu **ở mọi entry point**: slash command, view button, select, modal, DM, background callbacks/tool executor.
- Không tin prompt hoặc JSON tham số do AI trả về; bắt buộc validate/authorize ở backend.
- Không cho LLM trực tiếp SQL, gọi API tùy ý hoặc chạy lệnh shell; chỉ truy cập tool allowlisted.
- Với thao tác nhạy cảm, thực thi **sau** khi `pending_action` được người dùng duyệt và chưa hết hạn.
- Không tự gửi email/tin nhắn ngoài, không đọc kết nối bên ngoài nếu chưa có kết nối và quyền hợp lệ.

## 5. UI Discord

- `/menu` là đường vào dashboard; `/help`, `/settings`, `/ping` phục vụ setup/vận hành.
- Dashboard chung là **tin nhắn neo cố định**; thao tác riêng tư mở view/response riêng (ưu tiên ephemeral trong server; DM là cuộc trò chuyện riêng), tránh nhiều phiên ghi đè nhau.
- Dùng **legacy embeds + `discord.ui.View`** cho MVP để đảm bảo tương thích; nếu chọn Components V2 phải tách hẳn, không trộn Embed và V2 trong một message.
- Mỗi view có `Back` / `Refresh` khi phù hợp; phân trang khi danh sách dài; module chưa sẵn sàng hiện disabled hoặc “Sắp ra mắt”.
- Handler cần ACK interaction kịp thời và xử lý lỗi rõ ràng.
- Nếu persistent View dùng trên dashboard thì khôi phục khi bot restart; `custom_id` ổn định và ít dữ liệu nhạy cảm.

## 6. Dữ liệu và lịch

- SQLite cho local dev một process; PostgreSQL dành cho môi trường cần nhiều worker/production, migration qua Alembic.
- Nhắc việc gửi theo cơ chế at-least-once/best-effort chống trùng, không được tuyên bố tuyệt đối exactly-once trên Discord.
- Tách `Task` (cần làm), `CalendarEvent` (khung thời gian) và `Reminder` (thông báo).
- Các công việc đã có lịch phải giữ `task_id` tham chiếu; đổi lịch cần xử lý reminder gắn theo event.

## 7. Không tự mở rộng phạm vi

Không triển khai finance automation, Google/Gmail, voice, web dashboard, multi-tenant hay AI inference trước phase được duyệt. Nếu gặp thiếu thông tin chưa ảnh hưởng tới phase hiện tại, ghi thành assumption trong `docs/ROADMAP.md` và tiếp tục phần an toàn.
