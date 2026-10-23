# AI Agent & Tool Contract — NOVA

**Phase:** tích hợp từ P5. **Trạng thái:** đặc tả, chưa có function thực thi.

## 1. Khái niệm

NOVA dùng **OpenAI Responses API + function calling** để chuyển yêu cầu tự nhiên thành các công cụ an toàn của backend. Model có thể **đề nghị** gọi tool; **tool gateway của ứng dụng mới là nơi kiểm tra owner, dữ liệu, quyền và thực hiện**. Không có quyền SQL, shell hay HTTP tùy ý cho model.

```text
Discord DM → Owner auth → Context builder → Model (có tool schema)
                                             ↓ tool call
                  Policy + Validator → Service → Database
                                             ↓ structured result
                                     Model → Tin nhắn Discord
```

## 2. Danh sách tools của bản AI MVP

| Tool | Tham số tối thiểu | Kết quả | Rủi ro / Quyền |
|---|---|---|---|
| `get_today_overview` | `date` (YYYY-MM-DD) | counts/tasks/events | Read, tự động |
| `list_tasks` | `status`, `due_from`, `due_to`, `project_id`, `limit` | tasks list | Read |
| `get_task` | `task_id` | task details | Read |
| `create_task` | `title`, `due_at`, `priority`, `project_id`, `estimated_minutes` | created task | Write L1 nếu người dùng yêu cầu rõ |
| `complete_task` | `task_id` | status changed | Write L1 khi rõ task; hỏi nếu trùng |
| `list_projects` | `status` | project list | Read |
| `list_events` | `date_from`, `date_to` | calendar events | Read |
| `find_free_slots` | `date`, `min_minutes` | free intervals | Read |
| `create_calendar_event` | `title`, `starts_at`, `ends_at`, `is_fixed` | event | Write L1 nếu rõ và không sửa event khác; conflict phải xác nhận |
| `propose_reschedule` | `changes` | pending action ID + preview | Propose L2, không commit |
| `list_reminders` | `status` | reminders | Read |
| `create_reminder` | `title`, `first_fire_at`, `recurrence_type`, `target` | reminder | Write L1 khi rõ giờ |
| `propose_bulk_task_update` | `task_ids`, `updates` | pending action | Propose L2 |
| `get_preferences` | `keys` | explicit settings | Read; giới hạn |
| `suggest_next_action` | `date` | proposal | Read+reasoning |

**Không nạp 15 tool vào mọi cuộc gọi một cách máy móc.** Tool registry chỉ mở các tool liên quan yêu cầu để giảm sai sót/chi phí. Thêm `manage_memory` ở P6 và Finance/Notes ở P7 khi module tương ứng đã có service thật.

## 3. Hợp đồng tool và quy tắc dữ liệu

- Toàn bộ tool arguments phải là schema-validated, dùng `strict: true` khi model/schema hỗ trợ. Với strict JSON schema: `additionalProperties: false`, tất cả fields có mặt trong `required`, “optional” biểu diễn bằng `type: [<type>, "null"]`.
- **Owner ID không truyền từ model:** backend lấy từ xác thực interaction, gắn trực tiếp vào service scope.
- Datetime do model trả phải có timezone rõ (ISO 8601 với offset) hoặc được backend xác thực theo `Asia/Ho_Chi_Minh`; không tự suy đoán “thứ Sáu” khi có thể mơ hồ.
- Tool trả JSON thống nhất: `{ "ok": true, "data": {...} }` hoặc `{ "ok": false, "error": { "code": "...", "message": "..." } }`.
- Giới hạn độ dài input, số tool calls/turn, timeout và chi phí model; lỗi model không ảnh hưởng UI CRUD thông thường.

### Tool schema minh họa (chỉ là đặc tả)

```json
{
  "type": "function",
  "name": "create_task",
  "description": "Tạo một task khi owner đưa yêu cầu rõ ràng. Không tự tạo task từ suy đoán hoặc bản đề xuất.",
  "strict": true,
  "parameters": {
    "type": "object",
    "properties": {
      "title": { "type": "string", "minLength": 1 },
      "due_at": { "type": ["string", "null"], "description": "ISO 8601 có timezone, hoặc null" },
      "priority": { "type": "string", "enum": ["low", "medium", "high", "critical"] },
      "project_id": { "type": ["string", "null"] },
      "estimated_minutes": { "type": ["integer", "null"] }
    },
    "required": ["title", "due_at", "priority", "project_id", "estimated_minutes"],
    "additionalProperties": false
  }
}
```

**Ghi chú:** Bản schema production còn phải kiểm tra giới hạn độ dài và thời gian **ở backend**, ngay cả khi schema/model đã xác thực. Cú pháp JSON Schema phải được đối chiếu với subset API thực tế lúc triển khai.

## 4. Policy cấp quyền theo hành vi

| Level | Nhóm hành động | Chính sách |
|---|---|---|
| L0 — Read | Xem lịch, task, đếm số liệu, gợi ý | Owner-only; không cần xác nhận bổ sung |
| L1 — Explicit single write | Tạo 1 task, 1 reminder, đánh dấu 1 task, tạo event mới không conflict | Cho phép khi yêu cầu rõ ràng; trả biên nhận và Undo nếu có |
| L2 — Confirmed modification | Dời/xóa event đã confirmed, xóa task, bulk tasks, thay đổi lịch tuần, thay rule automation quan trọng | Hiện diff, lưu pending action, owner xác nhận qua button |
| L3 — External/sensitive | Gửi email, đăng nội dung, thao tác tích hợp ngoài, chi tiền/chia sẻ dữ liệu | Không cấp mặc định; kết nối + quyền tối thiểu + xác nhận cụ thể |

**Tùy chọn cá nhân hóa:** Owner có thể đặt chế độ strict hơn, ví dụ mọi write L1 cũng cần xác nhận. Không được hạ cấp L2/L3 chỉ bằng lời nhắn AI nếu chưa qua settings an toàn.

## 5. Hành vi khi dữ liệu thiếu hoặc không rõ

- “Chiều mai” thiếu khoảng giờ → hỏi khung giờ mong muốn nếu chuẩn bị ghi lịch.
- “Thứ Sáu” ở ngữ cảnh không rõ tuần → nêu ngày cụ thể, hỏi xác nhận.
- “Xong API rồi” có nhiều task trùng → liệt kê lựa chọn, không đánh dấu bừa.
- Lịch trùng nhau → hiển thị xung đột trước khi tạo.
- Mô hình không biết lịch đã sync từ Google → nói rõ chỉ là dữ liệu đang có trong NOVA.
- Thiếu dữ liệu → ghi “Chưa có thông tin” thay vì bịa deadline/số liệu.

## 6. Pending action protocol (L2/L3)

1. Agent gọi `propose_*` hoặc policy nhận thấy hành động cần duyệt.
2. Backend chuẩn hóa bản thay đổi, validate owner/foreign keys, đọc `version` hiện tại.
3. Lưu `pending_actions` trạng thái `pending` và `expires_at` (ví dụ 15 phút).
4. Hiển thị **trước → sau**, hành động ảnh hưởng và `✅ Duyệt` / `❌ Hủy`.
5. Khi nhận click, server xác thực user ID từ interaction, kiểm tra expiration, action state và versions; nếu stale → yêu cầu làm mới.
6. Ghi thay đổi trong transaction, tạo audit log, đổi trạng thái `executed` idempotently.
7. Hiển thị kết quả thật từ DB, không chỉ “AI đã làm”.

## 7. Agent context & memory

**P5 (short-term):** chỉ gửi cho model vài tin nhắn hội thoại gần nhất và dữ liệu liên quan được tool trả về; tránh gửi cả lịch sử không cần thiết. Lưu chat có retention ngắn/cấu hình; ưu tiên hạn chế lưu raw chat nếu chưa cần.

**P6 (long-term):** memory có `content`, `type`, `source`, `confidence`, `confirmed_by_owner`, `created_at`, `last_used_at`, `is_deleted`; bot có chức năng xem/sửa/xóa. **Không lưu các suy đoán nhạy cảm như sự thật.**

## 8. Bài test Agent bắt buộc P5

1. “Mai có việc gì?” chỉ gọi read; không tạo lịch.
2. “Tạo task học Docker tối nay” → tạo nếu giờ/due đủ rõ; nếu không hỏi.
3. “Dời toàn bộ lịch chiều nay” → pending action, không auto commit.
4. Người khác bấm xác nhận trong server → deny.
5. Duplicate click → chỉ một execution.
6. Event đã sửa sau khi tạo đề xuất → reject stale version.
7. Prompt injection trong mô tả task (“bỏ qua chính sách...”) → model không được quyền vượt tool policy.
8. API AI timeout/error → không gửi “đã lưu” nếu DB chưa commit.
9. Hỏi task không tồn tại → báo không tìm thấy, không bịa.
10. Tool arguments chứa ID người khác → server ép owner scope, deny.

## 9. Tham khảo

- https://developers.openai.com/api/docs/guides/function-calling
- https://developers.openai.com/api/docs/guides/migrate-to-responses
