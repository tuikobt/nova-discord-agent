# NOVA AI — Discord Personal Assistant

> **Trạng thái:** Phase 1 và Phase 2 **DONE**. Phase 3 đang triển khai: **3A — Database & Migration hoàn tất**, **250 tests pass**. Chưa bắt đầu 3B/3C; chưa có CRUD Tasks/Projects/Calendar trên Discord.
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
| — | [`AGENTS.md`](AGENTS.md) | Quy ước bắt buộc dành cho Codex/AI lập trình |

## Trạng thái module

| Module | Thời điểm xây | Trạng thái |
|---|---|---|
| Discord Bot, owner-only access, `/ping`, `/menu`, DB bootstrap | Phase 1 | ✅ DONE — người dùng xác nhận 2026-10-23 |
| Dashboard neo, buttons/select/modal, Help, Settings | Phase 2 | ✅ DONE — người dùng xác nhận 2026-10-23 |
| Tasks, Projects, Calendar | Phase 3 | 3A: models + migration hoàn tất; 3B services và 3C UI chưa bắt đầu |
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
│   │   ├── checks.py            # owner guard cho tree và callbacks
│   │   ├── error_handlers.py
│   │   ├── commands/foundation.py
│   │   ├── views/dashboard.py   # persistent View, panels, select, timezone modal
│   │   └── renderers/dashboard.py
│   ├── domain/                  # authorization, module catalogue, view models, pagination
│   ├── services/                # settings_service, dashboard_service
│   └── db/
│       ├── base.py              # UTC-aware application timestamps
│       ├── models.py            # Foundation + Project, Task, CalendarEvent
│       ├── backup.py            # SQLite snapshot, không ghi đè file đã có
│       ├── session.py           # async engine, transactions, PRAGMA, migrations
│       └── repositories/        # user_repository, settings_repository
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

Phase 2 dùng legacy Embed + View: có buttons/select, panel riêng tư, modal timezone, `/help` và `/settings`. Phase 3A bổ sung schema Tasks/Projects/Calendar; chưa có services CRUD hoặc UI quản lý, các panel vẫn “Sắp ra mắt”. Dependencies giữ nguyên; schema và dữ liệu Foundation được bảo toàn.

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

Trong server, `/ping` trả `Pong! NOVA đang online.`; lần đầu `/menu` tạo và ghim **NOVA — PERSONAL CONTROL CENTER** trong kênh riêng, lưu message/channel ID vào DB và trả link ephemeral. Các lần sau dùng lại bảng đó, kể cả gọi từ kênh khác. Button/select mở panel ephemeral, không ghi đè bảng neo. `/menu` trong DM mở Home riêng, không tạo dashboard server. DM thường của owner chỉ nhận hướng dẫn; DM từ tài khoản khác bị bỏ qua, nội dung không được đọc hoặc lưu.

## Chạy lại trên Linux

Nếu bot đang chạy, nhấn `Ctrl+C` trước. Dùng venv hiện có, giữ nguyên `.env` và database. Trước lần chạy source Phase 3A đầu tiên, backup và migrate theo [runbook Phase 3A](docs/PHASE_3A_VALIDATION.md#migration-và-khôi-phục), vì startup sẽ tự upgrade schema:

```bash
.venv/bin/python -m app.main
```

Máy mới cần Python 3.12+, tạo venv và cài `requirements-dev.txt`. Không cần thêm biến môi trường hay dependencies cho Phase 2. Startup tự đăng ký persistent View; không tự gửi dashboard mới. Mở `/menu` trong kênh riêng để tạo bảng đầu tiên hoặc phục hồi bảng đã bị xóa.

## Dùng Dashboard trong Discord

- Nút nhanh: **Today**, **Tasks**, **Projects**, **Reminders**, **AI Assistant**.
- Select **Các module khác…**: Calendar, Goals, Finance, Habits, Notes, Memory, Reports.
- **Help**, **Settings**, **Refresh** nằm trên dashboard. Mỗi panel module có **Back** và **Refresh**; danh sách tính năng dài có **Previous/Next**.
- Chưa có backend task/project/reminder/calendar: hiển thị **Chưa có dữ liệu** hoặc **Sắp ra mắt**, không hiển thị số 0 như thống kê đã đo.
- Settings đọc language, timezone, giờ briefing/review, notification preference từ DB. Chỉ **Sửa Timezone** được ghi thật; ví dụ `Asia/Ho_Chi_Minh` hoặc `UTC`. Language/automation/notification chưa mở chức năng sửa.
- Panel riêng tư có thời hạn 10 phút; điều hướng thay panel và làm mới phiên. Modal có thời hạn 5 phút. Bảng neo không có timeout, các nút được đăng ký lại sau restart.
- Khi chuyển giữa mobile và web, mở lại module từ bảng neo để có panel riêng trên thiết bị đang dùng. Settings đã lưu dùng chung database; Refresh đọc lại giá trị mới.

Hướng dẫn kiểm tra từng nút, tài khoản khác và restart nằm trong [báo cáo Phase 2](docs/PHASE_2_VALIDATION.md).

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

## Kiểm thử tự động

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

Phase 3A đã kiểm thử trên Linux với **Python 3.12.15: 250 passed**; gồm hồi quy Phase 1–2 và tests migration/constraints/relationships/UTC/persistence/backup/restore. Tests dùng SQLite tạm, mock Discord và chặn mạng. Bản sao backup DB Phase 2 thực tế cũng đã thử upgrade/downgrade/reupgrade và restore, bảo toàn mọi cột Foundation; `nova.db` đang dùng chưa bị migration. Chi tiết tại [báo cáo Phase 3A](docs/PHASE_3A_VALIDATION.md). [Báo cáo Phase 2](docs/PHASE_2_VALIDATION.md) và [Phase 1](docs/PHASE_1_VALIDATION.md) là kết quả lịch sử; chưa chạy PowerShell trên Windows hoặc kiểm chứng lại Discord trong phiên 3A.

## Kiểm tra hồi quy Foundation

Người dùng đã xác nhận “Phase 1 DONE” ngày 2026-10-23. Giữ checklist dưới đây để kiểm tra lại khi thay đổi cấu hình hoặc môi trường chạy.

1. Chạy bot trong server riêng, kiểm tra log `bot_online`, chạy `/ping` bằng owner.
2. Chạy `/menu`, kiểm tra dashboard có các module và trạng thái rõ ràng, không có số liệu giả; panel của owner vẫn là ephemeral.
3. Dùng tài khoản khác chạy `/ping`, `/menu`: chỉ nhận thông báo không có quyền. Nhắn DM từ tài khoản đó: không được phục vụ. DM từ owner: chỉ có hướng dẫn.
4. Sau khi backup/nâng cấp, dừng rồi chạy lại bot, kiểm tra `/ping`, `/menu`, revision `0002_core_management` và dữ liệu settings/dashboard vẫn còn. Persistence đã có integration tests.
5. Ghi nhận kết quả thực tế khi kiểm tra lại. P1/P2 đã nghiệm thu; P3A hoàn tất, P3B/P3C chưa bắt đầu. Panel module vẫn chưa có CRUD.

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
