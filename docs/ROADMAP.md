# Development Roadmap — NOVA

**Bản kế hoạch:** 2026-10-23 · **Nguyên tắc:** hoàn thành/kiểm thử từng phase, không làm đồng loạt. Đây là *roadmap theo đầu ra*, không phải cam kết thời gian.

## 1. Trạng thái tổng thể

| Phase | Tên | Trạng thái | Deliverable |
|---|---|---|---|
| P0 | Planning & Design | ✅ DONE (2026-10-23) | PRD, Architecture, Database, Discord UI, Agent Tools, Security, Roadmap, AGENTS, Handoff |
| P1 | Foundation | ✅ DONE (2026-10-23) | bot online, owner auth, DB bootstrap, `/ping`, `/menu` shell |
| P2 | Dashboard UI | ✅ DONE (2026-10-23) | buttons/select/modal, module views, settings shell, persistent view |
| P3 | Core Management | 🟨 IN PROGRESS — 3C source/tests xong, chờ nghiệm thu Discord | Tasks, Projects, Calendar (DB CRUD + conflicts) |
| P4 | Reminder Engine | ⬜ NOT STARTED | reminders schedule, retry/delivery, DM/channel |
| P5 | AI Agent | ⬜ NOT STARTED | natural-language DM + OpenAI tool calling + confirmations |
| P6 | Memory & Proactive Automation | ⬜ NOT STARTED | memory controls, planner suggestions, morning/daily/weekly reports |
| P7 | Expansion & Deployment | ⬜ NOT STARTED | Goals/Finance/Habits/Notes, integrations optional, Docker/VPS |

**P0 DONE nghĩa là xong tài liệu thiết kế, không có nghĩa bot đã chạy.** Chỉ đánh dấu P1–P7 `DONE` khi đạt toàn bộ acceptance tương ứng và đã kiểm thử.

## 2. Phase 0 — Planning & Design ✅

### Checklist

- [x] PRD phân định MVP và backlog.
- [x] Discord UI map: DM, 4 channels, Dashboard, module screens, buttons/modals.
- [x] Architecture: modular monolith, service boundaries.
- [x] Database schema chuẩn hóa timezone, entity links, deliveries, confirmations.
- [x] AI tool catalogue + permission policy.
- [x] Security baseline, roadmap và Codex handoff.
- [x] AGENTS.md kiểm soát scope và cách test cho các coding agents.

### Không thực hiện trong P0

- Không tạo Discord application hay API key thay cho owner.
- Không có project Python/bot runtime, không claim `/menu` chạy.
- Không deploy/charge API; không kích hoạt OAuth/Google Calendar.

## 3. Phase 1 — Foundation ✅

### Work packages

1. Python project layout theo `ARCHITECTURE.md`; chọn versions tương thích, dependency pinning, README runbook.
2. Settings `.env.example` + `.gitignore`, validate required env, logs không tiết lộ secret.
3. `discord.py` bot, connect Gateway, slash `/ping`, `/menu` (dashboard placeholder rõ).
4. Owner guard ở command và **callback**; deny người khác.
5. SQLAlchemy async SQLite, tạo/migrate `users`, `user_settings` (+ migration foundation), DB bootstrap.
6. Basic tests: config, auth, startup/bootstrap, services mockable; lint/test command.

### Acceptance P1

- [x] Bot online trong Discord và `/ping` trả lời.
- [x] `/menu` hiển thị dashboard placeholder/entry; không có fake data.
- [x] Non-owner bị chặn ở slash/DM/callback liên quan.
- [x] Config thiếu token/owner ID gây lỗi an toàn, không lộ secret.
- [x] Database SQLite tạo thành công, restart giữ settings/owner.
- [x] Tests chạy pass (không cần Discord thật trong unit tests).
- [x] README hướng dẫn cài, chạy và xử lý lỗi thường gặp.

**Nghiệm thu:** ngày 2026-10-23, người dùng xác nhận “Phase 1 DONE” sau checklist kiểm tra Discord thực tế. Kết quả tự động từ phiên triển khai: **65 tests pass**, lint/format pass. Xác nhận live do người dùng cung cấp; Codex không tự đăng nhập Discord để kiểm chứng lại. Chi tiết lịch sử tại [`PHASE_1_VALIDATION.md`](PHASE_1_VALIDATION.md). Tiến độ P2 theo mục bên dưới.

## 4. Phase 2 — Discord Dashboard UI ✅

**Nghiệm thu 2026-10-23:** người dùng xác nhận “phase-2 Done” sau hướng dẫn kiểm tra Discord thực tế. Kết quả tự động từ phiên triển khai: **159 tests pass** cùng hồi quy Foundation, lint/format pass. Xác nhận thực tế do người dùng cung cấp; Codex không tự đăng nhập Discord để kiểm chứng lại. P2 **DONE**; tiến độ P3 hiện tại ở mục bên dưới. Báo cáo và checklist kiểm tra lại: [`PHASE_2_VALIDATION.md`](PHASE_2_VALIDATION.md).

**Phạm vi/assumptions:** dùng lại schema P1, chỉ mở chỉnh timezone đã có storage; các settings automation/notification chỉ đọc. Dashboard neo đặt trong kênh riêng; runtime kiểm tra `@everyone`, owner chịu trách nhiệm các role/overwrites khác. Recovery message/channel bị xóa diễn ra khi owner gọi `/menu`, không tự gửi lúc startup. Chống trùng giới hạn một process SQLite và reconciliation 50 messages, không hứa atomic Discord/DB khi crash.

### Work packages

1. Home overview (empty states, summary từ DB), buttons/select menu.
2. Các panel Tasks/Projects/Calendar/Reminders/AI/Settings, chưa làm thì “Sắp ra mắt”.
3. `Back`, `Refresh`, Help, modals mẫu có validate, UX desktop + mobile.
4. Persistent view restore sau restart, dashboard message được lưu/nhận diện.
5. Hạn chế spam: thao tác private panel, không overwrite dashboard mọi lần.

### Acceptance P2

- [x] `/menu` có thể mở module/chọn nút trên mobile và desktop.
- [x] Owner-only enforced trên mọi button/select/modal.
- [x] Persistent dashboard hoạt động sau restart.
- [x] Nội dung chưa hoàn thiện ghi “Sắp ra mắt”; không báo đã tạo dữ liệu giả.
- [x] Chế độ lỗi/hết hạn interaction được xử lý rõ ràng.

**Ghi chú UX khi nghiệm thu:** bảng neo là message dùng chung; panel riêng tư là ephemeral theo phiên. Khi chuyển mobile/web, mở lại module từ bảng neo; Refresh đọc lại dữ liệu đã lưu. Không thay đổi thiết kế này trong lần chốt P2.

## 5. Phase 3 — Core Management

**Checkpoint 3A, 2026-10-23:** Database & Migration hoàn tất với **250 tests pass**, gồm hồi quy P1/P2. Có backup `backups/pre-phase-3a-20261023.db`; đã kiểm tra migration/restore trên bản sao DB Phase 2 thực tế, không nâng cấp `nova.db` đang dùng trong phiên 3A. Báo cáo/runbook: [`PHASE_3A_VALIDATION.md`](PHASE_3A_VALIDATION.md). Handoff: [`PHASE_3_HANDOFF.md`](PHASE_3_HANDOFF.md).

**Checkpoint 3B, 2026-10-23:** repositories/services hoàn tất, **340 tests pass in 6.02s**, lint/format/compile pass, hồi quy P1/P2/3A đạt. Không đổi schema hoặc chạy migration trên DB thật. Service API và kết quả lịch sử: [`PHASE_3B_VALIDATION.md`](PHASE_3B_VALIDATION.md).

**Checkpoint 3C, 2026-10-23:** người dùng yêu cầu tiếp tục sau 3B. Đã nối Discord UI với services, counts/Today thật, chọn quan hệ, form/status, paging/filter và confirmations. Bản đầu đạt 388 tests; sau yêu cầu rà soát form, bổ sung bản nháp trước khi Lưu, bộ chọn ngày/giờ và các select thay nhập tay: **419 tests pass in 8.32s**, lint/format/compile pass. Chưa chạy Discord Desktop/Mobile hoặc sửa DB thật trong phiên này. **Chưa chốt toàn P3 DONE**, đợi xác nhận nghiệm thu thực tế theo [`PHASE_3C_VALIDATION.md`](PHASE_3C_VALIDATION.md); không bắt đầu P4.

### Checkpoints

- [x] **3A:** models Project/Task/CalendarEvent, relationships, FK/constraints/indexes, migration `0002_core_management`, UTC round-trip, backup/restore và tests.
- [x] **3B:** repositories owner-scoped, CRUD services, validation nghiệp vụ, progress, filters/pagination, overlap và stale/double submit handling.
- [ ] **3C:** Discord CRUD UI, confirmations, counts thật, kiểm thử Desktop/Mobile và nghiệm thu toàn bộ P3.

Source và tests 3C đã xong; checkbox giữ trống vì còn nghiệm thu Desktop/Mobile, owner/non-owner và restart Discord thật.

**Giới hạn/assumptions:** schema 3A giữ FK ghép cùng owner, RESTRICT và defaults `proposed/manual`, `todo/medium`. Service 3B cho thao tác tạo lịch thủ công mặc định `confirmed` sau overlap check; `proposed` vẫn được hỗ trợ. Task status đồng bộ completed_at, không tự đổi calendar events liên kết. Updates task/event so sánh version, project so sánh updated_at; SQL ghi có owner predicate. SQLite service writes dùng BEGIN IMMEDIATE để reserve writer trước read-check-write, Foundation/migration vẫn BEGIN như cũ.

**Pending actions thủ công 3B:** hủy task/event, archive project, sửa event confirmed và giữ overlap cần token service cấp, gắn owner/payload/version/conflict snapshot, TTL 5 phút, dùng sau commit thành công; lỗi commit không tiêu thụ token. Lưu trong bộ nhớ có giới hạn 100 phiên, mất khi restart và phải duyệt lại. Không thêm bảng pending_actions/executor AI P5. Tạo bản ghi yêu cầu request_id ổn định để chống double submit, đối chiếu payload khi retry; thay đổi payload hoặc record đã chỉnh sửa có thể yêu cầu key mới. Chỉ một process SQLite, không tuyên bố multi-worker support. UI 3C phải giữ service instances qua các interactions, đọc timezone từ Settings và hiển thị trước/sau cùng conflicts trước khi gửi token duyệt; không tự duyệt token nhận từ lỗi.

**Quyết định UI 3C:** giữ bảng neo chung không có số liệu/nội dung riêng tư; `/menu` trả thêm Home ephemeral với counts thật. CoreServices sống suốt lifecycle client. Mỗi panel có state/expected snapshot riêng; không ghi SQL trong adapter. Modal thường chỉ nhập tên/mô tả, sau đó bản nháp dùng ngày/giờ/priority/fixed/estimated/link pickers; chỉ Lưu mới gọi service. Nhập tay datetime/số phút khác là tùy chọn, form tối đa 4 TextInputs. Bản nháp tối đa 10 phút, không gia hạn khi chọn menu; lock chung chống sửa payload giữa lúc Lưu. Timezone được chụp khi mở form, giữ precision giá trị không chỉnh sửa. Chọn links bằng menu phân trang, không nhập ID. Duyệt chỉ ở trang cuối của diff/conflicts; không tự execute pending action. Dùng archive/cancel thay hard-delete. Summary tính Tasks không cancelled, Projects không archived; Today gồm confirmed events và task todo/doing đến hạn/quá hạn hoặc high/critical. Reminders/AI vẫn sắp ra mắt.

### Work packages

1. `projects`: CRUD + list + tính tỷ lệ task done.
2. `tasks`: CRUD, statuses, priority, optional deadline/project, pagination.
3. `calendar_events`: create/list/edit, conflict detection, timezone input.
4. UI forms + services + repositories + migrations + tests.

### Acceptance P3

- [ ] Owner tạo/sửa task/project/event qua Discord UI, xem lại vẫn đúng.
- [ ] Restart bot không mất dữ liệu.
- [ ] Không có task/event tham chiếu project/task của owner khác (validation).
- [ ] Calendar phát hiện overlap và báo rõ; không tự xóa/thay lịch.
- [ ] Task/project counts phản ánh DB, empty states chuẩn.
- [ ] CRUD & timezone tests pass.

## 6. Phase 4 — Reminder Engine

### Work packages

1. Reminders one-time/recurring daily+weekly, snooze/cancel.
2. Worker poll DB, claim due, retry capped, deliveries history, quiet hours handling.
3. Discord DM send, private fallback channel only, buttons trên notification nếu SDK hỗ trợ.
4. Restart recovery and overdue/catch-up policy.

### Acceptance P4

- [ ] Tạo lời nhắc và nhận thông báo gần thời điểm theo timezone.
- [ ] Reminder vẫn tồn tại sau restart.
- [ ] Lời nhắc lặp lại tạo lần kế tiếp đúng và không nhân bản DB vô hạn.
- [ ] Retry/failure hiển thị trạng thái và có logs.
- [ ] Double click/worker duplicate không nhân đôi số bản ghi delivery.
- [ ] DM bị chặn không gây leak kênh công khai.

## 7. Phase 5 — AI Agent

### Work packages

1. OpenAI Responses API + model configurable.
2. DM parsing, short-term context; tool registry + parameter validation.
3. Tool services đọc/truy xuất/tạo task/reminder đơn rõ; proposals for reschedule/bulk changes.
4. Confirmation protocol & permission policy; cache/limits and API error fallback.
5. Natural language tests incl. ambiguous Vietnamese date/time and prompt injection.

### Acceptance P5

- [ ] Hỏi “Hôm nay có việc gì?” trả dữ liệu đúng từ DB.
- [ ] “Tạo task X...” tạo qua tool nếu đủ rõ, xác nhận hoàn thành.
- [ ] “Dời toàn bộ lịch chiều...” chỉ tạo đề xuất chờ duyệt.
- [ ] Người ngoài / prompt injection không gọi được tool trái phép.
- [ ] AI lỗi không làm hỏng CRUD UI, không trả “thành công” giả.
- [ ] Chi phí theo dõi được, có giới hạn tối thiểu.

## 8. Phase 6 — Personal Memory & Automation

### Work packages

1. Memory entries có nguồn và owner confirmation, xem/sửa/xóa.
2. Scheduler morning briefing/daily review/weekly plan (settings aware).
3. AI planner dùng confirmed calendar events + deadlines + preferences; review dựa trên dữ liệu thật.
4. `automation_runs` chống gửi lặp/đảm bảo idempotency.

### Acceptance P6

- [ ] Bật/tắt, đổi giờ briefing và report; không gửi ngoài quiet hours (trừ cảnh báo thật sự quan trọng được thiết lập).
- [ ] Memory có UI xem/sửa/xóa và không tự biến suy đoán thành sự thật.
- [ ] Planner phân biệt `proposed` và `confirmed`.
- [ ] Daily review không bịa số liệu cho ngày thiếu dữ liệu.

## 9. Phase 7 — Advanced modules, Integrations & Production

### Work packages

- Goals, Habits, Finance (manual income/expense), Notes + dashboard links.
- Tích hợp riêng từng provider theo nhu cầu: Google Calendar, Gmail, GitHub, Notion; OAuth least privilege và consent.
- Containerization, VPS, PostgreSQL migration (khi cần), backup/restore, monitoring/recovery, API budget.

### Acceptance P7

- [ ] Các module mới có CRUD thật và tests.
- [ ] Có hướng dẫn deploy/backup/restore; staging simulation pass.
- [ ] Integration không có quyền ngoài scopes đã yêu cầu và được duyệt.
- [ ] Restore từ backup hoạt động và owner ID không bị thay.

## 10. Definition of Done (áp dụng mọi phase)

- Code chạy/lint/test theo chỉ dẫn và không có regression lớn.
- Không chứa secret trong source, logs, fixtures; `.env` bị gitignore.
- Docs được cập nhật tương ứng và ghi rõ thay đổi ngoài thiết kế.
- Không hiển thị nút “đã làm” nếu backend chưa có.
- Các thao tác mới có owner guard, validation và tình huống lỗi.
- Người dùng có thể kiểm tra bằng hướng dẫn ngắn tại cuối phase.
- Không tự động bắt đầu phase tiếp theo.

## 11. Những việc có thể bổ sung sau (Backlog)

- Backup/export dữ liệu cá nhân qua DM an toàn.
- Task recurrence và habit streak nâng cao.
- GitHub issue import, Google Calendar bidirectional sync.
- Voice chat/stt/tts.
- UI nâng cấp Components V2 và views mới; chỉ khi SDK hỗ trợ ổn định.

## 12. Nhật ký tiến độ

| Ngày | Phase | Sự kiện |
|---|---|---|
| 2026-10-23 | P0 | Tạo tài liệu đặc tả ban đầu, chốt zero-command Discord UX |
| 2026-10-23 | P1 | Foundation hoàn thành; 65 tests pass, lint/format pass; người dùng xác nhận “Phase 1 DONE”; chưa bắt đầu P2 |
| 2026-10-23 | P2 | Hoàn thành dashboard neo, module panels, Help/Settings, timezone modal, persistent View; 159 tests pass; người dùng xác nhận “phase-2 Done”; chưa bắt đầu P3 |
| 2026-10-23 | P3A | Hoàn tất schema/migration Core Management; 250 tests pass; backup và thử upgrade/restore trên bản sao DB Phase 2; chưa migrate DB đang dùng, chưa bắt đầu 3B/3C |
| 2026-10-23 | P3B | Hoàn tất repositories/services/validation/overlap/manual approvals; 340 tests pass; schema giữ 0002; chưa nối UI, dừng trước 3C |
| 2026-10-23 | P3C | Source UI CRUD và confirmations/counts đã triển khai; rà soát UX thêm draft/date-time picker/select; 419 tests pass; chờ nghiệm thu Discord Desktop/Mobile, không đánh dấu toàn P3 DONE và chưa bắt đầu P4 |
