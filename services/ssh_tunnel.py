"""
SSH SOCKS5 туннель для локальной разработки.

Используется когда LOCAL_DEV=true для изолированного доступа к i-TAT API
через подсеть VPN без ручного запуска SSH-команд.

Схема: app → SOCKS5 (localhost:PORT) → SSH (ITAT_SSH_HOST) → i-TAT API

Предварительно необходимо подключиться к PPTP VPN (ITAT_VPN_HOST),
после чего туннель поднимается автоматически при старте приложения.
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_tunnel: Optional["SSHTunnel"] = None


class SSHTunnel:
    """Управляет SSH SOCKS5 туннелем через asyncssh."""

    def __init__(
        self,
        ssh_host: str,
        ssh_login: str,
        ssh_password: str,
        socks5_port: int = 1080,
    ) -> None:
        self.ssh_host = ssh_host
        self.ssh_login = ssh_login
        self.ssh_password = ssh_password
        self.socks5_port = socks5_port
        self._conn = None
        self._server = None

    async def start(self) -> None:
        """Поднимает SSH-соединение и локальный SOCKS5 сервер."""
        import asyncssh

        logger.info(
            f"LOCAL_DEV: connecting SSH tunnel "
            f"{self.ssh_login}@{self.ssh_host} → SOCKS5 localhost:{self.socks5_port}"
        )

        self._conn = await asyncssh.connect(
            host=self.ssh_host,
            username=self.ssh_login,
            password=self.ssh_password,
            known_hosts=None,          # не проверяем host key (аналог StrictHostKeyChecking=no)
            connect_timeout=15,
        )

        # Поднимаем SOCKS5 прокси-сервер на localhost
        self._server = await self._conn.start_socks_server(
            listen_host="127.0.0.1",
            listen_port=self.socks5_port,
        )

        logger.info(f"LOCAL_DEV: SSH SOCKS5 tunnel ready on localhost:{self.socks5_port}")

    async def stop(self) -> None:
        """Закрывает туннель и SSH-соединение."""
        if self._server:
            self._server.close()
            self._server = None
        if self._conn:
            self._conn.close()
            self._conn = None
        logger.info("LOCAL_DEV: SSH tunnel closed")


async def start_tunnel() -> None:
    """
    Запускает SSH SOCKS5 туннель если LOCAL_DEV=true.
    Вызывается при старте приложения (lifespan).
    """
    global _tunnel

    from constants import LOCAL_DEV, ITAT_SSH_HOST, ITAT_SSH_SOCKS5_PORT
    from constants import ITAT_SSH_LOGIN, ITAT_SSH_PASSWORD

    if not LOCAL_DEV:
        return

    if not ITAT_SSH_HOST or not ITAT_SSH_LOGIN:
        logger.warning(
            "LOCAL_DEV=true но ITAT_SSH_HOST или ITAT_SSH_LOGIN не заданы — туннель не запущен"
        )
        return

    _tunnel = SSHTunnel(
        ssh_host=ITAT_SSH_HOST,
        ssh_login=ITAT_SSH_LOGIN,
        ssh_password=ITAT_SSH_PASSWORD,
        socks5_port=ITAT_SSH_SOCKS5_PORT,
    )
    await _tunnel.start()


async def stop_tunnel() -> None:
    """
    Останавливает SSH SOCKS5 туннель.
    Вызывается при остановке приложения (lifespan).
    """
    global _tunnel
    if _tunnel:
        await _tunnel.stop()
        _tunnel = None
