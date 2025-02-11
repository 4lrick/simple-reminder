from datetime import datetime
from zoneinfo import ZoneInfo
import discord
from discord import app_commands
from core.reminder import format_discord_timestamp
from commands.handle_reminder import handle_reminder
from commands.autocomplete import timezone_autocomplete, recurring_autocomplete

@app_commands.command(name="set", description="Set a new reminder")
@app_commands.describe(
    date="Date in YYYY-MM-DD format",
    time="Time in HH:MM format",
    message="The reminder message (include @mentions here)",
    timezone="Optional: timezone (e.g., Europe/Paris)",
    recurring="Optional: recurring schedule (daily, weekly, monthly)"
)
@app_commands.autocomplete(timezone=timezone_autocomplete, recurring=recurring_autocomplete)
async def reminder_set(
    interaction: discord.Interaction,
    date: str,
    time: str,
    message: str,
    timezone: str = None,
    recurring: str = None
):
    await handle_reminder(interaction, date, time, message, timezone, recurring)