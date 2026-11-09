# NOVA AI — PHASE 3 HANDOFF

**Giai đoạn:** P3 — Core Management (Tasks · Projects · Calendar)  
**Trạng thái:** Chưa triển khai / chỉ hoàn thành sau nghiệm thu thực tế  
**Căn cứ:** `AGENTS.md`, `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/DATABASE.md`, `docs/DISCORD_UI.md`, `docs/ROADMAP.md`, `docs/SECURITY.md` của NOVA Phase 0.  
**Đầu vào bắt buộc:** Source code Phase 1–2 đang chạy trên máy người dùng; tài liệu này **không chứa source code mới nhất**, vì vậy phải kiểm tra repository thực tế trước khi sửa.

## 1. Mục tiêu sản phẩm P3

Biến các màn hình **✅ Tasks**, **🚀 Projects**, **📅 Calendar** từ các panel giới thiệu thành các tính năng thật. Owner có thể **tạo → xem → sửa → cập nhật trạng thái → lưu dữ liệu** bằng Discord UI; dữ liệu đúng sau restart. Dashboard hiển thị số liệu truy vấn từ database. Không cần nhớ các slash commands mới: ưu tiên `/menu` + nút bấm, menu chọn và modal.

**Không nằm trong P3:** AI Chat/Agent, tự động lập lịch bằng AI, Reminder Scheduler/gửi thông báo, Goals/Finance/Habits/Notes, web dashboard, Gmail/GitHub/Google Calendar, VPS. Các module này vẫn để “Sắp ra mắt”.

## 2. Phạm vi từng chức năng

### 2.1 Project Management
- Tạo project với `name` bắt buộc, `description` tùy chọn, `deadline_at` tùy chọn.
- Danh sách có phân trang, chi tiết project, sửa tên/mô tả/deadline/trạng thái.
- `status`: `active | paused | completed | archived`.
- Project có danh sách task liên kết, đếm task và tiến độ.
- Tiến độ = `done_tasks / all_non_cancelled_tasks * 100`, nếu không có task: `0% — Chưa có nhiệm vụ`; ghi rõ đây là *tỷ lệ số lượng task*.
- Thao tác xóa project có task liên quan: **không cascade xóa task âm thầm**. Trong P3 ưu tiên `archive`; nếu triển khai xóa thì phải có xác nhận rõ + chiến lược xử lý task liên kết.

### 2.2 Task Management
- Tạo task: `title` bắt buộc, `description` tùy chọn, `priority` tùy chọn, `due_at` tùy chọn, `project_id` tùy chọn.
- Danh sách theo trạng thái `todo | doing | done | cancelled`; lọc theo project, ưu tiên, deadline; phân trang.
- Sửa task, cập nhật trạng thái, đánh dấu hoàn thành, mở lại task; quản lý `completed_at` nhất quán.
- Priority: `low | medium | high | critical` (mặc định `medium`).
- `estimated_minutes` nếu có phải > 0.
- Nếu liên kết project, project đó phải thuộc cùng owner; ID không tồn tại/không hợp lệ phải trả lỗi rõ.
- Không xóa tác vụ nhầm do nhấn hai lần; thao tác hủy/xóa phải xác nhận. Có thể dùng `cancelled` thay vì hard-delete nếu phù hợp tài liệu.

### 2.3 Calendar Management
- Tạo event: `title`, `starts_at`, `ends_at`, `is_fixed`; trạng thái `proposed | confirmed | cancelled`; nguồn `manual`.
- Xem theo ngày/tuần, hiển thị rõ múi giờ Việt Nam; sửa và hủy event.
- `ends_at > starts_at`; không chấp nhận định dạng ngày không rõ (ví dụ `10/11` thiếu năm hoặc không biết ngày/tháng) mà tự đoán.
- Phân biệt `Task` (việc cần làm), `CalendarEvent` (khung giờ), `Reminder` (thông báo); **P3 không gửi reminder**.
- `task_id` tùy chọn nhưng nếu có phải thuộc cùng owner.
- Phát hiện trùng giờ giữa các sự kiện `confirmed` của cùng owner bằng điều kiện `new_start < existing_end AND new_end > existing_start`, loại trừ event đang sửa và các event `cancelled`/chỉ `proposed` theo quy tắc sản phẩm.
- Nếu trùng, **hiển thị danh sách sự kiện trùng và yêu cầu xác nhận riêng** trước khi vẫn lưu; không tự xóa, dời hay ghi đè.
- Các mốc thời gian người dùng nhập được hiểu theo `Asia/Ho_Chi_Minh`, lưu theo UTC, hiển thị lại theo `Asia/Ho_Chi_Minh`. Với SQLite, xác minh round-trip timezone do backend không có kiểu timezone gốc.

### 2.4 Dashboard và UX
- `/menu` vẫn chỉ có **một dashboard chung**, persistent view của P2 vẫn hoạt động sau restart.
- Khi owner chọn module, mở panel riêng tư hoặc cập nhật riêng phù hợp với thiết kế P2; không thay thế dashboard chung và không spam channel.
- Task/Project/Calendar có nút `➕ Thêm`, `📋 Danh sách`, `🔎 Chi tiết`, `✏️ Sửa`, `✅ Hoàn thành` (task), `⬅️ Quay lại`, `🔄 Làm mới`; chỉ hiển thị những thao tác có backend thật.
- Sử dụng modal để nhập văn bản; nếu số trường vượt giới hạn phù hợp của Discord, chia thành từng bước nhỏ hoặc dùng select.
- Mọi UI callback, modal submit, lệnh và service đều phải chặn non-owner. Phản hồi lỗi tiếng Việt, dễ sửa.
- Lúc DB rỗng hiển thị empty state và CTA tạo bản ghi, **không dùng dữ liệu demo**.

## 3. Mô hình dữ liệu cần khớp với `docs/DATABASE.md`

- `projects`: `id`, `owner_id`, `name`, `description`, `status`, `deadline_at`, `created_at`, `updated_at`.
- `tasks`: `id`, `owner_id`, `project_id?`, `title`, `description?`, `status`, `priority`, `estimated_minutes?`, `due_at?`, `completed_at?`, `version`, `created_at`, `updated_at`.
- `calendar_events`: `id`, `owner_id`, `task_id?`, `title`, `starts_at`, `ends_at`, `status`, `is_fixed`, `origin`, `version`, `created_at`, `updated_at`.
- Discord snowflake IDs lưu dạng chuỗi; query/updates bắt buộc giới hạn bằng `owner_id`.
- FK + indexes + check constraints; bật `PRAGMA foreign_keys=ON` cho SQLite mỗi connection.
- Dùng migration **Alembic** thay vì xóa database cũ hoặc `drop_all()`. **Sao lưu DB thực tế trước migration**, kiểm tra cả data trong `users`, `user_settings` và dashboard message IDs.
- Nếu repository hiện có migration theo cách khác, kiểm tra trước khi thay thế; không tự tạo baseline sai làm hỏng dữ liệu.
- Đảm bảo commit/rollback transactional; cân nhắc `version` cho cập nhật bị stale/double click.

## 4. Kiến trúc đề xuất

```text
Discord UI (P2: embeds/views/modals)
    ↓ validated DTO/input (không SQL trong UI)
Services (Projects/Tasks/Calendar + ownership + business rules)
    ↓
Repositories (SQLAlchemy AsyncSession, queries scoped by owner)
    ↓
SQLite + migrations
```

Tận dụng cấu trúc source code hiện tại. **Không tạo song song hai implementation** hoặc refactor Foundation không cần thiết. Dùng async I/O nhất quán; response/defer đúng hạn để không có “This interaction failed”. Các panel có state ngắn hạn phù hợp vòng đời Discord, và Dashboard lâu dài của P2 vẫn persistent.

## 5. Triển khai theo checkpoint, không làm ồ ạt

### P3-A — Database + migration (DỪNG LẠI SAU KHI XONG)
1. Đọc docs/source + `git status`, xác nhận P2 đã nghiệm thu.
2. Xác định SQLite DB từ config, giải thích cách backup; **không in secret từ `.env`**.
3. Bổ sung ORM `Project`, `Task`, `CalendarEvent` + relationships, validation cơ bản.
4. Bổ sung Alembic revision tương thích schema P1/P2 hiện có; không xóa dữ liệu.
5. Test migration từ DB mới và từ bản copy DB Phase 2; test FK & owner links.
6. Báo cáo file đã sửa, lệnh đã chạy, kết quả tests, lệnh rollback/restore.

### P3-B — Services + tests (DỪNG LẠI SAU KHI XONG)
1. Repositories owner-scoped; CRUD Projects, Tasks, Calendar.
2. Service validation: tên rỗng, status/priority sai, `estimated_minutes<=0`, foreign owner reference, datetime không hợp lệ, end<=start, overlap.
3. API/service trả kết quả/exception thống nhất để Discord UI bắt lỗi.
4. Tests CRUD, archive/reopen, progress, pagination, timezone roundtrip, overlap `[10:00,11:00)` vs `[11:00,12:00)` không trùng, overlap thật có cảnh báo, double click/stale update.
5. Đảm bảo không tạo scheduler/AI; kiểm tra regression P1/P2.

### P3-C — Discord UI + nghiệm thu (DỪNG LẠI SAU KHI XONG)
1. Kết nối giao diện P2 với services Tasks/Projects/Calendar; modal/select/buttons.
2. Confirmation UI cho hủy/xóa và tạo event chồng lịch; thông báo thành công **chỉ sau commit**.
3. Render dashboard counts thật; empty-state, paging, refresh, back.
4. Kiểm thử trên Discord Desktop + Mobile, restart bot, owner/non-owner.
5. Chạy test/lint, cập nhật README, `docs/ROADMAP.md` sau khi nghiệm thu; không làm P4.

## 6. Smoke test thủ công qua Discord

1. `/menu` → `✅ Tasks` → `➕ Thêm` → tên `Học Docker` → lưu → xem lại task; sửa priority; đánh dấu hoàn thành; refresh dashboard và kiểm tra số liệu.
2. `🚀 Projects` → tạo `HRM Backend` → liên kết hai task, hoàn thành một task → kiểm tra tiến độ `50%` nếu cả hai chưa hủy.
3. `📅 Calendar` → tạo `Học Python` từ `2026-10-25 20:00` đến `21:00` theo giờ Việt Nam → xem lại đúng ngày/giờ.
4. Tạo lịch `Đi họp` từ `20:30` đến `21:30` cùng ngày → nhận cảnh báo trùng → chọn Hủy → DB không thêm; tạo lại và xác nhận giữ trùng → DB thêm đúng một event.
5. Thử tạo event `21:00`–`22:00` khi event trước kết thúc `21:00` → không cảnh báo trùng do hai đầu tiếp giáp.
6. Restart bot → mở Dashboard **cũ**, nút vẫn hoạt động; tasks/projects/events còn nguyên.
7. Dùng non-owner trong một kênh mà người đó có quyền truy cập để test slash/callback → từ chối, không rò rỉ dữ liệu.
8. Bấm nút lưu hai lần, nhập ngày sai, nhập tên rỗng, chọn task/project đã bị thay đổi → UI không lỗi và không tạo duplicate.
9. `/ping`, `/menu`, Help, Settings của P1/P2 vẫn chạy đúng.

## 7. Tiêu chí nghiệm thu P3

- [ ] Task/Project/Calendar CRUD hoạt động qua UI.
- [ ] Sửa/lưu/hoàn thành/khôi phục status đúng.
- [ ] Dữ liệu tồn tại sau restart.
- [ ] Owner-only ở mọi endpoint/callback và truy vấn DB.
- [ ] Không liên kết chéo owner, FK bật.
- [ ] Overlap được cảnh báo và chỉ tạo trùng khi owner xác nhận.
- [ ] Thời gian local → UTC → local nhất quán.
- [ ] Dashboard counts/progress đọc dữ liệu thật; không có fake data.
- [ ] Dashboard P2 vẫn persistent và không bị nhân đôi.
- [ ] Tests chạy pass, đã có phương án restore DB.
- [ ] Docs và roadmap đúng tình trạng; chưa tự làm P4/P5.

## 8. Các lệnh tại thư mục dự án

**Linux/macOS/WSL**:
```bash
git status
.venv/bin/python -m pytest -q
.venv/bin/python -m app.main
```

**Windows PowerShell**:
```powershell
git status
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m app.main
```

Đây là ví dụ nếu Phase 1 đã có `.venv` và entry point `app.main`. Đối chiếu README của source code thực tế. Không chạy hai phiên bot cùng token đồng thời. Khi tests/migration đang xử lý DB file, dừng bot đang sử dụng DB nếu cần.

## 9. Prompt giao Codex — bắt đầu **P3-A**

> Hãy đọc `AGENTS.md`, toàn bộ `docs/` có liên quan và source code NOVA Phase 1–2. Phase 2 đã được tôi nghiệm thu trên Discord. Tôi muốn bắt đầu Phase 3: Core Management gồm Projects, Tasks, Calendar. Đọc `docs/PHASE_3_HANDOFF.md` và làm **chỉ checkpoint P3-A: Database + migration**. Trước khi sửa code, kiểm tra `git status`, architecture, ORM/database hiện có và đề xuất phương án migration **không làm mất dữ liệu Phase 1–2**; nêu rõ cách backup DB. Triển khai các models, constraints, foreign keys, migration Alembic tương thích repository hiện tại và tests cho migration, bảo toàn owner/settings/dashboard IDs. Không đụng AI, reminders, hay UI CRUD ở giai đoạn này. Chạy tests khả dụng, báo cáo kết quả thực, file sửa, hướng dẫn chạy migration/restore. **Dừng sau P3-A; không tự sang P3-B.**

Khi P3-A đạt, prompt tiếp theo:

> Tiếp tục theo `docs/PHASE_3_HANDOFF.md`, thực hiện **chỉ P3-B: repositories + services + unit tests** cho Projects, Tasks, Calendar. Giữ nguyên P1/P2 và DB migration đã nghiệm thu; tất cả query owner-scoped, timezone chuẩn, conflict check rõ. Chạy tests, dừng ở cuối P3-B.

Khi P3-B đạt, prompt tiếp theo:

> Tiếp tục theo `docs/PHASE_3_HANDOFF.md`, thực hiện **chỉ P3-C: Discord UI integration + acceptance**. Kết nối Dashboard P2 với 3 modules thật, modals/buttons/pagination, confirm actions nhạy cảm, cập nhật counts. Bảo đảm persistent dashboard sau restart, user guard đầy đủ. Chạy automated tests, hướng dẫn smoke tests thực tế; chỉ đánh dấu Phase 3 DONE sau khi tôi xác nhận đã thử trên Discord. Không làm P4.

## 10. Sau P3

Nếu P3 nghiệm thu xong, tạo Git commit kiểm tra sạch secrets và chuyển sang **P4 — Reminder Engine**. Trong P3 không có thông báo đẩy tự động, AI không tự lập lịch và modules nâng cao vẫn chưa kích hoạt.
