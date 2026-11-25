# Security & Privacy — NOVA

**7A.2 hiện tại:** đã cài GitHub HTTP reader/probe, chỉ chạy sau owner click và
trong resource allowlist đã Duyệt. Owner/provider/version/resource checked
trước/sau HTTP và sau chờ queue. Chỉ GET endpoint GitHub.com API cố định, không
redirect hoặc fetch download URL; timeout, stream/document/page/call budget
có giới hạn, không auto retry. Error body không được đọc, DTO lọc secret, nguồn
backend dựng và UI escape nội dung. GitHub text chưa đi vào AI hoặc database,
không có external writes/background reads. Token cấu hình trên máy với selected
repos và các quyền read-only; chưa có flow refresh/App/OAuth tự động. Chưa có
Notion adapter. Đoạn 7A.1 dưới đây mô tả checkpoint lịch sử; chi tiết hiện tại ở
[báo cáo 7A.2](PHASE_7A2_VALIDATION.md).

**7A.1:** connection chỉ giữ metadata và phạm vi chỉ đọc đã được owner Duyệt.
Credential có hai tên cố định `GITHUB_READ_TOKEN`, `NOTION_READ_TOKEN`, chỉ lấy
từ config trên máy/secret manager; không cho UI/model chọn tên secret tùy ý.
Các token này được đăng ký với bộ lọc log/AI và scanner Git; không gửi token
cho LLM. Có backstop nhận dạng token Notion ngoài exact-match các secret đã cấu
hình. Bộ lọc không thay thế việc giữ secrets ngoài Git.

Không có production HTTP adapter trong 7A.1, không đọc GitHub/Notion hoặc gọi
probe nền. Các identifier chỉ chuẩn hóa từ repo/page ID hoặc host HTTPS chính
thức; không fetch URL người dùng cung cấp. Scope gate kiểm tra owner, tài nguyên,
version, permission read và trạng thái ngắt ở backend. Model không được cung
cấp tool thêm/sửa/ngắt kết nối; những thao tác này chỉ đi qua UI riêng có duyệt.
Phép thử AI cần click rõ ràng, dùng quota và không kèm context cá nhân.

**Review trước P6 (2026-11-18):** xem [báo cáo bảo mật](SECURITY_REVIEW_2026-11-18.md)
cho phạm vi scan Git, prompt/public-source boundary, dữ liệu gửi model và các giới hạn.
Đã thêm local pre-push hook + CI check, lọc credential cả Discord/OpenAI, giảm tool
metadata, chặn một số prompt extraction và kiểm tra output. Prompt không chứa secrets
và không dùng làm lớp phân quyền; backend mới quyết định. Bộ lọc không đảm bảo tuyệt
đối chống lộ prompt/secret. Không tự triển khai P6 hoặc push các sửa này.

**P5:** OpenAI chỉ được gọi sau owner guard và khi AI_ENABLED=true, key/model đủ.
Chỉ DM được đọc; không bật privileged Message Content intent vì Discord cho bot đọc
content DM với chính app (xem nguồn Gateway dưới đây). Gửi context/tool data liên quan
tới OpenAI để trả lời; Responses dùng `store=false`, không dùng hosted conversation.
Điều này không thay thế chính sách retention/abuse monitoring của nhà cung cấp API.
Context raw chỉ RAM tối đa 20 messages/30 phút, timer xóa khi idle, có nút xóa và mất
khi restart. Proposals/receipts/audit và usage giữ bền vững; không chứa raw chat hay keys.
SDK/HTTP logs bị tắt; logs NOVA chỉ error class/metadata. Mọi AI write cần click duyệt.
Giới hạn input 4000 ký tự, 4 model rounds, 8 tool calls, 60s/turn, 12 requests/phút,
quota requests/tokens theo ngày UTC từ env. Usage không rõ giữ reservation; không tự
retry HTTP hoặc đổi sang model khác. Quota tokens là giới hạn ứng dụng, không phải
cam kết số tiền; theo dõi tiền và thiết lập ngân sách dự án tại OpenAI.

Nguồn: [Discord Gateway — Message Content](https://docs.discord.com/developers/events/gateway#message-content-intent),
[OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling).

**Phạm vi:** bot cá nhân lưu lịch, dự án, task và sau này có thể có tài chính, ghi chú, memory. Mặc định ưu tiên riêng tư và quyền tối thiểu.

## 1. Mô hình rủi ro

| Rủi ro | Phòng ngừa |
|---|---|
| Lộ Discord bot token / OpenAI API key | `.env`, không commit, redact logs, rotate khi lộ |
| Người khác bấm nút/đọc riêng tư | So khớp `interaction.user.id` với owner allowlist ở **mọi callback**; private channels |
| Model gọi tool sai quyền | Whitelist tool; server-side policy; xác thực resource ownership |
| AI tự dời/xóa lịch | Pending action, preview/diff, phê duyệt idempotent, expiry/version check |
| Dữ liệu ngày giờ sai múi giờ | UTC storage, timezone-aware parsing/conversion, date ambiguity check |
| Lời nhắc trùng hoặc không gửi | Durable schedule/delivery record + retries + alert; không hứa exactly-once |
| Lộ nội dung qua logs | Chỉ metadata cần thiết, tránh raw message / notes / finance |
| Chia sẻ dữ liệu qua tích hợp | OAuth scopes tối thiểu, consent từng connector, không kết nối mặc định |
| SQL injection/unsafe prompts | ORM + parameterized queries, structured tool schema, không thực thi code từ LLM |
| Mất database | Backup và restore drill; Git không chứa DB |

## 2. Setup an toàn cho Phase 1

- Environment variables dự kiến:
  - `DISCORD_TOKEN` — bắt buộc để chạy bot
  - `DISCORD_OWNER_ID` — snowflake user ID owner
  - `DATABASE_URL=sqlite+aiosqlite:///./nova.db`
  - `TIMEZONE=Asia/Ho_Chi_Minh`
  - `OPENAI_API_KEY` — **chưa cần tới Phase 5**
  - `OPENAI_MODEL` — cấu hình ở Phase 5, không hardcode
- Mỗi lần bot khởi động, kiểm tra thiếu biến bắt buộc, báo lỗi thân thiện nhưng không in giá trị.
- `.gitignore`: `.env`, `.venv/`, `*.db`, `*.db-*`, `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`.
- `DISCORD_OWNER_ID` là người sở hữu, không phải application/bot ID.
- Đặt quyền Discord bot tối thiểu; không cấp Administrator chỉ để thử nghiệm.

## 3. Discord permissions

- Trong private server: View Channels, Send Messages, Read Message History, Embed Links, Use Application Commands (phần phù hợp) theo đúng chức năng.
- Privileged intents: không bật không cần thiết. Với DM message handling P5, kiểm tra chính sách Message Content intent và các ngoại lệ DM theo tài liệu Discord mới nhất; không dựa vào suy đoán.
- Channel thông báo và báo cáo phải private. Nếu DM thất bại, **chỉ** fallback sang channel nằm trong allowlist do owner cấu hình.
- Never leak user data trong ephemeral vs public response: chủ động dùng private panel khi thích hợp, luôn kiểm tra owner.

## 4. Dữ liệu, retention và quyền người dùng

- Owner có thể xem/sửa/xóa task/lịch/memory theo module.
- Logs vận hành chỉ giữ metadata có ích cho debug; đề xuất 14–30 ngày, cấu hình được.
- Conversation raw data chỉ lưu nếu cần cho ngữ cảnh; phải mô tả rõ thời hạn và cung cấp cách xóa, không thu thập mặc định mọi tin nhắn server.
- Không dùng nội dung riêng tư để làm ví dụ trong test fixture hoặc Git.
- Backup phải nằm ở nơi riêng tư, mã hóa phù hợp; khi xóa dữ liệu cần có chính sách backup retention rõ ràng.
- Finance ở P7 là sổ thu chi thủ công; không yêu cầu thông tin tài khoản ngân hàng/mật khẩu.

## 5. Chính sách tự động hóa

- Automation chỉ chạy khi enabled trong settings; có thể pause hoặc đặt quiet hours.
- Không nhắn quá nhiều: gộp reminder khi hợp lý; cảnh báo deadline lặp giới hạn.
- Không tự thực hiện hành động bên ngoài do model suy luận. Cần consent + service permission + owner confirmation.
- P6 mặc định tắt cả ba automation; đổi policy cần pending approval. Không đọc
  Gmail/Google/GitHub/Notion trong P6. Kênh báo cáo phải vượt cùng private ACL
  của reminder, kiểm tra lại mỗi lần gửi; fallback phải được bật riêng, không
  tự chuyển kênh khi owner tắt DM. Quiet hours không có ngoại lệ tự suy diễn.
- Memory dùng cho AI tối đa 5 mục liên quan đã xác nhận/use_for_ai; nguồn backend,
  không chèn vào system instructions. Xóa/tắt làm rỗng context, chặn kết quả AI
  đang xử lý từ context cũ. Xóa nội dung khỏi các pending action liên quan;
  không tự xóa tin Discord/backup hoặc cam kết secure erase trên ổ đĩa.
- Report content lưu 30 ngày, metadata idempotency giữ lại. Memory xác nhận giữ
  tới khi owner xóa. Mọi thay đổi P6 dùng TTL/version/owner/message/channel
  binding và audit transaction. Tham khảo [giới hạn P6](PHASE_6_VALIDATION.md).

## 6. Checklist trước khi deploy công khai/VPS

- [ ] Secrets đã chuyển vào env/secret manager; scan Git history.
- [ ] Debug log không in nội dung nhạy cảm.
- [ ] Owner checks cho command, button, modal, tool calls, background actions.
- [ ] Hạn chế quyền Discord bot/server.
- [ ] DB backup tự động và đã test restore.
- [ ] Xử lý reconnect, retry, scheduler restart, stale pending actions.
- [ ] Rate limits và cost caps OpenAI.
- [ ] Error monitoring/alert chỉ gửi cho owner.
- [ ] Xác thực OAuth đúng chuẩn nếu bật Google/GitHub/Gmail.
