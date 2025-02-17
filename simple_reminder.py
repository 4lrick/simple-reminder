import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
import asyncio
import logging
from zoneinfo import ZoneInfo
from typing import Optional
from collections import defaultdict

from src.config import DISCORD_TOKEN, CLEANUP_DAYS
from src.reminder import ReminderManager, format_discord_timestamp, calculate_next_occurrence
from src.commands.set_reminder import reminder_set
from src.commands.list_reminders import list_command
from src.commands.remove_reminder import remove_command
from src.commands.edit_reminder import edit_command
from src.commands.help import show_help
from src.logger import setup_logger

logger = setup_logger()

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.presences = False

class ReminderBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)
        self.reminder_manager = ReminderManager()
        self._last_clear_time = None
        self._command_count = 0
        self._command_threshold = 1000
        self._guild_member_cache = {}
    
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
    
    async def on_message(self, message):
        if message.author.bot:
            return

        if self.user in message.mentions:
            await message.channel.send("👋 Hi! I'm a reminder bot that uses slash commands. Type `/reminder help` to see what I can do!")
            return
            
        await super().on_message(message)

    async def on_command_error(self, context, exception):
        if isinstance(exception, commands.CommandNotFound):
            await context.send("❌ This bot only uses slash (/) commands. Type `/reminder help` to see available commands!")
            return
        logger.error(f"Command error: {exception}")

    async def on_ready(self):
        logger.info(f'Logged in as {self.user}')
        await self.reminder_manager.load_reminders(self)
        
        total_reminders = len(self.reminder_manager.reminders)
        recurring_count = sum(1 for r in self.reminder_manager.reminders if r.recurring)
        timezone_stats = defaultdict(int)
        guild_stats = defaultdict(int)
        
        for reminder in self.reminder_manager.reminders:
            timezone_stats[reminder.timezone] += 1
            guild_stats[reminder.guild_id] += 1
        
        logger.info(f"Bot ready! Loaded {total_reminders} reminders:")
        logger.info(f"  • {recurring_count} recurring reminders")
        logger.info(f"  • {len(guild_stats)} guilds with active reminders")
        logger.info(f"  • Most used timezones: {dict(sorted(timezone_stats.items(), key=lambda x: x[1], reverse=True)[:3])}")
        
        check_reminders.start()
        cleanup_old_reminders.start()
        clear_user_cache.start(self)
        self._last_clear_time = datetime.now(ZoneInfo('UTC'))
        self._command_count = 0

    async def get_or_fetch_member(self, guild_id: int, user_id: int) -> Optional[discord.Member]:
        """Get a member from cache or fetch them with rate limit handling"""
        cache_key = f"{guild_id}_{user_id}"
        
        if cache_key in self._guild_member_cache:
            return self._guild_member_cache[cache_key]
        
        guild = self.get_guild(guild_id)
        if not guild:
            return None
        
        try:
            member = guild.get_member(user_id)
            if member:
                self._guild_member_cache[cache_key] = member
                return member
            
            try:
                member = await guild.fetch_member(user_id)
                if member:
                    self._guild_member_cache[cache_key] = member
                    return member
            except discord.HTTPException as e:
                if e.status == 429:
                    logger.warning(f"Rate limited while fetching member {user_id} from guild {guild_id}")
                    await asyncio.sleep(e.retry_after)
                    try:
                        member = await guild.fetch_member(user_id)
                        if member:
                            self._guild_member_cache[cache_key] = member
                            return member
                    except:
                        pass
                elif e.status == 404:
                    logger.debug(f"Member {user_id} not found in guild {guild_id}")
                    return None
                else:
                    logger.error(f"Error fetching member {user_id} from guild {guild_id}: {e}")
                    return None
                    
        except Exception as e:
            logger.error(f"Unexpected error fetching member {user_id} from guild {guild_id}: {e}")
            return None
        
        return None
    
    def clear_member_cache(self):
        """Clear the guild member cache"""
        self._guild_member_cache.clear()
        logger.debug("Cleared guild member cache")

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
            logger.info(
                f"Sending 15-minute warning for reminder: {reminder.message} | "
                f"Time: {format_discord_timestamp(reminder.time)} | "
                f"Channel: {reminder.channel.name} ({reminder.channel.id}) | "
                f"Targets: {', '.join(f'{t.name}' for t in reminder.targets)}"
            )
            channel_key = reminder.channel.id
            if channel_key not in channel_reminders:
                channel_reminders[channel_key] = []
            channel_reminders[channel_key].append(('warning', reminder))
        elif now >= reminder.time:
            logger.info(
                f"Triggering reminder: {reminder.message} | "
                f"Time: {format_discord_timestamp(reminder.time)} | "
                f"Channel: {reminder.channel.name} ({reminder.channel.id}) | "
                f"Targets: {', '.join(f'{t.name}' for t in reminder.targets)}"
            )
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
                        logger.info(
                            f"Created next occurrence of recurring reminder: {reminder.message} | "
                            f"Next time: {format_discord_timestamp(next_time)} | "
                            f"Recurring: {reminder.recurring}"
                        )
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
                        logger.info(
                            f"Sending 15-minute warning for reminder: {reminder.message} | "
                            f"Time: {format_discord_timestamp(reminder.time)} | "
                            f"Channel: {reminder.channel.name} ({reminder.channel.id}) | "
                            f"Targets: {', '.join(f'{t.name}' for t in reminder.targets)}"
                        )
                        for user in reminder.targets:
                            timezone_str = f" ({reminder.timezone})" if reminder.timezone != 'UTC' else ""
                            await channel.send(
                                f"⚠️ Heads up! {user.mention}, you have a reminder at {format_discord_timestamp(reminder.time, 't')}{timezone_str}: {reminder.message}"
                            )
                            await asyncio.sleep(0.5)
                    else:
                        logger.info(
                            f"Triggering reminder: {reminder.message} | "
                            f"Time: {format_discord_timestamp(reminder.time)} | "
                            f"Channel: {reminder.channel.name} ({reminder.channel.id}) | "
                            f"Targets: {', '.join(f'{t.name}' for t in reminder.targets)}"
                        )
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

    logger.info(f"Starting cleanup of old reminders (older than {CLEANUP_DAYS} days)")

    for reminder in bot.reminder_manager.reminders:
        if not reminder.recurring and reminder.time < cutoff:
            to_remove.append(reminder)
            logger.info(
                f"Cleaning up old reminder: {reminder.message} | "
                f"From: {format_discord_timestamp(reminder.time)} | "
                f"Channel: {reminder.channel.name} ({reminder.channel.id}) | "
                f"Author: {reminder.author.name}"
            )
    
    for reminder in to_remove:
        try:
            bot.reminder_manager.reminders.remove(reminder)
        except ValueError:
            logger.error(f"Failed to remove old reminder: {reminder.time} - {reminder.message}")
    
    if to_remove:
        bot.reminder_manager.save_reminders()
        logger.info(f"Cleanup completed. Removed {len(to_remove)} old reminders")
    else:
        logger.info("Cleanup completed. No old reminders to remove")

@tasks.loop(minutes=5)
async def clear_user_cache(bot):
    """Clear the user cache periodically or when command threshold is reached"""
    now = datetime.now(ZoneInfo('UTC'))
    hours_since_clear = 0
    if bot._last_clear_time:
        hours_since_clear = (now - bot._last_clear_time).total_seconds() / 3600

    if hours_since_clear >= 24 or bot._command_count >= bot._command_threshold:
        bot.reminder_manager.clear_cache()
        bot.clear_member_cache()
        bot._last_clear_time = now
        bot._command_count = 0
        logger.info("Cleared user cache")

bot.run(DISCORD_TOKEN)
