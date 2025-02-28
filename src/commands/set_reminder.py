from datetime import datetime
from zoneinfo import ZoneInfo
import discord
from discord import app_commands
import logging
from src.reminder import format_discord_timestamp, calculate_next_occurrence
from .handle_reminder import handle_reminder
from .autocomplete import timezone_autocomplete, recurring_autocomplete

logger = logging.getLogger('reminder_bot.commands.set')

@app_commands.command(name="set", description="Set a new reminder")
@app_commands.describe(
    date="Date in YYYY-MM-DD format",
    time="Time in HH:MM format",
    message="The reminder message",
    mentions="Users to mention (@user1 @user2)",
    timezone="Optional: timezone (e.g., Europe/Paris)",
    recurring="Optional: recurring schedule (daily, weekly, monthly)"
)
@app_commands.autocomplete(timezone=timezone_autocomplete, recurring=recurring_autocomplete)
async def reminder_set(
    interaction: discord.Interaction,
    date: str,
    time: str,
    message: str,
    mentions: str = None,
    timezone: str = None,
    recurring: str = None
):
    logger.info(
        f"Command: /reminder set | User: {interaction.user.name} ({interaction.user.id}) | "
        f"Server: {interaction.guild.name} ({interaction.guild.id}) | "
        f"Date: {date} | Time: {time} | TZ: {timezone or 'UTC'} | Recurring: {recurring or 'No'}"
    )
    
    full_message = message
    separate_mentions = None
    
    if mentions:
        separate_mentions = mentions
    
    await handle_reminder(interaction, date, time, full_message, timezone, recurring, separate_mentions)