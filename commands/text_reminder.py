from discord.ext import commands
from .help import show_help
from .list_reminders import list_reminders
from .remove_reminder import remove_reminder
from .handle_reminder import handle_reminder
from .edit_reminder import edit_command
from datetime import datetime
from zoneinfo import ZoneInfo
import re
import discord

async def parse_edit_args(args):
    """Parse arguments for the edit command in the format: key:value key:value"""
    if not args:
        return {}
    
    params = {}
    pattern = r'(\w+):((?:"[^"]*"|[^\s]*))(?:\s+|$)'
    matches = re.finditer(pattern, args)
    
    for match in matches:
        key, value = match.groups()
        value = value.strip('"')
        params[key] = value
    
    return params

async def text_reminder(ctx, action: str = None, *, args: str = None):
    if not action:
        await show_help(ctx)
        return

    if action == 'list':
        await list_reminders(ctx)
        return
    elif action == 'help':
        await show_help(ctx)
        return
    elif action == 'remove':
        await remove_reminder(ctx, args)
        return
    elif action == 'edit':
        try:
            if not args:
                await show_help(ctx)
                return
            
            parts = args.split(maxsplit=1)
            if len(parts) < 2:
                await ctx.send("❌ Please provide both a reminder number and what to edit.")
                return
            
            number = parts[0]
            params = await parse_edit_args(parts[1])
            
            if 'msg' in params:
                params['message'] = params.pop('msg')
            if 'tz' in params:
                params['timezone'] = params.pop('tz')
            
            mock_interaction = type('MockInteraction', (), {
                'response': type('MockResponse', (), {
                    'send_message': ctx.send,
                    'is_done': lambda: False
                }),
                'followup': type('MockFollowup', (), {
                    'send': ctx.send
                }),
                'user': ctx.author,
                'guild': ctx.guild,
                'client': ctx.bot,
                'guild_id': ctx.guild.id if ctx.guild else None
            })()
            
            await edit_command(
                mock_interaction,
                int(number),
                params.get('date'),
                params.get('time'),
                params.get('message'),
                params.get('timezone'),
                params.get('recurring')
            )
            return
        except ValueError:
            await ctx.send("❌ Invalid reminder number provided.")
            return
        except Exception as e:
            await ctx.send(f"❌ Error editing reminder: {str(e)}")
            return

    full_args = f"{action} {args}" if args else action
    try:
        parts = full_args.split(' ', 2)
        if len(parts) < 2:
            raise ValueError("Missing required arguments")

        date = parts[0]
        time = parts[1]
        message = parts[2] if len(parts) > 2 else ''
        
        words = message.split()
        timezone = None
        recurring = None
        
        if words and words[0].startswith('tz:'):
            timezone = words[0][3:]
            words = words[1:]
            message = ' '.join(words)
        
        if words and words[0].lower() in ['daily', 'weekly', 'monthly']:
            recurring = words[0].lower()
            words = words[1:]
            message = ' '.join(words)
        
        await handle_reminder(ctx, date, time, message, timezone, recurring)

    except ValueError:
        await show_help(ctx)