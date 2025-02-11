import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
import asyncio
import os
import json
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones
import logging
from typing import Optional, Literal

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = False

reminders = []
SAVE_FILE = 'reminders.json'
CLEANUP_DAYS = 7

def format_discord_timestamp(dt: datetime, style: Literal['t', 'T', 'd', 'D', 'f', 'F', 'R'] = 'f') -> str:
    """Format a datetime object into a Discord timestamp string.
    
    Args:
        dt: The datetime object to format
        style: Discord timestamp style
            t: Short Time (e.g., 2:30 PM)
            T: Long Time (e.g., 2:30:00 PM)
            d: Short Date (e.g., 02/16/2024)
            D: Long Date (e.g., February 16, 2024)
            f: Short Date/Time (e.g., February 16, 2024 2:30 PM)
            F: Long Date/Time (e.g., Friday, February 16, 2024 2:30 PM)
            R: Relative Time (e.g., 2 hours ago)
    
    Returns:
        A Discord formatted timestamp string
    """
    if not isinstance(dt, datetime):
        raise TypeError("dt must be a datetime object")
    if style not in ['t', 'T', 'd', 'D', 'f', 'F', 'R']:
        raise ValueError("Invalid timestamp style")
    return f"<t:{int(dt.timestamp())}:{style}>"

def get_timezone(timezone_name):
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        logger.error(f"Invalid timezone: {timezone_name}")
        return None
    except Exception as e:
        logger.error(f"Error processing timezone {timezone_name}: {e}")
        return None

def save_reminders():
    data = [reminder.to_dict() for reminder in reminders]
    try:
        with open(SAVE_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving reminders: {e}")

async def load_reminders():
    if not os.path.exists(SAVE_FILE):
        return
    
    try:
        with open(SAVE_FILE, 'r') as f:
            data = json.load(f)
        
        for reminder_data in data:
            reminder = await Reminder.from_dict(reminder_data, bot)
            if reminder:
                reminders.append(reminder)
        
        logger.info(f"Loaded {len(reminders)} reminders from {SAVE_FILE}")
    except Exception as e:
        logger.error(f"Error loading reminders: {e}")

class Reminder:
    def __init__(self, time, author, targets, message, channel, recurring=None, timezone=None):
        self.time = time
        self.author = author
        self.targets = targets
        self.message = message
        self.channel = channel
        self.recurring = recurring
        self.timezone = timezone or 'UTC'
    
    def to_dict(self):
        return {
            'time': self.time.isoformat(),
            'author_id': self.author.id,
            'target_ids': [user.id for user in self.targets],
            'message': self.message,
            'channel_id': self.channel.id,
            'recurring': self.recurring,
            'timezone': self.timezone
        }
    
    @classmethod
    async def from_dict(cls, data, bot):
        time = datetime.fromisoformat(data['time'])
        author = await bot.fetch_user(data['author_id'])
        targets = []
        for user_id in data['target_ids']:
            try:
                user = await bot.fetch_user(user_id)
                targets.append(user)
            except discord.NotFound:
                continue
        channel = bot.get_channel(data['channel_id'])
        if not channel:
            try:
                channel = await bot.fetch_channel(data['channel_id'])
            except (discord.NotFound, discord.Forbidden):
                return None
        
        timezone = data.get('timezone', 'UTC')
        reminder = cls(time, author, targets, data['message'], channel, data['recurring'], timezone)
        
        now = datetime.now(ZoneInfo('UTC'))
        if reminder.time <= now and reminder.recurring:
            next_time = calculate_next_occurrence(reminder.time, reminder.recurring)
            while next_time and next_time <= now:
                next_time = calculate_next_occurrence(next_time, reminder.recurring)
            if next_time:
                reminder.time = next_time
                return reminder
        elif reminder.time > now or reminder.recurring:
            return reminder
        return None

async def timezone_autocomplete(interaction: discord.Interaction, current: str) -> list[discord.app_commands.Choice[str]]:
    common_zones = [
        'UTC', 'Europe/Paris', 'Europe/London', 'America/New_York', 
        'America/Los_Angeles', 'Asia/Tokyo', 'Asia/Shanghai', 
        'Australia/Sydney', 'Pacific/Auckland'
    ]
    
    options = []
    
    for tz in common_zones:
        if not current or current.lower() in tz.lower():
            options.append(discord.app_commands.Choice(name=tz, value=tz))
    
    if len(options) < 25:
        remaining_slots = 25 - len(options)
        all_zones = available_timezones()
        matching_zones = sorted([
            tz for tz in all_zones 
            if tz not in common_zones and (not current or current.lower() in tz.lower())
        ])
        
        for tz in matching_zones[:remaining_slots]:
            options.append(discord.app_commands.Choice(name=tz, value=tz))
    
    return options

async def recurring_autocomplete(interaction: discord.Interaction, current: str) -> list[discord.app_commands.Choice[str]]:
    options = ['daily', 'weekly', 'monthly']
    return [
        discord.app_commands.Choice(name=opt, value=opt)
        for opt in options if current.lower() in opt.lower()
    ]

async def message_autocomplete(interaction: discord.Interaction, current: str) -> list[discord.app_commands.Choice[str]]:
    command_options = [
        ('List all reminders', '"list"'),
        ('Show help', '"help"'),
    ]
    options = []
    
    for display, value in command_options:
        if not current or current.lower() in value.lower():
            options.append(discord.app_commands.Choice(name=display, value=value))
    
    if current.lower().startswith('remove') or not current or current.lower().startswith('"remove'):
        active_reminders = []
        now = datetime.now(ZoneInfo('UTC'))
        user_reminder_count = 0
        
        for r in reminders:
            if r.time > now or r.recurring:
                if interaction.user in r.targets:
                    user_reminder_count += 1
                    if user_reminder_count <= 10:
                        reminder_preview = r.message[:30] + "..." if len(r.message) > 30 else r.message
                        remove_option = f'"remove {user_reminder_count}"'
                        recurring_str = f" (Recurring: {r.recurring})" if r.recurring else ""
                        remove_display = f"Remove #{user_reminder_count}: {reminder_preview}{recurring_str}"
                        options.append(discord.app_commands.Choice(name=remove_display, value=remove_option))
    
    return options[:25]

async def users_autocomplete(interaction: discord.Interaction, current: str) -> list[discord.app_commands.Choice[str]]:
    choices = []
    if interaction.guild:
        selected_users = current.strip().split()
        current_typing = selected_users[-1] if selected_users else ''
        selected_users = selected_users[:-1]
        
        selected_ids = set()
        for uid in selected_users:
            if uid.isdigit():
                selected_ids.add(int(uid))
        
        async for member in interaction.guild.fetch_members(limit=100):
            if member.id in selected_ids:
                continue
            
            if not current_typing or current_typing.lower() in member.display_name.lower():
                new_selection = selected_users + [str(member.id)]
                
                display_name = member.display_name
                if selected_users:
                    selected_names = []
                    for uid in selected_users:
                        if uid.isdigit():
                            try:
                                user = await interaction.guild.fetch_member(int(uid))
                                if user:
                                    selected_names.append(user.display_name)
                            except:
                                continue
                    if selected_names:
                        display_name += f" (with {', '.join(selected_names)})"
                
                choices.append(discord.app_commands.Choice(
                    name=display_name,
                    value=' '.join(new_selection)
                ))
    
    return choices[:25]

async def remove_number_autocomplete(interaction: discord.Interaction, current: str) -> list[discord.app_commands.Choice[str]]:
    choices = []
    now = datetime.now(ZoneInfo('UTC'))
    author = interaction.user
    
    active_reminders = []
    for r in reminders:
        if r.time > now and author in r.targets:
            active_reminders.append(r)
        elif r.recurring and author in r.targets:
            next_time = calculate_next_occurrence(r.time, r.recurring)
            while next_time and next_time <= now:
                next_time = calculate_next_occurrence(next_time, r.recurring)
            if next_time:
                r.time = next_time
                active_reminders.append(r)
    
    user_reminders = sorted(active_reminders, key=lambda x: x.time)
    
    for i, reminder in enumerate(user_reminders, 1):
        try:
            local_time = reminder.time.astimezone(ZoneInfo(reminder.timezone))
            time_str = local_time.strftime("%b %d %H:%M")
            
            base_format = f"#{i}: {time_str}"
            tz_part = f" ({reminder.timezone})" if reminder.timezone != 'UTC' else ""
            rec_part = f" [{reminder.recurring}]" if reminder.recurring else ""
            
            message_preview = reminder.message
            for word in message_preview.split():
                if word.startswith('<@') and word.endswith('>'):
                    try:
                        user_id = int(word[2:-1].replace('!', ''))
                        user = interaction.guild.get_member(user_id) if interaction.guild else None
                        if not user:
                            try:
                                user = await interaction.client.fetch_user(user_id)
                            except discord.NotFound:
                                continue
                        
                        if user:
                            name = user.display_name if isinstance(user, discord.Member) else user.name
                            message_preview = message_preview.replace(word, f"@{name}")
                    except (ValueError, AttributeError):
                        continue
            
            used_space = len(base_format) + len(tz_part) + len(rec_part) + 5
            max_msg_len = 90 - used_space
            
            if len(message_preview) > max_msg_len:
                message_preview = message_preview[:max_msg_len-3] + "..."
            
            display_name = f"{base_format}{tz_part} - {message_preview}{rec_part}"
            
            if len(display_name) > 97:
                display_name = display_name[:97] + "..."
            
            choices.append(discord.app_commands.Choice(name=display_name, value=i))
        except Exception as e:
            logger.error(f"Error formatting reminder choice: {e}")
            continue
    
    return choices[:25]

reminder_group = app_commands.Group(name="reminder", description="Reminder commands")

@reminder_group.command(name="list", description="List all active reminders")
async def reminder_list(interaction: discord.Interaction):
    await list_reminders(interaction)

@reminder_group.command(name="help", description="Show help message")
async def reminder_help(interaction: discord.Interaction):
    await show_help(interaction)

@reminder_group.command(name="remove", description="Remove a reminder by number")
@app_commands.describe(number="Select a reminder to remove")
@app_commands.autocomplete(number=remove_number_autocomplete)
async def reminder_remove(interaction: discord.Interaction, number: int):
    await remove_reminder(interaction, str(number))

@reminder_group.command(name="set", description="Set a new reminder")
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

async def reminder_autocomplete(interaction: discord.Interaction, current: str) -> list[discord.app_commands.Choice[str]]:
    choices = []
    now = datetime.now(ZoneInfo('UTC'))
    author = interaction.user
    
    active_reminders = []
    for r in reminders:
        if r.time > now and author in r.targets:
            active_reminders.append(r)
        elif r.recurring and author in r.targets:
            next_time = calculate_next_occurrence(r.time, r.recurring)
            while next_time and next_time <= now:
                next_time = calculate_next_occurrence(next_time, r.recurring)
            if next_time:
                r.time = next_time
                active_reminders.append(r)
    
    user_reminders = sorted(active_reminders, key=lambda x: x.time)
    
    for i, reminder in enumerate(user_reminders, 1):
        try:
            local_time = reminder.time.astimezone(ZoneInfo(reminder.timezone))
            time_str = local_time.strftime("%b %d %H:%M")
            base_format = f"#{i}: {time_str}"
            tz_part = f" ({reminder.timezone})" if reminder.timezone != 'UTC' else ""
            rec_part = f" [{reminder.recurring}]" if reminder.recurring else ""
            
            message_preview = reminder.message
            for word in message_preview.split():
                if word.startswith('<@') and word.endswith('>'):
                    try:
                        user_id = int(word[2:-1].replace('!', ''))
                        user = interaction.guild.get_member(user_id) if interaction.guild else None
                        if not user:
                            try:
                                user = await interaction.client.fetch_user(user_id)
                            except discord.NotFound:
                                continue
                        if user:
                            name = user.display_name if isinstance(user, discord.Member) else user.name
                            message_preview = message_preview.replace(word, f"@{name}")
                    except (ValueError, AttributeError):
                        continue
            
            used_space = len(base_format) + len(tz_part) + len(rec_part) + 5
            max_msg_len = 90 - used_space
            
            if len(message_preview) > max_msg_len:
                message_preview = message_preview[:max_msg_len-3] + "..."
            
            display_name = f"{base_format}{tz_part} - {message_preview}{rec_part}"
            
            if len(display_name) > 97:
                display_name = display_name[:97] + "..."
            
            choices.append(discord.app_commands.Choice(name=display_name, value=str(i)))
        except Exception as e:
            logger.error(f"Error formatting reminder choice: {e}")
            continue
    
    return choices[:25]

@reminder_group.command(name="edit", description="Edit an existing reminder")
@app_commands.describe(
    number="The reminder number to edit",
    date="New date in YYYY-MM-DD format (optional)",
    time="New time in HH:MM format (optional)",
    message="New reminder message (optional)",
    timezone="New timezone (optional)",
    recurring="New recurring schedule (optional)"
)
@app_commands.autocomplete(
    number=reminder_autocomplete,
    timezone=timezone_autocomplete,
    recurring=recurring_autocomplete
)
async def reminder_edit(
    interaction: discord.Interaction,
    number: str,
    date: Optional[str] = None,
    time: Optional[str] = None,
    message: Optional[str] = None,
    timezone: Optional[str] = None,
    recurring: Optional[str] = None
):
    try:
        index = int(number) - 1
    except ValueError:
        await bot.handle_interaction_response(interaction, "❌ Please provide a valid reminder number.")
        return

    now = datetime.now(ZoneInfo('UTC'))
    user_reminders = []
    for r in reminders:
        if interaction.user in r.targets:
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
        await bot.handle_interaction_response(interaction, "You have no active reminders to edit.")
        return

    if index < 0 or index >= len(user_reminders):
        await bot.handle_interaction_response(interaction, f"❌ Invalid reminder number. Please use a number between 1 and {len(user_reminders)}.")
        return

    reminder = user_reminders[index]

    if reminder.author != interaction.user and not interaction.user.guild_permissions.manage_messages:
        await bot.handle_interaction_response(interaction, "❌ You can only edit reminders that you created.")
        return

    try:
        old_time = reminder.time
        old_timezone = reminder.timezone
        old_message = reminder.message
        old_recurring = reminder.recurring

        if timezone:
            new_timezone = get_timezone(timezone)
            if not new_timezone:
                await bot.handle_interaction_response(interaction, f"❌ Invalid timezone '{timezone}'.")
                return
            reminder.timezone = new_timezone.key

        if date or time:
            current_time = reminder.time.astimezone(ZoneInfo(reminder.timezone))
            new_date = date or current_time.strftime('%Y-%m-%d')
            new_time = time or current_time.strftime('%H:%M')
            
            try:
                naive_time = datetime.strptime(f"{new_date} {new_time}", '%Y-%m-%d %H:%M')
                if naive_time.year < 1970:
                    raise ValueError("Year must be 1970 or later")
                if naive_time.year > 9999:
                    raise ValueError("Year must be 9999 or earlier")
                
                local_time = naive_time.replace(tzinfo=ZoneInfo(reminder.timezone))
                reminder.time = local_time.astimezone(ZoneInfo('UTC'))
                
                server_now = datetime.now(ZoneInfo('UTC'))
                if reminder.time < server_now and not (recurring or reminder.recurring):
                    reminder.time = old_time
                    await bot.handle_interaction_response(interaction, "❌ Cannot set non-recurring reminders in the past!")
                    return

                max_future = server_now + timedelta(days=365*5)
                if reminder.time > max_future and not (recurring or reminder.recurring):
                    reminder.time = old_time
                    await bot.handle_interaction_response(interaction, "❌ Cannot set reminders more than 5 years in the future!")
                    return

            except ValueError as e:
                await bot.handle_interaction_response(interaction, f"❌ Invalid date/time format: {str(e)}. Use 'YYYY-MM-DD HH:MM'.")
                return

        if recurring is not None:
            if recurring.lower() not in ['daily', 'weekly', 'monthly', '']:
                await bot.handle_interaction_response(interaction, "❌ Invalid recurring option. Use 'daily', 'weekly', or 'monthly'.")
                return
            reminder.recurring = recurring.lower() if recurring else None

        if message:
            reminder.message = message

        if reminder.time < now and (reminder.recurring or recurring):
            next_time = calculate_next_occurrence(
                reminder.time,
                reminder.recurring,
                ZoneInfo(reminder.timezone)
            )
            while next_time and next_time <= now:
                next_time = calculate_next_occurrence(next_time, reminder.recurring, ZoneInfo(reminder.timezone))
            if next_time:
                reminder.time = next_time
            else:
                reminder.time = old_time
                reminder.timezone = old_timezone
                reminder.message = old_message
                reminder.recurring = old_recurring
                await bot.handle_interaction_response(interaction, "❌ Could not calculate next valid occurrence for recurring reminder!")
                return

        save_reminders()

        changes = []
        if date or time:
            changes.append("time")
        if timezone:
            changes.append("timezone")
        if message:
            changes.append("message")
        if recurring is not None:
            changes.append("recurrence")

        if not changes:
            await bot.handle_interaction_response(interaction, "No changes were made to the reminder.")
            return

        mentions_str = ' '.join(user.mention for user in reminder.targets)
        recurring_str = f" (Recurring: {reminder.recurring})" if reminder.recurring else ""
        timezone_str = f" ({reminder.timezone})" if reminder.timezone != 'UTC' else ""
        
        await bot.handle_interaction_response(
            interaction,
            f"✅ Updated reminder {', '.join(changes)} for {mentions_str}.\n" + 
            f"New reminder set for {format_discord_timestamp(reminder.time)}{timezone_str}: {reminder.message}{recurring_str}"
        )

    except Exception as e:
        logger.error(f"Error editing reminder: {e}")
        await bot.handle_interaction_response(interaction, "❌ An error occurred while editing the reminder. Please try again.")

@bot.command(name='edit')
async def text_edit(ctx, number: str = None, *, args: str = None):
    if not number or not args:
        await ctx.send("❌ Please provide both a reminder number and what to edit. Example: !edit 1 time:14:30 message:New message")
        return

    try:
        params = {}
        current_key = None
        current_value = []

        args_split = args.split()
        for part in args_split:
            if ':' in part and part.split(':')[0] in ['date', 'time', 'tz', 'timezone', 'message', 'recurring']:
                if current_key and current_value:
                    params[current_key] = ' '.join(current_value)
                key = part.split(':')[0]
                value = ':'.join(part.split(':')[1:])
                if key == 'tz':
                    key = 'timezone'
                current_key = key
                current_value = [value] if value else []
            elif current_key:
                current_value.append(part)
            else:
                await ctx.send("❌ Invalid format. Use key:value pairs (date:, time:, tz:, message:, recurring:)")
                return

        if current_key and current_value:
            params[current_key] = ' '.join(current_value)

        interaction = await discord.Interaction.from_context(ctx)
        await reminder_edit(
            interaction,
            number,
            params.get('date'),
            params.get('time'),
            params.get('message'),
            params.get('timezone'),
            params.get('recurring')
        )

    except Exception as e:
        logger.error(f"Error processing edit command: {e}")
        await ctx.send("❌ An error occurred while editing the reminder. Please try again.")

class ReminderBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)
        self.interaction_responses = {}
    
    async def setup_hook(self):
        self.tree.add_command(reminder_group)
        await self.tree.sync()
    
    async def on_ready(self):
        logger.info(f'Logged in as {self.user}')
        await load_reminders()
        check_reminders.start()
        cleanup_old_reminders.start()

    async def handle_interaction_response(self, interaction, content, embed=None):
        try:
            if not interaction.response.is_done():
                if embed:
                    await interaction.response.send_message(embed=embed)
                else:
                    await interaction.response.send_message(content)
            else:
                if embed:
                    await interaction.followup.send(embed=embed)
                else:
                    await interaction.followup.send(content)
        except Exception as e:
            logger.error(f"Failed to send interaction response: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("An error occurred while processing your request.")
            except:
                pass

bot = ReminderBot()

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
            timezone_override = get_timezone(timezone)
            if not timezone_override:
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

            max_future = server_now + timedelta(days=365*5)  # 5 years
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
            
            reminders.append(reminder)
            save_reminders()
            
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

@bot.command(name='reminder')
async def text_reminder(ctx, action: str = None, *, args: str = None):
    if action in ['list', 'help', 'remove']:
        if action == 'list':
            await list_reminders(ctx)
            return
        elif action == 'help':
            await show_help(ctx)
            return
        elif action == 'remove':
            await remove_reminder(ctx, args)
            return

    full_args = f"{action} {args}" if args else action
    if not full_args:
        await show_help(ctx)
        return

    try:
        parts = full_args.split(' ', 2)
        if len(parts) < 2:
            raise ValueError("Missing required arguments")

        date = parts[0]
        time = parts[1]
        message = parts[2] if len(parts) > 2 else ''
        
        words = message.split()
        timezone = None
        recurring = None
        
        if words and words[0].startswith('tz:'):
            timezone = words[0][3:]
            words = words[1:]
            message = ' '.join(words)
        
        if words and words[0].lower() in ['daily', 'weekly', 'monthly']:
            recurring = words[0].lower()
            words = words[1:]
            message = ' '.join(words)
        
        await handle_reminder(ctx, date, time, message, timezone, recurring)

    except ValueError as e:
        if str(e) == "Missing required arguments":
            await show_help(ctx)
        else:
            await ctx.send("❌ Invalid format. Use !reminder YYYY-MM-DD HH:MM [tz:Region/City] [daily|weekly|monthly] [@user1 @user2...] message")

async def remove_reminder(ctx, args):
    is_interaction = isinstance(ctx, discord.Interaction)
    author = ctx.user if is_interaction else ctx.author
    
    try:
        index = int(args) - 1
    except (ValueError, TypeError):
        example = "/reminder remove number:1" if is_interaction else "!reminder remove 1"
        if is_interaction:
            await bot.handle_interaction_response(ctx, f"❌ Please provide a valid reminder number. Example: {example}")
        else:
            await ctx.send(f"❌ Please provide a valid reminder number. Example: {example}")
        return

    now = datetime.now(ZoneInfo('UTC'))
    user_reminders = []
    for r in reminders:
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
        if is_interaction:
            await bot.handle_interaction_response(ctx, "You have no active reminders.")
        else:
            await ctx.send("You have no active reminders.")
        return
    
    if index < 0 or index >= len(user_reminders):
        if is_interaction:
            await bot.handle_interaction_response(ctx, f"❌ Invalid reminder number. Please use a number between 1 and {len(user_reminders)}.")
        else:
            await ctx.send(f"❌ Invalid reminder number. Please use a number between 1 and {len(user_reminders)}.")
        return
    
    reminder_to_remove = user_reminders[index]
    
    if reminder_to_remove.author != author and not (hasattr(author, 'guild_permissions') and author.guild_permissions.manage_messages):
        if is_interaction:
            await bot.handle_interaction_response(ctx, "❌ You can only remove reminders that you created.")
        else:
            await ctx.send("❌ You can only remove reminders that you created.")
        return
    
    reminders.remove(reminder_to_remove)
    save_reminders()
    recurring_str = f" (Recurring: {reminder_to_remove.recurring})" if reminder_to_remove.recurring else ""
    timezone_str = f" ({reminder_to_remove.timezone})" if reminder_to_remove.timezone != 'UTC' else ""
    if is_interaction:
        await bot.handle_interaction_response(ctx, f"✅ Removed reminder: {format_discord_timestamp(reminder_to_remove.time)} - {reminder_to_remove.message}{recurring_str}{timezone_str}")
    else:
        await ctx.send(f"✅ Removed reminder: {format_discord_timestamp(reminder_to_remove.time)} - {reminder_to_remove.message}{recurring_str}{timezone_str}")

async def list_reminders(ctx):
    is_interaction = isinstance(ctx, discord.Interaction)
    active_reminders = []
    now = datetime.now(ZoneInfo('UTC'))
    
    for r in reminders:
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
        if is_interaction:
            await bot.handle_interaction_response(ctx, "No active reminders.")
        else:
            await ctx.send("No active reminders.")
        return

    user_reminders = {}
    for reminder in active_reminders:
        for target in reminder.targets:
            if target not in user_reminders:
                user_reminders[target] = []
            user_reminders[target].append(reminder)

    embed = discord.Embed(
        title="📋 Active Reminders",
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
                        mentioned_user = ctx.guild.get_member(user_id) if hasattr(ctx, 'guild') and ctx.guild else None
                        if not mentioned_user:
                            try:
                                mentioned_user = await ctx.bot.fetch_user(user_id)
                            except discord.NotFound:
                                continue
                        
                        if mentioned_user:
                            name = mentioned_user.display_name if isinstance(mentioned_user, discord.Member) else mentioned_user.name
                            message_preview = message_preview.replace(word, f"@{name}")
                    except (ValueError, AttributeError):
                        continue

            recurring_str = f" (Recurring: {reminder.recurring})" if reminder.recurring else ""
            timezone_str = f" ({reminder.timezone})" if reminder.timezone != 'UTC' else ""
            other_users = [u.display_name if isinstance(u, discord.Member) else u.name for u in reminder.targets if u != user]
            with_others = f" (with {', '.join(other_users)})" if other_users else ""
            created_by = "" if reminder.author == user else f" (created by {reminder.author.display_name if isinstance(reminder.author, discord.Member) else reminder.author.name})"
            reminder_texts.append(
                f"**{i}.** {format_discord_timestamp(reminder.time)}: {message_preview}{recurring_str}{timezone_str}{with_others}{created_by}"
            )
        
        if reminder_texts:
            user_name = user.display_name if isinstance(user, discord.Member) else user.name
            embed.add_field(
                name=f"Reminders for {user_name}",
                value="\n".join(reminder_texts),
                inline=False
            )

    if is_interaction:
        await bot.handle_interaction_response(ctx, None, embed=embed)
    else:
        await ctx.send(embed=embed)

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

List reminders:
```
/reminder list
```

Remove reminder:
```
/reminder remove number:1
```

Edit a reminder:
```
/reminder edit number:1 time:14:30 message:Updated meeting time
!edit 1 time:14:30 message:Updated meeting time
```

Create a reminder with timezone and recurring:
```
/reminder set date:2024-02-10 time:10:00 timezone:Europe/Paris recurring:daily message:Daily standup meeting
```

Create a reminder with mentions:
```
/reminder set date:2024-02-10 time:14:00 message:Hey @Alice, @Bob team meeting tomorrow
```

Create a text command reminder:
```
!reminder 2024-02-10 14:00 tz:Europe/Paris daily @Alice @Bob Team meeting
```

**Options:**
• **Timezone:** Use `timezone:` (slash) or `tz:` (text) with region name
  Examples: Europe/Paris, America/New_York, Asia/Tokyo

• **Recurring:** Use `recurring:` (slash) or add type word (text)
  Values: daily, weekly, monthly

• **User Mentions:** Include mentions directly in your message
  Text command: @Username
  Slash command: @Username or type in message

• **Time Format:** Always use 24-hour format (HH:MM)
  Example: 09:00 (for 9 AM), 14:30 (for 2:30 PM)

• **Edit Command:** Both date and time are optional when editing. Only specify what you want to change."""

    if is_interaction:
        await bot.handle_interaction_response(ctx, help_text)
    else:
        await ctx.send(help_text)

async def send_channel_message(channel, content):
    try:
        await channel.send(content)
    except discord.Forbidden:
        logger.error(f"Missing permissions to send message in channel {channel.id}")
        return False
    except discord.NotFound:
        logger.error(f"Channel {channel.id} not found")
        return False
    except discord.HTTPException as e:
        logger.error(f"Failed to send message: {e}")
        return False
    return True

def calculate_next_occurrence(current_time, recurrence_type, target_timezone=None):
    if not target_timezone:
        target_timezone = current_time.tzinfo

    if recurrence_type == 'daily':
        next_time = current_time + timedelta(days=1)
    elif recurrence_type == 'weekly':
        next_time = current_time + timedelta(weeks=1)
    elif recurrence_type == 'monthly':
        year = current_time.year + ((current_time.month + 1) - 1) // 12
        month = ((current_time.month + 1) - 1) % 12 + 1
        try:
            next_time = current_time.replace(year=year, month=month)
        except ValueError:
            if month == 12:
                year += 1
                month = 1
            else:
                month += 1
            next_time = current_time.replace(year=year, month=month, day=1) - timedelta(days=1)
    else:
        return None

    if target_timezone and target_timezone != current_time.tzinfo:
        local_time = next_time.astimezone(target_timezone)
        next_time = local_time.replace(tzinfo=current_time.tzinfo).astimezone(current_time.tzinfo)
    
    return next_time

@tasks.loop(seconds=60)
async def check_reminders():
    now = datetime.now(ZoneInfo('UTC'))
    seconds_until_next_minute = 60 - now.second
    if (seconds_until_next_minute > 0):
        await asyncio.sleep(seconds_until_next_minute)
    
    now = datetime.now(ZoneInfo('UTC'))
    logger.debug(f"Checking reminders at {now}")
    
    to_remove = []
    to_add = []

    for reminder in reminders:
        local_time = reminder.time.astimezone(ZoneInfo(reminder.timezone))
        if now >= reminder.time - timedelta(minutes=15) and now < reminder.time - timedelta(minutes=14):
            for user in reminder.targets:
                timezone_str = f" ({reminder.timezone})" if reminder.timezone != 'UTC' else ""
                if not await send_channel_message(
                    reminder.channel,
                    f"⚠️ Heads up! {user.mention}, you have a reminder at {format_discord_timestamp(reminder.time, 't')}{timezone_str}: {reminder.message}"
                ):
                    logger.error(f"Failed to send advance notification to {user.id} in channel {reminder.channel.id}")
            
        if now >= reminder.time:
            targets_mentions = ' '.join(user.mention for user in reminder.targets)
            timezone_str = f" ({reminder.timezone})" if reminder.timezone != 'UTC' else ""
            if not await send_channel_message(
                reminder.channel,
                f"🔔 Reminder for {targets_mentions}{timezone_str}: {reminder.message}"
            ):
                logger.error(f"Failed to send reminder to {targets_mentions} in channel {reminder.channel.id}")
                if not reminder.recurring:
                    continue
            
            if reminder.recurring:
                try:
                    next_time = calculate_next_occurrence(
                        reminder.time, 
                        reminder.recurring,
                        ZoneInfo(reminder.timezone)
                    )
                    while next_time and next_time <= now:
                        next_time = calculate_next_occurrence(
                            next_time, 
                            reminder.recurring,
                            ZoneInfo(reminder.timezone)
                        )
                    if next_time:
                        new_reminder = Reminder(
                            next_time,
                            reminder.author,
                            reminder.targets,
                            reminder.message,
                            reminder.channel,
                            reminder.recurring,
                            reminder.timezone
                        )
                        to_add.append(new_reminder)
                        logger.info(f"Scheduled next occurrence of recurring reminder for {format_discord_timestamp(next_time)} ({reminder.timezone})")
                    else:
                        logger.error(f"Invalid next time calculated for recurring reminder: {next_time}")
                except Exception as e:
                    logger.error(f"Failed to calculate next recurring time: {e}")
            
            to_remove.append(reminder)

    for reminder in to_remove:
        try:
            reminders.remove(reminder)
        except ValueError:
            logger.error(f"Failed to remove reminder: {reminder.time} - {reminder.message}")
    
    reminders.extend(to_add)
    
    try:
        save_reminders()
    except Exception as e:
        logger.error(f"Failed to save reminders: {e}")

@tasks.loop(hours=24)
async def cleanup_old_reminders():
    now = datetime.now(ZoneInfo('UTC'))
    cutoff = now - timedelta(days=CLEANUP_DAYS)
    to_remove = []

    for reminder in reminders:
        if not reminder.recurring and reminder.time < cutoff:
            to_remove.append(reminder)
            logger.info(f"Cleaning up old reminder from {format_discord_timestamp(reminder.time)}")
    
    for reminder in to_remove:
        try:
            reminders.remove(reminder)
        except ValueError:
            logger.error(f"Failed to remove old reminder: {reminder.time} - {reminder.message}")
    
    if to_remove:
        try:
            save_reminders()
        except Exception as e:
            logger.error(f"Failed to save reminders after cleanup: {e}")

TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    raise ValueError("No token provided. Set the DISCORD_TOKEN environment variable.")

bot.run(TOKEN)
