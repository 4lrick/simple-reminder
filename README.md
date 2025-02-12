# Simple Reminder Bot

[![Tests](https://github.com/4lrick/simple-reminder/actions/workflows/run-tests.yml/badge.svg)](https://github.com/4lrick/simple-reminder/actions/workflows/run-tests.yml)
[![Docker Build](https://github.com/4lrick/simple-reminder/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/4lrick/simple-reminder/actions/workflows/docker-publish.yml)

A Discord bot that manages reminders with features like:
- One-time and recurring reminders
- 15-minute advance notifications
- Mention multiple users
- List, edit, and remove reminders
- Support for different timezones
- Native Discord timestamp display

## Setup & Deployment

1. Clone the repository:
```bash
git clone https://github.com/4lrick/simple-reminder.git
cd simple-reminder
```

2. Start the bot with your Discord token:
```bash
DISCORD_TOKEN=your_token_here docker compose up -d
```

### Data Persistence

The bot stores all reminders in `/app/data/reminders.json` which is persisted using a Docker named volume `reminder-data`. This ensures your reminders survive container updates and restarts.

To backup your reminders:
```bash
# Copy reminders from the container
docker cp simple-reminder:/app/data/reminders.json ./reminders_backup.json

# To restore from backup
docker cp ./reminders_backup.json simple-reminder:/app/data/reminders.json
docker restart simple-reminder
```

## Usage

### Commands

```
/reminder list                   List all your active reminders
/reminder help                   Show help about using the bot
/reminder remove number:<number> Remove a reminder by its number
/reminder edit number:<number> [date:YYYY-MM-DD] [time:HH:MM] [message:MESSAGE] [timezone:ZONE] [recurring:TYPE]
/reminder set date:<date> time:<time> message:<message> [timezone:<zone>] [recurring:<type>]
```

### Examples

```
/reminder set date:2025-02-10 time:10:00 timezone:Europe/Paris recurring:daily message:Daily standup
/reminder set date:2025-02-10 time:14:00 message:@user1 @user2 Team meeting
```

### Additional Options
- Timezone: Use timezone: parameter with region name (e.g., Europe/Paris)
- Recurring: Use recurring: parameter (daily/weekly/monthly)
- Mentions: Include @mentions directly in your message
- Edit: Only specify the fields you want to change when editing

## Development

### Testing

The project uses pytest for testing. To run the tests locally:

```bash
# Install dev dependencies
pip install -r requirements.txt

# Run tests
python -m pytest tests/ -v
```

### CI/CD

The project uses GitHub Actions for:
- Running tests on Python 3.11, 3.12, and 3.13
- Building and publishing Docker images

Pull requests must pass all tests before being merged.
