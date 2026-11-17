"""Private DM adapter, durable paginated previews, and restart-safe buttons."""

import logging
from datetime import datetime

import discord

from app.agent.client import ResponsesClient
from app.agent.gateway import ToolGateway
from app.agent.orchestrator import AgentOrchestrator
from app.agent.serialization import encode
from app.agent.usage import UsageService
from app.discord_bot.checks import authorize_interaction
from app.domain.errors import DomainError
from app.domain.time import zone
from app.services.pending_action_service import PendingActionService

logger = logging.getLogger(__name__)


def pages(text, size=1800):
    return [text[i : i + size] for i in range(0, len(text), size)] or ["Chưa có dữ liệu."]


LABELS = {
    "title": "Tiêu đề",
    "due_at": "Hạn",
    "priority": "Ưu tiên",
    "status": "Trạng thái",
    "starts_at": "Bắt đầu",
    "ends_at": "Kết thúc",
    "is_fixed": "Cố định",
    "project_id": "Dự án",
    "task_id": "Task liên kết",
    "event_id": "Event liên kết",
    "next_fire_at": "Giờ nhắc",
    "recurrence_type": "Lặp",
    "recurrence_config_json": "Quy tắc lặp",
    "delivery_target": "Vị trí gửi",
    "channel_id": "Kênh",
    "description": "Mô tả",
    "estimated_minutes": "Phút ước tính",
}


def preview_pages(proposal):
    plan = proposal["preview"]
    tz = plan["timezone"]

    def value(item):
        if item is None:
            return "Chưa đặt"
        if isinstance(item, str):
            try:
                moment = datetime.fromisoformat(item)
                if moment.tzinfo:
                    return moment.astimezone(zone(tz)).strftime("%d/%m/%Y %H:%M:%S")
            except ValueError:
                pass
            return discord.utils.escape_markdown(item)
        return encode(item)

    lines = [f"ĐỀ XUẤT — CHƯA LƯU • {tz}", f"Hết hạn: {value(proposal['expires_at'])}"]
    for change in plan["changes"]:
        before, after = change["before"], change["after"]
        lines.append(f"\n{change['entity']}: {value(after.get('title', ''))}")
        for key, new in after.items():
            old = before.get(key) if before else None
            if before is None or new != old:
                lines.append(f"> {LABELS.get(key, key)}: {value(old)} → {value(new)}")
    if plan["conflicts"]:
        lines.append("\n⚠ Lịch trùng — Duyệt nghĩa là bạn chấp nhận các xung đột sau:")
        for conflict in plan["conflicts"]:
            lines.append(
                f"> {value(conflict['title'])}: {value(conflict['starts_at'])}"
                f" — {value(conflict['ends_at'])}"
            )
    for reminder in plan["reminders"]:
        lines.append(f"\nNhắc: {value(reminder['before']['title'])}")
        lines.append(
            f"> Giữ giờ: {value(reminder['before']['next_fire_at'])}; "
            f"dời cùng lịch: {value(reminder['shifted']['next_fire_at'])}"
        )
        if (
            reminder["before"]["recurrence_config_json"]
            != reminder["shifted"]["recurrence_config_json"]
        ):
            lines.append(
                f"> Lặp: {value(reminder['before']['recurrence_config_json'])}"
                f" → {value(reminder['shifted']['recurrence_config_json'])}"
            )
    return pages("\n".join(lines))


class AgentButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"nova:agent:v1:(?P<action>keep|shift|reject|page):(?P<key>[0-9a-f-]{36}):(?P<page>[0-9]{1,4})",
):
    def __init__(self, action, key, page=0, *, label=None):
        self.action, self.key, self.page = action, key, page
        super().__init__(
            discord.ui.Button(
                label=label
                or {
                    "keep": "Duyệt / giữ giờ nhắc",
                    "shift": "Duyệt / dời giờ nhắc",
                    "reject": "Hủy đề xuất",
                    "page": "Xem tiếp",
                }[action],
                custom_id=f"nova:agent:v1:{action}:{key}:{page}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match["action"], match["key"], int(match["page"]))

    async def callback(self, interaction):
        await interaction.client.agent.callback(interaction, self)


def proposal_view(proposal, page):
    view = discord.ui.View(timeout=None)
    total = len(preview_pages(proposal))
    if proposal["status"] != "pending":
        return view
    if page > 0:
        view.add_item(AgentButton("page", proposal["id"], page - 1, label="Trang trước"))
    if page + 1 < total:
        view.add_item(AgentButton("page", proposal["id"], page + 1, label="Trang sau"))
    else:
        view.add_item(
            AgentButton(
                "keep",
                proposal["id"],
                page,
                label="Duyệt / giữ giờ nhắc" if proposal["preview"]["reminders"] else "Duyệt",
            )
        )
        if proposal["preview"]["reminders"]:
            view.add_item(AgentButton("shift", proposal["id"], page))
    view.add_item(AgentButton("reject", proposal["id"], page))
    return view


class AgentController:
    def __init__(self, client):
        self.client, self.authorization, self.config = (
            client,
            client.authorization,
            client.settings.ai,
        )
        sessions = client.database.sessions
        self.pending = PendingActionService(sessions, self.authorization, client.core_services)
        self.usage = UsageService(sessions, self.authorization)
        gateway = ToolGateway(sessions, self.authorization, client.core_services, self.pending)
        transport = ResponsesClient(self.config) if self.config.ready else None
        self.orchestrator = AgentOrchestrator(
            self.config, self.authorization, gateway, self.pending, self.usage, transport
        )

    async def message(self, message):
        self.authorization.require_owner(message.author.id)
        try:
            # Disabled AI does not even inspect message content.
            if self.config.ready:
                await message.channel.send(
                    "NOVA đang xử lý…", allowed_mentions=discord.AllowedMentions.none()
                )
            result = (
                await self.orchestrator.turn(message.author.id, message.id, message.content)
                if self.config.ready
                else dict(
                    text=(
                        "AI chưa cấu hình; dùng /menu để quản lý công việc. "
                        "AI Assistant: Sắp ra mắt cho tới khi bật OpenAI."
                    )
                )
            )
            proposal = result.get("pending")
            if proposal:
                if proposal["status"] == "executed":
                    await message.channel.send(
                        proposal["receipt"]["message"],
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                elif proposal["message_id"]:
                    await message.channel.send(
                        "Đề xuất đã có: https://discord.com/channels/@me/"
                        f"{proposal['channel_id']}/{proposal['message_id']}",
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                else:
                    content = preview_pages(proposal)[0]
                    sent = await message.channel.send(
                        content, allowed_mentions=discord.AllowedMentions.none()
                    )
                    await self.pending.bind(
                        message.author.id, proposal["id"], sent.channel.id, sent.id
                    )
                    await sent.edit(view=proposal_view(proposal, 0))
            else:
                for chunk in pages(result["text"]):
                    await message.channel.send(
                        chunk, allowed_mentions=discord.AllowedMentions.none()
                    )
        except Exception as error:
            logger.warning("agent_turn_failed", extra={"error_type": type(error).__name__})
            text = (
                str(error)
                if isinstance(error, DomainError)
                else (
                    "AI chưa xử lý được yêu cầu. Dùng /menu hoặc thử lại; "
                    "không tự gửi lại thao tác ghi."
                )
            )
            try:
                await message.channel.send(text, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                pass

    async def callback(self, interaction, button):
        if not await authorize_interaction(interaction, self.authorization):
            return
        await interaction.response.defer()
        try:
            if interaction.guild is not None:
                raise ValueError("DM only")
            proposal = await self.pending.get(interaction.user.id, button.key)
            if proposal["message_id"] != str(interaction.message.id) or proposal[
                "channel_id"
            ] != str(interaction.channel_id):
                raise ValueError("Message mismatch")
            chunks = preview_pages(proposal)
            if button.action == "page":
                if not 0 <= button.page < len(chunks):
                    raise ValueError("Invalid page")
                await interaction.edit_original_response(
                    content=chunks[button.page],
                    view=proposal_view(proposal, button.page),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            else:
                if button.action != "reject" and button.page != len(chunks) - 1:
                    raise ValueError("Review all pages")
                receipt = await self.pending.decide(
                    interaction.user.id,
                    button.key,
                    interaction.channel_id,
                    interaction.message.id,
                    choice=button.action,
                )
                self.orchestrator.clear(interaction.user.id)
                await interaction.edit_original_response(
                    content=receipt["message"],
                    view=None,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
        except Exception as error:
            logger.warning("agent_confirmation_failed", extra={"error_type": type(error).__name__})
            await interaction.followup.send(
                str(error)
                if isinstance(error, DomainError)
                else "Không thể xác nhận. Hãy mở lại đề xuất.",
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )

    async def close(self):
        self.orchestrator.close()
        if self.orchestrator.client:
            await self.orchestrator.client.close()
