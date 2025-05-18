from datetime import datetime
from zoneinfo import ZoneInfo, available_timezones
import discord
from discord import app_commands
from src.reminder import format_discord_timestamp, calculate_next_occurrence
import re
import logging
from typing import List

logger = logging.getLogger('reminder_bot.commands.autocomplete')

COMMON_TIMEZONES = [
    "UTC",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Europe/Moscow",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "Asia/Tokyo",
    "Asia/Shanghai",
    "Asia/Dubai",
    "Australia/Sydney",
    "Pacific/Auckland"
]

def format_mentions(text: str, guild: discord.Guild) -> str:
    """Convert Discord mention format to human-readable text."""
    user_pattern = r'<@!?(\d+)>'
    for user_id in re.findall(user_pattern, text):
        try:
            member = guild.get_member(int(user_id))
            if member:
                text = text.replace(f'<@{user_id}>', f'@{member.display_name}')
                text = text.replace(f'<@!{user_id}>', f'@{member.display_name}')
        except (ValueError, AttributeError):
            pass

    role_pattern = r'<@&(\d+)>'
    for role_id in re.findall(role_pattern, text):
        try:
            role = guild.get_role(int(role_id))
            if role:
                text = text.replace(f'<@&{role_id}>', f'@{role.name}')
        except (ValueError, AttributeError):
            pass

    channel_pattern = r'<#(\d+)>'
    for channel_id in re.findall(channel_pattern, text):
        try:
            channel = guild.get_channel(int(channel_id))
            if channel:
                text = text.replace(f'<#{channel_id}>', f'#{channel.name}')
        except (ValueError, AttributeError):
            pass

    return text

def format_timestamp(dt: datetime) -> str:
    """Convert Discord timestamp to human-readable format."""
    return dt.strftime('%Y-%m-%d %H:%M')

async def timezone_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    """Autocomplete for timezone names"""
    try:
        current = current.lower()
        choices = []
        
        if not current:
            for tz in COMMON_TIMEZONES:
                choices.append(app_commands.Choice(name=tz, value=tz))
            return choices[:25]
        
        for tz in available_timezones():
            if current in tz.lower():
                choices.append(app_commands.Choice(name=tz, value=tz))
                if len(choices) >= 25: 
                    break
        
        return choices
    except Exception as e:
        logger.error(f"Error in timezone autocomplete: {e}")
        return []

async def recurring_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Autocomplete for both set and edit commands - 'none' only shown for edit command"""
    command_name = interaction.command.name if interaction.command else ""
    options = ['daily', 'weekly', 'monthly']
    
    if command_name == "edit":
        options.append('none')
    
    return [
        app_commands.Choice(name=truncate_display_name(opt), value=opt)
        for opt in options if current.lower() in opt.lower()
    ]

def truncate_display_name(text: str, max_length: int = 100) -> str:
    """Truncate a display name to fit Discord's limits"""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

async def message_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Shows current reminder message when editing"""
    command_name = interaction.command.name if interaction.command else ""
    if command_name != "edit":
        return []

    try:
        reminder_number = None
        if hasattr(interaction, 'namespace'):
            reminder_number = interaction.namespace.number
        else:
            for option in interaction.data.get("options", []):
                if option.get("name") == "number":
                    reminder_number = int(option.get("value"))
                    break

        if reminder_number is None:
            return []

        now = datetime.now(ZoneInfo('UTC'))
        user_reminders = []
        guild_id = interaction.guild.id if interaction.guild else None
        
        for r in interaction.client.reminder_manager.reminders:
            if r.guild_id != guild_id:
                continue
                
            if interaction.user in r.targets or interaction.user == r.author:
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
        if 0 <= reminder_number - 1 < len(user_reminders):
            reminder = user_reminders[reminder_number - 1]
            
            raw_msg = reminder.message
            formatted_msg = format_mentions(raw_msg, interaction.guild)
            value = raw_msg[:97] + "..." if len(raw_msg) > 100 else raw_msg
            
            if current:
                if current.lower() in formatted_msg.lower():
                    return [app_commands.Choice(name=formatted_msg, value=value)]
                return []
            else:
                return [app_commands.Choice(name=formatted_msg, value=value)]

    except (ValueError, AttributeError, TypeError) as e:
        logger.error(f"Error in message_autocomplete: {e}")
        pass
    
    return []

async def number_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Autocomplete for reminder numbers, showing a preview of each reminder."""
    now = datetime.now(ZoneInfo('UTC'))
    user_reminders = []
    guild_id = interaction.guild.id if interaction.guild else None
    
    for r in interaction.client.reminder_manager.reminders:
        if r.guild_id != guild_id:
            continue
            
        if interaction.user in r.targets or interaction.user == r.author:
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
    options = []
    total_reminders = len(user_reminders)
    
    REMINDERS_PER_PAGE = 5
    
    if current and current.isdigit():
        target_num = int(current)
        target_page = (target_num - 1) // REMINDERS_PER_PAGE + 1
    else:
        target_page = 1
        
    display_start = (target_page - 1) * REMINDERS_PER_PAGE
    display_end = min(display_start + REMINDERS_PER_PAGE, total_reminders)
    
    if display_start >= total_reminders:
        display_start = 0
        display_end = min(REMINDERS_PER_PAGE, total_reminders)
    
    for i in range(display_start, display_end):
        reminder = user_reminders[i]
        num = i + 1
        
        human_readable_msg = format_mentions(reminder.message, interaction.guild)
        message_preview = human_readable_msg[:30] + "..." if len(human_readable_msg) > 30 else human_readable_msg
        
        mentioned_users = [t.display_name for t in reminder.targets]
        mentions_str = f" (For: {', '.join(mentioned_users)})" if mentioned_users else ""
        
        recurring_str = f" (Recurring: {reminder.recurring})" if reminder.recurring else ""
        timezone_str = f" ({reminder.timezone})" if reminder.timezone != 'UTC' else ""
        time_str = format_timestamp(reminder.time.astimezone(ZoneInfo(reminder.timezone)))
        
        creator_str = "" if reminder.author == interaction.user else f" (by {reminder.author.display_name})"
        display = f"#{num}: {time_str} - {message_preview}{mentions_str}{recurring_str}{timezone_str}{creator_str}"
        options.append(app_commands.Choice(name=truncate_display_name(display), value=str(num)))
    
    return options[:25]