# Phase 3C — Discord CRUD UI: triển khai và kiểm thử

Ngày: **2026-10-23**. Source 3C và kiểm thử tự động hoàn tất, đã rà soát form theo phản hồi người dùng: **419 passed in 8.32s**. **Chưa nghiệm thu Discord Desktop/Mobile, chưa đánh dấu toàn Phase 3 DONE.** Không bắt đầu P4/P5.

## Phạm vi và repository

- Bắt đầu từ nhánh sạch `feat/phase-3`, đã có 3A/3B và 340 tests. Đã đọc AGENTS, tài liệu thiết kế/roadmap/security/handoff cùng API, source và tests hiện có.
- Nối services 3B vào bot lifecycle và adapter hiện có; giữ modular monolith, legacy Embed + View, không web frontend.
- Không sửa ORM, migrations, schema, dependencies, `.env` hoặc database thật. Revision vẫn **0002_core_management**. Không chạy bot, Discord API thật hay PowerShell Windows trong phiên này.
- CRUD dùng archive/cancel theo handoff, không hard-delete, không cascade xóa tasks/events.
- Không có reminder scheduler, AI inference, finance/habits/goals hoặc integration.
- Bản đầu 3C đạt 388 tests. Theo phản hồi form bắt gõ ngày giờ/có-không, thay bằng draft + legacy selectors, thêm 31 tests. Giữ các thay đổi đang có trong Git; không reset/stage/commit lại.

## Hành vi đã triển khai

### Dashboard và Today

`/menu` trong server vẫn tạo/tái sử dụng bảng neo theo lifecycle P2, trả link cùng Home ephemeral riêng của owner. Bảng neo chỉ điều hướng/module availability, không có counts/settings/nội dung cá nhân. Root custom IDs v1 giữ nguyên và đăng ký lại sau restart; không tự gửi bảng mới khi startup.

Home private đọc số liệu thật qua SummaryService/DashboardRepository theo owner:

- Tasks: mọi trạng thái trừ cancelled; tasks done là tập con của số này.
- Projects: trừ archived.
- Calendar hôm nay: confirmed events giao với khoảng ngày theo timezone đã lưu.
- Reminders không có backend, giữ Sắp ra mắt, không đưa số 0 vào như đã đo.

Today có tối đa 5 lịch confirmed giao ngày local và 5 task todo/doing đến hạn/quá hạn hoặc priority high/critical, kèm tổng thật. Có chọn mục để xem chi tiết, Thêm task/Thêm lịch và mở danh sách đầy đủ. Backend query/sắp xếp nằm trong repository/service, không SQL trong Discord adapter.

### Projects

- Thêm/Sửa: modal tên, mô tả tối đa 4000 ký tự → bản nháp chọn deadline/trạng thái → Lưu. Deadline tùy chọn, có nút bỏ deadline.
- Danh sách 5 mục/trang, chọn chi tiết, lọc trạng thái, Back/Refresh.
- Status active/paused/completed; archived cần xác nhận, có thể đổi lại active. Không tự cập nhật status các task.
- Progress = done / task không cancelled, tính theo số lượng. Empty project có 0% — Chưa có nhiệm vụ. Mô tả cách tính hiện trong list/detail.
- Chi tiết có Xem tasks và Thêm task; task mới gắn project sẵn, Back giữ danh sách theo project.

### Tasks

- Thêm/Sửa: modal title/description → bản nháp chọn due_at, estimated_minutes, priority, project → Lưu. Deadline và ước tính tùy chọn. Status/priority ở chi tiết vẫn dùng select có nhãn tiếng Việt; không cần nhớ enum hoặc lệnh con.
- Hoàn thành/Mở lại gọi backend có expected version; completed_at được service quản lý. Đổi/hủy task không tự đổi CalendarEvent liên kết.
- Đổi dự án dùng picker phân trang, có lựa chọn bỏ liên kết; backend kiểm tra owner lại, không nhập ID thủ công.
- List lọc status, priority, project và khoảng deadline. Khoảng ngày chọn bằng picker Từ ngày/Đến hết ngày, có Hôm nay/7 ngày tới và xóa từng mốc; ngày cuối được bao gồm bằng mốc cuối exclusive của ngày kế tiếp trong timezone của bản nháp. Chỉ Áp dụng mới thay bộ lọc.
- Lên lịch từ task mở form Calendar có sẵn title/task link, không gửi thông báo nhắc việc.

### Calendar

- Modal chỉ nhập title → bản nháp chọn start/end bằng ngày/giờ picker, hoặc chọn thời lượng sau khi chọn start. is_fixed là select Cố định/Linh hoạt; task liên kết cũng chọn trước khi lưu. Không còn TextInput có/không. Chỉ Lưu mới gọi backend; không tự lấy giờ gợi ý làm giờ đã chọn.
- Tạo thủ công mặc định confirmed qua backend conflict check. Có thể đổi status, cố định/linh hoạt và task liên kết ở chi tiết.
- Xem ngày/tuần, chọn ngày và dịch cửa sổ ngày/tuần trước/sau; list có filter status và phân trang. Event giao cửa sổ ngày vẫn được hiển thị nếu bắt đầu ở ngày trước.
- `ends_at > starts_at` và overlap `[start,end)` do service kiểm tra; hai đầu tiếp giáp không trùng. Không tự sửa/xóa/dời event khác.
- Sau tạo mới, Back về danh sách ngày chứa start đã nhập. Sửa event confirmed hoặc hủy event phải xem/duyệt trước.

## Forms, confirmations và vòng đời

Forms dùng tối đa **4 TextInputs**, không trộn Components V2. Giới hạn inputs, embed fields, tổng embed và rows được kiểm tra qua SDK/tests; cơ chế API đối chiếu [discord.py Interactions API](https://discordpy.readthedocs.io/en/stable/interactions/api.html).

- Form thường chỉ nhập tên/mô tả, không ép nhập datetime, estimated_minutes hoặc boolean. Trả về preview có nhãn Bản nháp chưa lưu, sau đó chọn các giá trị và bấm Lưu. Bỏ bản nháp không ghi DB; các sửa đổi trên picker chưa được dùng thì Quay lại sẽ bỏ.
- DatePicker dùng Embed lịch tháng (T2–CN), nút tháng trước/sau/Hôm nay, hai select ngày 01–16 và 17–cuối tháng; giờ có 24 lựa chọn, phút bước 5 phút. Giữ thêm phút gốc nếu không chia hết cho 5 để không làm tròn dữ liệu khi sửa. Dùng ngày giờ mới gán vào draft; chưa gọi create/update. Bộ chọn ngày xem lịch và lọc deadline chỉ có ngày, thêm Ngày mai. Mỗi select có custom_id riêng, tối đa 25 options; message tối đa 5 hàng.
- Muốn ngày xa hoặc phút bất kỳ, dùng Nhập ngày/giờ chính xác. Task dùng Nhập ngày/giờ, số phút cho ước tính khác mức có sẵn. Form nâng cao dùng `YYYY-MM-DD HH:MM`, hiển thị timezone, sửa lỗi giữ nguyên dữ liệu nhập. Legacy Embed + View giữ kiến trúc đã chốt; đối chiếu [Discord Component Reference](https://docs.discord.com/developers/components/reference#legacy-message-component-behavior).
- Bản nháp tối đa 10 phút (không vượt panel nguồn), form tối đa 5 phút. Chọn ngày/menu hoặc sửa text không gia hạn draft; restart thì mất bản nháp chưa lưu. Một lock chung tuần tự hóa modal/select/Lưu của cùng draft; thao tác đến muộn sau khi lưu/thay view bị từ chối trước sửa payload.
- Form mới có request_id riêng; retry/duplicate submit cùng form giữ nguyên key để backend không tạo lặp.
- Form sửa giữ immutable snapshot cùng version/updated_at. DTO thay thế toàn phần được dựng từ snapshot, chỉ đổi các trường có trên form; không vô tình reset status/priority/links. Datetime không chỉnh sửa giữ cả seconds/microseconds.
- Timezone được chụp khi mở form. Form tối đa 5 phút và không lâu hơn panel nguồn; source bị thay thế thì form cũ bị từ chối.
- Input sai trả lỗi an toàn và Nhập lại với giá trị đã nhập; không ghi DB trước validation. Lỗi storage có Thử lại cùng intent/key; stale version/token cần Refresh và xem lại.
- Các thao tác nhạy cảm và overlap nhận pending request từ service, hiển thị before/after cùng tất cả conflicts. Nội dung dài được chia trang; Duyệt bị disable ở mọi trang trừ cuối, callback cũng chặn gọi duyệt sớm.
- Chỉ nút Duyệt mới gửi token cùng đúng payload/expected snapshot về service. Bỏ qua không ghi và vô hiệu token; backend kiểm tra owner/TTL/versions/conflicts lại. Token nằm trong bộ nhớ, không trong embed/custom_id/logs.
- Confirmation tối đa 5 phút, paging không kéo dài expiry backend. Restart mất approvals và private panels; owner phải mở lại từ bảng neo và duyệt lại.
- Panel riêng tối đa 10 phút, khi điều hướng thay view thì stop view cũ. Callback trực tiếp cũng kiểm tra owner/expiry/is_finished; không chia sẻ current screen/page giữa sessions.
- Service trả kết quả sau commit mới hiển thị Đã lưu. Nếu Discord render lỗi sau commit, intent ghi nhận đã lưu, phản hồi hướng dẫn mở lại/Refresh và không submit mutation lần nữa. Delivery/disable controls vẫn phụ thuộc Discord/network như P2.

Mọi nội dung record đều ở panel riêng tư, escape markdown/mentions và không có mentions được gửi. Description quá dài ở detail được rút gọn có nhãn mở Sửa để xem đủ; confirmation không rút gọn nội dung thay đổi, dùng nhiều trang. Today là preview có tổng số và đường mở module đầy đủ.

## Kết quả kiểm thử

Môi trường: Linux, Python **3.12.15**, dependencies hiện có. Baseline 3B: **340 passed in 5.93s**. Bản 3C đầu: **388 passed in 7.98s**. Kết quả sau rà soát UX:

| Lệnh | Kết quả |
|---|---|
| `.venv/bin/python -m pytest -q` | **419 passed in 8.32s** |
| `.venv/bin/python -m ruff check .` | Pass |
| `.venv/bin/python -m ruff format --check .` | Pass |
| `.venv/bin/python -m compileall -q app alembic tests` | Pass |
| `git diff --check` | Pass |

Có **83 tests mới** trong bốn file UI/metrics (52 bản đầu + 31 picker/draft). Bốn test tham số placeholder core P2 được thay bằng bốn test module sẵn sàng trên SQLite thật, nên tổng tăng ròng 79 so với 3B. Hồi quy Foundation, dashboard lifecycle/auth, migration/constraints và services 3A/3B vẫn đạt. Mock Discord, SQLite file tạm, chặn network; pytest chạy ngoài sandbox vì giới hạn asyncio/socket nội bộ.

Các trường hợp quan trọng đã kiểm tra:

- Tạo project → thêm task gắn project → đổi priority → done/reopen → tạo event liên kết qua callbacks/modal/select thực với Discord API được mock.
- Sửa nullable fields, giữ trường không chỉnh sửa/time precision; chọn/xóa links không cần nhập ID.
- List/status/priority/project/deadline filter, paging và Back giữ ngữ cảnh; lịch ngày/tuần theo local timezone.
- Archive/cancel và sửa lịch confirmed không ghi trước duyệt; Bỏ qua không ghi, duplicate Duyệt không ghi lần hai.
- Overlap có cảnh báo, sát biên không overlap, conflict mới làm token cũ bị từ chối.
- Many-conflicts paging, token không xuất hiện trong custom_id/embed, chỉ trang cuối mới duyệt được.
- 13 trường hợp callback/controller mới từ chối non-owner trước DB; summary cũng có owner guard, metrics/today không tính record owner khác.
- Form/panel bị thay thế hoặc hết hạn không ghi; token hết hạn backend dù UI chưa hết timer vẫn bị chặn.
- Invalid input sửa lại được; stale snapshot không overwrite; storage retry dùng cùng request_id; Discord lỗi sau commit và duplicate modal không tạo thêm record.
- Embed/field/row/input limits, escape nội dung, empty-state và counts thật, không fake zero cho module chưa có.
- Đóng/tạo lại NovaClient trên cùng SQLite, mocked sync; root IDs cũ khôi phục và mở được persisted task qua button cũ, không sửa bảng neo khi thao tác private.
- Picker thật qua callbacks: tạo project/task/event, date/priority/estimate/fixed/link select, bỏ deadline, hủy chọn/hủy draft, Save/Duyệt riêng và range ngày cuối inclusive. Tháng 31 ngày sang tháng ngắn, năm nhuận, qua năm, DST không tồn tại/mơ hồ; nhập chính xác phút 17 và giữ seconds/microseconds.
- Mỗi loại view draft/date/range/link từ chối non-owner, expiry và view đã thay. Chặn select giả, unique custom IDs, component/embed limits và không kéo dài TTL. Modal/select đến trong lúc save đang chờ DB không đổi snapshot được lưu.

## Cách chạy source mới

1. Dừng phiên bot đang chạy bằng Ctrl+C. Giữ `.env` và database. Không chạy hai process bot cùng SQLite/token.
2. 3C không có dependency, biến `.env` hay migration mới. Nếu DB đã ở 0002, chỉ cần chạy lại source. Nếu chưa áp dụng 3A, làm [backup/migration runbook 3A](PHASE_3A_VALIDATION.md#migration-và-khôi-phục) trước: startup vẫn tự upgrade head, không xóa/reset DB.
3. Linux tại project root:

   ```bash
   .venv/bin/python -m app.main
   ```

   Windows PowerShell:

   ```powershell
   .\.venv\Scripts\python.exe -m app.main
   ```

4. Mở `/menu` trong kênh riêng. Bảng neo hiện có được dùng lại và cập nhật nhãn; Home riêng có counts thật. Có thể dùng buttons trên bảng neo để mở Tasks/Projects/Calendar/Today. Mở panel/form mới sau restart, không tiếp tục form cũ trước lần sửa UI.

Không cần token/API key mới. Không gửi token hoặc DB riêng tư vào chat để nghiệm thu.

## Checklist nghiệm thu Discord thực tế

**Chưa chạy các bước này trong phiên Codex.** Thử trên cả Desktop/Web và Mobile bằng tài khoản owner; các dữ liệu thử nên đặt tên rõ như “Test nghiệm thu P3”. Các thao tác sau sẽ tạo/sửa dữ liệu thật khi chính owner bấm lưu.

1. `/ping`, `/menu`, Help, Settings hoạt động; `/menu` lặp lại vẫn cùng bảng neo, Home ephemeral có counts DB. Module chưa xây vẫn Sắp ra mắt, không có số liệu giả.
2. Projects → Thêm tên/mô tả → bản nháp → Chọn deadline bằng menu → chọn status → Lưu. Trước Lưu chưa có record. Chọn detail, sửa tên/status/deadline, Refresh. Xem 0%/Chưa có nhiệm vụ lúc project mới.
3. Trong project → Thêm task hai lần cho hai task khác nhau. Mỗi lần nhập tiêu đề/mô tả rồi chọn deadline, ưu tiên, ước tính qua menu, kiểm tra dự án đã gắn, Lưu. Hoàn thành một task, kiểm tra 1/2 = 50%; mở lại rồi kiểm tra progress. Mở form sửa không làm mất trường khác.
4. Tasks → Dự án chọn project, thử status/priority/deadline filters và Previous/Next khi >5 mục. Deadline → chọn Từ ngày/Đến hết ngày/Áp dụng, thử Hôm nay/7 ngày tới/xóa mốc/Quay lại. Chọn task, Đổi dự án/bỏ liên kết, Back giữ filters/context. Hủy task cần Duyệt; Bỏ qua giữ nguyên dữ liệu.
5. Calendar → Chọn ngày bằng menu, Xem ngày/tuần. Thêm chỉ nhập tên; bản nháp → Chọn bắt đầu, chọn ngày/20 giờ/00 phút, Dùng ngày giờ → thời lượng 60 phút hoặc Chọn kết thúc 21:00 → select Cố định/Linh hoạt → Lưu. Kiểm tra timezone, task link, Today. Thử đổi tháng cuối tháng/năm nhuận; Quay lại không áp dụng lựa chọn, Bỏ bản nháp không tạo record. Task → Lên lịch có sẵn title/task link.
6. Tạo event 20:30–21:30 cùng ngày: thấy conflict, chọn Bỏ qua → không thêm record. Làm lại và Duyệt → thêm đúng một event, giữ event cũ. Với chỉ event 20:00–21:00, tạo 21:00–22:00 không cảnh báo overlap. Nếu có event khác đến 21:30 thì cảnh báo là đúng.
7. Sửa giờ/title/is_fixed của event confirmed, đổi task hoặc hủy: phải thấy before/after; trước duyệt dữ liệu không đổi. Thử Bỏ qua rồi làm lại/Duyệt. Nếu nhiều trang, xem đến cuối mới duyệt.
8. Bản nháp Calendar chưa chọn giờ không Lưu được. Thử end<=start, title rỗng; trong Nhập ngày/giờ chính xác thử `10/11`, và task Nhập ngày/giờ, số phút thử số phút<=0: có hướng dẫn sửa, giữ input. Nhập phút 17 để kiểm tra đường chính xác tùy chọn. Form/approval hết hạn hoặc dữ liệu đổi ở panel khác phải Refresh/xem lại; không ghi đè âm thầm.
9. Thử double submit/click, mở hai panel, chuyển giữa mobile/web: mỗi panel riêng, dùng Refresh để thấy DB mới. Chỉ dữ liệu đã lưu dùng chung; không kỳ vọng cùng ephemeral message xuất hiện trên hai thiết bị.
10. Non-owner chạy slash commands bị từ chối. Trong kênh thử có quyền xem bảng neo, non-owner bấm button/select phải bị chặn, không thấy counts hoặc records. Private server/channel ACL vẫn cần cấu hình đúng; không mở quyền kênh dữ liệu thật chỉ để thử.
11. Restart bot, bấm button của bảng neo cũ: còn dùng được, không nhân đôi bảng. Tasks/projects/events/settings còn nguyên. Panel/form/approval cũ không restore, mở lại từ bảng neo.
12. Kiểm tra counts/progress sau thao tác và sau restart. Ghi nhận kết quả Desktop/Mobile, owner/non-owner, timezone, overlap và restart trước khi xác nhận Phase 3 DONE.

## Đối chiếu acceptance Phase 3

| Tiêu chí | Tự động | Thực tế |
|---|---|---|
| Owner CRUD task/project/event qua UI | Mock interactions + SQLite pass | Chờ Desktop/Mobile |
| Restart giữ data và persistent dashboard | Hai clients trên cùng SQLite + restored callback pass | Chờ restart bot thật |
| Owner isolation và same-owner references | Callback/controller/service/SQL tests pass | Chờ non-owner thử |
| Overlap cảnh báo, duyệt trước khi giữ trùng | UI và backend tests pass | Chờ thao tác Discord |
| Counts/progress/empty-state đọc DB | Scoped metrics + UI tests pass | Chờ đối chiếu giao diện |
| UTC/local timezone và input validation | Round-trip/DST/strict parsing/UI tests pass | Chờ kiểm tra giờ hiển thị |

**Chưa đánh dấu P3/3C DONE.** Chờ người dùng xác nhận checklist thực tế; không tự chuyển P4.

## File tạo/sửa

Tạo **14 file**:

- `app/db/repositories/dashboard_repository.py`.
- `app/services/core_management.py`.
- `app/discord_bot/core_controller.py`, `app/discord_bot/core_state.py`.
- `app/discord_bot/form_controller.py`.
- `app/discord_bot/renderers/core.py`.
- `app/discord_bot/views/core.py`, `app/discord_bot/views/core_forms.py`.
- `app/discord_bot/views/core_pickers.py`.
- `tests/test_core_discord.py`, `tests/test_core_discord_security.py`, `tests/test_dashboard_metrics.py`.
- `tests/test_core_pickers.py`.
- `docs/PHASE_3C_VALIDATION.md`.

Sửa **16 file**:

- `app/discord_bot/client.py`, `app/discord_bot/dashboard_controller.py`.
- `app/discord_bot/renderers/dashboard.py`, `app/discord_bot/views/dashboard.py`.
- `app/domain/modules.py`, `app/domain/schemas.py`.
- `app/services/calendar_service.py`, `app/services/dashboard_service.py`.
- `tests/conftest.py`, `tests/test_dashboard_ui.py`, `tests/test_dashboard_rendering.py`, `tests/test_dashboard_publisher.py`.
- `README.md`, `docs/ROADMAP.md`, `docs/DATABASE.md`, `docs/DISCORD_UI.md`.

Không sửa DB thật/models/migrations/secrets. Không commit/push, deploy hoặc bắt đầu phase mới trong lần bàn giao này.
