"""Private Memory/Reports/Planner panels. Mutations always use durable approval."""

from datetime import datetime

import discord

from app.discord_bot.agent_controller import pages, preview_pages, proposal_view
from app.discord_bot.checks import authorize_interaction
from app.discord_bot.renderers.core import safe
from app.domain.errors import DomainError, ValidationError
from app.domain.modules import Screen
from app.domain.time import zone

REPORT_NAMES = {"morning": "Bản tin sáng", "daily": "Tổng kết ngày", "weekly": "Tổng kết tuần"}


def report_text(payload):
    counts = payload["counts"]
    lines = [
        f"{REPORT_NAMES[payload['kind']]} • {payload['timezone']}",
        f"Kỳ {payload['period_start']} đến trước {payload['period_end']}",
        f"Dữ liệu tại {payload['as_of']}",
        f"Task chưa xong hiện tại: {counts['unfinished']} • Quá hạn hiện tại: {counts['overdue']}",
        f"Hoàn thành trong kỳ: {counts['completed']} • Tạo trong kỳ: {counts['created']}",
        f"Lịch confirmed trong kỳ: {counts['events']}",
        payload["note"],
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
            f"\nKế hoạch {plan['date']}: {len(plan['entries'])} block CHƯA LƯU, "
            f"{len(plan['unscheduled'])} việc chưa xếp. Bấm Xem kế hoạch để duyệt riêng."
        )
        if payload.get("ai_status") != "assisted":
            lines.append("AI không khả dụng/không cần: kế hoạch dùng quy tắc và dữ liệu DB.")
    return "\n".join(lines)


class PersonalController:
    def __init__(self, dashboard, core):
        self.dashboard, self.core = dashboard, core
        self.authorization = dashboard.authorization

    async def ack(self, interaction):
        if not await authorize_interaction(interaction, self.authorization):
            return False
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=True)
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
                title="NOVA — Memory",
                description=(
                    "Chỉ dùng thông tin owner đã duyệt. Chọn mục để xem/sửa/xóa. "
                    "Không lưu token, thông tin nhạy cảm hoặc suy đoán."
                ),
            )
            for item in data["items"]:
                embed.add_field(
                    name=f"{item['kind']} • AI {'bật' if item['use_for_ai'] else 'tắt'}",
                    value=safe(item["content"], 1024),
                    inline=False,
                )
            if not data["items"]:
                embed.add_field(name="Danh sách", value="Chưa có memory phù hợp.", inline=False)
            embed.set_footer(text=f"Trang {page + 1} • Tổng {data['total']}")
            view = MemoryView(self, data, query)
        else:
            config = await self.core.personal.settings(interaction.user.id)
            history = await self.core.reports.history(interaction.user.id, page)
            embed = discord.Embed(
                title="NOVA — Reports & Planner",
                description=(
                    "Báo cáo từ dữ liệu thật. Mọi block lịch cần Duyệt. "
                    "Cấu hình giờ làm trước khi xếp task; thêm thời lượng ở Tasks."
                ),
            )
            work = config["work"]
            embed.add_field(
                name="Giờ làm",
                inline=False,
                value=(
                    f"Ngày (0=Hai…6=CN): {work['workdays']} • {work['start']}–{work['end']}\n"
                    f"Nghỉ {work['break_minutes']} phút • "
                    f"Gợi ý memory: {work['memory_suggestions']}"
                )
                if work["workdays"]
                else "Chưa cấu hình; Planner chưa xếp lịch.",
            )
            for kind, policy in config["policies"].items():
                embed.add_field(
                    name=REPORT_NAMES[kind],
                    value=(
                        f"{'BẬT' if policy['enabled'] else 'TẮT'} • "
                        f"{policy['time']} • {policy['target']}"
                        + (f" • ngày {policy['weekday']}" if kind == "weekly" else "")
                    ),
                    inline=False,
                )
            embed.set_footer(
                text=f"{config['timezone']} • Lịch sử trang {page + 1}: {history['total']} lần"
            )
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
                    f"Báo cáo: {row['status']} • {row['attempts']} lần thử • "
                    f"Lý do: {row['error'] or 'không có lỗi'}. "
                    "Chưa có nội dung hoặc đã hết hạn lưu 30 ngày; metadata vẫn được giữ."
                )
            view = ReportView(self, payload)
            await self.dashboard.finish(
                interaction, discord.Embed(title="NOVA — Báo cáo", description=view.chunks[0]), view
            )
        except Exception as error:
            await self.error(interaction, error)

    async def report_button(self, interaction, key):
        if not await self.ack(interaction):
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
