from datetime import datetime
from zoneinfo import ZoneInfo
import discord
from discord import app_commands
from reminder import format_discord_timestamp, calculate_next_occurrence
from .autocomplete import number_autocomplete

async def remove_reminder(ctx, number_str):
    is_interaction = isinstance(ctx, discord.Interaction)
    author = ctx.user if is_interaction else ctx.author
    guild_id = ctx.guild.id if ctx.guild else None
    
    try:
        index = int(number_str) - 1
    except (ValueError, TypeError):
        example = "/reminder remove number:1" if is_interaction else "!reminder remove 1"
        msg = f"❌ Please provide a valid reminder number. Example: {example}"
        if is_interaction:
            await ctx.response.send_message(msg) if not ctx.response.is_done() else await ctx.followup.send(msg)
        else:
            await ctx.send(msg)
        return

    now = datetime.now(ZoneInfo('UTC'))
    user_reminders = []
    client = ctx.client if is_interaction else ctx.bot
    for r in client.reminder_manager.reminders:
        if r.guild_id != guild_id:
            continue
            
        if author in r.targets:
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
        msg = "You have no active reminders."
        if is_interaction:
            await ctx.response.send_message(msg) if not ctx.response.is_done() else await ctx.followup.send(msg)
        else:
            await ctx.send(msg)
        return
    
    if index < 0 or index >= len(user_reminders):
        msg = f"❌ Invalid reminder number. Please use a number between 1 and {len(user_reminders)}."
        if is_interaction:
            await ctx.response.send_message(msg) if not ctx.response.is_done() else await ctx.followup.send(msg)
        else:
            await ctx.send(msg)
        return
    
    reminder_to_remove = user_reminders[index]
    
    if reminder_to_remove.author != author and not (hasattr(author, 'guild_permissions') and author.guild_permissions.manage_messages):
        msg = "❌ You can only remove reminders that you created."
        if is_interaction:
            await ctx.response.send_message(msg) if not ctx.response.is_done() else await ctx.followup.send(msg)
        else:
            await ctx.send(msg)
        return
    
    client.reminder_manager.reminders.remove(reminder_to_remove)
    client.reminder_manager.save_reminders()
    recurring_str = f" (Recurring: {reminder_to_remove.recurring})" if reminder_to_remove.recurring else ""
    timezone_str = f" ({reminder_to_remove.timezone})" if reminder_to_remove.timezone != 'UTC' else ""
    msg = f"✅ Removed reminder: {format_discord_timestamp(reminder_to_remove.time)} - {reminder_to_remove.message}{recurring_str}{timezone_str}"
    if is_interaction:
        await ctx.response.send_message(msg) if not ctx.response.is_done() else await ctx.followup.send(msg)
    else:
        await ctx.send(msg)

@app_commands.command(name="remove", description="Remove a reminder by its number")
@app_commands.describe(number="The number of the reminder (from /reminder list)")
@app_commands.autocomplete(number=number_autocomplete)
async def remove_command(interaction: discord.Interaction, number: int):
    await remove_reminder(interaction, str(number))