# Handoff — Bắt đầu Phase 1 với Codex CLI

## 1. Bạn đang có gì?

Bộ Phase 0 này **chỉ gồm tài liệu**. Trong thư mục project chưa có Python bot, token, database hoặc dashboard đang chạy. Điều đó là đúng kế hoạch: Phase 1 mới viết code.

## 2. Bạn cần chuẩn bị

- Python 3.12+ và Git cài trên máy.
- Codex CLI đã đăng nhập.
- Discord account + một private server.
- Discord application/bot token và Discord user ID owner (chỉ cần khi chạy bot, không cần khi tạo source).
- Chưa cần OpenAI API key khi Phase 1 không tích hợp AI.

### PowerShell — bước chạy

```powershell
# Giải nén thư mục 'nova-discord-agent' rồi mở PowerShell bên trong
pwd                         # Kiểm tra nơi có AGENTS.md và docs/
git init                    # Chỉ cần lần đầu nếu chưa là git repository
codex                       # Bắt đầu phiên Codex CLI
```

**Không copy secret/token vào cửa sổ chat Codex.** Sau khi code tạo `.env.example`, tự điền `.env` bằng trình chỉnh sửa trên máy. `DISCORD_OWNER_ID` là user ID tài khoản Discord của bạn.

## 3. Prompt copy vào Codex (chỉ Phase 1)

> Đọc `AGENTS.md`, `README.md` và tất cả tài liệu trong `docs/`. Đây là dự án NOVA AI Discord Personal Assistant đã hoàn thành Phase 0. **Chỉ xây Phase 1 (Foundation)**, không xây Phase 2 hay AI Agent.
>
> 1. Kiểm tra nội dung hiện tại, Git status và những điểm cần chú ý.
> 2. Trình bày kế hoạch ngắn theo `docs/ROADMAP.md` (Phase 1).
> 3. Tạo Python project dùng `discord.py`, SQLAlchemy 2.x, `aiosqlite`, `.env` qua `python-dotenv` hoặc settings tương đương; Python 3.12+.
> 4. Tạo `app/main.py`, config, Discord bot adapter, owner authorization guard và database bootstrap/migration `users`, `user_settings`.
> 5. Tạo slash `/ping` và `/menu` (placeholder dashboard; các module chưa có phải ghi “Sắp ra mắt”, không dữ liệu giả).
> 6. Tạo `.env.example`, `.gitignore`, dependency pins, README chạy trên Windows PowerShell, logging an toàn và tests mock.
> 7. Bảo đảm owner guard hoạt động ở commands/callbacks; không hardcode token, không log secrets. Không dùng OpenAI API ở Phase 1.
> 8. Chạy tests/lint khả dụng, nêu chính xác kết quả, tạo hướng dẫn kiểm thử Discord thực tế.
> 9. Khi toàn bộ nghiệm thu Phase 1 đạt, cập nhật `docs/ROADMAP.md`. **Dừng ở Phase 1 và không tự chuyển sang Phase 2.**

## 4. Checklist khi Codex làm xong

1. `README.md` có lệnh cài dependencies/chạy bot.
2. Có `.env.example` nhưng không chứa token thật.
3. Có `/ping` và `/menu` chạy trong Discord.
4. Chủ tài khoản thao tác được; tài khoản khác không được dùng.
5. Không có dữ liệu demo giả khi mở menu.
6. Cơ sở dữ liệu tạo được, restart vẫn hoạt động.
7. Unit tests không gọi API Discord/OpenAI thật.
8. Có báo cáo file đã tạo và phần chưa làm.

## 5. Các giá trị cấu hình dự kiến (mẫu, không phải secret)

```dotenv
DISCORD_TOKEN=replace-me
DISCORD_OWNER_ID=replace-with-your-user-id
DATABASE_URL=sqlite+aiosqlite:///./nova.db
TIMEZONE=Asia/Ho_Chi_Minh
```

Nếu Codex quyết định đặt tên env khác, hãy yêu cầu cập nhật `.env.example`, README và docs đồng nhất.

## 6. Các bước kiểm thử thủ công sau khi có bot

- Bật bot trong private server, chạy `/ping` → nhận status online.
- Chạy `/menu` → xem dashboard placeholder có các module (chưa xây ghi rõ).
- Dùng một tài khoản Discord không phải owner thử tương tác → nhận cảnh báo không có quyền, **không hiện thông tin private**.
- Restart bot → chạy lại `/ping`, `/menu` và kiểm tra DB còn đó.

## 7. Prompt gợi ý khi đã đạt Phase 1 (không chạy trước)

> Đọc AGENTS và docs. Đối chiếu toàn bộ acceptance Phase 1 với code/tests hiện tại. Nếu đã pass, mới lên kế hoạch Phase 2 — Discord Dashboard UI theo `docs/DISCORD_UI.md`. Không thay đổi phạm vi khi chưa báo cáo.
