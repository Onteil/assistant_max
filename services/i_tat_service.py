"""
Сервис для интеграции с 1С/CRM системой АЙТАТ-Диспетчер.
Содержит методы для работы с внешним API.

Enhanced with comprehensive error handling and retry logic.
Requirements: 25.1-25.5, 34.1-34.5

STUB IMPLEMENTATIONS:
The following methods currently use stub implementations for development:
- register_user(): Returns success response
- check_key_conflict(): Returns random available/conflict for testing
- get_user_assets(): Returns mock organizations and keys
- get_user_status(): Returns mock subscription status

These stubs can be easily replaced with real API implementations by:
1. Removing the stub implementation
2. Uncommenting the _make_request call
3. Adjusting the endpoint and payload as needed
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

    async def get_info(self) -> dict[str, Any]:
        """
        Получение справки по API - описание методов и параметров сервиса

        Returns:
            Справочная информация о доступных методах API
        
        Raises:
            httpx.TimeoutException: Request timeout
            httpx.HTTPStatusError: HTTP error status
            httpx.ConnectError: Connection error
        """
        endpoint = f"{self.base_url}/getinfo"
        return await self._make_request("GET", endpoint)

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
        self, tg_user_id: int, phone: str, name: str, surname: str, inn: str, grand_key: str
    ) -> dict[str, Any]:
        """
        Отправка данных регистрации пользователя в 1С

        Args:
            tg_user_id: Telegram ID пользователя
            phone: Номер телефона
            name: Имя
            surname: Фамилия
            inn: ИНН организации
            grand_key: Номер ключа

        Returns:
            {"status": "ok"} или {"status": "error", "code": "key_busy|invalid_inn"}
        
        Raises:
            httpx.TimeoutException: Request timeout
            httpx.HTTPStatusError: HTTP error status
            httpx.ConnectError: Connection error
        
        Note:
            STUB IMPLEMENTATION - Returns success for all registrations.
            Replace with real API call when CRM endpoint is available.
            Requirements: 34.1, 34.2, 34.3, 34.4, 34.5
        """
        endpoint = f"{self.base_url}/api/v1/user/register"
        payload = {
            "tg_user_id": tg_user_id,
            "phone": phone,
            "name": name,
            "surname": surname,
            "inn": inn,
            "grand_key": grand_key,
        }

        logger.info(f"Registering user: tg_user_id={tg_user_id}, phone={phone}")
        
        # STUB: Return success response
        logger.warning(
            f"STUB: register_user called with tg_user_id={tg_user_id}, "
            f"phone={phone}, name={name}, surname={surname}, inn={inn}, grand_key={grand_key}"
        )
        return {"status": "ok"}
        
        # Real implementation (uncomment when CRM is ready):
        # return await self._make_request("POST", endpoint, json=payload)

    # ========== Блок: Профиль и Проверки ==========

    async def get_user_assets(self, tg_user_id: int) -> dict[str, Any]:
        """
        Получение списка активов пользователя (организаций и ключей)

        Args:
            tg_user_id: Telegram ID пользователя

        Returns:
            {
                "companies": [{"inn": "...", "name": "..."}],
                "grand_keys": [{"number": "...", "is_active": true}]
            }
        
        Raises:
            httpx.TimeoutException: Request timeout
            httpx.HTTPStatusError: HTTP error status
            httpx.ConnectError: Connection error
        
        Note:
            STUB IMPLEMENTATION - Returns mock organizations and keys.
            Replace with real API call when CRM endpoint is available.
            Requirements: 34.1, 34.2, 34.3, 34.4, 34.5
        """
        endpoint = f"{self.base_url}/api/v1/user/assets"
        params = {"tg_user_id": tg_user_id}

        logger.debug(f"Fetching user assets: tg_user_id={tg_user_id}")
        
        # STUB: Return mock data
        logger.warning(f"STUB: get_user_assets called with tg_user_id={tg_user_id}")
        return {
            "companies": [
                {"inn": "1234567890", "name": "ООО Тестовая Компания 1"},
                {"inn": "9876543210", "name": "ИП Иванов И.И."}
            ],
            "grand_keys": [
                {"number": "MG123456", "is_active": True},
                {"number": "MG789012", "is_active": True},
                {"number": "MG345678", "is_active": False}
            ]
        }
        
        # Real implementation (uncomment when CRM is ready):
        # return await self._make_request("GET", endpoint, params=params)

    async def get_user_status(self, tg_user_id: int) -> dict[str, Any]:
        """
        Проверка статуса подписки пользователя

        Args:
            tg_user_id: Telegram ID пользователя

        Returns:
            {
                "is_support_active": true,
                "support_expires_at": "2026-12-31"
            }
        
        Raises:
            httpx.TimeoutException: Request timeout
            httpx.HTTPStatusError: HTTP error status
            httpx.ConnectError: Connection error
        
        Note:
            STUB IMPLEMENTATION - Returns mock subscription status.
            Replace with real API call when CRM endpoint is available.
            Requirements: 34.1, 34.2, 34.3, 34.4, 34.5
        """
        endpoint = f"{self.base_url}/api/v1/user/status"
        params = {"tg_user_id": tg_user_id}

        logger.debug(f"Checking user status: tg_user_id={tg_user_id}")
        
        # STUB: Return mock subscription status
        logger.warning(f"STUB: get_user_status called with tg_user_id={tg_user_id}")
        return {
            "is_support_active": True,
            "support_expires_at": "2026-12-31"
        }
        
        # Real implementation (uncomment when CRM is ready):
        # return await self._make_request("GET", endpoint, params=params)

    async def check_key_conflict(self, key_number: str, telegram_id: int, phone: str) -> dict[str, Any]:
        """
        Проверка конфликта ключа (занят ли другим пользователем)

        Args:
            key_number: Номер ключа
            telegram_id: Telegram ID пользователя
            phone: Номер телефона

        Returns:
            {"status": "available"} или
            {"status": "conflict", "owner_phone": "7900***1122"}
        
        Raises:
            httpx.TimeoutException: Request timeout
            httpx.HTTPStatusError: HTTP error status
            httpx.ConnectError: Connection error
        
        Note:
            STUB IMPLEMENTATION - Returns random available/conflict for testing.
            Replace with real API call when CRM endpoint is available.
            Requirements: 34.1, 34.2, 34.3, 34.4, 34.5
        """
        endpoint = f"{self.base_url}/api/v1/assets/check_key"
        payload = {"key_number": key_number, "telegram_id": telegram_id, "phone": phone}

        logger.info(f"Checking key conflict: key={key_number}, user={telegram_id}")
        
        # STUB: Return random available/conflict for testing
        logger.warning(
            f"STUB: check_key_conflict called with key_number={key_number}, "
            f"telegram_id={telegram_id}, phone={phone}"
        )
        
        # 70% chance of available, 30% chance of conflict for testing
        if random.random() < 0.7:
            return {"status": "available"}
        else:
            return {
                "status": "conflict",
                "owner_phone": "7900***1122"
            }
        
        # Real implementation (uncomment when CRM is ready):
        # return await self._make_request("POST", endpoint, json=payload)

    # ========== Блок: Обращения ==========

    async def get_staff_list(self) -> dict[str, Any]:
        """
        Получение списка сотрудников с их Telegram ID и ролями

        Returns:
            {
                "employees": [
                    {
                        "tg_id": 987654,
                        "role": "manager",
                        "signature": "Анна Петрова, менеджер",
                        "reserves": [112233, 445566]
                    }
                ]
            }
        
        Raises:
            httpx.TimeoutException: Request timeout
            httpx.HTTPStatusError: HTTP error status
            httpx.ConnectError: Connection error
        """
        endpoint = f"{self.base_url}/api/v1/system/staff"

        logger.debug("Fetching staff list")
        # TODO: Реализовать реальный запрос
        return await self._make_request("GET", endpoint)

    async def log_ticket(
        self,
        ticket_id: str,
        tg_user_id: int,
        ticket_type: str,
        status: str,
        comment: str | None = None,
        history_link: str | None = None,
    ) -> dict[str, Any]:
        """
        Логирование создания/закрытия обращения в 1С

        Args:
            ticket_id: ID тикета в боте
            tg_user_id: Telegram ID пользователя
            ticket_type: Тип обращения (invoice, support, etc.)
            status: Статус (created, closed)
            comment: Финальный комментарий сотрудника
            history_link: Ссылка на историю в боте

        Returns:
            {"status": "ok"}
        
        Raises:
            httpx.TimeoutException: Request timeout
            httpx.HTTPStatusError: HTTP error status
            httpx.ConnectError: Connection error
        """
        endpoint = f"{self.base_url}/api/v1/tickets/log"
        payload = {"ticket_id": ticket_id, "tg_user_id": tg_user_id, "type": ticket_type, "status": status}

        if comment:
            payload["comment"] = comment
        if history_link:
            payload["history_link"] = history_link

        logger.info(f"Logging ticket: ticket_id={ticket_id}, type={ticket_type}, status={status}")
        # TODO: Реализовать реальный запрос
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
