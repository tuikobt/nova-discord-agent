# PRD — NOVA AI Personal Assistant

**Version:** 1.0 Draft (Phase 0) · **Ngày:** 2026-10-23 · **Trạng thái:** Design baseline — sẵn sàng làm đầu vào Phase 1

## 1. Bài toán

Người dùng muốn quản lý tất cả việc cá nhân từ một nơi nhưng **không muốn ghi nhớ nhiều lệnh, ứng dụng hoặc workflow**. Discord là giao diện đã quen. NOVA phải giảm thao tác bằng cách **chat tự nhiên + dashboard bấm nút**, chủ động nhắc và đề xuất chứ không thay người dùng quyết định những việc quan trọng.

## 2. Người dùng mục tiêu và phạm vi

- **Persona chính:** một chủ tài khoản Discord (owner), dùng điện thoại và máy tính.
- **Phạm vi:** server riêng và DM; một múi giờ mặc định `Asia/Ho_Chi_Minh`; giao diện tiếng Việt.
- **Không nằm trong MVP:** nhiều người dùng, website, thanh toán, kết nối tài khoản ngân hàng, đăng nội dung công khai, quản lý sức khỏe y khoa, voice assistant.
- **Nguyên tắc:** mọi thao tác phải có đường đi qua UI; slash commands là lối tắt, không là điều kiện bắt buộc.

## 3. Mục tiêu thành công

1. Người dùng có thể mở `/menu`, nhìn thấy module và điều hướng mà không cần học lệnh con.
2. Tạo task, calendar event, reminder từ Discord; dữ liệu còn nguyên sau restart.
3. Dashboard phản ánh số liệu từ database; không hiển thị mẫu giả như dữ liệu thật.
4. Nhắc việc đúng mốc đã định với múi giờ chính xác, có chiến lược retry và chống lặp.
5. AI có thể hiểu yêu cầu bằng tiếng Việt, tra cứu và đề xuất action; không tự ý thực thi action nhạy cảm.
6. Daily briefing/review chủ động nhưng có thể tắt, cấu hình giờ và quiet hours.
7. Chỉ owner được đọc hoặc sửa dữ liệu; người khác không thấy thông tin riêng tư qua bot.

## 4. Trải nghiệm cốt lõi (job stories)

| ID | Khi tôi... | Tôi muốn... | Để... | Mốc |
|---|---|---|---|---|
| US-01 | Mở Discord | Có dashboard tổng quan kèm nút chọn module | Không nhớ lệnh | P2 |
| US-02 | Nhớ ra việc cần làm | Tạo task qua biểu mẫu | Không quên việc | P3 |
| US-03 | Có nhiều việc trong ngày | Xem lịch, tìm giờ trống, kiểm tra xung đột | Không quá tải | P3 |
| US-04 | Có deadline | Đặt nhắc trước một khoảng thời gian | Không bỏ lỡ | P4 |
| US-05 | Nhắn tự nhiên | AI phân tích, chọn tool phù hợp và phản hồi | Không nhập cú pháp | P5 |
| US-06 | Ngày mới bắt đầu | Nhận kế hoạch sáng có thể chấp nhận/sửa | Bắt đầu nhanh | P6 |
| US-07 | Có lịch đột xuất | AI đề xuất dời lịch, đợi tôi duyệt | Giữ quyền kiểm soát | P5–P6 |
| US-08 | Đến cuối ngày | Nhận review dựa trên dữ liệu thực | Theo dõi hiệu suất | P6 |
| US-09 | Hỏi về thói quen hoặc mục tiêu | AI sử dụng sở thích đã xác nhận | Tư vấn cá nhân hóa | P6–P7 |
| US-10 | Ghi chi tiêu hoặc note | Có module tương ứng trên dashboard | Dùng một nơi | P7 |

## 5. Phạm vi module theo release

### Foundation / Dashboard (Phase 1–2)
- Bot online, giới hạn owner, `/ping`, `/menu`, `/help`, `/settings`.
- Dashboard: tổng quan, điều hướng module, trạng thái “Sắp ra mắt”, nút Refresh, back, modals phù hợp.
- Server chính: `#nova-dashboard`, `#nova-chat`, `#nova-notifications`, `#nova-reports` (tên có thể điều chỉnh).
- DM là nơi chat; `#nova-chat` có thể chứa lời mời chuyển sang DM khi AI chat chưa có.

### Core MVP (Phase 3–5)
- **Tasks:** tạo/sửa/hoàn thành/đánh dấu ưu tiên/đặt deadline/liên kết project.
- **Projects:** tạo/sửa/trạng thái, task liên quan, tiến độ theo tỷ lệ task đã xong (ghi rõ cách tính).
- **Calendar:** sự kiện cố định, block công việc, đề xuất lịch có trạng thái `proposed`, xác nhận thành `confirmed`; phát hiện xung đột theo thời điểm.
- **Reminders:** một lần + lặp đơn giản; DM hoặc private channel; hoãn/hủy.
- **AI Chat & Agent:** hỏi đáp; đọc tasks/lịch; tạo task hoặc reminder theo lời yêu cầu rõ ràng; đề xuất và xin duyệt lịch hoặc bulk updates.

### Intelligence & Expansion (Phase 6–7+)
- Lập lịch bằng AI dựa trên sự kiện cố định, thời gian rảnh, mức độ ưu tiên.
- Morning briefing, daily review, weekly planning; memory dài hạn có thể xem/sửa/xóa.
- Goals, Habits, Finance (ghi thu/chi thủ công), Notes, báo cáo, integrations OAuth riêng.
- VPS + Docker + PostgreSQL, monitoring, backup.

## 6. Ví dụ yêu cầu bằng ngôn ngữ tự nhiên

| Tin nhắn | Hành vi thiết kế |
|---|---|
| “Mai tôi cần làm gì?” | Đọc tasks/events của ngày mai, trả câu trả lời có nguồn nội bộ |
| “Thêm việc học Docker, hạn thứ sáu” | Parse ngày theo timezone, hỏi rõ nếu mơ hồ, tạo task khi rõ |
| “Cho tôi lịch trống chiều mai” | Trả danh sách slot rảnh |
| “Dời toàn bộ lịch chiều nay sang tối” | Tạo đề xuất (không commit), hiển thị nút Duyệt/Từ chối |
| “Nhắc tôi tập thể dục lúc 18h mỗi ngày” | Tạo recurring reminder từ yêu cầu rõ ràng |
| “Hôm nay tiêu 50k ăn sáng” | Khi module Finance P7 bật: xác định giao dịch, lưu theo chế độ cấp quyền |
| “NOVA giúp tôi” | Xem overview/tasks, gợi ý 1–3 hành động tiếp theo |
| “Bạn nhớ gì về tôi?” | Hiển thị memory entries được cấp quyền và nguồn gốc |

## 7. Functional requirements & mức ưu tiên

**Must:** Owner-only, `menu`, task CRUD, project CRUD, calendar events, reminder persists/retry, AI tool gating, xác nhận thao tác nhạy cảm, lịch UTC + timezone, logs, basic tests.

**Should:** Dashboard có pagination/refresh; cấu hình giờ báo cáo; thoát/bỏ qua, short-term chat, dark Discord-friendly embeds, chỉ DM thông tin riêng tư.

**Could:** finance, habits, goals, notes, integrations, charts, voice. Không nằm trong nghiệm thu MVP.

## 8. Non-functional requirements

- **Bảo mật:** không log secret; owner allowlist ở mỗi interaction; least privilege OAuth/Discord; xác thực tools server-side; chống prompt injection từ user content/tài liệu.
- **Dữ liệu:** migration, foreign keys, transaction, backup/restore test; không mất task sau restart.
- **Độ tin cậy:** scheduler nhắc việc qua DB, retry có giới hạn; phân biệt scheduled vs sent; xử lý thiếu DM permissions.
- **UX:** hiển thị lỗi tiếng Việt; tối đa 1–3 bước cho việc thường gặp; trang tổng quan ít chữ, rõ CTA; không spam channel.
- **Hiệu suất:** thao tác đọc/click không phụ thuộc API AI; AI xử lý bất đồng bộ, phản hồi trạng thái kịp thời.
- **Khả năng quản lý chi phí:** model được cấu hình từ `.env`, theo dõi lượng sử dụng, đặt ngân sách; có fallback nếu AI lỗi.

## 9. Quyền thực thi

- **Đọc/trả báo cáo:** tự động khi owner yêu cầu hoặc automation đã bật.
- **Tạo một đối tượng với yêu cầu rõ ràng** (task, reminder, note): có thể tự thực hiện trong phạm vi đã cho phép, luôn thông báo kết quả; hỏi khi thiếu thông tin.
- **Dời/xóa lịch đã xác nhận; xóa/bulk sửa; thay đổi mục tiêu lớn:** chỉ lưu `pending_action`, đợi duyệt.
- **Gửi email/đăng nội dung bên ngoài hoặc thao tác tích hợp nhạy cảm:** yêu cầu kết nối và xác nhận riêng.

## 10. Đo lường thành công

- Hoàn thành ≥ 90% luồng test nghiệm thu trong tài liệu roadmap trước khi chuyển phase.
- 100% action nhạy cảm đã được chặn nếu không có owner confirmation.
- 100% thao tác CRUD cơ bản lưu bền vững sau restart trong test.
- Không có đường truy cập dữ liệu của người không được cho phép trong các test security.
- Thông báo thất bại được ghi nhận rõ thay vì tuyên bố đã gửi.

## 11. Ranh giới, giả định, rủi ro

- Không có lịch sử Google Calendar khi chưa kết nối. Bot **chỉ biết lịch người dùng đã tạo/lưu**.
- Discord UI không phải web app tự do: dùng embeds/views/components phù hợp khả năng nền tảng.
- Discord DM có thể bị chặn bởi privacy settings; fallback sang kênh riêng đã cấu hình.
- AI có thể hiểu sai ngày giờ, nội dung; dự án cần hỏi lại trong trường hợp mơ hồ.
- Tỷ lệ hoàn thành task không đồng nghĩa tiến độ kỹ thuật thực tế; hiển thị quy tắc tính.
- Đơn vị “nhắc đúng giờ” phụ thuộc uptime/network; không cam kết chính xác tuyệt đối tới giây.

## 12. Acceptance cho *Phase 0* này

- [x] Xác định user persona, giao diện DM + server, nguyên tắc zero-command.
- [x] Xác định phạm vi MVP và module tương lai.
- [x] Viết kiến trúc, data model, UI flow, tool policies, roadmap và handoff.
- [x] Nêu quyết định kỹ thuật và giới hạn nền tảng.
- [ ] Người dùng duyệt thay đổi nếu có; **không phải điều kiện để đọc/bắt đầu Phase 1**.
