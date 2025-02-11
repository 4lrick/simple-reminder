# Simple Reminder Bot

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

### Command Formats

**Slash Commands:**
```
/reminder list
/reminder help
/reminder remove number:<number>
/reminder edit number:<number> [date:YYYY-MM-DD] [time:HH:MM] [message:MESSAGE] [timezone:ZONE] [recurring:TYPE]
/reminder set date:<date> time:<time> message:<message> [timezone:<zone>] [recurring:<type>]
```

**Text Commands:**
```
!reminder list
!reminder help
!reminder remove NUMBER
!reminder edit NUMBER date:YYYY-MM-DD time:HH:MM message:MESSAGE timezone:ZONE recurring:TYPE
!reminder YYYY-MM-DD HH:MM [tz:ZONE] [TYPE] [@users] MESSAGE
```

### Examples

Management commands:
```
/reminder list
/reminder help
/reminder remove number:1
/reminder edit number:1 time:14:30 message:Updated meeting time
!reminder edit 1 time:14:30 message:Updated meeting time
```

Creating reminders (slash command):
```
/reminder set date:2025-02-10 time:10:00 timezone:Europe/Paris recurring:daily message:Daily standup
/reminder set date:2025-02-10 time:14:00 message:@user1 @user2 Team meeting
```

Creating reminders (text command):
```
!reminder 2025-02-10 14:00 tz:Europe/Paris daily @user1 @user2 Team meeting
!reminder 2025-02-10 15:30 Project review
```

### Additional Options
- Timezone: Use timezone: parameter or tz: for text command
- Recurring: Use recurring: parameter (daily/weekly/monthly) or the word for text command
- Mentions: Include @mentions directly in your message
- Edit: Only specify the fields you want to change when editing
