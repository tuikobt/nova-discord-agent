# Phase 6 — Memory, Planner và báo cáo chủ động

Ngày kiểm tra: 2026-11-24. Phạm vi: Phase 6; không bắt đầu Phase 7.

**Phase 6 DONE — owner xác nhận hoàn thành ngày 2026-11-24**, qua yêu cầu
“update cho tôi phase 6 đã xong”. Kết quả tự động cuối cùng đã ghi nhận:
**803 passed in 70.85s**, lint/format/compile đạt. Phiên cập nhật trạng thái này
chỉ sửa tài liệu; không chạy lại tests, gọi API hoặc thay đổi database.

Giao diện tiếp tục được tối ưu theo phản hồi người dùng:
[hướng dẫn sử dụng hiện tại](HUONG_DAN_SU_DUNG.md) và [báo cáo UX](PHASE_6_UX.md).
Các tên màn hình tiếng Anh dưới đây mô tả bản triển khai ban đầu.

## Trạng thái và bằng chứng

- Nhánh triển khai `feat/phase-6`, nền `80b368f` (Phase 5 đã merge).
- Baseline đã chạy trước thay đổi: **719 tests pass**.
- Bộ đầy đủ sau triển khai: **780 passed in 90.22s**. Discord/OpenAI được mock;
  tests chặn kết nối mạng. Không suy ra nghiệm thu Discord thật từ các mocks này.
- Tests backup/upgrade/restore từ P5 có dữ liệu, rollback DDL bị gián đoạn,
  và downgrade từ chối xóa lịch sử P6 đều đạt.
- Sau bản đầu 780 tests và tối ưu UX 790 tests, đã sửa lỗi kết nối AI, đạt
  **803 tests pass** và xác minh OpenAI gọi `get_today_overview` thật. Chi tiết:
  [sửa lỗi DM](DM_CONNECTION_FIX_2026-11-24.md).
- Owner xác nhận tổng thể P6 hoàn thành; README/ROADMAP cập nhật DONE. Owner
  không liệt kê riêng từng phép thử live. Các biến thể không có bằng chứng live
  vẫn được ghi là kiểm thử tự động, không suy diễn từ xác nhận tổng thể.

### Database vận hành và khởi động

- Đã xác minh không còn tiến trình Python trước backup/migration. Không khởi
  động hai bot cùng lúc.
- Backup riêng tư: `backups/pre-phase6-stopped-20261124.db`, integrity OK. Giữ
  cả backup cũ `pre-phase6-20261120.db`; không ghi đè snapshot.
- Diễn tập trên `backups/phase6-migration-drill-20261124.db`: upgrade, upgrade
  lặp, downgrade về 0005 rồi upgrade lại. Restore sang file riêng
  `backups/phase6-restore-drill-20261124.db`. Tất cả cột và bản ghi cũ khớp
  snapshot, integrity/FK đạt, không thay database vận hành trong diễn tập.
- Sau bộ 780 tests, nâng DB vận hành lên `0006_personal`, đối chiếu lại mọi cột
  và bản ghi P1–5 khớp backup. Ba bảng P6 rỗng, không policy nào được bật ngầm.
  `app.preflight` exit 0: config/AI/integrity/FK/revision/owner/settings đều OK.
- `python -m app.main` đã sync 4 slash commands và có `bot_online` lúc
  **2026-11-24 20:53:24 Việt Nam**. Đây là kiểm tra kết nối, chưa phải owner
  nghiệm thu Memory/Planner/nhận report thật. Không gọi OpenAI thật để thay thế
  bộ kiểm thử mock và không gửi báo cáo thử khi owner chưa bật.
- `ruff check`, `ruff format --check` (137 Python files), `compileall`,
  `git diff --check` đạt. Security check working tree/index/local history:
  **255 reachable blobs, findings=[]**; mẫu dò không bảo đảm phát hiện mọi secret.
  Không stage, commit hoặc push thay user. `.env`/DB/backups vẫn bị Git ignore.

## Chức năng

### Memory

`/menu` → Các module khác → Memory: xem, tìm kiếm, phân trang, thêm, sửa, bật/tắt
“dùng cho AI”, xóa; có nguồn và trạng thái owner xác nhận. Mỗi thay đổi có preview,
TTL 15 phút, binding owner/message/channel và kiểm tra version trước khi commit.

AI chỉ được gợi ý tối đa một memory trong mỗi lượt khi owner nói rõ thông tin
sở thích/thói quen/hồ sơ. Nội dung phải trích từ lời owner; nguồn DM do backend
gắn, không lấy từ JSON của model. Gợi ý dùng pending key riêng và không cản task
chính. Chỉ sau Duyệt mới thành MemoryEntry. Token, private key và các nhóm thông
tin nhạy cảm/suy đoán có bộ lọc backend; bộ lọc từ khóa không phải phân loại ngữ
nghĩa đầy đủ, owner vẫn phải đọc preview.

Context chỉ lấy tối đa 5 memory đã duyệt, chưa xóa, bật dùng cho AI và liên quan
từ khóa; planner có thể lấy sở thích/thói quen. Memory là user data, không đưa
vào system instructions. Sửa/tắt/xóa memory xóa context RAM và chặn kết quả AI
đang xử lý từ context cũ. Memory đã duyệt không có ngày tự hết hạn.

Xóa làm rỗng nội dung/source/last_used_at, giữ tombstone ID/version và audit
metadata; xóa các bản sao trong pending actions liên quan. Không tự xóa tin
Discord, backup cũ hoặc bảo đảm ghi đè byte đã xóa trên ổ đĩa. Owner cần xóa tin
Discord/backup riêng nếu cần loại bỏ các bản sao đó.

### Planner

`Reports & Planner` → `Giờ làm & Memory AI`: chọn ngày làm rồi nhập giờ bắt đầu,
kết thúc và thời gian nghỉ. Ban đầu chưa cấu hình, không tự giả định giờ làm.
Khoảng nghỉ mặc định 10 phút, có thể chọn 0–120 phút. Có thể tắt AI gợi ý memory.

`Lập kế hoạch ngày/tuần`: chọn ngày ISO và 1 hoặc 7 ngày. Planner xét tối đa 100
task todo/doing chưa có block confirmed trong tương lai; ưu tiên deadline rồi
priority. Chỉ dùng estimated_minutes đã có; việc thiếu thời lượng được liệt kê
để bổ sung trong Tasks. Tối đa 10 task mỗi đề xuất, không tự chia nhỏ task.

AI có thể chọn một ưu tiên mềm sáng/chiều/tối từ confirmed memory. Backend giữ
quyền quyết định thời gian và kiểm tra giờ làm, deadline, lịch confirmed, khoảng
nghỉ. Hết quota/lỗi API dùng kế hoạch theo quy tắc. Task quá hạn vẫn có thể xếp,
không sửa deadline. Block không đủ slot được giải thích.

Các block vẫn CHƯA LƯU tới khi owner Duyệt. Lúc duyệt đọc lại task/version,
memory/version, settings và toàn bộ lịch bận; stale/conflict/giờ đã qua bị chặn.
Commit tất cả block, pending receipt và audit trong một transaction. Event mới
có task_id, origin=agent, status=confirmed. Không dời các event/reminder cũ.

### Reports và automation

Reports có bản xem thủ công, lịch sử 5 lần/trang, trạng thái gửi và lỗi. Số task
chưa xong/quá hạn là snapshot hiện tại; số tạo/hoàn thành và lịch confirmed tính
trong kỳ theo timezone. Không suy ra giờ làm hay năng suất từ dữ liệu thiếu.
Weekly review tổng kết tuần hiện tại và gợi ý tuần kế tiếp.

Ba lịch độc lập, **mặc định TẮT**:

| Loại | Giờ mặc định theo timezone Settings |
|---|---|
| Bản tin sáng | 07:00 mỗi ngày |
| Tổng kết ngày | 21:30 mỗi ngày |
| Tổng kết tuần | Chủ nhật 20:00 |

Đổi giờ/ngày, bật/tắt và vị trí gửi đều cần Duyệt. DM hoặc kênh văn bản riêng
trong server owner sở hữu; private ACL kiểm tra khi cấu hình và trước mỗi lần
gửi. Fallback chỉ khi owner chọn riêng và DM bị Forbidden. Tắt nhận DM không
được coi là đồng ý chuyển nội dung sang kênh. Không có cảnh báo bypass quiet hours.

Worker riêng với reminder, poll 15 giây, durable claim lease 2 phút, tối đa 3
attempts, retry 1/5 phút, catch-up tối đa 2 giờ. Quiet hours trì hoãn; quá cửa sổ
thì bỏ qua. Đổi timezone/policy khiến run cũ không còn hợp lệ. Bật/đổi giờ sau
mốc đã qua không tự gửi bù mốc đó. Unique `(owner, kind, local period)` chống
gửi lại kỳ đã xử lý; thay giờ trong cùng kỳ không tạo thêm bản tin đã gửi.
Một process SQLite; crash sau Discord send trước commit có thể gây tin trùng,
không cam kết exactly-once.

Nút trên bản tin khôi phục sau restart, kiểm tra owner/message/channel và mở
panel riêng. Kế hoạch được tính lại trước khi tạo đề xuất; bản tin không tự ghi
lịch. Report content hết hạn sau 30 ngày; giữ khóa và metadata để chống gửi lặp.
Nội dung tin Discord không tự hết hạn theo database retention.

Background AI dùng cùng quota ngày UTC với DM và thêm trần 20% requests/tokens
trong quota đó. Không có key/model mới cần cấu hình; giữ Responses client/model
P5, store=False. Các requests chưa xác định usage vẫn giữ reservation.

## Schema và file thay đổi

- `alembic/versions/0006_personal.py`: ba bảng mới memory_entries,
  automation_policies, automation_runs; thêm agent_usage.purpose mặc định dm.
  Không sửa migrations P1–5, không rebuild/xóa các bảng cũ.
- `app/db/models.py`, `app/domain/personal.py`: persistence và validation.
- `app/services/{personal,planner,report,automation}_service.py`: nghiệp vụ P6;
  CoreServices và PendingActionService tích hợp durable approval.
- `app/agent/{orchestrator,gateway,privacy,tool_registry,usage,personal_ai}.py`:
  context, sidecar memory, tool validation, budget, AI preference chỉ đọc.
- `app/discord_bot/{personal_controller,report_sender,agent_controller,client,
  dashboard_controller}.py`, views personal/agent/dashboard, domain/modules:
  giao diện và owner guards, persistent buttons, lifecycle worker.
- `app/scheduler/automation.py`: polling/lifecycle riêng.
- `tests/test_{personal,automation,personal_discord,personal_migration}.py`:
  nghiệp vụ, lỗi/rollback, owner/expiry, mock Discord/OpenAI. Các tests migration
  cũ cập nhật head/tập bảng, giữ các assertions bảo toàn dữ liệu cũ.

Schema P6 chốt tên loại là `kind` thay tên khái niệm `type` trong thiết kế ban
đầu. Không dùng điểm confidence AI để xác nhận sự thật: `confirmed_by_owner`
là điều kiện bắt buộc. Candidates nằm trong pending_actions, bảng memory chỉ
nhận nội dung đã duyệt. AutomationPolicy lưu versioned JSON thay vì kích hoạt
ngầm các cột giờ briefing P1. Giờ làm được đồng bộ vào cột UserSettings cũ sau
duyệt; settings briefing/report đọc policy P6 làm nguồn chính.

## Lệnh kiểm tra

```powershell
.\.venv\Scripts\python.exe -m ruff check app tests alembic
.\.venv\Scripts\python.exe -m ruff format --check app tests alembic
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q app alembic
.\.venv\Scripts\python.exe -m app.security_check
.\.venv\Scripts\python.exe -m app.preflight
```

Quét đầy đủ Git đã chạy thêm `python -m app.security_check --history --staged`.

## Rollback

1. Trong Reports, tắt cả ba automation qua preview/Duyệt; có thể tắt dùng memory
   cho AI từng mục. Dừng bot. Tạo backup mới trước mọi thao tác phục hồi.
2. Ưu tiên giữ schema và dữ liệu additive; P1–5 tiếp tục dùng được. Không chỉ đổi
   code về commit P5 rồi chạy preflight: code P5 coi head P6 là revision lạ.
3. Chỉ `alembic downgrade 0005_agent` khi cả ba bảng P6 rỗng và chưa có usage
   background. Migration tự từ chối khi có lịch sử, kể cả policy đang tắt hoặc
   memory tombstone. Không xóa dữ liệu để ép downgrade.
4. Restore backup P5 vào **file mới**, kiểm tra integrity/FK, revision, owner và
   đối chiếu dữ liệu trước khi đổi DATABASE_URL/code. Không ghi đè DB hiện tại.
   Snapshot cũ không có ghi sau backup; cần bảo toàn/export chênh lệch hoặc owner
   duyệt mất phần chênh lệch trước khi thay thế.
5. Không đưa backup, .env, nội dung riêng tư vào Git. Không dùng stamp/reset để
   bỏ qua kiểm tra schema.

## Checklist Discord cho owner

1. `/menu` → Memory: thêm một sở thích không nhạy cảm; trước Duyệt chưa xuất hiện
   trong danh sách. Duyệt, xem nguồn, sửa, tắt/bật dùng AI, xóa.
2. Reports → Giờ làm: chọn ngày làm, nhập giờ và Duyệt. Trong Tasks bổ sung thời
   lượng cho một việc, lập kế hoạch ngày. Kiểm tra giờ local và task liên kết;
   Hủy không tạo lịch, Duyệt mới có event trong Calendar.
3. Xem ba bản báo cáo thủ công. Khi chưa có dữ liệu phải hiện đúng số 0/chưa ghi
   nhận. Kiểm tra task/lịch thật có trong báo cáo, không có số liệu demo.
4. Cấu hình bản tin sáng, chọn giờ sắp tới **ngoài quiet
   hours**, chọn DM và Duyệt Bật. Chờ nhận bản tin; nút mở panel riêng. Tắt lại
   sau thử nếu chưa muốn chạy hàng ngày. Có thể thử daily/weekly tương tự.
5. Kiểm tra trên Desktop/Mobile; restart rồi thử nút báo cáo/đề xuất còn TTL.
   Tài khoản khác phải bị chặn. Kênh public phải bị từ chối.

Owner đã yêu cầu chốt P6 DONE ngày 2026-11-24. Checklist trên được giữ để dùng
kiểm tra lại; không có xác nhận chi tiết riêng cho từng bước/thiết bị.
