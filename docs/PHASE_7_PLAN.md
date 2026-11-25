# Kế hoạch Phase 7 — Trợ lý công việc và vận hành bền vững

Ngày lập: 2026-11-24. Cập nhật 2026-11-25: **P7 IN PROGRESS, dừng tại 7A.2**.
Nguồn phạm vi: [ROADMAP](ROADMAP.md), [PRD](PRD.md), [AGENTS](../AGENTS.md).

7A.1 đạt code/tests và migration bảo toàn P1–6. 7A.2 đã có GitHub reader/UI,
**961 tests pass**, DB giữ `0007_connections`, backup/restore và restart đạt.
Chờ token/phạm vi để thử GitHub thật và owner nghiệm thu UI; chưa có Notion,
AI tools đọc nguồn hoặc 7B–7F. Xem [7A.1](PHASE_7A1_VALIDATION.md) và
[báo cáo checkpoint 7A.2, cấu hình/rollback](PHASE_7A2_VALIDATION.md).

## 1. Mục tiêu và nền hiện tại

Sau P7, NOVA có thể giúp owner theo dõi công việc từ nguồn đã kết nối, liên kết
mục tiêu với việc cần làm, giữ ghi chú, theo dõi thói quen và thu chi thủ công.
Các hành động bên ngoài được mở riêng, có bản xem trước và xác nhận. Bot có
quy trình chạy thường trực, backup và phục hồi đã được thử.

Nền khi lập kế hoạch: P6 DONE, schema `0006_personal`, 803 tests
pass, owner-only, Tasks/Projects/Calendar/Reminders, Memory/Planner/Reports,
Responses tools và durable pending approvals. Chưa có service thật cho Goals,
Notes, Habits, Finance hoặc connector; chưa có Docker/VPS runbook thực thi.

Định hướng đề xuất: ưu tiên hỗ trợ công việc qua GitHub/Notion trước. Tích hợp
là lựa chọn theo nhu cầu, không phải bắt buộc kết nối mọi dịch vụ trong roadmap.
GitHub/Notion ở đây là connector của bot NOVA; kết nối một app trong ChatGPT
không tự cung cấp credentials/quyền cho bot.

## 2. Chia chặng và thứ tự

| Chặng | Đầu ra người dùng nhận được | Phụ thuộc |
|---|---|---|
| 7A | Đọc GitHub/Notion đã cấp quyền, tổng hợp có nguồn, soạn đề xuất công việc | Nền P6; owner chọn nguồn và cấp quyền trước phép thử thật |
| 7B | Mục tiêu và ghi chú gắn với dự án/công việc | Nền P6; dùng được khi chưa kết nối 7A |
| 7C | Thói quen, đánh dấu theo ngày, nhắc và tổng kết | Nền P6; có thể liên kết mục tiêu 7B |
| 7D | Sổ thu chi VND nhập tay, báo cáo số liệu thật | Nền P6; tách quyền/ngữ cảnh tài chính |
| 7E | Tạo issue/comment hoặc trang Notion sau khi duyệt | 7A đạt; owner chọn loại thao tác và cấp thêm quyền |
| 7F | Docker/Linux/VPS, backup, phục hồi và kiểm tra hoạt động | Kiểm thử các chặng được chọn trước khi triển khai thật |

Thứ tự mặc định: **7A → 7B → 7C → 7D → 7E nếu cần → 7F**. Có thể đưa phần
vận hành 7F lên sớm nếu cần bot chạy khi tắt máy cá nhân; vẫn nghiệm thu riêng,
không gộp việc đổi hạ tầng với migration tính năng trong một lần chuyển hệ thống.

Mỗi lần thực hiện chỉ nhận một chặng/checkpoint. Hoàn tất báo cáo và nghiệm thu
rồi mới chuyển tiếp; việc đồng ý kế hoạch không tự bật connector, mua VPS hoặc
cho phép đăng nội dung ra bên ngoài.

## 3. Phase 7A — Cùng theo dõi công việc từ GitHub/Notion

### Trải nghiệm

- “Repo này còn issue nào cần xử lý?” → danh sách thật, trạng thái và link nguồn.
- “Tóm tắt tài liệu dự án tôi đã kết nối.” → tóm tắt nội dung được phép đọc,
  kèm nguồn và thời điểm lấy dữ liệu.
- “Từ những issue này, đề xuất việc nên làm tiếp.” → đề xuất; tạo task nội bộ
  chỉ khi owner xem và Duyệt. Không mặc định mọi issue là việc owner phải làm.
- “Soạn nội dung phản hồi issue này.” → bản nháp trong DM, chưa gửi lên GitHub.

### 7A.1 — Khung kết nối và bảo vệ dữ liệu

- Thêm `IntegrationConnection`: owner, provider, tên hiển thị, danh sách tài
  nguyên cho phép, quyền đã cấp, trạng thái/version, thời điểm kiểm tra. DB giữ
  tham chiếu credential đã định nghĩa trong config, không giữ token plaintext.
- Chỉ đọc nguồn owner chọn. Kiểm tra cả ở service/tool executor; không dựa vào
  câu nhắc trong prompt hoặc khả năng token có thể đọc thêm tài nguyên.
- UI **Cài đặt → Kết nối**: chọn nguồn, xem phạm vi, Kiểm tra kết nối, Ngắt kết
  nối. Token nhập trên máy/secret manager, không có modal yêu cầu dán key trong DM.
- Màn chẩn đoán phân biệt Discord/OpenAI/GitHub/Notion; bot_online không đồng
  nghĩa AI hay connector hoạt động. Phép thử gọi AI thật phải được báo rõ và
  tính vào quota. Lỗi một provider không chặn Tasks/Reminders.
- Trước migration: backup, thử upgrade/restore trên bản sao P6, so khớp toàn bộ
  cột và bản ghi cũ. Tên revision chốt lúc triển khai, nối tiếp head thực tế.

### 7A.2 — GitHub chỉ đọc

- Đọc metadata repo, issues, pull requests và các tài liệu văn bản được chọn.
  Bản đầu không tải cả repository hoặc chạy mã từ repo.
- Cấu hình một repo thử trước. Với tài khoản cá nhân có thể bắt đầu bằng
  fine-grained token giới hạn repo, chỉ quyền đọc endpoint cần dùng. Khi vận
  hành lâu dài/cho tổ chức, ưu tiên GitHub App; chốt theo quyền thực tế của owner.
  [Quản lý token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens),
  [quyền GitHub App](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app).
- Không yêu cầu quyền administration, push, merge hoặc workflow nếu chức năng
  chỉ cần đọc issue/PR/tài liệu. Chưa mở API viết trong 7A.

### 7A.3 — Notion chỉ đọc

- Đọc/tìm trong các trang hoặc vùng dữ liệu owner đã cho kết nối; có phân trang
  và giới hạn nội dung. Không giả định bot biết toàn bộ workspace.
- Bản cá nhân ưu tiên internal connection, capability Read content và chỉ chia
  sẻ các trang cần dùng. Quyền với trang cha có thể mở tới trang con nên phải
  rà phạm vi chia sẻ. Không cần xây web frontend/OAuth public chỉ để thử một
  workspace cá nhân. [Capabilities](https://developers.notion.com/reference/capabilities),
  [authorization](https://developers.notion.com/guides/authorization/overview).
- Chốt version API/kiểu dữ liệu theo tài liệu hiện hành khi triển khai; không
  dựa vào schema Notion hoặc phiên bản SDK suy đoán từ kế hoạch này.

### 7A.4 — Nối vào trợ lý và nghiệm thu

- Tool catalogue chỉ mở tool theo ý định và kết nối đang bật, không nạp tất cả
  nguồn vào mọi câu hỏi. Giữ giới hạn vòng lặp/requests/tokens từ P5–6.
- Kết quả có link nguồn từ backend, thời điểm lấy và nhãn dữ liệu cũ/không đầy
  đủ nếu có. Chưa kết nối/lỗi quyền phải nói rõ, không trả số 0 như dữ liệu thật.
- Nội dung issue/page/file là dữ liệu không tin cậy; không được đổi policy,
  yêu cầu shell/SQL, lấy secret hay tự cấp quyền. HTTP adapter chỉ gọi origin
  API cố định và resource đã allowlist, không fetch URL tùy ý do model cung cấp.
- Đề xuất mặc định để đo trong checkpoint: tối đa 10 kết quả/lần, lấy sâu tối
  đa 5 tài liệu, không tải attachment/binary; có giới hạn dung lượng và số API
  calls mỗi lượt. Cache tối đa 15 phút để dùng lại, purge content sau 24 giờ;
  dữ liệu stale phải có nhãn, không dùng để duyệt mutation.
- `IntegrationObjectLink` có owner/source/remote ID/local ID để chống nhập một
  issue thành nhiều task khi bấm lại. Nhập nội bộ cần pending approval; bản nháp
  AI đơn thuần chưa phải task hay Memory đã xác nhận.
- Ngắt kết nối: chặn lượt đọc mới, vô hiệu hóa đề xuất phụ thuộc nguồn, xóa
  cache/context liên quan. Task/Note owner đã chủ động nhập được giữ với nguồn
  gốc, có thông báo rõ; không tự xóa công việc của owner.

**Nghiệm thu:** dữ liệu thật từ nguồn thử đã cấp quyền; bị chặn với repo/page
ngoài allowlist; đọc/tổng hợp có nguồn; thu hồi quyền hoặc timeout hiển thị đúng;
không có mutation bên ngoài, không lộ token. Tests gồm pagination, 401/403/404,
rate limit, prompt injection, duplicate import, nguồn vừa bị ngắt và quota.

## 4. Phase 7B — Mục tiêu và ghi chú

- Goals: tạo/sửa/lưu trữ mục tiêu, deadline, mốc hoàn thành; liên kết dự án/việc
  đã có để tránh quản lý hai danh sách độc lập. Tiến độ tính từ mốc hoặc việc
  liên kết theo quy tắc công khai, không để AI tự nhận xét thành số phần trăm.
- Notes: tạo/sửa/tìm kiếm/lưu trữ, gắn dự án hoặc mục tiêu, giữ nguồn nếu nhập
  từ connector. Note là tài liệu owner lưu; không tự biến Note thành Memory.
- UI mở từ công việc/dự án liên quan hoặc danh sách mở rộng, không thêm nhiều
  nút lên trang chính. Có hướng dẫn ngắn và trạng thái trống kèm hành động tiếp.
- Models dự kiến: `Goal`, `GoalMilestone`, liên kết goal/project/task và `Note`.
  Owner/FK/version, soft delete phù hợp, validation độ dài và UTC timestamps.
- DM ví dụ: “Tạo mục tiêu học Python, chia thành các mốc để tôi xem”, “Lưu ghi
  chú này vào dự án X”. Mọi AI write tiếp tục strict preview → Duyệt.

**Nghiệm thu:** CRUD bền sau restart, sửa/xóa có duyệt, liên kết cùng owner,
tiến độ/tìm kiếm từ DB; test stale/atomic rollback. Owner hoàn thành một luồng
từ mục tiêu → công việc → ghi chú trên Discord, không cần nhớ slash command mới.

## 5. Phase 7C — Thói quen

- Tạo thói quen theo ngày hoặc một số ngày trong tuần. Bản đầu là check-in
  hoàn thành/chưa hoàn thành, tránh mở thêm nhiều kiểu đo lường cùng lúc.
- `HabitDefinition` và `HabitLog`: unique habit/local date, lưu UTC check-in,
  ngày local/timezone làm ngữ cảnh; lịch có thời điểm hiệu lực để đổi lịch không
  làm sai lịch sử. Không tự bù check-in khi bot tắt hoặc khi chưa có dữ liệu.
- Đánh dấu bằng nút; bấm hai lần không thêm hai lượt. Ghi bù/sửa lịch sử cần
  owner duyệt. Streak chỉ tính những ngày phải thực hiện theo lịch đã chọn.
- Nhắc thói quen dùng engine P4 và quiet hours hiện có. Đã nhận/đã bấm thông
  báo không tự được coi là hoàn thành thói quen nếu chưa xác nhận check-in.
- Daily/weekly report có phần thói quen nếu owner bật; không tự suy ra năng suất.

**Nghiệm thu:** không trùng ngày, đúng timezone/ngày chuyển tuần, lịch thay đổi
không sửa quá khứ, nhắc việc không nhân đôi, restart không mất check-in.

## 6. Phase 7D — Thu chi thủ công

- Ghi thu/chi, ngày, số tiền, loại tiền, danh mục, ghi chú tùy chọn; sửa/hủy
  theo version và duyệt. Bản đầu chỉ VND, không quy đổi tỷ giá hay đồng bộ ngân hàng.
- Số tiền lưu chính xác theo đơn vị tiền nguyên, không dùng float. “50k” được
  chuẩn hóa thành 50.000 VND trong preview. Thiếu/không rõ số tiền thì hỏi lại.
- `FinanceTransaction` và danh mục theo owner; hủy giữ dấu vết, không tự nhân
  bản khi retry. Tổng thu/chi theo kỳ tính ở backend, phần đã hủy không cộng lại.
- Tài chính không được nạp vào context chung, memory hoặc bản tin hiện có theo
  mặc định. Chỉ đọc khi owner hỏi hoặc bật riêng phạm vi báo cáo đó.
- UI có nhập nhanh, lọc ngày/danh mục, tổng tháng; không yêu cầu số tài khoản,
  mật khẩu hoặc đưa ra lệnh chuyển tiền.

**Nghiệm thu:** tổng tiền đúng với dữ liệu thử và dữ liệu rỗng, phân kỳ local
đúng; decimal/overflow/duplicate/version/owner có tests; AI không tự tạo giao
dịch chỉ vì nhìn thấy số tiền trong tài liệu hay hội thoại không yêu cầu ghi.

## 7. Phase 7E — Làm một số việc bên ngoài sau khi duyệt

Chặng này tùy chọn, chỉ mở cho provider và thao tác owner chọn. Bắt đầu với
**tạo issue/comment GitHub** hoặc **tạo trang Notion**, không bật mọi write API.

- Cấp thêm đúng quyền thao tác, riêng với quyền đọc 7A. Xem trước đích gửi,
  nội dung đầy đủ, người dùng/provider và ảnh hưởng; kiểm tra lại quyền tại lúc
  duyệt. Backend không tin destination hoặc owner ID do model truyền.
- Bổ sung durable external action với TTL, payload hash, connection/version,
  trạng thái và remote receipt. Bấm lặp hoặc restart không tự gửi lại yêu cầu.
- Gửi mạng và commit DB không atomic: timeout sau gửi là trạng thái chưa xác
  định, không tuyên bố thành công và không tự retry write. Dùng idempotency của
  provider nếu endpoint hỗ trợ; nếu không, đối chiếu hoặc để owner xử lý rõ ràng.
- Nút Hủy trước gửi chặn write. Đảo thao tác đã gửi là một hành động mới cần
  duyệt, không tự xóa remote object để giả lập rollback.

**Nghiệm thu:** không có external write trước click; đúng đích/nội dung đã duyệt;
expiry/revoke/stale/duplicate/timeout có tests; xác minh từng provider thật sau
owner cấp quyền. Push code, merge PR, workflow, email và chi tiền chưa nằm trong
chặng này; muốn thêm cần một phạm vi được duyệt riêng.

## 8. Phase 7F — Chạy thường trực và phục hồi

- Dockerfile/Compose, image có dependency pin, user không phải root, health
  check và graceful shutdown. Không đóng gói .env, DB, backup, private key vào image.
- Triển khai một process bot/scheduler. Dùng SQLite persistent volume cho quy
  mô hiện tại; PostgreSQL là nhánh có điều kiện khi cần nhiều process/worker,
  phải có kế hoạch chuyển dữ liệu và bộ tests riêng, không đổi chỉ để có tên stack.
- Linux/VPS có chính sách restart, đồng bộ giờ, giới hạn log/AI, outbound access
  tới Discord/OpenAI/provider đã bật. Không cần cổng web công khai cho UI Discord.
- Backup nhất quán qua SQLite backup API; mặc định đề xuất một bản/ngày, giữ
  7 bản ngày và 4 bản tuần. Có bản sao riêng ngoài máy chủ, mã hóa và kiểm tra
  quyền; owner quyết định nơi lưu/retention trước bật. Không gửi DB qua Discord.
- Thử restore sang môi trường sạch: integrity/FK/owner/schema và dữ liệu phải
  khớp snapshot. Ghi rõ các thay đổi sau backup không có trong snapshot; không
  ghi đè DB hiện tại để thử. RPO đề xuất tối đa 24 giờ khi backup ngày; mục tiêu
  RTO 60 phút phải đo qua diễn tập, không coi là cam kết đã đạt.
- Theo dõi readiness từng kết nối, job lỗi, backup quá hạn; lỗi chỉ log metadata.
  Khi Discord mất kết nối, lưu lỗi cục bộ và báo cho owner khi gửi lại được;
  kênh cảnh báo ngoài Discord chỉ thêm khi có consent riêng.

**Nghiệm thu:** restart máy vẫn lên đúng một bot, dữ liệu giữ nguyên, thử mất
mạng/AI/provider có fallback rõ, backup/restore thành công, smoke test luồng
P3–6 trên máy triển khai. Không chạy đồng thời bot Windows và VPS với cùng token.

## 9. Nhóm file dự kiến và dữ liệu

| Phạm vi | Nhóm file dự kiến |
|---|---|
| 7A/7E | `app/integrations/`, services kết nối/action, models và migrations mới, tool registry/gateway/policy, màn Kết nối |
| 7B–7D | domain/repository/service riêng cho goal/note/habit/finance; UI/renderers tương ứng; mở module khi backend thật đã đạt |
| Báo cáo/AI | Mở rộng ReportService/ToolGateway có kiểm soát, source attribution, data minimization và giới hạn theo chủ đề |
| Vận hành | Dockerfile, compose, .dockerignore, deploy/runbook, health/backup tooling và CI tests phù hợp |
| Nghiệm thu | `tests/`, báo cáo từng chặng, cập nhật hướng dẫn người dùng; README/ROADMAP chỉ ghi DONE khi đạt |

Tên file/revision ban đầu là dự kiến. 7A.1 đã chốt `0007_connections`, chỉ thêm
metadata table; các bảng/chặng còn lại chưa triển khai. Không dùng create_all/
drop_all/stamp hoặc sửa migration P1–6 để triển khai P7.

Trước mỗi migration: bot dừng có kiểm soát, backup mới không ghi đè, thử upgrade
và restore trên bản sao có dữ liệu, so sánh mọi cột/bản ghi cũ. Downgrade có dữ
liệu mới phải từ chối; rollback ưu tiên tắt chức năng và giữ schema additive.

## 10. Tests và điều kiện chốt

Mỗi chặng phải chạy linter, format và toàn bộ hồi quy hiện có cùng tests mới;
ghi số thực chạy, không coi baseline 803 là kết quả mới. Mock Discord/OpenAI và
provider trong unit/integration tests, không dùng dữ liệu thật làm fixtures.

Bắt buộc có kiểm thử quyền owner ở command/button/select/modal/DM/tool/job,
stale/TTL/idempotency/rollback, token trong HTTP error, nguồn bị thu hồi,
prompt injection, lịch local/DST và quota. Core CRUD vẫn dùng được khi AI hoặc
connector hỏng. Phép thử ngoài thật chỉ gọi nguồn/thao tác đã được owner cấp
quyền và không được tự ghi là đã làm từ bằng chứng mocks.

Chốt P7 khi **7B, 7C, 7D và 7F** đạt: bốn module Goals/Notes/Habits/Finance có
CRUD/tests thật, có hướng dẫn vận hành và restore drill đạt. Với 7A, nghiệm thu
provider owner chọn; muốn công bố khả năng tổng hợp nguồn ngoài phải thử thật
ít nhất một provider đã kết nối. 7E chỉ bắt buộc nếu owner chọn mở hành động
bên ngoài. Tích hợp được chọn không vượt quyền và owner nghiệm thu trải nghiệm
trên Discord. Google/Gmail, voice, web dashboard, multi-tenant và tự chạy
shell/coding agent không tự được mở bởi kế hoạch này.

## 11. Việc owner cần chuẩn bị khi bắt đầu 7A

1. Chọn repo GitHub và trang/nhóm trang Notion dùng thử; có thể bắt đầu một
   provider nếu chỉ dùng một dịch vụ. Chưa cần mua hạ tầng.
2. Khi triển khai tới bước kết nối, tạo credential đúng quyền; lưu trực tiếp
   trên máy hoặc secret manager. Không gửi token cho Codex qua chat.
3. Chọn những loại nội dung NOVA được đọc và loại việc muốn nó giúp tổng hợp.
4. Nghiệm thu 7A trước khi cấp quyền ghi ra ngoài hoặc chuyển sang chặng kế tiếp.

Điểm khởi động 7A.1 đã thực hiện và báo cáo riêng. Theo yêu cầu tiếp tục của
owner, đã triển khai code/tests **7A.2 GitHub chỉ đọc qua UI**, dừng chờ token/
phạm vi và thử provider thật. Chưa tự chuyển Notion hoặc tools AI đọc nguồn.
