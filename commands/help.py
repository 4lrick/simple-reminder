import discord
from discord import app_commands

HELP_TEXT = """📝 **Simple Reminder Bot Commands**

**Slash Commands:**
```
/reminder list
/reminder help
/reminder remove number:<number>
/reminder edit number:<number> [date:YYYY-MM-DD] [time:HH:MM] [message:MESSAGE] [timezone:ZONE] [recurring:TYPE]
/reminder set date:YYYY-MM-DD time:HH:MM message:MESSAGE [timezone:ZONE] [recurring:TYPE]
```

**Text Commands:**
```
!reminder list
!reminder help
!reminder remove NUMBER
!reminder edit NUMBER date:YYYY-MM-DD time:HH:MM message:MESSAGE timezone:ZONE recurring:TYPE
!reminder YYYY-MM-DD HH:MM [tz:ZONE] [TYPE] [@users] MESSAGE
```

**Examples:**
Create a reminder:
```
/reminder set date:2024-02-10 time:14:00 message:@user1 @user2 Team meeting
!reminder 2024-02-10 14:00 tz:Europe/Paris daily @user1 @user2 Team meeting
```

Edit a reminder:
```
/reminder edit number:1 time:14:30 message:Updated meeting time
!reminder edit 1 time:14:30 message:Updated meeting time
!reminder edit 1 recurring:none    # Remove recurring status
```

**Options:**
• Timezone: Use timezone: (slash) or tz: (text) with region name
• Recurring Options:
  - When creating: daily, weekly, monthly
  - When editing: daily, weekly, monthly, none (to remove recurring)
• Time Format: 24-hour (HH:MM)

**Tips:**
• Use the tab key for command autocomplete
• Numbers in edit/remove commands are from !reminder list
• You can edit multiple fields at once
• Only the reminder creator can edit/remove it"""

async def show_help(ctx):
    is_interaction = isinstance(ctx, discord.Interaction)
    if is_interaction:
        await ctx.response.send_message(HELP_TEXT) if not ctx.response.is_done() else await ctx.followup.send(HELP_TEXT)
    else:
        await ctx.send(HELP_TEXT)