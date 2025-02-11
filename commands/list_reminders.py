from datetime import datetime
from zoneinfo import ZoneInfo
import discord
from discord import app_commands
from reminder import format_discord_timestamp, calculate_next_occurrence

@app_commands.command(name="list", description="List all active reminders in the server")
async def list_command(interaction: discord.Interaction):
    active_reminders = []
    now = datetime.now(ZoneInfo('UTC'))
    guild_id = interaction.guild.id if interaction.guild else None
    
    for r in interaction.client.reminder_manager.reminders:
        if r.guild_id != guild_id:
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

    user_reminders = {}
    for reminder in active_reminders:
        for target in reminder.targets:
            if target not in user_reminders:
                user_reminders[target] = []
            user_reminders[target].append(reminder)

    embed = discord.Embed(
        title=f"📋 Active Reminders for {interaction.guild.name}" if interaction.guild else "📋 Active Reminders",
        color=discord.Color.blue()
    )

    for user, user_reminder_list in user_reminders.items():
        reminder_texts = []
        for i, reminder in enumerate(sorted(user_reminder_list, key=lambda x: x.time), 1):
            message_preview = reminder.message
            for word in message_preview.split():
                if word.startswith('<@') and word.endswith('>'):
                    try:
                        user_id = int(word[2:-1].replace('!', ''))
                        mentioned_user = interaction.guild.get_member(user_id) if interaction.guild else None
                        if mentioned_user:
                            message_preview = message_preview.replace(word, f"@{mentioned_user.display_name}")
                    except ValueError:
                        continue

            recurring_str = f" (Recurring: {reminder.recurring})" if reminder.recurring else ""
            timezone_str = f" ({reminder.timezone})" if reminder.timezone != 'UTC' else ""
            other_users = [u.display_name for u in reminder.targets if u != user]
            with_others = f" (with {', '.join(other_users)})" if other_users else ""
            created_by = "" if reminder.author == user else f" (created by {reminder.author.display_name})"
            reminder_texts.append(
                f"**{i}.** {format_discord_timestamp(reminder.time)}: {message_preview}{recurring_str}{timezone_str}{with_others}{created_by}"
            )
        
        if reminder_texts:
            embed.add_field(
                name=f"Reminders for {user.display_name}",
                value="\n".join(reminder_texts),
                inline=False
            )

    await interaction.response.send_message(embed=embed)