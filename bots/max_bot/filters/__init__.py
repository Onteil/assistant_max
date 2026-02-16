"""
Filters Package for MAX Bot

Contains custom filters for handler routing:
- chat_filter: Filter updates by chat type (private, group, channel)
"""

from .chat_filter import PrivateChatFilter

__all__ = ["PrivateChatFilter"]
