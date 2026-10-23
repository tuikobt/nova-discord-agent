# NOVA AI — Discord Personal Assistant

> **Trạng thái:** Phase 1/2 và checkpoint 3A/3B đã hoàn tất. **Source Phase 3C — Discord CRUD UI đã triển khai, 419 tests pass**, có bộ chọn ngày/giờ và bản nháp trước khi lưu; chờ nghiệm thu Discord Desktop/Mobile để chốt toàn Phase 3. Chưa triển khai Phase 4.
>
> **Cập nhật:** 2026-10-23 · **Ngôn ngữ:** Tiếng Việt · **Múi giờ mặc định:** `Asia/Ho_Chi_Minh`

## NOVA là gì?

NOVA là **trợ lý AI cá nhân trên Discord**, sử dụng **DM để trò chuyện tự nhiên** và **một server riêng để hiển thị dashboard, thông báo, báo cáo**. NOVA giúp quản lý lịch, công việc, dự án, nhắc nhở và — ở các giai đoạn kế tiếp — mục tiêu, thói quen, ghi chú, tài chính, trí nhớ dài hạn, ứng dụng ngoài.

**Nguyên tắc sản phẩm:** *Không cần nhớ lệnh; nhắn tin hoặc bấm nút là đủ.* AI chỉ đề xuất hoặc thực hiện hành động trong phạm vi quyền được cấu hình; thao tác quan trọng cần được xác nhận.

## Bắt đầu đọc tài liệu theo thứ tự

| Thứ tự | Tài liệu | Để làm gì? |
|---|---|---|
| 1 | [`docs/PRD.md`](docs/PRD.md) | Hiểu sản phẩm, phạm vi MVP và tiêu chí nghiệm thu |
| 2 | [`docs/DISCORD_UI.md`](docs/DISCORD_UI.md) | Hình dung màn hình, nút bấm, thao tác và luồng sử dụng |
| 3 | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Cấu trúc hệ thống và các thành phần kỹ thuật |
| 4 | [`docs/DATABASE.md`](docs/DATABASE.md) | Các bảng dữ liệu, quan hệ và quy tắc lưu trữ |
| 5 | [`docs/AGENT_TOOLS.md`](docs/AGENT_TOOLS.md) | AI có những tool nào, lúc nào phải xin xác nhận |
| 6 | [`docs/ROADMAP.md`](docs/ROADMAP.md) | Các phase và tiêu chuẩn hoàn thành |
| 7 | [`docs/SECURITY.md`](docs/SECURITY.md) | Token, dữ liệu riêng tư, phân quyền và sao lưu |
| 8 | [`docs/PHASE_1_HANDOFF.md`](docs/PHASE_1_HANDOFF.md) | Hướng dẫn tiếp tục Phase 1 bằng Codex CLI |
| 9 | [`docs/PHASE_1_VALIDATION.md`](docs/PHASE_1_VALIDATION.md) | Kết quả tests, đối chiếu nghiệm thu và danh sách file Phase 1 |
| 10 | [`docs/PHASE_2_VALIDATION.md`](docs/PHASE_2_VALIDATION.md) | Dashboard Phase 2, kết quả tests, file thay đổi và checklist kiểm tra từng nút |
| 11 | [`docs/PHASE_3_HANDOFF.md`](docs/PHASE_3_HANDOFF.md) | Handoff Phase 3, chia checkpoint 3A/3B/3C |
| 12 | [`docs/PHASE_3A_VALIDATION.md`](docs/PHASE_3A_VALIDATION.md) | Models, migration, backup/restore và kết quả kiểm thử Phase 3A |
| 13 | [`docs/PHASE_3B_VALIDATION.md`](docs/PHASE_3B_VALIDATION.md) | Service API, owner scope, CRUD, overlap, pending actions thủ công và tests 3B |
| 14 | [`docs/PHASE_3C_VALIDATION.md`](docs/PHASE_3C_VALIDATION.md) | UI CRUD, kết quả kiểm thử, file thay đổi và checklist nghiệm thu Phase 3 |
| — | [`AGENTS.md`](AGENTS.md) | Quy ước bắt buộc dành cho Codex/AI lập trình |

## Trạng thái module

| Module | Thời điểm xây | Trạng thái |
|---|---|---|
| Discord Bot, owner-only access, `/ping`, `/menu`, DB bootstrap | Phase 1 | ✅ DONE — người dùng xác nhận 2026-10-23 |
| Dashboard neo, buttons/select/modal, Help, Settings | Phase 2 | ✅ DONE — người dùng xác nhận 2026-10-23 |
| Tasks, Projects, Calendar | Phase 3 | Có schema, services và Discord CRUD UI; source/tests xong, chờ nghiệm thu Desktop/Mobile |
| Reminders tự động | Phase 4 | Chưa bắt đầu |
| AI Agent, chat tự nhiên, function tools | Phase 5 | Chưa bắt đầu |
| Memory, planner thông minh, daily/weekly reports | Phase 6 | Chưa bắt đầu |
| Goals, Finance, Habits, Notes, integrations, deploy | Phase 7+ | Chưa bắt đầu |

## Cấu trúc source hiện tại

```text
nova-discord-agent/
├── app/
│   ├── main.py                  # lifecycle, chạy Gateway, cleanup
│   ├── config.py                # đọc .env, validate trước khi kết nối
│   ├── logging_config.py        # JSON metadata, che token, không log raw content
│   ├── discord_bot/
│   │   ├── client.py            # intents, events, setup_hook, slash sync
│   │   ├── dashboard_controller.py # điều phối các panel riêng tư
│   │   ├── dashboard_publisher.py  # tái sử dụng/ghim dashboard neo
│   │   ├── core_controller.py   # điều phối CRUD, xác nhận và lỗi; không SQL
│   │   ├── core_state.py        # navigation / write intent riêng từng panel
│   │   ├── form_controller.py   # bản nháp, chọn ngày/giờ và liên kết trước khi lưu
│   │   ├── checks.py            # owner guard cho tree và callbacks
│   │   ├── error_handlers.py
│   │   ├── commands/foundation.py
│   │   ├── views/              # dashboard.py, core.py, core_forms.py, core_pickers.py
│   │   └── renderers/          # dashboard.py, core.py (legacy embeds)
│   ├── domain/                  # DTO, errors, enums, UTC/local time, manual approvals, UI models
│   ├── services/                # project/task/calendar, summary, settings/dashboard
│   └── db/
│       ├── base.py              # UTC-aware application timestamps
│       ├── models.py            # Foundation + Project, Task, CalendarEvent
│       ├── backup.py            # SQLite snapshot, không ghi đè file đã có
│       ├── session.py           # async engine, transactions, PRAGMA, migrations
│       └── repositories/        # project/task/calendar owner scope + user/settings
├── alembic/                    # migration foundation có upgrade/downgrade
├── tests/                      # mock Discord, SQLite file tạm, chặn network
├── docs/
├── alembic.ini
├── requirements.txt            # runtime dependencies đã pin
├── requirements-dev.txt        # pytest + Ruff
├── pyproject.toml              # Python >=3.12, cấu hình lint/test
├── .env.example
├── .gitignore
├── AGENTS.md
└── README.md
```

Phase 3C nối legacy Embed + View với services 3B. Có form thêm/sửa, danh sách/chi tiết, status/priority, chọn quan hệ, ngày/tuần và duyệt thay đổi nhạy cảm. Không có hard-delete; dùng archive/cancel để giữ liên kết. Dependencies và schema giữ nguyên; bot vẫn chưa có AI/reminder engine.

## Chuẩn bị Discord

1. Tạo application trong [Discord Developer Portal](https://discord.com/developers/applications), vào **Bot** để lấy/reset bot token. Điền token trực tiếp vào `.env` trên máy; không đưa vào chat, source hay Git. Xem [hướng dẫn tạo bot của discord.py](https://discordpy.readthedocs.io/en/stable/discord.html).
2. Mời bot vào server riêng với scopes `bot` và `applications.commands`. Cấp View Channels, Send Messages, Read Message History, Embed Links và **Pin Messages** cho kênh dashboard; owner cần quyền Use Application Commands. Không cần Administrator. Tham khảo [Discord installation setup](https://docs.discord.com/developers/quick-start/getting-started) và [quyền ghim tin nhắn](https://discordpy.readthedocs.io/en/stable/interactions/api.html#discord.InteractionMessage.pin).
3. Bật Developer Mode trong Discord, dùng **Copy User ID** của tài khoản owner cho `DISCORD_OWNER_ID`. Đây là user ID, không phải bot/application ID. Có thể copy server ID cho biến `DISCORD_GUILD_ID` tùy chọn.
4. Bot chỉ bật intents `guilds` và `dm_messages`; để các privileged intents Message Content, Server Members, Presence tắt. Bot dùng Gateway, không yêu cầu Interactions Endpoint URL hay web server.
5. Tạo kênh văn bản riêng như `#nova-dashboard`: tắt **View Channel** cho `@everyone`, chỉ cho owner/bot xem. Kiểm tra cả các role/overwrites khác; bot kiểm tra quyền `@everyone`, không thay thế việc cấu hình quyền server. Owner guard vẫn kiểm tra mỗi slash command, button, select, modal và DM.

## Cài và chạy trên Windows PowerShell

Cài Python **3.12+**; ví dụ dưới đây chọn Python 3.12. Mở PowerShell tại thư mục có `app/`, `AGENTS.md` và `README.md`.

```powershell
py -3.12 --version
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Chỉ cần runtime thì cài `requirements.txt`. Các lệnh dùng trực tiếp Python trong venv nên không cần đổi ExecutionPolicy hoặc activate PowerShell script. Nếu dùng Python mới hơn, thay `-3.12` bằng phiên bản đã cài khi tạo venv.

Điền `.env` bằng trình chỉnh sửa cục bộ:

```dotenv
DISCORD_TOKEN=replace-me
DISCORD_OWNER_ID=replace-with-your-user-id
DATABASE_URL=sqlite+aiosqlite:///./nova.db
TIMEZONE=Asia/Ho_Chi_Minh
LOG_LEVEL=INFO
DISCORD_GUILD_ID=
```

| Biến | Ý nghĩa |
|---|---|
| `DISCORD_TOKEN` | Bắt buộc: bot token thật thay placeholder; không phải Client Secret |
| `DISCORD_OWNER_ID` | Bắt buộc: Discord user ID dạng số của owner |
| `DATABASE_URL` | File SQLite qua `aiosqlite`; đường dẫn tương đối tính từ thư mục project, không dùng `:memory:` |
| `TIMEZONE` | Múi giờ IANA để khởi tạo owner mới; mặc định `Asia/Ho_Chi_Minh` |
| `LOG_LEVEL` | `INFO`, `WARNING`, `ERROR`, `CRITICAL`; mặc định `INFO` |
| `DISCORD_GUILD_ID` | Tùy chọn: đăng ký lệnh cho server riêng để kiểm thử; để trống thì sync global |

Biến môi trường của process ưu tiên hơn `.env`. Không cần OpenAI key. Settings đã lưu trong DB không bị ghi đè khi restart hay khi đổi `TIMEZONE` trong `.env`; đổi múi giờ đang dùng bằng **Settings → Sửa Timezone**. Các cài đặt automation vẫn chỉ đọc và ghi rõ “Chưa kích hoạt”.

```powershell
# Database cũ: dừng bot và backup theo phần Database bên dưới trước khi nâng cấp
# Máy mới: tạo schema trước khi kết nối Discord; không cần token để chạy migration
.\.venv\Scripts\python.exe -m alembic upgrade head

# Chạy bot; startup cũng tự áp dụng migration còn thiếu và khởi tạo owner/settings
.\.venv\Scripts\python.exe -m app.main
```

Khi kết nối thành công, log JSON có event `slash_commands_registered`, sau đó `bot_online`. Dừng bằng `Ctrl+C`. Bot bật reconnect khi mất Gateway và đóng async engine khi thoát.

Trong server, `/ping` trả `Pong! NOVA đang online.`; lần đầu `/menu` tạo/ghim **NOVA — PERSONAL CONTROL CENTER**, lưu message/channel ID và trả link kèm Home riêng tư có số liệu DB. Các lần sau dùng lại bảng neo. Bảng neo chỉ có điều hướng, không công khai thống kê/settings; buttons/select mở panel ephemeral. `/menu` trong DM mở Home riêng, không tạo bảng server. DM thường của owner chỉ nhận hướng dẫn; chưa có AI chat.

## Chạy lại trên Linux

Nếu bot đang chạy, nhấn `Ctrl+C` trước. Dùng venv hiện có, giữ nguyên `.env` và database. Trước lần chạy source Phase 3A đầu tiên, backup và migrate theo [runbook Phase 3A](docs/PHASE_3A_VALIDATION.md#migration-và-khôi-phục), vì startup sẽ tự upgrade schema:

```bash
.venv/bin/python -m app.main
```

Máy mới cần Python 3.12+, tạo venv và cài `requirements-dev.txt`. Riêng 3C không thêm biến `.env`, dependency hoặc migration. Startup tự đăng ký lại persistent View. Sau nâng cấp, mở `/menu` hoặc bấm Refresh trên bảng neo để cập nhật nhãn module; bảng không bị nhân đôi.

## Dùng Dashboard trong Discord

- Nút nhanh: **Today**, **Tasks**, **Projects**, **Reminders**, **AI Assistant**.
- Select **Các module khác…**: Calendar, Goals, Finance, Habits, Notes, Memory, Reports.
- **Projects → Thêm** nhập tên, mô tả tùy chọn → bản nháp → **Chọn deadline**, chọn trạng thái → **Lưu**. Deadline có thể bỏ trống. **Xem tasks** mở danh sách liên quan; **Thêm task** gắn project sẵn.
- **Tasks → Thêm** nhập tiêu đề, mô tả tùy chọn → bản nháp → chọn deadline, ưu tiên, thời lượng ước tính và dự án → **Lưu**. Chọn task đã lưu để **Sửa**, **Hoàn thành / Mở lại**, đổi status/priority, **Đổi dự án** hoặc **Lên lịch**. Chọn quan hệ qua menu, không cần nhập ID.
- **Calendar → Thêm** nhập tiêu đề → bản nháp → **Chọn bắt đầu** → chọn ngày, giờ, phút → **Dùng ngày giờ** → chọn thời lượng hoặc **Chọn kết thúc** → chọn **Cố định/Linh hoạt**, công việc liên kết → **Lưu**. Không cần gõ ngày giờ hay “có/không”. Trùng giờ hoặc sửa lịch confirmed vẫn cần duyệt riêng.
- Bộ chọn hiện lịch tháng, nút tháng trước/sau, **Hôm nay**, hai menu ngày 01–16 / 17–cuối tháng, giờ 00–23 và phút theo bước 5 phút. Chọn xong bấm **Dùng ngày giờ** mới cập nhật bản nháp. Cần phút khác hoặc ngày xa: **Nhập ngày/giờ chính xác**; Tasks dùng **Nhập ngày/giờ, số phút** để nhập thời lượng khác. Nhập tay tùy chọn dùng `YYYY-MM-DD HH:MM` theo timezone Settings.
- **Calendar → Chọn ngày** dùng bộ chọn ngày, có **Ngày mai**; **Xem tuần/Xem ngày** và nút trước/sau hỗ trợ xem lịch. **Tasks → Deadline** chọn **Từ ngày / Đến hết ngày**, có **Hôm nay / 7 ngày tới**, bấm **Áp dụng**; không phải gõ khoảng ngày.
- Nhập form/chọn menu chưa ghi database. **Bỏ bản nháp** không lưu; **Quay lại** trong bộ chọn không áp dụng lựa chọn. Bản nháp hết hạn tối đa 10 phút, việc đổi màn hình/chọn menu không gia hạn; sau restart mở lại từ bảng neo.
- Danh sách có 5 mục/trang, **Previous/Next**, bộ lọc trạng thái; Tasks có thêm ưu tiên, project và khoảng deadline. **Back** giữ ngữ cảnh; **Refresh** đọc lại DB. **Today** có preview tối đa 5 lịch confirmed và 5 việc đến hạn/quá hạn hoặc ưu tiên cao, kèm tổng số thật.
- Hủy task/event, archive project, sửa lịch confirmed và giữ lịch trùng mở **Xác nhận thay đổi**. Xem trước/sau và các lịch trùng; nếu nhiều trang, **Duyệt** chỉ mở ở trang cuối. **Bỏ qua** không ghi. Token hết hạn tối đa 5 phút hoặc khi restart; phải xem/duyệt lại.
- Home riêng của owner hiển thị số liệu DB: Tasks không tính cancelled, Projects không tính archived, số tasks done và lịch confirmed giao ngày local. Tiến độ project là done / task không cancelled, tính theo số lượng. DB rỗng hiển thị 0/empty-state thật. Reminders/AI và module tương lai vẫn **Sắp ra mắt**.
- Settings đọc language, timezone, giờ briefing/review, notification preference từ DB. Chỉ **Sửa Timezone** được ghi thật; ví dụ `Asia/Ho_Chi_Minh` hoặc `UTC`. Language/automation/notification chưa mở chức năng sửa.
- Panel riêng tư có thời hạn tối đa 10 phút; bản nháp và các bước chọn ngày/giờ giữ nguyên hạn của phiên, không gia hạn khi điều hướng. Modal tối đa 5 phút. Bảng neo không có timeout, các nút được đăng ký lại sau restart.
- Khi chuyển giữa mobile và web, mở lại module từ bảng neo để có panel riêng trên thiết bị đang dùng. Settings đã lưu dùng chung database; Refresh đọc lại giá trị mới.

Checklist thử Desktop/Mobile, owner/non-owner và restart: [báo cáo 3C](docs/PHASE_3C_VALIDATION.md). Chưa đánh dấu Phase 3 DONE trước khi người dùng xác nhận kết quả thực tế.

## Database và migration

SQLite dành cho một process local. Migration `0001_foundation` tạo `users`, `user_settings`, `audit_logs`; `0002_core_management` thêm `projects`, `tasks`, `calendar_events`. `alembic_version` ghi revision. Startup vẫn tự áp dụng migration còn thiếu, vì vậy **dừng bot và backup database cũ trước lần chạy source Phase 3A đầu tiên**. Bootstrap owner + settings vẫn dùng transaction, giữ preferences/dashboard IDs; đổi owner cấu hình không được tiếp quản DB cũ.

Nâng cấp trong PowerShell, tại thư mục project, sau khi đã dừng bot:

```powershell
$novaBackup = ".\backups\pre-phase-3a-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".db"
.\.venv\Scripts\python.exe -m app.db.backup --output $novaBackup
if ($LASTEXITCODE -ne 0) { throw "Backup thất bại; dừng nâng cấp." }
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw "Migration thất bại; chưa chạy bot. Xem hướng dẫn restore." }
.\.venv\Scripts\python.exe -m alembic check
if ($LASTEXITCODE -ne 0) { throw "Schema chưa khớp; chưa chạy bot." }
.\.venv\Scripts\python.exe -m alembic current
```

Revision sau nâng cấp: `0002_core_management`. Không cần thêm biến `.env` hoặc thư viện. Backup lấy đường dẫn từ cùng cấu hình `DATABASE_URL` như bot; dùng SQLite backup API để lấy snapshot nhất quán, bao gồm dữ liệu đã commit trong WAL; không ghi đè backup cũ. Máy chưa có DB bỏ qua bước backup và chạy `alembic upgrade head`. Hướng dẫn Linux, xác định đường dẫn và **khôi phục nếu migration lỗi**: [Phase 3A runbook](docs/PHASE_3A_VALIDATION.md#migration-và-khôi-phục).

Mốc `created_at`/`updated_at` ở application layer luôn UTC-aware; adapter SQLite chuẩn hóa UTC khi lưu và gắn UTC khi đọc. Các giờ briefing/workday chưa cấu hình để trống; chưa có automation gửi thông báo. `tzdata` cung cấp timezone database cho Windows.

```powershell
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic check
```

Giữ nguyên `DATABASE_URL` và file database khi restart. Giữ backup tại nơi riêng tư (`backups/` đã được gitignore); không đưa DB vào Git và không chạy nhiều process bot trên cùng SQLite file. Downgrade về `0001_foundation` chỉ cho phép khi ba bảng P3 còn rỗng; không tự xóa dữ liệu để rollback.

Phase 3B/3C giữ revision `0002_core_management`, không có migration/cấu hình mới. Service kiểm tra owner trước khi mở session; updates có owner + expected version/timestamp, trả DTO sau commit. UI 3C dùng pending actions thủ công 5 phút của 3B, không có bảng pending_actions/AI executor P5. Chi tiết backend tại [báo cáo 3B](docs/PHASE_3B_VALIDATION.md).

## Kiểm thử tự động

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

Phase 3C đã kiểm thử trên Linux với **Python 3.12.15: 419 passed in 8.32s**. Bản UI đầu đạt 388 tests; lần rà soát trải nghiệm bổ sung 31 tests cho draft/picker, không lưu trước khi Lưu, lọc ngày, năm nhuận/DST, sửa chính xác và xử lý thao tác đồng thời. Hồi quy Foundation/Dashboard/schema/services vẫn pass, lint/format/compile pass. Tests dùng SQLite tạm, mock Discord và chặn mạng. Chưa chạy bot, Discord Desktop/Mobile hoặc PowerShell Windows trong phiên 3C. Chi tiết: [báo cáo 3C](docs/PHASE_3C_VALIDATION.md); báo cáo các checkpoint trước lưu kết quả lịch sử.

## Kiểm tra hồi quy Foundation

Người dùng đã xác nhận “Phase 1 DONE” ngày 2026-10-23. Giữ checklist dưới đây để kiểm tra lại khi thay đổi cấu hình hoặc môi trường chạy.

1. Chạy bot trong server riêng, kiểm tra log `bot_online`, chạy `/ping` bằng owner.
2. Chạy `/menu`, kiểm tra dashboard có các module và trạng thái rõ ràng, không có số liệu giả; panel của owner vẫn là ephemeral.
3. Dùng tài khoản khác chạy `/ping`, `/menu`: chỉ nhận thông báo không có quyền. Nhắn DM từ tài khoản đó: không được phục vụ. DM từ owner: chỉ có hướng dẫn.
4. Sau khi backup/nâng cấp, dừng rồi chạy lại bot, kiểm tra `/ping`, `/menu`, revision `0002_core_management` và dữ liệu settings/dashboard vẫn còn. Persistence đã có integration tests.
5. Thử đầy đủ checklist 3C và ghi nhận kết quả. P1/P2 đã nghiệm thu, 3A/3B hoàn tất; source/tests 3C xong nhưng Phase 3 chờ nghiệm thu thực tế, chưa chuyển P4.

## Xử lý lỗi thường gặp

| Hiện tượng | Cách kiểm tra |
|---|---|
| Lỗi cấu hình, exit code `2` | Điền token/owner ID, kiểm tra timezone/SQLite URL, kiểm tra env của process có ghi đè `.env` không; lỗi không in giá trị secret |
| `startup_failed`, `LoginFailure` | Token không đúng hoặc đã reset; sửa `.env` cục bộ rồi chạy lại |
| Không thấy slash commands | Kiểm tra scope `applications.commands`, quyền dùng lệnh, server ID đúng; global commands có thể cần chờ cập nhật trên client |
| `startup_failed`, `Forbidden` | Kiểm tra bot đã được mời vào đúng server và quyền kênh; không cấp Administrator để xử lý lỗi |
| Command trùng khi đổi guild/global | Dùng một chế độ sync ổn định; chuyển chế độ không tự xóa registration cũ trên Discord |
| `OperationalError` / database locked | Kiểm tra quyền ghi thư mục DB, đường dẫn và chỉ một process đang chạy |
| `OwnerMismatchError` | Đối chiếu owner ID với DB đã dùng; bot không tự đổi chủ hoặc xóa DB |
| Owner không nhận DM | Kiểm tra privacy settings; Phase 1 không fallback sang kênh công khai |
| `command_failed` / interaction hết hạn | Thử lại lệnh và xem `interaction_id`, `error_type`; không chia sẻ token hoặc raw nội dung riêng tư |
| `/menu` yêu cầu kênh riêng | Tắt View Channel cho `@everyone` trong kênh văn bản dashboard, cấp quyền owner/bot và kiểm tra role khác |
| Dashboard tạo được nhưng chưa ghim | Cấp Pin Messages, kiểm tra giới hạn ghim hoặc owner ghim thủ công; mở lại `/menu` sẽ dùng cùng message |
| Dashboard bị xóa | Mở `/menu`; bot tạo lại trong kênh đã lưu. Nếu cả kênh bị xóa, mở `/menu` trong kênh riêng mới |
| Mất quyền xem/đọc dashboard cũ | Sửa quyền kênh cũ; lỗi Forbidden không làm bot tạo bảng trùng ở kênh khác |
| Panel hết hạn sau restart hoặc chờ lâu | Mở panel mới từ bảng neo; chỉ bảng neo có persistent View |
| Form báo ngày không hợp lệ | Dùng `YYYY-MM-DD HH:MM` theo timezone Settings, hoặc `YYYY-MM-DD` ở bộ lọc ngày; không nhập `10/11` thiếu năm |
| Dữ liệu đã thay đổi / xác nhận không hợp lệ | Refresh, mở form và xem/duyệt lại; bot không ghi đè snapshot cũ |
| Có thông báo Đã lưu nhưng panel chưa tải được | Dữ liệu đã commit; mở module/Refresh để xem lại, không cần tạo thêm |

Log chỉ ghi metadata vận hành ra console, không bật SDK debug/SQL logging và không lưu raw DM. `.env`, DB, venv và cache được gitignore.

## Những quyết định đã chốt

- **Một chủ tài khoản** (allowlist Discord Owner ID), server riêng, **DM là giao diện trò chuyện chính**.
- Giao diện server có **4 kênh chức năng** để giảm sự phức tạp; không tạo hàng chục channel.
- **Zero-command by default:** người dùng có thể chọn nút/menu, slash commands chỉ để vào nhanh.
- **Giao diện dashboard thực sự nằm trong Discord**, không phải website được vẽ giống Discord.
- MVP làm lần lượt; module chưa xây hiển thị **“Sắp ra mắt”**, không trả dữ liệu giả.
- **Python + discord.py + SQLAlchemy + SQLite** ban đầu; **OpenAI Responses API** khi tới Phase 5.
- Các thay đổi lịch quan trọng, xóa dữ liệu, thao tác bên ngoài đều có bước xác nhận.

## Tài liệu tham khảo chính thức

- Discord setup: https://docs.discord.com/developers/quick-start/getting-started
- Discord Components: https://github.com/discord/discord-api-docs/blob/main/developers/components/overview.mdx
- Discord Application Commands: https://docs.discord.com/developers/docs/interactions/slash-commands
- OpenAI Function Calling: https://developers.openai.com/api/docs/guides/function-calling
- discord.py docs: https://discordpy.readthedocs.io/en/stable/
- Async migrations: https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic
- SQLite transactions: https://docs.sqlalchemy.org/en/21/dialects/sqlite.html#enabling-non-legacy-sqlite-transactional-modes-with-the-sqlite3-or-aiosqlite-driver
