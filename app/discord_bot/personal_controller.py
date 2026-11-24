"""Private Memory/Reports/Planner panels. Mutations always use durable approval."""

from datetime import datetime

import discord

from app.discord_bot.agent_controller import pages, preview_pages, proposal_view
from app.discord_bot.checks import authorize_interaction
from app.discord_bot.renderers.core import safe
from app.discord_bot.renderers.personal import (
    MEMORY_KINDS,
    REPORT_NAMES,
    RUN_STATES,
    when,
    work_summary,
)
from app.domain.errors import DomainError, ValidationError
from app.domain.modules import Screen
from app.domain.time import zone


def report_text(payload):
    counts = payload["counts"]
    lines = [
        f"{REPORT_NAMES[payload['kind']]} • {payload['timezone']}",
        f"Kỳ {payload['period_start']} đến trước {payload['period_end']}",
        f"Cập nhật {when(payload['as_of'], payload['timezone'])}",
        f"Việc chưa xong: {counts['unfinished']} • Quá hạn: {counts['overdue']}",
        f"Hoàn thành trong kỳ: {counts['completed']} • Tạo trong kỳ: {counts['created']}",
        f"Lịch đã xác nhận trong kỳ: {counts['events']}",
        "Tổng hợp từ dữ liệu đã ghi nhận; chưa phản ánh thời gian làm thực tế.",
    ]
    if not any(counts.values()):
        lines.append("Chưa có dữ liệu được ghi nhận trong kỳ; không suy ra năng suất.")
    if payload["tasks"]:
        lines.append("\nTối đa 5 việc chưa xong:")
        lines.extend(f"• {safe(t['title'], 120)}" for t in payload["tasks"])
    if payload["events"]:
        lines.append("\nTối đa 5 lịch đã xác nhận:")
        for event in payload["events"]:
            start = datetime.fromisoformat(event["starts_at"]).astimezone(zone(payload["timezone"]))
            lines.append(f"• {start:%d/%m %H:%M} — {safe(event['title'], 100)}")
    if payload.get("plan"):
        plan = payload["plan"]
        lines.append(
            f"\nKế hoạch {plan['date']}: {len(plan['entries'])} khung giờ CHƯA LƯU, "
            f"{len(plan['unscheduled'])} việc chưa xếp. Bấm Xem kế hoạch để xem và duyệt."
        )
        if payload.get("ai_status") != "assisted":
            lines.append("Kế hoạch dựa trên giờ rảnh, hạn chót và thời lượng công việc của bạn.")
    return "\n".join(lines)


class PersonalController:
    def __init__(self, dashboard, core):
        self.dashboard, self.core = dashboard, core
        self.authorization = dashboard.authorization

    async def ack(self, interaction, *, new_panel=False):
        if not await authorize_interaction(interaction, self.authorization):
            return False
        if not interaction.response.is_done():
            if new_panel:
                await interaction.response.defer(ephemeral=True, thinking=True)
            else:
                await interaction.response.defer()
        return True

    async def error(self, interaction, error):
        if not await self.ack(interaction):
            return
        await interaction.followup.send(
            str(error) if isinstance(error, DomainError) else "Không xử lý được; hãy mở lại panel.",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def open(self, interaction, screen, *, page=0, query="", previous=None):
        self.authorization.require_owner(interaction.user.id)
        from app.discord_bot.views.personal import MemoryView, ReportsView

        if screen == Screen.MEMORY:
            data = await self.core.personal.memories(interaction.user.id, page=page, query=query)
            embed = discord.Embed(
                title="NOVA — Điều NOVA ghi nhớ",
                description=(
                    "NOVA ghi nhớ sở thích và thói quen để hỗ trợ bạn phù hợp hơn. "
                    "Chỉ lưu khi bạn duyệt. Chọn một mục để sửa, ngừng sử dụng hoặc xóa."
                ),
            )
            for item in data["items"]:
                embed.add_field(
                    name=f"{MEMORY_KINDS[item['kind']]} • "
                    + ("Được sử dụng" if item["use_for_ai"] else "Tạm ngừng dùng"),
                    value=safe(item["content"], 1024),
                    inline=False,
                )
            if not data["items"]:
                embed.add_field(
                    name="Bắt đầu",
                    value="Chưa có ghi nhớ phù hợp. Bấm **Thêm ghi nhớ**, "
                    "hoặc nhắn NOVA về sở thích của bạn.",
                    inline=False,
                )
            embed.set_footer(text=f"Trang {page + 1} • Tổng {data['total']}")
            view = MemoryView(self, data, query)
        else:
            config = await self.core.personal.settings(interaction.user.id)
            history = await self.core.reports.history(interaction.user.id, page)
            embed = discord.Embed(
                title="NOVA — Kế hoạch & báo cáo",
                description=(
                    "Chọn **Xếp lịch hôm nay** hoặc **Xếp lịch tuần tới** để NOVA đề xuất giờ làm. "
                    "Bạn xem trước rồi duyệt; lúc đó lịch mới được lưu."
                ),
            )
            work = config["work"]
            embed.add_field(
                name="1. Giờ làm của bạn",
                inline=False,
                value=work_summary(work),
            )
            embed.add_field(
                name="2. Việc cần xếp lịch",
                value="Thêm việc và số phút dự kiến ở **Việc cần làm**. "
                "NOVA sẽ báo những việc còn thiếu thời lượng.",
                inline=False,
            )
            enabled = sum(policy["enabled"] for policy in config["policies"].values())
            embed.add_field(
                name="Bản tin tự động",
                value=f"Đang bật {enabled}/3 lịch gửi. "
                "Chọn **Lịch gửi bản tin** để xem hoặc thay đổi.",
                inline=False,
            )
            embed.set_footer(text=f"Giờ theo {config['timezone']} • Bạn quyết định mọi thay đổi")
            view = ReportsView(self, config, history)
        await self.dashboard.finish(interaction, embed, view, previous)

    async def propose(self, interaction, kind, args):
        if not await self.ack(interaction):
            return
        try:
            pending = self.dashboard.client.agent.pending
            proposal = await pending.propose(
                interaction.user.id,
                kind,
                args,
                turn=f"ui:{interaction.id}",
                source="owner:discord-ui",
            )
            sent = await interaction.followup.send(
                preview_pages(proposal)[0],
                ephemeral=True,
                wait=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            await pending.bind(interaction.user.id, proposal["id"], sent.channel.id, sent.id)
            await sent.edit(view=proposal_view(proposal, 0))
        except Exception as error:
            await self.error(interaction, error)

    async def planner(self, interaction, day, days):
        if not await self.ack(interaction):
            return
        try:
            draft = await self.core.planner.draft(interaction.user.id, day, days)
            ai = self.core.reports.ai
            if ai and draft["entries"]:
                preference = await ai.preference(interaction.user.id, draft)
                if preference["period"]:
                    draft = await self.core.planner.draft(
                        interaction.user.id, day, days, preferred_period=preference["period"]
                    )
            if draft["unscheduled"]:
                reasons = "\n".join(
                    f"• {safe(t['title'], 100)}: {t['reason']}" for t in draft["unscheduled"]
                )
                for chunk in pages("Chưa xếp:\n" + reasons):
                    await interaction.followup.send(
                        chunk, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
                    )
            if draft["capped"]:
                await interaction.followup.send(
                    "Chỉ xét 100 task đầu; lọc/hoàn tất task rồi lập lại.", ephemeral=True
                )
            if not draft["entries"]:
                raise ValidationError(
                    "Chưa có block để duyệt. Kiểm tra giờ làm, thời lượng và lịch bận."
                )
            args = dict(
                date=day,
                days=days,
                entries=[
                    {k: t[k] for k in ("task_id", "starts_at", "ends_at")} for t in draft["entries"]
                ],
            )
            await self.propose(interaction, "propose_schedule_tasks", args)
        except Exception as error:
            await self.error(interaction, error)

    async def history(self, interaction, *, page=0, previous=None):
        if not await self.ack(interaction):
            return
        try:
            from app.discord_bot.views.personal import HistoryView

            history = await self.core.reports.history(interaction.user.id, page)
            embed = discord.Embed(
                title="NOVA — Lịch sử gửi bản tin",
                description=(
                    "Chọn một lần gửi để xem kết quả. Nội dung báo cáo được giữ 30 ngày."
                    if history["items"]
                    else "Chưa có lần gửi nào. Vào Lịch gửi bản tin "
                    "để chọn giờ và bật bản tin bạn cần."
                ),
            )
            embed.set_footer(text=f"Trang {page + 1} • {history['total']} lần gửi được ghi nhận")
            await self.dashboard.finish(interaction, embed, HistoryView(self, history), previous)
        except Exception as error:
            await self.error(interaction, error)

    async def report(self, interaction, kind, *, key=None):
        if not await self.ack(interaction):
            return
        try:
            from app.discord_bot.views.personal import ReportView

            payload = (
                (await self.core.reports.get(interaction.user.id, key))["payload"]
                if key
                else (await self.core.reports.build(interaction.user.id, kind))
            )
            if payload is None:
                row = await self.core.reports.get(interaction.user.id, key)
                raise ValidationError(
                    f"Báo cáo: {RUN_STATES[row['status']]} • {row['attempts']} lần thử. "
                    "Chưa có nội dung hoặc đã hết hạn lưu 30 ngày; metadata vẫn được giữ."
                )
            view = ReportView(self, payload)
            await self.dashboard.finish(
                interaction, discord.Embed(title="NOVA — Báo cáo", description=view.chunks[0]), view
            )
        except Exception as error:
            await self.error(interaction, error)

    async def report_button(self, interaction, key):
        if not await self.ack(interaction, new_panel=True):
            return
        try:
            row = await self.core.reports.get(interaction.user.id, key)
            if (
                row["status"] != "sent"
                or row["message_id"] != str(interaction.message.id)
                or (row["channel_id"] != str(interaction.channel_id))
            ):
                raise ValidationError("Tin nhắn báo cáo không khớp hoặc chưa được ghi nhận.")
            await self.report(interaction, row["kind"], key=key)
        except Exception as error:
            await self.error(interaction, error)
