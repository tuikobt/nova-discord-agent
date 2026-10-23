# Phase 3A — Database & Migration: bàn giao

Ngày: **2026-10-23**. **3A hoàn tất**; Phase 3 còn 3B/3C, chưa DONE. Phase 1/2 giữ nguyên hành vi. Không triển khai services CRUD, Discord CRUD UI, AI, scheduler hoặc integration.

## Repository và database ban đầu

- Nhánh lúc bắt đầu là `main`, hiện tại là `feat/phase-3` theo thay đổi workspace của người dùng. Handoff người dùng cung cấp hiện là `docs/PHASE_3_HANDOFF.md` (ban đầu mang tên `NOVA_PHASE_3_HANDOFF.md`), chưa được Git theo dõi. Đã đọc lại tài liệu sau đổi tên, không sửa nội dung handoff.
- Đã đọc các tài liệu quy định và kiểm tra toàn bộ source `app/`, config, engine/session, repositories/services Foundation, Discord adapter/views/renderers cùng Alembic và tests hiện có.
- `DATABASE_URL` resolve tới `/home/minhphuonglee/Desktop/nova-discord-agent/nova.db`. Chỉ xác định đường dẫn, schema/revision; không in token hoặc nội dung record riêng tư.
- Schema thực tế trước triển khai: `users`, `user_settings`, `audit_logs`, `alembic_version`; revision `0001_foundation`. Migration 0001 và cơ chế async transaction/PRAGMA đã có, được giữ nguyên.
- Backup đã tạo bằng `python -m app.db.backup --output backups/pre-phase-3a-20261023.db`, integrity đạt. Thư mục backup đã gitignore; file có quyền POSIX `0600`, thư mục mới `0700`. Trên Windows phải dùng thư mục/ACL riêng tư.
- **DB đang dùng chưa được migrate.** Lần kiểm tra cuối chạy trên bản sao backup trong `/tmp/nova-phase3a-oiq4xn9h/`. Các bản sao chứa dữ liệu riêng tư, không đưa vào Git/chia sẻ.

## Cấu trúc và ràng buộc

Migration mới: **`0002_core_management`**, parent **`0001_foundation`**. Chỉ tạo ba bảng/indexes mới; không sửa hoặc rebuild bảng P1/P2.

| Bảng | Cột |
|---|---|
| `projects` | id, owner_id, name, description, status, deadline_at, created_at, updated_at |
| `tasks` | id, owner_id, project_id nullable, title, description, status, priority, estimated_minutes nullable, due_at nullable, completed_at nullable, version, created_at, updated_at |
| `calendar_events` | id, owner_id, task_id nullable, title, starts_at, ends_at, status, is_fixed, origin, version, created_at, updated_at |

- PK UUID string do ứng dụng sinh; owner snowflake string FK tới `users`. Config allowlist vẫn là nguồn xác thực, có record DB không tự cấp quyền.
- FK ghép `tasks(project_id, owner_id) → projects(id, owner_id)` và `calendar_events(task_id, owner_id) → tasks(id, owner_id)` enforce cùng owner tại DB cả khi bypass ORM validators. Bảng cha có UNIQUE `(id, owner_id)` để làm đích FK. Không thêm multi-tenant API.
- Quan hệ Project.tasks / Task.project / Task.calendar_events / CalendarEvent.task có `back_populates`, join xét owner, chỉ đồng bộ cột link. Không tự ghi đè owner khi gán relationship. Dùng `selectinload` rõ ràng, không implicit async I/O.
- `RESTRICT` khi xóa bản ghi cha có tham chiếu; không tự cascade hoặc unlink. Việc archive/cancel/confirmation thuộc 3B/3C.
- CHECK: enum lowercase theo DATABASE.md, name/title có nội dung và tối đa 200/250 ký tự, estimated_minutes nguyên >0 nếu có, version nguyên >0, `ends_at > starts_at`, `is_fixed` boolean. ORM validators bắt thêm whitespace-only, kiểu số/bool không đúng.
- Defaults: project active; task todo/medium; event proposed/manual/non-fixed; version 1. Enum chứa agent/integration để khớp schema, không có chức năng AI/integration.
- Dùng lại `UTCDateTime`: input phải timezone-aware, chuẩn hóa UTC khi bind, SQLite lưu datetime không offset đã chuẩn hóa, đọc trở lại UTC-aware. Chuyển bằng `ZoneInfo` khi hiển thị; tests kiểm tra giờ Việt Nam 20:00 → UTC 13:00 → giờ Việt Nam 20:00.
- ORM cấp created_at/updated_at, cập nhật updated_at khi sửa; Task/Event dùng optimistic `version_id_col`. Chỉ bảo vệ ORM flush, không bảo vệ bulk SQL; 3B phải dùng expected version phù hợp.
- `Database.initialize()` vẫn chạy Alembic trong transaction với `foreign_keys=ON` mỗi connection. Tests kiểm tra lỗi DDL và lỗi DML rollback toàn bộ transaction.

| Bảng | Indexes |
|---|---|
| projects | `(owner_id, status)` |
| tasks | `(owner_id, status, due_at)`, `(project_id, status)` |
| calendar_events | `(owner_id, starts_at, ends_at)`, `(task_id, owner_id)` |

Không có DB constraint cấm overlap tuyệt đối: cảnh báo và xác nhận khi cố ý giữ trùng thuộc 3B/3C. Đồng bộ status/completed_at, owner-scoped CRUD, progress và idempotency cũng chưa triển khai.

## Kết quả kiểm thử thực tế

Môi trường: Linux, Python **3.12.15**, dependencies hiện có, không thêm package. Mốc trước triển khai: **159 passed in 2.18s**. Lần chạy toàn bộ sau thay đổi code: **250 passed in 5.41s**.

| Lệnh / kiểm tra | Kết quả |
|---|---|
| `.venv/bin/python -m pytest -q` | **250 passed in 5.41s**; gồm toàn bộ hồi quy P1/P2 và 91 tests mới |
| `.venv/bin/python -m ruff check .` | Pass |
| `.venv/bin/python -m ruff format --check .` | Pass, 63 files already formatted |
| `.venv/bin/python -m compileall -q app alembic tests` | Pass |
| `git diff --check` | Pass |
| Upgrade/downgrade/reupgrade trên bản sao backup DB Phase 2 thực tế | Pass; mọi cột users/settings/audit còn nguyên, gồm timezone, preferences và dashboard IDs |
| Restore backup vào file mới + kiểm tra nguồn | Pass; dữ liệu Foundation khớp, hash file `nova.db` không thay đổi |

Tests tự động dùng database tạm/synthetic records, mock Discord và fixture chặn mạng; không gọi Discord API. Kiểm tra bản sao DB thực tế là bước riêng, chỉ báo pass/fail, không xuất nội dung riêng tư. Pytest cần chạy ngoài sandbox do hạn chế asyncio/socket nội bộ của môi trường; không phải để truy cập dịch vụ ngoài.

Phạm vi tests mới:

- Migration DB mới, schema khớp metadata, upgrade từ 0001 có dữ liệu, chạy initialize nhiều lần, indexes và `foreign_key_check`.
- Nâng cấp bị ngắt sau DDL rollback về nguyên schema/revision 0001; retry thành công, Foundation nguyên vẹn.
- Downgrade bảng mới rỗng về 0001 và upgrade lại; downgrade bị từ chối khi bất kỳ bảng P3 có dữ liệu.
- Relationships hai chiều, nullable links, UUID/defaults, restart persistence.
- FK thiếu cha/owner, insert/update và thay owner tạo liên kết chéo bị từ chối; gán relationship không đổi owner âm thầm; chặn xóa cha.
- Tên rỗng/quá dài, enum sai, thời lượng/version không hợp lệ, boolean sai, end<=start; direct SQL không vượt DB checks. Datetime thiếu timezone bị từ chối.
- UTC/local round-trip, optimistic stale write, timestamp update, DML unit-of-work rollback.
- Backup có dữ liệu WAL đã commit; no-overwrite, missing/invalid source, cleanup khi thất bại, restore vào file mới, CLI không cần Discord credentials.

Chưa chạy bot thật, PowerShell trên Windows hoặc thử Discord trong phiên 3A. UI không đổi; nghiệm thu toàn Phase 3 phải đợi 3C.

## Migration và khôi phục

### 1. Dừng bot và xác định file

Nhấn `Ctrl+C` ở phiên bot đang chạy. Không chạy đồng thời hai process dùng cùng SQLite. Đường dẫn tương đối trong `.env` tính từ project root; environment của process ưu tiên `.env`. Không cần token cho công cụ backup hoặc Alembic.

PowerShell, tại project root:

```powershell
$novaDb = (& .\.venv\Scripts\python.exe -c "from app.config import database_url_from_mapping, environment; from sqlalchemy.engine import make_url; print(make_url(database_url_from_mapping(environment())).database)")
if ($LASTEXITCODE -ne 0) { throw "Không xác định được database; dừng." }
$novaDb
.\.venv\Scripts\python.exe -m alembic current
```

Lệnh chỉ in đường dẫn, không in các biến secrets. Đối chiếu file đúng trước khi tiếp tục. Không thay DATABASE_URL để né migration và không xóa DB.

### 2. Backup rồi migrate

```powershell
$novaBackup = ".\backups\pre-phase-3a-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".db"
.\.venv\Scripts\python.exe -m app.db.backup --output $novaBackup
if ($LASTEXITCODE -ne 0) { throw "Backup thất bại; không migrate hoặc khởi động bot." }
.\.venv\Scripts\python.exe -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw "Migration lỗi; giữ bot dừng và kiểm tra/restore." }
.\.venv\Scripts\python.exe -m alembic check
if ($LASTEXITCODE -ne 0) { throw "Schema chưa khớp; giữ bot dừng." }
.\.venv\Scripts\python.exe -m alembic current
```

Kết quả mong đợi: `0002_core_management (head)`, `alembic check` không có thay đổi schema. Sau đó có thể chạy `python -m app.main` như README. Panels vẫn “Sắp ra mắt”, chưa có CRUD.

Trên Linux (dừng nếu bất kỳ bước nào thất bại):

```bash
.venv/bin/python -m app.db.backup --output backups/pre-phase-3a-manual.db
.venv/bin/python -m alembic current
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m alembic check
.venv/bin/python -m alembic current
```

Backup trùng tên sẽ bị từ chối, chọn tên mới thay vì ghi đè. Máy mới chưa có DB: chạy `alembic upgrade head` từ database rỗng, không cần backup file chưa tồn tại.

### 3. Nếu migration thất bại

Giữ bot dừng. Kiểm tra `alembic current` và lỗi an toàn trước khi chạy lại. Với engine hiện tại, DDL được bao trong transaction: tests cho thấy lỗi ở migration 0002 rollback về 0001 mà không mất dữ liệu cũ. Không tự `stamp head`, xóa bảng hoặc reset DB để che lỗi.

Nếu đã upgrade thành công nhưng cần quay schema về P2 **và cả ba bảng P3 còn rỗng**, có thể dùng:

```powershell
.\.venv\Scripts\python.exe -m alembic downgrade 0001_foundation
```

Lệnh từ chối khi có dữ liệu P3; không tự xóa dữ liệu để cho lệnh chạy. Nếu muốn giữ schema P2, dùng source P2 trước khi khởi động lại: source hiện tại sẽ tự upgrade head lúc startup.

Khi cần restore đúng mốc snapshot, giữ lại DB lỗi cùng sidecars để có thể kiểm tra/lấy lại thay đổi sau backup. **Restore đưa dữ liệu về thời điểm backup**, không tự hợp nhất các thay đổi mới. Thao tác dưới đây chỉ chạy khi bot và mọi process đang dùng DB đã dừng, `$novaDb` là đúng file ở bước 1, `$novaBackup` là đúng snapshot cần phục hồi:

```powershell
$novaQuarantine = Join-Path ".\backups" ("failed-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
New-Item -ItemType Directory -Path $novaQuarantine -ErrorAction Stop | Out-Null
foreach ($novaSuffix in @("", "-wal", "-shm", "-journal")) {
    $novaPart = $novaDb + $novaSuffix
    if (Test-Path -LiteralPath $novaPart) {
        Move-Item -LiteralPath $novaPart -Destination $novaQuarantine -ErrorAction Stop
    }
}
.\.venv\Scripts\python.exe -c "from pathlib import Path; import sys; from app.db.backup import backup_database; print(backup_database(Path(sys.argv[1]), Path(sys.argv[2])))" $novaBackup $novaDb
if ($LASTEXITCODE -ne 0) { throw "Restore chưa thành công; giữ bot dừng." }
.\.venv\Scripts\python.exe -m alembic current
```

Backup tool kiểm tra integrity và không ghi đè file đích. Sau restore snapshot trước 3A, revision phải là `0001_foundation`. Nếu muốn tiếp tục 3A, xử lý nguyên nhân lỗi rồi chạy upgrade/check lại; nếu muốn vận hành P2 thì dùng source tương ứng, tránh startup tự nâng cấp lại. Không tự thay owner ID. Quy trình restore đã thử trên Linux bằng cùng hàm backup vào file mới; đoạn PowerShell chưa được chạy trên Windows.

## File tạo/sửa

Tạo mới:

- `app/domain/enums.py`
- `app/db/backup.py`
- `alembic/versions/0002_core_management.py`
- `tests/test_core_models.py`
- `tests/test_core_migration.py`
- `tests/test_database_backup.py`
- `docs/PHASE_3A_VALIDATION.md`

Sửa:

- `app/db/models.py`: thêm models/relationships/constraints/validators/versioning.
- `alembic/env.py`: nạp metadata của toàn bộ models.
- `tests/test_database.py`: kỳ vọng schema/revision mới, giữ các test Foundation.
- `.gitignore`: bỏ qua thư mục backups.
- `README.md`, `docs/ROADMAP.md`, `docs/DATABASE.md`, `docs/DISCORD_UI.md`: trạng thái 3A và runbook, giữ P3 chưa DONE.

Không sửa migration 0001, engine/session, config/token, Discord source hoặc services P1/P2. Handoff chưa theo dõi có sẵn từ người dùng không tính là file mới do 3A tạo. Backup/copies là dữ liệu local, không phải source để commit.

## Các phần còn lại của Phase 3

- **3B:** repositories owner-scoped và services CRUD; completed_at khi done/reopen; progress theo task không cancelled; filters/pagination; validation quyền resource; calendar overlap theo khoảng nửa mở; expected version, duplicate submit và transaction rules.
- **3C:** nối UI P2 với services, modals/buttons/list/detail, xác nhận hủy/xóa/giữ lịch trùng, counts thật, kiểm tra Discord Desktop/Mobile và restart, nghiệm thu Phase 3 với người dùng.

**Dừng sau 3A.** Không bắt đầu 3B/3C hoặc Reminder/AI trong lần bàn giao này.
