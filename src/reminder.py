from datetime import datetime, timedelta
import json
import logging
import asyncio
import time
from zoneinfo import ZoneInfo
from typing import List, Optional
import discord
from discord.ext import commands
import src.config

logger = logging.getLogger(__name__)

REMINDER_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "required": ["time", "author_id", "target_ids", "message", "channel_id"],
        "properties": {
            "time": {"type": "string", "format": "date-time"},
            "author_id": {"type": "integer"},
            "target_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "minItems": 1
            },
            "message": {"type": "string", "maxLength": 1000},
            "channel_id": {"type": "integer"},
            "guild_id": {"type": ["integer", "null"]},
            "recurring": {"type": ["string", "null"], "enum": ["daily", "weekly", "monthly", None]},
            "timezone": {"type": "string"}
        }
    }
}

try:
    import jsonschema
    SCHEMA_VALIDATION = True
except ImportError:
    logger.warning("jsonschema not installed. Schema validation disabled.")
    SCHEMA_VALIDATION = False

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

class ReminderManager:
    def __init__(self):
        self.reminders: List[Reminder] = []
        self._user_cache = {}
        self._rate_limit_reset = 0
        self._retry_count = {}
    
    def save_reminders(self):
        data = [reminder.to_dict() for reminder in self.reminders]
        try:
            if SCHEMA_VALIDATION:
                try:
                    jsonschema.validate(instance=data, schema=REMINDER_SCHEMA)
                except jsonschema.exceptions.ValidationError as e:
                    logger.error(f"Invalid reminder data: {e}")
                    return

            save_file = src.config.SAVE_FILE
            with open(save_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving reminders: {e}")
    
    async def _fetch_user_with_backoff(self, bot, user_id, max_retries=3, base_delay=1):
        """Fetch a user with exponential backoff retry logic"""
        if user_id in self._user_cache:
            return self._user_cache[user_id]
            
        retry_key = f"user_{user_id}"
        if self._retry_count.get(retry_key, 0) >= max_retries:
            logger.warning(f"Max retries exceeded for user {user_id}")
            return None
            
        try:
            now = time.time()
            if now < self._rate_limit_reset:
                wait_time = self._rate_limit_reset - now
                logger.debug(f"Waiting for rate limit reset: {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
            
            user = await bot.fetch_user(user_id)
            if user:
                self._user_cache[user_id] = user
                self._retry_count[retry_key] = 0
                return user
                
        except discord.HTTPException as e:
            if e.status == 429:
                self._retry_count[retry_key] = self._retry_count.get(retry_key, 0) + 1
                retry_after = e.retry_after
                self._rate_limit_reset = time.time() + retry_after
                
                delay = base_delay * (2 ** (self._retry_count[retry_key] - 1))
                delay = min(delay, 30)
                
                logger.info(f"Rate limited fetching user {user_id}, retry {self._retry_count[retry_key]}/{max_retries} in {delay}s")
                await asyncio.sleep(delay)
                return await self._fetch_user_with_backoff(bot, user_id, max_retries, base_delay)
            else:
                logger.error(f"Error fetching user {user_id}: {e}")
                return None
                
        except Exception as e:
            logger.error(f"Unexpected error fetching user {user_id}: {e}")
            return None
    
    async def load_reminders(self, bot):
        import os
        import time
        save_file = src.config.SAVE_FILE
        if not os.path.exists(save_file):
            return
        
        try:
            with open(save_file, 'r') as f:
                data = json.load(f)
                
            if SCHEMA_VALIDATION:
                try:
                    jsonschema.validate(instance=data, schema=REMINDER_SCHEMA)
                except jsonschema.exceptions.ValidationError as e:
                    logger.error(f"Invalid reminder data in file: {e}")
                    return

            user_ids = set()
            for reminder_data in data:
                user_ids.add(reminder_data['author_id'])
                user_ids.update(reminder_data['target_ids'])
            
            BATCH_SIZE = 50
            user_list = list(user_ids)
            for i in range(0, len(user_list), BATCH_SIZE):
                batch = user_list[i:i + BATCH_SIZE]
                batch_tasks = []
                
                for user_id in batch:
                    if user_id not in self._user_cache:
                        await asyncio.sleep(0.1)
                        task = asyncio.create_task(self._fetch_user_with_backoff(bot, user_id))
                        batch_tasks.append(task)
                
                if batch_tasks:
                    await asyncio.gather(*batch_tasks, return_exceptions=True)
                
                if i + BATCH_SIZE < len(user_list):
                    await asyncio.sleep(1)
            
            valid_reminders = []
            for reminder_data in data:
                try:
                    author = self._user_cache.get(reminder_data['author_id'])
                    if not author:
                        continue
                    
                    targets = []
                    for user_id in reminder_data['target_ids']:
                        user = self._user_cache.get(user_id)
                        if user:
                            targets.append(user)
                    
                    if not targets:
                        continue
                    
                    channel_id = reminder_data['channel_id']
                    channel = bot.get_channel(channel_id)
                    if not channel:
                        try:
                            channel = await bot.fetch_channel(channel_id)
                        except (discord.NotFound, discord.Forbidden):
                            continue
                    
                    time = datetime.fromisoformat(reminder_data['time'])
                    timezone = reminder_data.get('timezone', 'UTC')
                    reminder = Reminder(
                        time, author, targets, reminder_data['message'],
                        channel, reminder_data['recurring'], timezone
                    )
                    reminder.guild_id = reminder_data.get('guild_id')
                    
                    now = datetime.now(ZoneInfo('UTC'))
                    if reminder.time <= now and reminder.recurring:
                        next_time = calculate_next_occurrence(reminder.time, reminder.recurring)
                        while next_time and next_time <= now:
                            next_time = calculate_next_occurrence(next_time, reminder.recurring)
                        if next_time:
                            reminder.time = next_time
                            valid_reminders.append(reminder)
                    elif reminder.time > now or reminder.recurring:
                        valid_reminders.append(reminder)
                
                except Exception as e:
                    logger.error(f"Error loading reminder: {e}")
                    continue
            
            self.reminders = valid_reminders
            logger.info(f"Loaded {len(self.reminders)} reminders from {save_file}")
            
            self.save_reminders()
            
        except Exception as e:
            logger.error(f"Error loading reminders: {e}")
            
    def clear_cache(self):
        """Clear the user cache and rate limit tracking to free up memory"""
        self._user_cache.clear()
        self._retry_count.clear()
        self._rate_limit_reset = 0

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