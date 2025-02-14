import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
import asyncio
import logging
from zoneinfo import ZoneInfo

from src.config import DISCORD_TOKEN, CLEANUP_DAYS
from src.reminder import ReminderManager, format_discord_timestamp, calculate_next_occurrence
from src.commands.set_reminder import reminder_set
from src.commands.list_reminders import list_command
from src.commands.remove_reminder import remove_command
from src.commands.edit_reminder import edit_command
from src.commands.help import show_help

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.members = True
intents.presences = False

class ReminderBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=None, intents=intents)
        self.reminder_manager = ReminderManager()
    
    async def setup_hook(self):
        reminder_group = app_commands.Group(name="reminder", description="Reminder commands")
        
        reminder_group.add_command(reminder_set)
        reminder_group.add_command(list_command)
        reminder_group.add_command(remove_command)
        reminder_group.add_command(edit_command)
        reminder_group.add_command(app_commands.Command(
            name="help",
            description="Show help about using the bot",
            callback=show_help
        ))
        
        self.tree.add_command(reminder_group)
        await self.tree.sync()
        
        clear_user_cache.start(self)
    
    async def on_ready(self):
        logger.info(f'Logged in as {self.user}')
        await self.reminder_manager.load_reminders(self)
        check_reminders.start()
        cleanup_old_reminders.start()

bot = ReminderBot()

@tasks.loop(seconds=60)
async def check_reminders():
    now = datetime.now(ZoneInfo('UTC'))
    seconds_until_next_minute = 60 - now.second
    if seconds_until_next_minute > 0:
        await asyncio.sleep(seconds_until_next_minute)
    
    now = datetime.now(ZoneInfo('UTC'))
    logger.debug(f"Checking reminders at {now}")
    
    to_remove = []
    to_add = []

    channel_reminders = {}
    for reminder in bot.reminder_manager.reminders:
        if reminder.time - timedelta(minutes=15) <= now < reminder.time - timedelta(minutes=14):
            channel_key = reminder.channel.id
            if channel_key not in channel_reminders:
                channel_reminders[channel_key] = []
            channel_reminders[channel_key].append(('warning', reminder))
        elif now >= reminder.time:
            channel_key = reminder.channel.id
            if channel_key not in channel_reminders:
                channel_reminders[channel_key] = []
            channel_reminders[channel_key].append(('trigger', reminder))
            
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
                        new_reminder = reminder.__class__(
                            next_time,
                            reminder.author,
                            reminder.targets,
                            reminder.message,
                            reminder.channel,
                            reminder.recurring,
                            reminder.timezone
                        )
                        to_add.append(new_reminder)
                    else:
                        logger.error(f"Invalid next time calculated for recurring reminder")
                except Exception as e:
                    logger.error(f"Failed to calculate next recurring time: {e}")
            
            to_remove.append(reminder)

    for channel_id, reminder_list in channel_reminders.items():
        try:
            channel = bot.get_channel(channel_id)
            if not channel:
                logger.warning(f"Channel {channel_id} not found, skipping {len(reminder_list)} reminders")
                continue
                
            for reminder_type, reminder in reminder_list:
                try:
                    if reminder_type == 'warning':
                        for user in reminder.targets:
                            timezone_str = f" ({reminder.timezone})" if reminder.timezone != 'UTC' else ""
                            await channel.send(
                                f"⚠️ Heads up! {user.mention}, you have a reminder at {format_discord_timestamp(reminder.time, 't')}{timezone_str}: {reminder.message}"
                            )
                            await asyncio.sleep(0.5)
                    else:
                        targets_mentions = ' '.join(user.mention for user in reminder.targets)
                        timezone_str = f" ({reminder.timezone})" if reminder.timezone != 'UTC' else ""
                        await channel.send(
                            f"🔔 Reminder for {targets_mentions}{timezone_str}: {reminder.message}"
                        )
                        await asyncio.sleep(0.5)
                except discord.HTTPException as e:
                    if e.status == 429:
                        retry_after = e.retry_after
                        logger.info(f"Rate limited when sending message, waiting {retry_after} seconds")
                        await asyncio.sleep(retry_after)
                        try:
                            if reminder_type == 'warning':
                                for user in reminder.targets:
                                    timezone_str = f" ({reminder.timezone})" if reminder.timezone != 'UTC' else ""
                                    await channel.send(
                                        f"⚠️ Heads up! {user.mention}, you have a reminder at {format_discord_timestamp(reminder.time, 't')}{timezone_str}: {reminder.message}"
                                    )
                            else:
                                targets_mentions = ' '.join(user.mention for user in reminder.targets)
                                timezone_str = f" ({reminder.timezone})" if reminder.timezone != 'UTC' else ""
                                await channel.send(
                                    f"🔔 Reminder for {targets_mentions}{timezone_str}: {reminder.message}"
                                )
                        except Exception as e2:
                            logger.error(f"Failed to send message after rate limit retry: {e2}")
                    else:
                        logger.error(f"Failed to send message: {e}")
        except Exception as e:
            logger.error(f"Error processing channel {channel_id}: {e}")

    for reminder in to_remove:
        try:
            bot.reminder_manager.reminders.remove(reminder)
        except ValueError:
            logger.error(f"Failed to remove reminder: {reminder.time} - {reminder.message}")
    
    bot.reminder_manager.reminders.extend(to_add)
    if to_remove or to_add:
        bot.reminder_manager.save_reminders()

@tasks.loop(hours=24)
async def cleanup_old_reminders():
    now = datetime.now(ZoneInfo('UTC'))
    cutoff = now - timedelta(days=CLEANUP_DAYS)
    to_remove = []

    for reminder in bot.reminder_manager.reminders:
        if not reminder.recurring and reminder.time < cutoff:
            to_remove.append(reminder)
            logger.info(f"Cleaning up old reminder from {format_discord_timestamp(reminder.time)}")
    
    for reminder in to_remove:
        try:
            bot.reminder_manager.reminders.remove(reminder)
        except ValueError:
            logger.error(f"Failed to remove old reminder: {reminder.time} - {reminder.message}")
    
    if to_remove:
        bot.reminder_manager.save_reminders()

@tasks.loop(hours=24)
async def clear_user_cache(bot):
    """Clear the user cache daily to prevent memory bloat"""
    bot.reminder_manager.clear_cache()
    logger.debug("Cleared user cache")

bot.run(DISCORD_TOKEN)
