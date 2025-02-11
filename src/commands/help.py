import discord
from discord import app_commands

HELP_TEXT = """📝 **Simple Reminder Bot Commands**

**Commands:**
```
/reminder list                   List all your active reminders
/reminder help                   Show this help message
/reminder remove number:<number> Remove a reminder by its number
/reminder edit number:<number> [date:YYYY-MM-DD] [time:HH:MM] [message:MESSAGE] [timezone:ZONE] [recurring:TYPE]
/reminder set date:<date> time:<time> message:<message> [timezone:<zone>] [recurring:<type>]
```

**Examples:**
```
/reminder set date:2024-02-10 time:14:00 message:@user1 @user2 Team meeting
/reminder set date:2024-02-10 time:14:00 timezone:Europe/Paris recurring:daily message:Daily standup
```

**Options:**
• Timezone: Use timezone: parameter with a region name (e.g., Europe/Paris, America/New_York)
• Recurring: Use recurring: parameter with daily, weekly, or monthly
• Time Format: 24-hour (HH:MM)
• Date Format: YYYY-MM-DD

**Tips:**
• Use the tab key for command autocomplete
• Numbers in edit/remove commands are from /reminder list
• You can edit multiple fields at once
• Only the reminder creator can edit/remove it"""

async def show_help(ctx):
    is_interaction = isinstance(ctx, discord.Interaction)
    if is_interaction:
        await ctx.response.send_message(HELP_TEXT) if not ctx.response.is_done() else await ctx.followup.send(HELP_TEXT)
    else:
        await ctx.send(HELP_TEXT)