import discord

from app.domain.modules import MODULES, Screen
from app.domain.schemas import DashboardOverview, FeaturePage, SettingsSnapshot

TITLE = "NOVA — PERSONAL CONTROL CENTER"
ANCHOR_MARKER = "NOVA • Dashboard • v1"


def render_dashboard(overview: DashboardOverview | None = None) -> discord.Embed:
    embed = discord.Embed(
        title=TITLE,
        description="Chọn nút hoặc module để mở bảng riêng tư. Các module đang được phát triển.",
        colour=discord.Colour.blurple(),
    )
    if overview:
        embed.add_field(
            name="Hôm nay", value=f"{overview.today:%d/%m/%Y} • {overview.timezone}", inline=False
        )
    embed.add_field(
        name="Lịch trình hôm nay",
        value=f"{overview.events_today} lịch confirmed • Mở Today để xem."
        if overview and overview.events_today is not None
        else "Mở bảng riêng từ /menu hoặc Today để xem dữ liệu.",
        inline=False,
    )
    for name in ("Tasks", "Projects", "Reminders"):
        metric = getattr(overview, name.lower(), None) if overview else None
        value = (
            str(metric)
            if metric is not None
            else "Sắp ra mắt"
            if name == "Reminders"
            else "Xem trong bảng riêng"
        )
        embed.add_field(name=name, value=value, inline=True)
    if overview and overview.done_tasks is not None:
        embed.add_field(name="Tasks đã xong", value=str(overview.done_tasks), inline=True)
        embed.add_field(
            name="Cách đếm",
            value=(
                "Tasks không tính đã hủy; Projects không tính lưu trữ. Reminders chưa có backend."
            ),
            inline=False,
        )
    embed.add_field(
        name="Trạng thái các module",
        inline=False,
        value="\n".join(
            f"• {module.title}: {'Đã có giao diện' if module.available else 'Sắp ra mắt'}"
            for screen, module in MODULES.items()
            if screen != Screen.TODAY
        ),
    )
    embed.set_footer(text=ANCHOR_MARKER if overview is None else "NOVA • Bảng riêng tư")
    return embed


def render_module(screen: Screen, page: FeaturePage) -> discord.Embed:
    module = MODULES[screen]
    embed = discord.Embed(
        title=f"NOVA — {module.title}",
        description=module.description,
        colour=discord.Colour.blurple(),
    )
    embed.add_field(name="Trạng thái", value="🔒 Sắp ra mắt", inline=False)
    embed.add_field(
        name="Chức năng dự kiến", value="\n".join(f"• {item}" for item in page.items), inline=False
    )
    embed.add_field(
        name="Dữ liệu",
        value="Chưa có dữ liệu. Module này chưa hỗ trợ quản lý dữ liệu.",
        inline=False,
    )
    embed.set_footer(text=f"NOVA • Trang {page.index + 1}/{page.total} • Back để về Dashboard")
    return embed


def render_settings(settings: SettingsSnapshot, *, saved: bool = False) -> discord.Embed:
    embed = discord.Embed(
        title="NOVA — Settings",
        colour=discord.Colour.blurple(),
        description="Đã lưu múi giờ." if saved else "Cài đặt được đọc từ database.",
    )
    embed.add_field(
        name="Language",
        value=f"{settings.locale} • Giao diện hiện hỗ trợ tiếng Việt.",
        inline=False,
    )
    embed.add_field(name="Timezone", value=settings.timezone, inline=False)
    for name, value in (
        ("Morning Briefing", settings.morning_briefing_time),
        ("Daily Review", settings.daily_review_time),
    ):
        configured = value.strftime("%H:%M") if value else "Chưa đặt giờ"
        embed.add_field(name=name, value=f"{configured} • Chưa kích hoạt", inline=False)
    preference = "Bật" if settings.dm_notifications_enabled else "Tắt"
    embed.add_field(
        name="Notification Preferences",
        value=f"Tùy chọn DM đã lưu: {preference}. Tự động gửi: Chưa kích hoạt.",
        inline=False,
    )
    embed.add_field(
        name="Owner Access", value="Chỉ chủ tài khoản trong cấu hình được truy cập.", inline=False
    )
    embed.add_field(
        name="Trạng thái",
        value="Có thể sửa Timezone. Các cài đặt mở rộng: Sắp ra mắt.",
        inline=False,
    )
    return embed


def render_help() -> discord.Embed:
    embed = discord.Embed(
        title="NOVA — Help",
        colour=discord.Colour.blurple(),
        description="Bấm nút hoặc chọn module; không cần nhớ lệnh con.",
    )
    embed.add_field(
        name="Điều hướng",
        value="Back: về Dashboard. Refresh: đọc lại màn hình hiện tại.",
        inline=False,
    )
    embed.add_field(
        name="Riêng tư",
        value="Các module mở trong panel chỉ bạn thấy; bảng neo giữ nguyên.",
        inline=False,
    )
    embed.add_field(
        name="Settings", value="Xem cấu hình và đổi múi giờ bằng biểu mẫu.", inline=False
    )
    embed.add_field(
        name="Sắp ra mắt",
        value=(
            "Reminders, AI và các module mở rộng: Sắp ra mắt. "
            "Tasks/Projects/Calendar có Thêm, chọn mục để Sửa, đổi trạng thái và Refresh."
        ),
        inline=False,
    )
    embed.add_field(
        name="Hết phiên",
        value="Panel riêng tư hết hạn sau 10 phút. Điều hướng sẽ làm mới phiên. "
        "Mở lại bằng nút trên bảng neo hoặc /menu.",
        inline=False,
    )
    return embed


def render_error() -> discord.Embed:
    return discord.Embed(
        title="NOVA — Chưa thể tải màn hình",
        description="Vui lòng bấm Refresh để thử lại hoặc Back để về Dashboard. "
        "Nếu vẫn lỗi, mở lại /menu và kiểm tra log vận hành.",
        colour=discord.Colour.orange(),
    )
