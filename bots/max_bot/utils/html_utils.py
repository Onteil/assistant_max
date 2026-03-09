"""
HTML Utilities for MAX Bot

Provides HTML escaping for user-provided content to prevent HTML injection.
All user-provided content must be escaped before including in messages with HTML parse mode.

Requirements: 12.6
"""

import html
from typing import Optional


def escape_html(text: Optional[str]) -> str:
    """
    Escape HTML special characters in user-provided text.
    
    Escapes:
    - & → &amp;
    - < → &lt;
    - > → &gt;
    - " → &quot;
    - ' → &#x27;
    
    Args:
        text: User-provided text to escape (can be None)
    
    Returns:
        Escaped text safe for HTML, or empty string if None
    
    Requirements: 12.6
    """
    if text is None:
        return ""
    
    return html.escape(str(text), quote=True)


def escape_html_dict(data: dict, keys: list[str]) -> dict:
    """
    Escape HTML in specific keys of a dictionary.
    
    Args:
        data: Dictionary containing user data
        keys: List of keys to escape
    
    Returns:
        New dictionary with escaped values
    
    Requirements: 12.6
    """
    escaped_data = data.copy()
    
    for key in keys:
        if key in escaped_data and escaped_data[key] is not None:
            escaped_data[key] = escape_html(escaped_data[key])
    
    return escaped_data


def format_user_text(text: Optional[str], max_length: Optional[int] = None) -> str:
    """
    Format user-provided text for display in messages.
    
    Performs:
    1. HTML escaping
    2. Optional truncation with ellipsis
    3. Whitespace normalization
    
    Args:
        text: User-provided text
        max_length: Optional maximum length (truncates with "..." if exceeded)
    
    Returns:
        Formatted and escaped text
    
    Requirements: 12.6
    """
    if text is None:
        return ""
    
    # Escape HTML
    escaped = escape_html(text)
    
    # Normalize whitespace (collapse multiple spaces/newlines)
    normalized = " ".join(escaped.split())
    
    # Truncate if needed
    if max_length and len(normalized) > max_length:
        return normalized[:max_length - 3] + "..."
    
    return normalized


def format_user_multiline(text: Optional[str], max_lines: Optional[int] = None) -> str:
    """
    Format user-provided multiline text for display.
    
    Performs:
    1. HTML escaping
    2. Optional line limit with "..." indicator
    3. Preserves line breaks
    
    Args:
        text: User-provided multiline text
        max_lines: Optional maximum number of lines
    
    Returns:
        Formatted and escaped multiline text
    
    Requirements: 12.6
    """
    if text is None:
        return ""
    
    # Escape HTML
    escaped = escape_html(text)
    
    # Split into lines
    lines = escaped.split('\n')
    
    # Limit lines if needed
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines.append("...")
    
    return '\n'.join(lines)


def safe_format(template: str, **kwargs) -> str:
    """
    Safely format template with user-provided values.
    
    Escapes all kwargs values before formatting to prevent HTML injection.
    
    Args:
        template: Format string template
        **kwargs: Values to format (will be escaped)
    
    Returns:
        Formatted string with escaped values
    
    Example:
        safe_format("Hello, <b>{name}</b>!", name=user_input)
        # If user_input = "<script>alert('xss')</script>"
        # Returns: "Hello, <b>&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;</b>!"
    
    Requirements: 12.6
    """
    # Escape all values
    escaped_kwargs = {
        key: escape_html(value) if isinstance(value, str) else value
        for key, value in kwargs.items()
    }
    
    return template.format(**escaped_kwargs)


def format_profile_field(label: str, value: Optional[str], empty_text: str = "Не указано") -> str:
    """
    Format profile field for display with HTML escaping.
    
    Args:
        label: Field label (not escaped, should be safe)
        value: User-provided value (will be escaped)
        empty_text: Text to show if value is empty
    
    Returns:
        Formatted field string
    
    Requirements: 12.6
    """
    if value:
        escaped_value = escape_html(value)
        return f"<b>{label}:</b> {escaped_value}"
    else:
        return f"<b>{label}:</b> <i>{empty_text}</i>"


def format_list_item(text: str, escape: bool = True) -> str:
    """
    Format list item with bullet point and optional HTML escaping.
    
    Args:
        text: Item text
        escape: Whether to escape HTML (default: True)
    
    Returns:
        Formatted list item
    
    Requirements: 12.6
    """
    if escape:
        text = escape_html(text)
    
    return f"• {text}"


def format_numbered_item(number: int, text: str, escape: bool = True) -> str:
    """
    Format numbered list item with optional HTML escaping.
    
    Args:
        number: Item number
        text: Item text
        escape: Whether to escape HTML (default: True)
    
    Returns:
        Formatted numbered item
    
    Requirements: 12.6
    """
    if escape:
        text = escape_html(text)
    
    return f"{number}. {text}"
