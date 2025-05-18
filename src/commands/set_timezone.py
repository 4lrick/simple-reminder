import discord
from discord import app_commands
import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from .autocomplete import timezone_autocomplete

logger = logging.getLogger('reminder_bot.commands.timezone')

@app_commands.command(name="timezone", description="Show or set the default timezone for this server")
@app_commands.describe(timezone="The timezone to set (e.g., Europe/Paris, America/New_York). Leave empty to show current timezone.")
@app_commands.autocomplete(timezone=timezone_autocomplete)
async def timezone_command(interaction: discord.Interaction, timezone: str = None):
    """Show or set the default timezone for the server"""
    logger.info(
        f"Command: /reminder timezone | User: {interaction.user.name} ({interaction.user.id}) | "
        f"Server: {interaction.guild.name if interaction.guild else 'DM'} ({interaction.guild.id if interaction.guild else 'N/A'}) | "
        f"Timezone: {timezone if timezone else 'show current'}"
    )
    
    if not interaction.guild:
        await interaction.response.send_message("❌ This command can only be used in a server.")
        return
    
    if timezone is None:
        current_tz = interaction.client.server_config.get_server_timezone(interaction.guild.id)
        await interaction.response.send_message(f"🕒 Current server timezone is set to: {current_tz}")
        return
    
    if not interaction.user.guild_permissions.manage_guild:
        raise app_commands.errors.MissingPermissions(['manage_guild'])
    
    try:
        ZoneInfo(timezone)
        
        success = interaction.client.server_config.set_server_timezone(interaction.guild.id, timezone)
        if success:
            await interaction.response.send_message(f"✅ Server timezone has been set to {timezone}")
        else:
            await interaction.response.send_message("❌ Failed to set server timezone. Please try again.")
            
    except ZoneInfoNotFoundError:
        await interaction.response.send_message(
            "❌ Invalid timezone. Please use a valid timezone name.\n"
            "Examples: Europe/Paris, America/New_York, Asia/Tokyo\n"
            "See full list: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones"
        ) 