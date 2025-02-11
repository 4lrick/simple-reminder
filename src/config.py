import os
import sys

def get_token():
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        print("Error: No Discord token provided!")
        print("Please set the DISCORD_TOKEN environment variable.")
        print("Example: export DISCORD_TOKEN=your_token_here")
        sys.exit(1)
    return token

DATA_DIR = 'data'
os.makedirs(DATA_DIR, exist_ok=True)

DISCORD_TOKEN = get_token()
SAVE_FILE = os.path.join(DATA_DIR, 'reminders.json')
CLEANUP_DAYS = 7
DEFAULT_TIMEZONE = 'UTC'