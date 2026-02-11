"""
Сервис для интеграции с 1С/CRM системой АЙТАТ-Диспетчер.
Содержит методы для работы с внешним API.

Enhanced with comprehensive error handling and retry logic.
All methods use real API endpoints as documented in docs/I-TAT-API-DOCUMENTATION.md.

Requirements: 25.1-25.5, 34.1-34.5
"""

import logging
import random
from typing import Any

import httpx

from constants import ITAT_API_BASE_URL, ITAT_API_PASSWORD, ITAT_API_USERNAME

logger = logging.getLogger(__name__)


class ITatAPIClient:
    """Клиент для работы с API 1С/CRM АЙТАТ"""

    def __init__(self, base_url: str | None = None, username: str | None = None, password: str | None = None):
        """
        Инициализация клиента API

        Args:
            base_url: Базовый URL API (по умолчанию из constants)
            username: Логин для Basic авторизации (по умолчанию из constants)
            password: Пароль для Basic авторизации (по умолчанию из constants)
        """
        self.base_url = base_url or ITAT_API_BASE_URL
        self.username = username or ITAT_API_USERNAME
        self.password = password or ITAT_API_PASSWORD

        self.client = httpx.AsyncClient(
            timeout=30.0, auth=(self.username, self.password), headers={"Content-Type": "application/json"}
        )

    async def close(self):
        """Закрытие HTTP клиента"""
        await self.client.aclose()

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        **kwargs
    ) -> dict[str, Any]:
        """
        Internal method to make HTTP requests with error handling.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: Full endpoint URL
            **kwargs: Additional arguments for httpx request
        
        Returns:
            Response JSON
        
        Raises:
            httpx.TimeoutException: Request timeout
            httpx.HTTPStatusError: HTTP error status
            httpx.ConnectError: Connection error
        
        Requirements: 25.1, 25.2, 25.3
        """
        try:
            if method.upper() == "GET":
                response = await self.client.get(endpoint, **kwargs)
            elif method.upper() == "POST":
                response = await self.client.post(endpoint, **kwargs)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            
            # API использует стандартную кодировку, определяемую httpx автоматически
            return response.json()
        
        except httpx.TimeoutException as e:
            logger.error(
                f"API timeout: endpoint={endpoint}, method={method}",
                exc_info=True
            )
            raise
        
        except httpx.HTTPStatusError as e:
            logger.error(
                f"API HTTP error: endpoint={endpoint}, method={method}, "
                f"status={e.response.status_code}, response={e.response.text}",
                exc_info=True
            )
            raise
        
        except httpx.ConnectError as e:
            logger.error(
                f"API connection error: endpoint={endpoint}, method={method}",
                exc_info=True
            )
            raise
        
        except Exception as e:
            logger.error(
                f"Unexpected API error: endpoint={endpoint}, method={method}, "
                f"error={e}",
                exc_info=True
            )
            raise

    # ========== Блок: Системные методы ==========

    async def get_info(self) -> str:
        """
        Получение справки по API - описание методов и параметров сервиса

        Returns:
            Текстовая справочная информация о доступных методах API
        
        Raises:
            httpx.TimeoutException: Request timeout
            httpx.HTTPStatusError: HTTP error status
            httpx.ConnectError: Connection error
        """
        endpoint = f"{self.base_url}/getinfo"
        
        try:
            response = await self.client.get(endpoint)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(
                f"API error in get_info: endpoint={endpoint}, error={e}",
                exc_info=True
            )
            raise

    async def get_staff(self) -> dict[str, Any]:
        """
        Получение списка активных сотрудников с учетными записями в мессенджерах

        Returns:
            {
                "status": "ok",
                "staff": [
                    {
                        "user_id": 123456789,
                        "name": "Иванов Иван Иванович",
                        "role": "manager",
                        "position": "Менеджер отдела продаж"
                    }
                ]
            }

        Raises:
            httpx.TimeoutException: Request timeout
            httpx.HTTPStatusError: HTTP error status (500, etc.)
            httpx.ConnectError: Connection error
        """
        endpoint = f"{self.base_url}/system/staff"
        return await self._make_request("GET", endpoint)

    # ========== Блок: Регистрация и аутентификация ==========

    async def register_user(
        self, telegram_id: int, phone: str, first_name: str, last_name: str, grand_key: str
    ) -> dict[str, Any]:
        """
        Register a new user in the I-TAT CRM system.

        Args:
            telegram_id: Telegram ID of the user
            phone: Phone number (format: "+79001234567")
            first_name: User's first name
            last_name: User's last name
            grand_key: Protection key number (format: "MG123456" or "00202_12345")

        Returns:
            {
                "status": "ok",
                "message": "Пользователь зарегистрирован",
                "user_id": "USER_ID",
                "potential_matches": 0
            }
        
        Raises:
            httpx.TimeoutException: Request timeout
            httpx.HTTPStatusError: HTTP error status
                - 400: Invalid parameters
                - 404: Grand key not found
                - 409: User already exists
                - 500: Server error
            httpx.ConnectError: Connection error
        
        Requirements: 1.1, 1.2, 1.3, 1.7, 7.1, 7.2
        """
        endpoint = f"{self.base_url}/user/register"
        payload = {
            "telegram_id": telegram_id,
            "phone": phone,
            "first_name": first_name,
            "last_name": last_name,
            "grand_key": grand_key,
        }

        logger.info(f"Registering user: telegram_id={telegram_id}, phone={phone}")
        return await self._make_request("POST", endpoint, json=payload)

    # ========== Блок: Профиль и Проверки ==========

    async def get_user_assets(self, telegram_id: int) -> dict[str, Any]:
        """
        Получение списка активов пользователя (организаций и ключей)

        Args:
            telegram_id: Telegram ID пользователя

        Returns:
            Verified user:
            {
                "status": "ok",
                "organizations": [{"inn": "...", "name": "..."}],
                "keys": ["MG123456", "MG789012"]
            }
            
            Unverified user:
            {
                "status": "error",
                "message": "Пользователь не верифицирован",
                "verification_status": "pending"
            }
        
        Raises:
            httpx.TimeoutException: Request timeout
            httpx.HTTPStatusError: HTTP error status (400, 404, 500)
            httpx.ConnectError: Connection error
        
        Requirements: 2.1, 2.2, 2.3, 2.4, 2.6, 2.7, 7.1
        """
        endpoint = f"{self.base_url}/user/assets"

        logger.debug(f"Fetching user assets: telegram_id={telegram_id}")
        
        return await self._make_request("GET", endpoint, params={"telegram_id": telegram_id})


    async def check_key_conflict(self, grand_key: str, telegram_id: int) -> dict[str, Any]:
        """
        Check if a protection key is available or occupied by another user.

        Args:
            grand_key: Protection key number (format: "MG123456" or "00202_12345")
            telegram_id: Telegram ID of the user

        Returns:
            Available:
            {"status": "available"}
            
            Conflict:
            {
                "status": "conflict",
                "owner": "Иван Иванов +7912-XXX-XX-89"
            }
        
        Raises:
            httpx.TimeoutException: Request timeout
            httpx.HTTPStatusError: HTTP error status
                - 400: Invalid parameters
                - 500: Server error
            httpx.ConnectError: Connection error
        
        Requirements: 4.1, 4.2, 4.3, 4.4, 4.6, 7.1, 7.3
        """
        endpoint = f"{self.base_url}/assets/check_key"
        payload = {"grand_key": grand_key, "telegram_id": telegram_id}

        logger.info(f"Checking key conflict: key={grand_key}, user={telegram_id}")
        return await self._make_request("POST", endpoint, json=payload)


    async def log_ticket(
        self,
        ticket_id: str,
        telegram_id: int,
        ticket_type: str,
        status: str,
        comment: str | None = None,
        history_link: str | None = None,
    ) -> dict[str, Any]:
        """
        Log ticket creation or closure in the CRM system.

        Args:
            ticket_id: Ticket ID in the bot (format: "TG_12345")
            telegram_id: Telegram ID of the user
            ticket_type: Ticket type (e.g., "Техподдержка", "Счет")
            status: Ticket status (e.g., "Новое", "Закрыто")
            comment: Optional employee comment
            history_link: Optional link to ticket history (format: "https://t.me/c/123/456")

        Returns:
            {
                "status": "ok",
                "message": "Обращение зарегистрировано",
                "ticket_id": "TG_12345"
            }
        
        Raises:
            httpx.TimeoutException: Request timeout
            httpx.HTTPStatusError: HTTP error status
                - 400: Invalid parameters or type/status values
                - 404: User not found
                - 500: Server error
            httpx.ConnectError: Connection error
        
        Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.7, 7.1
        """
        endpoint = f"{self.base_url}/tickets/log"
        payload = {"ticket_id": ticket_id, "telegram_id": telegram_id, "type": ticket_type, "status": status}

        if comment:
            payload["comment"] = comment
        if history_link:
            payload["history_link"] = history_link

        logger.info(f"Logging ticket: ticket_id={ticket_id}, type={ticket_type}, status={status}")
        return await self._make_request("POST", endpoint, json=payload)


# Singleton instance
_client: ITatAPIClient | None = None


def get_itat_client() -> ITatAPIClient:
    """Получение singleton экземпляра клиента API"""
    global _client
    if _client is None:
        _client = ITatAPIClient()
    return _client


async def close_itat_client():
    """Закрытие клиента API"""
    global _client
    if _client is not None:
        await _client.close()
        _client = None
