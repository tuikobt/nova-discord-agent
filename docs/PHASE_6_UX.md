# Điều chỉnh trải nghiệm Phase 6

Người dùng phản hồi giao diện khó hiểu và yêu cầu hướng dẫn sử dụng. Thay đổi
này tập trung vào Discord, không thay schema hay cài đặt đang lưu.

## Thay đổi

- Trang chính dùng tiếng Việt, ưu tiên Nhắn NOVA/Hôm nay/Việc cần làm; Kế hoạch
  & báo cáo truy cập trực tiếp. Bỏ danh sách dài chức năng chưa triển khai.
- Hướng dẫn trong `/help` theo bốn việc thường làm, có nút chuyển tới màn hình
  cần dùng. Tài liệu cho người sử dụng: [HUONG_DAN_SU_DUNG](HUONG_DAN_SU_DUNG.md).
- Tách chọn báo cáo, cài lịch gửi và lịch sử. Lập kế hoạch hôm nay/tuần tới bằng
  nút; ngày khác chọn một ngày hoặc tuần, không nhập số 1/7.
- Giờ làm có nút chọn nhanh Thứ Hai–Thứ Sáu/Cả tuần. Loại ghi nhớ và thứ trong
  tuần chọn bằng tên; không yêu cầu nhập enum hay mã weekday.
- Bản duyệt P6 hiển thị nội dung, ngày giờ local, tên loại và trước/sau. Giữ
  đầy đủ nội dung, phân trang và nút Duyệt ở trang cuối. Nơi nhận kênh hiển thị
  liên kết kênh để owner biết đang duyệt gửi tới đâu.
- Điều hướng đọc cập nhật bảng riêng đang xem; từ bản tin thông báo vẫn mở
  riêng tư để không ghi đè tin đã gửi. Owner/message/channel/expiry checks giữ
  nguyên. Tên nút đổi nhưng custom_id bảng neo cũ giữ nguyên; nhận cả tiêu đề
  dashboard cũ khi cập nhật qua `/menu`.

## Phạm vi và nghiệm thu

P6 đã có chức năng và bộ tự động trước thay đổi là 780 tests pass. Phản hồi
“khó hiểu” là yêu cầu cải thiện UX, chưa phải xác nhận nghiệm thu ở thời điểm đó.
Sau cải thiện UX và sửa kết nối DM, owner yêu cầu chốt P6 DONE ngày 2026-11-24.
Kết quả cuối cùng 803 tests pass tại [báo cáo sửa lỗi DM](DM_CONNECTION_FIX_2026-11-24.md).
Không tự bật bản tin, đổi giờ làm, sửa ghi nhớ hoặc đổi dữ liệu nghiệp vụ.

Tests mới kiểm tra hướng dẫn/owner guard, giữ ID cũ, chọn loại/weekday trước
proposal, ngày lập kế hoạch local, preset không ghi ngay, phân trang/duyệt và
privacy khi chuyển màn hình.

Kết quả đã chạy ngày 2026-11-24:

- `python -m pytest -q --disable-warnings --maxfail=2`: **790 passed in 75.93s**.
- `python -m ruff check app tests alembic`: đạt.
- `python -m ruff format --check app tests alembic`: 140 files đã đúng format.
- `python -m compileall -q app` và `git diff --check`: đạt.
- `python -m app.security_check --history --staged`: 295 reachable blobs,
  findings=[]; không phải bảo đảm phát hiện mọi secret.
- `python -m app.preflight`: config/AI/integrity/FK/head/owner/settings đều OK.
- Dừng process cũ có log bot_stopped, xác minh không còn process Python rồi
  khởi động một bot. Sync 4 commands và bot_online lúc **21:20:05 Việt Nam**.
  Không tự bật hoặc gửi bản tin để thay cho owner nghiệm thu.

File thay đổi thuộc Discord controllers/renderers/views, UI labels, tests và
tài liệu. Không đổi DB models, migration, business services, AI policy hoặc .env.
Rollback UI có thể dùng bản P6 trước UX ở commit `62a9694` sau khi bảo toàn diff
hiện tại và dừng bot; giữ nguyên schema `0006_personal`, không cần downgrade DB.

Để thử bản mới, mở lại `/menu`: bảng neo được cập nhật bằng chính tin nhắn đã
lưu. Chọn **Hướng dẫn** → **Bắt đầu trong 5 phút**. P6 đã chốt DONE theo xác nhận
tổng thể của owner; phạm vi bằng chứng tại [báo cáo P6](PHASE_6_VALIDATION.md).
P7 chưa bắt đầu.
