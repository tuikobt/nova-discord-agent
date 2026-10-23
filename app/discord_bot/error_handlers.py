import logging

import discord
from discord import app_commands

logger = logging.getLogger(__name__)
DENIED_MESSAGE = "Chỉ chủ tài khoản được sử dụng NOVA."
ERROR_MESSAGE = "NOVA gặp lỗi khi xử lý. Vui lòng thử lại lệnh; nếu vẫn lỗi, kiểm tra log vận hành."


async def send_private(interaction: discord.Interaction, content: str) -> None:
    try:
        if interaction.response.is_done():
            await interaction.followup.send(
                content, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
            )
        else:
            await interaction.response.send_message(
                content, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
            )
    except discord.HTTPException as error:
        logger.warning(
            "interaction_response_failed",
            extra={"interaction_id": interaction.id, "error_type": type(error).__name__},
        )


async def handle_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    original = getattr(error, "original", error)
    logger.error(
        "command_failed",
        extra={"interaction_id": interaction.id, "error_type": type(original).__name__},
    )
    await send_private(interaction, ERROR_MESSAGE)
