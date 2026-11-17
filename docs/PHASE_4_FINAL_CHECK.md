# Phase 4 — Báo cáo nghiệm thu

## Phase 4 DONE — 2026-11-17

Người dùng xác nhận **“oke tôi đã tét xong rồi”** sau lần thử reminder thật. Chốt P4 theo xác nhận owner, bằng chứng DB/Discord và bộ tự động gần nhất **625 passed in 37.60s** (lint/format/compile đạt). Không chạy lại tests hoặc thay business code trong lượt chốt tài liệu; không bắt đầu P5.

Bằng chứng kiểm chứng trực tiếp:

- DB Windows mới được tạo theo yêu cầu owner, head `0004_reminder_dispatch`, preflight config/integrity/FK/revision/owner/settings đạt exit 0; không đụng DB Linux.
- Bot đăng nhập Discord, sync 4 lệnh và online.
- Owner tự Lưu reminder one-time qua UI, target DM, lịch 23:19:00 VN. API/DB xác nhận sent lúc **23:19:06.744815**, một attempt, không lỗi, chậm khoảng 6,7 giây.
- Kiểm tra read-only sau xác nhận của owner: reminder done, delivery sent, **acknowledged_at 23:19:49.151119 VN**. Không có delivery snooze; theo contract hiện tại, đây là acknowledgment từ nút Đã làm. Không in title hoặc nội dung DM.

Phạm vi nghiệm thu: owner xác nhận kiểm thử xong nhưng không nêu riêng thiết bị/kịch bản. Không suy diễn Desktop/Mobile, daily/weekly, snooze, private fallback, non-owner hoặc restart đã được thử live từng trường hợp; các luồng này có tests mock/SQLite như báo cáo 4B/4C. Giữ checklist để hồi quy khi cần. Giới hạn một process và crash-window best-effort/at-least-once vẫn áp dụng.

Các mục phía dưới lưu lịch sử triển khai và các bước trước nghiệm thu. Mọi ghi chú “chưa DONE/chờ cấu hình/chưa gửi thật” ở đó mô tả mốc trước xác nhận này.

## Lần gửi reminder thật đầu tiên — 2026-11-17

Người dùng tự tạo và Lưu một reminder one-time qua Discord, target DM, mốc **23:19:00 Asia/Ho_Chi_Minh**. Bot đang chạy ghi nhận API success và commit **23:19:06.744815 +07:00**, chậm khoảng **6,7 giây**, một attempt. Kiểm tra read-only: reminder `done`, delivery `sent`, không error_code/finished_reason/retry_at; log `reminder_delivery_sent`, attempt_count=1. Không đọc/in title hoặc nội dung DM.

Đã xác minh tạo/lưu và worker gửi thật qua Discord API/DB. Chưa có xác nhận người dùng đã đọc DM hoặc thử nút snooze/Done/Tắt; chưa nghiệm thu Desktop/Mobile, private fallback và restart thật. Giữ toàn P4 chưa DONE đến khi có đủ bằng chứng; các phát biểu chưa có lần gửi thật bên dưới mô tả mốc kiểm tra trước đó.

## Cập nhật kết nối Discord thật — 2026-11-17

Sau khi người dùng cấu hình lại `.env`, preflight đạt **exit 0**, toàn bộ config/integrity/FK/revision/owner/settings đều OK. Không hiển thị hoặc ghi token vào báo cáo. Kiểm tra không có process bot trước khi chạy, không khởi động bản thứ hai trên cùng SQLite.

Đã chạy `.\.venv\Scripts\python.exe -m app.main`, nhận log thật:

- `2026-11-17 15:59:15 UTC`: `slash_commands_registered`, command_count=4.
- `2026-11-17 15:59:18 UTC`: `bot_online`, Gateway đã kết nối.

Bot được giữ chạy cho người dùng thử `/menu → Reminders → Thêm → Lưu` với mốc sau 2–3 phút. Chưa ghi nhận người dùng nhận DM hoặc kết quả Desktop/Mobile/nút/restart; không đánh dấu toàn P4 DONE từ kết quả login. Không tạo dữ liệu nhắc thử hoặc gửi DM thay owner trong bước này. Các phát biểu cấu hình còn thiếu phía dưới là lịch sử trước lần cập nhật này. Source không thay đổi, không chạy lại bộ tests trong lượt xác minh kết nối.

## Cập nhật khởi tạo DB mới trên Windows

Theo yêu cầu rõ ràng của người dùng sau khi bàn giao cấu hình, đã tạo **database mới** tại `C:\Users\FPT\OneDrive\Desktop\nova-discord-agent\nova.db`. Đường dẫn được xác minh trong workspace; trước tạo không có file hoặc sidecar SQLite. Dùng exclusive-create, không overwrite file có sẵn; không đụng phân vùng/DB Linux. Vì nguồn là DB mới, không có dữ liệu cũ để backup/migrate từ Linux.

Đã chạy migrations qua Database.initialize tới `0004_reminder_dispatch`, khởi tạo đúng config owner và settings với timezone `Asia/Ho_Chi_Minh`. Có một owner và một settings record; projects/tasks/calendar/reminders/deliveries/audit đều rỗng, không seed dữ liệu ví dụ. Kiểm tra integrity, foreign_key_check, PRAGMA foreign_keys và compare_metadata đều đạt. `.env`/`nova.db` bị Git ignore.

- `.\.venv\Scripts\python.exe -m alembic current`: `0004_reminder_dispatch (head)`, exit 0.
- `.\.venv\Scripts\python.exe -m alembic check`: `No new upgrade operations detected.`, exit 0.
- `.\.venv\Scripts\python.exe -m app.preflight`: integrity/FK/revision đạt; exit 2 do `DISCORD_TOKEN` trong `.env` còn thiếu/placeholder. Owner/settings được kiểm tra trực tiếp khi bootstrap; preflight chỉ kiểm tra owner khi toàn bộ config hợp lệ.
- `git diff --check`: pass. Không thay code trong lần tạo DB này, không chạy lại toàn bộ tests; kết quả 625 tests bên dưới là lịch sử lượt kiểm tra trước.

Chưa khởi động bot hoặc gọi Discord; cần điền token mới trực tiếp vào `.env` để nghiệm thu live. Các phát biểu DB chưa tồn tại ở các mục bên dưới mô tả thời điểm kiểm tra trước khi người dùng yêu cầu tạo mới.

## Kết quả hiện tại

Đã kiểm tra lại source 4A/4B/4C và bổ sung nghiệm thu qua hai NovaClient/engine riêng biệt trên cùng SQLite tạm. Bộ cuối: **625 passed in 37.60s**, Python **3.12.3**, Windows; lint/format/compile đạt. Không làm Phase 5.

Các kiểm tra thêm:

- Client thứ nhất bootstrap DB, tạo reminder, worker + Discord transport gửi qua HTTP mock; đóng client/engine.
- Client thứ hai mở cùng DB, đăng ký DynamicItem, nhận nút snooze từ notification cũ, tạo một delivery sau 15 phút và gửi đúng một lần bổ sung. Đây là restart thực của client/service/engine trong test, không chỉ dựng lại một button trên controller cũ.
- Dừng worker khi sender đang chờ: lock được nhả, claim được giữ trong DB; sau lease, một lượt dispatch mới xử lý thành công. Không bỏ claim hoặc đóng DB trước khi worker dừng.
- `app.preflight` kiểm tra cấu hình và DB hiện có bằng SQLite read-only: integrity, FK, revision, owner/config và settings. Không tạo thư mục/DB thay thế, không migrate, không gọi Discord và không in secret/nội dung record.
- Tests preflight bao gồm DB thiếu, DB hỏng, revision lạ, owner mismatch, settings thiếu, FK hỏng, exit code CLI và giữ nguyên SHA-256 của DB hợp lệ.

**Chưa có cấu hình/DB vận hành để chạy live.** Đã tạo `.env` từ `.env.example` nếu chưa có, bằng chế độ tạo độc quyền, không overwrite file có sẵn. File mẫu này bị gitignore, chưa chứa token/owner thật. `nova.db` tại đường dẫn mặc định chưa tồn tại. Không tạo fake owner/data, không migrate DB thật và không gửi Discord thật.

## Lệnh đã chạy

| Lệnh | Kết quả |
|---|---|
| `.\.venv\Scripts\python.exe -m pytest -q` | **625 passed in 37.60s**, exit 0 |
| `.\.venv\Scripts\python.exe -m ruff check .` | All checks passed, exit 0 |
| `.\.venv\Scripts\python.exe -m ruff format --check .` | 122 files already formatted, exit 0 |
| `.\.venv\Scripts\python.exe -m compileall -q app alembic tests` | Pass, exit 0 |
| `.\.venv\Scripts\python.exe -m alembic heads` | `0004_reminder_dispatch (head)` |
| `.\.venv\Scripts\python.exe -m app.preflight` | Exit **2** đúng kỳ vọng: config token thiếu/placeholder, DB cũ chưa có |
| `git diff --check` | Pass, exit 0 |
| `git check-ignore .env` | `.env` bị ignore |

Head và business policies giữ nguyên; chỉ thêm helper kiểm tra vận hành và 8 test cases. Kết quả 617 tests của [báo cáo 4B/4C](PHASE_4BC_VALIDATION.md) là mốc trước kiểm tra cuối này.

## Phần cần cấu hình để chạy thật

1. Điền trực tiếp `.env` bằng editor trên máy chạy bot: `DISCORD_TOKEN`, `DISCORD_OWNER_ID`, `DATABASE_URL` trỏ đúng DB P1–3 đang dùng; guild ID tùy chọn. Không gửi token hoặc DB cá nhân vào chat. Không dùng owner ID/data trong tests làm dữ liệu thật.
2. Nếu bot/DB đang ở máy khác, thực hiện runbook tại máy đó bằng source hiện tại và venv của máy đó; không thay DB cũ bằng file rỗng trên máy này.
3. Dừng bot cũ và kiểm tra đường dẫn. Chạy preflight để xác định config/owner/integrity/FK/revision. Nếu chỉ revision cần nâng cấp, backup rồi migrate theo [runbook 4B/4C](PHASE_4BC_VALIDATION.md#backup-migrate-và-chạy-trên-máy-có-database-thật). Config/owner/integrity/FK lỗi thì giữ DB nguyên trạng và xử lý nguyên nhân trước.
4. Sau migrate/check, chạy lại preflight; phải exit 0 trước khi khởi động bot. Exit 0 chỉ xác minh cấu hình cú pháp/DB, **không** xác minh token với Discord, quyền kênh hoặc nhận thông báo.
5. Chạy bot và thực hiện [checklist live](PHASE_4BC_VALIDATION.md#checklist-live-còn-lại) trên Desktop/Mobile: nhận DM thật, daily/weekly, snooze/bấm lặp, pause/resume/cancel, restart, non-owner và fallback/quiet hours. Ghi nhận kết quả trước khi chốt toàn P4 DONE.

```powershell
# Read-only; không login Discord, không backup/migrate/tạo DB.
.\.venv\Scripts\python.exe -m app.preflight
```

## Files và rollback

Tạo `app/preflight.py`, `tests/test_preflight.py`, `tests/test_reminder_acceptance.py` và báo cáo này; cập nhật trạng thái/checklist README, ROADMAP và báo cáo 4B/4C. `.env` chỉ là mẫu cục bộ bị ignore. Không đổi schema, migration, dependency hoặc logic nhắc việc; không cần rollback DB cho những bổ sung này.

Source và nghiệm thu tự động P4 đã sẵn sàng. **Nghiệm thu vận hành vẫn chờ cấu hình và DB thật; không đánh dấu toàn P4 DONE hoặc bắt đầu P5.**
