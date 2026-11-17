# Phase 5 — Báo cáo nghiệm thu 2026-11-18

**Phase 5 DONE — owner xác nhận hoạt động ngày 2026-11-18.**

Sau hướng dẫn thử “Hôm nay có việc gì?” và tạo task qua preview/Duyệt, owner xác nhận
“tuyệt vời nó đã hoạt dộng rồi”. Kiểm tra read-only DB xác minh một pending action
`create_task/executed` và một audit `agent.create_task/success`, usage model
`gpt-6-luna` có requests đã settle. Head 0005, integrity OK, 0 foreign-key violations.
Lượt OpenAI đọc thật trước đó đã gọi `get_today_overview` thành công.

Chốt nghiệm thu dựa trên **687 tests** ở lần chạy gần nhất, bằng chứng đọc/ghi thật và
xác nhận owner. Lần cập nhật tài liệu này không chạy lại tests, không gọi OpenAI thêm
và không sửa dữ liệu nghiệp vụ. Owner không nêu riêng mọi thiết bị/kịch bản; reschedule,
bulk, keep/shift, expiry/stale, non-owner và restart có tests tự động, không được tự
ghi đã chạy live riêng biệt. Các ghi chú “chờ nghiệm thu” trong lịch sử được thay bằng
trạng thái mới này. Chưa bắt đầu P6, chưa commit/push thay đổi P5.

Cập nhật 18/11 sau khi owner cấu hình: `AI_ENABLED=true`, model `gpt-6-luna`, key có
mặt và không in/log. Preflight config/AI/DB đạt. Một lượt thật “Hôm nay có việc gì?”
qua orchestrator gọi `get_today_overview` thành công, trả text; đối chiếu tasks,
events, reminders và pending actions trước/sau không đổi. Có ghi usage/reservations
theo policy. Lần trong sandbox lỗi APIConnectionError, chạy lại ngoài sandbox thành
công; không kết luận đây là lỗi key. Bot đã khởi động lại ngoài sandbox, sync 4
commands và online lúc 00:49:44 VN ngày 18/11. Sau đó owner tạo/duyệt task đã có
executed receipt và audit trong DB; không ghi nhận reschedule live riêng.
Branch `feat/phase-5`, nền `944d807`. Chưa commit/push thay đổi Phase 5.
README/ROADMAP đã cập nhật P5 DONE theo acceptance và xác nhận owner, giữ nguyên
lịch sử P3/P4 và ranh giới không tự chuyển phase.

## Kết quả kiểm tra

| Kiểm tra | Kết quả |
|---|---|
| Baseline trước thay đổi | `python -m pytest -q`: 625 passed in 53.40s |
| Toàn bộ sau triển khai | `python -m pytest -q`: **687 passed in 40.45s** |
| Lint | `python -m ruff check .`: All checks passed |
| Format | `python -m ruff format --check .`: 140 files already formatted |
| Compile | `python -m compileall -q app alembic tests`: exit 0 |
| Whitespace | `git diff --check`: exit 0 |
| Migration | `python -m alembic heads/current`: `0005_agent (head)` |
| Schema so với models | `python -m alembic check`: No new upgrade operations detected |
| Database thật | `python -m app.preflight`: config/integrity/FK/revision/owner/settings OK, exit 0 |
| Discord sau cấu hình AI | 4 slash commands đăng ký, log `bot_online` lúc 00:49:44 VN ngày 18/11 |
| OpenAI live | `gpt-6-luna`: read → `get_today_overview` → trả lời; dữ liệu nghiệp vụ không đổi |
| AI tạo task trong Discord | Một proposal `create_task/executed`, audit success; owner xác nhận hoạt động |

Các lệnh trên dùng `.\.venv\Scripts\python.exe` trên Windows, Python 3.12.3.
Tests tự động chặn network, mock Discord/OpenAI, không gọi API tính phí. Đã cài/pin
`openai==3.52.0`, `jsonschema==4.25.1`; không thêm agent framework.

## Phần đã thực hiện

- Responses API async, model env, `store=false`, fixed official endpoint, không tự
  retry HTTP/đổi model; giữ reasoning items và function_call_output trong tool loop.
- Registry 15 tools theo AGENT_TOOLS; chỉ mở write tools phù hợp từ khóa yêu cầu,
  schema strict và JSON Schema validation backend, DTO/domain validation và owner
  predicates. Model không được truyền owner, SQL, shell, HTTP hay approval.
- Reads: today/task/project/event/reminder/preferences, free slots từ confirmed
  events và workday settings, gợi ý theo yêu cầu. Lists có giới hạn/total, không cache
  dữ liệu nghiệp vụ giữa lượt; không tự lập lịch/memory/report.
- Strict writes: create task/event/reminder, complete task, reschedule và bulk update
  đều tạo preview. Biên nhận thực thi lấy từ DB sau owner click, không từ model text.
- Thời gian phổ biến được kiểm tra bằng clock/timezone backend (hôm nay/mai/ngày kia,
  ngày cụ thể, giờ h/:, daily/weekly đơn giản, sau N phút/giờ). Thiếu giờ/weekday mơ hồ
  hỏi lại. Câu bổ sung nối vào yêu cầu còn dở, TTL 30 phút và có hủy.
- Proposals TTL 15 phút, unique owner/turn key, snapshots/version/ref/conflict/timezone
  checks, message/channel binding, persistent paginated UI, reject/expiry/stale an toàn.
- Executor dùng validators/repos P3/P4 trong cùng writer transaction cho bulk/audit/
  receipt. Repeat click/Gateway/restart lấy lại cùng proposal/receipt, không ghi lặp.
- Khi dời event, preview reminder active/paused, owner chọn giữ giờ hay shift cùng
  delta. Shift cập nhật recurrence local và supersede delivery chưa gửi; claim đang
  gửi bị chặn và dùng chung lock worker, lịch sử sent giữ nguyên.
- Context RAM tối đa 20 messages/30 phút, timer tự xóa khi idle, nút xóa và usage.
  Không lưu raw chat hoặc bật conversation/memory dài hạn. Proposals chứa dữ liệu
  cần review; audit/usage chỉ metadata nghiệp vụ.
- API limits: input 4000 chars, 4 rounds, 8 tool calls, 60s/turn; one turn at a time;
  12 API requests/phút, daily request/token caps theo UTC. Reserve trước API, settle
  actual input/output sau thành công; lỗi hoặc usage chưa biết giữ reservation.
- AI thiếu config/tắt/lỗi không ngăn UI CRUD/reminder worker. SDK/HTTP logs tắt để
  tránh raw payload. Preflight kiểm tra cấu hình AI nếu yêu cầu bật, không gọi API.

## Tests bổ sung

`test_agent.py`, `test_agent_acceptance.py`, `test_agent_migration.py` thêm 62 cases:

- Real SQLite read tools; DM → proposal → client restart → approve → DB receipt.
- Duplicate proposal/click, hai yêu cầu chủ ý riêng biệt; stale bulk không ghi một phần;
  simulated flush failure rollback mutation/receipt và cho retry đúng.
- Owner/message/channel/TTL checks, foreign-owner references, unknown tools/extra
  arguments và injection không ghi được trái phép.
- Ambiguous Vietnamese không gọi API/không ghi; hỏi giờ rồi tiếp tục proposal.
- Create reminder none/daily/weekly → owner approve → worker P4 gửi mock một lần;
  reschedule keep/shift, pending supersede, đang claimed bị từ chối, new conflict stale.
- Quota concurrent reserve, unknown usage, settlement idempotency, context expiry,
  busy/loop limits, SDK options; UI pagination và DynamicItem restore.
- P4 → P5 migration + restore preserving old data; interruption rollback schema;
  downgrade refuses pending/usage history. Tests head/schema cũ cập nhật kỳ vọng head.

Đây là bằng chứng tự động, không thay thế nghiệm thu OpenAI/Discord Desktop/Mobile.

## Database thật và backup

Bot cũ đã dừng, mới khởi động lại đúng một phiên sau migration. Có hai PID Python
trước khi dừng là venv launcher và process con, cùng một phiên bot.

- `backups/pre-phase5-20261118.db`: snapshot nhất quán trước dừng.
- `backups/pre-phase5-stopped-20261118.db`: snapshot ngay sau dừng, nguồn rollback.
- `backups/phase5-migration-drill-20261118.db`: thử upgrade bản sao.
- `backups/phase4-restore-drill-20261118.db`: restore thử vào file mới từ snapshot P4.

So sánh toàn bộ rows và SQL định nghĩa của **8 bảng P1–P4** trước/sau cả drill và DB
thật đều bằng nhau. Backup nguồn không bị sửa. DB thật giờ ở `0005_agent`, integrity
và foreign keys tốt, không seed dữ liệu mẫu. Linux DB không bị truy cập/thay đổi.
`.env`, `nova.db`, các snapshots đều Git-ignored; không in token/key hoặc nội dung riêng.

## Cấu hình và checklist hồi quy

Máy hiện tại đã cấu hình key/model và AI bật. Phần dưới dùng cho cài lại hoặc
kiểm tra hồi quy; không yêu cầu chia sẻ key và không tự coi mọi checklist đã chạy live.

Nhập trực tiếp trên máy vào `.env`, không đưa key vào chat/Git:

```dotenv
AI_ENABLED=true
OPENAI_API_KEY=<your-local-key>
OPENAI_MODEL=<model-supported-by-your-api-project>
AI_DAILY_TOKEN_LIMIT=100000
AI_DAILY_REQUEST_LIMIT=100
```

Không hardcode model khi chưa biết tài khoản hỗ trợ. Token cap là bảo vệ tối thiểu,
không phải ngân sách USD chính xác; xem chi phí thật tại OpenAI Usage và cấu hình
budget dự án. Khi API lỗi, phần reservation chưa biết vẫn được tính hết. Muốn tắt
AI: `AI_ENABLED=false` và restart bot; callback proposal vẫn có thể hoạt động.

Sau cấu hình: dừng phiên hiện tại bằng Ctrl+C, chạy preflight rồi `python -m app.main`.
Kiểm thử owner trong DM:

1. “Hôm nay có việc gì?” đối chiếu task/lịch thật trong menu.
2. “Tạo task kiểm thử AI” → preview → Duyệt → xem lại Tasks; thử click lặp.
3. “Mai nhắc tôi làm bài” → bot hỏi giờ, trả lời giờ cụ thể → xem ngày/timezone →
   Duyệt. Tạo thêm reminder gần hiện tại để kiểm tra delivery thật; tránh giờ yên lặng.
4. Tạo event thử, đề nghị dời → kiểm tra diff rồi Hủy, DB không đổi. Đề xuất lại →
   Duyệt, kiểm tra event và lựa chọn keep/shift reminder.
5. Để pending rồi restart và duyệt; sửa event qua menu trước khi duyệt pending khác
   phải báo stale. Tài khoản khác không đọc/chạy tool/duyệt được.
6. Thử Xóa ngữ cảnh và Sử dụng AI; tắt AI để xác nhận CRUD/reminders vẫn dùng được.

P5 đã chốt sau xác nhận owner và bằng chứng read/create-task ở trên. Bot online với
AI bật; dùng checklist để hồi quy khi thay model/môi trường/source.

## File tạo/sửa

Tạo:

- `app/agent/`: config, client, serialization, schemas/registry, policy, gateway,
  usage và orchestrator (cùng `__init__.py`).
- `app/services/pending_action_service.py`.
- `app/discord_bot/agent_controller.py`, `views/agent.py`.
- `alembic/versions/0005_agent.py`.
- Ba test files P5 ở trên; `docs/PHASE_5_PLAN.md`, báo cáo này.

Sửa:

- `.env.example`, `requirements.txt`, `app/config.py`, `app/db/models.py`.
- Discord client/dashboard controller/help renderer, `app/domain/modules.py`.
- `app/logging_config.py`, `app/preflight.py`.
- `tests/test_core_migration.py`, `test_database.py`, `test_reminder_migration.py`
  để đối chiếu revision/schema mới, giữ assertions bảo toàn dữ liệu cũ.
- `docs/ARCHITECTURE.md`, `DATABASE.md`, `AGENT_TOOLS.md`, `SECURITY.md`, `DISCORD_UI.md`.
- README và ROADMAP: cập nhật setup/usage/head và trạng thái nghiệm thu sau owner xác nhận.

## Rollback

Ưu tiên tắt AI bằng env và giữ schema additive/dữ liệu. Không quay về code P4 trực tiếp:
source P4 không biết revision 0005 và startup/preflight có thể từ chối head mới.

Nếu cần downgrade:

1. Dừng bot, backup trạng thái mới bằng `python -m app.db.backup --output <new-file.db>`.
2. Nếu hai bảng AI chưa có history, `python -m alembic downgrade 0004_reminder_dispatch`
   bằng source P5 được phép. Migration từ chối nếu bất kỳ bảng AI có rows.
3. Nếu có history, giữ AI tắt để dùng CRUD; muốn chuyển code/schema phải xuất/chuyển
   history và kiểm tra bảo toàn, không xóa/drop bảng tự động.
4. Restore snapshot P4 cũ sẽ bỏ các ghi sau snapshot. Cần owner duyệt rõ mất dữ liệu
   hoặc thực hiện chuyển đổi bảo toàn trước. Giữ DB hiện tại thành backup riêng,
   restore vào tên file mới và đổi DATABASE_URL sau kiểm tra; không chép đè DB đang chạy.

## Giới hạn thực tế

- Model `gpt-6-luna` đã gọi Responses function calling thật thành công; có read-tool
  và create-task executed/audit thực tế. Các write variants khác có tests tự động,
  chưa ghi nhận live riêng.
- Date parser hỗ trợ tập câu phổ biến nêu trên, không hứa hiểu mọi cách diễn đạt.
  Khi không khớp, yêu cầu ngày/giờ rõ và vẫn bắt buộc owner review.
- Mỗi DM turn tối đa một proposal; bulk tối đa 10 records, không tự chia rồi ghi từng phần.
- Quota/usage không tính tiền chính xác, chưa cấu hình giá model; không tự mua credits.
- SQLite một process; không exactly-once với Discord. Proposals dài có phân trang,
  chỉ Duyệt sau trang cuối; pending hết hạn vẫn bị backend từ chối dù message cũ còn nút.

Nguồn tích hợp: [OpenAI quickstart](https://developers.openai.com/api/docs/quickstart),
[function calling](https://developers.openai.com/api/docs/guides/function-calling),
[Discord Message Content exceptions](https://docs.discord.com/developers/events/gateway#message-content-intent).
