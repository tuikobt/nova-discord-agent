# Phase 2 — Discord Dashboard UI: triển khai và kiểm thử

Ngày: **2026-10-23**. **Phase 2 — DONE** theo xác nhận “phase-2 Done” của người dùng. Kết quả tự động từ phiên triển khai: **159 tests pass**, lint/format pass. Phase 1 đã DONE; Phase 3 chưa bắt đầu.

Xác nhận nghiệm thu thực tế do người dùng cung cấp sau checklist Discord; Codex không tự đăng nhập Discord để kiểm chứng lại. Lần chốt nghiệm thu chỉ cập nhật README, ROADMAP, Discord UI và báo cáo này; không sửa source hoặc chạy lại bộ tests.

## Kết quả và phạm vi

- Legacy Embed + View, năm nút nhanh, select bảy module, Back/Refresh/Help/Settings.
- Home, Help và đủ 13 màn hình: Today, Tasks, Projects, Calendar, Reminders, AI Assistant, Goals, Finance, Habits, Notes, Memory, Reports, Settings.
- Không có fake counts; task/project/reminder stats và lịch hiển thị “Chưa có dữ liệu”. Backend chưa làm hiển thị “Sắp ra mắt”, chỉ có danh sách chức năng dự kiến.
- Settings đọc language/timezone/briefing/review/notification preference từ SQLite thật. Modal chỉ sửa timezone, backend validate IANA và commit trước khi báo lưu. Automation ghi “Chưa kích hoạt”; không có nút CRUD giả.
- Dashboard neo dùng lại ID đã lưu trong `user_settings`; persistent View đăng ký tại startup. Navigation mở panel ephemeral, không ghi đè bảng neo; các phiên có state riêng.
- Owner guard ở slash commands, View, từng callback button/select, modal check/submit, settings services và publisher. Custom IDs không có owner ID hoặc dữ liệu nhạy cảm.
- ACK/defer trước thao tác DB/Discord lâu; error panel có Back/Refresh, log chỉ class lỗi và interaction ID. Private panels có timeout 10 phút, modal 5 phút; view cũ được stop khi thay mới.
- Dùng lại schema/migration `0001_foundation`, giữ nguyên dependencies, config và dữ liệu Foundation. Không cần điền thêm biến `.env`.

## Cấu trúc

`domain/modules.py` là catalog màn hình và trạng thái; `domain/schemas.py` chứa DTO và phân trang. Repository đọc owner-scoped ORM records, SettingsService quản lý transaction đọc/lưu timezone/location, DashboardService tạo overview theo timezone đã lưu.

Discord controller điều phối response; renderers chỉ tạo Embed từ DTO; views chứa buttons/select/modal. Publisher chịu trách nhiệm tra cứu/tạo/ghim dashboard, lock chống gửi trùng và recovery. Services không import Discord.

Bảng neo không chứa timezone/locale/settings riêng tư. Home/Today trong panel riêng mới đọc và hiển thị ngày/múi giờ. Khi chưa có backend, không suy luận số 0 từ việc chưa có bảng task/project/reminder.

## Kết quả kiểm thử tự động

Kết quả từ phiên triển khai: Linux, **Python 3.12.15**, venv hiện có. Mốc trước triển khai: **65 passed in 2.23s**. Bộ cuối sau Phase 2:

| Lệnh | Kết quả |
|---|---|
| `.venv/bin/python -m pytest -q` | **159 passed in 2.33s**, exit 0 |
| `.venv/bin/python -m ruff check .` | **All checks passed!**, exit 0 |
| `.venv/bin/python -m ruff format --check .` | **55 files already formatted**, exit 0 |
| `.venv/bin/python -m compileall -q app tests alembic` | Pass, exit 0 |
| `git diff --check` | Pass, exit 0 |

Tests dùng mock Discord và chặn socket kết nối mạng; SQLite dùng file tạm. Pytest chạy ngoài sandbox vì socket nội bộ dùng để đánh thức asyncio bị sandbox chặn. Không khởi động bot thật, không in/log secrets và không đọc database cá nhân; các tests UI dùng settings giả lập và SQLite tạm. Chưa chạy PowerShell trên Windows.

Các test bao phủ:

- Home/settings/module rendering, giới hạn Embed, metrics unavailable, timezone qua ranh giới ngày, automation inactive.
- Từng screen/option, Back/Refresh, Previous/Next và page bounds, nguồn điều hướng public/private, state riêng theo View.
- Owner/non-owner ở cả dispatch guard và trực tiếp gọi callbacks; select giả mạo route bị từ chối.
- Modal mở không đợi DB, timezone hợp lệ/sai/hết hạn, service validate lại, lỗi commit không báo đã lưu.
- DB rỗng không giả lập settings; bootstrap thật tạo owner/settings; timezone và dashboard IDs còn sau engine restart.
- Ba `/menu` đồng thời chỉ gửi một bảng; restart dùng lại location, bảng bị xóa tạo lại, kênh bị xóa phục hồi tại kênh riêng hiện tại.
- Forbidden không bị hiểu thành NotFound, không ghi đè message khác, thiếu quyền ghim không tạo bảng trùng; retry sau DB commit lỗi và reconciliation marker.
- Integration dùng SQLite thật và hai `NovaClient` nối tiếp: startup đăng ký persistent View theo ID đã lưu và callback nút restored mở panel riêng tư mà không gọi Discord API.
- Panel/modal expiry, disable controls, lỗi HTTP/DB không lộ nội dung và có đường thử lại.

## Giới hạn vận hành

Chỉ một process bot + SQLite. `/menu` cần TextChannel có `@everyone` không được xem; owner kiểm tra các role/overwrites khác. Cần View Channel, Send Messages, Read Message History, Embed Links và Pin Messages; không cần Administrator.

Dashboard location cố định: gọi `/menu` ở kênh khác trả link về bảng đang dùng, không tự di chuyển/xóa bảng. Startup chỉ restore View; recovery bảng/kênh bị xóa chờ owner gọi `/menu`. Lỗi quyền/mạng không kích hoạt tự tạo bảng khác.

Discord send và DB commit không atomic: lock + message pending + tìm marker trong 50 message gần nhất giảm trùng khi retry/crash. Nếu orphan nằm ngoài cửa sổ đó vẫn có thể cần owner xử lý thủ công; không tự xóa message. Panel ephemeral cũ không được restore sau restart; mở panel mới từ bảng neo. Timeout disable message là best effort nếu token đã bị Discord từ chối.

Ghi chú đã giải thích khi nghiệm thu: bảng neo là tin nhắn dùng chung, còn panel riêng tư là ephemeral theo phiên. Khi chuyển mobile/web, mở lại module từ bảng neo trên thiết bị đang dùng. Settings đã lưu vẫn dùng chung SQLite; Refresh đọc lại dữ liệu mới. Lần chốt nghiệm thu giữ nguyên thiết kế này.

## Chạy và kiểm tra trên Discord

Checklist đã được người dùng xác nhận qua nghiệm thu Phase 2 ngày 2026-10-23; giữ lại để kiểm tra hồi quy khi thay đổi cấu hình hoặc môi trường.

1. Nếu bot cũ đang chạy, `Ctrl+C` để dừng. Giữ nguyên `.env` và SQLite. Trên máy Linux hiện tại chạy:

   ```bash
   .venv/bin/python -m app.main
   ```

   Windows PowerShell dùng `.\.venv\Scripts\python.exe -m app.main`. Dependencies không đổi. Chờ `slash_commands_registered` và `bot_online`. Nếu chưa có `/help`/`settings`, kiểm tra guild/global sync như README.

2. Chuẩn bị kênh văn bản riêng `#nova-dashboard`, chỉ owner/bot xem. Tắt View Channel của `@everyone`, kiểm tra các role khác. Cấp quyền đọc/gửi/embed/ghim cho bot.
3. Owner chạy `/menu`: thấy bảng neo và link phản hồi riêng tư. Gọi lại hai lần: vẫn một message. Nếu có thông báo chưa ghim, sửa Pin Messages hoặc ghim thủ công rồi gọi lại.
4. Kiểm tra bảng nút dưới đây trên cả Discord Desktop và Mobile. Dashboard neo phải giữ nguyên khi đi vào panel; chỉ Refresh trên chính bảng neo mới cập nhật bảng neo.

| Nút/menu | Kết quả cần thấy |
|---|---|
| Today | Ngày theo timezone đã lưu; lịch/việc chưa có backend, không báo lịch trống giả |
| Tasks | Panel Task Management “Sắp ra mắt”; có feature pages và Previous/Next, không có Create/Save task |
| Projects | Panel Project Management, mô tả và trạng thái Sắp ra mắt |
| Reminders | Panel Reminder Management, chưa tạo/gửi reminder |
| AI Assistant | Panel Sắp ra mắt, không tự gọi AI hoặc trả lời như AI đã hoạt động |
| Select → Calendar | Panel Calendar |
| Select → Goals | Panel Goals |
| Select → Finance | Panel Finance |
| Select → Habits | Panel Habits |
| Select → Notes | Panel Notes |
| Select → Memory | Panel Memory |
| Select → Reports | Panel Reports |
| Back | Home riêng tư, không sửa bảng neo |
| Refresh trong panel | Đọc lại đúng screen/page; không tạo message công khai |
| Help, `/help` | Hướng dẫn điều hướng, riêng tư, trạng thái chưa triển khai và hết phiên |
| Settings, `/settings` | Language, Timezone, Morning Briefing, Daily Review, Notification Preferences, Owner Access từ settings service |
| Sửa Timezone | Form có giá trị đã lưu; nhập `UTC`, submit, Refresh thấy `UTC`; nhập timezone sai bị từ chối, không ghi đè |
| Refresh trên bảng neo | Chỉ làm mới bảng neo, trả xác nhận ephemeral |

5. Restart bot, **bấm nút trên bảng neo cũ trước khi chạy `/menu` lại**: nút vẫn mở panel. Settings giữ timezone đã lưu. Mở panel mới; các panel riêng từ phiên cũ có thể hết hạn.
6. Kiểm tra tài khoản không phải owner: slash commands bị từ chối; trong kênh thử nghiệm được owner cấp quyền xem, button/select đều phải từ chối và không lộ settings. Các trường hợp modal được unit test trực tiếp, không chia sẻ token hoặc dữ liệu riêng tư để thử.
7. Chờ một panel hết hạn 10 phút: controls bị disable và có hướng dẫn mở lại; mở panel mới từ bảng neo. Modal hết hạn sau 5 phút, không lưu dữ liệu.
8. Owner chủ động xóa dashboard test rồi `/menu`: bot phục hồi một message mới. Nếu đổi quyền khiến bot không đọc được bảng cũ, `/menu` báo lỗi và không tạo thêm bảng.
9. Ghi kết quả Desktop/Mobile, owner/non-owner, modal/refresh và restart khi kiểm tra lại. P2 đã DONE theo xác nhận của người dùng; không cần gửi token vào chat.

## Đối chiếu nghiệm thu Phase 2

| Acceptance | Tự động | Kiểm tra thực tế |
|---|---|---|
| `/menu` mở module trên mobile và desktop | Rendering/routes/select/buttons pass | **Đạt theo xác nhận nghiệm thu của người dùng** |
| Owner-only trên button/select/modal | Dispatch + callback/service tests pass | **Đạt theo xác nhận nghiệm thu của người dùng** |
| Persistent dashboard sau restart | SQLite + hai client + restored callback pass | **Đạt theo xác nhận nghiệm thu của người dùng** |
| Chưa có backend ghi Sắp ra mắt, không fake data | Availability/rendering tests pass | **Đạt theo xác nhận nghiệm thu của người dùng** |
| Error/hết hạn interaction rõ ràng | DB/HTTP/modal/panel timeout tests pass | **Đạt theo xác nhận nghiệm thu của người dùng** |

**P2 DONE (2026-10-23)** theo kết quả tự động và xác nhận nghiệm thu của người dùng. P3 vẫn **NOT STARTED**.

## File tạo mới và sửa trong Phase 2

File mới:

```text
app/domain/modules.py
app/domain/schemas.py
app/db/repositories/settings_repository.py
app/services/dashboard_service.py
app/discord_bot/dashboard_controller.py
app/discord_bot/dashboard_publisher.py
app/discord_bot/views/__init__.py
app/discord_bot/views/dashboard.py
tests/test_dashboard_rendering.py
tests/test_dashboard_ui.py
tests/test_dashboard_publisher.py
tests/test_settings_service.py
docs/PHASE_2_VALIDATION.md
```

File sửa:

```text
app/discord_bot/client.py
app/discord_bot/commands/foundation.py
app/discord_bot/renderers/dashboard.py
app/services/settings_service.py
tests/conftest.py
tests/test_commands.py
tests/test_client.py
pyproject.toml
README.md
docs/DISCORD_UI.md
docs/ROADMAP.md
docs/PHASE_1_VALIDATION.md
```

Không thay đổi token/env, models/schema, dependency pins hoặc dữ liệu cá nhân. Không tự chuyển/reset nhánh hoặc commit các thay đổi của người dùng; nhánh hiện tại khi kiểm tra cuối là `feat/phase-2`.

## Chưa triển khai

OpenAI/AI Agent, Task/Project/Calendar CRUD, Reminder Scheduler, Personal Memory backend, Finance Management, integrations và web frontend. Không tự chuyển Phase 3.

Tham chiếu triển khai: [persistent View example chính thức của discord.py](https://github.com/Rapptz/discord.py/blob/master/examples/views/persistent.py), [Interactions API và quyền pin](https://discordpy.readthedocs.io/en/stable/interactions/api.html).
