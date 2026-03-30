"""
Сервис для интеграции с 1С/CRM системой АЙТАТ-Диспетчер.
Содержит методы для работы с внешним API.

Enhanced with comprehensive error handling and retry logic.
All methods use real API endpoints as documented in docs/I-TAT-API-DOCUMENTATION.md.

Requirements: 25.1-25.5, 34.1-34.5
"""

import asyncio
import logging
import os
import random
from typing import Any

import httpx

from constants import ITAT_API_BASE_URL, ITAT_API_PASSWORD, ITAT_API_USERNAME
from constants import LOCAL_DEV, ITAT_SSH_HOST, ITAT_SSH_SOCKS5_PORT

logger = logging.getLogger(__name__)

# Режим заглушек (включается через переменную окружения)
USE_MOCK_API = os.getenv("USE_MOCK_ITAT_API", "false").lower() == "true"


class RetryableAPIError(Exception):
    """
    Transient i-TAT API error that should be retried.

    Raised for: connection errors, timeouts, 5xx server errors.
    These are temporary failures where retrying may succeed.
    """

    def __init__(self, message: str, original_error: Exception | None = None):
        super().__init__(message)
        self.original_error = original_error


class NonRetryableAPIError(Exception):
    """
    Permanent i-TAT API error that should NOT be retried.

    Raised for: 4xx client errors (400, 404, 409, 422).
    These indicate a logic/data problem — retrying won't help.
    """

    def __init__(self, message: str, status_code: int | None = None, original_error: Exception | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.original_error = original_error


class ITatAPIClient:
    """Клиент для работы с API 1С/CRM АЙТАТ"""

    def __init__(self, base_url: str | None = None, username: str | None = None, password: str | None = None, use_mock: bool | None = None):
        """
        Инициализация клиента API

        Args:
            base_url: Базовый URL API (по умолчанию из constants)
            username: Логин для Basic авторизации (по умолчанию из constants)
            password: Пароль для Basic авторизации (по умолчанию из constants)
            use_mock: Использовать заглушки вместо реальных API вызовов (по умолчанию из USE_MOCK_API)
        """
        self.base_url = base_url or ITAT_API_BASE_URL
        self.username = username or ITAT_API_USERNAME
        self.password = password or ITAT_API_PASSWORD
        self.use_mock = use_mock if use_mock is not None else USE_MOCK_API

        # При LOCAL_DEV=true направляем трафик через SSH SOCKS5 туннель.
        # Предварительно: 1) подключиться к PPTP VPN (ITAT_VPN_HOST)
        #                  2) запустить туннель: ssh -D <port> -N <login>@<ssh_host>
        client_kwargs: dict[str, Any] = {
            "timeout": 30.0,
            "auth": (self.username, self.password),
            "headers": {"Content-Type": "application/json"},
        }
        if LOCAL_DEV and ITAT_SSH_HOST:
            socks5_url = f"socks5://{ITAT_SSH_HOST}:{ITAT_SSH_SOCKS5_PORT}"
            client_kwargs["proxy"] = socks5_url
            logger.info(f"LOCAL_DEV: i-TAT requests routed via SOCKS5 proxy {socks5_url}")

        self.client = httpx.AsyncClient(**client_kwargs)

    async def close(self):
        """Закрытие HTTP клиента"""
        await self.client.aclose()

    # ========== Блок: Заглушки API ==========

    async def _mock_check_key_conflict(self, grand_key: str, user_id: int | None = None) -> dict[str, Any]:
        """Заглушка для проверки конфликта ключа"""
        logger.info(f"[MOCK] Checking key conflict: key={grand_key}, user={user_id}")
        
        # Имитация конфликта для ключа 00000_00001
        if grand_key == "00000_00001":
            return {
                "status": "conflict",
                "owner": "Петров Петр +7912-XXX-XX-45"
            }
        
        # Для всех остальных ключей - доступен
        return {"status": "available"}

    async def _mock_register_user(
        self,
        user_id: int,
        phone: str,
        name: str | None,
        surname: str | None,
        grand_key: str
    ) -> dict[str, Any]:
        """Заглушка для регистрации пользователя"""
        logger.info(f"[MOCK] Registering user: user_id={user_id}, phone={phone}, key={grand_key}")
        
        # Имитация успешной регистрации
        return {
            "status": "ok",
            "message": "Пользователь зарегистрирован",
            "user_id": user_id,
            "potential_matches": 0
        }

    async def _mock_get_user_assets(self, user_id: int) -> dict[str, Any]:
        """Заглушка для получения активов пользователя"""
        logger.info(f"[MOCK] Fetching user assets: user_id={user_id}")
        
        # Имитация неверифицированного пользователя
        return {
            "status": "error",
            "message": "Пользователь не верифицирован",
            "verification_status": "pending"
        }

    async def _mock_log_ticket(
        self,
        ticket_id: str,
        user_id: int,
        ticket_type: str,
        status: str,
        comment: str | None,
        history_link: str | None
    ) -> dict[str, Any]:
        """Заглушка для логирования тикета"""
        logger.info(f"[MOCK] Logging ticket: ticket_id={ticket_id}, type={ticket_type}, status={status}")
        
        return {
            "status": "ok",
            "message": "Обращение зарегистрировано",
            "ticket_id": ticket_id
        }

    async def _mock_approve_user_registration(
        self,
        user_id: int,
        phone: str,
        inn_list: list[str],
        gs_key_list: list[str]
    ) -> dict[str, Any]:
        """Заглушка для одобрения регистрации"""
        logger.info(f"[MOCK] Approving user registration: user_id={user_id}, phone={phone}")
        
        return {
            "status": "ok",
            "message": "Регистрация одобрена",
            "user_id": user_id
        }

    async def _mock_reject_user_registration(
        self,
        user_id: int,
        phone: str,
        rejection_reason: str
    ) -> dict[str, Any]:
        """Заглушка для отклонения регистрации"""
        logger.info(f"[MOCK] Rejecting user registration: user_id={user_id}, phone={phone}")
        
        return {
            "status": "ok",
            "message": "Регистрация отклонена",
            "user_id": user_id
        }

    async def _mock_get_staff(self) -> dict[str, Any]:
        """Заглушка для получения списка сотрудников"""
        logger.info("[MOCK] Fetching staff list")
        
        return {
            "status": "ok",
            "staff": [
                {
                    "user_id": 123456789,
                    "name": "Иванов Иван Иванович",
                    "role": "manager",
                    "position": "Менеджер отдела продаж",
                    "reserves": [987654321, 111222333]
                }
            ]
        }

    async def _mock_transfer_gs_key(
        self,
        old_user_id: int,
        new_user_id: int,
        key_number: str
    ) -> dict[str, Any]:
        """Заглушка для передачи ключа"""
        logger.info(f"[MOCK] Transferring GS_Key: key={key_number}, old_user={old_user_id}, new_user={new_user_id}")
        
        return {
            "status": "ok",
            "message": "Ключ передан",
            "key_number": key_number,
            "old_user_id": old_user_id,
            "new_user_id": new_user_id
        }

    # ========== Заглушки для новых методов ==========

    async def _mock_check_inn(self, messenger: str, user_id: int | None, inn: str) -> dict[str, Any]:
        """Заглушка для проверки ИНН"""
        logger.info(f"[MOCK] Checking INN: inn={inn}, user={user_id}, messenger={messenger}")
        return {"status": "ok", "message": "ИНН доступен"}

    async def _mock_update_user_assets(
        self, messenger: str, user_id: int, asset_type: str, action: str, value: str
    ) -> dict[str, Any]:
        """Заглушка для обновления активов пользователя"""
        logger.info(f"[MOCK] Updating user assets: user={user_id}, type={asset_type}, action={action}, value={value}")
        return {"status": "success", "message": "Ассет успешно привязан/удален"}

    async def _mock_update_staff(
        self, messenger: str, user_id: int, action: str, **kwargs
    ) -> dict[str, Any]:
        """Заглушка для обновления сотрудника"""
        logger.info(f"[MOCK] Updating staff: user={user_id}, action={action}, messenger={messenger}")
        return {"status": "ok", "message": "Сотрудник обновлен"}


    async def _mock_change_phone(
        self, messenger: str, user_id: int, old_phone: str, new_phone: str, staff_id: int
    ) -> dict[str, Any]:
        """Заглушка для смены номера телефона"""
        logger.info(f"[MOCK] Changing phone: user={user_id}, old={old_phone}, new={new_phone}")
        return {"status": "ok", "message": "Номер телефона изменен"}

    async def _mock_audit_log(self, messenger: str, action_type: str, **kwargs) -> dict[str, Any]:
        """Заглушка для аудит лога"""
        logger.info(f"[MOCK] Audit log: action={action_type}, messenger={messenger}")
        return {"status": "ok", "message": "Событие записано"}

    async def _mock_get_ticket_history(self, ticket_id: str) -> dict[str, Any]:
        """Заглушка для истории тикета"""
        logger.info(f"[MOCK] Getting ticket history: ticket_id={ticket_id}")
        return {"status": "ok", "history": [{"action": "created", "timestamp": "2026-03-18T10:00:00Z"}]}

    async def _mock_resolve_conflict(
        self, key_number: str, action: str, new_user_phone: str, old_user_phone: str, **kwargs
    ) -> dict[str, Any]:
        """Заглушка для разрешения конфликта ключа"""
        logger.info(f"[MOCK] Resolving key conflict: key={key_number}, action={action}")
        if action == "transfer":
            return {"status": "ok", "message": "Ключ успешно перенесен в 1С"}
        else:
            return {"status": "ok", "message": "Попытка переноса отклонена"}

    async def _mock_run_webhook_retry(self, **kwargs) -> dict[str, Any]:
        """Заглушка для запуска webhook retry"""
        logger.info("[MOCK] Running webhook retry")
        return {
            "status": "ok",
            "message": "Retry process completed",
            "limit": 100,
            "max_attempts": 3,
            "checked": 50,
            "processed": 45,
            "succeeded": 40,
            "failed": 5,
            "skipped_max_attempts": 0
        }

    async def _mock_get_webhook_retry_status(self, **kwargs) -> dict[str, Any]:
        """Заглушка для статуса webhook retry"""
        logger.info("[MOCK] Getting webhook retry status")
        return {
            "total": 100,
            "queued": 10,
            "success": 80,
            "failed": 5,
            "dead_letter": 5,
            "queued_at_max_attempts": 2
        }

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
            raise RetryableAPIError(
                f"Request timeout: {endpoint}", original_error=e
            ) from e

        except httpx.ConnectError as e:
            logger.error(
                f"API connection error: endpoint={endpoint}, method={method}",
                exc_info=True
            )
            raise RetryableAPIError(
                f"Connection error: {endpoint}", original_error=e
            ) from e

        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            logger.error(
                f"API HTTP error: endpoint={endpoint}, method={method}, "
                f"status={status_code}, response={e.response.text}",
                exc_info=True
            )
            # 5xx — server-side, transient → retryable
            if status_code >= 500:
                raise RetryableAPIError(
                    f"Server error {status_code}: {endpoint}", original_error=e
                ) from e
            # 4xx — client-side, permanent → non-retryable
            raise NonRetryableAPIError(
                f"Client error {status_code}: {endpoint}",
                status_code=status_code,
                original_error=e
            ) from e

        except (RetryableAPIError, NonRetryableAPIError):
            raise

        except Exception as e:
            logger.error(
                f"Unexpected API error: endpoint={endpoint}, method={method}, "
                f"error={e}",
                exc_info=True
            )
            # Unknown errors treated as retryable (network stack issues, etc.)
            raise RetryableAPIError(
                f"Unexpected error: {type(e).__name__}: {e}", original_error=e
            ) from e

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
                        "position": "Менеджер отдела продаж",
                        "reserves": [987654321, 111222333]
                    }
                ]
            }

        Raises:
            httpx.TimeoutException: Request timeout
            httpx.HTTPStatusError: HTTP error status (500, etc.)
            httpx.ConnectError: Connection error
        """
        # Использование заглушки
        if self.use_mock:
            return await self._mock_get_staff()
        
        endpoint = f"{self.base_url}/system/staff"
        return await self._make_request("GET", endpoint)

    # ========== Блок: Регистрация и аутентификация ==========

    async def register_user(
        self, 
        messenger: str,
        user_id: int | None = None,
        phone: str = "",
        name: str = "",
        surname: str = "",
        inn: str = "",
        grand_key: str = "",
        email: str | None = None,
        telegram_id: int | None = None  # Backward compatibility
    ) -> dict[str, Any]:
        """
        Register a new user in the I-TAT CRM system.

        Args:
            messenger: Messenger type ("telegram" or "max")
            user_id: User ID from messenger (Telegram/MAX)
            phone: Phone number (format: "+79001234567")
            name: User's first name
            surname: User's last name
            inn: Organization INN
            grand_key: Protection key number (format: "MG123456" or "00202_12345")
            email: User's email (optional)
            telegram_id: (Deprecated) Use user_id instead. Kept for backward compatibility.

        Returns:
            {
                "status": "ok",
                "message": "Пользователь зарегистрирован",
                "user_id": 123456789,
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
        # Backward compatibility: telegram_id → user_id
        if telegram_id is not None and user_id is None:
            user_id = telegram_id
        
        if user_id is None:
            raise ValueError("user_id is required")
        
        # Использование заглушки
        if self.use_mock:
            return await self._mock_register_user(user_id, phone, name, surname, grand_key)
        
        endpoint = f"{self.base_url}/user/register"
        payload = {
            "messenger": messenger,
            "user_id": user_id,
            "phone": phone,
            "name": name,
            "surname": surname,
            "inn": inn,
            "grand_key": grand_key,
        }
        
        if email:
            payload["email"] = email

        logger.info(f"Registering user: user_id={user_id}, phone={phone}, messenger={messenger}")
        return await self._make_request("POST", endpoint, json=payload)

    # ========== Блок: Профиль и Проверки ==========

    async def get_user_assets(
        self, 
        user_id: int | None = None,
        telegram_id: int | None = None  # Backward compatibility
    ) -> dict[str, Any]:
        """
        Получение списка активов пользователя (организаций и ключей)

        Args:
            user_id: User ID from messenger (Telegram/MAX)
            telegram_id: (Deprecated) Use user_id instead. Kept for backward compatibility.

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
        # Backward compatibility: telegram_id → user_id
        if telegram_id is not None and user_id is None:
            user_id = telegram_id
        
        if user_id is None:
            raise ValueError("user_id is required")
        
        # Использование заглушки
        if self.use_mock:
            return await self._mock_get_user_assets(user_id)
        
        endpoint = f"{self.base_url}/user/assets"

        logger.debug(f"Fetching user assets: user_id={user_id}")
        
        return await self._make_request("GET", endpoint, params={"user_id": user_id})


    async def check_key_conflict(
        self, 
        grand_key: str,
        user_id: int | None = None,
        telegram_id: int | None = None  # Backward compatibility
    ) -> dict[str, Any]:
        """
        Check if a protection key is available or occupied by another user.

        Args:
            grand_key: Protection key number (format: "MG123456" or "00202_12345")
            user_id: User ID from messenger (Telegram/MAX) - optional
            telegram_id: (Deprecated) Use user_id instead. Kept for backward compatibility.

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
        # Backward compatibility: telegram_id → user_id
        if telegram_id is not None and user_id is None:
            user_id = telegram_id
        
        # Использование заглушки
        if self.use_mock:
            return await self._mock_check_key_conflict(grand_key, user_id)
        
        endpoint = f"{self.base_url}/assets/check_key"
        payload = {"grand_key": grand_key}
        if user_id is not None:
            payload["user_id"] = user_id

        logger.info(f"Checking key conflict: key={grand_key}, user={user_id}")
        return await self._make_request("POST", endpoint, json=payload)


    async def log_ticket(
        self,
        ticket_id: str,
        messenger: str,
        user_id: int | None = None,
        staff_id: int | None = None,
        ticket_type: str = "",
        status: str = "",
        created_at: str | None = None,
        updated_at: str | None = None,
        comment: str | None = None,
        history_link: str | None = None,
        telegram_id: int | None = None  # Backward compatibility
    ) -> dict[str, Any]:
        """
        Log ticket creation or closure in the CRM system.

        Args:
            ticket_id: Ticket ID in the bot (format: "TKT_12345")
            messenger: Messenger type ("telegram" or "max")
            user_id: User ID from messenger (Telegram/MAX)
            staff_id: Staff member ID (optional)
            ticket_type: Ticket type (e.g., "Техподдержка", "Счет")
            status: Ticket status (e.g., "Новое", "Закрыто")
            created_at: Creation timestamp (ISO format)
            updated_at: Update timestamp (ISO format)
            comment: Optional employee comment
            history_link: Optional link to ticket history
            telegram_id: (Deprecated) Use user_id instead. Kept for backward compatibility.

        Returns:
            {
                "status": "ok",
                "message": "Обращение зарегистрировано",
                "ticket_id": "TKT_12345"
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
        # Backward compatibility: telegram_id → user_id
        if telegram_id is not None and user_id is None:
            user_id = telegram_id
        
        if user_id is None:
            raise ValueError("user_id is required")
        
        # Использование заглушки
        if self.use_mock:
            return await self._mock_log_ticket(ticket_id, user_id, ticket_type, status, comment, history_link)
        
        endpoint = f"{self.base_url}/tickets/log"
        payload = {
            "ticket_id": ticket_id, 
            "messenger": messenger,
            "user_id": user_id, 
            "type": ticket_type, 
            "status": status
        }

        if staff_id:
            payload["staff_id"] = staff_id
        if created_at:
            payload["created_at"] = created_at
        if updated_at:
            payload["updated_at"] = updated_at
        if comment:
            payload["comment"] = comment
        if history_link:
            payload["history_link"] = history_link

        logger.info(f"Logging ticket: ticket_id={ticket_id}, type={ticket_type}, status={status}, messenger={messenger}")
        return await self._make_request("POST", endpoint, json=payload)

    # ========== Блок: Регистрация - Одобрение и Отклонение ==========

    async def approve_user_registration(
        self,
        user_id: int,
        phone: str,
        inn_list: list[str],
        gs_key_list: list[str]
    ) -> dict[str, Any]:
        """
        Approve user registration in the i-TAT CRM system.
        
        Synchronizes user data with CRM and activates the account.
        
        Args:
            user_id: User ID from messenger (Telegram/MAX)
            phone: User's phone number
            inn_list: List of organization INN numbers
            gs_key_list: List of GS_Key numbers
        
        Returns:
            {
                "status": "ok",
                "message": "Регистрация одобрена",
                "user_id": 123456789
            }
        
        Raises:
            httpx.TimeoutException: Request timeout (10 seconds)
            httpx.HTTPStatusError: HTTP error status
                - 400: Invalid parameters
                - 404: User not found
                - 500: Server error
            httpx.ConnectError: Connection error
        
        Requirements: 25.1, 25.2, 25.4, 25.5, 25.6, 25.9, 25.10
        """
        # Использование заглушки
        if self.use_mock:
            return await self._mock_approve_user_registration(user_id, phone, inn_list, gs_key_list)
        
        endpoint = f"{self.base_url}/user/approve"
        payload = {
            "user_id": user_id,
            "phone": phone,
            "inn_list": inn_list,
            "gs_key_list": gs_key_list
        }
        
        logger.info(f"Approving user registration: user_id={user_id}, phone={phone}")
        
        # Retry logic with exponential backoff (1s, 2s, 4s)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                return await self._make_request("POST", endpoint, json=payload)
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # 1s, 2s, 4s
                    logger.warning(
                        f"API call failed (attempt {attempt + 1}/{max_retries}), "
                        f"retrying in {wait_time}s: {e}"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"API call failed after {max_retries} attempts: {e}")
                    raise

    async def reject_user_registration(
        self,
        user_id: int,
        phone: str,
        rejection_reason: str
    ) -> dict[str, Any]:
        """
        Reject user registration in the i-TAT CRM system.
        
        Records rejection reason and prevents account activation.
        
        Args:
            user_id: User ID from messenger (Telegram/MAX)
            phone: User's phone number
            rejection_reason: Reason for rejection (admin-provided text)
        
        Returns:
            {
                "status": "ok",
                "message": "Регистрация отклонена",
                "user_id": 123456789
            }
        
        Raises:
            httpx.TimeoutException: Request timeout (10 seconds)
            httpx.HTTPStatusError: HTTP error status
                - 400: Invalid parameters
                - 404: User not found
                - 500: Server error
            httpx.ConnectError: Connection error
        
        Requirements: 25.1, 25.2, 25.4, 25.5, 25.6, 25.9, 25.10
        """
        # Использование заглушки
        if self.use_mock:
            return await self._mock_reject_user_registration(user_id, phone, rejection_reason)
        
        endpoint = f"{self.base_url}/user/reject"
        payload = {
            "user_id": user_id,
            "phone": phone,
            "rejection_reason": rejection_reason
        }
        
        logger.info(f"Rejecting user registration: user_id={user_id}, phone={phone}")
        
        # Retry logic with exponential backoff (1s, 2s, 4s)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                return await self._make_request("POST", endpoint, json=payload)
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # 1s, 2s, 4s
                    logger.warning(
                        f"API call failed (attempt {attempt + 1}/{max_retries}), "
                        f"retrying in {wait_time}s: {e}"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"API call failed after {max_retries} attempts: {e}")
                    raise


    async def transfer_gs_key(
        self,
        old_user_id: int,
        new_user_id: int,
        key_number: str
    ) -> dict[str, Any]:
        """
        Transfer GS_Key ownership from one user to another in the i-TAT CRM system.
        
        Updates key ownership records in CRM to reflect the transfer.
        
        Args:
            old_user_id: Current owner's user ID
            new_user_id: New owner's user ID
            key_number: GS_Key number to transfer
        
        Returns:
            {
                "status": "ok",
                "message": "Ключ передан",
                "key_number": "MG123456",
                "old_user_id": 123,
                "new_user_id": 456
            }
        
        Raises:
            httpx.TimeoutException: Request timeout (10 seconds)
            httpx.HTTPStatusError: HTTP error status
                - 400: Invalid parameters
                - 404: Key or user not found
                - 500: Server error
            httpx.ConnectError: Connection error
        
        Requirements: 25.3, 25.4, 25.9, 25.10
        """
        # Использование заглушки
        if self.use_mock:
            return await self._mock_transfer_gs_key(old_user_id, new_user_id, key_number)
        
        endpoint = f"{self.base_url}/assets/transfer_key"
        payload = {
            "old_user_id": old_user_id,
            "new_user_id": new_user_id,
            "key_number": key_number
        }
        
        logger.info(
            f"Transferring GS_Key: key={key_number}, "
            f"old_user={old_user_id}, new_user={new_user_id}"
        )
        
        # Retry logic with exponential backoff (1s, 2s, 4s)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                return await self._make_request("POST", endpoint, json=payload)
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # 1s, 2s, 4s
                    logger.warning(
                        f"API call failed (attempt {attempt + 1}/{max_retries}), "
                        f"retrying in {wait_time}s: {e}"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"API call failed after {max_retries} attempts: {e}")
                    raise

    # ========== Блок: Новые методы API ==========

    async def check_inn(
        self,
        messenger: str,
        inn: str,
        user_id: int | None = None
    ) -> dict[str, Any]:
        """
        Check INN availability and validation.

        Args:
            messenger: Messenger type ("telegram" or "max")
            inn: Organization INN to check
            user_id: User ID from messenger - optional

        Returns:
            {
                "status": "ok",
                "message": "ИНН доступен"
            }
        
        Raises:
            httpx.TimeoutException: Request timeout
            httpx.HTTPStatusError: HTTP error status (400, 404, 500)
            httpx.ConnectError: Connection error
        """
        if self.use_mock:
            return await self._mock_check_inn(messenger, user_id, inn)
            
        endpoint = f"{self.base_url}/assets/check_inn"
        payload = {
            "messenger": messenger,
            "inn": inn
        }
        if user_id is not None:
            payload["user_id"] = user_id

        logger.info(f"Checking INN: inn={inn}, user={user_id}, messenger={messenger}")
        return await self._make_request("POST", endpoint, json=payload)

    async def update_user_assets(
        self,
        messenger: str,
        user_id: int,
        asset_type: str,
        action: str,
        value: str
    ) -> dict[str, Any]:
        """
        Update user assets (add/remove INN or grand_key).

        Args:
            messenger: Messenger type ("telegram" or "max")
            user_id: User ID from messenger
            asset_type: Asset type ("inn" or "grand_key")
            action: Action to perform ("add" or "remove")
            value: Asset value (INN number or key number)

        Returns:
            {
                "status": "success",
                "message": "Ассет успешно привязан/удален"
            }
        
        Raises:
            httpx.TimeoutException: Request timeout
            httpx.HTTPStatusError: HTTP error status (400, 404, 409, 500)
            httpx.ConnectError: Connection error
        """
        if self.use_mock:
            return await self._mock_update_user_assets(messenger, user_id, asset_type, action, value)
            
        endpoint = f"{self.base_url}/user/assets/update"
        payload = {
            "messenger": messenger,
            "user_id": user_id,
            "asset_type": asset_type,
            "action": action,
            "value": value
        }

        logger.info(f"Updating user assets: user={user_id}, type={asset_type}, action={action}, value={value}")
        return await self._make_request("POST", endpoint, json=payload)

    async def update_staff(
        self,
        messenger: str,
        user_id: int,
        action: str,
        role: str | None = None,
        position: str | None = None,
        is_active: bool | None = None,
        reserves: list[int] | None = None
    ) -> dict[str, Any]:
        """
        Update staff member information.

        Args:
            messenger: Messenger type ("telegram" or "max")
            user_id: Staff member's user ID in messenger
            action: Action to perform ("upsert" or "deactivate")
            role: Staff role (optional)
            position: Staff position (optional)
            is_active: Active status (optional)
            reserves: List of reserve staff IDs (optional)

        Returns:
            {
                "status": "ok",
                "message": "Сотрудник обновлен"
            }
        
        Raises:
            httpx.TimeoutException: Request timeout
            httpx.HTTPStatusError: HTTP error status (400, 404, 500)
            httpx.ConnectError: Connection error
        """
        if self.use_mock:
            return await self._mock_update_staff(messenger, user_id, action, role=role, position=position, is_active=is_active, reserves=reserves)
            
        endpoint = f"{self.base_url}/system/staff/update"
        payload = {
            "messenger": messenger,
            "user_id": user_id,
            "action": action
        }

        if role is not None:
            payload["role"] = role
        if position is not None:
            payload["position"] = position
        if is_active is not None:
            payload["is_active"] = is_active
        if reserves is not None:
            payload["reserves"] = reserves

        logger.info(f"Updating staff: user={user_id}, action={action}, messenger={messenger}")
        return await self._make_request("POST", endpoint, json=payload)

    async def resolve_conflict(
        self,
        key_number: str,
        action: str,
        new_user_phone: str,
        old_user_phone: str,
        user_id: int | None = None,
        messenger: str = "max",
        reason: str | None = None
    ) -> dict[str, Any]:
        """
        Resolve key conflict by transferring or rejecting.

        Args:
            key_number: Key number in conflict
            action: Action to take ("transfer" or "reject")
            new_user_phone: Phone of user requesting the key
            old_user_phone: Phone of current key owner
            user_id: MAX user ID of admin performing the action (optional)
            messenger: Messenger type ("max" or "telegram")
            reason: Optional reason for the action

        Returns:
            {
                "status": "ok",
                "message": "Ключ успешно перенесен в 1С" | "Попытка переноса отклонена"
            }
        
        Raises:
            httpx.TimeoutException: Request timeout
            httpx.HTTPStatusError: HTTP error status (400, 404, 500)
            httpx.ConnectError: Connection error
        """
        if self.use_mock:
            return await self._mock_resolve_conflict(key_number, action, new_user_phone, old_user_phone, reason=reason)
            
        endpoint = f"{self.base_url}/assets/resolve_conflict"
        payload = {
            "key_number": key_number,
            "action": action,
            "new_user_phone": new_user_phone,
            "old_user_phone": old_user_phone,
            "messenger": messenger
        }

        if user_id is not None:
            payload["user_id"] = user_id
        if reason:
            payload["reason"] = reason

        logger.info(f"Resolving key conflict: key={key_number}, action={action}")
        return await self._make_request("POST", endpoint, json=payload)

    async def change_phone(
        self,
        messenger: str,
        user_id: int,
        old_phone: str,
        new_phone: str,
        staff_id: int
    ) -> dict[str, Any]:
        """
        Change user's phone number.

        Args:
            messenger: Messenger type ("telegram" or "max")
            user_id: User ID from messenger
            old_phone: Current phone number
            new_phone: New phone number
            staff_id: Staff member who approved the change

        Returns:
            {
                "status": "ok",
                "message": "Номер телефона изменен"
            }
        
        Raises:
            httpx.TimeoutException: Request timeout
            httpx.HTTPStatusError: HTTP error status (400, 404, 409, 500)
            httpx.ConnectError: Connection error
        """
        if self.use_mock:
            return await self._mock_change_phone(messenger, user_id, old_phone, new_phone, staff_id)
            
        endpoint = f"{self.base_url}/user/change_phone"
        payload = {
            "messenger": messenger,
            "user_id": user_id,
            "old_phone": old_phone,
            "new_phone": new_phone,
            "staff_id": staff_id
        }

        logger.info(f"Changing phone: user={user_id}, old={old_phone}, new={new_phone}")
        return await self._make_request("POST", endpoint, json=payload)

    async def audit_log(
        self,
        messenger: str,
        action_type: str,
        action_timestamp: str | None = None,
        user_id: int | None = None,
        staff_id: int | None = None,
        ticket_id: str | None = None,
        action_details: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Log system events for audit trail.

        Args:
            messenger: Messenger type ("telegram" or "max")
            action_type: Type of action performed
            action_timestamp: When the action occurred (ISO format)
            user_id: User ID involved (optional)
            staff_id: Staff ID who performed action (optional)
            ticket_id: Ticket ID involved (optional)
            action_details: Additional details as JSON (optional)

        Returns:
            {
                "status": "ok",
                "message": "Событие записано"
            }
        
        Raises:
            httpx.TimeoutException: Request timeout
            httpx.HTTPStatusError: HTTP error status (400, 500)
            httpx.ConnectError: Connection error
        """
        if self.use_mock:
            return await self._mock_audit_log(messenger, action_type, action_timestamp=action_timestamp, user_id=user_id, staff_id=staff_id, ticket_id=ticket_id, action_details=action_details)
            
        endpoint = f"{self.base_url}/system/audit_log"
        payload = {
            "messenger": messenger,
            "action_type": action_type
        }

        if action_timestamp:
            payload["action_timestamp"] = action_timestamp
        if user_id:
            payload["user_id"] = user_id
        if staff_id:
            payload["staff_id"] = staff_id
        if ticket_id:
            payload["ticket_id"] = ticket_id
        if action_details:
            payload["action_details"] = action_details

        logger.info(f"Audit log: action={action_type}, messenger={messenger}")
        return await self._make_request("POST", endpoint, json=payload)

    async def get_ticket_history(
        self,
        ticket_id: str
    ) -> dict[str, Any]:
        """
        Get ticket history from CRM.

        Args:
            ticket_id: Ticket ID to get history for

        Returns:
            {
                "status": "ok",
                "history": [...]
            }
        
        Raises:
            httpx.TimeoutException: Request timeout
            httpx.HTTPStatusError: HTTP error status (400, 404, 500)
            httpx.ConnectError: Connection error
        """
        if self.use_mock:
            return await self._mock_get_ticket_history(ticket_id)
            
        endpoint = f"{self.base_url}/tickets/{ticket_id}/history"

        logger.info(f"Getting ticket history: ticket_id={ticket_id}")
        return await self._make_request("GET", endpoint)

    async def run_webhook_retry(
        self,
        limit: int | None = None,
        max_attempts: int | None = None
    ) -> dict[str, Any]:
        """
        Run webhook retry process.

        Args:
            limit: Maximum number of records to process (optional)
            max_attempts: Maximum retry attempts (optional)

        Returns:
            {
                "status": "ok",
                "message": "Retry process completed",
                "limit": 100,
                "max_attempts": 3,
                "checked": 50,
                "processed": 45,
                "succeeded": 40,
                "failed": 5,
                "skipped_max_attempts": 0
            }
        
        Raises:
            httpx.TimeoutException: Request timeout
            httpx.HTTPStatusError: HTTP error status (500)
            httpx.ConnectError: Connection error
        """
        if self.use_mock:
            return await self._mock_run_webhook_retry(limit=limit, max_attempts=max_attempts)
            
        endpoint = f"{self.base_url}/system/webhook_retry/run"
        payload = {}

        if limit is not None:
            payload["limit"] = limit
        if max_attempts is not None:
            payload["max_attempts"] = max_attempts

        logger.info(f"Running webhook retry: limit={limit}, max_attempts={max_attempts}")
        return await self._make_request("POST", endpoint, json=payload)

    async def get_webhook_retry_status(
        self,
        max_attempts: int | None = None
    ) -> dict[str, Any]:
        """
        Get webhook retry queue status.

        Args:
            max_attempts: Filter by max attempts (optional)

        Returns:
            {
                "total": 100,
                "queued": 10,
                "success": 80,
                "failed": 5,
                "dead_letter": 5,
                "queued_at_max_attempts": 2
            }
        
        Raises:
            httpx.TimeoutException: Request timeout
            httpx.HTTPStatusError: HTTP error status
            httpx.ConnectError: Connection error
        """
        if self.use_mock:
            return await self._mock_get_webhook_retry_status(max_attempts=max_attempts)
            
        endpoint = f"{self.base_url}/system/webhook_retry/status"
        params = {}

        if max_attempts is not None:
            params["max_attempts"] = max_attempts

        logger.info(f"Getting webhook retry status: max_attempts={max_attempts}")
        return await self._make_request("GET", endpoint, params=params)


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
