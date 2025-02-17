from datetime import datetime
from zoneinfo import ZoneInfo
import discord
from discord import app_commands
import logging
from src.reminder import format_discord_timestamp, calculate_next_occurrence

logger = logging.getLogger('reminder_bot.commands.list')

@app_commands.command(name="list", description="List all active reminders in the server")
@app_commands.describe(page="Page number (10 reminders per page)")
async def list_command(interaction: discord.Interaction, page: int = 1):
    logger.info(
        f"Command: /reminder list | User: {interaction.user.name} ({interaction.user.id}) | "
        f"Server: {interaction.guild.name if interaction.guild else 'DM'} ({interaction.guild.id if interaction.guild else 'N/A'}) | "
        f"Page: {page}"
    )
    
    REMINDERS_PER_PAGE = 10
    
    active_reminders = []
    now = datetime.now(ZoneInfo('UTC'))
    guild_id = interaction.guild.id if interaction.guild else None
    
    for r in interaction.client.reminder_manager.reminders:
        if r.guild_id != guild_id:
            continue
            
        if interaction.user not in r.targets:
            continue
            
        if r.time > now:
            active_reminders.append(r)
        elif r.recurring:
            next_time = calculate_next_occurrence(r.time, r.recurring)
            while next_time and next_time <= now:
                next_time = calculate_next_occurrence(next_time, r.recurring)
            if next_time:
                r.time = next_time
                active_reminders.append(r)

    if not active_reminders:
        await interaction.response.send_message("No active reminders in this server.")
        return

    active_reminders.sort(key=lambda x: x.time)
    total_reminders = len(active_reminders)
    max_pages = (total_reminders + REMINDERS_PER_PAGE - 1) // REMINDERS_PER_PAGE
    
    if page < 1 or page > max_pages:
        message = "❌ Invalid page number."
        if max_pages > 1:
            message += f" Please use a number between 1 and {max_pages}."
        await interaction.response.send_message(message)
        return

    embed = discord.Embed(
        title=f"📋 Active Reminders for {interaction.guild.name} (Page {page}/{max_pages})" if interaction.guild else f"📋 Active Reminders (Page {page}/{max_pages})",
        color=discord.Color.blue()
    )

    start_idx = (page - 1) * REMINDERS_PER_PAGE
    end_idx = min(start_idx + REMINDERS_PER_PAGE, total_reminders)
    
    for i, reminder in enumerate(active_reminders[start_idx:end_idx], start=start_idx + 1):
        message_preview = reminder.message
        for word in message_preview.split():
            if word.startswith('<@&') and word.endswith('>'):
                try:
                    role_id = int(word[3:-1])
                    role = interaction.guild.get_role(role_id)
                    if role:
                        message_preview = message_preview.replace(word, f"@{role.name}")
                except ValueError:
                    continue
            elif word.startswith('<@') and word.endswith('>'):
                try:
                    user_id = int(word[2:-1].replace('!', ''))
                    mentioned_user = interaction.guild.get_member(user_id) if interaction.guild else None
                    if mentioned_user:
                        message_preview = message_preview.replace(word, f"@{mentioned_user.display_name}")
                except ValueError:
                    continue

        recurring_str = f" (Recurring: {reminder.recurring})" if reminder.recurring else ""
        timezone_str = f" ({reminder.timezone})" if reminder.timezone != 'UTC' else ""
        targets_str = ", ".join(t.display_name for t in reminder.targets)
        created_by = "" if reminder.author == interaction.user else f"\nCreated by {reminder.author.display_name}"
        
        embed.add_field(
            name=f"#{i}. {format_discord_timestamp(reminder.time)}",
            value=f"**Message:** {message_preview}\n**For:** {targets_str}{recurring_str}{timezone_str}{created_by}",
            inline=False
        )

    if page < max_pages:
        embed.set_footer(text=f"Use /reminder list page:{page+1} to see more reminders")

    await interaction.response.send_message(embed=embed)