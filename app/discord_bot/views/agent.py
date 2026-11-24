import discord

from app.discord_bot.views.dashboard import NavigateButton, OwnerView
from app.domain.modules import Screen


class AgentPanel(OwnerView):
    @classmethod
    def build(cls, dashboard):
        ready = bool(
            getattr(getattr(dashboard.client, "agent", None), "config", None)
            and dashboard.client.agent.config.ready
        )
        embed = discord.Embed(
            title="NOVA — Trò chuyện với trợ lý",
            description=("NOVA sẵn sàng trò chuyện. " if ready else "Trò chuyện AI chưa được bật. ")
            + "Bấm **Mở tin nhắn riêng** rồi nhắn như đang nói với một trợ lý:\n"
            "• Hôm nay có việc gì?\n• Tạo việc học Docker.\n"
            "• Nhắc tôi lúc 18h ngày mai.\n\n"
            "NOVA sẽ hỏi khi thiếu thông tin. Nếu có đề xuất thay đổi, bạn đọc rồi bấm **Duyệt**. "
            "Thông tin muốn nhớ lâu cũng cần bạn duyệt; quản lý ở **Ghi nhớ**.",
        )
        view = cls(dashboard)
        if dashboard.client.user:
            view.add_item(
                discord.ui.Button(
                    label="Mở tin nhắn riêng",
                    url=f"https://discord.com/users/{dashboard.client.user.id}",
                )
            )
        view.add_item(NavigateButton(dashboard, Screen.HOME, label="Back", row=1))
        view.add_item(NavigateButton(dashboard, Screen.AI, label="Refresh", row=1))
        view.add_item(NavigateButton(dashboard, Screen.MEMORY, label="Memory", row=2))
        view.add_item(NavigateButton(dashboard, Screen.REPORTS, label="Planner & Reports", row=2))
        return embed, view

    @discord.ui.button(label="Xóa ngữ cảnh", row=1)
    async def clear(self, interaction, button):
        if await self.interaction_check(interaction):
            agent = self.controller.client.agent
            if agent.orchestrator.lock.locked():
                await interaction.response.send_message(
                    "Hãy đợi lượt đang chạy xong rồi xóa.", ephemeral=True
                )
                return
            agent.orchestrator.clear(interaction.user.id)
            await interaction.response.send_message(
                "Đã xóa hội thoại trong bộ nhớ; task/lịch và đề xuất đã lưu giữ nguyên.",
                ephemeral=True,
            )

    @discord.ui.button(label="Sử dụng AI", row=1)
    async def usage(self, interaction, button):
        if await self.interaction_check(interaction):
            await interaction.response.defer(ephemeral=True, thinking=True)
            rows = await self.controller.client.agent.usage.summary(interaction.user.id)
            text = (
                "\n".join(
                    f"{r['model']}: {r['requests']} requests, input {r['input_tokens']}, "
                    f"output {r['output_tokens']}, charged/reserved {r['charged_tokens']} tokens"
                    for r in rows
                )
                or "Chưa dùng API."
            )
            await interaction.followup.send(
                text[:1800]
                + "\nGiới hạn ngày tính UTC; chi phí tiền xem ở OpenAI Usage theo giá model.",
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
