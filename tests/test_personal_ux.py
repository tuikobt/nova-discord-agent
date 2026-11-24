import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

from test_personal import MEMORY, approve, personal_bundle

from app.discord_bot.agent_controller import preview_pages, proposal_view
from app.discord_bot.renderers.dashboard import LEGACY_TITLE
from app.discord_bot.views.dashboard import DashboardView
from app.discord_bot.views.guide import SECTIONS, GuideSelect, GuideView, render_guide
from app.discord_bot.views.personal import MemoryKindView, PolicyView, ReportsView, WorkView


def test_vietnamese_buttons_preserve_existing_persistent_ids(controller):
    async def scenario():
        view = DashboardView(controller)
        buttons = {item.custom_id: item for item in view.children}
        assert buttons["nova:dashboard:v1:tasks:tasks"].label == "Việc cần làm"
        assert buttons["nova:dashboard:v1:ai:ai_assistant"].label == "Nhắn NOVA"
        assert buttons["nova:dashboard:v1:help:help"].label == "Hướng dẫn"
        assert view.is_persistent()

    asyncio.run(scenario())


def test_guide_sections_have_useful_steps_and_shortcuts(controller, interaction):
    async def scenario():
        view = GuideView(controller)
        assert all(len(render_guide(key)) <= 6000 for key in SECTIONS)
        select = next(item for item in view.children if isinstance(item, GuideSelect))
        select._values = ["planning"]
        await select.callback(interaction)
        interaction.response.defer.assert_awaited_once_with()
        embed = interaction.edit_original_response.await_args.kwargs["embed"]
        assert "Xếp lịch" in embed.title and "Duyệt" in str(embed.to_dict())
        assert any(
            item.label == "Kế hoạch & báo cáo" for item in view.children if hasattr(item, "label")
        )

    asyncio.run(scenario())


def test_guide_denies_nonowner_before_navigation(controller, interaction):
    async def scenario():
        view = GuideView(controller)
        select = next(item for item in view.children if isinstance(item, GuideSelect))
        select._values = ["planning"]
        interaction.user.id += 1
        await select.callback(interaction)
        interaction.edit_original_response.assert_not_awaited()

    asyncio.run(scenario())


def test_memory_category_buttons_open_single_input_then_propose(core_ui_factory, interaction):
    async def scenario():
        async with core_ui_factory() as (_, dashboard):
            personal = dashboard.personal
            personal.propose = AsyncMock()
            view = MemoryKindView(personal)
            await view.input(interaction, "routine")
            modal = interaction.response.send_modal.await_args.args[0]
            assert len(modal.children) == 1
            personal.propose.assert_not_awaited()
            modal.children[0]._value = "Tôi thường học vào sáng sớm"
            await modal.on_submit(interaction)
            assert personal.propose.await_args.args[1] == "propose_memory"
            assert personal.propose.await_args.args[2]["kind"] == "routine"

    asyncio.run(scenario())


def test_weekly_day_picker_keeps_numeric_codes_out_of_form(core_ui_factory, interaction):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            personal = dashboard.personal
            personal.propose = AsyncMock()
            config = await personal.core.personal.settings(env.owner)
            view = PolicyView(personal, config["policies"]["weekly"])
            await view.weekday(interaction, ["0"])
            form = interaction.response.send_modal.await_args.args[0]
            assert len(form.children) == 1
            form.children[0]._value = "08:30"
            await form.on_submit(interaction)
            args = personal.propose.await_args.args[2]
            assert args["weekday"] == 0 and args["time"] == "08:30" and not args["enabled"]

    asyncio.run(scenario())


def test_quick_plans_use_local_today_and_next_monday(core_ui_factory, interaction):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            personal = dashboard.personal
            personal.core.personal.clock = lambda: datetime(2030, 1, 10, 3, tzinfo=UTC)
            personal.planner = AsyncMock()
            config = await personal.core.personal.settings(env.owner)
            view = ReportsView(personal, config, dict(items=[], total=0, page=0))
            await view.quick_plan(interaction, "today")
            personal.planner.assert_awaited_with(interaction, "2030-01-10", 1)
            await view.quick_plan(interaction, "week")
            personal.planner.assert_awaited_with(interaction, "2030-01-14", 7)

    asyncio.run(scenario())


def test_read_navigation_updates_current_panel_but_notifications_open_privately(
    core_ui_factory, interaction
):
    async def scenario():
        async with core_ui_factory() as (_, dashboard):
            await dashboard.personal.ack(interaction)
            interaction.response.defer.assert_awaited_once_with()
            interaction.response.is_done.return_value = False
            interaction.response.defer.reset_mock()
            await dashboard.personal.ack(interaction, new_panel=True)
            interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)

    asyncio.run(scenario())


def test_human_memory_previews_show_complete_content_and_last_page_approval(core_factory):
    async def scenario():
        async with core_factory() as env:
            _, pending, _, _ = personal_bundle(env)
            content = "sở thích " * 100
            receipt = await approve(
                env, pending, "propose_memory", {**MEMORY, "content": content.strip()}
            )
            p = await pending.propose(
                env.owner,
                "update_memory",
                dict(
                    memory_id=receipt["ids"][0],
                    expected_version=1,
                    **{**MEMORY, "content": "thói quen " * 99},
                ),
                turn="edit",
            )
            chunks = preview_pages(p)
            rendered = "".join(chunks)
            assert len(chunks) > 1
            assert receipt["ids"][0] not in rendered
            assert "use_for_ai" not in rendered and "Sở thích" in rendered
            assert content.strip() in rendered
            assert not any(
                getattr(item, "action", None) == "keep" for item in proposal_view(p, 0).children
            )
            assert any(
                getattr(item, "action", None) == "keep"
                for item in proposal_view(p, len(chunks) - 1).children
            )

    asyncio.run(scenario())


def test_work_presets_do_not_save_until_approval(core_ui_factory, interaction):
    async def scenario():
        async with core_ui_factory() as (env, dashboard):
            config = await dashboard.personal.core.personal.settings(env.owner)
            view = WorkView(dashboard.personal, config["work"])
            await next(
                item for item in view.children if getattr(item, "label", None) == "Thứ Hai–Thứ Sáu"
            ).callback(interaction)
            interaction.response.send_modal.assert_awaited_once()
            assert not (await dashboard.personal.core.personal.settings(env.owner))["work"][
                "workdays"
            ]

    asyncio.run(scenario())


def test_legacy_anchor_title_still_recognized(controller):
    async def scenario():
        from types import SimpleNamespace

        import discord

        from app.discord_bot.renderers.dashboard import ANCHOR_MARKER

        embed = discord.Embed(title=LEGACY_TITLE)
        embed.set_footer(text=ANCHOR_MARKER)
        message = SimpleNamespace(author=controller.client.user, embeds=[embed])
        assert controller.publisher.is_anchor(message)

    asyncio.run(scenario())
