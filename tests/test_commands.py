import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import discord
from src.commands.set_reminder import reminder_set
from src.commands.list_reminders import list_command
from src.commands.remove_reminder import remove_command
from src.reminder import ReminderManager, Reminder
from src.commands.autocomplete import number_autocomplete

class MockInteractionResponse:
    def __init__(self, interaction):
        self.interaction = interaction
        self._deferred = False
        self._responded = False
    
    async def defer(self, ephemeral=False):
        self._deferred = True
    
    async def send_message(self, content=None, embed=None, ephemeral=False):
        self.interaction.response_sent = True
        self.interaction.response_content = content
        self.interaction.response_embed = embed
        self._responded = True
    
    def is_done(self):
        return self._responded

class MockInteraction:
    def __init__(self, user, channel, client):
        self.user = user
        self.channel = channel
        self.client = client
        self.guild = channel.guild
        self.response_sent = False
        self.response_content = None
        self.response_embed = None
        self.data = {"resolved": {"users": {}}}
        self.response = MockInteractionResponse(self)

@pytest.fixture
def mock_bot(mock_user, mock_channel):
    class MockClient:
        def __init__(self):
            self.reminder_manager = ReminderManager()
            self.user = mock_user
    
    return MockClient()

@pytest.fixture
def mock_interaction(mock_user, mock_channel, mock_bot):
    return MockInteraction(mock_user, mock_channel, mock_bot)

@pytest.fixture
def future_time():
    return datetime.now(ZoneInfo("UTC")) + timedelta(days=1)

@pytest.mark.asyncio
async def test_set_reminder(mock_interaction, future_time):
    await reminder_set.callback(
        mock_interaction,
        date=future_time.strftime("%Y-%m-%d"),
        time=future_time.strftime("%H:%M"),
        message="Test reminder",
        timezone="UTC"
    )
    
    assert mock_interaction.response_sent
    assert "✅" in str(mock_interaction.response_content)
    assert "<t:" in str(mock_interaction.response_content)
    assert mock_interaction.user.mention in str(mock_interaction.response_content)

@pytest.mark.asyncio
async def test_set_reminder_invalid_date(mock_interaction):
    await reminder_set.callback(
        mock_interaction,
        date="invalid",
        time="12:00",
        message="Test reminder"
    )
    
    assert mock_interaction.response_sent
    assert "❌" in str(mock_interaction.response_content)

@pytest.mark.asyncio
async def test_list_reminders_empty(mock_interaction):
    await list_command.callback(mock_interaction)
    assert mock_interaction.response_sent
    assert "No active reminders" in str(mock_interaction.response_content)

@pytest.mark.asyncio
async def test_list_reminders_with_data(mock_interaction, future_time):
    reminder = Reminder(
        time=future_time,
        author=mock_interaction.user,
        targets=[mock_interaction.user],
        message="Test reminder",
        channel=mock_interaction.channel,
        recurring=None,
        timezone="UTC"
    )
    mock_interaction.client.reminder_manager.reminders.append(reminder)
    
    await list_command.callback(mock_interaction)
    assert mock_interaction.response_sent
    assert isinstance(mock_interaction.response_embed, discord.Embed)
    assert "Active Reminders" in mock_interaction.response_embed.title

@pytest.mark.asyncio
async def test_remove_reminder(mock_interaction, future_time):
    reminder = Reminder(
        time=future_time,
        author=mock_interaction.user,
        targets=[mock_interaction.user],
        message="Test reminder",
        channel=mock_interaction.channel,
        recurring=None,
        timezone="UTC"
    )
    mock_interaction.client.reminder_manager.reminders.append(reminder)
    
    await remove_command.callback(mock_interaction, 1)
    assert mock_interaction.response_sent
    assert "✅" in str(mock_interaction.response_content)
    assert len(mock_interaction.client.reminder_manager.reminders) == 0

@pytest.mark.asyncio
async def test_remove_reminder_invalid_number(mock_interaction, future_time):
    reminder = Reminder(
        time=future_time,
        author=mock_interaction.user,
        targets=[mock_interaction.user],
        message="Test reminder",
        channel=mock_interaction.channel,
        recurring=None,
        timezone="UTC"
    )
    mock_interaction.client.reminder_manager.reminders.append(reminder)
    
    await remove_command.callback(mock_interaction, 999)
    assert mock_interaction.response_sent
    assert "❌" in str(mock_interaction.response_content)
    assert "Invalid reminder number" in str(mock_interaction.response_content)

@pytest.mark.asyncio
async def test_set_reminder_with_separate_mentions(mock_interaction, future_time, mock_guild):
    mentioned_user = discord.Object(id=123456789)
    mentioned_user.display_name = "MentionedUser"
    mentioned_user.mention = "<@123456789>"
    
    mock_interaction.guild.get_member = lambda user_id: mentioned_user if user_id == 123456789 else None
    
    await reminder_set.callback(
        mock_interaction,
        date=future_time.strftime("%Y-%m-%d"),
        time=future_time.strftime("%H:%M"),
        message="Test reminder without mentions",
        mentions="<@123456789>",
        timezone="UTC"
    )
    
    assert mock_interaction.response_sent
    assert "✅" in str(mock_interaction.response_content)
    
    assert len(mock_interaction.client.reminder_manager.reminders) == 1
    created_reminder = mock_interaction.client.reminder_manager.reminders[0]
    
    assert created_reminder.message == "Test reminder without mentions"
    
    assert len(created_reminder.targets) >= 1
    
    assert "<@" in str(mock_interaction.response_content)

@pytest.mark.asyncio
async def test_edit_reminder_with_mentions(mock_interaction, future_time, mock_guild):
    from src.commands.edit_reminder import edit_command
    
    reminder = Reminder(
        time=future_time,
        author=mock_interaction.user,
        targets=[mock_interaction.user],
        message="Original message",
        channel=mock_interaction.channel,
        recurring=None,
        timezone="UTC"
    )
    mock_interaction.client.reminder_manager.reminders.append(reminder)
    
    mentioned_user = discord.Object(id=123456789)
    mentioned_user.display_name = "MentionedUser"
    mentioned_user.mention = "<@123456789>"
    
    mock_interaction.guild.get_member = lambda user_id: mentioned_user if user_id == 123456789 else None
    
    await edit_command.callback(
        mock_interaction,
        number=1,
        mentions="<@123456789>",
        message=None,
        date=None,
        time=None,
        timezone=None,
        recurring=None
    )
    
    assert mock_interaction.response_sent
    assert "✅" in str(mock_interaction.response_content)
    
    edited_reminder = mock_interaction.client.reminder_manager.reminders[0]
    assert edited_reminder.message == "Original message"
    
    target_ids = [target.id for target in edited_reminder.targets]
    assert 123456789 in target_ids
    
    assert mentioned_user.mention in str(mock_interaction.response_content)

@pytest.mark.asyncio
async def test_autocomplete_page_navigation(mock_interaction, future_time):
    """Test that autocomplete pagination works correctly with the REMINDERS_PER_PAGE=5 setting."""
    
    for i in range(12):
        reminder_time = future_time + timedelta(hours=i)
        reminder = Reminder(
            time=reminder_time,
            author=mock_interaction.user, 
            targets=[mock_interaction.user],
            message=f"Test reminder #{i+1}",
            channel=mock_interaction.channel,
            recurring=None,
            timezone="UTC"
        )
        mock_interaction.client.reminder_manager.reminders.append(reminder)
    
    result1 = await number_autocomplete(mock_interaction, "")
    assert len(result1) <= 5
    
    result2 = await number_autocomplete(mock_interaction, "6")
    assert len(result2) > 0
    first_result_num = int(result2[0].name.split("#")[1].split(":")[0])
    assert first_result_num == 6