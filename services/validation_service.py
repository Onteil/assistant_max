"""
Validation Service

Provides validation functions for user input data.
Validates phone numbers, INN, GS_Key, and email formats.
Provides file type classification for attachments.

Requirements: 21.1-21.5, 22.1-22.5, 23.1-23.5, 24.1-24.5, 15.6, 15.7, 15.8
"""

import re
from database.models import FileType


def validate_phone_number(phone: str) -> tuple[bool, str | None]:
    """
    Validates phone number format.
    
    Accepts:
    - E.164 format: +79991234567
    - Russian format: 89991234567
    
    Returns:
        tuple[bool, str | None]: (is_valid, normalized_phone or error_message)
        - If valid: (True, normalized_phone in E.164 format)
        - If invalid: (False, error_message)
    
    Requirements: 21.1, 21.2, 21.3, 21.4, 21.5
    """
    if not phone:
        return False, "Номер телефона не может быть пустым"
    
    # Remove whitespace
    phone = phone.strip()
    
    # Remove all non-digit characters except leading +
    if phone.startswith("+"):
        digits = phone[1:]
        has_plus = True
    else:
        digits = phone
        has_plus = False
    
    # Extract only digits
    digits_only = ''.join(c for c in digits if c.isdigit())
    
    # Check length constraints
    if len(digits_only) < 10:
        return False, "Номер телефона должен содержать минимум 10 цифр"
    
    if len(digits_only) > 15:
        return False, "Номер телефона должен содержать максимум 15 цифр"
    
    # Normalize to E.164 format
    if has_plus:
        # Already has +, just use digits
        normalized = f"+{digits_only}"
    elif digits_only.startswith("8") and len(digits_only) == 11:
        # Russian format 89991234567 -> +79991234567
        normalized = f"+7{digits_only[1:]}"
    elif digits_only.startswith("7") and len(digits_only) == 11:
        # Already in format 79991234567 -> +79991234567
        normalized = f"+{digits_only}"
    else:
        # Assume international format, add +
        normalized = f"+{digits_only}"
    
    return True, normalized


def validate_inn(inn: str) -> tuple[bool, str | None]:
    """
    Validates INN (Russian tax identification number) format.
    
    Accepts:
    - 10 digits (organization INN)
    - 12 digits (individual entrepreneur INN)
    
    Returns:
        tuple[bool, str | None]: (is_valid, error_message)
        - If valid: (True, None)
        - If invalid: (False, error_message)
    
    Requirements: 22.1, 22.2, 22.3, 22.4, 22.5
    """
    if not inn:
        return False, "ИНН не может быть пустым"
    
    # Trim whitespace
    inn = inn.strip()
    
    # Check if contains only digits
    if not inn.isdigit():
        return False, "ИНН должен содержать только цифры"
    
    # Check length
    if len(inn) not in [10, 12]:
        return False, "ИНН должен содержать ровно 10 или 12 цифр"
    
    return True, None


def validate_gs_key(key: str) -> tuple[bool, str | None]:
    """
    Validates GS_Key (GRAND-Smeta license key) format.
    
    Expected format: [A-Z]{2}[0-9]{6}
    Example: MG123456
    
    Returns:
        tuple[bool, str | None]: (is_valid, normalized_key or error_message)
        - If valid: (True, normalized_key in uppercase)
        - If invalid: (False, error_message)
    
    Requirements: 23.1, 23.2, 23.3, 23.4, 23.5
    """
    if not key:
        return False, "Номер ключа не может быть пустым"
    
    # Trim whitespace and convert to uppercase
    key = key.strip().upper()
    
    # Validate format: 2 letters + 6 digits
    pattern = r'^[A-Z]{2}[0-9]{6}$'
    
    if not re.match(pattern, key):
        return False, "Неверный формат ключа. Ожидается формат: MG123456 (2 буквы + 6 цифр)"
    
    return True, key


def validate_email(email: str) -> tuple[bool, str | None]:
    """
    Validates email address format.
    
    Returns:
        tuple[bool, str | None]: (is_valid, error_message)
        - If valid: (True, None)
        - If invalid: (False, error_message)
    
    Requirements: 24.1, 24.2, 24.3, 24.4, 24.5
    """
    if not email:
        return False, "Email не может быть пустым"
    
    # Trim whitespace
    email = email.strip()
    
    # Check for @ symbol
    if "@" not in email:
        return False, "Email должен содержать символ @"
    
    # Split into local part and domain
    parts = email.split("@")
    
    if len(parts) != 2:
        return False, "Email должен содержать только один символ @"
    
    local_part, domain = parts
    
    # Check local part is not empty
    if not local_part:
        return False, "Email должен содержать локальную часть перед @"
    
    # Check domain is not empty
    if not domain:
        return False, "Email должен содержать домен после @"
    
    # Check domain has extension
    if "." not in domain:
        return False, "Email должен содержать доменное расширение (например, .ru, .com)"
    
    # Basic regex validation
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if not re.match(pattern, email):
        return False, "Неверный формат email адреса"
    
    return True, None



def classify_file_type(file_name: str | None) -> FileType:
    """
    Classify file type based on file name extension.
    
    Classifies files into categories:
    - PDF: .pdf files
    - IMAGE: .jpg, .jpeg, .png, .gif, .bmp, .webp files
    - DOCUMENT: .doc, .docx, .xls, .xlsx, .txt, .rtf files
    - OTHER: all other file types
    
    Args:
        file_name: File name with extension (can be None)
    
    Returns:
        FileType enum value (PDF, IMAGE, DOCUMENT, or OTHER)
    
    Requirements: 15.6, 15.7, 15.8
    """
    if not file_name:
        return FileType.OTHER
    
    # Normalize to lowercase for comparison
    file_name_lower = file_name.lower()
    
    # PDF files
    if file_name_lower.endswith('.pdf'):
        return FileType.PDF
    
    # Image files
    image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.ico')
    if file_name_lower.endswith(image_extensions):
        return FileType.IMAGE
    
    # Document files
    document_extensions = ('.doc', '.docx', '.xls', '.xlsx', '.txt', '.rtf', '.odt', '.ods')
    if file_name_lower.endswith(document_extensions):
        return FileType.DOCUMENT
    
    # All other file types
    return FileType.OTHER
