# NOVA AI — Discord Personal Assistant

> **Trạng thái:** Phase 1 (Foundation) **DONE**, người dùng xác nhận nghiệm thu ngày **2026-10-23**. Kết quả tự động từ phiên triển khai: **65 tests pass**. Phase 2 chưa bắt đầu.
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
| — | [`AGENTS.md`](AGENTS.md) | Quy ước bắt buộc dành cho Codex/AI lập trình |

## Trạng thái module

| Module | Thời điểm xây | Trạng thái |
|---|---|---|
| Discord Bot, owner-only access, `/ping`, `/menu`, DB bootstrap | Phase 1 | ✅ DONE — người dùng xác nhận 2026-10-23 |
| Dashboard, menu, button, modal, settings shell | Phase 2 | Chưa bắt đầu |
| Tasks, Projects, Calendar | Phase 3 | Chưa bắt đầu |
| Reminders tự động | Phase 4 | Chưa bắt đầu |
| AI Agent, chat tự nhiên, function tools | Phase 5 | Chưa bắt đầu |
| Memory, planner thông minh, daily/weekly reports | Phase 6 | Chưa bắt đầu |
| Goals, Finance, Habits, Notes, integrations, deploy | Phase 7+ | Chưa bắt đầu |

## Cấu trúc source Phase 1

```text
nova-discord-agent/
├── app/
│   ├── main.py                  # lifecycle, chạy Gateway, cleanup
│   ├── config.py                # đọc .env, validate trước khi kết nối
│   ├── logging_config.py        # JSON metadata, che token, không log raw content
│   ├── discord_bot/
│   │   ├── client.py            # intents, events, setup_hook, slash sync
│   │   ├── checks.py            # owner guard cho tree và callbacks
│   │   ├── error_handlers.py
│   │   ├── commands/foundation.py
│   │   └── renderers/dashboard.py
│   ├── domain/authorization.py
│   ├── services/settings_service.py
│   └── db/
│       ├── base.py              # UTC-aware application timestamps
│       ├── models.py            # users, user_settings, audit_logs skeleton
│       ├── session.py           # async engine, transactions, PRAGMA, migrations
│       └── repositories/user_repository.py
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

Các thư mục views, scheduler, agent và module nghiệp vụ sẽ được tạo ở phase tương ứng. Phase 1 chỉ có Embed shell; chưa có button/select/modal, pinned dashboard, `/help` hoặc `/settings`.

## Chuẩn bị Discord

1. Tạo application trong [Discord Developer Portal](https://discord.com/developers/applications), vào **Bot** để lấy/reset bot token. Điền token trực tiếp vào `.env` trên máy; không đưa vào chat, source hay Git. Xem [hướng dẫn tạo bot của discord.py](https://discordpy.readthedocs.io/en/stable/discord.html).
2. Mời bot vào server riêng với scopes `bot` và `applications.commands`. Cấp View Channels, Send Messages, Read Message History, Embed Links cho kênh dùng bot; owner cần quyền Use Application Commands. Không cần Administrator. Tham khảo [Discord installation setup](https://docs.discord.com/developers/quick-start/getting-started).
3. Bật Developer Mode trong Discord, dùng **Copy User ID** của tài khoản owner cho `DISCORD_OWNER_ID`. Đây là user ID, không phải bot/application ID. Có thể copy server ID cho biến `DISCORD_GUILD_ID` tùy chọn.
4. Phase 1 chỉ bật intents `guilds` và `dm_messages`; để các privileged intents Message Content, Server Members, Presence tắt. Bot dùng Gateway, không yêu cầu Interactions Endpoint URL hay web server.
5. Giữ các kênh NOVA private cho owner/bot. Owner guard trong code vẫn áp dụng cho từng slash command, callback của command và DM.

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

Biến môi trường của process ưu tiên hơn `.env`. Không cần OpenAI key. Settings đã lưu trong DB không bị ghi đè khi restart hay khi đổi `TIMEZONE` trong `.env`; UI sửa settings thuộc phase sau.

```powershell
# Tùy chọn: tạo schema trước khi kết nối Discord; không cần token để chạy migration
.\.venv\Scripts\python.exe -m alembic upgrade head

# Chạy bot; startup cũng tự áp dụng migration còn thiếu và khởi tạo owner/settings
.\.venv\Scripts\python.exe -m app.main
```

Khi kết nối thành công, log JSON có event `slash_commands_registered`, sau đó `bot_online`. Dừng bằng `Ctrl+C`. Bot bật reconnect khi mất Gateway và đóng async engine khi thoát.

Trong server, `/ping` trả `Pong! NOVA đang online.`; `/menu` mở Embed **NOVA — PERSONAL CONTROL CENTER** với đủ 11 module, tất cả ghi **Sắp ra mắt**. Các phản hồi là ephemeral. Chưa có số liệu task/lịch hay dữ liệu demo. DM của owner chỉ nhận hướng dẫn Phase 1; DM từ tài khoản khác bị bỏ qua, nội dung không được đọc hoặc lưu.

## Database và migration

SQLite dành cho một process local. Startup tạo `users`, `user_settings`, `audit_logs` skeleton và `alembic_version` qua migration `0001_foundation`; không tạo bảng của phase sau. Bootstrap owner + settings dùng một transaction, có khóa ngoại; chạy lại giữ nguyên bản ghi và preferences. Nếu DB đang thuộc owner khác, startup dừng với `OwnerMismatchError`.

Mốc `created_at`/`updated_at` ở application layer luôn UTC-aware; adapter SQLite chuẩn hóa UTC khi lưu và gắn UTC khi đọc. Các giờ briefing/workday chưa cấu hình để trống; chưa có automation gửi thông báo. `tzdata` cung cấp timezone database cho Windows.

```powershell
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic check
```

Giữ nguyên `DATABASE_URL` và file database khi restart. Dừng bot trước khi sao lưu file DB vào nơi riêng tư. Không đưa DB vào Git và không chạy nhiều process bot trên cùng SQLite file.

## Kiểm thử tự động

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

Đã kiểm thử trên Linux với **Python 3.12.15: 65 passed**; lint/format pass. Tests dùng SQLite file tạm và mock Discord, chặn kết nối mạng, không cần `.env` thật. Bao gồm config, quyền owner, callbacks, DM, startup, rollback, migration/khóa ngoại, UTC, giữ settings qua restart và lỗi không lộ nội dung riêng tư. Người dùng đã xác nhận nghiệm thu Phase 1 ngày 2026-10-23 sau checklist Discord thực tế. Codex không tự đăng nhập Discord hoặc chạy PowerShell trên Windows trong môi trường này. Xem [báo cáo nghiệm thu](docs/PHASE_1_VALIDATION.md).

## Checklist kiểm thử thủ công Phase 1

Người dùng đã xác nhận “Phase 1 DONE” ngày 2026-10-23. Giữ checklist dưới đây để kiểm tra lại khi thay đổi cấu hình hoặc môi trường chạy.

1. Chạy bot trong server riêng, kiểm tra log `bot_online`, chạy `/ping` bằng owner.
2. Chạy `/menu`, kiểm tra tiêu đề, đủ 11 module “Sắp ra mắt”, không có số liệu giả; tài khoản khác không thấy phản hồi ephemeral.
3. Dùng tài khoản khác chạy `/ping`, `/menu`: chỉ nhận thông báo không có quyền. Nhắn DM từ tài khoản đó: không được phục vụ. DM từ owner: chỉ có hướng dẫn Phase 1.
4. Dừng rồi chạy lại bot, kiểm tra `/ping`, `/menu` và `alembic current` vẫn là `0001_foundation`, file DB vẫn còn. Persistence của owner/settings đã có integration test riêng.
5. Ghi nhận kết quả thực tế khi kiểm tra lại. Acceptance P1 trong ROADMAP đã được cập nhật theo xác nhận của người dùng; chưa triển khai Phase 2.

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
