from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import discord
from discord import app_commands
import logging
from src.reminder import format_discord_timestamp, calculate_next_occurrence
from .autocomplete import timezone_autocomplete, recurring_autocomplete, number_autocomplete, message_autocomplete

logger = logging.getLogger('reminder_bot.commands.edit')

@app_commands.command(name="edit", description="Edit an existing reminder")
@app_commands.describe(
    number="The reminder number from /reminder list (you can type a specific number)",
    date="(Optional) New date in YYYY-MM-DD format",
    time="(Optional) New time in HH:MM format",
    message="(Optional) New message - press TAB to autofill current message",
    timezone="(Optional) New timezone (e.g., Europe/Paris)",
    recurring="(Optional) Change recurring schedule (daily, weekly, monthly, or 'none' to remove)"
)
@app_commands.autocomplete(
    number=number_autocomplete,
    timezone=timezone_autocomplete,
    recurring=recurring_autocomplete,
    message=message_autocomplete
)
async def edit_command(
    interaction: discord.Interaction,
    number: int,
    date: str = None,
    time: str = None,
    message: str = None,
    timezone: str = None,
    recurring: str = None
):
    logger.info(
        f"Command: /reminder edit | User: {interaction.user.name} ({interaction.user.id}) | "
        f"Server: {interaction.guild.name} ({interaction.guild.id}) | "
        f"Number: {number} | Changes: {', '.join(f'{k}={v}' for k, v in {'date': date, 'time': time, 'message': message, 'timezone': timezone, 'recurring': recurring}.items() if v is not None)}"
    )
    
    author = interaction.user
    guild_id = interaction.guild.id if interaction.guild else None
    
    now = datetime.now(ZoneInfo('UTC'))
    user_reminders = []
    
    for r in interaction.client.reminder_manager.reminders:
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
        await interaction.response.send_message("You have no active reminders to edit.")
        return
    
    try:
        index = number - 1
    except (ValueError, TypeError):
        await interaction.response.send_message("❌ Please provide a valid reminder number.")
        return
    
    if index < 0 or index >= len(user_reminders):
        await interaction.response.send_message(f"❌ Invalid reminder number. Please use a number between 1 and {len(user_reminders)}.")
        return
    
    reminder = user_reminders[index]
    
    if reminder.author != author and not author.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ You can only edit reminders that you created.")
        return

    current_timezone = reminder.timezone
    current_time = reminder.time
    new_timezone = timezone if timezone else current_timezone
    new_recurring = None
    new_time_utc = None
    

    if timezone:
        try:
            new_tz = ZoneInfo(timezone)
        except ZoneInfoNotFoundError:
            await interaction.response.send_message(f"❌ Invalid timezone '{timezone}'. Timezone not changed.")
            return

    if date or time:
        try:
            if date and time:
                new_time_str = f"{date} {time}"
            elif date:
                new_time_str = f"{date} {current_time.strftime('%H:%M')}"
            else:
                current_local_time = current_time.astimezone(ZoneInfo(new_timezone))
                new_time_str = f"{current_local_time.strftime('%Y-%m-%d')} {time}"
            
            naive_time = datetime.strptime(new_time_str, '%Y-%m-%d %H:%M')
            if naive_time.year < 1970:
                raise ValueError("Year must be 1970 or later")
            if naive_time.year > 9999:
                raise ValueError("Year must be 9999 or earlier")
            
            tz = ZoneInfo(new_timezone)
            local_time = naive_time.replace(tzinfo=tz)
            new_time_utc = local_time.astimezone(ZoneInfo('UTC'))
            
            server_now = datetime.now(ZoneInfo('UTC'))
            if new_time_utc < server_now and not reminder.recurring:
                await interaction.response.send_message(
                    f"❌ The specified time {format_discord_timestamp(local_time)} ({new_timezone}) "
                    "is in the past. Cannot set non-recurring reminders in the past!"
                )
                return
        except ValueError as e:
            await interaction.response.send_message(f"❌ Invalid date/time format: {str(e)}. Use 'YYYY-MM-DD' for date and 'HH:MM' for time.")
            return
    
    if recurring:
        if recurring.lower() == 'none':
            new_recurring = None
        elif recurring.lower() in ['daily', 'weekly', 'monthly']:
            new_recurring = recurring.lower()
            check_time = new_time_utc if new_time_utc else current_time
            
            if check_time < datetime.now(ZoneInfo('UTC')):
                next_time = calculate_next_occurrence(
                    check_time,
                    new_recurring,
                    ZoneInfo(new_timezone)
                )
                while next_time and next_time <= datetime.now(ZoneInfo('UTC')):
                    next_time = calculate_next_occurrence(next_time, new_recurring, ZoneInfo(new_timezone))
                if next_time:
                    new_time_utc = next_time
                else:
                    await interaction.response.send_message("❌ Could not calculate next valid occurrence for recurring reminder!")
                    return
        else:
            await interaction.response.send_message("❌ Invalid recurring option. Use 'daily', 'weekly', 'monthly', or 'none'.")
            return

    new_targets = None
    new_message = None
    if message:
        has_mentions = any(word.startswith('<@') and word.endswith('>') for word in message.split())
        if not has_mentions:
            original_mentions = [user.mention for user in reminder.targets if user != reminder.author]
            message = f"{message} {' '.join(original_mentions)}".strip()
        new_message = message
        
        new_targets = [author]
        mention_count = 0
        
        for word in message.split():
            if word.startswith('<@&') and word.endswith('>'):
                try:
                    role_id = int(word[3:-1])
                    role = interaction.guild.get_role(role_id)
                    if role:
                        mention_count += len(role.members)
                        if mention_count > 25:
                            await interaction.response.send_message("❌ Too many total mentions (including role members). Maximum is 25 users per reminder.")
                            return
                        for member in role.members:
                            if member not in new_targets:
                                new_targets.append(member)
                except ValueError:
                    continue
            elif word.startswith('<@') and word.endswith('>'):
                try:
                    user_id = int(word[2:-1].replace('!', ''))
                    mention_count += 1
                    if mention_count > 25:
                        await interaction.response.send_message("❌ Too many mentions. Maximum is 25 users per reminder.")
                        return
                    user = interaction.guild.get_member(user_id)
                    if user and user not in new_targets:
                        new_targets.append(user)
                except ValueError:
                    continue
        
        if not new_targets:
            await interaction.response.send_message("❌ Could not find any valid users to remind (including role members).")
            return

    if timezone:
        reminder.timezone = new_timezone
    if new_time_utc:
        reminder.time = new_time_utc
    if recurring:
        reminder.recurring = new_recurring
    if new_message:
        reminder.message = new_message
        reminder.targets = new_targets
    
    interaction.client.reminder_manager.save_reminders()
    
    mentions_str = ' '.join(user.mention for user in reminder.targets)
    recurring_str = f" (Recurring: {reminder.recurring})" if reminder.recurring else ""
    timezone_str = f" ({reminder.timezone})" if reminder.timezone != 'UTC' else ""
    
    await interaction.response.send_message(
        f"✅ Reminder updated.\n"
        f"New reminder:\n"
        f"Time: {format_discord_timestamp(reminder.time)}\n"
        f"For: {mentions_str}\n"
        f"Message: {reminder.message}{recurring_str}{timezone_str}"
    )