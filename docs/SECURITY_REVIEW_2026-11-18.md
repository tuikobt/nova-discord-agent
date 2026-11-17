# Security review trước Phase 6 — 2026-11-18

Phạm vi: an toàn khi push GitHub, dữ liệu qua LLM, prompt/output và logs. Không triển
khai P6, không migrate database, không gọi OpenAI để thử tấn công, không commit/push
hoặc rewrite Git history trong lần review. Nền `ba2be72` trên `feat/phase-5`, khớp
`origin/feat/phase-5` theo refs cục bộ lúc bắt đầu.

## Kết quả Git

- Quét **239 blob reachable** từ tất cả local refs, sau đó kiểm tra cả index và working
  tree. Không phát hiện mẫu OpenAI/Discord/GitHub token, private-key header hoặc giá trị
  khớp token/key cục bộ đang cấu hình. Không in giá trị matched hoặc nội dung riêng tư.
- `.env`, `nova.db` và `backups/` bị Git ignore; tracked env file chỉ có `.env.example`
  với placeholders. Các commit chạm mẫu `.env.*` là env example; không suy ra `.env`
  thật đã từng được commit chỉ từ tên glob đó.
- Đây là kết quả quét local Git/index/working tree, không chứng minh tuyệt đối không
  có mọi loại secret. Chưa kiểm tra GitHub cached PR refs, artifacts/logs server,
  repository visibility hoặc trạng thái Push protection trên tài khoản GitHub.
- Token Discord từng được gửi trong cuộc trò chuyện trước đây. Nếu owner chưa reset
  token đó, cần reset tại Discord Developer Portal và sửa `.env`. Không dùng kết quả
  Git scan để kết luận token từng lộ trong chat vẫn an toàn. Không ghi token vào báo cáo.

## Những điểm đã sửa

| Điểm rà soát | Trước | Sau |
|---|---|---|
| Logs | Chỉ đăng ký Discord token để redact | Đăng ký cả OpenAI key, lọc thêm mẫu credential; redact trước JSON encode để giữ log hợp lệ |
| Tool context | DTO chứa owner ID, timestamps/version và descriptions trong lists | Whitelist business fields, bỏ metadata không cần thiết; chỉ get_task trả description chi tiết |
| Key trong DM/tool output | Chưa có bộ lọc tại biên LLM | Chặn input chứa key trước API/context; redact tool output/context/response; từ chối tool arguments chứa key |
| Prompt extraction | Hướng dẫn trong prompt, output chưa được kiểm tra | Chặn một số yêu cầu xuất prompt, kiểm tra echo trong response, thêm chỉ dẫn không nhắc lại nội bộ |
| Discord output | Có thể tạo link previews tự động | AI text dùng suppress_embeds và AllowedMentions.none |
| Push nhầm file | Gitignore chưa bao gồm logs/dumps/key files | Bổ sung patterns và scanner cho working tree/index/history, kể cả SQLite đổi extension |
| Trước push | Chưa có local hook | Bật `.githooks/pre-push`; scanner trả exit 1 khi có finding, exit 2 khi không kiểm tra được |
| GitHub CI | Chưa có check tương ứng | Thêm workflow permissions contents:read, no bot/API secrets, checkout pin full SHA và persist-credentials:false |

Scanner phát hiện cả blob có secret đã stage dù file working tree được sửa sạch,
và secret trong commit cũ đã bị xóa/rename. Tên file có mẫu key cũng bị che khi báo cáo.
Tests dùng credential giả được ghép lúc runtime, không commit chuỗi token-shaped.

## Prompt cần hiểu như thế nào

NOVA gửi `PROMPT` qua trường Responses `instructions` để hướng dẫn ngôn ngữ/cách dùng
tools; tin nhắn owner và tool results nằm trong input. Chỉ dẫn này có thể nằm trong
source public, không chứa token, API key hoặc mật khẩu database. Chuyển nguyên prompt
sang `.env`, đổi tên biến hay mã hóa rồi giải mã trước API không tạo ra ranh giới quyền.

Model vẫn có thể suy luận hoặc diễn đạt lại quy tắc. Bộ lọc echo chỉ giảm lộ nguyên văn
và một số kiểu hỏi trực tiếp; không cam kết ngăn mọi paraphrase/base64/obfuscation.
Không có bằng chứng DM cụ thể được cung cấp trong lần review để khẳng định đã xảy ra
một incident lộ prompt; đã kiểm tra và gia cố cả source lẫn đường phản hồi.

Các kiểm soát thật tiếp tục nằm ở backend: owner guard trước đọc DM, registry/schema,
owner predicates, resource references, pending-action TTL/message/version/conflicts,
nút Duyệt, transaction/idempotency. Model không có tool approve, SQL, shell hay HTTP
tùy ý. Lộ nội dung chỉ dẫn không cấp thêm các quyền này.

OpenAI vẫn nhận nội dung hội thoại và dữ liệu nghiệp vụ cần thiết cho tool request.
Lọc key/metadata không đồng nghĩa không gửi dữ liệu cho nhà cung cấp. `store=false`
được giữ nguyên; không gọi nó là Zero Data Retention. Secret recognition theo mẫu và
giá trị đã biết không thể nhận diện mọi mật khẩu/secret do người dùng tự đặt.

Nguồn: [OWASP LLM07 System Prompt Leakage](https://genai.owasp.org/llmrisk/llm072025-system-prompt-leakage/).

## Kiểm tra và sử dụng

Kết quả tự động cuối: `python -m pytest -q` **719 passed in 60.80s** (32 cases bảo
mật mới cùng 687 tests hồi quy), Ruff check/format đạt, compileall và diff check đạt.
Tests mock Discord/OpenAI và chặn network; bao gồm chặn input trước API, prompt echo,
redaction nested/tool replay/logs, minimization, index khác working tree, history
đã xóa/rename, private key multiline và filename có credential. Không gọi API tính phí
để thử lộ prompt. Preflight config/AI/integrity/FK/schema/owner/settings đạt.

```powershell
.\.venv\Scripts\python.exe -m app.security_check --history --staged
git config --local core.hooksPath .githooks
git hook run pre-push
```

Hook đã được bật trên máy review (`core.hooksPath=.githooks`) và chạy thử không có
push/network, scan 239 blobs đạt. Git Bash trong sandbox Windows ban đầu gặp lỗi
signal pipe; chạy lại ngoài sandbox đạt. Máy clone mới/Linux khác cần bật hook lại.
Hook là cấu hình local và có thể bị bỏ qua; không thay thế protection trên GitHub.
Trên Linux, chạy thêm `chmod +x .githooks/pre-push`. Khi stage/commit hook từ Windows,
cần giữ executable bit cho bản Git bằng `git update-index --chmod=+x .githooks/pre-push`
sau khi đã chủ ý stage file; lần review này không tự stage thay người dùng.

Workflow `.github/workflows/security.yml` được thêm nhưng chưa push/chạy trên server.
CI chạy sau khi nội dung được gửi lên GitHub, nên **không dùng CI làm bảo vệ duy nhất
chống upload secret**. Checkout v7.0.1 pin
`3d3c42e5aac5ba805825da76410c181273ba90b1`, xác minh từ release/commit chính thức.
CI không cần cài runtime bot hoặc nhập DISCORD_TOKEN/OPENAI_API_KEY vào GitHub Secrets.

Owner cần xác nhận/bật GitHub Secret scanning và Push protection nếu repository/gói
tài khoản hỗ trợ; không có connector/CLI authenticated để xác minh hay bật thay trong
lần review. Nguồn [GitHub Push protection](https://docs.github.com/en/code-security/how-tos/secure-your-secrets/prevent-future-leaks/enable-push-protection).

Nếu scan phát hiện key thật: dừng push, revoke/rotate key trước, rồi xử lý file/index/
history. Không tự force-push hay rewrite lịch sử đã chia sẻ. Xóa file ở commit mới
không xóa credential trong commit cũ. Nguồn [GitHub sensitive data removal](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository).

## File thay đổi và rollback

- `.gitignore`, `.gitattributes`, `.githooks/pre-push`, `.github/workflows/security.yml`.
- `app/security.py`, `app/security_check.py`, `app/agent/privacy.py`.
- Agent orchestrator/controller, logging_config và main; thêm `tests/test_security_review.py`.
- Báo cáo này và hướng dẫn Security/README/ROADMAP.

Không đổi schema hay business records. Muốn tắt hook local: `git config --local --unset
core.hooksPath` (trước review không có hooksPath riêng). Không tắt hook chỉ để vượt finding
chưa xử lý. Khôi phục code qua Git diff/commit cụ thể sau khi review, không reset cả working
tree vì có thể mất thay đổi khác. Phần gia cố chưa commit/push; P6 chưa bắt đầu.
