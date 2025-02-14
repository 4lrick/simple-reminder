import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import discord
import json
import os
from src.reminder import Reminder, calculate_next_occurrence, format_discord_timestamp

class MockUser:
    def __init__(self, id, name):
        self.id = id
        self.name = name
        self.display_name = name
        self.mention = f"<@{id}>"

class MockChannel:
    def __init__(self, id, name):
        self.id = id
        self.name = name
        self.guild = MockGuild(1, "Test Guild")
        self._messages = []
    
    async def send(self, content):
        self._messages.append(content)
        return MockMessage(content=content)

class MockGuild:
    def __init__(self, id, name):
        self.id = id
        self.name = name

class MockMessage:
    def __init__(self, content):
        self.content = content

@pytest.fixture
def mock_user():
    return MockUser(123, "TestUser")

@pytest.fixture
def mock_channel():
    return MockChannel(456, "test-channel")

@pytest.fixture
def future_time():
    return datetime.now(ZoneInfo("UTC")) + timedelta(days=1)

@pytest.fixture
def mock_reminder_data(future_time):
    return {
        "time": future_time.isoformat(),
        "author_id": 123,
        "target_ids": [123],
        "message": "Test reminder",
        "channel_id": 456,
        "guild_id": 1,
        "recurring": None,
        "timezone": "UTC"
    }

@pytest.mark.asyncio
async def test_reminder_creation(mock_user, mock_channel, future_time):
    reminder = Reminder(future_time, mock_user, [mock_user], "Test message", mock_channel)
    
    assert reminder.time == future_time
    assert reminder.author == mock_user
    assert reminder.targets == [mock_user]
    assert reminder.message == "Test message"
    assert reminder.channel == mock_channel
    assert reminder.recurring is None
    assert reminder.timezone == "UTC"

@pytest.mark.asyncio
async def test_reminder_to_dict(mock_user, mock_channel, future_time):
    reminder = Reminder(future_time, mock_user, [mock_user], "Test message", mock_channel)
    
    data = reminder.to_dict()
    assert data["time"] == future_time.isoformat()
    assert data["author_id"] == mock_user.id
    assert data["target_ids"] == [mock_user.id]
    assert data["message"] == "Test message"
    assert data["channel_id"] == mock_channel.id
    assert data["guild_id"] == mock_channel.guild.id
    assert data["recurring"] is None
    assert data["timezone"] == "UTC"

def test_format_discord_timestamp():
    dt = datetime(2024, 1, 1, 12, 0, tzinfo=ZoneInfo("UTC"))
    
    assert format_discord_timestamp(dt, 'f') == "<t:1704110400:f>"
    assert format_discord_timestamp(dt, 't') == "<t:1704110400:t>"
    
    with pytest.raises(ValueError):
        format_discord_timestamp(dt, 'invalid')
    
    with pytest.raises(TypeError):
        format_discord_timestamp("not a datetime", 'f')

def test_calculate_next_occurrence():
    base_time = datetime(2024, 1, 1, 12, 0, tzinfo=ZoneInfo("UTC"))
    
    next_daily = calculate_next_occurrence(base_time, "daily")
    assert next_daily == base_time + timedelta(days=1)
    
    next_weekly = calculate_next_occurrence(base_time, "weekly")
    assert next_weekly == base_time + timedelta(weeks=1)
    
    next_monthly = calculate_next_occurrence(base_time, "monthly")
    assert next_monthly == datetime(2024, 2, 1, 12, 0, tzinfo=ZoneInfo("UTC"))
    
    assert calculate_next_occurrence(base_time, "invalid") is None
    
    edge_case = datetime(2024, 1, 31, 12, 0, tzinfo=ZoneInfo("UTC"))
    next_edge = calculate_next_occurrence(edge_case, "monthly")
    assert next_edge == datetime(2024, 2, 29, 12, 0, tzinfo=ZoneInfo("UTC"))  # 2024 is leap year

def test_calculate_next_occurrence_dst():
    base_time = datetime(2024, 3, 10, 1, 30, tzinfo=ZoneInfo("America/New_York"))
    next_daily = calculate_next_occurrence(base_time, "daily")
    assert next_daily.hour == 1
    
    utc_diff = next_daily.astimezone(ZoneInfo('UTC')) - base_time.astimezone(ZoneInfo('UTC'))
    assert utc_diff.total_seconds() == 23 * 3600

    base_time = datetime(2024, 11, 3, 1, 30, tzinfo=ZoneInfo("America/New_York"))
    next_daily = calculate_next_occurrence(base_time, "daily")
    assert next_daily.hour == 1
    
    utc_diff = next_daily.astimezone(ZoneInfo('UTC')) - base_time.astimezone(ZoneInfo('UTC'))
    assert utc_diff.total_seconds() == 25 * 3600

    base_time = datetime(2024, 10, 15, 2, 30, tzinfo=ZoneInfo("America/New_York"))
    next_monthly = calculate_next_occurrence(base_time, "monthly")
    assert next_monthly.month == 11
    assert next_monthly.hour == 2
    
    utc_diff = next_monthly.astimezone(ZoneInfo('UTC')) - base_time.astimezone(ZoneInfo('UTC'))
    assert utc_diff.total_seconds() > 0

@pytest.mark.asyncio
async def test_reminder_manager_save_load(mock_reminder_data, tmp_path, monkeypatch):
    from src.reminder import ReminderManager
    import src.config
    
    data_dir = tmp_path / "data"
    os.makedirs(data_dir, exist_ok=True)
    
    monkeypatch.setattr(src.config, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(src.config, "SAVE_FILE", str(data_dir / "reminders.json"))
    
    manager = ReminderManager()
    time = datetime.fromisoformat(mock_reminder_data["time"])
    reminder = Reminder(
        time=time,
        author=MockUser(123, "TestUser"),
        targets=[MockUser(123, "TestUser")],
        message=mock_reminder_data["message"],
        channel=MockChannel(456, "test-channel"),
        recurring=None,
        timezone="UTC"
    )
    manager.reminders.append(reminder)
    manager.save_reminders()
    
    save_file = data_dir / "reminders.json"
    assert os.path.exists(save_file)
    with open(save_file, 'r') as f:
        saved_data = json.load(f)
    assert len(saved_data) == 1
    assert saved_data[0]["message"] == mock_reminder_data["message"]
    
    new_manager = ReminderManager()
    
    class MockBot:
        async def fetch_user(self, user_id):
            return MockUser(user_id, f"User{user_id}")
        
        async def fetch_channel(self, channel_id):
            return MockChannel(channel_id, f"Channel{channel_id}")
        
        def get_channel(self, channel_id):
            return MockChannel(channel_id, f"Channel{channel_id}")
    
    await new_manager.load_reminders(MockBot())
    
    assert len(new_manager.reminders) == 1
    loaded_reminder = new_manager.reminders[0]
    assert loaded_reminder.message == mock_reminder_data["message"]
    assert loaded_reminder.author.id == mock_reminder_data["author_id"]
    assert loaded_reminder.channel.id == mock_reminder_data["channel_id"]