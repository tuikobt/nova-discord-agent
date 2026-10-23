# Phase 1 — Báo cáo triển khai và nghiệm thu

Đây là báo cáo lịch sử tại thời điểm chốt Phase 1. Trạng thái hiện tại xem [ROADMAP](ROADMAP.md) và [báo cáo Phase 2](PHASE_2_VALIDATION.md).

Ngày: **2026-10-23**, timezone hiển thị `Asia/Ho_Chi_Minh`.

**Phase 1 — DONE.** Người dùng xác nhận nghiệm thu bằng thông báo “Phase 1 DONE” ngày **2026-10-23**, sau checklist kiểm tra Discord thực tế. Kết quả kiểm thử tự động từ phiên triển khai là **65 tests pass**, lint/format pass. `docs/ROADMAP.md` đã cập nhật P1 DONE; P2 chưa bắt đầu.

Xác nhận live do người dùng cung cấp; Codex không tự đăng nhập Discord để kiểm chứng lại. Lần cập nhật nghiệm thu này chỉ sửa tài liệu, không đổi source hoặc chạy lại bộ tests.

## Phạm vi đã làm

- Python >=3.12, runtime dependencies pin trong `requirements.txt`; pytest và Ruff trong `requirements-dev.txt`.
- `discord.Client`, Gateway connection/reconnect, setup hook đăng ký `/ping`, `/menu`, event handling và cleanup.
- Owner allowlist từ config áp dụng ở command tree, cả hai callbacks của slash commands, DM handler và service bootstrap. Record trong DB không tự cấp quyền.
- `/menu` là legacy Embed shell riêng tư với đúng 11 module được yêu cầu, tất cả “Sắp ra mắt”, không có số liệu demo.
- `.env` qua python-dotenv, validate token/ID/SQLite URL/timezone/log level, lỗi cấu hình an toàn.
- JSON logs chỉ gồm event/metadata, che token, không in exception payload/raw DM/SQL parameters.
- Async SQLAlchemy + aiosqlite, Alembic migration foundation, foreign keys, transaction cho DDL/DML, owner/settings bootstrap có rollback.
- `users`, `user_settings`, `audit_logs` skeleton theo P1 trong DATABASE; UTC-aware application timestamps.
- Runbook Windows PowerShell, hướng dẫn setup Discord, smoke test và xử lý lỗi trong README.

Không tích hợp OpenAI, không xây web frontend, không có task/project/calendar CRUD, scheduler/reminder engine, buttons/select/modal/persistent dashboard hoặc UI sửa settings. Chỉ có hai slash commands P1.

## Quyết định trong phạm vi Foundation

- Áp dụng phân phase của ROADMAP: pinned dashboard và View tương tác để P2. Embed P1 trả ephemeral để kiểm soát riêng tư; chưa lưu dashboard message/channel IDs.
- Các giờ briefing/review/workday trong settings chưa được owner chọn để `NULL`; không dùng giờ ví dụ trong thiết kế như preferences đã xác nhận. Không có automation hoạt động ở P1.
- `TIMEZONE` dùng khởi tạo owner mới; restart không ghi đè settings/locale/timezone đã lưu. Mọi kiểm tra quyền vẫn dùng `DISCORD_OWNER_ID` hiện tại.
- Thêm biến tùy chọn `DISCORD_GUILD_ID` để sync server khi dev, `LOG_LEVEL` cho vận hành; `.env.example` và README đã đồng bộ. Không có key AI.
- SQLite URL tương đối được neo vào thư mục project. Memory DB/URI query bị từ chối cho runtime để bảo đảm dùng file bền vững.
- Alembic được dùng ngay cho migration foundation theo Work package P1 và DATABASE. Không dùng `create_all` để bỏ qua versioning.

## Kết quả kiểm thử

Kết quả từ phiên triển khai: Linux, **CPython 3.12.15**, venv riêng. Các bài kiểm thử tự động không sử dụng token thật, không gọi Discord/OpenAI API. Các bài async SQLite cần chạy ngoài sandbox vì sandbox hiện tại chặn socket nội bộ mà asyncio dùng để đánh thức event loop; fixture vẫn chặn network connections.

| Lệnh đã chạy | Kết quả |
|---|---|
| `.venv/bin/python -m pytest -q` | **65 passed in 1.98s**, exit code 0 |
| `.venv/bin/python -m ruff check .` | **All checks passed!**, exit code 0 |
| `.venv/bin/python -m ruff format --check .` | **42 files already formatted**, exit code 0 |
| `.venv/bin/python -m compileall -q app tests alembic` | Pass, exit code 0 |
| `git diff --check` | Pass, exit code 0 |
| `env -u DISCORD_TOKEN -u DISCORD_OWNER_ID .venv/bin/python -m app.main` | Exit code **2** đúng kỳ vọng: lỗi thiếu `DISCORD_TOKEN` an toàn, chưa kết nối Discord |

Các nhóm kiểm thử:

| Nhóm | Bằng chứng |
|---|---|
| Config | Thiếu token/ID; ID không hợp lệ; timezone/URL/log level; `.env` và precedence; `repr` không lộ token |
| Owner auth | Tree guard, trực tiếp gọi callbacks, phản hồi deny ephemeral/followup, service từ chối trước truy cập DB |
| Commands/UI | `/ping`, chính xác tiêu đề và 11 module “Sắp ra mắt”, không tạo View hoặc số liệu giả |
| Startup/events | Init DB + owner trước sync; sync một lần qua setup hook; ready lặp không sync lại; startup lỗi không sync; cleanup |
| DM | Chỉ phản hồi owner, bỏ qua non-owner/bot/server messages; không đọc message content |
| Database | Migration từ DB rỗng, lặp bootstrap, schema không lệch models, rollback migration bị gián đoạn và chạy lại thành công |
| Durability | Đóng engine, mở engine mới trên cùng file: owner/settings/timezone/preferences và UTC timestamps được giữ |
| Integrity | Khóa ngoại từ chối settings mồ côi; bootstrap lỗi rollback; đổi config owner không chiếm DB cũ; từ chối naive datetime |
| Migration CLI | Subprocess `alembic upgrade head`, `check`, `downgrade base`, `upgrade head` trên DB tạm; không cần Discord credentials |
| Logging/errors | Token kể cả ký tự JSON đặc biệt bị che, exception text/payload không ra log, lỗi response hết hạn được xử lý |

`git check-ignore` cũng xác minh `.env`, `.env.local`, `.venv/`, `nova.db`, `nova.db-wal`, `__pycache__/`, `.pytest_cache/` bị ignore. Chưa chạy PowerShell trên Windows trong môi trường Linux.

## Đối chiếu Acceptance P1 trong ROADMAP

| Tiêu chí | Trạng thái và bằng chứng |
|---|---|
| Bot online trong Discord và `/ping` trả lời | Logic/startup mock pass; **đạt theo xác nhận nghiệm thu Phase 1 của người dùng** |
| `/menu` dashboard placeholder, không fake data | Embed/callback test pass; **đạt theo xác nhận nghiệm thu Phase 1 của người dùng** |
| Chặn non-owner ở slash/DM/callback liên quan | Tests tree + callback + DM pass; **đạt theo xác nhận nghiệm thu Phase 1 của người dùng**; P1 không có UI callbacks |
| Thiếu token/owner ID lỗi an toàn | **Đạt tự động**: configuration/main/logging tests pass |
| SQLite tạo được, restart giữ settings/owner | **Đạt tự động**: SQLite file thật, engine restart, migration và persistence tests pass |
| Tests pass, không cần Discord thật | **Đạt**: 65 tests, network guard, mock Discord |
| README hướng dẫn cài/chạy/xử lý lỗi | **Đã viết và rà soát**; chưa chạy PowerShell trên Windows |

ROADMAP đã cập nhật toàn bộ acceptance P1 theo kết quả tự động và xác nhận nghiệm thu của người dùng. Không có phiên đăng nhập Discord bằng token thật do Codex thực hiện trong quá trình kiểm thử tự động.

## File đã tạo

Các file source mới, bao gồm các package `__init__.py`:

```text
.env.example
.gitignore
pyproject.toml
requirements.txt
requirements-dev.txt
alembic.ini
alembic/env.py
alembic/script.py.mako
alembic/versions/0001_foundation.py
app/__init__.py
app/config.py
app/logging_config.py
app/main.py
app/domain/__init__.py
app/domain/authorization.py
app/db/__init__.py
app/db/base.py
app/db/models.py
app/db/session.py
app/db/repositories/__init__.py
app/db/repositories/user_repository.py
app/services/__init__.py
app/services/settings_service.py
app/discord_bot/__init__.py
app/discord_bot/client.py
app/discord_bot/checks.py
app/discord_bot/error_handlers.py
app/discord_bot/commands/__init__.py
app/discord_bot/commands/foundation.py
app/discord_bot/renderers/__init__.py
app/discord_bot/renderers/dashboard.py
tests/conftest.py
tests/test_authorization.py
tests/test_client.py
tests/test_commands.py
tests/test_config.py
tests/test_database.py
tests/test_logging_and_main.py
docs/PHASE_1_VALIDATION.md
```

Tổng cộng **39 file mới** trong phiên triển khai ban đầu. File đã sửa khi triển khai: `README.md` (trạng thái source, cấu trúc, runbook, config, tests, smoke test, troubleshooting). Không sửa kiến trúc đã chốt hoặc triển khai phase khác. `.venv/` và các cache được tạo cục bộ, bị ignore. Tại thời điểm chạy kiểm thử tự động ban đầu chưa có `.env` hoặc `DISCORD_TOKEN`/`DISCORD_OWNER_ID` trong environment. Sau đó đã tạo `.env` từ file mẫu để người dùng tự cấu hình; không đọc hoặc in secret. Lần chốt nghiệm thu cập nhật `README.md`, `docs/ROADMAP.md` và báo cáo này.

## Chạy lại và kiểm tra khi cần

Khi cần cài trên máy khác hoặc kiểm tra lại, dùng các lệnh PowerShell trong [README](../README.md): tạo venv, cài dependencies, copy `.env.example` nếu chưa có `.env`, tự điền token/user ID bằng trình chỉnh sửa. Có thể điền guild ID cho private server. Chạy `python -m app.main` bằng Python trong venv, sau đó thực hiện checklist smoke test owner/non-owner/restart.

Không đưa token vào phản hồi nghiệm thu. Khi xác nhận kết quả live, chỉ cần ghi trạng thái `/ping`, `/menu`, owner/non-owner và restart.
