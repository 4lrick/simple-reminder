from datetime import datetime, timedelta
import json
import logging
from zoneinfo import ZoneInfo
from typing import List, Optional
import discord
from discord.ext import commands
from src.config import SAVE_FILE

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
    
    def save_reminders(self):
        data = [reminder.to_dict() for reminder in self.reminders]
        try:
            with open(SAVE_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving reminders: {e}")
    
    async def load_reminders(self, bot):
        import os
        if not os.path.exists(SAVE_FILE):
            return
        
        try:
            with open(SAVE_FILE, 'r') as f:
                data = json.load(f)
            
            for reminder_data in data:
                reminder = await Reminder.from_dict(reminder_data, bot)
                if reminder:
                    self.reminders.append(reminder)
            
            logger.info(f"Loaded {len(self.reminders)} reminders from {SAVE_FILE}")
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