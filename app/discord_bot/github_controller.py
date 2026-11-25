"""Explicit private GitHub browsing; external text never enters the AI context here."""

from datetime import datetime
from time import monotonic

import discord

from app.discord_bot.connections_controller import ConnectionAction, ConnectionView
from app.domain.errors import ValidationError
from app.domain.time import format_local_datetime


def display(value, limit=1000):
    value = discord.utils.escape_mentions(discord.utils.escape_markdown(str(value)))
    return value if len(value) <= limit else value[: limit - 40] + "… (đã rút gọn; mở link nguồn)"


class GitHubPicker(discord.ui.Select):
    def __init__(self, placeholder, options, callback, *, row=1):
        super().__init__(placeholder=placeholder, options=options, row=row)
        self.handler = callback

    async def callback(self, interaction):
        if await self.view.interaction_check(interaction):
            try:
                await self.handler(interaction, self.values[0])
            except Exception as error:
                await self.view.connections.error(interaction, error)


class GitHubDocumentForm(discord.ui.Modal):
    def __init__(self, view, handler):
        super().__init__(title="Đọc một tài liệu GitHub", timeout=300)
        self.parent, self.handler, self.expires = view, handler, monotonic() + 300
        self.path = discord.ui.TextInput(
            label="Đường dẫn trong repo, không phải URL",
            default="README.md",
            max_length=240,
        )
        self.add_item(self.path)

    async def on_submit(self, interaction):
        if not await self.parent.interaction_check(interaction):
            return
        try:
            if monotonic() >= self.expires or self.parent.is_finished():
                raise ValidationError("Biểu mẫu đã hết hạn; mở lại repo để đọc.")
            await self.handler(interaction, self.path.value)
        except Exception as error:
            await self.parent.connections.error(interaction, error)

    async def on_error(self, interaction, error):
        await self.parent.connections.error(interaction, error)


class GitHubController:
    def __init__(self, connections):
        self.connections, self.dashboard = connections, connections.dashboard
        self.service = self.dashboard.client.github

    async def open(self, interaction, key):
        if not await self.connections.ack(interaction):
            return
        record = await self.connections.service.get(interaction.user.id, key)
        if record["provider"] != "github" or record["status"] == "disconnected":
            raise ValidationError("Chọn kết nối GitHub chưa ngắt để đọc.")
        embed = discord.Embed(
            title="NOVA — Đọc GitHub",
            description="Chọn repo trong phạm vi đã Duyệt. Chỉ đọc khi bạn bấm; "
            "không gửi nội dung sang AI, không tạo task hoặc đăng lên GitHub.",
        )
        view = ConnectionView(self.connections)
        view.add_item(
            GitHubPicker(
                "Chọn repo đã được phép đọc",
                [
                    discord.SelectOption(label=repo[:100], value=str(index))
                    for index, repo in enumerate(record["resources"])
                ],
                lambda i, index: self.read(
                    i, record, record["resources"][int(index)], "repository"
                ),
            )
        )
        await self.dashboard.finish(interaction, embed, view)

    async def read(self, interaction, record, repo, operation, **options):
        if not await self.connections.ack(interaction):
            return
        data = await self.service.read(
            interaction.user.id,
            record["id"],
            repo,
            operation,
            expected_version=record["version"],
            **options,
        )
        preferences = await self.dashboard.settings.get(interaction.user.id)
        embed = discord.Embed(title=f"GitHub — {repo}", url=data["source_url"])
        stamp = format_local_datetime(
            datetime.fromisoformat(data["retrieved_at"]),
            preferences.timezone,
        )
        embed.set_footer(
            text=f"Lấy lúc {stamp} • Nguồn ngoài, chỉ đọc • Không lưu nội dung vào DB/AI"
        )
        view = ConnectionView(self.connections)

        async def read(i, kind, **kwargs):
            await self.read(i, record, repo, kind, **kwargs)

        view.add_item(ConnectionAction("Thông tin repo", lambda i: read(i, "repository")))
        view.add_item(ConnectionAction("Issues", lambda i: read(i, "issues")))
        view.add_item(ConnectionAction("Pull requests", lambda i: read(i, "pulls")))

        async def document(i):
            await i.response.send_modal(
                GitHubDocumentForm(view, lambda j, path: read(j, "document", path=path))
            )

        view.add_item(ConnectionAction("Đọc tài liệu", document))
        view.add_item(
            ConnectionAction("Chọn repo khác", lambda i: self.open(i, record["id"]), row=3)
        )
        if operation == "repository":
            embed.description = display(data["description"] or "Repo chưa có mô tả.", 2500)
            embed.add_field(
                name="Nhánh mặc định", value=display(data["default_branch"]) or "Chưa có"
            )
            embed.add_field(name="Nguồn", value=data["source_url"], inline=False)
        elif operation in {"issues", "pulls"}:
            embed.description = (
                f"Trang {data['page']} • Trạng thái {data['state']} • "
                "Tối đa 10 mục/trang, không phải tổng số mục của repo."
            )
            for item in data["items"]:
                embed.add_field(
                    name=f"#{item['number']} • {display(item['title'], 230)}",
                    value=f"{item['state']} • {item['source_url']}",
                    inline=False,
                )
            if not data["items"]:
                embed.add_field(
                    name="Kết quả trang này", value="Không có mục phù hợp trên trang này."
                )
            if data["excluded_pulls"]:
                embed.add_field(
                    name="Lọc kết quả",
                    value="Đã bỏ PR khỏi danh sách issues; có thể vẫn còn issues ở trang tiếp.",
                    inline=False,
                )
            if data["items"]:
                detail = "issue" if operation == "issues" else "pull"
                view.add_item(
                    GitHubPicker(
                        "Chọn một mục để đọc nội dung",
                        [
                            discord.SelectOption(
                                label=f"#{item['number']} {item['title']}"[:100],
                                value=str(item["number"]),
                            )
                            for item in data["items"]
                        ],
                        lambda i, number: read(i, detail, number=int(number)),
                    )
                )
            view.add_item(
                GitHubPicker(
                    "Lọc trạng thái",
                    [
                        discord.SelectOption(label=label, value=value)
                        for label, value in (
                            ("Đang mở", "open"),
                            ("Đã đóng", "closed"),
                            ("Tất cả", "all"),
                        )
                    ],
                    lambda i, state: read(i, operation, state=state),
                    row=2,
                )
            )
            if data["page"] > 1:
                view.add_item(
                    ConnectionAction(
                        "Trang trước",
                        lambda i: read(i, operation, page=data["page"] - 1, state=data["state"]),
                        row=3,
                    )
                )
            if data["may_have_more"]:
                view.add_item(
                    ConnectionAction(
                        "Trang sau",
                        lambda i: read(i, operation, page=data["page"] + 1, state=data["state"]),
                        row=3,
                    )
                )
        else:
            heading = data.get("path") or f"#{data['number']} {data['title']}"
            body = data["body"]
            embed.description = f"**{display(heading, 300)}**\n{display(body, 3300)}"
            if data["truncated"] or len(body) > 3000:
                embed.add_field(name="Nội dung rút gọn", value="Mở link nguồn để đọc đầy đủ.")
            embed.add_field(name="Nguồn", value=data["source_url"], inline=False)
        await self.dashboard.finish(interaction, embed, view)
