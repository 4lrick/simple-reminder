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
    
    async def on_ready(self):
        logger.info(f'Logged in as {self.user}')
        await self.reminder_manager.load_reminders(self)
        check_reminders.start()
        cleanup_old_reminders.start()

bot = ReminderBot()

@tasks.loop(seconds=60)
async def check_reminders():
    while True:
        now = datetime.now(ZoneInfo('UTC'))
        next_reminder_time = None
        
        for reminder in bot.reminder_manager.reminders:
            warning_time = reminder.time - timedelta(minutes=15)
            if warning_time > now and (next_reminder_time is None or warning_time < next_reminder_time):
                next_reminder_time = warning_time
            if reminder.time > now and (next_reminder_time is None or reminder.time < next_reminder_time):
                next_reminder_time = reminder.time
        
        if next_reminder_time is None:
            await asyncio.sleep(60)
            continue
        
        sleep_duration = (next_reminder_time - now).total_seconds()
        if sleep_duration > 0:
            await asyncio.sleep(sleep_duration)
        
        now = datetime.now(ZoneInfo('UTC'))
        to_remove = []
        to_add = []

        for reminder in bot.reminder_manager.reminders:
            if now >= reminder.time - timedelta(minutes=15) and now < reminder.time - timedelta(minutes=14):
                for user in reminder.targets:
                    timezone_str = f" ({reminder.timezone})" if reminder.timezone != 'UTC' else ""
                    try:
                        await reminder.channel.send(
                            f"⚠️ Heads up! {user.mention}, you have a reminder at {format_discord_timestamp(reminder.time, 't')}{timezone_str}: {reminder.message}"
                        )
                    except (discord.NotFound, discord.Forbidden):
                        logger.warning(f"Could not send advance notification to channel {reminder.channel.id}")
                    except Exception as e:
                        logger.error(f"Failed to send advance notification: {e}")
            
            if now >= reminder.time:
                targets_mentions = ' '.join(user.mention for user in reminder.targets)
                timezone_str = f" ({reminder.timezone})" if reminder.timezone != 'UTC' else ""
                try:
                    await reminder.channel.send(
                        f"🔔 Reminder for {targets_mentions}{timezone_str}: {reminder.message}"
                    )
                except (discord.NotFound, discord.Forbidden):
                    logger.warning(f"Could not send reminder to channel {reminder.channel.id}")
                    if not reminder.recurring:
                        to_remove.append(reminder)
                        continue
                except Exception as e:
                    logger.error(f"Failed to send reminder: {e}")
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

        for reminder in to_remove:
            try:
                bot.reminder_manager.reminders.remove(reminder)
            except ValueError:
                logger.error(f"Failed to remove reminder: {reminder.time} - {reminder.message}")
        
        bot.reminder_manager.reminders.extend(to_add)
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

bot.run(DISCORD_TOKEN)
