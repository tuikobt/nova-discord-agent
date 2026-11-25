# Phase 7A.2 — GitHub chỉ đọc

Ngày: 2026-11-25. Code và kiểm thử tự động đạt; **chưa nghiệm thu GitHub thật**.
Chưa có GITHUB_READ_TOKEN hoặc kết nối GitHub được owner duyệt khi bắt đầu.
Dừng ở checkpoint này; không triển khai Notion, tools AI/import (7A.3–4),
Goals/Notes/Habits/Finance, external writes hoặc deploy.

## Phạm vi đã làm

- `/menu` → Cài đặt → Kết nối & chẩn đoán → chọn kết nối → Đọc GitHub.
  Chọn repo đã Duyệt để xem metadata, issues/PR theo trang/trạng thái, nội dung
  một issue/PR hoặc một tài liệu được nhập đường dẫn rõ ràng.
- Sources do backend dựng, có thời điểm lấy theo timezone Settings. Dữ liệu
  là kết quả API thật khi có kết nối; empty/error không giả tổng repo là 0.
  API issues có thể chứa PR; lọc PR riêng, giải thích trang rỗng và trang tiếp.
- Không gửi nội dung GitHub cho LLM, không tạo task, không lưu raw content vào
  database/cache/log. Nội dung là dữ liệu không tin cậy, hiển thị đã escape;
  SecretFilter lọc credentials trước khi trả DTO.
- Owner/provider/resource/version/disconnected kiểm tra trước đọc, sau kết
  quả và sau hàng đợi ngay trước HTTP. Thu hồi/sửa scope giữa lượt làm kết quả
  cũ bị loại; không giữ DB transaction trong khi gọi mạng.
- Kiểm tra dịch vụ gọi metadata, issues, pulls và contents root cho từng repo
  đã duyệt. Chỉ verified khi cả bốn đọc thành công trên toàn bộ phạm vi.
  Đây là kết quả lần kiểm tra gần nhất; mỗi lần đọc vẫn xác thực quyền với GitHub.
  Repo rỗng có thể không vượt phép thử contents; không báo quyền đã xác minh
  chỉ từ việc token có giá trị hoặc metadata đọc được.

## HTTP và giới hạn

REST version `2026-03-10`, chỉ GET tới `https://api.github.com`, endpoint repo /
issues / pulls / contents cố định. Không theo redirect, html_url/download_url,
attachments, pagination URL, submodule hoặc origin tùy ý. API trả symlink/file
trong repo theo chính sách Contents; NOVA không tự tải target hoặc URL ngoài.

Mỗi read là một API call; list tối đa 10 kết quả, page 1–100. Next là khả năng
còn trang khi API trả đủ 10 mục, không phải tổng chính xác. Document tối đa
32 KiB UTF-8, một file/click; chỉ .md/.txt/.rst/.adoc hoặc README/LICENSE/
CHANGELOG/NOTICE/COPYING. Từ chối path ẩn, traversal, URL, binary và submodule.
Body issue/PR tối đa 6.000 ký tự ở DTO; Discord rút gọn thêm và có link đọc đủ.

Response JSON stream tối đa 256 KiB, không decompress response; HTTP timeout
8s/connect 3s; service read deadline 15s; diagnostic toàn phạm vi 10s, tối đa
40 calls (10 repo × 4 endpoint) nếu đủ thời gian. Request được tuần tự hóa,
tối đa 60/phút trong process. Không tự retry; tôn trọng Retry-After và reset
của GitHub, giữ cooldown tối thiểu 60s với lỗi rate limit. HTTP error body
không được đọc, không đưa raw exception vào thông báo. Lỗi provider không
chặn core CRUD hoặc worker hiện có.

## Cấu hình trên máy

Tạo fine-grained PAT giới hạn đúng repo cần dùng, chỉ quyền repository:
**Metadata: Read**, **Issues: Read**, **Pull requests: Read**, **Contents: Read**.
Không cần quyền push, administration, workflows hoặc bất kỳ quyền write nào.
Token có quyền rộng hơn cũng không vượt allowlist của NOVA; nên giới hạn ở cả
GitHub và NOVA. App installation token đọc đúng các quyền cũng dùng được, nhưng
chưa có luồng cấp/refresh App token tự động.

Lưu GITHUB_READ_TOKEN trực tiếp trong `.env`/secret manager, restart bot rồi
tạo và Duyệt phạm vi qua Discord. Không gửi token trong chat/modal/Git. Không
sửa DATABASE_URL hoặc tạo lại database. `.env` thật không được thay trong lần này.

Nguồn đã đối chiếu khi triển khai:
[API versions](https://docs.github.com/en/rest/about-the-rest-api/api-versions),
[repository contents](https://docs.github.com/en/rest/repos/contents?apiVersion=2026-03-10),
[repository issues](https://docs.github.com/en/rest/issues/issues?apiVersion=2026-03-10#list-repository-issues),
[pull requests](https://docs.github.com/en/rest/pulls/pulls?apiVersion=2026-03-10#list-pull-requests),
[rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api).

## File thay đổi riêng checkpoint này

| Nhóm | File |
|---|---|
| Adapter | app/integrations/github.py, errors.py; protocol.py thêm callback kiểm tra quyền trước request |
| Service | app/services/github_service.py; connection_service.py chuyển callback owner/version cho probe |
| Runtime | app/discord_bot/client.py đăng ký reader/probe, close HTTP session; logging_config.py tắt log HTTP SDK; requirements.txt pin aiohttp đã có sẵn 3.14.5 |
| UI | app/discord_bot/github_controller.py; connections_controller.py; renderers/connections.py |
| Tests | tests/test_github_reader.py, test_github_service.py, test_github_discord.py; cập nhật text assertion test_connections_discord.py |
| Docs | README, ROADMAP, PHASE_7_PLAN, ARCHITECTURE, DATABASE, DISCORD_UI, AGENT_TOOLS, SECURITY, HUONG_DAN_SU_DUNG; báo cáo này; .env.example |

Giữ nguyên toàn bộ thay đổi 7A.1 chưa commit trên nhánh `feat/phase-6`.
Không stage/commit/push, không sửa migrations/schema hoặc dữ liệu P1–7A.1.

## Kết quả kiểm tra

Baseline kiểm tra lại trước sửa: **863 passed in 71.77s**.
Sau sửa: **961 passed in 65.34s** toàn bộ suite cuối; tăng 98 tests GitHub.
Nhóm HTTP/reader/service: **88 passed in 1.91s**. Nhóm GitHub/UI + hồi quy
connections: **145 passed in 5.08s** trước lần full cuối.

Kiểm thử chặn network thật; mock Discord/OpenAI/HTTP, SQLite tạm. Bao gồm
401/403/404/429/redirect/timeout/network, stream quá lớn, binary/base64/type,
rate budget/cooldown, pagination/PR filtering, nguồn từ backend, credential
redaction, owner/scope/provider/version, ngắt/sửa khi request chờ hoặc đang
trả về, modal TTL, Discord limits và không gửi external text tới AI.

Lệnh đã chạy: `python -m pytest -q`, `python -m ruff check .`,
`python -m ruff format .`, `python -m compileall -q app alembic tests`,
`python -m app.security_check --history --staged`, `git diff --check`,
`python -m app.preflight`, `python -m alembic check`
(tất cả dùng `.venv/Scripts/python.exe`). Preflight đạt mọi mục;
Alembic: `No new upgrade operations detected.` Ruff format xác nhận 190 files;
security scan working tree/index/history: 327 reachable blobs, findings rỗng
(patterns không bảo đảm phát hiện mọi secret).

Runtime bản cuối: **2026-11-25 16:38:14 UTC** đăng ký 4 commands,
**16:38:17 UTC bot_online** (23:38:17 VN), chạy lại sau khi tắt logging aiohttp.
Không tự đọc repo hoặc gọi OpenAI để nghiệm thu; startup chỉ có kết nối Discord.

## Database, backup và rollback

Không thêm migration. Revision vẫn `0007_connections`. Đã dừng bot và xác nhận
không còn app.main trước backup mới bằng SQLite backup API:
`backups/pre-phase7a2-20261125-232712.db`, integrity OK. Đây là thời gian VN.

Đã restore snapshot sang file riêng
`backups/phase7a2-restored-20261125-232712.db`: integrity/FK đạt, toàn bộ
15 bảng (gồm Alembic và connection) khớp snapshot. Sau restart, schema/rows DB
đang dùng cũng khớp backup. Không chép đè database đang chạy để thử restore.

Rollback ưu tiên ngừng dùng nút đọc hoặc ngắt connection có Duyệt. Nếu cần
quay về source 7A.1: dừng bot, giữ backup mới, dùng đúng bản source đã lưu của
7A.1 và khởi động lại đúng một bot; schema tương thích, không cần downgrade.
Không `git reset --hard` vì 7A.1 và 7A.2 đang cùng có thay đổi chưa commit.
Không xóa bảng/connection/pending_actions để rollback; không phục hồi snapshot
đè DB đang chạy. Restore cần chọn file mới, kiểm tra integrity/FK/owner và
ghi nhận dữ liệu sau backup sẽ không có trong snapshot.

## Checklist thử thật còn chờ owner

1. Cấu hình token đọc tối thiểu trực tiếp trên máy, restart đúng một bot.
2. Tạo phạm vi GitHub một repo do bạn chọn, đọc proposal rồi Duyệt.
3. Bấm Kiểm tra dịch vụ; mở lại chi tiết nếu phiên/version đã thay đổi.
4. Đọc GitHub → chọn repo → metadata, issues/PR, một mục chi tiết và README.md.
   Đối chiếu link nguồn với GitHub; không nhập token trong Discord.
5. Thử đổi scope/ngắt và mở lại panel cũ: không đọc/hiển thị kết quả scope cũ.
6. Ghi riêng kết quả live; unit tests không thay thế bước này. Notion và tools
   đọc GitHub bằng DM thuộc checkpoint sau, chưa tự chuyển tiếp.
