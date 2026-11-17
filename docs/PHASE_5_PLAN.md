# Phase 5 — Kế hoạch triển khai theo luồng dọc

Trạng thái 2026-11-18: **P5 DONE**, owner xác nhận hoạt động. Bộ gần nhất 687 tests
đạt; database thật ở `0005_agent`, bot online với AI `gpt-6-luna`. Đã có read tool
OpenAI thật và create_task executed/audit success trong DB. Không suy ra các biến thể
khác đã thử live riêng. Chi tiết: [PHASE_5_VALIDATION.md](PHASE_5_VALIDATION.md).
Phạm vi: AI Agent theo ROADMAP, dừng sau P5.

## 1. Nền triển khai đã kiểm tra

Các mục nền dưới đây là lịch sử lúc lập kế hoạch. Khi triển khai, workspace đã ở
`feat/phase-5` trên `944d807`, fetch origin thành công, baseline chạy lại 625 pass.
Policy bản đầu đã chọn strict: mọi write L1/L2 đều cần preview và click Duyệt.
Hành vi reminder keep/shift đã thống nhất trong DATABASE/ARCHITECTURE trước migration.

- Working tree đang ở `main`, commit `856ad21` (Phase 2), sạch trước khi thêm tài liệu này; chậm `origin/main` 6 commit theo refs cục bộ.
- `feat/phase-4` ở `0173bdf`, có services P3/P4 và migrations tới `0004_reminder_dispatch`.
- `origin/main` ở `944d807`, đã merge Phase 4. Đây là thông tin refs hiện có, chưa fetch lại remote.
- ROADMAP trên nhánh P4 ghi P4 DONE, 625 tests ở lần nghiệm thu trước; P3 vẫn ghi tự động đạt, chưa xác minh live riêng. Không sửa lịch sử nghiệm thu này.
- Chưa chạy lại tests, chưa đọc secret, chưa đổi nhánh, chưa thay database trong lần lập kế hoạch.

Trước triển khai: fetch, kiểm tra diff, tạo nhánh P5 từ bản main có P4; giữ tài liệu này và mọi thay đổi của người dùng. Không triển khai trên source P2 và không dùng reset để thay nền code. Chạy lại baseline, preflight và migration check bằng đúng bản P4. Nếu baseline lỗi, xử lý và báo rõ trước khi thêm AI.

## 2. Đầu ra và giới hạn

Owner nhắn tiếng Việt qua DM để đọc dữ liệu thật, tạo task/reminder, hoàn thành task, tạo event rõ ràng; thay đổi lịch và cập nhật hàng loạt phải có preview và nút duyệt. UI CRUD và reminder worker hoạt động khi AI tắt hoặc API lỗi.

Không làm memory dài hạn, planner tự động, morning briefing/reports, Google/Gmail, finance, voice, website hoặc multi-user. `suggest_next_action` chỉ gợi ý khi owner hỏi từ dữ liệu hiện có, không thành automation P6.

Mỗi checkpoint đi đủ luồng: Discord → xác thực → agent/tool → service → DB → kết quả Discord, với tests tương ứng; không xây xong toàn bộ backend rồi mới nối UI.

## 3. Checkpoints

### 5A — DM tra cứu dữ liệu thật

- Cấu hình AI bật/tắt; `OPENAI_API_KEY`, `OPENAI_MODEL` chỉ cấu hình cục bộ. Thiếu cấu hình AI không ngăn bot CRUD khởi động.
- Adapter bất đồng bộ cho Responses API, model cấu hình được, timeout/cancel, giới hạn input/output và vòng tool ngay từ đầu. Đối chiếu tài liệu OpenAI/Discord chính thức và pin SDK tương thích khi triển khai; không chốt tên model/giá từ trí nhớ.
- Owner guard trước khi đọc nội dung DM/gọi model; bỏ qua server messages và bot messages. Tuần tự hóa turn của owner để tránh đảo ngữ cảnh.
- Registry allowlist và validation backend; model không truyền owner, SQL, shell, URL tùy ý hay approval token.
- Tools đọc: `get_today_overview`, `list_tasks`, `get_task`, `list_projects`, `list_events`, `find_free_slots`, `list_reminders`, `get_preferences` (chỉ keys cho phép), `suggest_next_action`.
- Context ngắn trong RAM, đề xuất tối đa 10 lượt/30 phút, có thao tác xóa context; mất context khi restart được thông báo. Không lưu raw chat mặc định. Không cache số liệu DB qua lượt ghi.
- Mở panel AI với đường vào DM, trạng thái bật/tắt và câu hỏi gợi ý. Trả lời rỗng/không tìm thấy trung thực; kết quả có ngày giờ và nguồn bản ghi khi phù hợp.
- Nghiệm thu: “Hôm nay có việc gì?”, “Mai có lịch gì?” chỉ đọc đúng ngày local; tài khoản khác không gọi được API/tools; API lỗi vẫn dùng menu và reminder bình thường.

### 5B — Tạo và hoàn thành việc qua hội thoại

- Tools `create_task`, `complete_task`, `create_reminder`, `create_calendar_event` dùng services thật; single write chỉ khi yêu cầu rõ. Không suy diễn mô tả task thành lệnh mới của owner.
- Backend giữ trạng thái yêu cầu/clarification của turn, kiểm tra schema và quyền; không tin trường “user đã đồng ý” do model tự khai. Khi chưa chứng minh được ý định rõ thì hỏi lại hoặc dùng preview xác nhận.
- “Mai nhắc tôi làm bài” hỏi giờ; “thứ Sáu” mơ hồ hỏi ngày; nhiều task cùng tên cho chọn bản ghi. Đổi local sang UTC bằng clock/timezone backend, không chỉ tin timestamp model.
- Reminder hỗ trợ none/daily/weekly và các ràng buộc P4; target mặc định DM, channel phải qua cấu hình private đã được duyệt.
- Idempotency bền vững gắn message/turn và hành động đã chuẩn hóa; retry tool, duplicate Gateway event hoặc restart không tạo hai bản ghi. Cho phép hai yêu cầu chủ ý riêng biệt có cùng nội dung.
- Biên nhận thành công xuất phát từ kết quả service đã commit. Nếu model hoặc Discord lỗi sau commit, lấy lại biên nhận, không thực thi lại write.
- Event mới trùng lịch chuyển sang xác nhận; không dùng cờ model để bỏ qua conflict. Tái sử dụng quy tắc P3, không bypass approvals hiện có.
- Nghiệm thu: tạo task, hoàn thành đúng task, tạo reminder và nhận DM; thiếu giờ không ghi; duplicate/retry không nhân đôi.

### 5C — Đề xuất thay đổi và duyệt bền vững

- Migration bổ sung `pending_actions`, storage idempotency/usage cần thiết; tận dụng `audit_logs` hiện có. Chốt schema trong DATABASE trước migration, không sửa migration cũ.
- `propose_reschedule` và `propose_bulk_task_update` chỉ lưu đề xuất; preview trước/sau và tất cả đối tượng ảnh hưởng; owner bấm Duyệt/Hủy.
- Pending TTL đề xuất 15 phút, ID ngẫu nhiên, owner/payload/version/message binding. Kiểm tra lại quyền, trạng thái, version, hết hạn và conflicts tại lúc duyệt; stale yêu cầu tạo đề xuất mới.
- Thay đổi tất cả bản ghi, audit và trạng thái executed trong cùng transaction; không gọi nhiều service tự commit rồi để bulk thành công một phần. Refactor transaction boundary có tests hồi quy, giữ nguyên quyền của UI cũ.
- Nút xác nhận hoạt động sau restart; double click chỉ một lần execution; model không có tool approve. Không tự duyệt event cố định hoặc override conflict.
- **Điểm cần chốt trước khi viết phần reschedule:** ARCHITECTURE/DATABASE mô tả cập nhật reminder liên kết, còn P4 thực tế giữ giờ tuyệt đối, chưa có offset. Tạm dừng code dời lịch liên quan tới khi thống nhất tài liệu. Đề xuất: preview liệt kê reminder bị ảnh hưởng, owner chọn giữ giờ tuyệt đối hoặc dời cùng độ lệch event; không âm thầm suy ra offset. Khi đổi reminder, kiểm tra updated_at, delivery pending/claimed/sent và dùng khóa chung với worker; không viết lại lịch sử đã gửi. Nếu đang gửi, từ chối và yêu cầu làm mới.
- Nghiệm thu: “Dời toàn bộ lịch chiều nay…” không đổi DB nghiệp vụ trước duyệt; hủy/hết hạn/stale/non-owner không ghi; approve cập nhật nguyên tử và không để reminder cũ gửi nhầm.

### 5D — Chi phí, lỗi và nghiệm thu toàn Phase 5

- Giới hạn khởi điểm đề xuất: 4.000 ký tự input, 4 vòng model/turn, 8 tool calls/turn, timeout toàn turn 60 giây; cấu hình và kiểm thử, điều chỉnh theo trải nghiệm thực tế.
- Theo dõi tokens/request/model, budget ngày và rate limit owner; reserve ngân sách trước request, reconcile usage sau trả lời. Requests lỗi/usage chưa biết xử lý bảo thủ, không mặc định miễn phí. Giá và model phải cấu hình/đối chiếu nguồn hiện hành, không báo chi phí chính xác khi thiếu giá.
- Chạm giới hạn dừng AI với thông báo rõ; timeout/429/5xx retry hữu hạn, không replay write. Không tự chọn model đắt hơn khi lỗi.
- Injection trong mô tả task, tool output hoặc nội dung hội thoại không mở thêm quyền; hạn chế context tới bản ghi cần thiết. Logs chỉ metadata, không raw chat/tool payload/secrets.
- Test đầy đủ P1–P5, migration/restore, restart, lỗi API/DB/Discord và cạnh tranh với scheduler. Tất cả tests tự động mock OpenAI/Discord, không chi tiền API.
- Live smoke test có cấu hình API hợp lệ: hỏi dữ liệu thật, tạo task, tạo reminder, thiếu giờ phải hỏi, đề xuất đổi lịch rồi Hủy/Duyệt, restart pending, tắt AI vẫn CRUD/nhắc được. Ghi riêng bằng chứng mock và live; không tự ghi đã test những tình huống chưa thử.
- Chỉ cập nhật README/ROADMAP P5 DONE sau acceptance và owner nghiệm thu; tạo báo cáo file thay đổi, lệnh tests, kết quả, hạn chế và rollback. Dừng, không tự bắt đầu P6.

## 4. Nhóm file dự kiến

| Nhóm | File/thư mục |
|---|---|
| AI | `app/agent/{client,orchestrator,context,tool_registry,policy,schemas,usage}.py`, `app/agent/prompts/` |
| Discord | `app/discord_bot/client.py`, controller/view/renderers AI và confirmations; dashboard/help/settings |
| Nghiệp vụ | `app/services/agent_action_service.py`, `pending_action_service.py`; transaction helpers và services P3/P4 cần dùng chung |
| Dữ liệu | `app/db/models.py`, repositories mới, migration tiếp sau `0004_reminder_dispatch` |
| Config | `app/config.py`, `.env.example`, `requirements.txt`, preflight và logging |
| Tests | agent read/write/policy/context/budget, pending actions, migrations, DM integration và hồi quy P1–P4 |
| Tài liệu | `docs/PHASE_5_PLAN.md`, `PHASE_5_VALIDATION.md`, DATABASE/AGENT_TOOLS/SECURITY/DISCORD_UI; README/ROADMAP khi đạt nghiệm thu |

Tên file là dự kiến, chốt theo source nền P4 khi triển khai. Không thêm framework agent nặng.

## 5. Bảo toàn dữ liệu và rollback

1. Trước migration thật, xác định DB đang dùng mà không in secrets; tạo SQLite backup nhất quán bằng công cụ dự án, không chép riêng file đang có WAL. Kiểm tra integrity và restore thử vào file tạm.
2. Thử upgrade trên bản sao có dữ liệu P1–P4; đối chiếu schema, foreign keys, số lượng và nội dung bản ghi cũ. Không chỉ thử DB rỗng.
3. Dừng bot có kiểm soát khi thay schema/runtime; không mở process thứ hai. Sau upgrade: preflight, schema check và smoke test rồi bật AI theo cấu hình.
4. Rollback ưu tiên tắt AI, giữ schema additive và dữ liệu đã tạo; xác minh bản code P4 có chấp nhận migration head mới trước khi quay code về.
5. Không downgrade/drop bảng P5 có dữ liệu tự động. Restore snapshot cũ sẽ mất các ghi sau backup: cần dừng bot, backup trạng thái mới, thống kê chênh lệch và owner duyệt mất dữ liệu hoặc chuyển đổi bảo toàn trước khi restore.

## 6. Điều kiện hoàn tất

- Đạt cả 6 tiêu chí Acceptance P5 trong ROADMAP và 10 tình huống AGENT_TOOLS.
- Linter/format/tests/compile và migration checks đạt; ghi lệnh và số tests thực chạy, không coi 625 là kết quả chạy mới.
- UI cũ và reminder tiếp tục hoạt động; không lộ dữ liệu/secret; approval không bị prompt vượt qua.
- Có hướng dẫn `.env.example`, bật/tắt AI, giới hạn chi phí, retention và rollback; API key chỉ nhập trên máy, không gửi trong chat.
- Owner hoàn tất live acceptance; nếu thiếu API key/budget hoặc chưa test live, báo đúng phần còn thiếu thay vì đánh dấu P5 DONE.
