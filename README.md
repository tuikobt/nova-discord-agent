# NOVA AI — Discord Personal Assistant

> **Trạng thái:** **Phase 5 DONE — người dùng xác nhận hoạt động ngày 2026-11-18.** Bộ tự động gần nhất: **687 tests pass**, lint/format/compile đạt. Bot online với AI `gpt-6-luna`, DB Windows ở head `0005_agent`. Đã xác minh OpenAI gọi tool đọc dữ liệu thật và một đề xuất tạo task được duyệt/executed, audit success trong DB. Phạm vi bằng chứng và rollback tại [báo cáo P5](docs/PHASE_5_VALIDATION.md). Dữ liệu Phase 1–4 giữ nguyên khi migration; chưa nhập dữ liệu Linux. **Phase 6 chưa bắt đầu**.
>
> **Cập nhật:** nghiệm thu P5, 2026-11-18 · **Ngôn ngữ:** Tiếng Việt · **Múi giờ mặc định:** `Asia/Ho_Chi_Minh`

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
| 15 | [`docs/NOVA_PHASE_4_HANDOFF.md`](docs/NOVA_PHASE_4_HANDOFF.md) | Handoff P4 chia checkpoint 4A/4B/4C |
| 16 | [`docs/PHASE_4A_VALIDATION.md`](docs/PHASE_4A_VALIDATION.md) | Schema, validation, 551 tests, giới hạn DB thật và runbook backup/migrate/rollback |
| 17 | [`docs/PHASE_4BC_VALIDATION.md`](docs/PHASE_4BC_VALIDATION.md) | Worker/UI, chính sách gửi/retry/quiet hours, 617 tests, runbook hiện tại và checklist live |
| 18 | [`docs/PHASE_4_FINAL_CHECK.md`](docs/PHASE_4_FINAL_CHECK.md) | Nghiệm thu P4: 625 tests, DB/Discord thật, DM/nút Đã làm và xác nhận người dùng |
| 19 | [`docs/PHASE_5_PLAN.md`](docs/PHASE_5_PLAN.md) | Kế hoạch các luồng DM/tools/approvals/limits của P5 |
| 20 | [`docs/PHASE_5_VALIDATION.md`](docs/PHASE_5_VALIDATION.md) | Nghiệm thu P5: 687 tests, OpenAI/Discord thật, cấu hình và rollback |
| — | [`AGENTS.md`](AGENTS.md) | Quy ước bắt buộc dành cho Codex/AI lập trình |

## Trạng thái module

| Module | Thời điểm xây | Trạng thái |
|---|---|---|
| Discord Bot, owner-only access, `/ping`, `/menu`, DB bootstrap | Phase 1 | ✅ DONE — người dùng xác nhận 2026-10-23 |
| Dashboard neo, buttons/select/modal, Help, Settings | Phase 2 | ✅ DONE — người dùng xác nhận 2026-10-23 |
| Tasks, Projects, Calendar | Phase 3 | Nghiệm thu tự động đạt; Discord live chưa xác minh |
| Reminders tự động | Phase 4 | ✅ DONE — người dùng xác nhận đã kiểm thử ngày 2026-11-17 |
| AI Agent, chat tự nhiên, function tools | Phase 5 | ✅ DONE — người dùng xác nhận hoạt động ngày 2026-11-18 |
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
│   ├── services/                # project/task/calendar, reminders/delivery, settings/summary
│   ├── scheduler/               # asyncio polling DB, claim/retry/recovery, shutdown
│   ├── agent/                   # Responses API, registry/gateway, policy/context/usage
│   └── db/
│       ├── base.py              # UTC-aware application timestamps
│       ├── models.py            # Foundation/Core + Reminder, ReminderDelivery
│       ├── backup.py            # SQLite snapshot, không ghi đè file đã có
│       ├── session.py           # async engine, transactions, PRAGMA, migrations
│       └── repositories/        # project/task/calendar owner scope + user/settings
├── alembic/                    # 0001 → 0002 Core → 0003 Reminders → 0004 Dispatch → 0005 Agent
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

Legacy Embed + View nối với các services CRUD. P4 thêm Reminder Engine/UI; P5 thêm AI DM qua Responses API, tools có validation, preview và nút duyệt bền vững. Worker dùng asyncio polling DB một process; dependencies AI là OpenAI SDK và JSON Schema validator.

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
AI_ENABLED=false
OPENAI_API_KEY=
OPENAI_MODEL=
AI_DAILY_TOKEN_LIMIT=100000
AI_DAILY_REQUEST_LIMIT=100
```

| Biến | Ý nghĩa |
|---|---|
| `DISCORD_TOKEN` | Bắt buộc: bot token thật thay placeholder; không phải Client Secret |
| `DISCORD_OWNER_ID` | Bắt buộc: Discord user ID dạng số của owner |
| `DATABASE_URL` | File SQLite qua `aiosqlite`; đường dẫn tương đối tính từ thư mục project, không dùng `:memory:` |
| `TIMEZONE` | Múi giờ IANA để khởi tạo owner mới; mặc định `Asia/Ho_Chi_Minh` |
| `LOG_LEVEL` | `INFO`, `WARNING`, `ERROR`, `CRITICAL`; mặc định `INFO` |
| `DISCORD_GUILD_ID` | Tùy chọn: đăng ký lệnh cho server riêng để kiểm thử; để trống thì sync global |
| `AI_ENABLED` | `true` để bật AI; tắt vẫn dùng CRUD/reminders |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | Key cục bộ và model hỗ trợ Responses function calling; cấu hình đang nghiệm thu dùng `gpt-6-luna` |
| `AI_DAILY_TOKEN_LIMIT` / `AI_DAILY_REQUEST_LIMIT` | Giới hạn API theo ngày UTC; usage chưa rõ giữ reservation bảo thủ |

Biến môi trường của process ưu tiên hơn `.env`. Chỉ AI cần OpenAI key/model và `AI_ENABLED=true`; không đưa key vào chat/Git. Settings đã lưu trong DB không bị ghi đè khi restart hay khi đổi `TIMEZONE` trong `.env`; đổi múi giờ đang dùng bằng **Settings → Sửa Timezone**. Automation P6 vẫn chưa kích hoạt. Giới hạn token không phải cam kết ngân sách tiền; xem Usage/budget tại tài khoản OpenAI.

```powershell
# Database cũ: dừng bot và backup theo phần Database bên dưới trước khi nâng cấp
# Máy mới: tạo schema trước khi kết nối Discord; không cần token để chạy migration
.\.venv\Scripts\python.exe -m alembic upgrade head

# Chạy bot; startup cũng tự áp dụng migration còn thiếu và khởi tạo owner/settings
.\.venv\Scripts\python.exe -m app.main
```

Khi kết nối thành công, log JSON có event `slash_commands_registered`, sau đó `bot_online`. Dừng bằng `Ctrl+C`. Bot bật reconnect khi mất Gateway và đóng async engine khi thoát.

Trong server, `/ping` trả `Pong! NOVA đang online.`; lần đầu `/menu` tạo/ghim **NOVA — PERSONAL CONTROL CENTER**, lưu message/channel ID và trả link kèm Home riêng tư có số liệu DB. Các lần sau dùng lại bảng neo. Bảng neo chỉ có điều hướng, không công khai thống kê/settings; buttons/select mở panel ephemeral. `/menu` trong DM mở Home riêng. DM owner dùng AI khi cấu hình sẵn; AI tắt/thiếu cấu hình thì bot hướng dẫn dùng menu.

## Chạy lại trên Linux

Nếu bot đang chạy, nhấn `Ctrl+C` trước. Dùng venv hiện có, giữ nguyên `.env` và database. Trước lần chạy source mới, backup và migrate theo [runbook 4B/4C](docs/PHASE_4BC_VALIDATION.md#backup-migrate-và-chạy-trên-máy-có-database-thật), vì startup sẽ tự upgrade schema:

```bash
.venv/bin/python -m app.main
```

Máy mới cần Python 3.12+, tạo venv và cài `requirements-dev.txt`. Head hiện tại là `0005_agent`; P5 có thêm dependency/env AI tùy chọn như trên. Startup đăng ký persistent dashboard/notification/AI approval callbacks; worker bắt đầu một lần khi bot ready và dừng trước khi đóng DB. Sau nâng cấp, mở `/menu` hoặc Refresh bảng neo, không tạo dashboard trùng.

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
- **Reminders → Thêm** nhập title, chọn ngày/giờ, một lần/daily/weekly, vị trí gửi và links task/event tùy chọn → **Lưu**. List 5 mục/trang, filter trạng thái, detail/lịch sử gửi, Sửa, Tạm dừng/Tiếp tục, Hủy, Back/Refresh. Sửa/hủy cần Duyệt. Notification có Đã làm, Hoãn 15 phút, Tắt; callbacks còn được nhận sau restart, backend kiểm tra owner/message/TTL.
- **Reminders → Cài đặt gửi** quản lý DM, kênh dự phòng và quiet hours theo timezone Settings, có xác nhận. Kênh phải là TextChannel riêng trên server do owner sở hữu; @everyone/role/thành viên khác không được xem, ngoại trừ managed role của bot. DM bị chặn chỉ fallback vào kênh đã duyệt; không tự chọn kênh khác.
- Home riêng hiển thị counts DB: Tasks không cancelled, Projects không archived, reminders active và lịch confirmed giao ngày local. Tiến độ project = done / task không cancelled. DB rỗng hiển thị 0/empty-state thật; module P6/P7 vẫn Sắp ra mắt. Bảng neo không công khai counts/settings.
- **AI Assistant** mở DM, Xóa ngữ cảnh và Sử dụng AI. Hỏi “Hôm nay có việc gì?”, “Tạo task học Docker”, “Nhắc tôi lúc 18h ngày mai”. Mọi write hiện dùng chế độ strict: xem đề xuất và bấm Duyệt; thiếu giờ thì hỏi lại. Đề xuất có TTL 15 phút, nút khôi phục sau restart, kiểm tra lại dữ liệu lúc duyệt; dời event cho chọn giữ giờ nhắc hoặc shift cùng event. Context RAM tối đa 20 messages/30 phút, mất khi restart; không có memory dài hạn P6.
- Settings sửa timezone IANA, ví dụ `Asia/Ho_Chi_Minh` hoặc `UTC`; notification preferences sửa tại Reminders. Language/briefing/review/planner chưa có automation P6.
- Panel riêng tư có thời hạn tối đa 10 phút; bản nháp và các bước chọn ngày/giờ giữ nguyên hạn của phiên, không gia hạn khi điều hướng. Modal tối đa 5 phút. Bảng neo không có timeout, các nút được đăng ký lại sau restart.
- Khi chuyển giữa mobile và web, mở lại module từ bảng neo để có panel riêng trên thiết bị đang dùng. Settings đã lưu dùng chung database; Refresh đọc lại giá trị mới.

P4 đã nghiệm thu theo xác nhận người dùng, lần gửi DM thật và acknowledgment trong DB; xem [báo cáo nghiệm thu](docs/PHASE_4_FINAL_CHECK.md). Checklist để kiểm tra hồi quy Desktop/Mobile, owner/non-owner, fallback và restart: [báo cáo 4B/4C](docs/PHASE_4BC_VALIDATION.md#checklist-live-còn-lại), cùng [hồi quy P3](docs/PHASE_3C_VALIDATION.md). Không ghi nhận từng biến thể đã chạy live nếu chỉ có test mock.

Worker poll 15 giây; tối đa 3 attempts, retry sau 1 và 5 phút; claim lease 2 phút. Quá hạn hơn 30 phút so với lịch hoặc retry due được ghi overdue, không gửi dồn. Quiet hours trì hoãn tới cuối khung giờ. Daily/weekly theo giờ local qua DST; snooze chỉ thêm occurrence hiện tại. Xem [policy đầy đủ](docs/PHASE_4BC_VALIDATION.md#chính-sách-worker). Không cam kết exactly-once khi Discord send và DB commit bị ngắt.

## Database và migration

SQLite dành cho một process local. 0001 tạo users/settings/audit; 0002 thêm Core; 0003 thêm reminders/deliveries; 0004 thêm 4 cột nullable cho retry/claim/ack; **0005** thêm pending_actions/agent_usage. Không rebuild bảng cũ. Startup tự migrate nên **dừng bot và backup DB cũ trước khi chạy source mới**. Giữ owner/settings/dashboard IDs; đổi config owner không được chiếm DB cũ.

Máy Windows hiện có `.env` cấu hình và `nova.db` mới do người dùng yêu cầu tạo; đã bootstrap đúng owner/settings và migrate head, không nhập hoặc xóa dữ liệu Linux. Preflight đã exit 0. Khi nâng cấp hoặc cài lại, xác định đúng DB theo [runbook](docs/PHASE_4BC_VALIDATION.md#backup-migrate-và-chạy-trên-máy-có-database-thật), backup trước rồi migrate/check. `.\.venv\Scripts\python.exe -m app.preflight` chỉ kiểm tra read-only và không in secret.

Nâng cấp trong PowerShell, tại thư mục project, sau khi đã dừng bot:

```powershell
$novaBackup = ".\backups\pre-phase-5-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".db"
.\.venv\Scripts\python.exe -m app.db.backup --output $novaBackup
if ($LASTEXITCODE -ne 0) { throw "Backup thất bại; dừng nâng cấp." }
.\.venv\Scripts\python.exe -m alembic current
if ($LASTEXITCODE -ne 0) { throw "Không đọc được revision; dừng." }
.\.venv\Scripts\python.exe -m alembic upgrade 0005_agent
if ($LASTEXITCODE -ne 0) { throw "Migration thất bại; chưa chạy bot. Xem hướng dẫn restore." }
.\.venv\Scripts\python.exe -m alembic check
if ($LASTEXITCODE -ne 0) { throw "Schema chưa khớp; chưa chạy bot." }
.\.venv\Scripts\python.exe -m alembic current
```

Revision sau nâng cấp: `0005_agent`. Backup dùng DATABASE_URL như bot, gồm WAL đã commit, kiểm tra integrity và không overwrite. Chỉ cài mới thực sự chưa có dữ liệu mới dùng `alembic upgrade head` tạo DB mới; không thay file dữ liệu cũ chưa tìm thấy bằng DB rỗng. Rollback/restore: [runbook P5](docs/PHASE_5_VALIDATION.md#rollback).

Mốc thời gian application luôn UTC-aware, SQLite chuẩn hóa UTC khi lưu và gắn UTC khi đọc; `tzdata` hỗ trợ Windows. Reminder worker gửi theo lịch active đã lưu; chưa có briefing/review/planner P6.

```powershell
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic check
```

Giữ nguyên DATABASE_URL/file DB, backup riêng tư (`backups/` bị gitignore), chỉ một process SQLite. Downgrade 0005 → 0004 bị từ chối nếu có proposal/usage history; ưu tiên tắt AI và giữ dữ liệu. Các downgrade P4/P3 cũng yêu cầu bảng tương ứng rỗng. Không xóa dữ liệu để ép rollback.

UI 3B/3C vẫn dùng approvals thủ công trong RAM 5 phút. P5 bổ sung durable pending_actions/executor riêng, không bỏ các gates UI cũ. Service kiểm tra owner trước session; updates có owner + expected version/timestamp, trả DTO sau commit. Chi tiết tại [báo cáo 3B](docs/PHASE_3B_VALIDATION.md) và [P5](docs/PHASE_5_VALIDATION.md).

## Kiểm thử tự động

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

Windows **Python 3.12.3: 687 passed in 40.45s**, lint/format/compile pass, là kết quả tự động gần nhất. Tests dùng SQLite tạm/mock Discord/OpenAI, chặn network. Nghiệm thu P5 riêng đã kiểm chứng OpenAI read tool thật, proposal create_task executed và audit success trong DB; owner xác nhận hoạt động. Lần chốt tài liệu không chạy lại tests. Các biến thể reschedule/bulk/expiry/restart/security có tests tự động, không tự ghi đã thử live riêng. Chi tiết: [báo cáo P5](docs/PHASE_5_VALIDATION.md); [nghiệm thu P4](docs/PHASE_4_FINAL_CHECK.md).

## Kiểm tra hồi quy Foundation

Người dùng đã xác nhận “Phase 1 DONE” ngày 2026-10-23. Giữ checklist dưới đây để kiểm tra lại khi thay đổi cấu hình hoặc môi trường chạy.

1. Chạy bot trong server riêng, kiểm tra log `bot_online`, chạy `/ping` bằng owner.
2. Chạy `/menu`, kiểm tra dashboard có các module và trạng thái rõ ràng, không có số liệu giả; panel của owner vẫn là ephemeral.
3. Dùng tài khoản khác chạy `/ping`, `/menu`: chỉ nhận thông báo không có quyền. Nhắn DM từ tài khoản đó: không được phục vụ. DM owner dùng AI nếu cấu hình sẵn, nếu tắt thì nhận hướng dẫn.
4. Sau backup/nâng cấp, restart bot, kiểm tra `/ping`, `/menu`, revision `0005_agent`, dữ liệu settings/dashboard và chỉ một worker. Persistence đã có integration tests.
5. Khi cần hồi quy, thử checklist 3C, 4B/4C và P5, ghi rõ kết quả thực tế. P5 đã nghiệm thu; không tự bắt đầu P6.

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
