"""Text entry for private drafts; dates and choices are picked before explicit Save."""

import asyncio
import re
from dataclasses import dataclass, field, replace
from time import monotonic
from uuid import uuid4

import discord

from app.discord_bot.checks import authorize_interaction
from app.discord_bot.core_state import WriteIntent
from app.discord_bot.error_handlers import send_private
from app.domain.core import EventData, ProjectData, TaskData, text_value, to_record
from app.domain.errors import ValidationError
from app.domain.modules import Screen
from app.domain.time import format_local_datetime, parse_local_datetime


def wall_time(value, timezone):
    return format_local_datetime(value, timezone).split(" (")[0] if value else ""


@dataclass
class FormDraft:
    route: object
    timezone: str
    record: object = None
    link_id: str | None = None
    seed_title: str = ""
    request_id: str = field(default_factory=lambda: str(uuid4()))
    raw: dict = field(default_factory=dict)
    selections: dict = field(default_factory=dict)
    expires_at: float = field(default_factory=lambda: monotonic() + 600)
    intent: object = None
    advanced_input: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def values(self):
        return {**self.defaults(), **self.raw}

    def validate_text(self):
        values = self.values()
        key = "name" if self.route.screen == Screen.PROJECTS else "title"
        text_value(values[key], 200 if key == "name" else 250)
        if "description" in values:
            text_value(values["description"], 4000, required=False)
        if self.route.screen == Screen.TASKS:
            minutes = values["estimated_minutes"].strip()
            if minutes and (not re.fullmatch(r"[0-9]{1,9}", minutes) or int(minutes) <= 0):
                raise ValidationError("Thời lượng phải là số phút nguyên dương hoặc để trống.")

    def defaults(self):
        row = self.record
        if self.route.screen == Screen.PROJECTS:
            return {
                "name": row.name if row else "",
                "description": row.description or "" if row else "",
                "deadline_at": wall_time(row.deadline_at, self.timezone) if row else "",
            }
        if self.route.screen == Screen.TASKS:
            return {
                "title": row.title if row else self.seed_title,
                "description": row.description or "" if row else "",
                "due_at": wall_time(row.due_at, self.timezone) if row else "",
                "estimated_minutes": str(row.estimated_minutes)
                if row and row.estimated_minutes
                else "",
            }
        return {
            "title": row.title if row else self.seed_title,
            "starts_at": wall_time(row.starts_at, self.timezone) if row else "",
            "ends_at": wall_time(row.ends_at, self.timezone) if row else "",
        }

    def parse(self):
        raw = {key: value.strip() for key, value in self.values().items()}

        def timestamp(name):
            value = raw[name]
            if self.record is not None and value == self.defaults()[name]:
                return getattr(self.record, name)  # preserve seconds/microseconds when untouched
            return parse_local_datetime(value, self.timezone) if value else None

        if self.route.screen == Screen.PROJECTS:
            base = (
                to_record(ProjectData, self.record)
                if self.record
                else ProjectData(name=raw["name"])
            )
            data = replace(
                base,
                name=raw["name"],
                description=raw["description"] or None,
                deadline_at=timestamp("deadline_at"),
            )
        elif self.route.screen == Screen.TASKS:
            minutes = raw["estimated_minutes"]
            if minutes and not re.fullmatch(r"[0-9]{1,9}", minutes):
                raise ValidationError("Thời lượng phải là số phút nguyên dương hoặc để trống.")
            base = (
                to_record(TaskData, self.record)
                if self.record
                else TaskData(title=raw["title"], project_id=self.link_id)
            )
            data = replace(
                base,
                title=raw["title"],
                description=raw["description"] or None,
                due_at=timestamp("due_at"),
                estimated_minutes=int(minutes) if minutes else None,
            )
        else:
            if not raw["starts_at"] or not raw["ends_at"]:
                raise ValidationError("Chọn bắt đầu và kết thúc (hoặc thời lượng) trước khi Lưu.")
            values = {
                "title": raw["title"],
                "starts_at": timestamp("starts_at"),
                "ends_at": timestamp("ends_at"),
                "is_fixed": self.record.is_fixed if self.record else False,
            }
            data = (
                replace(to_record(EventData, self.record), **values)
                if self.record
                else EventData(**values, task_id=self.link_id)
            )
        data = replace(data, **self.selections)
        return WriteIntent(self.route, data, record=self.record, request_id=self.request_id)


class CoreFormModal(discord.ui.Modal):
    def __init__(self, core, previous, draft: FormDraft, *, advanced=False):
        super().__init__(title="Nhập thông tin • Tiếp tục chọn lịch", timeout=300)
        self.core, self.previous, self.draft = core, previous, draft
        draft.advanced_input = advanced
        self.expires_at = min(monotonic() + 300, previous.expires_at, draft.expires_at)
        self.submitted = False
        self.submit_lock = asyncio.Lock()
        defaults = draft.defaults()
        labels = {
            "name": "Tên dự án",
            "title": "Tiêu đề",
            "description": "Mô tả (tùy chọn)",
            "deadline_at": "Deadline local (tùy chọn)",
            "due_at": "Deadline local (tùy chọn)",
            "estimated_minutes": "Ước tính số phút (tùy chọn)",
            "starts_at": "Bắt đầu (giờ local)",
            "ends_at": "Kết thúc (giờ local)",
        }
        self.inputs = {}
        for key, initial in defaults.items():
            timestamp = key.endswith("_at")
            if (timestamp or key == "estimated_minutes") and not advanced:
                continue
            maximum = (
                4000
                if key == "description"
                else 200
                if key == "name"
                else 250
                if key == "title"
                else 16
                if timestamp
                else 9
                if key == "estimated_minutes"
                else 5
            )
            required = key in ("name", "title", "starts_at", "ends_at")
            item = discord.ui.TextInput(
                label=labels[key],
                default=draft.raw.get(key, initial),
                required=required,
                max_length=maximum,
                style=discord.TextStyle.paragraph
                if key == "description"
                else discord.TextStyle.short,
                placeholder=f"YYYY-MM-DD HH:MM • {draft.timezone}" if timestamp else None,
            )
            self.inputs[key] = item
            self.add_item(item)

    async def interaction_check(self, interaction):
        return await authorize_interaction(interaction, self.core.authorization)

    async def on_submit(self, interaction):
        if not await authorize_interaction(interaction, self.core.authorization):
            return
        if monotonic() >= self.expires_at or self.previous.is_finished():
            await send_private(interaction, "Form đã hết hạn hoặc màn hình đã đổi. Hãy mở lại.")
            return
        await self.core.submit_form(interaction, self)

    async def on_error(self, interaction, error):
        await self.core.error(interaction, error, self.draft.route, self.previous)
