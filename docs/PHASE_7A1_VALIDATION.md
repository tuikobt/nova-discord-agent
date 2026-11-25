# Phase 7A.1 — Khung kết nối và chẩn đoán

Ngày triển khai: 2026-11-24–25 (Asia/Ho_Chi_Minh). Phạm vi theo
[kế hoạch P7](PHASE_7_PLAN.md): chỉ checkpoint 7A.1, dừng trước 7A.2.
Phase 7 tổng thể chưa hoàn thành. Chưa nghiệm thu UI mới bằng thao tác của owner.

## Chức năng và giới hạn

- Connection metadata theo owner, allowlist 1–10 repo/page, quyền chỉ đọc,
  version, trạng thái và thời điểm kiểm tra. Token ở config, DB chỉ giữ tên
  credential cố định; `.env` thật không bị chỉnh sửa.
- Thêm/sửa/ngắt có preview đầy đủ và durable approval P5, message/channel
  binding, TTL, kiểm tra stale, chống thực thi trùng. Business row, receipt và
  audit ghi chung transaction. Sửa/ngắt làm mất hiệu lực scope/version cũ,
  xóa context AI trong RAM và giữ lịch sử.
- `/menu` → Cài đặt → Kết nối & chẩn đoán: danh sách riêng có phân trang,
  form tên/phạm vi, kiểm tra, ngắt và nút quay lại.
- Phân biệt Discord readiness với OpenAI đã cấu hình. Nút Thử AI mới gọi API,
  không gửi dữ liệu cá nhân/tools và dùng quota hiện có. Lỗi không có raw body.
- Có protocol/probe result và backend scope gate, **chưa cài bộ đọc/probe HTTP
  GitHub/Notion**. Credential thiếu → missing_credential; có key nhưng chưa có
  adapter → adapter_pending. Không giả trạng thái verified hay dữ liệu nguồn.
- Model không được gọi tool cấu hình/ngắt kết nối. Không worker connector,
  import task, external write, Goals/Notes/Habits/Finance hoặc deploy P7.

## File thay đổi

| Nhóm | File |
|---|---|
| Dữ liệu | app/db/models.py; alembic/versions/0007_connections.py |
| Domain/config/protocol | app/domain/connections.py; app/integrations/{__init__,config,protocol}.py; app/config.py |
| Service/approvals | app/services/{connection_service,core_management,pending_action_service}.py |
| AI boundary | app/agent/{gateway,tool_registry}.py; app/discord_bot/agent_controller.py |
| Discord | app/discord_bot/{connections_controller,dashboard_controller,client}.py; views/dashboard.py; renderers/connections.py |
| Secrets | .env.example; app/{logging_config,main,security,security_check}.py |
| Tests mới | tests/test_connections.py; tests/test_connections_discord.py; tests/test_connection_migration.py |
| Hồi quy schema | tests/test_{database,core_migration,agent_migration,reminder_migration,personal_migration}.py cập nhật expected head/table, không sửa migrations P1–6 |
| Tài liệu | README; docs/{ROADMAP,PHASE_7_PLAN,DATABASE,DISCORD_UI,SECURITY,HUONG_DAN_SU_DUNG,PHASE_7A1_VALIDATION}.md |

Git ở nhánh `feat/phase-6`; giữ nguyên thay đổi kế hoạch đã có từ lần trước.
Không stage/commit/push, không đưa database hoặc backup vào Git.

## Kiểm thử

Baseline trước sửa: **803 passed in 89.24s**. Test mới mock Discord/OpenAI/probe,
SQLite tạm, không gọi provider thật. Các trường hợp gồm:

- Owner/service/modal/callback, UI expiry, không phát tool cấu hình cho model.
- Resource normalization, host giả/HTTP/credential URL/port/subpath không hợp lệ,
  tài nguyên ngoài allowlist, write bị chặn, trùng và giới hạn scope.
- Preview chưa ghi nghiệp vụ; approval bound, restart, idempotency, stale,
  ngắt trong khi probe đang chờ, rollback row/receipt/audit khi ghi thất bại.
- Trạng thái chưa kiểm tra trung thực, typed probe results, timeout/exception
  không lưu raw error; token không nằm trong DTO/preview/prompt hoặc repr config.
- Phép thử AI chỉ chạy khi click và ghi usage/quota, không echo model output.
- Migration idempotency, interruption rollback, dữ liệu cũ nguyên vẹn, backup/
  restore và downgrade refusal cả connection đã ngắt và proposal chưa thực thi.

Lệnh kiểm tra:

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
.venv/Scripts/python.exe -m compileall -q app alembic tests
.venv/Scripts/python.exe -m app.security_check --history --staged
.venv/Scripts/python.exe -m app.preflight
.venv/Scripts/python.exe -m alembic check
git diff --check
```

Kết quả cuối (Windows Python 3.12.3): **863 passed in 98.26s** toàn bộ suite;
**58 passed in 7.24s** cho ba file mới. Thêm hai action schema cũng làm test
parametrized chung tăng hai trường hợp so với baseline 803. Ruff check, format
(182 files), compileall và git diff --check đạt. Security scan history/staged/
working tree: 327 reachable blobs, không có finding; patterns không tuyệt đối.

Preflight sau migration: config/AI cấu hình/integrity/FK/revision/owner/settings
đều OK, không gọi API. Alembic check: `No new upgrade operations detected.`
Bot khởi động lại ngoài sandbox sau khi xác nhận không còn app.main đang chạy:
2026-11-25 16:08:26 UTC đăng ký 4 lệnh, **16:08:29 UTC bot_online** (23:08:29 VN).
Không gọi probe GitHub/Notion/OpenAI thật trong lần nghiệm thu này. Bộ thử AI mới
được kiểm bằng mock; không dùng bằng chứng đó để nhận đã thử provider thật.

## Backup và diễn tập

Snapshot trước triển khai:
`backups/pre-phase7a1-20261124-1640.db`, tạo bằng SQLite backup API, integrity OK.
Đã thử trên bản sao `backups/phase7a1-drill-20261124-170030.db`:
upgrade 0006 → 0007, upgrade lại, Alembic metadata check, downgrade rỗng → 0006,
upgrade lại. **13 bảng cũ, 31 bản ghi, toàn bộ cột và giá trị giữ nguyên**;
integrity và foreign_key_check đạt.

Restore thử sang file riêng
`backups/phase7a1-restored-20261124-170030.db` khớp snapshot cũ. Không ghi đè
database hiện tại để thử restore. Trước nâng DB thật phải dừng bot, tạo backup
mới vì owner có thể đã ghi dữ liệu sau snapshot đầu, rồi so lại tất cả cột/row.

**Nâng DB thật 2026-11-25 16:07:43 UTC:** đã xác nhận bot dừng, tạo backup mới
`backups/pre-phase7a1-live-20261125-160742.db`. Từ snapshot này thử upgrade ở
`backups/phase7a1-live-drill-20261125-160742.db`, restore riêng ở
`backups/phase7a1-live-restored-20261125-160742.db`, rồi mới nâng DB thật.
Revision `0007_connections`; bảng mới rỗng, **13 bảng/31 bản ghi cũ giữ nguyên
tất cả cột và giá trị**, integrity/FK đạt trên DB thật và cả hai bản thử.
Metadata chứng minh (không chứa dữ liệu riêng):
`backups/phase7a1-migration-report-20261125-160742.json`.

## Rollback

Ưu tiên **ngắt connection trong NOVA và giữ schema additive** để giữ lịch sử.
Tasks/Calendar/Reminders/AI tiếp tục dùng độc lập với nguồn ngoài. Ngắt không
tự thu hồi token provider; nếu cần, owner thu hồi trên dịch vụ rồi bỏ key khỏi
cấu hình máy và restart bot.

Chỉ downgrade khi bảng connection rỗng **và** không có pending_actions kết nối:

```powershell
# Dừng bot, backup mới trước mọi downgrade; dùng source 7A.1 để chạy lệnh này.
.venv/Scripts/python.exe -m app.db.backup --output backups/before-rollback-7a1.db
if ($LASTEXITCODE -ne 0) { throw 'Backup failed; stop.' }
.venv/Scripts/python.exe -m alembic downgrade 0006_personal
```

Nếu có lịch sử, migration từ chối; không delete/stamp/drop để ép. Muốn quay hẳn
về P6: dừng bot, backup DB hiện tại, phục hồi snapshot P6 sang **đường dẫn mới**
qua SQLite backup API, kiểm tra integrity/FK/owner/revision và so với snapshot,
chọn source P6 rồi đổi DATABASE_URL trực tiếp trên máy. Chạy preflight bằng
source P6 trước khi khởi động đúng một process. Source 7A.1 sẽ tự nâng head lúc
startup; không dùng nó để giữ một DB ở revision P6.

Phục hồi snapshot không bao gồm dữ liệu mới hơn thời điểm backup. Giữ nguyên
DB hiện tại, snapshot và các file WAL/SHM liên quan để đối chiếu, không chép đè
file SQLite khi bot còn chạy và không bật hai bot Windows/Linux cùng token.

## Checklist owner trên Discord

1. Mở panel mới từ `/menu` → Cài đặt → Kết nối & chẩn đoán.
2. Thêm phạm vi GitHub/Notion bạn chọn; thử Hủy trước, xác nhận không có bản ghi.
3. Tạo lại và Duyệt; làm mới, mở chi tiết và kiểm tra phạm vi đã lưu.
4. Kiểm tra dịch vụ: bản này báo thiếu key/chưa có adapter, chưa đọc nguồn thật.
5. Sửa phạm vi, xem và Duyệt; ngắt cũng cần Duyệt. Không dán token vào Discord.
6. Nếu cần kiểm tra OpenAI, bấm Thử AI (tính quota); thử Tasks/Reminders hiện có.

Nghiệm thu provider thật, tools đọc có nguồn và nguồn vừa bị thu hồi thuộc
7A.2–7A.4. Dừng tại checkpoint này; không tự chuyển sang các phần đó.
