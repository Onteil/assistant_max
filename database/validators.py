"""
Validation helper functions for database fields.

Provides validators for phone numbers, INN, key numbers, and email addresses
to ensure data integrity before database insertion.

Requirements: Error Handling section
"""

import re
from typing import Optional


class ValidationError(Exception):
    """
    Custom exception for validation errors.
    
    Attributes:
        field: Name of the field that failed validation
        message: Human-readable error message
    """
    
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


def validate_phone_number(phone_number: str) -> bool:
    """
    Validate phone number format.
    
    Phone numbers must:
    - Optionally start with '+'
    - Contain 10-15 digits
    - May contain spaces, hyphens, or parentheses for formatting
    
    Args:
        phone_number: Phone number string to validate
    
    Returns:
        True if valid
    
    Raises:
        ValidationError: If phone number format is invalid
    
    Examples:
        >>> validate_phone_number("+79991234567")
        True
        >>> validate_phone_number("89991234567")
        True
        >>> validate_phone_number("+7 (999) 123-45-67")
        True
        >>> validate_phone_number("123")
        ValidationError: phone_number: Invalid phone number format
    """
    if not phone_number:
        raise ValidationError("phone_number", "Phone number is required")
    
    # Remove formatting characters for validation
    digits_only = re.sub(r'[\s\-\(\)]', '', phone_number)
    
    # Check if it starts with + and remove it for digit count
    if digits_only.startswith('+'):
        digits_only = digits_only[1:]
    
    # Validate format: 10-15 digits
    if not re.match(r'^\d{10,15}$', digits_only):
        raise ValidationError(
            "phone_number",
            "Invalid phone number format. Must contain 10-15 digits."
        )
    
    return True


def validate_inn(inn: str) -> bool:
    """
    Validate INN (tax identification number) format.
    
    INN must be either 10 or 12 digits.
    
    Args:
        inn: INN string to validate
    
    Returns:
        True if valid
    
    Raises:
        ValidationError: If INN format is invalid
    
    Examples:
        >>> validate_inn("1655060636")
        True
        >>> validate_inn("165506063612")
        True
        >>> validate_inn("123")
        ValidationError: inn: Invalid INN format
    """
    if not inn:
        raise ValidationError("inn", "INN is required")
    
    # INN must be exactly 10 or 12 digits
    if not re.match(r'^\d{10}$|^\d{12}$', inn):
        raise ValidationError(
            "inn",
            "Invalid INN format. Must be exactly 10 or 12 digits."
        )
    
    return True


def validate_key_number(key_number: str) -> bool:
    """
    Validate GRAND-Smeta key number format.
    
    Key numbers must match the pattern: 2 uppercase letters followed by 6 digits.
    Example: MG123456
    
    Args:
        key_number: Key number string to validate
    
    Returns:
        True if valid
    
    Raises:
        ValidationError: If key number format is invalid
    
    Examples:
        >>> validate_key_number("MG123456")
        True
        >>> validate_key_number("AB999999")
        True
        >>> validate_key_number("mg123456")
        ValidationError: key_number: Invalid key number format
        >>> validate_key_number("M123456")
        ValidationError: key_number: Invalid key number format
    """
    if not key_number:
        raise ValidationError("key_number", "Key number is required")
    
    # Key format: 2 uppercase letters + 6 digits
    if not re.match(r'^[A-Z]{2}\d{6}$', key_number):
        raise ValidationError(
            "key_number",
            "Invalid key number format. Must be 2 uppercase letters followed by 6 digits (e.g., MG123456)."
        )
    
    return True


def validate_email(email: str) -> bool:
    """
    Validate email address format.
    
    Uses a simplified regex pattern that covers most common email formats.
    
    Args:
        email: Email address string to validate
    
    Returns:
        True if valid
    
    Raises:
        ValidationError: If email format is invalid
    
    Examples:
        >>> validate_email("user@example.com")
        True
        >>> validate_email("user.name+tag@example.co.uk")
        True
        >>> validate_email("invalid.email")
        ValidationError: email: Invalid email format
    """
    if not email:
        raise ValidationError("email", "Email is required")
    
    # Simplified email regex pattern
    # Matches: local-part@domain.tld
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if not re.match(email_pattern, email):
        raise ValidationError(
            "email",
            "Invalid email format. Must be in format: user@example.com"
        )
    
    return True


def validate_escalation_level(level: int) -> bool:
    """
    Validate escalation level value.
    
    Escalation level must be 0, 1, or 2.
    
    Args:
        level: Escalation level integer
    
    Returns:
        True if valid
    
    Raises:
        ValidationError: If escalation level is invalid
    """
    if level not in (0, 1, 2):
        raise ValidationError(
            "escalation_level",
            "Invalid escalation level. Must be 0 (primary), 1 (backup1), or 2 (backup2)."
        )
    
    return True


def safe_validate_phone_number(phone_number: Optional[str]) -> tuple[bool, Optional[str]]:
    """
    Safely validate phone number without raising exceptions.
    
    Args:
        phone_number: Phone number string to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    
    Examples:
        >>> safe_validate_phone_number("+79991234567")
        (True, None)
        >>> safe_validate_phone_number("123")
        (False, "phone_number: Invalid phone number format...")
    """
    try:
        validate_phone_number(phone_number)
        return True, None
    except ValidationError as e:
        return False, str(e)


def safe_validate_inn(inn: Optional[str]) -> tuple[bool, Optional[str]]:
    """
    Safely validate INN without raising exceptions.
    
    Args:
        inn: INN string to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        validate_inn(inn)
        return True, None
    except ValidationError as e:
        return False, str(e)


def safe_validate_key_number(key_number: Optional[str]) -> tuple[bool, Optional[str]]:
    """
    Safely validate key number without raising exceptions.
    
    Args:
        key_number: Key number string to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        validate_key_number(key_number)
        return True, None
    except ValidationError as e:
        return False, str(e)


def safe_validate_email(email: Optional[str]) -> tuple[bool, Optional[str]]:
    """
    Safely validate email without raising exceptions.
    
    Args:
        email: Email address string to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        validate_email(email)
        return True, None
    except ValidationError as e:
        return False, str(e)


def validate_user_data(
    phone_number: str,
    username: Optional[str] = None,
    email: Optional[str] = None
) -> dict[str, str]:
    """
    Validate multiple user fields at once.
    
    Args:
        phone_number: Phone number to validate
        username: Optional username to validate
        email: Optional email to validate
    
    Returns:
        Dictionary of field errors (empty if all valid)
    
    Example:
        >>> errors = validate_user_data("+79991234567", email="user@example.com")
        >>> if errors:
        ...     print(f"Validation failed: {errors}")
    """
    errors = {}
    
    # Validate phone number
    is_valid, error = safe_validate_phone_number(phone_number)
    if not is_valid:
        errors['phone_number'] = error
    
    # Validate email if provided
    if email:
        is_valid, error = safe_validate_email(email)
        if not is_valid:
            errors['email'] = error
    
    return errors


def validate_organization_data(inn: str, organization_name: Optional[str] = None) -> dict[str, str]:
    """
    Validate organization fields.
    
    Args:
        inn: INN to validate
        organization_name: Optional organization name
    
    Returns:
        Dictionary of field errors (empty if all valid)
    """
    errors = {}
    
    # Validate INN
    is_valid, error = safe_validate_inn(inn)
    if not is_valid:
        errors['inn'] = error
    
    return errors


def validate_key_data(key_number: str) -> dict[str, str]:
    """
    Validate GS key fields.
    
    Args:
        key_number: Key number to validate
    
    Returns:
        Dictionary of field errors (empty if all valid)
    """
    errors = {}
    
    # Validate key number
    is_valid, error = safe_validate_key_number(key_number)
    if not is_valid:
        errors['key_number'] = error
    
    return errors


def validate_ticket_data(
    delivery_method: str,
    delivery_email: Optional[str] = None,
    escalation_level: int = 0
) -> dict[str, str]:
    """
    Validate ticket fields.
    
    Args:
        delivery_method: Delivery method (telegram, email, none)
        delivery_email: Email address if delivery_method is email
        escalation_level: Escalation level (0, 1, or 2)
    
    Returns:
        Dictionary of field errors (empty if all valid)
    """
    errors = {}
    
    # Validate delivery email if method is email
    if delivery_method == 'email':
        if not delivery_email:
            errors['delivery_email'] = "Email address is required when delivery method is email"
        else:
            is_valid, error = safe_validate_email(delivery_email)
            if not is_valid:
                errors['delivery_email'] = error
    
    # Validate escalation level
    try:
        validate_escalation_level(escalation_level)
    except ValidationError as e:
        errors['escalation_level'] = str(e)
    
    return errors
