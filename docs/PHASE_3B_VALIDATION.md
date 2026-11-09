# Phase 3B — Repositories & Services: bàn giao

Ngày: **2026-10-23**. **3B hoàn tất**, toàn bộ **340 tests pass**. Phase 3 còn 3C, chưa DONE. Người dùng yêu cầu tiếp tục sau bàn giao 3A; phạm vi lần này chỉ backend và tests theo handoff.

## Phạm vi và hiện trạng

- Bắt đầu từ nhánh sạch `feat/phase-3`, đã có schema/migration và 250 tests Phase 1–3A.
- Đã đọc lại tài liệu và kiểm tra source hiện có. Tận dụng async engine/session, models, owner authorization và UTCDateTime; không viết lại Foundation/Dashboard.
- Có repositories/services Projects, Tasks, Calendar; DTO validated, kết quả immutable và lỗi nghiệp vụ tiếng Việt để adapter xử lý.
- Giữ nguyên schema **`0002_core_management`**, không có dependency hoặc biến `.env` mới. Không sửa migration 0001/0002 hoặc ORM models.
- Không đọc/sửa DB thực tế, không chạy migration lên `nova.db`, không chạy bot hoặc Discord API trong phiên 3B. Database trong tests là file tạm.
- Không nối services vào Discord, không thêm button/modal/slash CRUD, không đổi counts/empty-state P2. Không có reminder, AI, integration hoặc module tương lai.

## Repository và transaction

`ProjectRepository`, `TaskRepository`, `CalendarRepository` dùng `CoreRepository` với owner scope bắt buộc. Get/list/count/progress/conflict/update đều có owner predicate. Bản ghi không tồn tại và bản ghi của owner khác trả cùng NotFoundError. Liên kết project/task được service tra cứu trong scope trước khi ghi; FK ghép 3A vẫn bảo vệ tầng DB.

Repository không tự commit. Service dùng transaction bao toàn bộ validate reference → kiểm tra trạng thái/conflict → ghi → commit; chỉ trả kết quả sau commit. Lỗi flush/commit rollback và chuyển sang StorageError an toàn, không đưa SQL/parameters/private payload vào thông báo.

UPDATE task/event có điều kiện `owner_id + id + expected version`, tăng version một đơn vị. Project dùng `owner_id + id + expected updated_at`, timestamp mới tăng ít nhất 1 microsecond. Trường ID/owner/version/origin không nhận từ payload cập nhật.

Writes của services mới yêu cầu execution option `nova_sqlite_immediate=True` trước lần query đầu. Listener BEGIN hiện có chỉ chọn BEGIN IMMEDIATE cho tùy chọn đó; các transaction Foundation/migration giữ BEGIN cũ. Điều này reserve SQLite writer trước read-check-write, giúp request sau thấy commit mới khi kiểm tra stale/overlap. Busy/DB failures vẫn trả lỗi để retry, không hứa multi-worker support. Cơ chế BEGIN và execution options được đối chiếu với [SQLite transactions](https://www.sqlite.org/lang_transaction.html) và [SQLAlchemy Session.connection](https://docs.sqlalchemy.org/en/21/orm/session_api.html#sqlalchemy.orm.Session.connection).

## Hợp đồng services cho 3C

Khởi tạo services từ cùng `database.sessions` và `OwnerAuthorization` lấy owner cấu hình. Giữ service instances sống qua các interactions để dùng lại pending actions. Không tạo lại service mỗi lần submit/approve.

| Service | API |
|---|---|
| Cả ba | `get(actor_id, id)`; `create(actor_id, data, request_id=..., approval_token=None)`; `update(actor_id, id, data, expected=..., approval_token=None)` |
| ProjectService | `list(actor_id, status=None, page=0, page_size=10)`; `progress(actor_id, project_id)`; `archive(actor_id, id, expected=updated_at, approval_token=None)` |
| TaskService | `list(actor_id, status=None, priority=None, project_id=None, due_from=None, due_until=None, page=0, page_size=10)`; `set_status(actor_id, id, status, expected=version, approval_token=None)` |
| CalendarService | `list(actor_id, starts_at, ends_at, status=None, page=0, page_size=10)`; `list_day` / `list_week` với date và timezone; `cancel(actor_id, id, expected=version, approval_token=None)` |

Các tham số sau data/id ở bảng là keyword arguments. Project mutation yêu cầu updated_at UTC đầy đủ từ snapshot; Task/Event yêu cầu version nguyên dương từ snapshot. Adapter không được thay version/timestamp bằng giá trị tự đoán hoặc chuỗi đã format mất precision.

Inputs: `ProjectData`, `TaskData`, `EventData`; outputs: `ProjectRecord`, `TaskRecord`, `EventRecord`, `Page` và `ProjectProgress`. Không trả ORM object/session hoặc lazy relationships ra UI.

**Update là thay thế toàn bộ phần editable**, không phải patch từng trường. Khi mở form sửa, lấy snapshot rồi dùng `to_record(TaskData, before)` (tương tự ProjectData/EventData) và `dataclasses.replace` những field người dùng đổi. Giữ các field còn lại, truyền expected snapshot. Nullable field `None` có nghĩa xóa liên kết/deadline/description; không dựng DTO mới chỉ có title rồi vô tình reset các field khác.

### Projects và Tasks

- Project có create/list/get/update, status active/paused/completed, archive có duyệt và có thể mở lại bằng update status active. Archive không xóa/gỡ liên kết tasks.
- Task có create/list/get/update, priority/estimated_minutes/due_at/project, status todo/doing/done/cancelled. Done đặt completed_at UTC; sửa task đang done giữ mốc đó; reopen hoặc cancel xóa completed_at. Cancel cần duyệt.
- Hoàn thành/hủy task không tự hủy hoặc dời CalendarEvent liên kết. Project completed cũng không tự đánh dấu tất cả tasks done.
- Progress = số task done / số task không cancelled. Không có task trả 0% cùng “Chưa có nhiệm vụ”; mô tả rõ tỷ lệ số lượng task.
- Không hard-delete; CRUD dùng archive/cancel làm thao tác loại khỏi danh sách hoạt động, có thể đọc lại theo status.
- Description tùy chọn giới hạn 4000 ký tự ở service, tên 200/title 250; trim khoảng trắng đầu/cuối. Enum, UUID reference, số nguyên dương, datetime aware, boolean được xác thực.

### Calendar và thời gian

- Tạo lịch thủ công mặc định confirmed sau khi không có conflict hoặc sau duyệt riêng; origin do backend mặc định manual. Có thể tạo proposed. Không nhận origin/owner từ input.
- Overlap dùng `new_start < existing_end AND new_end > existing_start`, chỉ xét confirmed cùng owner, loại event đang sửa. `[10:00,11:00)` và `[11:00,12:00)` không trùng. Event proposed/cancelled không chặn lịch.
- Khi overlap, không ghi event trước; trả CalendarConflictError kèm pending request và snapshot các event trùng. Giữ overlap cần approve; không xóa/dời/ghi đè event cũ.
- Mọi sửa event confirmed và hủy event cần duyệt; is_fixed không bị âm thầm thay đổi. Sửa proposed không overlap có thể lưu trực tiếp.
- List trả sự kiện giao với khoảng thời gian, theo starts_at rồi created_at/id. Day/week dùng timezone truyền vào, tuần bắt đầu thứ Hai; UI 3C phải lấy timezone đã lưu từ Settings. Mặc định Asia/Ho_Chi_Minh.
- `parse_local_datetime` chỉ nhận `YYYY-MM-DD HH:MM`, trả UTC; từ chối ngày sai/thiếu năm, DST giờ không tồn tại hoặc có hai offset, không đoán ngày tự nhiên. Input DTO datetime phải aware; có thể nhận datetime đã có offset rõ qua `as_utc`. Format hiển thị ngày/giờ cùng timezone. Các ngày vượt phạm vi cũng trả ValidationError.

### Chống gửi lặp và cập nhật cũ

- Create yêu cầu request_id không rỗng, tối đa 128 ký tự. ID record là UUID5 của owner + loại entity + request_id; không thêm schema. Cùng request_id/payload trả record hiện có, kể cả khi service/DB restart.
- Cùng request_id nhưng nội dung hiện có đã khác trả DuplicateRequestError; không overwrite hoặc tạo thêm. Sau khi record được chỉnh sửa, retry create cũ cũng có thể bị từ chối. Intent tạo mới phải dùng key mới; giữ key ổn định cho các lần submit/approve của cùng form.
- Mutations kiểm tra expected version/timestamp trong cùng UPDATE. Gửi lặp expected cũ trả StaleWriteError, không thực thi lại. Adapter nên Refresh và thông báo thay vì báo đã lưu lần hai.
- SQLite writer được reserve trước đọc. Tests nhiều coroutine đồng thời chứng minh một record cho duplicate create, một update cho expected cũ và một event khi hai request mới có overlap.

## Pending actions thủ công: backend đã có, UI chưa nối

Đây là pending action cho thao tác thủ công P3, **không phải bảng SQL pending_actions/executor AI P5**. Không có auto-approve.

1. Owner gọi mutation. Backend xác thực, validate và kiểm tra DB; nếu cần duyệt thì raise ConfirmationRequired hoặc CalendarConflictError. DB chưa đổi.
2. `error.request` có token ngẫu nhiên, reason, expires_at, before/after và conflicts. Token được giữ trong ApprovalStore với owner + fingerprint ràng buộc loại thao tác, entity ID, nội dung, trạng thái/version trước và snapshot conflicts.
3. UI 3C cần hiển thị trước/sau và xung đột cho đúng owner, có nút Duyệt/Bỏ qua. Chỉ callback Duyệt được truyền token cùng đúng dữ liệu và expected version vào service. Không tự gửi token trở lại ngay khi nhận lỗi.
4. Service xác thực owner lại, mở transaction và đọc lại dữ liệu/conflicts. Token giả, hết hạn, dùng lại cho payload/owner/entity khác hoặc snapshot conflict thay đổi bị từ chối. Target version đổi có thể trả StaleWriteError trước bước kiểm tra token.
5. Token được tiêu thụ sau commit thành công. Lỗi flush/commit không tiêu thụ token, có thể retry nếu chưa hết hạn và DB vẫn khớp. Replay không thể ghi lại cùng mutation.

Store giữ tối đa 100 pending actions, TTL **5 phút**, loại phiên hết hạn khi cấp phiên mới. Restart/process hoặc service mới làm mất pending approvals; phải xem và duyệt lại. Không khôi phục nút xác nhận cũ thành quyền ghi mới. Nếu chủ động bỏ qua ở UI, không gọi mutation có token; phiên tự hết hạn. Không ghi token/nội dung pending action vào logs.

## Errors

DomainError có `code`, thông báo an toàn: validation_error, not_found, stale_write, duplicate_request, storage_error, confirmation_required, calendar_conflict, approval_invalid. Confirmation/conflict errors có request riêng để owner xem; không dùng toàn bộ request làm log hoặc phản hồi công khai. AuthorizationError hiện có tiếp tục xử lý bằng owner-denied flow của P2.

## Kiểm thử thực tế

Linux, Python **3.12.15**, dependencies giữ nguyên. Baseline trước sửa: **250 passed in 4.68s**. Sau triển khai: **340 passed in 6.02s**, thêm **90 tests**, không gọi mạng/Discord thật.

| Lệnh | Kết quả |
|---|---|
| `.venv/bin/python -m pytest -q` | **340 passed in 6.02s** |
| `.venv/bin/python -m ruff check .` | Pass |
| `.venv/bin/python -m ruff format --check .` | Pass, 80 files already formatted |
| `.venv/bin/python -m compileall -q app alembic tests` | Pass |
| `git diff --check` | Pass |

Pytest chạy ngoài sandbox do hạn chế asyncio/socket nội bộ, dùng SQLite tạm và fixture chặn kết nối ngoài. Chưa chạy PowerShell trên Windows hoặc thao tác Discord thực tế.

### Đối chiếu 3B

- [x] Owner guard trước DB ở 18 service entry points được kiểm thử; query/count/update/progress/conflicts không trả dữ liệu owner khác.
- [x] Create/read/update, archive/cancel, complete/reopen và nullable fields hoạt động; FK/owner references được kiểm tra trước ghi.
- [x] Progress, filters và pagination đúng; không lệch total hoặc trùng mục giữa các trang.
- [x] Datetime validation, UTC/local round-trip, strict date parsing, DST và ngày ngoài phạm vi được xử lý.
- [x] Overlap thật cần duyệt, hai đầu tiếp giáp không trùng; không auto thay đổi event liên kết.
- [x] Stale writes, duplicate create/status và concurrent create/updates bị chặn đúng.
- [x] Pending approvals owner/payload/conflict bound, expiry/restart/replay, lỗi commit và retry an toàn.
- [x] Flush/commit failure rollback, không trả success giả; DB/service restart giữ dữ liệu.
- [x] Toàn bộ tests Phase 1/2/3A vẫn pass; không đổi schema và không triển khai 3C.

## File tạo/sửa

Tạo **17 file**:

- `app/domain/core.py`, `app/domain/errors.py`, `app/domain/time.py`, `app/domain/approvals.py`.
- `app/db/repositories/core_repository.py`, `project_repository.py`, `task_repository.py`, `calendar_repository.py`.
- `app/services/core_service.py`, `project_service.py`, `task_service.py`, `calendar_service.py`.
- `tests/test_core_services.py`, `tests/test_calendar_service.py`, `tests/test_core_repositories.py`, `tests/test_core_validation.py`.
- `docs/PHASE_3B_VALIDATION.md`.

Sửa **6 file**:

- `app/db/session.py`: tùy chọn BEGIN IMMEDIATE cho service transactions mới.
- `tests/conftest.py`: fixture services với SQLite tạm.
- `README.md`, `docs/ROADMAP.md`, `docs/DATABASE.md`, `docs/DISCORD_UI.md`: tình trạng backend 3B, API/giới hạn, giữ UI chưa có CRUD.

Không sửa models/migrations, `.env`, dependencies hoặc Discord source. Không commit/push trong lần bàn giao.

## Cấu hình và phần tiếp theo

Không cần thêm biến môi trường hay chạy migration cho riêng 3B. Nếu máy vẫn ở schema trước 3A, dùng [runbook backup/migration 3A](PHASE_3A_VALIDATION.md#migration-và-khôi-phục) trước khi vận hành backend này; không xóa hoặc reset DB.

**3C còn lại:** giữ service instances trong lifecycle bot; nối panels/forms/list/detail/pagination với DTOs; truyền timezone Settings; UI confirmation có Back/Bỏ qua/hết hạn; giữ request_id/expected snapshot; chỉ báo success sau commit; counts thật; xử lý errors/Refresh; kiểm thử Desktop/Mobile, owner/non-owner, restart và nghiệm thu toàn P3.

**Dừng tại 3B. Chưa bắt đầu 3C hoặc phase tiếp theo.**
