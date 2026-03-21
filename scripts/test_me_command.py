"""
Test script for /me command in MAX bot.

This script simulates a /me command to verify the handler works correctly.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from bots.max_bot.handlers.user.commands import cmd_me
from maxapi.types import MessageCreated, Message, MessageBody, User, Recipient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


class MockMessengerAdapter:
    """Mock messenger adapter for testing."""
    
    async def send_message(self, chat_id: int, text: str, parse_mode: str = None, **kwargs):
        """Mock send_message method."""
        logger.info(f"[MOCK] Sending message to chat {chat_id}:")
        logger.info(f"[MOCK] Text:\n{text}")
        logger.info(f"[MOCK] Parse mode: {parse_mode}")
        return True


async def test_me_command():
    """Test the /me command handler."""
    logger.info("Testing /me command handler...")
    
    # Create mock event
    mock_event = MessageCreated(
        timestamp=1234567890,
        message=Message(
            recipient=Recipient(
                chat_id=12345,
                chat_type="dialog",
                user_id=999999
            ),
            timestamp=1234567890,
            body=MessageBody(
                mid="test_mid",
                seq=1,
                text="/me"
            ),
            sender=User(
                user_id=12345,
                first_name="Test",
                last_name="User",
                is_bot=False,
                last_activity_time=1234567890,
                name="Test User"
            )
        ),
        user_locale="ru",
        update_type="message_created"
    )
    
    # Create mock messenger adapter
    mock_adapter = MockMessengerAdapter()
    
    # Call the handler
    try:
        await cmd_me(mock_event, mock_adapter)
        logger.info("✅ /me command handler executed successfully!")
        return True
    except Exception as e:
        logger.error(f"❌ Error executing /me command: {e}", exc_info=True)
        return False


async def main():
    """Main test function."""
    logger.info("─" * 5)
    logger.info("MAX Bot /me Command Test")
    logger.info("─" * 5)
    
    success = await test_me_command()
    
    logger.info("─" * 5)
    if success:
        logger.info("✅ All tests passed!")
    else:
        logger.error("❌ Tests failed!")
    logger.info("─" * 5)
    
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
