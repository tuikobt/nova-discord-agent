import discord

MODULES = (
    "AI Assistant",
    "Task Management",
    "Project Management",
    "Calendar",
    "Reminder",
    "Goals",
    "Finance",
    "Habits",
    "Notes",
    "Reports",
    "Settings",
)


def render_dashboard() -> discord.Embed:
    embed = discord.Embed(
        title="NOVA — PERSONAL CONTROL CENTER",
        description="Nền tảng Phase 1 đã sẵn sàng. Các module đang chờ triển khai.",
        colour=discord.Colour.blurple(),
    )
    for module in MODULES:
        embed.add_field(name=module, value="Sắp ra mắt", inline=True)
    embed.set_footer(text="Phase 1 • Foundation • Dùng /ping để kiểm tra kết nối")
    return embed
