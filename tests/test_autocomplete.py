import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import discord
from discord import app_commands
from src.commands.autocomplete import number_autocomplete, timezone_autocomplete, COMMON_TIMEZONES
from src.reminder import Reminder

class MockUser:
    def __init__(self, id, name):
        self.id = id
        self.name = name
        self.display_name = name
        self.mention = f"<@{id}>"

class MockGuild:
    def __init__(self, id, name):
        self.id = id
        self.name = name
        
    def get_member(self, user_id):
        return None
        
    def get_role(self, role_id):
        return None

class MockChannel:
    def __init__(self, id, name, guild):
        self.id = id
        self.name = name
        self.guild = guild

class MockReminderManager:
    def __init__(self):
        self.reminders = []

class MockClient:
    def __init__(self, user):
        self.reminder_manager = MockReminderManager()
        self.user = user

class MockInteraction:
    def __init__(self, client, user, guild):
        self.client = client
        self.user = user
        self.guild = guild
        self.response_sent = False
        self.response_content = None

@pytest.fixture
def mock_user():
    return MockUser(123, "TestUser")

@pytest.fixture
def mock_guild():
    return MockGuild(1, "Test Guild")

@pytest.fixture
def mock_channel(mock_guild):
    return MockChannel(456, "test-channel", mock_guild)

@pytest.fixture
def mock_client(mock_user):
    return MockClient(mock_user)

@pytest.fixture
def mock_interaction(mock_client, mock_user, mock_guild):
    return MockInteraction(mock_client, mock_user, mock_guild)

@pytest.mark.asyncio
async def test_number_autocomplete_pagination():
    """Test that autocomplete paginates results correctly."""
    user = MockUser(123, "TestUser")
    guild = MockGuild(1, "Test Guild")
    channel = MockChannel(456, "test-channel", guild)
    client = MockClient(user)
    
    now = datetime.now(ZoneInfo("UTC"))
    future_time_base = now + timedelta(hours=1)
    
    for i in range(15):
        reminder_time = future_time_base + timedelta(hours=i)
        reminder = Reminder(
            time=reminder_time,
            author=user,
            targets=[user],
            message=f"Test reminder #{i+1}",
            channel=channel
        )
        client.reminder_manager.reminders.append(reminder)
    
    interaction = MockInteraction(client, user, guild)
    
    result1 = await number_autocomplete(interaction, "")
    assert len(result1) == 5
    assert all(int(choice.value) <= 5 for choice in result1)
    
    result2 = await number_autocomplete(interaction, "6")
    assert len(result2) == 5
    assert all(6 <= int(choice.value) <= 10 for choice in result2)
    
    result3 = await number_autocomplete(interaction, "11")
    assert len(result3) == 5
    assert all(11 <= int(choice.value) <= 15 for choice in result3)
    
    result4 = await number_autocomplete(interaction, "3")
    assert len(result4) == 5
    assert all(int(choice.value) <= 5 for choice in result4)
    
    result5 = await number_autocomplete(interaction, "100")
    assert len(result5) == 5
    assert all(int(choice.value) <= 5 for choice in result5)

@pytest.mark.asyncio
async def test_number_autocomplete_empty_reminders():
    """Test autocomplete behavior with no reminders."""
    user = MockUser(123, "TestUser")
    guild = MockGuild(1, "Test Guild")
    client = MockClient(user)
    interaction = MockInteraction(client, user, guild)
    
    result = await number_autocomplete(interaction, "")
    assert len(result) == 0

@pytest.mark.asyncio
async def test_number_autocomplete_with_few_reminders():
    """Test autocomplete with fewer reminders than page size."""
    user = MockUser(123, "TestUser")
    guild = MockGuild(1, "Test Guild") 
    channel = MockChannel(456, "test-channel", guild)
    client = MockClient(user)
    
    now = datetime.now(ZoneInfo("UTC"))
    future_time_base = now + timedelta(hours=1)
    
    for i in range(3):
        reminder_time = future_time_base + timedelta(hours=i)
        reminder = Reminder(
            time=reminder_time,
            author=user,
            targets=[user],
            message=f"Test reminder #{i+1}",
            channel=channel
        )
        client.reminder_manager.reminders.append(reminder)
    
    interaction = MockInteraction(client, user, guild)
    
    result = await number_autocomplete(interaction, "")
    assert len(result) == 3
    assert all(1 <= int(choice.value) <= 3 for choice in result)

@pytest.mark.asyncio
async def test_timezone_autocomplete_empty(mock_interaction):
    result = await timezone_autocomplete(mock_interaction, "")
    assert len(result) == len(COMMON_TIMEZONES)
    assert all(isinstance(choice, app_commands.Choice) for choice in result)
    assert all(choice.name in COMMON_TIMEZONES for choice in result)

@pytest.mark.asyncio
async def test_timezone_autocomplete_search(mock_interaction):
    result = await timezone_autocomplete(mock_interaction, "paris")
    assert len(result) > 0
    assert any(choice.name == "Europe/Paris" for choice in result)
    assert all(isinstance(choice, app_commands.Choice) for choice in result)
    assert all("paris" in choice.name.lower() for choice in result)

@pytest.mark.asyncio
async def test_timezone_autocomplete_limit(mock_interaction):
    result = await timezone_autocomplete(mock_interaction, "a")
    assert len(result) <= 25
    assert all(isinstance(choice, app_commands.Choice) for choice in result)
