# Phase 4B/4C — Reminder Engine và Discord UI

**P4 đã nghiệm thu ngày 2026-11-17:** người dùng xác nhận đã kiểm thử xong, DB/Discord thật xác minh reminder DM sent và nút Đã làm acknowledged. Bộ tự động gần nhất **625 tests pass**; xem [`PHASE_4_FINAL_CHECK.md`](PHASE_4_FINAL_CHECK.md) cho bằng chứng và phạm vi kiểm chứng. Phần còn lại là báo cáo lịch sử tại mốc 4B/4C (617 tests), gồm các ghi chú chờ cấu hình/nghiệm thu trước xác nhận này; checklist vẫn dùng để hồi quy.

## Kết quả

Theo yêu cầu người dùng, đã tiếp tục cả **4B và 4C**, giữ các thay đổi 4A/sửa Windows đang có. **Source và kiểm thử tự động đạt: 617 passed in 48.84s**, Python **3.12.3**, Windows. Không triển khai P5/AI.

4B có owner-scoped repository/service, CRUD có xác nhận, recurrence, snooze/ack, durable claims/retry/recovery, quiet hours và Discord DM/private fallback. 4C có Reminders panel thật, bản nháp, date/time picker, links, filter/pagination, settings và persistent notification callbacks.

**Chưa nghiệm thu Discord thật.** Tại mốc triển khai 4B/4C chưa có `.env`/DB vận hành; sau kiểm tra cuối đã có `.env` mẫu nhưng chưa có cấu hình thật hoặc `nova.db`. Không chạy bot, không gửi thông báo thật, không backup/migrate DB vận hành. Các bằng chứng dưới đây dùng SQLite tạm và mock. Toàn P4 chưa đánh dấu DONE; cần checklist live phía cuối.

## Kiến trúc và schema

- `ReminderRepository` luôn owner-scope reminder và join delivery qua reminder owner. Service yêu cầu config owner ở mọi entry point, kể cả các phương thức worker và notification callbacks.
- `ReminderService` giữ transaction BEGIN IMMEDIATE cho writes, revalidate DTO/references, UUID5 từ owner/request_id chống duplicate create, timestamp snapshot chống stale update. Sửa/pause/resume/cancel và đổi notification settings phải có token approval gắn payload/owner/expected snapshot, TTL 5 phút; consume sau commit. Không có bảng pending_actions/AI executor P5.
- Một lock dùng chung cho mutations và dispatcher, bao gồm cửa sổ gửi Discord. Không giữ transaction DB trong lúc chờ Discord. Callback chỉnh sửa đến trong lúc gửi phải chờ; expected snapshot cũ bị từ chối sau worker update. Thiết kế dành cho **một process SQLite**, không tuyên bố multi-worker support.
- `ReminderDeliveryService` materialize occurrence, claim, fence completion bằng claim_token, ghi kết quả/retry và advance schedule. `ReminderDispatcher` chỉ điều phối polling/sender, một task cho mỗi client lifecycle.
- Migration mới **`0004_reminder_dispatch`**, parent `0003_reminders`: chỉ ADD 4 cột nullable `retry_at`, `claim_token`, `finished_reason`, `acknowledged_at` vào reminder_deliveries. Không rebuild hoặc xóa dữ liệu bảng cũ, không sửa migrations 0001–0003. ORM dùng UTCDateTime cho timestamps mới.
- Tests xác minh dữ liệu delivery từ schema 4A giữ nguyên, các cột mới NULL; lỗi giữa migration rollback mọi cột đã thêm. Downgrade 0004 → 0003 bị từ chối khi có bất kỳ delivery history, tránh mất metadata.

## Chính sách worker

| Nội dung | Chính sách đã triển khai |
|---|---|
| Poll | 15 giây, tối đa 25 due reminders/deliveries mỗi tick; chỉ chạy khi client sẵn sàng |
| Send timeout | 10 giây mỗi attempt |
| Retry | Tối đa 3 attempts tổng cộng; sau lỗi tạm thời chờ 1 phút rồi 5 phút |
| Permanent failure | DM Forbidden không có fallback hợp lệ, kênh không riêng tư/thiếu quyền/đã xóa: terminal `blocked`, không retry vô hạn |
| Retry exhausted | Delivery failed/exhausted; reminder scheduled chuyển paused để owner kiểm tra/resume |
| Claim recovery | Lease 2 phút; restart/crash giữ claim trong DB, sau lease mới claim lại; token cũ không được ghi đè completion mới |
| Catch-up | Quá 30 phút so với lịch ban đầu hoặc retry/lease due: ghi failed/overdue, không gửi dồn. One-time chuyển paused; recurring nhảy tới lần tương lai, chỉ ghi một occurrence bị bỏ qua |
| Quiet hours | Theo timezone trong Settings; delay tới cuối quiet hours, không đổi lịch logic. Hỗ trợ qua nửa đêm; boundary trong DST gap dùng phút hợp lệ đầu tiên. Trễ hơn 30 phút so với boundary sau downtime vẫn theo catch-up |
| Recurrence | Daily/weekly theo local time/timezone, không cộng cố định 24h UTC; DST gap bỏ ngày không có giờ đó, fold chọn occurrence đầu tiên, không lặp cùng ngày local. Next occurrence luôn lớn hơn mốc đã xử lý |
| One-time success | Chỉ done sau khi sender trả Discord message ID và DB commit; lỗi chưa có message ID không được hiển thị đã gửi |
| Snooze | Thêm delivery sau 15 phút, một child mỗi parent; không đổi recurrence/next_fire_at gốc. Có thể snooze tiếp từ child đã gửi. Trùng time slot có sẵn thì từ chối an toàn |
| Resume | One-time đã quá giờ: đề xuất mốc mới sau 1 phút; recurring: mốc local tương lai kế tiếp. Owner xem trước và Duyệt, không phát backlog |
| Notification actions | TTL 24h, owner + message ID + sent status bắt buộc. Done/Snooze đã xử lý hoặc stale sau chỉnh sửa/kỳ mới bị chặn. Tắt luôn cần xác nhận trạng thái hiện tại |

Gửi Discord và commit SQLite không atomic. Nếu gửi đã thành công nhưng process chết trước commit, retry sau lease có thể gửi lại. Tests tái hiện cửa sổ này; đây là **best-effort/at-least-once có giảm trùng**, không phải exactly-once.

Lỗi được lưu bằng mã allowlisted, không raw exception/body. Log chỉ có event, delivery UUID, attempt count, safe error code hoặc exception class; không có title, message content, token hoặc claim token.

## Quyền và vị trí gửi

- DM chỉ tới config owner. DM HTTP/network lỗi dùng retry; chỉ DM Forbidden hoặc DM bị tắt mới dùng fallback đã duyệt.
- `delivery_target=channel` phải trùng fallback channel trong user_settings. Không cho input tự chọn kênh tùy ý ngoài cấu hình.
- **Reminders → Cài đặt gửi** cho bật/tắt DM, chọn kênh bằng ChannelSelect và đặt quiet hours HH:MM. Mọi thay đổi được preview và Duyệt; backend kiểm tra lại private channel lúc thực thi, sender kiểm tra lại trước mỗi lần gửi.
- Chính sách fallback bảo thủ: chỉ TextChannel trên server do config owner sở hữu; @everyone không được View Channel; mọi role khác có quyền xem (kể cả Administrator) bị từ chối, ngoại trừ managed role của chính bot. Member overwrite cho người khác được xem cũng bị từ chối. Bot cần View Channel, Send Messages và Embed Links. Không tự sửa quyền server để cho phép gửi.
- Nếu owner đang có một role Administrator chung, kênh có thể bị từ chối dù chưa có người khác mang role. Dùng DM hoặc cấu hình quyền kênh/server không cấp View Channel qua role khác; guild owner vẫn có quyền quản lý vốn có. Không hạ kiểm tra private để gửi cho tiện.
- Done đánh dấu task liên kết chưa done là done trong cùng transaction với acknowledgment. Không tự mở lại task cancelled. Với reminder độc lập, chỉ ghi nhận occurrence; với recurring, lịch lặp tiếp tục. Task/event links là tuyệt đối, không offset và không tự dời reminder khi lịch/task thay đổi.

## Discord UI

`/menu → Reminders` mở panel ephemeral, không sửa dashboard neo. Có list 5 mục/trang, status filter active/paused/done/cancelled, Previous/Next, Back/Refresh, detail và 5 delivery gần nhất. Home đếm reminders active từ DB; bảng neo không công khai counts.

**Thêm** mở modal title và datetime nhập chính xác tùy chọn; sau đó bản nháp chọn ngày/giờ, once/daily/weekly, weekday, DM/kênh đã duyệt và task/event qua picker có pagination. Date picker legacy có lịch tháng, ngày/giờ/phút, không yêu cầu nhập ID. Chỉ Lưu mới ghi DB. Weekly phải khớp ngày/giờ đầu đã chọn, sai thì báo sửa; không đoán ngày.

Form/bản nháp giữ timezone khi mở, giữ fields/precision không chỉnh sửa. Bản nháp tối đa 10 phút, modal tối đa 5 phút; điều hướng không gia hạn. Lock chung chặn sửa dữ liệu trong lúc Save, view cũ/hết hạn bị chặn. Invalid time giữ title/raw input để sửa. Retry dùng cùng request ID; Discord render lỗi sau commit không submit create lần nữa.

Sửa, pause/resume/cancel và settings đều có before/after + Duyệt/Bỏ qua. Thay đổi reminder vô hiệu hóa các lần gửi/hoãn chưa xử lý; không hard-delete lịch sử. Active reminder được sửa phải có mốc tương lai. Approval stale/hết hạn/replay bị từ chối.

Thông báo có Đã làm / Hoãn 15 phút / Tắt. `discord.ui.DynamicItem` với stable prefix và delivery UUID được đăng ký lại lúc setup; button cũ sau restart không cần khôi phục danh sách message IDs. Backend xác minh owner/message/TTL/state trước thực thi. Panels/bản nháp/approval chưa lưu không restore; mở lại từ bảng neo. Embeds escape markdown/mentions, mọi gửi dùng AllowedMentions.none().

## Kiểm thử thực tế

| Lệnh | Kết quả |
|---|---|
| `.\.venv\Scripts\python.exe -m pytest -q` | **617 passed in 48.84s**, exit 0 |
| `.\.venv\Scripts\python.exe -m ruff check .` | All checks passed, exit 0 |
| `.\.venv\Scripts\python.exe -m ruff format --check .` | 118 files already formatted, exit 0 |
| `.\.venv\Scripts\python.exe -m compileall -q app alembic tests` | Pass, exit 0 |
| `.\.venv\Scripts\python.exe -m alembic heads` | `0004_reminder_dispatch (head)` |
| `.\.venv\Scripts\python.exe -m alembic history` | 0001 → 0002 → 0003 → 0004, một chuỗi |
| `git diff --check` | Pass, exit 0 |

Có **67 test cases mới** cho 4B/4C; một parameter case placeholder Reminders cũ được bỏ vì module đã có backend, tổng tăng ròng 66 so với 551 của 4A. Toàn bộ hồi quy cũ vẫn chạy; một số expected head/availability/count được cập nhật theo schema/UI thật.

Bao phủ service CRUD/owner/references/idempotency/stale/approvals; due/retry/permanent failure/catch-up/quiet hours/DST; restart lease và fencing; crash-window send-before-commit; duplicate delivery/notification action; expiry/message forgery; Done không mở lại task cancelled; DM/private ACL/error classification; lifecycle một worker và shutdown trước engine; UI create/picker/links/edit/status/settings/confirmations, invalid/expired/replaced views, Back/Refresh/filter/paging, dynamic callback registration, owner denials và render lỗi sau commit. Tests không gọi Discord/OpenAI thật.

## Backup, migrate và chạy trên máy có database thật

Không thêm dependencies/biến env mới. Giữ `.env`, config owner và file DB cũ. **Dừng bot/mọi process SQLite trước**, xác định đúng file, backup rồi mới upgrade. Không chạy lệnh tạo DB mới để thay cho file dữ liệu cũ chưa tìm thấy.

PowerShell tại project root:

```powershell
$novaDb = (& .\.venv\Scripts\python.exe -c "from app.config import database_url_from_mapping, environment; from sqlalchemy.engine import make_url; print(make_url(database_url_from_mapping(environment())).database)")
if ($LASTEXITCODE -ne 0) { throw "Không xác định được DB; dừng." }
$novaDb = [System.IO.Path]::GetFullPath($novaDb)
if (-not (Test-Path -LiteralPath $novaDb -PathType Leaf)) { throw "Không có DB cũ tại đường dẫn này; dừng." }
$novaBackup = Join-Path (Get-Location).Path ("backups\pre-phase-4bc-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".db")
.\.venv\Scripts\python.exe -m app.db.backup --output $novaBackup
if ($LASTEXITCODE -ne 0) { throw "Backup thất bại; không migrate." }
.\.venv\Scripts\python.exe -m alembic current
if ($LASTEXITCODE -ne 0) { throw "Không đọc được revision; dừng." }
.\.venv\Scripts\python.exe -m alembic upgrade 0004_reminder_dispatch
if ($LASTEXITCODE -ne 0) { throw "Migration lỗi; giữ bot dừng." }
.\.venv\Scripts\python.exe -m alembic check
if ($LASTEXITCODE -ne 0) { throw "Schema chưa khớp; giữ bot dừng." }
.\.venv\Scripts\python.exe -m alembic current
# Sau khi revision đúng, đã cấu hình token/owner và sẵn sàng nhận reminder:
.\.venv\Scripts\python.exe -m app.preflight
if ($LASTEXITCODE -ne 0) { throw "Preflight chưa đạt; giữ bot dừng và kiểm tra cấu hình/DB." }
.\.venv\Scripts\python.exe -m app.main
```

Linux dùng `.venv/bin/python` với cùng các module/arguments và đường dẫn backup mới. Startup tự migrate head, đăng ký DynamicItem và khởi động worker một lần lúc ready; shutdown dừng worker trước engine. Không chạy hai process với cùng SQLite/token. Backup có WAL đã commit, integrity check và no-overwrite như 4A.

Rollback 0004 → 0003 chỉ khi không có delivery history, bot đã dừng:

```powershell
.\.venv\Scripts\python.exe -m alembic downgrade 0003_reminders
if ($LASTEXITCODE -ne 0) { throw "Rollback bị từ chối; không xóa dữ liệu để ép chạy." }
```

Để vận hành schema 0003 phải dùng source tương ứng, vì source mới tự upgrade head. Có history thì giữ nguyên dữ liệu và restore snapshot vào file mới theo [runbook restore 4A](PHASE_4A_VALIDATION.md#rollback-và-restore), kiểm tra integrity/revision trước khi đổi file vận hành; giữ DB hiện tại cùng sidecars riêng tư. Restore đưa dữ liệu về thời điểm backup, không hợp nhất các thay đổi sau đó. Không có rollback/restore DB thật nào được chạy trong phiên này.

## Checklist live còn lại

1. Desktop và Mobile: `/menu → Reminders → Thêm`, chọn mốc sau 2 phút theo timezone Settings, Lưu; kiểm tra list/detail/counts. Chưa Lưu thì không có record.
2. Nhận DM thật gần giờ đã chọn; ghi nhận độ trễ. Hoãn 15 phút, bấm lặp và kiểm tra chỉ một delivery bổ sung; Đã làm với task liên kết, Tắt cần Duyệt.
3. Daily/weekly: gửi một occurrence rồi next_fire_at đúng local, không tạo reminder logic mới. Pause trước giờ không gửi; resume có preview mốc tương lai, Cancel/Bỏ qua/Duyệt đúng.
4. Restart trước giờ và sau giờ: dữ liệu còn, một worker, catch-up/overdue đúng policy. Bấm button notification cũ sau restart; stale/đã xử lý/hết hạn phải được báo rõ.
5. Cài đặt gửi: DM off/blocked, kênh fallback private, quiet hours qua nửa đêm. Kênh public/role khác có View Channel/thiếu quyền phải bị chặn, không có thông tin gửi ra kênh khác.
6. Non-owner slash/button/select/modal/notification bị chặn. Kiểm tra lại Tasks/Projects/Calendar/Today/Help/Settings, bảng neo và Back/Refresh, không rò dữ liệu hoặc tạo dashboard trùng.
7. Ghi kết quả bot online, migration thực tế, desktop/mobile, nhận DM, restart và fallback trước khi đánh dấu toàn P4 DONE.

## Files và điểm dừng

Tạo: migration 0004; `app/domain/reminder_delivery.py`; reminder repository; `reminder_service.py`, `reminder_delivery_service.py`; `app/scheduler/`; Discord reminder sender/controller/views/renderers; `tests/test_reminder_engine.py`, `test_reminder_sender.py`, `test_reminder_ui.py`, `test_reminder_dispatch_migration.py`; báo cáo này.

Sửa: delivery metadata trong models; CoreServices/DashboardService, NovaClient lifecycle, DashboardController route, module availability, dashboard/help/settings rendering, safe log metadata; expected head/count/UI trong tests; README/ROADMAP/DATABASE/DISCORD_UI. Giữ mọi thay đổi 4A/sửa Windows trước đó và handoff người dùng cung cấp, không commit/push hoặc đổi nhánh.

**Dừng sau source/tests 4C.** Không triển khai P5. P4 còn nghiệm thu Discord/DB vận hành thật theo checklist trên.
