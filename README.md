# NOVA AI — Discord Personal Assistant

> **Trạng thái:** Phase 0 (Planning & Design) **hoàn thành**. Chưa có mã bot chạy thực tế.
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
| — | [`AGENTS.md`](AGENTS.md) | Quy ước bắt buộc dành cho Codex/AI lập trình |

## Trạng thái module

| Module | Thời điểm xây | Trạng thái |
|---|---|---|
| Discord Bot, owner-only access, `/ping`, `/menu` | Phase 1 | Chưa bắt đầu |
| Dashboard, menu, button, modal, settings shell | Phase 2 | Chưa bắt đầu |
| Tasks, Projects, Calendar | Phase 3 | Chưa bắt đầu |
| Reminders tự động | Phase 4 | Chưa bắt đầu |
| AI Agent, chat tự nhiên, function tools | Phase 5 | Chưa bắt đầu |
| Memory, planner thông minh, daily/weekly reports | Phase 6 | Chưa bắt đầu |
| Goals, Finance, Habits, Notes, integrations, deploy | Phase 7+ | Chưa bắt đầu |

## Cấu trúc dự kiến (chỉ là thiết kế — chưa có source code)

```text
nova-discord-agent/
├── README.md
├── AGENTS.md
└── docs/
    ├── PRD.md
    ├── ARCHITECTURE.md
    ├── DATABASE.md
    ├── DISCORD_UI.md
    ├── AGENT_TOOLS.md
    ├── ROADMAP.md
    ├── SECURITY.md
    └── PHASE_1_HANDOFF.md
```

## Tiếp tục sang Phase 1 (Windows PowerShell)

1. Giải nén thư mục `nova-discord-agent` ở vị trí bạn muốn trên máy tính.
2. Mở PowerShell trong thư mục đó (nơi có file `AGENTS.md` và `README.md`).
3. Khởi tạo Git nếu chưa có: `git init`.
4. Mở Codex CLI: `codex`.
5. Dán yêu cầu ở cuối [`docs/PHASE_1_HANDOFF.md`](docs/PHASE_1_HANDOFF.md).
6. Chỉ chuyển sang Phase 2 khi Phase 1 đạt toàn bộ tiêu chí nghiệm thu.

**Chưa cần** Discord Bot Token, OpenAI API Key, VPS hay PostgreSQL khi chỉ đọc và duyệt Phase 0. Không đưa token/API key vào prompt, source code hay Git.

## Những quyết định đã chốt

- **Một chủ tài khoản** (allowlist Discord Owner ID), server riêng, **DM là giao diện trò chuyện chính**.
- Giao diện server có **4 kênh chức năng** để giảm sự phức tạp; không tạo hàng chục channel.
- **Zero-command by default:** người dùng có thể chọn nút/menu, slash commands chỉ để vào nhanh.
- **Giao diện dashboard thực sự nằm trong Discord**, không phải website được vẽ giống Discord.
- MVP làm lần lượt; module chưa xây hiển thị **“Sắp ra mắt”**, không trả dữ liệu giả.
- **Python + discord.py + SQLAlchemy + SQLite** ban đầu; **OpenAI Responses API** khi tới Phase 5.
- Các thay đổi lịch quan trọng, xóa dữ liệu, thao tác bên ngoài đều có bước xác nhận.

## Tài liệu tham khảo chính thức

- Discord Interactions: https://docs.discord.com/developers/topics/interactions
- Discord Components: https://github.com/discord/discord-api-docs/blob/main/developers/components/overview.mdx
- Discord Application Commands: https://docs.discord.com/developers/docs/interactions/slash-commands
- OpenAI Function Calling: https://developers.openai.com/api/docs/guides/function-calling
- discord.py docs: https://discordpy.readthedocs.io/en/stable/