from datetime import datetime
from zoneinfo import ZoneInfo, available_timezones
import discord
from discord import app_commands
from reminder import format_discord_timestamp, calculate_next_occurrence
import re

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
    """Autocomplete for both set and edit commands - 'none' only shown for edit command"""
    command_name = interaction.command.name if interaction.command else ""
    options = ['daily', 'weekly', 'monthly']
    
    # Add 'none' option only for edit command
    if command_name == "edit":
        options.append('none')
    
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
                        human_readable_msg = format_mentions(r.message, interaction.guild)
                        message_preview = human_readable_msg[:30] + "..." if len(human_readable_msg) > 30 else human_readable_msg
                        remove_option = f'"remove {user_reminder_count}"'
                        recurring_str = f" (Recurring: {r.recurring})" if r.recurring else ""
                        time_str = format_timestamp(r.time.astimezone(ZoneInfo(r.timezone)))
                        remove_display = f"Remove #{user_reminder_count}: {time_str} - {message_preview}{recurring_str}"
                        options.append(app_commands.Choice(name=remove_display, value=remove_option))
    
    return options[:25]

async def number_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Autocomplete for reminder numbers, showing a preview of each reminder."""
    now = datetime.now(ZoneInfo('UTC'))
    user_reminders = []
    guild_id = interaction.guild.id if interaction.guild else None
    
    for r in interaction.client.reminder_manager.reminders:
        if r.guild_id != guild_id:
            continue
            
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
    options = []
    
    for i, reminder in enumerate(user_reminders, 1):
        if not current or str(i).startswith(current):
            human_readable_msg = format_mentions(reminder.message, interaction.guild)
            message_preview = human_readable_msg[:30] + "..." if len(human_readable_msg) > 30 else human_readable_msg
            recurring_str = f" (Recurring: {reminder.recurring})" if reminder.recurring else ""
            timezone_str = f" ({reminder.timezone})" if reminder.timezone != 'UTC' else ""
            time_str = format_timestamp(reminder.time.astimezone(ZoneInfo(reminder.timezone)))
            display = f"#{i}: {time_str} - {message_preview}{recurring_str}{timezone_str}"
            options.append(app_commands.Choice(name=display, value=str(i)))
    
    return options[:25]