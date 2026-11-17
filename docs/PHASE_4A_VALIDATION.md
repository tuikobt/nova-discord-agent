# Phase 4A — Models, migration và validation

**Báo cáo lịch sử checkpoint 4A.** Theo yêu cầu tiếp theo của người dùng, source 4B/4C đã được triển khai và head hiện tại là `0004_reminder_dispatch`. Dùng [runbook và checklist hiện tại](PHASE_4BC_VALIDATION.md) để nâng cấp/vận hành; các kết quả và lệnh dưới đây mô tả mốc 4A.

## Kết quả và phạm vi nghiệm thu

Người dùng yêu cầu nghiệm thu Phase 3 bằng các khả năng hiện có và tiếp tục **chỉ Phase 4A**. Baseline Phase 3 sau sửa Windows đã chạy lại: **431 passed in 26.33s**, Python **3.12.3**, Windows. Các tests bao phủ CRUD qua mocked Discord callbacks, owner isolation, timezone/DST, overlap/confirmations, counts, restart, migrations và backup/restore. Đây là **nghiệm thu tự động**; chưa tự đăng nhập Discord hoặc kiểm chứng Desktop/Mobile thực tế. Việc tiếp tục 4A được người dùng yêu cầu rõ ràng, không phải bằng chứng đã chạy live smoke test.

**Source/tests 4A đạt: 551 passed in 35.14s**, gồm 120 test cases mới và toàn bộ hồi quy P1–3. Chưa làm repositories/ReminderService CRUD, worker, sender, reminder UI hay AI. Module Reminders vẫn Sắp ra mắt; không có thông báo nào được gửi.

**Database vận hành chưa có trên máy này.** Không có `.env`; DATABASE_URL cấu hình hiện tại resolve tới `C:\Users\FPT\OneDrive\Desktop\nova-discord-agent\nova.db`, file không tồn tại. Không tự tạo DB vận hành, không tạo fake owner/data và không chạy upgrade trên file này. Vì vậy chưa có backup hoặc migration DB thật; các bằng chứng backup/upgrade/restore bên dưới dùng SQLite tạm có dữ liệu P1–3 synthetic. Cần chạy runbook trên máy giữ DB thật trước khi vận hành source mới.

## Schema và ràng buộc

Revision mới **`0003_reminders`**, parent **`0002_core_management`**. Giữ nguyên nội dung migrations 0001/0002.

- Tạo `reminders` theo DATABASE.md: owner, task/event links tùy chọn, title, next_fire_at, recurrence type/config, delivery target/channel, status và timestamps. Thêm indexes `(status, next_fire_at)`, `(owner_id, status)` và các link/owner.
- Tạo `reminder_deliveries`: occurrence UTC, trạng thái, số lần thử, mã lỗi an toàn, message ID, claimed/sent timestamps; unique `(reminder_id, scheduled_fire_at)` và index `(status, scheduled_fire_at)`.
- Thêm unique index **`ux_calendar_events_id_owner`** trên `(id, owner_id)`, làm đích FK ghép. Đây là CREATE INDEX; không rebuild hoặc thay cột/bản ghi của bất kỳ bảng P1–3 nào.
- `reminders.owner_id` tham chiếu users; `(task_id, owner_id)` và `(event_id, owner_id)` dùng FK ghép tới task/event cùng owner, kể cả khi ghi SQL bỏ qua ORM. NULL link hợp lệ. Quan hệ ORM chỉ đồng bộ cột link, không tự đổi owner.
- Delivery thuộc owner thông qua reminder cha. Tất cả FK mới dùng RESTRICT; không cascade xóa task/event, reminders hoặc lịch sử delivery. Backend 4B vẫn phải xác thực config owner và owner-scope mọi query; models không tự cấp quyền cho actor.
- CHECK cho title, enums, số lần thử nguyên không âm, quy tắc có/không config, DM/channel tương ứng. ORM và domain kiểm tra JSON, timezone, thời gian và toàn bộ record; SQL CHECK bảo vệ cấu trúc cơ bản, không tự diễn giải lịch JSON.
- `last_error_code` chỉ nhận `forbidden`, `http_error`, `network_error`, `timeout`, `unknown_error` hoặc NULL. Sender 4B phải phân loại exception thành mã, không lưu response body/exception text.

### Schema chuẩn bị cho snooze

Thêm `delivery_kind=scheduled|snooze` và `parent_delivery_id` vào deliveries. Scheduled delivery không có parent; snooze phải có parent. FK ghép `(parent_delivery_id, reminder_id)` đảm bảo parent thuộc cùng reminder; cấm tự trỏ chính nó. Unique parent cho phép tối đa một lần hoãn từ một delivery; có thể tiếp tục hoãn từ delivery snooze vừa nhận để tạo chuỗi.

Snooze sau này chỉ bổ sung occurrence, không ghi đè recurrence hoặc next_fire_at gốc. Unique `(reminder_id, scheduled_fire_at)` vẫn giữ: nếu thời điểm snooze trùng một occurrence có sẵn thì service 4B phải xử lý rõ ràng, không overwrite. **4A mới tạo ràng buộc, chưa thực thi snooze hoặc chống double click ở UI.** Không cam kết exactly-once khi gửi Discord.

## Hợp đồng validation cho 4B

`app/domain/reminders.py` độc lập Discord/SQL, dùng lại tiện ích UTC/local của Phase 3:

- `ReminderData`: immutable, title tối đa 250 ký tự; datetime phải aware và chuẩn hóa UTC; validate UUID links, enums và Discord channel ID. Owner không nhận từ input DTO.
- `RecurrenceRule`: immutable, `time` theo HH:MM, IANA timezone; daily không có weekday, weekly cần weekday nguyên 0–6 (Thứ Hai–Chủ nhật). JSON chỉ có `time`, `timezone`, tùy loại có `weekday`; không nhận trường lạ.
- `none` không có config. Daily/weekly yêu cầu lần gửi đầu khớp giờ/ngày local, chính xác tới phút. Quy tắc được lưu theo local timezone; không thay thành chu kỳ cố định 24 giờ UTC. Test qua DST chứng minh cùng 09:00 local có thể cách nhau 23 giờ UTC.
- Thời gian local thiếu/không rõ hoặc rơi vào DST gap/fold bị utility từ chối; datetime có offset tường minh được chuẩn hóa. Overflow đổi timezone trả ValidationError an toàn.
- Service create 4B bắt buộc gọi **`data.validate_create(now=backend_clock)`**, từ chối thời điểm quá khứ/hiện tại và trạng thái terminal. Constructor/ORM vẫn cho đọc/lưu lịch sử occurrence đã qua, không dùng đồng hồ hiện tại để làm hỏng dữ liệu cũ.
- `data.to_storage()` trả config mới, không để mutation dict thay đổi rule gốc. ORM kiểm tra lại record đầy đủ trước insert/update.
- `delivery_target=channel` chỉ kiểm tra ID/cấu trúc trong 4A. Private channel/allowlist/permission, liên kết actor, retry/catch-up/quiet hours, tính occurrence tiếp theo, offset theo event và confirmation/stale handling thuộc 4B. Link event hiện là mốc tuyệt đối, không có offset hoặc tự dời reminder khi sửa event.

## Kiểm thử thực tế

| Lệnh | Kết quả |
|---|---|
| `.\.venv\Scripts\python.exe -m pytest -q` | **551 passed in 35.14s**, exit 0 |
| `.\.venv\Scripts\python.exe -m ruff check .` | All checks passed, exit 0 |
| `.\.venv\Scripts\python.exe -m ruff format --check .` | 101 files already formatted, exit 0 |
| `.\.venv\Scripts\python.exe -m compileall -q app alembic tests` | Pass, exit 0 |
| `.\.venv\Scripts\python.exe -m alembic heads` | `0003_reminders (head)` |
| `.\.venv\Scripts\python.exe -m alembic history` | 0001 → 0002 → 0003, một chuỗi |
| `git diff --check` | Pass, exit 0 |

Tests dùng database file tạm, fake clocks khi cần và mock Discord; không gọi dịch vụ ngoài. Những điểm đã kiểm tra:

- DB rỗng upgrade head, FK ON, metadata không lệch migration; CLI upgrade/check/downgrade/reupgrade trên DB tạm.
- Tạo bản P3 có dữ liệu trên toàn bộ 6 bảng P1–3, backup bằng SQLite API rồi upgrade bản sao. Mọi cột dữ liệu và table DDL cũ khớp trước/sau; FK/integrity đạt. SHA-256 của file nguồn không đổi.
- Downgrade P4 rỗng → P3 rồi upgrade lại, restore backup vào file mới; dữ liệu giữ nguyên. Downgrade có reminder/delivery, kể cả terminal, bị từ chối. Offline downgrade bị từ chối.
- Ngắt migration sau khi tạo bảng deliveries: transaction rollback cả hai bảng mới, unique index và revision; dữ liệu P1–3 giữ nguyên, retry thành công.
- Owner FK từ SQL trực tiếp, quan hệ ORM không đổi owner, RESTRICT không cascade; UTC round-trip của reminder và delivery, từ chối naive timestamps.
- Một occurrence chỉ có một delivery, kể cả hai coroutine ghi đồng thời hoặc cùng instant với offsets khác nhau. Snooze cùng parent/cross-reminder/self-parent bị chặn đúng; recurrence không bị ghi đè.
- Recurrence JSON, daily/weekly/weekday/timezone, DST, thời gian tạo mới, invalid enum/count/channel/error code và rollback khi insert lỗi.

## Backup và migration trên DB thật

**Các lệnh này là runbook, chưa chạy trên database vận hành.** Dừng bot bằng Ctrl+C và đóng các process dùng SQLite trước. Đặt DATABASE_URL đúng file cũ bằng cấu hình hiện có; không thay owner, không stamp revision hoặc xóa DB để nâng cấp.

PowerShell tại thư mục project:

```powershell
$novaDb = (& .\.venv\Scripts\python.exe -c "from app.config import database_url_from_mapping, environment; from sqlalchemy.engine import make_url; print(make_url(database_url_from_mapping(environment())).database)")
if ($LASTEXITCODE -ne 0) { throw "Không xác định được database; dừng." }
$novaDb = [System.IO.Path]::GetFullPath($novaDb)
if (-not (Test-Path -LiteralPath $novaDb -PathType Leaf)) { throw "Không tìm thấy DB cũ; dừng, không tạo DB thay thế." }
$novaDb
$novaBackup = Join-Path (Get-Location).Path ("backups\pre-phase-4a-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".db")
.\.venv\Scripts\python.exe -m app.db.backup --output $novaBackup
if ($LASTEXITCODE -ne 0) { throw "Backup thất bại; không migrate." }
.\.venv\Scripts\python.exe -m alembic current
if ($LASTEXITCODE -ne 0) { throw "Không đọc được revision; dừng." }
.\.venv\Scripts\python.exe -m alembic upgrade 0003_reminders
if ($LASTEXITCODE -ne 0) { throw "Migration lỗi; giữ bot dừng và kiểm tra/restore." }
.\.venv\Scripts\python.exe -m alembic check
if ($LASTEXITCODE -ne 0) { throw "Schema chưa khớp; chưa chạy bot." }
.\.venv\Scripts\python.exe -m alembic current
```

Backup tool lấy snapshot nhất quán, gồm WAL đã commit, kiểm tra integrity và không ghi đè file đã có. Giữ backup riêng tư, thư mục bị gitignore; Windows cần ACL phù hợp. Revision sau upgrade là `0003_reminders`; chưa có scheduler hoặc nút tạo reminder. Startup source mới vẫn tự upgrade head, do đó phải backup trước khi chạy bot.

## Rollback và restore

Nếu hai bảng P4 vẫn rỗng, dừng bot rồi chạy:

```powershell
.\.venv\Scripts\python.exe -m alembic downgrade 0002_core_management
if ($LASTEXITCODE -ne 0) { throw "Rollback bị từ chối; giữ dữ liệu, không xóa bảng để ép chạy." }
.\.venv\Scripts\python.exe -m alembic current
```

Lệnh bỏ hai bảng P4 rỗng và unique index mới, giữ mọi dữ liệu P1–3. Có dữ liệu P4 thì từ chối; không tự xóa để cho downgrade chạy. Muốn vận hành ở schema P3 phải dùng source tương ứng; source 4A tự upgrade lại khi startup.

Khi cần restore snapshot, ưu tiên phục hồi vào **file mới** để không ghi đè DB hiện tại. Với `$novaDb` và `$novaBackup` đã xác định từ runbook:

```powershell
$novaRestored = Join-Path (Split-Path -Parent $novaDb) ("nova-restored-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".db")
.\.venv\Scripts\python.exe -c "from pathlib import Path; import sys; from app.db.backup import backup_database; backup_database(Path(sys.argv[1]), Path(sys.argv[2])); print('Restore integrity OK')" $novaBackup $novaRestored
if ($LASTEXITCODE -ne 0) { throw "Restore thất bại; giữ bot dừng." }
.\.venv\Scripts\python.exe -c "import sqlite3, sys; from pathlib import Path; from contextlib import closing; path = Path(sys.argv[1]).resolve(); connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True); print(connection.execute('PRAGMA integrity_check').fetchall()); print(connection.execute('SELECT version_num FROM alembic_version').fetchall()); connection.close()" $novaRestored
```

Snapshot trước 4A ở revision `0002_core_management` nếu DB nguồn đã ở P3. Restore đưa dữ liệu về thời điểm backup, không hợp nhất thay đổi về sau. Muốn trả snapshot về đúng file vận hành, dừng toàn bộ process SQLite, giữ DB hiện tại cùng sidecars trong nơi riêng tư rồi dùng quy trình [restore Phase 3A](PHASE_3A_VALIDATION.md#3-nếu-migration-thất-bại) với đúng snapshot 4A; không trộn WAL cũ với file mới. Chưa thực hiện thay file vận hành trong phiên này.

## Files và điểm dừng

Tạo mới: `app/domain/reminders.py`, `alembic/versions/0003_reminders.py`, `tests/test_reminder_validation.py`, `tests/test_reminder_models.py`, `tests/test_reminder_migration.py`, báo cáo này.

Sửa trong 4A: `app/domain/enums.py`, `app/db/models.py`, `tests/test_database.py`, `tests/test_core_migration.py`, README/ROADMAP/DATABASE và ghi chú nghiệm thu kỹ thuật trong báo cáo 3C. Các thay đổi sửa Windows từ lượt trước giữ nguyên; `docs/NOVA_PHASE_4_HANDOFF.md` do người dùng cung cấp, không sửa.

**Dừng ở 4A.** Source/tests đạt; backup/migration DB vận hành còn chờ file thật. Không bắt đầu 4B/4C/P5, không đánh dấu toàn P4 DONE.
