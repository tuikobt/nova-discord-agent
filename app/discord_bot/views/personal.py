"""Legacy owner-only components; forms submit proposals rather than writing data."""

from time import monotonic

import discord

from app.discord_bot.checks import authorize_interaction
from app.discord_bot.personal_controller import REPORT_NAMES, report_text
from app.discord_bot.renderers.core import safe
from app.discord_bot.views.dashboard import NavigateButton, OwnerView
from app.domain.errors import ValidationError
from app.domain.modules import Screen
from app.domain.time import zone


class Action(discord.ui.Button):
    def __init__(self, label, callback, *, row=0, disabled=False):
        super().__init__(label=label, row=row, disabled=disabled)
        self.handler = callback

    async def callback(self, interaction):
        if await self.view.interaction_check(interaction):
            try:
                await self.handler(interaction)
            except Exception as error:
                await self.view.personal.error(interaction, error)


class Choice(discord.ui.Select):
    def __init__(self, placeholder, options, callback, *, row=0, max_values=1):
        super().__init__(placeholder=placeholder, options=options, row=row, max_values=max_values)
        self.handler = callback

    async def callback(self, interaction):
        if await self.view.interaction_check(interaction):
            try:
                await self.handler(interaction, self.values)
            except Exception as error:
                await self.view.personal.error(interaction, error)


class PersonalView(OwnerView):
    def __init__(self, personal, screen):
        super().__init__(personal.dashboard)
        self.personal = personal
        self.add_item(NavigateButton(self.controller, Screen.HOME, label="Back", row=4))
        self.add_item(NavigateButton(self.controller, screen, label="Refresh", row=4))

    async def on_error(self, interaction, error, item):
        await self.personal.error(interaction, error)

    async def modal(self, interaction, title, fields, handler):
        await interaction.response.send_modal(Form(self, title, fields, handler))

    def pagination(self, screen, page, total, *, query=""):
        async def open_page(interaction, target):
            if await self.personal.ack(interaction):
                await self.personal.open(
                    interaction, screen, page=target, query=query, previous=self
                )

        if page > 0:
            self.add_item(Action("Trang trước", lambda i: open_page(i, page - 1), row=3))
        if (page + 1) * 5 < total:
            self.add_item(Action("Trang sau", lambda i: open_page(i, page + 1), row=3))


class Form(discord.ui.Modal):
    def __init__(self, view, title, fields, handler):
        super().__init__(title=title, timeout=300)
        self.parent, self.handler = view, handler
        self.expires = monotonic() + 300
        for label, default, max_length in fields:
            self.add_item(
                discord.ui.TextInput(
                    label=label,
                    default=str(default) if default is not None else None,
                    max_length=max_length,
                    style=discord.TextStyle.paragraph
                    if max_length > 200
                    else discord.TextStyle.short,
                )
            )

    async def interaction_check(self, interaction):
        return await authorize_interaction(interaction, self.parent.personal.authorization)

    async def on_submit(self, interaction):
        if not await self.interaction_check(interaction):
            return
        try:
            if monotonic() >= self.expires or monotonic() >= self.parent.expires_at:
                raise ValidationError("Biểu mẫu/panel hết hạn; hãy mở lại từ /menu.")
            await self.handler(interaction, [item.value.strip() for item in self.children])
        except Exception as error:
            await self.parent.personal.error(interaction, error)

    async def on_error(self, interaction, error):
        await self.parent.personal.error(interaction, error)


class MemoryView(PersonalView):
    def __init__(self, personal, data, query):
        super().__init__(personal, Screen.MEMORY)
        self.records = {item["id"]: item for item in data["items"]}
        self.add_item(Action("Thêm memory", self.create, row=0))
        self.add_item(Action("Tìm kiếm", self.search, row=0))
        if self.records:
            self.add_item(
                Choice(
                    "Chọn memory để sửa/xóa",
                    [
                        discord.SelectOption(label=item["content"][:100], value=item["id"])
                        for item in self.records.values()
                    ],
                    self.select,
                    row=1,
                )
            )
        self.pagination(Screen.MEMORY, data["page"], data["total"], query=query)

    async def create(self, interaction):
        await self.modal(
            interaction,
            "Thêm memory (chờ duyệt)",
            [
                ("Nội dung owner xác nhận", None, 1000),
                ("Loại: preference / routine / profile", "preference", 20),
            ],
            lambda i, values: self.personal.propose(
                i,
                "propose_memory",
                dict(
                    content=values[0],
                    kind=values[1],
                    use_for_ai=True,
                ),
            ),
        )

    async def search(self, interaction):
        async def submit(i, values):
            if await self.personal.ack(i):
                await self.personal.open(i, Screen.MEMORY, query=values[0], previous=self)

        await self.modal(interaction, "Tìm Memory", [("Từ khóa", None, 200)], submit)

    async def select(self, interaction, values):
        item = self.records[values[0]]
        if not await self.personal.ack(interaction):
            return
        embed = discord.Embed(
            title="NOVA — Memory đã xác nhận", description=safe(item["content"], 3000)
        )
        embed.add_field(name="Nguồn", value=safe(item["source"] or "Owner", 150))
        embed.add_field(name="Loại / dùng cho AI", value=f"{item['kind']} / {item['use_for_ai']}")
        embed.set_footer(
            text="Xóa gỡ nội dung trong DB/context/đề xuất. "
            "Tin Discord và backup cũ cần xử lý riêng."
        )
        await self.personal.dashboard.finish(
            interaction, embed, MemoryDetail(self.personal, item), self
        )


class MemoryDetail(PersonalView):
    def __init__(self, personal, item):
        super().__init__(personal, Screen.MEMORY)
        self.item = item
        self.add_item(Action("Sửa nội dung", self.edit))
        self.add_item(Action("Tắt AI" if item["use_for_ai"] else "Bật AI", self.toggle))
        self.add_item(Action("Xóa memory", self.delete))

    def args(self, **changes):
        return dict(
            memory_id=self.item["id"],
            expected_version=self.item["version"],
            content=self.item["content"],
            kind=self.item["kind"],
            use_for_ai=self.item["use_for_ai"],
            **changes,
        )

    async def edit(self, interaction):
        async def submit(i, values):
            args = self.args()
            args.update(content=values[0], kind=values[1])
            await self.personal.propose(i, "update_memory", args)

        await self.modal(
            interaction,
            "Sửa memory (chờ duyệt)",
            [
                ("Nội dung", self.item["content"], 1000),
                ("Loại: preference / routine / profile", self.item["kind"], 20),
            ],
            submit,
        )

    async def toggle(self, interaction):
        args = self.args()
        args["use_for_ai"] = not args["use_for_ai"]
        await self.personal.propose(interaction, "update_memory", args)

    async def delete(self, interaction):
        await self.personal.propose(
            interaction,
            "delete_memory",
            dict(
                memory_id=self.item["id"],
                expected_version=self.item["version"],
            ),
        )


class ReportsView(PersonalView):
    def __init__(self, personal, config, history):
        super().__init__(personal, Screen.REPORTS)
        self.config = config
        self.add_item(
            Choice(
                "Xem báo cáo / cấu hình",
                [
                    discord.SelectOption(label=f"Xem: {name}", value=f"report:{kind}")
                    for kind, name in REPORT_NAMES.items()
                ]
                + [
                    discord.SelectOption(label=f"Cấu hình: {name}", value=f"config:{kind}")
                    for kind, name in REPORT_NAMES.items()
                ],
                self.choose,
                row=0,
            )
        )
        self.add_item(Action("Giờ làm & Memory AI", self.work, row=1))
        self.add_item(Action("Lập kế hoạch ngày/tuần", self.plan, row=1))
        if history["items"]:
            self.add_item(
                Choice(
                    "Lịch sử gửi / lỗi",
                    [
                        discord.SelectOption(
                            label=f"{r['period']} {r['kind']} • {r['status']}",
                            description=r["error"] or "Không có lỗi",
                            value=r["id"],
                        )
                        for r in history["items"]
                    ],
                    self.history,
                    row=2,
                )
            )
        self.pagination(Screen.REPORTS, history["page"], history["total"])

    async def choose(self, interaction, values):
        action, kind = values[0].split(":")
        if action == "report":
            await self.personal.report(interaction, kind)
        elif await self.personal.ack(interaction):
            view = PolicyView(self.personal, self.config["policies"][kind])
            await self.personal.dashboard.finish(interaction, view.embed(), view, self)

    async def history(self, interaction, values):
        await self.personal.report(interaction, "daily", key=values[0])

    async def work(self, interaction):
        if await self.personal.ack(interaction):
            view = WorkView(self.personal, self.config["work"])
            await self.personal.dashboard.finish(
                interaction,
                discord.Embed(
                    title="Ngày làm việc",
                    description="Chọn ngày trước, sau đó nhập giờ và xem đề xuất.",
                ),
                view,
                self,
            )

    async def plan(self, interaction):
        today = self.personal.core.personal.clock().astimezone(zone(self.config["timezone"])).date()

        async def submit(i, values):
            await self.personal.planner(i, values[0], int(values[1]))

        await self.modal(
            interaction,
            "Lập kế hoạch (chờ duyệt)",
            [
                ("Ngày bắt đầu YYYY-MM-DD", today.isoformat(), 10),
                ("Số ngày: 1 hoặc 7", "1", 1),
            ],
            submit,
        )


class WorkView(PersonalView):
    def __init__(self, personal, work):
        super().__init__(personal, Screen.REPORTS)
        self.work = work
        self.add_item(
            Choice(
                "Chọn ngày làm (có thể chọn nhiều)",
                [
                    discord.SelectOption(
                        label=name, value=str(day), default=day in work["workdays"]
                    )
                    for day, name in enumerate(
                        ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ nhật"]
                    )
                ],
                self.select,
                row=0,
                max_values=7,
            )
        )

    async def select(self, interaction, values):
        days = [int(value) for value in values]

        async def submit(i, fields):
            if fields[3] not in {"bật", "tắt"}:
                raise ValidationError("Gợi ý memory phải là bật hoặc tắt.")
            await self.personal.propose(
                i,
                "configure_work",
                dict(
                    workdays=days,
                    start=fields[0],
                    end=fields[1],
                    break_minutes=int(fields[2]),
                    memory_suggestions=fields[3] == "bật",
                ),
            )

        await self.modal(
            interaction,
            "Giờ làm & gợi ý memory",
            [
                ("Bắt đầu HH:MM", self.work["start"] or "09:00", 5),
                ("Kết thúc HH:MM", self.work["end"] or "17:00", 5),
                ("Nghỉ giữa task (phút, 0–120)", self.work["break_minutes"], 3),
                (
                    "AI đề xuất memory: bật / tắt",
                    "bật" if self.work["memory_suggestions"] else "tắt",
                    3,
                ),
            ],
            submit,
        )


class PolicyView(PersonalView):
    def __init__(self, personal, policy):
        super().__init__(personal, Screen.REPORTS)
        self.policy = policy
        self.add_item(Action("Tắt" if policy["enabled"] else "Bật", self.toggle))
        self.add_item(Action("Đổi giờ/ngày", self.time))
        self.add_item(
            Choice(
                "Vị trí gửi",
                [
                    discord.SelectOption(label="Chỉ DM", value="dm"),
                    discord.SelectOption(label="Kênh riêng", value="channel"),
                    discord.SelectOption(label="DM, lỗi quyền thì kênh riêng", value="fallback"),
                ],
                self.target,
                row=1,
            )
        )

    def args(self, **changes):
        return {**{k: v for k, v in self.policy.items() if k != "version"}, **changes}

    def embed(self):
        p = self.policy
        return discord.Embed(
            title=f"NOVA — {REPORT_NAMES[p['kind']]}",
            description=(
                f"{'BẬT' if p['enabled'] else 'TẮT'} • {p['time']} • "
                f"ngày {p['weekday']} (0=Hai…6=CN)\n"
                f"Gửi: {p['target']} • Kênh: {p['channel_id'] or 'chưa chọn'} • "
                f"Fallback: {p['fallback']}\n"
                "Mỗi thay đổi cần Duyệt. Theo timezone Settings và giờ yên lặng; "
                "không gửi bù quá 2 giờ."
            ),
        )

    async def toggle(self, interaction):
        await self.personal.propose(
            interaction, "configure_automation", self.args(enabled=not self.policy["enabled"])
        )

    async def time(self, interaction):
        async def submit(i, fields):
            await self.personal.propose(
                i, "configure_automation", self.args(time=fields[0], weekday=int(fields[1]))
            )

        await self.modal(
            interaction,
            "Giờ báo cáo",
            [
                ("Giờ local HH:MM", self.policy["time"], 5),
                ("Ngày tuần: 0=Hai…6=CN (weekly)", self.policy["weekday"], 1),
            ],
            submit,
        )

    async def target(self, interaction, values):
        if values[0] == "dm":
            await self.personal.propose(
                interaction,
                "configure_automation",
                self.args(target="dm", channel_id=None, fallback=False),
            )
        elif await self.personal.ack(interaction):
            view = PersonalView(self.personal, Screen.REPORTS)
            view.add_item(ReportChannel(self, values[0]))
            await self.personal.dashboard.finish(
                interaction,
                discord.Embed(
                    title="Chọn kênh báo cáo",
                    description="Chỉ chấp nhận kênh riêng trong server owner sở hữu.",
                ),
                view,
                self,
            )


class ReportChannel(discord.ui.ChannelSelect):
    def __init__(self, policy_view, target):
        super().__init__(placeholder="Kênh riêng", channel_types=[discord.ChannelType.text], row=0)
        self.policy_view, self.target = policy_view, target

    async def callback(self, interaction):
        if await self.view.interaction_check(interaction):
            await self.policy_view.personal.propose(
                interaction,
                "configure_automation",
                self.policy_view.args(
                    target="channel" if self.target == "channel" else "dm",
                    channel_id=str(self.values[0].id),
                    fallback=self.target == "fallback",
                ),
            )


class ReportView(PersonalView):
    def __init__(self, personal, payload, page=0):
        super().__init__(personal, Screen.REPORTS)
        from app.discord_bot.agent_controller import pages

        self.chunks = pages(report_text(payload), 3500)
        if payload.get("planning_date"):
            self.add_item(
                Action(
                    "Xem và duyệt kế hoạch",
                    lambda i: personal.planner(
                        i, payload["planning_date"], payload["planning_days"]
                    ),
                )
            )

        async def turn(i, target):
            if await personal.ack(i):
                view = ReportView(personal, payload, target)
                await personal.dashboard.finish(
                    i, discord.Embed(title="Báo cáo", description=self.chunks[target]), view, self
                )

        if page:
            self.add_item(Action("Trang trước", lambda i: turn(i, page - 1), row=3))
        if page + 1 < len(self.chunks):
            self.add_item(Action("Trang sau", lambda i: turn(i, page + 1), row=3))


class ReportButton(
    discord.ui.DynamicItem[discord.ui.Button], template=r"nova:report:v1:(?P<key>[0-9a-f-]{36})"
):
    def __init__(self, key):
        self.key = key
        super().__init__(
            discord.ui.Button(label="Mở báo cáo / xem kế hoạch", custom_id=f"nova:report:v1:{key}")
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match["key"])

    async def callback(self, interaction):
        await interaction.client.dashboard.personal.report_button(interaction, self.key)
