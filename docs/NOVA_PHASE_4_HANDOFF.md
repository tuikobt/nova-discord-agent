# NOVA AI — PHASE 4 HANDOFF

**Tên phase:** P4 — Reminder Engine (nhắc nhở tự động qua Discord)

**Trạng thái:** Bản bàn giao để triển khai; **chưa có mã P4 được thực hiện trong tài liệu này**.

**Đầu vào bắt buộc:** NOVA Phase 1–3 đã chạy và được kiểm thử trên repository thực tế. Tài liệu này dựa trên baseline Phase 0 (`AGENTS.md`, `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/DATABASE.md`, `docs/DISCORD_UI.md`, `docs/ROADMAP.md`, `docs/SECURITY.md`) và **không có quyền truy cập code mới nhất trên máy người dùng**. Codex phải kiểm tra code hiện tại trước khi thay đổi.

## 1. Mục tiêu sản phẩm

Đưa module **⏰ Reminders** trên Discord Dashboard từ “Sắp ra mắt” thành tính năng thật. Chủ sở hữu có thể tạo, xem, sửa, tạm dừng, tiếp tục, hoãn và hủy nhắc nhở; NOVA tự gửi thông báo vào **DM** hoặc **kênh riêng được phê duyệt** khi tới giờ. Dữ liệu và trạng thái nhắc nhở tồn tại qua restart; không cần AI để nhắc.

**Ví dụ luồng hoàn chỉnh:** `/menu` → ⏰ Reminders → ➕ Tạo → nhập “Học tiếng Anh”, `2026-11-10 20:00` (Asia/Ho_Chi_Minh) → lưu → lúc đến hạn bot gửi thông báo → người dùng chọn `⏰ Hoãn 15 phút`, `✅ Đã làm` hoặc `❌ Tắt` → database và UI phản ánh trạng thái chính xác.

**Không thuộc P4:** chat ngôn ngữ tự nhiên, OpenAI Responses API/function calling (P5), AI tự tối ưu lịch, trí nhớ và daily briefings (P6), Gmail/Google Calendar, Goals/Finance/Habits/Notes, web frontend, hệ thống nhiều người dùng, server production nhiều worker (P7).

## 2. Các chức năng bắt buộc

### 2.1. Nhắc một lần (one-time)

- Tạo nhắc nhở với `title`, thời điểm cụ thể, vị trí gửi (`dm` hoặc kênh riêng đã cấu hình), và liên kết task/event tùy chọn.
- Thời gian nhập và hiển thị theo `Asia/Ho_Chi_Minh` mặc định; lưu **UTC** trong DB (với SQLite kiểm tra round-trip rõ ràng).
- Kiểm tra thời gian hợp lệ; từ chối thời gian quá khứ khi tạo mới, trừ luồng catch-up được thiết kế.
- Sau khi thông báo được ghi nhận gửi thành công, one-time chuyển thành `done`; nếu gửi lỗi, giữ trạng thái có thể retry.
- Có nút `➕ Tạo`, `📋 Danh sách`, `🔎 Chi tiết`, `✏️ Sửa`, `⏸️ Tạm dừng`, `▶️ Tiếp tục`, `❌ Hủy`, `⬅️ Back`, `🔄 Refresh` tùy trạng thái.

### 2.2. Nhắc lặp lại (recurring)

- MVP hỗ trợ **daily** và **weekly**; không cần quy tắc lịch phức tạp.
- Ví dụ: “Học tiếng Anh lúc 20:00 mỗi ngày” hoặc “Review tuần lúc 19:00 Chủ nhật”. Ở P4 người dùng điền form/select; chưa cần AI hiểu câu tự nhiên.
- Lưu quy tắc lặp theo **múi giờ địa phương**, không cố định thành khoảng 24 giờ UTC vì có thể sai ở timezone có DST sau này.
- Chỉ giữ một reminder logic và `next_fire_at`; không tự nhân bản một reminder cho từng ngày.
- Khi đã xử lý một occurrence, tính lần kế tiếp bằng timezone local, đảm bảo **lần tiếp theo > occurrence vừa xử lý**.
- Có thể tạm dừng/tiếp tục và hủy lịch lặp; `cancelled` không được phát tiếp.

### 2.3. Hoãn (snooze) và nút trên thông báo

- Thông báo Discord có tiêu đề, giờ local, tính chất một lần/lặp và nút thao tác: `✅ Đã làm`, `⏰ Hoãn 15 phút`, `❌ Tắt` (theo trạng thái).
- Hoãn tạo lần nhắc bổ sung có theo dõi và không ghi đè/mất quy tắc lặp gốc. **Nghĩa vụ triển khai:** quyết định rõ “hoãn một occurrence” hay “dời tất cả chu kỳ”; mặc định chỉ hoãn occurrence hiện tại.
- Bấm lặp nút nhiều lần không tạo hai lần hoãn, không gửi hai thông báo; thao tác stale/đã xử lý trả lời rõ ràng.
- Nút trên tin nhắn cũ sau restart phải hoạt động hoặc báo hết hạn có hướng dẫn, không giả vờ thành công.

### 2.4. Lọc, liên kết và cập nhật

- Hiển thị reminders `active | paused | done | cancelled`, có phân trang và empty state.
- Reminder liên kết `task_id` hoặc `event_id` (nếu có) phải thuộc **cùng owner**.
- Sửa lịch confirmed hoặc task liên quan: **không tự ý đổi reminder độc lập**. Với lời nhắc gắn event và được định nghĩa theo offset, thay đổi cần tuân thủ contract mà Phase 4 thiết kế và hỏi xác nhận khi cần.
- Tất cả DB queries theo `owner_id`; không tin `custom_id` hoặc ID do người dùng gửi.

## 3. Thiết kế dữ liệu chuẩn theo DATABASE.md

### `reminders` (P4)

| Field | Nội dung |
|---|---|
| `id` | UUID/string PK |
| `owner_id` | Discord User ID string, FK users |
| `task_id`, `event_id` | FK nullable, phải cùng owner |
| `title` | VARCHAR(250), required |
| `next_fire_at` | UTC, required |
| `recurrence_type` | `none | daily | weekly` |
| `recurrence_config_json` | Quy tắc local: time, weekday, timezone... có validation |
| `delivery_target` | `dm | channel` |
| `channel_id` | nullable, chỉ kênh riêng hợp lệ |
| `status` | `active | paused | done | cancelled` |
| `created_at`, `updated_at` | UTC |

Index `(status, next_fire_at)`; thêm index theo `owner_id`. Không dùng hard delete mặc định.

### `reminder_deliveries` (P4)

| Field | Nội dung |
|---|---|
| `id` | UUID/string PK |
| `reminder_id` | FK reminders |
| `scheduled_fire_at` | UTC của occurrence / lần hoãn |
| `status` | `pending | claimed | sent | failed` |
| `attempt_count` | >= 0 |
| `last_error_code` | Mã lỗi an toàn, **không lưu token/PII** |
| `discord_message_id` | ID tin nhắn nếu gửi thành công |
| `claimed_at`, `sent_at` | UTC nullable |

Unique `(reminder_id, scheduled_fire_at)` đảm bảo không tạo trùng delivery cho cùng occurrence. Với **snooze** và một occurrence gốc, kiểm tra schema hiện tại có đủ để phân biệt lần gửi bổ sung hay chưa; nếu thiếu, đề xuất migration mở rộng *tương thích ngược* (ví dụ `parent_delivery_id`, `delivery_kind`) và giải thích trong tài liệu. Không tự ý sửa schema nền tùy tiện.

**Không cam kết gửi exactly-once**: Discord send và DB commit không nằm trong cùng một transaction; nếu process crash ở khoảng giữa, có thể cần đối soát/truy vết. Hướng tới **best-effort / at-least-once với giảm thiểu trùng** bằng unique key, claim, trạng thái và chống bấm lặp. Mọi thông báo 'Đã gửi' chỉ xuất hiện khi Discord API trả thành công.

## 4. Kiến trúc và vòng đời worker

```text
Discord UI (Views/Buttons/Modals) -> ReminderService -> ReminderRepository -> SQLite
                                                           ^
                                                           |
                                  ReminderDispatcher/Worker (poll DB)
                                                           |
                                                           v
                                    Discord DM / Private Notification Channel
                                                           |
                                                           v
                                 reminder_deliveries (sent / failed / retry)
```

- Tận dụng layout repository thực tế; theo baseline có `app/services/reminder_service.py`, `app/db/repositories/`, `app/scheduler/jobs.py`, `app/scheduler/dispatcher.py`.
- Service quản lý nghiệp vụ và transaction; Discord adapter chỉ validate, check owner, ack/defer, render.
- **Đề xuất cho NOVA một process:** worker asyncio polling DB theo chu kỳ hợp lý (ví dụ 15–30s), start một lần khi bot sẵn sàng, stop khi bot shutdown. Có thể dùng APScheduler theo version được pin hiện có, nhưng **DB reminders/deliveries là source of truth**, không chỉ lưu job trong RAM.
- Nếu chọn APScheduler, xác minh APIs theo **version đã pin**. APScheduler 3.x và 4.x khác biệt đáng kể; không trộn `AsyncIOScheduler` 3.x với API 4.x.
- Retry với backoff có giới hạn (ví dụ 1, 5, 15 phút, tối đa 3 lần; có thể điều chỉnh sau). Không loop gửi vô hạn khi Discord trả Forbidden.
- **Owner-specific:** Không bao giờ gửi fallback sang channel công khai; kiểm tra channel hợp lệ và permission trước khi gửi; nếu DM bị chặn, log failure an toàn rồi chỉ dùng fallback private đã cho phép.
- Catch-up khi restart: chọn chính sách rõ ràng cho overdue (ví dụ gửi những lần nhắc một lần trễ không quá 30 phút, quá hạn thì hiển thị missed, không gửi lại cả loạt thông báo cũ); nhất quán và có test. Đây là **đề xuất**, Codex cần ghi rõ policy được chọn.
- Quiet hours: tôn trọng settings hiện tại nếu đã có, phân biệt delay/skip thông báo thường, giữ nguyên lịch logic; policy phải có test đặc biệt khi qua nửa đêm.
- Không có nhiều process/worker cùng sử dụng SQLite ở P4; nếu code đã hỗ trợ nhiều worker, phải có claim atomic/cơ chế khóa thích hợp. Không tuyên bố an toàn đa worker nếu chưa kiểm thử.

## 5. Discord UI (tương thích P2/P3)

- `/menu` → `⏰ Reminders` → màn hình chính với `➕ Tạo`, `📋 Danh sách`, `🔄 Refresh`, `⬅️ Back`.
- Tạo mới qua modal hoặc flow nhiều bước: `title`, thời điểm `YYYY-MM-DD HH:MM`, loại nhắc (once/daily/weekly), ngày trong tuần nếu weekly, đích gửi.
- `📋 Danh sách`: trạng thái, thời gian gửi tiếp theo theo VN, trang trước/sau; chọn reminder bằng select/ID không có secret.
- `🔎 Chi tiết`: edit/pause/resume/cancel; confirm thao tác hủy nếu đã active.
- Khi lưu thành công, refresh counts thật từ DB trên dashboard. `Tasks`, `Projects`, `Calendar`, Back/Refresh/Help/Settings và dashboard pinned P2 phải vẫn hoạt động.
- Không làm giao diện giả “đã tạo reminder” khi chưa ghi DB thành công.
- Mọi callback và modal submit kiểm tra `DISCORD_OWNER_ID`; phản hồi riêng tư trong guild; tránh lỗi “This interaction failed”.

## 6. Phân chia thi công — bắt buộc theo checkpoint

### P4-A — Models / migrations / service hợp đồng (**DỪNG sau P4-A**)

1. `git status`; đọc docs, code P3 và tests; xác nhận P3 đạt nghiệm thu. Dừng bot, backup DB và kiểm tra vị trí SQLite thực tế.
2. Thiết kế `Reminder`, `ReminderDelivery` theo docs; đề xuất schema cho snooze nếu cần, không phá dữ liệu cũ.
3. Thêm ORM, indexes, constraints và Alembic revisions; bật FK SQLite.
4. Tạo domain enums/schemas input; timezone utility local ↔ UTC; validation loại recurrence.
5. Unit tests migration từ DB rỗng và từ DB copy P3, FK, owner, timezone, uniqueness, recurrence rule.
6. Chạy tests, báo cáo kết quả và hướng rollback/restore; chưa làm UI hay gửi Discord.

### P4-B — Service + worker + delivery (**DỪNG sau P4-B**)

1. Repository owner-scoped; service CRUD + pause/resume/cancel/snooze và link task/event an toàn.
2. Dispatcher scan DB due, claim transaction + uniqueness; enqueue/claim/retry/backoff, update status và next occurrence.
3. Discord delivery adapter giao tiếp bất đồng bộ; `discord.Forbidden`, HTTP/network errors được phân loại.
4. Recovery sau restart, overdue/catch-up, quiet hours, chặn gửi fallback công khai, graceful shutdown.
5. Tests với fake clock/Discord client: due, retry, crash-window, repeating, snooze-double-click, restart, DM blocked, stale version.
6. Chạy toàn bộ regression P1–P3; chưa làm reminder UI.

### P4-C — Discord UI + nghiệm thu (**DỪNG sau P4-C**)

1. Nối P2 Reminders panel với service P4. Forms/modals/choice, danh sách phân trang, detail/edit/pause/resume/cancel.
2. Tạo notification embeds/views với `✅ Đã làm`, `⏰ Hoãn 15 phút`, `❌ Tắt`. Owner guard, xử lý notification cũ sau restart.
3. Không spam dashboard; nhắc qua DM/private fallback. Refresh overview từ DB.
4. Thử trên Desktop/Mobile, bấm lặp, restart trước/sau giờ, DM blocked, non-owner denial.
5. Chạy tests; cập nhật docs/ROADMAP.md **chỉ khi** acceptance thực sự đạt. Không triển khai P5.

## 7. Kịch bản kiểm thử trực tiếp trên Discord

1. Trong `🎛️・nova-dashboard`, mở `/menu` → `⏰ Reminders` → tạo **one-time reminder** “Kiểm thử NOVA” sau **2 phút** bằng form chọn thời điểm tuyệt đối chính xác theo giờ máy/VN; kiểm tra lưu vào danh sách.
2. Đến giờ, bot gửi **DM**. Nếu bot không gửi: xem log lỗi an toàn, Discord privacy settings, quyền/kết nối.
3. Tạo reminder sau 2 phút khác → tại thông báo chọn `⏰ Hoãn 15 phút`; kiểm tra next delivery và không có hai thông báo trùng từ một lần bấm.
4. Tạo reminder **daily** lúc giờ gần hiện tại để kiểm tra lần nhắc đầu; sau gửi, xem `next_fire_at` chuyển sang lần kế tiếp đúng ngày/giờ VN. Tương tự với **weekly** vào một ngày cụ thể.
5. Tạo và **pause** reminder trước giờ → không gửi; resume → tính lại `next_fire_at` an toàn, không gửi backlog trái policy.
6. **Restart bot trước** giờ nhắc và kiểm tra vẫn gửi; **restart sau** khi đã đến hạn để kiểm tra catch-up policy. Không chạy hai process bot cùng token.
7. Nếu đã có kênh fallback riêng, thử chặn DM từ bot (bằng cấu hình riêng tư Discord) → chỉ gửi vào kênh **riêng đã cho phép**, không rò rỉ dữ liệu tại `nova-chat` công khai.
8. Người không phải owner thử nhấn nút trên notification/channel có thể truy cập → bị chặn; dữ liệu không thay đổi.
9. Kiểm tra Overview/Dashboard, Tasks, Projects, Calendar, Help, Settings, Back, Refresh sau P4; không có regression.
10. Kiểm thử nhận/chỉnh/sửa nhắc thời gian trước hiện tại, thiếu title, sai giờ `25:99`, bấm cancel hai lần, lỗi Discord 403/HTTP 5xx, mạng mất đột ngột.

## 8. Acceptance P4 (chỉ đánh dấu DONE khi đạt)

- [ ] Owner tạo, xem, sửa, pause/resume, cancel và snooze reminder từ Discord UI.
- [ ] Nhắc một lần được gửi khoảng thời điểm đến hạn theo VN timezone khi bot đang Online; sai số thực tế và nguyên nhân trễ được ghi nhận.
- [ ] Daily/weekly recurrence tính ngày tiếp theo đúng, không sinh reminders vô hạn.
- [ ] DB bền vững qua restart, overdue/catch-up theo policy.
- [ ] Claim/unique và nút double-click giảm thiểu trùng delivery; failure/retry được ghi logs và DB rõ.
- [ ] DM bị chặn không gửi dữ liệu cá nhân tới kênh không riêng tư.
- [ ] Non-owner không đọc/ghi/nhấn thành công; mọi link task/event cùng owner.
- [ ] Dashboard persistent, P1/P2/P3 không bị hỏng.
- [ ] Unit/integration tests pass, migrations an toàn, docs có ghi config và cách troubleshoot.
- [ ] P5 không bị triển khai trước.

## 9. Lệnh thực thi tham khảo

**Linux / macOS / WSL:**

```bash
# Trong thư mục repository NOVA hiện tại
git status
.venv/bin/python -m pytest -q
.venv/bin/python -m app.main
```

**Windows PowerShell:**

```powershell
git status
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m app.main
```

Đọc README project thực tế cho Alembic và command chạy ứng dụng, không đoán đường dẫn `.db`. Luôn dừng bot trước khi backup/migrate SQLite thực tế.

## 10. Prompt cho Codex (dán nguyên văn)

### 10.1. Bắt đầu P4-A

> Đọc `AGENTS.md`, `README.md`, `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/DATABASE.md`, `docs/DISCORD_UI.md`, `docs/ROADMAP.md`, `docs/SECURITY.md` và `docs/PHASE_4_HANDOFF.md`; kiểm tra Git và source code thật hiện tại. Tôi đã hoàn thành P1/P2; trước khi làm P4, **xác minh P3 (Task/Project/Calendar CRUD và tests) đã đạt**. Nếu chưa, báo phần thiếu, không áp migration P4. Nếu đạt, triển khai **chỉ P4-A**: backup và migration DB, models `reminders`, `reminder_deliveries`, recurrence/timezone validation, owner FK và unique constraints. Giữ nguyên dashboard và data P1–P3. Chạy tests và ghi kết quả thực tế. Báo file thay đổi và lệnh migrate/restore chính xác. **Dừng sau P4-A**, chưa làm worker, UI, AI.

### 10.2. Tiếp tục P4-B

> Tôi đã nghiệm thu P4-A. Hãy đọc lại `docs/PHASE_4_HANDOFF.md` và code hiện tại, triển khai **chỉ P4-B**: ReminderService owner-scoped, worker đọc due reminders từ DB, transaction claim, deliveries uniqueness, retry/backoff, DM/private fallback, recurring daily/weekly, snooze, quiet hours, startup recovery và graceful shutdown. Dùng async an toàn, không blocking Discord event loop; không hứa exactly-once. Dùng version APScheduler đã pin và đúng API tương ứng nếu cần. Viết tests với fake clock/Discord, chạy regression P1–P3 và báo kết quả. **Dừng sau P4-B**, chưa làm giao diện hay AI.

### 10.3. Tiếp tục P4-C

> Tôi đã nghiệm thu P4-B. Đọc `docs/PHASE_4_HANDOFF.md` và source hiện tại. Triển khai **chỉ P4-C**: kết nối Reminders Dashboard P2/P3 với CRUD UI bằng buttons/select/modals; notification có nút `✅ Đã làm`, `⏰ Hoãn 15 phút`, `❌ Tắt`; owner guards, persistent callback/restart behavior, phân trang/empty states, refresh Overview, DM/private fallback. Kiểm thử Discord Desktop/Mobile, non-owner, double-click, restart, quiet hours, lost DM. Không tạo fake data, không làm AI/Phase 5. Chạy tests, trình bày acceptance checklist, hướng dẫn người dùng smoke test; chỉ cập nhật ROADMAP thành P4 DONE khi đủ bằng chứng kiểm thử. **Dừng sau P4-C**.

## 11. Troubleshooting nhanh

- **Bot Online nhưng không gửi DM:** kiểm tra Discord DM permissions/privacy, channel routing, `Forbidden`, due scan, `status`, `next_fire_at` UTC, timezone, logs.
- **Lỡ nhắc sau restart:** kiểm tra worker startup, catch-up window/policy, cấu hình stop/start một worker, `claim` trạng thái.
- **Nhắc hai lần:** kiểm tra `UNIQUE(reminder_id, scheduled_fire_at)`, duplicate click, hai process bot/worker và crash window. Không khẳng định đã xử lý tuyệt đối nếu chưa test.
- **Daily bị lệch giờ:** phân biệt local recurrence time và UTC storage; convert trong `ZoneInfo`.
- **Nút trên thông báo báo interaction failed:** xem persistent callback registration/custom_id, ACK/defer, owner check, xử lý delivery stale.
- **Migration lỗi:** dừng app, xem Alembic current/history, **khôi phục từ backup trước migration** theo runbook được Codex ghi lại; không xóa `nova.db` cho nhanh.

## 12. Bàn giao cuối Phase 4

Codex phải ghi: files touched; schema changes; commands backup/migrate/test/run; test counts; actual smoke-test evidence; scheduler policy (retry, quiet hours, catch-up, recurrence, snooze); known limitations; P4 status trong ROADMAP. Không động đến P5.
