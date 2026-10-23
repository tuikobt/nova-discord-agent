# Discord UI Specification — NOVA

**Quyết định:** Discord là *product UI*, không xây website. Chủ yếu dùng **DM + persistent dashboard message trong server**, điều hướng bằng `discord.ui.View`, Buttons, Select Menus và Modals. MVP sử dụng **legacy embeds + View**, không trộn với Components V2 trong cùng message.

## 1. Thông tin server

```text
🤖 NOVA — PERSONAL SPACE
├── 🎛️ #nova-dashboard       | Một bảng điều khiển chính (bot quản lý)
├── 💬 #nova-chat            | Hướng dẫn, chat bổ sung (DM là chính)
├── 🔔 #nova-notifications   | Nhắc việc khi DM không khả dụng hoặc theo tùy chọn
└── 📊 #nova-reports         | Daily/weekly review

📩 DM với NOVA              | Chat cá nhân + quick actions
```

**Permission:** Server private; dashboard & reports chỉ owner/bot xem; tuyệt đối không cho người không được phép thấy nội dung riêng tư. Không được hiểu “private channel” như thay thế cho kiểm tra owner trong code.

## 2. Dashboard chính `/menu`

```text
┌──────────────────────────────────────────────────┐
│ 🤖 NOVA — PERSONAL CONTROL CENTER                │
│ Chào mừng! Hôm nay: 0 task (nếu database rỗng)    │
│ ✅ Done: 0 | ⏰ Reminders: 0 | 🚀 Projects: 0     │
│                                                  │
│ [📅 Hôm nay] [✅ Công việc] [🗓️ Lập lịch]       │
│ [⏰ Nhắc nhở] [🧠 AI trợ lý]                     │
│                                                  │
│ Chọn module: [▼ Danh sách các module]             │
│ [⚙️ Cài đặt] [🔄 Làm mới] [❔ Hướng dẫn]          │
└──────────────────────────────────────────────────┘
```

**Tất cả số đếm lấy từ DB; trong Phase 2 có thể hiển thị `— / Chưa có dữ liệu`, không gắn demo counts lên dashboard như dữ liệu thật.**

### Select menu “Các module”

- ✅ Tasks — P3
- 🚀 Projects — P3
- 📅 Calendar — P3
- ⏰ Reminders — P4
- 🧠 AI Assistant — P5
- 🎯 Goals — P7
- 💰 Finance — P7
- 🏃 Habits — P7
- 📝 Notes — P7
- 💾 Memory — P6
- 📊 Reports — P6

Menu các module chưa có thể hiển thị với nhãn `🔒 Sắp ra mắt` hoặc không có hành động; khi được chọn thì trả thông báo rõ “chức năng chưa phát triển”.

## 3. Màn hình và CTA

| Màn hình | Nội dung | CTA chính | Trạng thái ban đầu |
|---|---|---|---|
| Home | Tổng task/projects/reminders + ngày | Today, Tasks, Planner, Reminders, AI, More | P2 |
| Today | Calendar list hôm nay, task ưu tiên | Thêm sự kiện, Đề xuất lịch, Quay lại | P3 (AI từ P5) |
| Tasks | Bộ lọc Todo/Doing/Done, tối đa 5–10/trang | Thêm, Sửa, Done, Next, Back | P3 |
| Projects | Danh sách, trạng thái, tỷ lệ done | Tạo, Xem task, Back | P3 |
| Calendar | Timeline ngày/tuần dạng danh sách, xung đột | Thêm, Chọn ngày, Back | P3 |
| Reminders | Upcoming/Recurring/Paused | Thêm, Hoãn, Tắt, Back | P4 |
| AI | Nút mở DM + gợi ý câu hỏi mẫu | Mở DM, Gợi ý, Back | P5 |
| Settings | Timezone, giờ briefing/review, DM/channel | Sửa setting, Lưu, Back | P2 shell / logic mở rộng |
| Reports | Daily/Weekly/Monthly (chưa đủ data → thông báo) | Daily, Weekly, Back | P6 |
| Goals/Finance/Habits/Notes/Memory | Theo module cụ thể | Từng module | P6–P7 |

## 4. Luồng tương tác mẫu

### A. Thêm task (không AI)

`/menu` → `✅ Công việc` → `➕ Thêm` → modal `Tên*`, `Mô tả`, `Deadline (optional)`, `Ưu tiên (optional)` → Validate → Save DB → `✅ Đã thêm` → cập nhật overview. Deadline nhập có thể là chuỗi ISO chuẩn, nếu nhập tự do không parse được thì hỏi/hiển thị lỗi. Không giả định ngày thiếu giờ là một thời điểm chính xác.

### B. Tạo lịch

Home → `📅 Hôm nay` → `➕ Thêm lịch` → nhập tên, start, end (theo timezone) → check `end > start` và kiểm tra conflict → nếu conflict, hiển thị `Đổi giờ` / `Vẫn tạo`; ghi rõ người dùng xác nhận trùng giờ → lưu `confirmed`.

### C. AI đổi lịch quan trọng

DM “Chiều mai bận 14–16h, dời lịch giúp tôi” → AI đọc sự kiện có liên quan → tạo **bản đề xuất** → bot hiển thị diff: `Event A 14:00–16:00 → 19:00–21:00` → `✅ Duyệt` / `❌ Bỏ qua` → backend kiểm tra owner, pending action chưa hết hạn, event version, xung đột mới → commit + thông báo. **Không dời lịch chỉ dựa vào output văn bản của AI.**

### D. Reminder

`⏰ Nhắc nhở` → `➕ Tạo` → title + thời gian + lặp (nếu hỗ trợ) + vị trí gửi → save → trước giờ hệ thống push DM/channel. Message có nút `✅ Đã làm`, `⏰ Hoãn 15p`, `❌ Tắt` tùy loại reminder.

### E. Không rõ người muốn gì

DM “Mai nhắc tôi làm bài” → NOVA hỏi “Bạn muốn được nhắc lúc mấy giờ?” bằng câu hỏi ngắn hoặc modal → chưa tạo reminder cho đến khi biết thời gian.

## 5. Lệnh bắt buộc (ngắn gọn)

| Lệnh | Ý nghĩa | Phase |
|---|---|---|
| `/ping` | Kiểm tra bot chạy | P1 |
| `/menu` | Dashboard | P1 shell → P2 |
| `/help` | Hướng dẫn chat/bấm nút | P2 |
| `/settings` | Cài đặt giờ giấc/quyền | P2 |

**Không bắt buộc** `/task add`, `/calendar edit` v.v.; có thể bổ sung làm shortcut sau khi các button/modal đã hoạt động.

## 6. Những quy tắc UI quan trọng

1. Tại server, **tin nhắn dashboard neo cố định**; khi owner bấm module, mở **panel riêng tư** (ưu tiên ephemeral) để tránh sửa dashboard chung và tránh spam.
2. Dashboard có nút refresh, dữ liệu cần reload từ DB. Đừng tự động edit pinned message mỗi vài giây.
3. Khi bot restart, đăng ký lại `persistent View` với `custom_id` ổn định; lưu `dashboard_message_id` và channel id trong DB/config.
4. Không đặt secret hay nội dung nhạy cảm trong `custom_id`. Mọi callback phải xác minh `interaction.user.id`.
5. Tương tác nhiều bước cần xử lý hết hạn, hủy, duplicate clicks, xác nhận một lần và stale data.
6. Không block Discord event loop khi gọi AI hoặc DB; gọi dài cần phản hồi/defer sớm.
7. Phản hồi lỗi có hành động tiếp theo: `Thử lại` / `Đổi dữ liệu` / `Về menu`.
8. Dữ liệu dài phải phân trang, có trạng thái rỗng thân thiện (“Chưa có công việc. Bấm ➕ để tạo”).
9. DM fallback: nếu Discord không cho DM, thông báo qua kênh notification riêng đã duyệt; không phát tán ra kênh công khai.
10. Định dạng mốc giờ người dùng nhập theo `Asia/Ho_Chi_Minh`, lưu UTC; hiển thị rõ ngày và timezone.

## 7. Hình thức triển khai Discord

- **MVP:** `discord.Embed` + `discord.ui.View` legacy buttons/select/modal.
- **Nếu nâng cấp Components V2:** áp dụng theo tài liệu Discord; một message gắn `IS_COMPONENTS_V2` không dùng `content`/`embeds` truyền thống. Không chuyển cách hiển thị nửa chừng không kiểm thử.
- Persistent components cần `timeout=None` với `custom_id` phù hợp và restore View khi startup, tùy tính tương thích SDK thực tế.

## 8. Tiêu chí nghiệm thu dashboard (P2)

- [x] `/menu` hiện overview chính xác, không có dữ liệu demo giả.
- [x] Buttons/Select điều hướng tới các panel tương ứng.
- [x] Module chưa triển khai ghi “Sắp ra mắt”, không hiện thông tin lỗi ẩn.
- [x] `Back`, `Refresh`, `Help`, `Settings` hoạt động.
- [x] Không có thông tin riêng tư hiển thị cho tài khoản không phải owner.
- [x] Dashboard còn tương tác được sau restart bot.
- [x] Không có lỗi “interaction failed” khi thao tác đúng.
- [x] Có UX kiểm tra được trên mobile và desktop Discord.

Nghiệm thu ngày 2026-10-23 theo xác nhận “phase-2 Done” của người dùng và kết quả tự động **159 tests pass** từ phiên triển khai. Codex không tự đăng nhập Discord để kiểm chứng lại.

## 9. Triển khai Phase 2 hiện tại

P2 **DONE** theo xác nhận của người dùng ngày 2026-10-23. Giữ legacy `discord.Embed` + `discord.ui.View`, không có Components V2 hoặc web frontend. P3A chỉ thêm schema/migration; chưa có services hoặc UI CRUD, các module vẫn “Sắp ra mắt”.

- `/menu` trong server tạo hoặc tái sử dụng một dashboard neo. `dashboard_channel_id` và `dashboard_message_id` dùng các cột sẵn có trong `user_settings`; không có migration schema mới.
- Bảng neo chỉ chứa UI và trạng thái chưa có dữ liệu, không chứa settings riêng tư. Ngày hiện tại được tính từ timezone đã lưu khi mở Home/Today riêng tư. Các bộ đếm không có backend hiển thị “Chưa có dữ liệu”.
- Dashboard có Today, Tasks, Projects, Reminders, AI Assistant chia hai hàng 3+2 để dễ đọc trên mobile; select có Calendar, Goals, Finance, Habits, Notes, Memory, Reports. Có Help/Settings/Refresh; thêm slash `/help`, `/settings` làm shortcut.
- Mỗi click từ dashboard tạo panel ephemeral. Điều hướng/Back/Refresh trong panel sửa đúng panel đó; chỉ Refresh trên bảng neo mới sửa bảng neo. Mỗi panel là một View riêng; không có biến screen/page dùng chung.
- Khi chuyển mobile/web, mở lại module từ bảng neo để có panel trên thiết bị đang dùng. Các panel riêng tư không dùng làm lịch sử chung; Settings đã lưu dùng chung database, Refresh đọc lại giá trị mới.
- Settings đọc dữ liệu thật. Modal chỉ sửa timezone IANA đã có storage/service; language và notification preferences chỉ đọc, briefing/review luôn ghi “Chưa kích hoạt”. Không có automation hoặc CRUD.
- Danh sách tính năng có phân trang 4 mục; Previous/Next chỉ xuất hiện khi có nhiều trang. Chưa hiển thị danh sách task/lịch giả.
- `timeout=None`, custom IDs phiên bản `nova:dashboard:v1:...` và `add_view` trong startup giữ nút bảng neo sau restart. Panel riêng tư hết hạn 10 phút, modal 5 phút; panel cũ bị stop khi thay mới để tránh timeout ghi đè màn hình mới.
- Khi panel hết hạn, bot cố gắng disable nút và ghi hướng dẫn mở lại. Lỗi token/HTTP hết hạn được xử lý an toàn, không log payload riêng tư.

### Dashboard bị xóa, thiếu quyền và chống trùng

Bot chỉ tạo bảng trong TextChannel có `@everyone` không được View Channel. Owner cần giới hạn các role/overwrites khác; kiểm tra `@everyone` không phải audit toàn bộ quyền của server. Bot cần View Channel, Send Messages, Read Message History, Embed Links và Pin Messages; không cần Administrator.

Một lock trong process tuần tự hóa `/menu`. Tin nhắn đang gửi chờ DB commit được giữ để retry. Nếu cần phục hồi sau lần gửi bị gián đoạn, bot tìm marker của chính nó trong tối đa 50 tin nhắn gần nhất của kênh. Đây là cơ chế best effort; không cam kết Discord send và DB commit là atomic khi process chết. Không tự xóa message dư.

Nếu message trả NotFound, `/menu` phục hồi tại kênh đã lưu; nếu kênh đã bị xóa, dùng kênh riêng nơi gọi lệnh. Forbidden/HTTP lỗi tạm thời không bị coi là đã xóa và không gây tự gửi bảng mới. Thiếu quyền ghim giữ nguyên message/location, báo riêng tư và cho phép thử lại. Startup chỉ restore View, không tự gửi message hoặc sửa quyền Discord.

Chi tiết file, tests và hướng dẫn kiểm tra từng nút: [`PHASE_2_VALIDATION.md`](PHASE_2_VALIDATION.md).
