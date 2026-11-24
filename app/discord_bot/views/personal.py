"""Legacy owner-only components; forms submit proposals rather than writing data."""

from datetime import timedelta
from time import monotonic

import discord

from app.discord_bot.checks import authorize_interaction
from app.discord_bot.personal_controller import REPORT_NAMES, report_text
from app.discord_bot.renderers.core import safe
from app.discord_bot.renderers.personal import (
    DAYS,
    MEMORY_KINDS,
    RUN_STATES,
    policy_summary,
    source_name,
)
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
        if screen == Screen.MEMORY:
            self.add_item(NavigateButton(self.controller, Screen.HELP, label="Help", row=4))

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
        self.add_item(Action("Thêm ghi nhớ", self.create, row=0))
        self.add_item(Action("Tìm kiếm", self.search, row=0))
        if self.records:
            self.add_item(
                Choice(
                    "Chọn điều bạn muốn xem hoặc sửa",
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
        if await self.personal.ack(interaction):
            view = MemoryKindView(self.personal)
            await self.personal.dashboard.finish(
                interaction,
                discord.Embed(
                    title="Bạn muốn NOVA nhớ điều gì?",
                    description="Chọn loại thông tin, rồi nhập điều bạn muốn ghi nhớ. "
                    "Bạn sẽ được xem lại trước khi lưu.",
                ),
                view,
                self,
            )

    async def search(self, interaction):
        async def submit(i, values):
            if await self.personal.ack(i):
                await self.personal.open(i, Screen.MEMORY, query=values[0], previous=self)

        await self.modal(interaction, "Tìm điều đã ghi nhớ", [("Từ khóa", None, 200)], submit)

    async def select(self, interaction, values):
        item = self.records[values[0]]
        if not await self.personal.ack(interaction):
            return
        embed = discord.Embed(
            title="NOVA — Điều đã ghi nhớ", description=safe(item["content"], 3000)
        )
        embed.add_field(name="Nguồn", value=source_name(item["source"]))
        embed.add_field(name="Loại", value=MEMORY_KINDS[item["kind"]])
        embed.add_field(name="NOVA được sử dụng", value="Có" if item["use_for_ai"] else "Không")
        embed.set_footer(
            text="Mọi thay đổi cần bạn duyệt. Tin nhắn Discord và bản sao lưu cũ cần xóa riêng."
        )
        await self.personal.dashboard.finish(
            interaction, embed, MemoryDetail(self.personal, item), self
        )


class MemoryKindView(PersonalView):
    def __init__(self, personal):
        super().__init__(personal, Screen.MEMORY)
        for kind, name in MEMORY_KINDS.items():
            self.add_item(Action(name, lambda i, selected=kind: self.input(i, selected)))

    async def input(self, interaction, kind):
        await self.modal(
            interaction,
            "Thêm ghi nhớ",
            [("Bạn muốn NOVA nhớ điều gì?", None, 1000)],
            lambda i, values: self.personal.propose(
                i, "propose_memory", dict(content=values[0], kind=kind, use_for_ai=True)
            ),
        )


class MemoryDetail(PersonalView):
    def __init__(self, personal, item):
        super().__init__(personal, Screen.MEMORY)
        self.item = item
        self.add_item(Action("Sửa nội dung", self.edit))
        self.add_item(
            Action("Ngừng sử dụng" if item["use_for_ai"] else "Cho phép sử dụng", self.toggle)
        )
        self.add_item(Action("Xóa ghi nhớ", self.delete))
        self.add_item(
            Choice(
                "Đổi loại ghi nhớ",
                [
                    discord.SelectOption(label=name, value=kind)
                    for kind, name in MEMORY_KINDS.items()
                ],
                self.kind,
                row=1,
            )
        )

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
            args.update(content=values[0])
            await self.personal.propose(i, "update_memory", args)

        await self.modal(
            interaction,
            "Sửa điều đã ghi nhớ",
            [
                ("Nội dung", self.item["content"], 1000),
            ],
            submit,
        )

    async def kind(self, interaction, values):
        args = self.args()
        args["kind"] = values[0]
        await self.personal.propose(interaction, "update_memory", args)

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
        self.add_item(Action("Xếp lịch hôm nay", lambda i: self.quick_plan(i, "today")))
        self.add_item(Action("Xếp lịch tuần tới", lambda i: self.quick_plan(i, "week")))
        self.add_item(Action("Chọn ngày khác", self.plan))
        self.add_item(Action("Thiết lập giờ làm", self.work, row=1))
        self.add_item(Action("Lịch gửi bản tin", self.policies, row=1))
        self.add_item(Action("Lịch sử gửi", self.history, row=1))
        self.add_item(
            Choice(
                "Xem ngay một bản báo cáo",
                [
                    discord.SelectOption(label=name, value=kind)
                    for kind, name in REPORT_NAMES.items()
                ],
                self.choose,
                row=2,
            )
        )
        self.add_item(NavigateButton(self.controller, Screen.TASKS, label="Tasks", row=3))
        self.add_item(NavigateButton(self.controller, Screen.HELP, label="Help", row=4))

    async def choose(self, interaction, values):
        await self.personal.report(interaction, values[0])

    async def policies(self, interaction):
        if await self.personal.ack(interaction):
            config = await self.personal.core.personal.settings(interaction.user.id)
            view = PoliciesView(self.personal, config)
            await self.personal.dashboard.finish(interaction, view.embed(), view, self)

    async def history(self, interaction):
        await self.personal.history(interaction, previous=self)

    async def quick_plan(self, interaction, period):
        today = self.personal.core.personal.clock().astimezone(zone(self.config["timezone"])).date()
        day = today if period == "today" else today + timedelta(days=7 - today.weekday())
        await self.personal.planner(interaction, day.isoformat(), 1 if period == "today" else 7)

    async def work(self, interaction):
        if await self.personal.ack(interaction):
            view = WorkView(self.personal, self.config["work"])
            await self.personal.dashboard.finish(
                interaction,
                discord.Embed(
                    title="NOVA — Giờ làm của bạn",
                    description="Bước 1: chọn những ngày bạn muốn làm việc.\n"
                    "Bước 2: nhập giờ, xem lại rồi bấm Duyệt. "
                    "NOVA chỉ xếp lịch trong thời gian bạn chọn.",
                ),
                view,
                self,
            )

    async def plan(self, interaction):
        if await self.personal.ack(interaction):
            view = PlanDateView(self.personal, self.config["timezone"])
            await self.personal.dashboard.finish(
                interaction,
                discord.Embed(
                    title="Bạn muốn xếp lịch trong bao lâu?",
                    description="Chọn một ngày hoặc cả tuần, sau đó nhập ngày bắt đầu.",
                ),
                view,
                self,
            )


class PlanDateView(PersonalView):
    def __init__(self, personal, timezone):
        super().__init__(personal, Screen.REPORTS)
        self.timezone = timezone
        self.add_item(Action("Một ngày", lambda i: self.date(i, 1)))
        self.add_item(Action("Cả tuần (7 ngày)", lambda i: self.date(i, 7)))

    async def date(self, interaction, days):
        today = self.personal.core.personal.clock().astimezone(zone(self.timezone)).date()
        await self.modal(
            interaction,
            "Chọn ngày bắt đầu",
            [("Ngày bắt đầu (năm-tháng-ngày)", today.isoformat(), 10)],
            lambda i, values: self.personal.planner(i, values[0], days),
        )


class PoliciesView(PersonalView):
    def __init__(self, personal, config):
        super().__init__(personal, Screen.REPORTS)
        self.config = config
        self.add_item(
            Choice(
                "Chọn bản tin muốn cài đặt",
                [
                    discord.SelectOption(label=name, value=kind)
                    for kind, name in REPORT_NAMES.items()
                ],
                self.choose,
            )
        )

    def embed(self):
        embed = discord.Embed(
            title="NOVA — Lịch gửi bản tin",
            description="Chọn một bản tin để bật, tắt, đổi giờ hoặc nơi nhận. "
            "Mỗi thay đổi cần bạn duyệt.",
        )
        for kind, policy in self.config["policies"].items():
            embed.add_field(name=REPORT_NAMES[kind], value=policy_summary(policy), inline=False)
        embed.set_footer(
            text=f"Giờ theo {self.config['timezone']} • Giờ yên lặng: Nhắc việc → Cài đặt gửi"
        )
        return embed

    async def choose(self, interaction, values):
        if await self.personal.ack(interaction):
            view = PolicyView(self.personal, self.config["policies"][values[0]])
            await self.personal.dashboard.finish(interaction, view.embed(), view, self)


class HistoryView(PersonalView):
    def __init__(self, personal, history):
        super().__init__(personal, Screen.REPORTS)
        if history["items"]:
            self.add_item(
                Choice(
                    "Chọn một lần gửi để xem kết quả",
                    [
                        discord.SelectOption(
                            label=f"{r['period']} • {REPORT_NAMES[r['kind']]}"[:100],
                            description=RUN_STATES[r["status"]],
                            value=r["id"],
                        )
                        for r in history["items"]
                    ],
                    self.choose,
                )
            )
        page = history["page"]
        if page:
            self.add_item(
                Action(
                    "Trang trước",
                    lambda i: personal.history(i, page=page - 1, previous=self),
                    row=3,
                )
            )
        if (page + 1) * 5 < history["total"]:
            self.add_item(
                Action(
                    "Trang sau", lambda i: personal.history(i, page=page + 1, previous=self), row=3
                )
            )

    async def choose(self, interaction, values):
        await self.personal.report(interaction, "daily", key=values[0])


class WorkView(PersonalView):
    def __init__(self, personal, work):
        super().__init__(personal, Screen.REPORTS)
        self.work = work
        self.add_item(
            Action("Thứ Hai–Thứ Sáu", lambda i: self.select(i, [str(d) for d in range(5)]), row=1)
        )
        self.add_item(
            Action("Cả tuần", lambda i: self.select(i, [str(d) for d in range(7)]), row=1)
        )
        self.add_item(
            Choice(
                "Chọn ngày làm (có thể chọn nhiều)",
                [
                    discord.SelectOption(
                        label=name, value=str(day), default=day in work["workdays"]
                    )
                    for day, name in enumerate(DAYS)
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
                raise ValidationError("Nhập ‘bật’ hoặc ‘tắt’ cho tùy chọn gợi ý ghi nhớ.")
            try:
                rest = int(fields[2])
            except ValueError:
                raise ValidationError("Số phút nghỉ cần là một số, ví dụ 10.") from None
            await self.personal.propose(
                i,
                "configure_work",
                dict(
                    workdays=days,
                    start=fields[0],
                    end=fields[1],
                    break_minutes=rest,
                    memory_suggestions=fields[3] == "bật",
                ),
            )

        await self.modal(
            interaction,
            "Giờ làm của bạn",
            [
                ("Bắt đầu HH:MM", self.work["start"] or "09:00", 5),
                ("Kết thúc HH:MM", self.work["end"] or "17:00", 5),
                ("Nghỉ giữa task (phút, 0–120)", self.work["break_minutes"], 3),
                (
                    "NOVA gợi ý ghi nhớ: bật / tắt",
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
        self.add_item(Action("Tắt bản tin" if policy["enabled"] else "Bật bản tin", self.toggle))
        self.add_item(Action("Đổi giờ gửi", self.time))
        self.add_item(
            Choice(
                "Bạn muốn nhận bản tin ở đâu?",
                [
                    discord.SelectOption(label="Tin nhắn riêng với NOVA", value="dm"),
                    discord.SelectOption(label="Kênh riêng", value="channel"),
                    discord.SelectOption(
                        label="Tin riêng; bị chặn thì dùng kênh dự phòng", value="fallback"
                    ),
                ],
                self.target,
                row=1,
            )
        )
        if policy["kind"] == "weekly":
            self.add_item(
                Choice(
                    "Gửi tổng kết vào ngày nào?",
                    [
                        discord.SelectOption(
                            label=name, value=str(day), default=day == policy["weekday"]
                        )
                        for day, name in enumerate(DAYS)
                    ],
                    self.weekday,
                    row=2,
                )
            )

    def args(self, **changes):
        return {**{k: v for k, v in self.policy.items() if k != "version"}, **changes}

    def embed(self):
        p = self.policy
        return discord.Embed(
            title=f"NOVA — {REPORT_NAMES[p['kind']]}",
            description=(
                policy_summary(p) + "\n\nĐổi giờ hoặc nơi nhận, xem lại rồi Duyệt. "
                "Giờ yên lặng được cài ở Nhắc việc → Cài đặt gửi."
            ),
        )

    async def toggle(self, interaction):
        await self.personal.propose(
            interaction, "configure_automation", self.args(enabled=not self.policy["enabled"])
        )

    async def time(self, interaction):
        await self.edit_time(interaction, self.policy["weekday"])

    async def weekday(self, interaction, values):
        await self.edit_time(interaction, int(values[0]))

    async def edit_time(self, interaction, weekday):
        async def submit(i, fields):
            await self.personal.propose(
                i, "configure_automation", self.args(time=fields[0], weekday=weekday)
            )

        await self.modal(
            interaction,
            "Giờ nhận bản tin",
            [
                ("Giờ gửi (giờ:phút, ví dụ 07:00)", self.policy["time"], 5),
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
