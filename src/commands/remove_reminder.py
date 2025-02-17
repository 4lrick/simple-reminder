from datetime import datetime
from zoneinfo import ZoneInfo
import discord
from discord import app_commands
import logging
from src.reminder import format_discord_timestamp, calculate_next_occurrence
from .autocomplete import number_autocomplete

logger = logging.getLogger('reminder_bot.commands.remove')

@app_commands.command(name="remove", description="Remove a reminder by its number")
@app_commands.describe(number="The number of the reminder (from /reminder list)")
@app_commands.autocomplete(number=number_autocomplete)
async def remove_command(interaction: discord.Interaction, number: int):
    logger.info(
        f"Command: /reminder remove | User: {interaction.user.name} ({interaction.user.id}) | "
        f"Server: {interaction.guild.name} ({interaction.guild.id}) | "
        f"Number: {number}"
    )
    
    author = interaction.user
    guild_id = interaction.guild.id if interaction.guild else None
    
    try:
        index = number - 1
    except (ValueError, TypeError):
        await interaction.response.send_message("❌ Please provide a valid reminder number.")
        return

    now = datetime.now(ZoneInfo('UTC'))
    user_reminders = []
    
    for r in interaction.client.reminder_manager.reminders:
        if r.guild_id != guild_id:
            continue
            
        if interaction.user not in r.targets:
            continue
            
        if r.time > now:
            user_reminders.append(r)
        elif r.recurring:
            next_time = calculate_next_occurrence(r.time, r.recurring)
            while next_time and next_time <= now:
                next_time = calculate_next_occurrence(next_time, r.recurring)
            if next_time:
                r.time = next_time
                user_reminders.append(r)
    
    user_reminders.sort(key=lambda x: x.time)
    
    if not user_reminders:
        await interaction.response.send_message("You have no active reminders.")
        return
    
    if index < 0 or index >= len(user_reminders):
        await interaction.response.send_message(f"❌ Invalid reminder number. Please use a number between 1 and {len(user_reminders)}.")
        return
    
    reminder_to_remove = user_reminders[index]
    
    if reminder_to_remove.author != author and not author.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ You can only remove reminders that you created.")
        return
    
    interaction.client.reminder_manager.reminders.remove(reminder_to_remove)
    interaction.client.reminder_manager.save_reminders()
    recurring_str = f" (Recurring: {reminder_to_remove.recurring})" if reminder_to_remove.recurring else ""
    timezone_str = f" ({reminder_to_remove.timezone})" if reminder_to_remove.timezone != 'UTC' else ""
    await interaction.response.send_message(
        f"✅ Removed reminder: {format_discord_timestamp(reminder_to_remove.time)} - {reminder_to_remove.message}{recurring_str}{timezone_str}"
    )