"""
MAX Bot Middleware Package

This package contains middleware components for the MAX bot.
Middleware intercepts and processes updates before/after handlers.
"""

from .database import DatabaseSessionMiddleware
from .throttling import ThrottlingMiddleware
from .bot_reconstruction import BotInReconstructionMiddleware
from .user_data import UserDataMiddleware
from .error_handler import ErrorHandlerMiddleware
from .state_clearer import StateClearerMiddleware
from .album import AlbumMiddleware
from .messenger_adapter import MessengerAdapterMiddleware

__all__ = [
    "DatabaseSessionMiddleware",
    "ThrottlingMiddleware",
    "BotInReconstructionMiddleware",
    "UserDataMiddleware",
    "ErrorHandlerMiddleware",
    "StateClearerMiddleware",
    "AlbumMiddleware",
    "MessengerAdapterMiddleware",
]
