from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones
import logging
import discord
from discord import app_commands
from typing import Optional, List
from reminder import Reminder, format_discord_timestamp, calculate_next_occurrence

logger = logging.getLogger(__name__)

async def timezone_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    common_zones = [
        'UTC', 'Europe/Paris', 'Europe/London', 'America/New_York', 
        'America/Los_Angeles', 'Asia/Tokyo', 'Asia/Shanghai', 
        'Australia/Sydney', 'Pacific/Auckland'
    ]
    
    options = []
    for tz in common_zones:
        if not current or current.lower() in tz.lower():
            options.append(app_commands.Choice(name=tz, value=tz))
    
    if len(options) < 25:
        remaining_slots = 25 - len(options)
        all_zones = available_timezones()
        matching_zones = sorted([
            tz for tz in all_zones 
            if tz not in common_zones and (not current or current.lower() in tz.lower())
        ])
        
        for tz in matching_zones[:remaining_slots]:
            options.append(app_commands.Choice(name=tz, value=tz))
    
    return options

async def recurring_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    options = ['daily', 'weekly', 'monthly']
    return [
        app_commands.Choice(name=opt, value=opt)
        for opt in options if current.lower() in opt.lower()
    ]

async def message_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    command_options = [
        ('List all reminders', '"list"'),
        ('Show help', '"help"'),
    ]
    options = []
    
    for display, value in command_options:
        if not current or current.lower() in value.lower():
            options.append(app_commands.Choice(name=display, value=value))
    
    if current.lower().startswith('remove') or not current or current.lower().startswith('"remove'):
        now = datetime.now(ZoneInfo('UTC'))
        user_reminder_count = 0
        
        for r in interaction.client.reminder_manager.reminders:
            if r.time > now or r.recurring:
                if interaction.user in r.targets:
                    user_reminder_count += 1
                    if user_reminder_count <= 10:
                        reminder_preview = r.message[:30] + "..." if len(r.message) > 30 else r.message
                        remove_option = f'"remove {user_reminder_count}"'
                        recurring_str = f" (Recurring: {r.recurring})" if r.recurring else ""
                        remove_display = f"Remove #{user_reminder_count}: {reminder_preview}{recurring_str}"
                        options.append(app_commands.Choice(name=remove_display, value=remove_option))
    
    return options[:25]

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

            max_future = server_now + timedelta(days=365*5)
            if local_time > max_future and not recurring:
                await send_response("❌ Cannot set reminders more than 5 years in the future!")
                return

        except Exception as e:
            logger.error(f"Error parsing date/time: {e}")
            await send_response("❌ Invalid date/time format. Use 'YYYY-MM-DD HH:MM'.")
            return

        if recurring and recurring.lower() not in ['daily', 'weekly', 'monthly']:
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
            
            ctx.bot.reminder_manager.reminders.append(reminder)
            ctx.bot.reminder_manager.save_reminders()
            
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

async def show_help(ctx):
    is_interaction = isinstance(ctx, discord.Interaction)
    help_text = """📝 **Simple Reminder Bot Commands**

**Slash Commands:**
```
/reminder list
/reminder help
/reminder remove number:<number>
/reminder edit number:<number> [date:YYYY-MM-DD] [time:HH:MM] [message:MESSAGE] [timezone:ZONE] [recurring:TYPE]
/reminder set date:YYYY-MM-DD time:HH:MM message:MESSAGE [timezone:ZONE] [recurring:TYPE]
```

**Text Commands:**
```
!reminder list
!reminder help
!reminder remove NUMBER
!edit NUMBER date:YYYY-MM-DD time:HH:MM message:MESSAGE timezone:ZONE recurring:TYPE
!reminder YYYY-MM-DD HH:MM [tz:ZONE] [TYPE] [@users] MESSAGE
```

**Examples:**
Create a reminder:
```
/reminder set date:2024-02-10 time:14:00 message:@user1 @user2 Team meeting
!reminder 2024-02-10 14:00 tz:Europe/Paris daily @user1 @user2 Team meeting
```

**Options:**
• Timezone: Use timezone: (slash) or tz: (text) with region name
• Recurring: Use recurring: (slash) or word (text) - daily/weekly/monthly
• Time Format: 24-hour (HH:MM)"""

    if is_interaction:
        await ctx.response.send_message(help_text) if not ctx.response.is_done() else await ctx.followup.send(help_text)
    else:
        await ctx.send(help_text)

async def list_reminders(ctx):
    is_interaction = isinstance(ctx, discord.Interaction)
    active_reminders = []
    now = datetime.now(ZoneInfo('UTC'))
    guild_id = ctx.guild.id if ctx.guild else None
    
    for r in ctx.bot.reminder_manager.reminders:
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
        msg = "No active reminders in this server."
        if is_interaction:
            await ctx.response.send_message(msg) if not ctx.response.is_done() else await ctx.followup.send(msg)
        else:
            await ctx.send(msg)
        return

    user_reminders = {}
    for reminder in active_reminders:
        for target in reminder.targets:
            if target not in user_reminders:
                user_reminders[target] = []
            user_reminders[target].append(reminder)

    embed = discord.Embed(
        title=f"📋 Active Reminders for {ctx.guild.name}" if ctx.guild else "📋 Active Reminders",
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
                        mentioned_user = ctx.guild.get_member(user_id) if ctx.guild else None
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

    if is_interaction:
        await ctx.response.send_message(embed=embed) if not ctx.response.is_done() else await ctx.followup.send(embed=embed)
    else:
        await ctx.send(embed=embed)

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
    for r in ctx.bot.reminder_manager.reminders:
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
    
    ctx.bot.reminder_manager.reminders.remove(reminder_to_remove)
    ctx.bot.reminder_manager.save_reminders()
    recurring_str = f" (Recurring: {reminder_to_remove.recurring})" if reminder_to_remove.recurring else ""
    timezone_str = f" ({reminder_to_remove.timezone})" if reminder_to_remove.timezone != 'UTC' else ""
    msg = f"✅ Removed reminder: {format_discord_timestamp(reminder_to_remove.time)} - {reminder_to_remove.message}{recurring_str}{timezone_str}"
    if is_interaction:
        await ctx.response.send_message(msg) if not ctx.response.is_done() else await ctx.followup.send(msg)
    else:
        await ctx.send(msg)