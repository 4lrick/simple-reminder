from datetime import datetime, timedelta
import json
import logging
from zoneinfo import ZoneInfo
from typing import List, Optional
import discord
from discord.ext import commands
import src.config

logger = logging.getLogger(__name__)

def format_discord_timestamp(dt: datetime, style: str = 'f') -> str:
    """Format a datetime object into a Discord timestamp string."""
    if not isinstance(dt, datetime):
        raise TypeError("dt must be a datetime object")
    if style not in ['t', 'T', 'd', 'D', 'f', 'F', 'R']:
        raise ValueError("Invalid timestamp style")
    return f"<t:{int(dt.timestamp())}:{style}>"

def calculate_next_occurrence(current_time: datetime, recurrence_type: str, target_timezone: Optional[ZoneInfo] = None) -> Optional[datetime]:
    if not target_timezone:
        target_timezone = current_time.tzinfo

    local_time = current_time.astimezone(target_timezone)
    
    def get_next_time(dt: datetime, delta: timedelta) -> datetime:
        """Get next occurrence time accounting for DST transitions"""
        next_date = dt.date() + delta
        next_time = dt.timetz()
        
        candidate_times = [
            datetime.combine(next_date, next_time.replace(tzinfo=None)).replace(tzinfo=dt.tzinfo),
            datetime.combine(next_date, next_time.replace(tzinfo=None)).replace(tzinfo=dt.tzinfo) - timedelta(hours=1),
            datetime.combine(next_date, next_time.replace(tzinfo=None)).replace(tzinfo=dt.tzinfo) + timedelta(hours=1)
        ]
        
        for candidate in candidate_times:
            if candidate.hour == dt.hour:
                return candidate
        
        return candidate_times[0]

    if recurrence_type == 'daily':
        next_local = get_next_time(local_time, timedelta(days=1))
    elif recurrence_type == 'weekly':
        next_local = get_next_time(local_time, timedelta(weeks=1))
    elif recurrence_type == 'monthly':
        year = local_time.year + ((local_time.month + 1) - 1) // 12
        month = ((local_time.month + 1) - 1) % 12 + 1
        try:
            next_day = local_time.date().replace(year=year, month=month)
            days_diff = next_day - local_time.date()
            next_local = get_next_time(local_time, days_diff)
        except ValueError:
            if month == 12:
                year += 1
                month = 1
            else:
                month += 1
            last_day = (datetime(year, month, 1) - timedelta(days=1)).date()
            days_diff = last_day - local_time.date()
            next_local = get_next_time(local_time, days_diff)
    else:
        return None

    next_time = next_local if next_local.tzinfo == current_time.tzinfo else next_local.astimezone(current_time.tzinfo)
    return next_time

class Reminder:
    def __init__(self, time, author, targets, message, channel, recurring=None, timezone=None):
        self.time = time
        self.author = author
        self.targets = targets
        self.message = message
        self.channel = channel
        self.recurring = recurring
        self.timezone = timezone or 'UTC'
        self.guild_id = channel.guild.id if channel.guild else None
    
    def to_dict(self):
        return {
            'time': self.time.isoformat(),
            'author_id': self.author.id,
            'target_ids': [user.id for user in self.targets],
            'message': self.message,
            'channel_id': self.channel.id,
            'guild_id': self.guild_id,
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
        reminder.guild_id = data.get('guild_id')
        
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

class ReminderManager:
    def __init__(self):
        self.reminders: List[Reminder] = []
        self._retries = {}
    
    def save_reminders(self):
        data = [reminder.to_dict() for reminder in self.reminders]
        try:
            save_file = src.config.SAVE_FILE
            with open(save_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving reminders: {e}")
    
    async def load_reminders(self, bot):
        import os
        save_file = src.config.SAVE_FILE
        if not os.path.exists(save_file):
            return
        
        try:
            with open(save_file, 'r') as f:
                data = json.load(f)
            
            valid_reminders = []
            for reminder_data in data:
                try:
                    reminder = await self._load_reminder(reminder_data, bot)
                    if reminder:
                        valid_reminders.append(reminder)
                except Exception as e:
                    logger.error(f"Error loading reminder: {e}")
            
            self.reminders = valid_reminders
            logger.info(f"Loaded {len(self.reminders)} reminders from {save_file}")
            
            self.save_reminders()
        except Exception as e:
            logger.error(f"Error loading reminders: {e}")
    
    async def _load_reminder(self, data: dict, bot, max_retries: int = 3) -> Optional[Reminder]:
        """Load a single reminder with retry logic for network operations."""
        retry_key = f"{data['channel_id']}_{data['author_id']}"
        if self._retries.get(retry_key, 0) >= max_retries:
            logger.error(f"Max retries exceeded for reminder in channel {data['channel_id']}")
            return None
        
        try:
            time = datetime.fromisoformat(data['time'])
            author = await bot.fetch_user(data['author_id'])
            if not author:
                return None
            
            targets = []
            for user_id in data['target_ids']:
                try:
                    user = await bot.fetch_user(user_id)
                    if user:
                        targets.append(user)
                except discord.NotFound:
                    logger.warning(f"Target user {user_id} not found")
                except discord.HTTPException as e:
                    self._retries[retry_key] = self._retries.get(retry_key, 0) + 1
                    raise e
            
            if not targets:
                return None
            
            channel = bot.get_channel(data['channel_id'])
            if not channel:
                try:
                    channel = await bot.fetch_channel(data['channel_id'])
                except (discord.NotFound, discord.Forbidden):
                    logger.warning(f"Channel {data['channel_id']} not found or not accessible")
                    return None
                except discord.HTTPException as e:
                    self._retries[retry_key] = self._retries.get(retry_key, 0) + 1
                    raise e
            
            timezone = data.get('timezone', 'UTC')
            reminder = Reminder(time, author, targets, data['message'], channel, data['recurring'], timezone)
            reminder.guild_id = data.get('guild_id')
            
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
            
        except discord.HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error loading reminder: {e}")
            return None

class Reminder:
    def __init__(self, time, author, targets, message, channel, recurring=None, timezone=None):
        self.time = time
        self.author = author
        self.targets = targets
        self.message = message
        self.channel = channel
        self.recurring = recurring
        self.timezone = timezone or 'UTC'
        self.guild_id = channel.guild.id if channel.guild else None
    
    def to_dict(self):
        return {
            'time': self.time.isoformat(),
            'author_id': self.author.id,
            'target_ids': [user.id for user in self.targets],
            'message': self.message,
            'channel_id': self.channel.id,
            'guild_id': self.guild_id,
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
        reminder.guild_id = data.get('guild_id')
        
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