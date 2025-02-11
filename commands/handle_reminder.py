from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import logging
import discord
from reminder import Reminder, format_discord_timestamp, calculate_next_occurrence

logger = logging.getLogger(__name__)

async def handle_reminder(ctx, date: str, time: str, message: str, timezone: str = None, recurring: str = None):
    is_interaction = isinstance(ctx, discord.Interaction)
    async def send_response(content):
        if is_interaction:
            if not ctx.response.is_done():
                await ctx.response.send_message(content)
            else:
                await ctx.followup.send(content)
        else:
            await ctx.send(content)

    try:
        if not message:
            await send_response("⚠️ Please provide a message for your reminder.")
            return

        if not ctx.guild:
            await send_response("❌ Reminders can only be set in a server, not in DMs.")
            return

        author = ctx.user if is_interaction else ctx.author
        channel = ctx.channel
        mentioned_users = [author]

        if is_interaction:
            if hasattr(ctx, 'data') and 'resolved' in ctx.data and 'users' in ctx.data['resolved']:
                for user_id in ctx.data['resolved']['users']:
                    user = await ctx.guild.fetch_member(int(user_id))
                    if user and user not in mentioned_users:
                        mentioned_users.append(user)
        else:
            for word in message.split():
                if word.startswith('<@') and word.endswith('>'):
                    try:
                        user_id = int(word[2:-1].replace('!', ''))
                        user = ctx.guild.get_member(user_id)
                        if user and user not in mentioned_users:
                            mentioned_users.append(user)
                    except ValueError:
                        continue

        timezone_override = None
        if timezone:
            try:
                timezone_override = ZoneInfo(timezone)
            except ZoneInfoNotFoundError:
                await send_response(f"❌ Invalid timezone '{timezone}'. Using server timezone.")
                return
        
        server_tz = ZoneInfo('UTC')
        try:
            try:
                naive_time = datetime.strptime(f"{date} {time}", '%Y-%m-%d %H:%M')
                if naive_time.year < 1970:
                    raise ValueError("Year must be 1970 or later")
                if naive_time.year > 9999:
                    raise ValueError("Year must be 9999 or earlier")
            except ValueError as e:
                example = "!reminder 2025-02-10 15:30 Your message" if not is_interaction else "/reminder date: 2025-02-10 time: 15:30 message: Your message"
                await send_response(f"❌ Invalid date/time format: {str(e)}. Use 'YYYY-MM-DD HH:MM'.\nExample: {example}")
                return

            local_time = naive_time.replace(tzinfo=timezone_override or server_tz)
            reminder_time = local_time.astimezone(ZoneInfo('UTC'))
            
            server_now = datetime.now(server_tz)
            if local_time < server_now and not recurring:
                await send_response("❌ Cannot set non-recurring reminders in the past!")
                return

        except Exception as e:
            logger.error(f"Error parsing date/time: {e}")
            await send_response("❌ Invalid date/time format. Use 'YYYY-MM-DD HH:MM'.")
            return

        if recurring:
            if recurring.lower() == 'none':
                await send_response("❌ The 'none' option is only available when editing reminders. When creating a new reminder, simply don't specify a recurring option.")
                return
            elif recurring.lower() not in ['daily', 'weekly', 'monthly']:
                await send_response("❌ Invalid recurring option. Use 'daily', 'weekly', or 'monthly'.")
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
                    await send_response("❌ Could not calculate next valid occurrence for recurring reminder!")
                    return
            
            client = ctx.client if is_interaction else ctx.bot
            client.reminder_manager.reminders.append(reminder)
            client.reminder_manager.save_reminders()
            
            mentions_str = ' '.join(user.mention for user in mentioned_users)
            recurring_str = f" (Recurring: {recurring})" if recurring else ""
            timezone_str = f" ({reminder.timezone})" if reminder.timezone != 'UTC' else ""
            await send_response(f"✅ Reminder set for {format_discord_timestamp(reminder.time)} for {mentions_str}{recurring_str}{timezone_str}.")
        except Exception as e:
            logger.error(f"Error creating reminder: {e}")
            await send_response("❌ An error occurred while creating the reminder. Please try again.")
            return

    except Exception as e:
        logger.error(f"Error setting reminder: {e}")
        await send_response("❌ An error occurred while setting the reminder. Please try again.")