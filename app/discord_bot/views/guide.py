"""Task-oriented help inside Discord, with links to the next useful screen."""

import discord

from app.discord_bot.views.dashboard import NavigateButton, OwnerView
from app.domain.modules import Screen

SECTIONS = {
    "start": (
        "Bắt đầu trong 5 phút",
        (
            (
                "1. Ghi lại một việc",
                "Mở **Việc cần làm** → Thêm. Ghi tên việc và thời lượng dự kiến, "
                "chẳng hạn 30 phút. Đây là việc cần làm; chưa phải lịch hay thông báo.",
            ),
            (
                "2. Xem ngày của bạn",
                "Mở **Hôm nay** để xem lịch đã xác nhận và những việc cần chú ý. "
                "Muốn hỏi tự nhiên, mở **Nhắn NOVA** rồi bấm Mở tin nhắn riêng.",
            ),
            (
                "3. Để NOVA đề xuất giờ làm",
                "Mở **Kế hoạch & báo cáo** → Thiết lập giờ làm → chọn ngày và giờ → Duyệt. "
                "Sau đó bấm Xếp lịch hôm nay, xem đề xuất rồi Duyệt nếu phù hợp.",
            ),
        ),
    ),
    "daily": (
        "Dùng NOVA mỗi ngày",
        (
            (
                "Muốn ghi lại việc",
                "Nhắn ‘Tạo việc học Docker’, hoặc mở **Việc cần làm** → Thêm. "
                "Làm xong thì chọn việc → Hoàn thành.",
            ),
            (
                "Muốn có thông báo",
                "Nhắn ‘Nhắc tôi lúc 18h ngày mai’, hoặc mở **Nhắc việc** → Thêm. "
                "Có việc trong danh sách hoặc lịch chưa đồng nghĩa với có thông báo nhắc.",
            ),
            (
                "Muốn xem lịch",
                "Mở **Hôm nay** hoặc danh sách lựa chọn → **Lịch của bạn**. "
                "Muốn dời lịch, đọc kỹ đề xuất và giờ nhắc liên quan trước khi Duyệt.",
            ),
        ),
    ),
    "planning": (
        "Xếp lịch cho công việc",
        (
            (
                "Chuẩn bị một lần",
                "Trong **Kế hoạch & báo cáo**, thiết lập ngày/giờ làm. "
                "Thêm số phút dự kiến cho mỗi việc trong **Việc cần làm**.",
            ),
            (
                "Lập kế hoạch",
                "Bấm **Xếp lịch hôm nay**, **Xếp lịch tuần tới**, hoặc Chọn ngày khác. "
                "NOVA dựa trên giờ rảnh, hạn chót và thời lượng đã nhập.",
            ),
            (
                "Kiểm tra rồi lưu",
                "Đọc từng khung giờ. Duyệt mới tạo lịch gắn với việc gốc; "
                "Hủy đề xuất thì không tạo. "
                "Nếu thiếu thời lượng hoặc không đủ chỗ, làm theo thông báo rồi lập lại kế hoạch.",
            ),
        ),
    ),
    "personal": (
        "Ghi nhớ và bản tin",
        (
            (
                "Điều NOVA ghi nhớ",
                "Mở danh sách lựa chọn → **Điều NOVA ghi nhớ** → Thêm ghi nhớ. "
                "Bạn cũng có thể nhắn về sở thích; nếu NOVA gợi ý ghi nhớ, chỉ lưu khi bạn Duyệt.",
            ),
            (
                "Sửa hoặc quên một điều",
                "Chọn ghi nhớ → Sửa nội dung, Ngừng sử dụng hoặc Xóa ghi nhớ. "
                "Ngừng sử dụng vẫn giữ mục để bạn xem; xóa sẽ gỡ nội dung khỏi bộ nhớ của NOVA.",
            ),
            (
                "Nhận bản tin theo giờ",
                "**Kế hoạch & báo cáo** → Lịch gửi bản tin → chọn loại → giờ/nơi nhận → Duyệt. "
                "Bấm Bật bản tin rồi Duyệt. Giờ yên lặng đặt tại **Nhắc việc** → Cài đặt gửi.",
            ),
        ),
    ),
}


def render_guide(section="start"):
    title, steps = SECTIONS[section]
    embed = discord.Embed(
        title=f"NOVA — {title}",
        description="Chọn điều bạn muốn làm trong danh sách bên dưới. "
        "Các ví dụ là câu gợi ý, chưa tạo dữ liệu.",
    )
    for name, text in steps:
        embed.add_field(name=name, value=text, inline=False)
    embed.set_footer(
        text="Duyệt để lưu • Về trang chính để chọn việc khác • Bảng riêng hết hạn sau 10 phút"
    )
    return embed


class GuideSelect(discord.ui.Select):
    def __init__(self, controller):
        super().__init__(
            placeholder="Bạn muốn được hướng dẫn phần nào?",
            row=0,
            options=[
                discord.SelectOption(label=title, value=key) for key, (title, _) in SECTIONS.items()
            ],
        )
        self.controller = controller

    async def callback(self, interaction):
        if await self.view.interaction_check(interaction):
            key = self.values[0]
            if key not in SECTIONS:
                return
            await interaction.response.defer()
            await self.controller.finish(
                interaction, render_guide(key), GuideView(self.controller), self.view
            )


class GuideView(OwnerView):
    def __init__(self, controller):
        super().__init__(controller)
        self.add_item(GuideSelect(controller))
        for screen, label in (
            (Screen.TASKS, "Tasks"),
            (Screen.AI, "AI Assistant"),
            (Screen.REPORTS, "Reports"),
        ):
            self.add_item(NavigateButton(controller, screen, label=label, row=1))
        self.add_item(NavigateButton(controller, Screen.HOME, label="Back", row=4))
        self.add_item(NavigateButton(controller, Screen.HELP, label="Refresh", row=4))
