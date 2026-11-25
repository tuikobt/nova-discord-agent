"""Private settings for approved scopes and explicit connectivity diagnostics."""

import asyncio
import logging
from time import monotonic

import discord

from app.agent.failures import explain_failure
from app.discord_bot.agent_controller import preview_pages, proposal_view
from app.discord_bot.checks import authorize_interaction
from app.discord_bot.renderers.connections import CHECK_MESSAGES, STATES, scope_text
from app.discord_bot.views.dashboard import NavigateButton, OwnerView
from app.domain.connections import PROVIDERS
from app.domain.errors import DomainError, ValidationError
from app.domain.modules import Screen

logger = logging.getLogger(__name__)


class OpenConnectionsButton(discord.ui.Button):
    def __init__(self, dashboard):
        super().__init__(label="Kết nối & chẩn đoán", row=2)
        self.dashboard = dashboard

    async def callback(self, interaction):
        if await self.view.interaction_check(interaction):
            await self.dashboard.connections.open(interaction)


class ConnectionAction(discord.ui.Button):
    def __init__(self, label, handler, row=0):
        super().__init__(label=label, row=row)
        self.handler = handler

    async def callback(self, interaction):
        if await self.view.interaction_check(interaction):
            try:
                await self.handler(interaction)
            except Exception as error:
                await self.view.connections.error(interaction, error)


class ConnectionView(OwnerView):
    def __init__(self, controller):
        super().__init__(controller.dashboard)
        self.connections = controller
        self.add_item(ConnectionAction("Làm mới kết nối", controller.open, row=4))
        self.add_item(
            NavigateButton(controller.dashboard, Screen.SETTINGS, label="Settings", row=4)
        )

    async def on_error(self, interaction, error, item):
        await self.connections.error(interaction, error)


class ConnectionPicker(discord.ui.Select):
    def __init__(self, controller, items):
        super().__init__(
            placeholder="Chọn kết nối để xem phạm vi",
            row=1,
            options=[
                discord.SelectOption(
                    label=item["label"][:100], value=item["id"], description=STATES[item["status"]]
                )
                for item in items
            ],
        )
        self.connections = controller

    async def callback(self, interaction):
        if await self.view.interaction_check(interaction):
            await self.connections.detail(interaction, self.values[0])


class ConnectionForm(discord.ui.Modal):
    def __init__(self, view, provider, record=None):
        super().__init__(title=f"Phạm vi {PROVIDERS[provider]}", timeout=300)
        self.parent, self.provider, self.record = view, provider, record
        self.expires = monotonic() + 300
        self.label_input = discord.ui.TextInput(
            label="Tên để bạn dễ nhận ra",
            max_length=80,
            default=record["label"] if record else None,
        )
        self.resources = discord.ui.TextInput(
            label="Repo hoặc link/ID trang, mỗi dòng một mục",
            style=discord.TextStyle.paragraph,
            max_length=2000,
            default="\n".join(record["resources"]) if record else None,
        )
        self.add_item(self.label_input)
        self.add_item(self.resources)

    async def interaction_check(self, interaction):
        return await authorize_interaction(interaction, self.parent.connections.authorization)

    async def on_submit(self, interaction):
        if not await self.interaction_check(interaction):
            return
        try:
            if (
                monotonic() >= self.expires
                or monotonic() >= self.parent.expires_at
                or self.parent.is_finished()
            ):
                raise ValidationError("Biểu mẫu đã hết hạn; mở lại Cài đặt để tiếp tục.")
            args = dict(
                connection_id=self.record["id"] if self.record else None,
                expected_version=self.record["version"] if self.record else 0,
                provider=self.provider,
                label=self.label_input.value.strip(),
                resources=[
                    line.strip() for line in self.resources.value.splitlines() if line.strip()
                ],
            )
            await self.parent.connections.propose(interaction, "configure_connection", args)
        except Exception as error:
            await self.parent.connections.error(interaction, error)

    async def on_error(self, interaction, error):
        await self.parent.connections.error(interaction, error)


class ConnectionsController:
    def __init__(self, dashboard, service):
        self.dashboard, self.service = dashboard, service
        self.authorization = dashboard.authorization

    async def ack(self, interaction):
        if not await authorize_interaction(interaction, self.authorization):
            return False
        if not interaction.response.is_done():
            await interaction.response.defer()
        return True

    async def error(self, interaction, error):
        if await self.ack(interaction):
            logger.warning(
                "connection_interaction_failed", extra={"error_type": type(error).__name__}
            )
            await interaction.followup.send(
                str(error)
                if isinstance(error, DomainError)
                else "Chưa xử lý được kết nối; hãy làm mới và thử lại.",
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )

    async def open(self, interaction, *, page=0):
        if not await self.ack(interaction):
            return
        try:
            if self.service is None:
                raise ValidationError("Quản lý kết nối chưa sẵn sàng trong bản này.")
            data = await self.service.list(interaction.user.id, page)
            client = self.dashboard.client
            embed = discord.Embed(
                title="NOVA — Kết nối & chẩn đoán",
                description=(
                    "Bạn chọn rõ nguồn NOVA được phép đọc. "
                    "Mỗi lần thêm, sửa hoặc ngắt đều cần Duyệt. "
                    "Đã có bộ đọc GitHub; chưa có bộ đọc Notion. "
                    "Không nhập token vào Discord."
                ),
            )
            embed.add_field(
                name="Discord",
                value="Đang kết nối" if client.is_ready() else "Chưa sẵn sàng",
                inline=False,
            )
            agent = getattr(client, "agent", None)
            embed.add_field(
                name="OpenAI",
                value="Đã cấu hình; bấm Thử AI để kiểm tra thật"
                if agent and agent.config.ready
                else "Chưa bật hoặc chưa cấu hình",
                inline=False,
            )
            for item in data["items"]:
                embed.add_field(
                    name=item["label"],
                    value=f"{PROVIDERS[item['provider']]} • {STATES[item['status']]}",
                    inline=False,
                )
            if not data["items"]:
                embed.add_field(
                    name="Phạm vi đã lưu",
                    value="Chưa có kết nối. Chọn GitHub hoặc Notion để chuẩn bị phạm vi.",
                    inline=False,
                )
            embed.set_footer(
                text=f"Trang {page + 1} • {data['total']} kết nối • Không tự cấp quyền ghi"
            )
            view = ConnectionView(self)

            async def create(i, provider):
                await i.response.send_modal(ConnectionForm(view, provider))

            for provider in PROVIDERS:
                view.add_item(
                    ConnectionAction(
                        f"Thêm {PROVIDERS[provider]}", lambda i, p=provider: create(i, p)
                    )
                )
            view.add_item(ConnectionAction("Thử AI (tính quota)", self.check_ai))
            if data["items"]:
                view.add_item(ConnectionPicker(self, data["items"]))
            if page:
                view.add_item(
                    ConnectionAction("Trang trước", lambda i: self.open(i, page=page - 1), row=3)
                )
            if (page + 1) * 5 < data["total"]:
                view.add_item(
                    ConnectionAction("Trang sau", lambda i: self.open(i, page=page + 1), row=3)
                )
            await self.dashboard.finish(interaction, embed, view)
        except Exception as error:
            await self.error(interaction, error)

    async def detail(self, interaction, key):
        if not await self.ack(interaction):
            return
        try:
            record = await self.service.get(interaction.user.id, key)
            embed = discord.Embed(title="NOVA — Phạm vi kết nối", description=scope_text(record))
            embed.add_field(name="Trạng thái", value=STATES[record["status"]], inline=False)
            embed.add_field(
                name="Quyền NOVA được sử dụng",
                value="Chỉ đọc; không tự đăng nội dung hoặc sửa dữ liệu ở dịch vụ.",
                inline=False,
            )
            view = ConnectionView(self)

            async def edit(i):
                await i.response.send_modal(ConnectionForm(view, record["provider"], record))

            view.add_item(ConnectionAction("Sửa phạm vi / thiết lập lại", edit))
            view.add_item(ConnectionAction("Kiểm tra dịch vụ", lambda i: self.check(i, key)))
            if record["provider"] == "github" and record["status"] != "disconnected":

                async def browse(i):
                    from app.discord_bot.github_controller import GitHubController

                    await GitHubController(self).open(i, key)

                view.add_item(ConnectionAction("Đọc GitHub", browse))
            if record["status"] != "disconnected":
                view.add_item(
                    ConnectionAction(
                        "Ngắt trong NOVA",
                        lambda i: self.propose(
                            i,
                            "disconnect_connection",
                            dict(connection_id=key, expected_version=record["version"]),
                        ),
                    )
                )
            await self.dashboard.finish(interaction, embed, view)
        except Exception as error:
            await self.error(interaction, error)

    async def propose(self, interaction, kind, args):
        if not await self.ack(interaction):
            return
        pending = self.dashboard.client.agent.pending
        proposal = await pending.propose(
            interaction.user.id, kind, args, turn=f"connection:{interaction.id}"
        )
        sent = await interaction.followup.send(
            preview_pages(proposal)[0],
            ephemeral=True,
            wait=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        await pending.bind(interaction.user.id, proposal["id"], sent.channel.id, sent.id)
        await sent.edit(view=proposal_view(proposal, 0))

    async def check(self, interaction, key):
        if await self.ack(interaction):
            result = await self.service.check(interaction.user.id, key)
            await interaction.followup.send(
                CHECK_MESSAGES[result["status"]],
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )

    async def check_ai(self, interaction):
        if not await self.ack(interaction):
            return
        agent = self.dashboard.client.agent
        text = "AI chưa bật hoặc chưa cấu hình."
        if agent.config.ready and agent.orchestrator.client:
            try:
                key = await agent.usage.reserve(
                    interaction.user.id, agent.config, agent.config.output_tokens + 2048
                )
                async with asyncio.timeout(30):
                    response = await agent.orchestrator.client.respond(
                        inputs=[dict(role="user", content="Connectivity check: reply OK.")],
                        instructions="Reply with OK. Do not request or change any personal data.",
                        tools=[],
                    )
                await agent.usage.settle(interaction.user.id, key, getattr(response, "usage", None))
                text = (
                    "Đã gọi AI thật thành công; kết quả đã tính vào quota."
                    if getattr(response, "status", None) == "completed"
                    else "AI đã phản hồi nhưng chưa hoàn tất kiểm tra."
                )
            except Exception as error:
                _, text = explain_failure(error)
        await interaction.followup.send(
            text, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )
