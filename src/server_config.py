import os
import json
import logging
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger('reminder_bot.server_config')

class ServerConfig:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.config_file = os.path.join(data_dir, 'server_config.json')
        self.server_timezones = {}
        self.load_config()
    
    def load_config(self):
        """Load server configurations from file"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    self.server_timezones = data.get('server_timezones', {})
            except Exception as e:
                logger.error(f"Error loading server config: {e}")
    
    def save_config(self):
        """Save server configurations to file"""
        try:
            data = {
                'server_timezones': self.server_timezones
            }
            with open(self.config_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving server config: {e}")
    
    def set_server_timezone(self, guild_id: int, timezone: str) -> bool:
        """Set timezone for a specific server"""
        try:
            ZoneInfo(timezone)
            self.server_timezones[str(guild_id)] = timezone
            self.save_config()
            return True
        except ZoneInfoNotFoundError:
            return False
    
    def get_server_timezone(self, guild_id: int) -> str:
        """Get timezone for a specific server, returns UTC if not set"""
        return self.server_timezones.get(str(guild_id), 'UTC') 