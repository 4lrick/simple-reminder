import pytest
from datetime import datetime
from zoneinfo import ZoneInfo
import discord
from typing import List, Optional
from src.reminder import ReminderManager

class MockUser:
    id: int
    name: str
    display_name: str
    mention: str
    global_name: str

    def __init__(self, id: int, name: str):
        self.id = id
        self.name = name
        self.display_name = name
        self.global_name = name
        self.mention = f"<@{id}>"
        self.guild_permissions = type('Permissions', (), {'manage_guild': True})()

class MockChannel:
    id: int
    name: str
    guild: 'MockGuild'
    _messages: List[str]

    def __init__(self, id: int, name: str):
        self.id = id
        self.name = name
        self.guild = MockGuild(1, "Test Guild")
        self._messages = []
    
    async def send(self, content: str) -> 'MockMessage':
        self._messages.append(content)
        return MockMessage(content=content)

class MockGuild:
    id: int
    name: str

    def __init__(self, id: int, name: str):
        self.id = id
        self.name = name

class MockMessage:
    content: str

    def __init__(self, content: str):
        self.content = content

@pytest.fixture
def mock_user():
    return MockUser(123, "TestUser")

@pytest.fixture
def mock_channel():
    return MockChannel(456, "test-channel")

@pytest.fixture
def reminder_manager():
    return ReminderManager()

@pytest.fixture
def mock_reminder_data():
    return {
        "time": datetime.now(ZoneInfo("UTC")).isoformat(),
        "author_id": 123,
        "target_ids": [123],
        "message": "Test reminder",
        "channel_id": 456,
        "guild_id": 1,
        "recurring": None,
        "timezone": "UTC"
    }

@pytest.fixture
def mock_guild():
    guild = MockGuild(1, "Test Guild")
    guild.get_role = lambda role_id: None
    guild.get_member = lambda user_id: None
    guild.get_channel = lambda channel_id: None
    guild.members = []
    return guild

class MockServerConfig:
    def __init__(self):
        self.server_timezones = {}
    
    def set_server_timezone(self, guild_id: int, timezone: str) -> bool:
        try:
            ZoneInfo(timezone)
            self.server_timezones[str(guild_id)] = timezone
            return True
        except ZoneInfoNotFoundError:
            return False
    
    def get_server_timezone(self, guild_id: int) -> str:
        return self.server_timezones.get(str(guild_id), 'UTC')

@pytest.fixture
def mock_server_config():
    return MockServerConfig()

@pytest.fixture
def mock_interaction(mock_user, mock_channel, mock_server_config):
    class MockInteraction:
        def __init__(self):
            self.user = mock_user
            self.channel = mock_channel
            self.guild = mock_channel.guild
            self.response_sent = False
            self.response_message = None
            self.response_embed = None
            self.client = MockClient()
            self.data = {'resolved': {'users': {}}}
        
        async def response_send(self, content=None, embed=None):
            self.response_sent = True
            self.response_message = content
            self.response_embed = embed
        
        async def response_edit(self, content=None, embed=None):
            self.response_sent = True
            self.response_message = content
            self.response_embed = embed
    
    interaction = MockInteraction()
    interaction.client.reminder_manager = ReminderManager()
    interaction.client.server_config = mock_server_config
    interaction.response = type('Response', (), {
        'send_message': interaction.response_send,
        'edit_message': interaction.response_edit
    })
    return interaction