from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import logging
import discord
from src.reminder import Reminder, format_discord_timestamp, calculate_next_occurrence

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 1000
MAX_MENTIONS_PER_REMINDER = 10
MAX_YEARS_IN_FUTURE = 10

async def handle_reminder(interaction: discord.Interaction, date: str, time: str, message: str, timezone: str = None, recurring: str = None):
    try:
        if not message:
            await interaction.response.send_message("⚠️ Please provide a message for your reminder.")
            return

        if len(message) > MAX_MESSAGE_LENGTH:
            await interaction.response.send_message(f"❌ Message is too long. Maximum length is {MAX_MESSAGE_LENGTH} characters.")
            return

        if not interaction.guild:
            await interaction.response.send_message("❌ Reminders can only be set in a server, not in DMs.")
            return

        author = interaction.user
        channel = interaction.channel
        mentioned_users = [author]
        mention_count = 0

        if hasattr(interaction, 'data') and 'resolved' in interaction.data and 'users' in interaction.data['resolved']:
            for user_id in interaction.data['resolved']['users']:
                mention_count += 1
                if mention_count > MAX_MENTIONS_PER_REMINDER:
                    await interaction.response.send_message(f"❌ Too many mentions. Maximum is {MAX_MENTIONS_PER_REMINDER} users per reminder.")
                    return
                    
                user = await interaction.guild.fetch_member(int(user_id))
                if user and user not in mentioned_users:
                    mentioned_users.append(user)

        timezone_override = None
        if timezone:
            try:
                timezone_override = ZoneInfo(timezone)
            except ZoneInfoNotFoundError:
                await interaction.response.send_message(f"❌ Invalid timezone '{timezone}'. Using server timezone.")
                return
        
        server_tz = ZoneInfo('UTC')
        try:
            try:
                naive_time = datetime.strptime(f"{date} {time}", '%Y-%m-%d %H:%M')
                if naive_time.year < 1970:
                    raise ValueError("Year must be 1970 or later")
                if naive_time.year > 9999:
                    raise ValueError("Year must be 9999 or earlier")
                
                max_future = datetime.now() + timedelta(days=MAX_YEARS_IN_FUTURE * 365)
                if naive_time > max_future:
                    await interaction.response.send_message(f"❌ Cannot set reminders more than {MAX_YEARS_IN_FUTURE} years in the future.")
                    return

            except ValueError as e:
                await interaction.response.send_message(
                    f"❌ Invalid date/time format: {str(e)}. Use 'YYYY-MM-DD HH:MM'.\n"
                    "Example: /reminder date:2025-02-10 time:15:30 message:Your message"
                )
                return

            local_time = naive_time.replace(tzinfo=timezone_override or server_tz)
            reminder_time = local_time.astimezone(ZoneInfo('UTC'))
            
            server_now = datetime.now(server_tz)
            if local_time < server_now and not recurring:
                await interaction.response.send_message("❌ Cannot set non-recurring reminders in the past!")
                return

        except Exception as e:
            logger.error(f"Error parsing date/time: {e}")
            await interaction.response.send_message("❌ Invalid date/time format. Use 'YYYY-MM-DD HH:MM'.")
            return

        if recurring:
            if recurring.lower() == 'none':
                await interaction.response.send_message("❌ The 'none' option is only available when editing reminders. When creating a new reminder, simply don't specify a recurring option.")
                return
            elif recurring.lower() not in ['daily', 'weekly', 'monthly']:
                await interaction.response.send_message("❌ Invalid recurring option. Use 'daily', 'weekly', or 'monthly'.")
                return

        try:
            reminder = Reminder(
                reminder_time,
                author,
                mentioned_users,
                message,
                channel,
                recurring.lower() if recurring else None,
                (timezone_override or server_tz).key
            )
            
            if reminder.time < datetime.now(ZoneInfo('UTC')) and recurring:
                next_time = calculate_next_occurrence(
                    reminder.time, 
                    recurring.lower(),
                    ZoneInfo(reminder.timezone)
                )
                while next_time and next_time <= datetime.now(ZoneInfo('UTC')):
                    next_time = calculate_next_occurrence(next_time, recurring.lower(), ZoneInfo(reminder.timezone))
                if next_time:
                    reminder.time = next_time
                else:
                    await interaction.response.send_message("❌ Could not calculate next valid occurrence for recurring reminder!")
                    return
            
            interaction.client.reminder_manager.reminders.append(reminder)
            interaction.client.reminder_manager.save_reminders()
            
            mentions_str = ' '.join(user.mention for user in mentioned_users)
            recurring_str = f" (Recurring: {recurring})" if recurring else ""
            timezone_str = f" ({reminder.timezone})" if reminder.timezone != 'UTC' else ""
            await interaction.response.send_message(f"✅ Reminder set for {format_discord_timestamp(reminder.time)} for {mentions_str}{recurring_str}{timezone_str}.")
        except Exception as e:
            logger.error(f"Error creating reminder: {e}")
            await interaction.response.send_message("❌ An error occurred while creating the reminder. Please try again.")
            return

    except Exception as e:
        logger.error(f"Error setting reminder: {e}")
        await interaction.response.send_message("❌ An error occurred while setting the reminder. Please try again.")