"""
Messenger abstraction layer for MAX Bot.

This module provides abstract interfaces and implementations for messenger operations,
enabling decoupling of business logic from messenger-specific APIs.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class MessageContext:
    """Messenger-agnostic message context."""

    chat_id: int
    user_id: int
    text: Optional[str]
    payload: Optional[dict]
    attachments: list[Any]
    raw_update: Any


@dataclass
class KeyboardButton:
    """Messenger-agnostic button representation."""

    text: str
    payload: Optional[dict] = None
    url: Optional[str] = None
    button_type: str = "callback"  # callback, link, contact, location


@dataclass
class Keyboard:
    """Messenger-agnostic keyboard representation."""

    buttons: list[list[KeyboardButton]]
    inline: bool = True
    one_time: bool = False


class IMessengerAdapter(ABC):
    """Abstract interface for messenger operations."""

    @abstractmethod
    async def send_message(
        self,
        chat_id: int,
        text: str,
        keyboard: Optional[Keyboard] = None,
        parse_mode: Optional[str] = None
    ) -> int:
        """
        Send a message to a chat.
        
        Args:
            chat_id: Target chat identifier
            text: Message text
            keyboard: Optional keyboard to attach
            parse_mode: Optional parse mode (HTML, Markdown)
            
        Returns:
            Message ID of the sent message
        """
        pass

    @abstractmethod
    async def edit_message(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        keyboard: Optional[Keyboard] = None,
        parse_mode: Optional[str] = None
    ) -> bool:
        """
        Edit an existing message.
        
        Args:
            chat_id: Chat identifier
            message_id: Message identifier to edit
            text: New message text
            keyboard: Optional new keyboard
            parse_mode: Optional parse mode (HTML, Markdown)
            
        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def delete_message(
        self,
        chat_id: int,
        message_id: int
    ) -> bool:
        """
        Delete a message.
        
        Args:
            chat_id: Chat identifier
            message_id: Message identifier to delete
            
        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def send_photo(
        self,
        chat_id: int,
        photo_path: str,
        caption: Optional[str] = None,
        keyboard: Optional[Keyboard] = None,
        parse_mode: Optional[str] = None
    ) -> int:
        """
        Upload and send a photo.
        
        Args:
            chat_id: Target chat identifier
            photo_path: Local path to photo file
            caption: Optional photo caption
            keyboard: Optional keyboard to attach
            parse_mode: Optional parse mode (HTML, Markdown)
            
        Returns:
            Message ID of the sent message
        """
        pass

    @abstractmethod
    async def send_document(
        self,
        chat_id: int,
        document_path: str,
        caption: Optional[str] = None,
        keyboard: Optional[Keyboard] = None,
        parse_mode: Optional[str] = None
    ) -> int:
        """
        Upload and send a document.
        
        Args:
            chat_id: Target chat identifier
            document_path: Local path to document file
            caption: Optional document caption
            keyboard: Optional keyboard to attach
            parse_mode: Optional parse mode (HTML, Markdown)
            
        Returns:
            Message ID of the sent message
        """
        pass

    @abstractmethod
    async def answer_callback(
        self,
        callback_id: str,
        text: Optional[str] = None,
        show_alert: bool = False
    ) -> bool:
        """
        Answer a callback query.
        
        Args:
            callback_id: Callback query identifier
            text: Optional text to show to user
            show_alert: Whether to show as alert popup
            
        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def download_file(
        self,
        file_url: str,
        destination: str
    ) -> str:
        """
        Download a file from URL.
        
        Args:
            file_url: URL of the file to download
            destination: Local path to save the file
            
        Returns:
            Local path where file was saved
        """
        pass



import json
import logging
from pathlib import Path
from typing import Optional

import aiofiles
import aiohttp
from maxapi import Bot
from maxapi.enums.parse_mode import ParseMode
from maxapi.types import (
    CallbackButton,
    InputMedia,
    LinkButton,
    RequestContactButton,
    RequestGeoLocationButton,
)
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from .exceptions import MAXAPIError

logger = logging.getLogger(__name__)


class MAXMessengerAdapter(IMessengerAdapter):
    """MAX-specific implementation of messenger adapter."""

    def __init__(self, bot: Bot):
        """
        Initialize MAX messenger adapter.
        
        Args:
            bot: maxapi Bot instance
        """
        self.bot = bot

    async def send_message(
        self,
        chat_id: int,
        text: str,
        keyboard: Optional[Keyboard] = None,
        parse_mode: Optional[str] = None
    ) -> int:
        """Send a message via MAX API."""
        max_keyboard = self._convert_keyboard(keyboard) if keyboard else None
        max_parse_mode = self._convert_parse_mode(parse_mode)

        try:
            response = await self.bot.send_message(
                chat_id=chat_id,
                text=text,
                attachments=[max_keyboard] if max_keyboard else None,
                parse_mode=max_parse_mode
            )
            return response.message_id
        except Exception as e:
            logger.error(f"Failed to send message to {chat_id}: {e}")
            # Convert to MAXAPIError if it's an API error
            if hasattr(e, 'status_code'):
                raise MAXAPIError(
                    code=e.status_code,
                    message=str(e),
                    response=getattr(e, 'response', None)
                )
            raise

    async def edit_message(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        keyboard: Optional[Keyboard] = None,
        parse_mode: Optional[str] = None
    ) -> bool:
        """Edit a message via MAX API."""
        max_keyboard = self._convert_keyboard(keyboard) if keyboard else None
        max_parse_mode = self._convert_parse_mode(parse_mode)

        try:
            await self.bot.edit_message(
                message_id=message_id,
                text=text,
                attachments=[max_keyboard] if max_keyboard else None,
                parse_mode=max_parse_mode
            )
            return True
        except Exception as e:
            logger.error(f"Failed to edit message {message_id} in chat {chat_id}: {e}")
            # Convert to MAXAPIError if it's an API error
            if hasattr(e, 'status_code'):
                raise MAXAPIError(
                    code=e.status_code,
                    message=str(e),
                    response=getattr(e, 'response', None)
                )
            return False

    async def delete_message(
        self,
        chat_id: int,
        message_id: int
    ) -> bool:
        """Delete a message via MAX API."""
        try:
            result = await self.bot.delete_message(message_id=message_id)
            return result.ok if hasattr(result, 'ok') else True
        except Exception as e:
            logger.error(f"Failed to delete message {message_id} in chat {chat_id}: {e}")
            # Convert to MAXAPIError if it's an API error
            if hasattr(e, 'status_code'):
                raise MAXAPIError(
                    code=e.status_code,
                    message=str(e),
                    response=getattr(e, 'response', None)
                )
            return False

    async def send_photo(
        self,
        chat_id: int,
        photo_path: str,
        caption: Optional[str] = None,
        keyboard: Optional[Keyboard] = None,
        parse_mode: Optional[str] = None
    ) -> int:
        """Upload and send a photo via MAX API."""
        max_keyboard = self._convert_keyboard(keyboard) if keyboard else None
        max_parse_mode = self._convert_parse_mode(parse_mode)

        try:
            # Create attachments list with photo and optional keyboard
            attachments = [InputMedia(path=photo_path)]
            if max_keyboard:
                attachments.append(max_keyboard)

            response = await self.bot.send_message(
                chat_id=chat_id,
                text=caption or "",
                attachments=attachments,
                parse_mode=max_parse_mode
            )
            return response.message_id
        except Exception as e:
            logger.error(f"Failed to send photo to {chat_id}: {e}")
            # Convert to MAXAPIError if it's an API error
            if hasattr(e, 'status_code'):
                raise MAXAPIError(
                    code=e.status_code,
                    message=str(e),
                    response=getattr(e, 'response', None)
                )
            raise

    async def send_document(
        self,
        chat_id: int,
        document_path: str,
        caption: Optional[str] = None,
        keyboard: Optional[Keyboard] = None,
        parse_mode: Optional[str] = None
    ) -> int:
        """Upload and send a document via MAX API."""
        max_keyboard = self._convert_keyboard(keyboard) if keyboard else None
        max_parse_mode = self._convert_parse_mode(parse_mode)

        try:
            # Create attachments list with document and optional keyboard
            attachments = [InputMedia(path=document_path)]
            if max_keyboard:
                attachments.append(max_keyboard)

            response = await self.bot.send_message(
                chat_id=chat_id,
                text=caption or "",
                attachments=attachments,
                parse_mode=max_parse_mode
            )
            return response.message_id
        except Exception as e:
            logger.error(f"Failed to send document to {chat_id}: {e}")
            # Convert to MAXAPIError if it's an API error
            if hasattr(e, 'status_code'):
                raise MAXAPIError(
                    code=e.status_code,
                    message=str(e),
                    response=getattr(e, 'response', None)
                )
            raise

    async def answer_callback(
        self,
        callback_id: str,
        text: Optional[str] = None,
        show_alert: bool = False
    ) -> bool:
        """
        Answer a callback query via MAX API.
        
        Note: In maxapi, callback answers are typically handled via event.answer()
        in the callback handler itself. This method provides a way to answer
        callbacks programmatically when needed.
        
        Args:
            callback_id: Callback query identifier (not used in maxapi event.answer())
            text: Optional text to show to user
            show_alert: Whether to show as alert popup (not directly supported in maxapi)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # In maxapi, callback answers are handled via event.answer() in handlers
            # This is a compatibility method for the abstraction layer
            # The actual callback answering should be done in the handler using:
            # await event.answer(new_text="response text")
            logger.info(f"Callback answer requested for {callback_id}: {text}")
            return True
        except Exception as e:
            logger.error(f"Failed to answer callback {callback_id}: {e}")
            return False

    async def download_file(
        self,
        file_url: str,
        destination: str
    ) -> str:
        """
        Download a file from URL to the media directory.
        
        Args:
            file_url: URL of the file to download
            destination: Local path to save the file (relative to media directory)
            
        Returns:
            Local path where file was saved
        """
        try:
            # Ensure destination is within media directory
            dest_path = Path(destination)
            if not dest_path.is_absolute():
                # If relative path, make it relative to media directory
                media_dir = Path("media")
                dest_path = media_dir / dest_path

            # Ensure destination directory exists
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            # Download file using aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(file_url) as response:
                    response.raise_for_status()

                    async with aiofiles.open(dest_path, 'wb') as f:
                        await f.write(await response.read())

            logger.info(f"Downloaded file from {file_url} to {dest_path}")
            return str(dest_path)
        except aiohttp.ClientResponseError as e:
            logger.error(f"Failed to download file from {file_url}: HTTP {e.status}")
            # Convert HTTP errors to MAXAPIError
            raise MAXAPIError(
                code=e.status,
                message=f"Failed to download file: {e.message}",
                response=None
            )
        except Exception as e:
            logger.error(f"Failed to download file from {file_url}: {e}")
            raise

    def _convert_keyboard(self, keyboard: Keyboard):
        """
        Convert abstract Keyboard to MAX keyboard format.
        
        Args:
            keyboard: Abstract keyboard representation
            
        Returns:
            MAX keyboard markup (ButtonsPayload)
        """
        if not keyboard or not keyboard.buttons:
            return None

        builder = InlineKeyboardBuilder()

        for row in keyboard.buttons:
            row_buttons = []
            for button in row:
                max_button = self._convert_button(button)
                if max_button:
                    row_buttons.append(max_button)

            if row_buttons:
                builder.row(*row_buttons)

        return builder.as_markup()

    def _convert_button(self, button: KeyboardButton):
        """
        Convert abstract KeyboardButton to MAX button type.
        
        Args:
            button: Abstract button representation
            
        Returns:
            MAX button instance (CallbackButton, LinkButton, etc.)
        """
        if button.button_type == "link" and button.url:
            return LinkButton(text=button.text, url=button.url)
        elif button.button_type == "contact":
            return RequestContactButton(text=button.text)
        elif button.button_type == "location":
            return RequestGeoLocationButton(text=button.text)
        else:  # Default to callback button
            # Serialize payload to JSON string for callback_data
            payload_str = json.dumps(button.payload) if button.payload else ""
            return CallbackButton(text=button.text, payload=payload_str)

    def _convert_parse_mode(self, parse_mode: Optional[str]) -> Optional[ParseMode]:
        """
        Convert parse mode string to MAX ParseMode enum.
        
        Args:
            parse_mode: Parse mode string (HTML, Markdown, etc.)
            
        Returns:
            MAX ParseMode enum value or None
        """
        if not parse_mode:
            return None

        parse_mode_upper = parse_mode.upper()
        if parse_mode_upper == "HTML":
            return ParseMode.HTML
        elif parse_mode_upper in ("MARKDOWN", "MD"):
            return ParseMode.MARKDOWN

        return None
