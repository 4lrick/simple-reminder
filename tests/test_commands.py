import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import discord
from src.commands.set_reminder import reminder_set
from src.commands.list_reminders import list_command
from src.commands.remove_reminder import remove_command
from src.reminder import ReminderManager, Reminder

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