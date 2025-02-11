import os

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
if not DISCORD_TOKEN:
    raise ValueError("No token provided. Set the DISCORD_TOKEN environment variable.")

SAVE_FILE = 'reminders.json'
CLEANUP_DAYS = 7

DEFAULT_TIMEZONE = 'UTC'