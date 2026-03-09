"""
MAX Bot Middleware Package

This package contains middleware components for the MAX bot.
Middleware intercepts and processes updates before/after handlers.
"""

from .database import DatabaseSessionMiddleware
from .messenger_adapter import MessengerAdapterMiddleware

# Temporarily disabled - missing dependencies or not yet needed
# from .throttling import ThrottlingMiddleware
# from .bot_reconstruction import BotInReconstructionMiddleware
# from .user_data import UserDataMiddleware
# from .error_handler import ErrorHandlerMiddleware
# from .state_clearer import StateClearerMiddleware
# from .album import AlbumMiddleware

__all__ = [
    "DatabaseSessionMiddleware",
    "MessengerAdapterMiddleware",
    # "ThrottlingMiddleware",
    # "BotInReconstructionMiddleware",
    # "UserDataMiddleware",
    # "ErrorHandlerMiddleware",
    # "StateClearerMiddleware",
    # "AlbumMiddleware",
]
