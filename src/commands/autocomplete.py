from datetime import datetime
from zoneinfo import ZoneInfo, available_timezones
import discord
from discord import app_commands
from src.reminder import format_discord_timestamp, calculate_next_occurrence
import re
import logging

logger = logging.getLogger('reminder_bot.commands.autocomplete')

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

async def timezone_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    common_zones = [
        'UTC', 'Europe/Paris', 'Europe/London', 'America/New_York', 
        'America/Los_Angeles', 'Asia/Tokyo', 'Asia/Shanghai', 
        'Australia/Sydney', 'Pacific/Auckland'
    ]
    
    options = []
    for tz in common_zones:
        if not current or current.lower() in tz.lower():
            options.append(app_commands.Choice(name=truncate_display_name(tz), value=tz))
    
    if len(options) < 25:
        remaining_slots = 25 - len(options)
        all_zones = available_timezones()
        matching_zones = sorted([
            tz for tz in all_zones 
            if tz not in common_zones and (not current or current.lower() in tz.lower())
        ])
        
        for tz in matching_zones[:remaining_slots]:
            options.append(app_commands.Choice(name=truncate_display_name(tz), value=tz))
    
    return options

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
            
            if current:
                if current.lower() in formatted_msg.lower():
                    return [app_commands.Choice(name=formatted_msg, value=raw_msg)]
                return []
            else:
                return [app_commands.Choice(name=formatted_msg, value=raw_msg)]

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
    
    try:
        target_num = int(current) if current and current.isdigit() else 1
        total_reminders = len(user_reminders)
        
        if current and current.isdigit():
            target_num = int(current)
            start_idx = max(0, target_num - 3)
            end_idx = min(total_reminders, start_idx + 5)
            start_idx = max(0, end_idx - 5)
        else:
            start_idx = 0
            end_idx = min(5, total_reminders)
            
            if total_reminders > 5:
                jump_points = []
                
                for i in range(5, total_reminders, 5):
                    jump_points.append(i + 1)
                
                for point in jump_points[:3]:
                    options.append(app_commands.Choice(
                        name=f"↓ Jump to #{point} and beyond...",
                        value=str(point)
                    ))
        
        for i in range(start_idx, end_idx):
            reminder = user_reminders[i]
            num = i + 1
            if not current or str(num).startswith(current):
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
                
        if current and current.isdigit() and int(current) % 5 == 0 and int(current) < total_reminders:
            next_page = int(current) + 1
            options.append(app_commands.Choice(
                name=f"↓ See next page (starting at #{next_page})...",
                value=str(next_page)
            ))
            
        if current and current.isdigit() and int(current) > 5:
            options.append(app_commands.Choice(
                name="↑ Back to first page...",
                value="1"
            ))
            
    except ValueError:
        pass
    
    if len(user_reminders) > 5 and len(options) < 25:
        remaining = total_reminders - (int(current) if current and current.isdigit() else 0)
        if remaining > 0:
            display = f"Type a number between 1 and {total_reminders} to jump directly to that reminder"
            options.append(app_commands.Choice(
                name=truncate_display_name(display),
                value=current or "1"
            ))
    
    return options[:25]