"""
Database session management utilities with async support.

Provides async context managers for database sessions with connection retry logic
and connection pool configuration.

Requirements: Error Handling section
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class DatabaseSessionManager:
    """
    Manages database connections and sessions with retry logic.
    
    Provides async context managers for database sessions with automatic
    connection retry and connection pool configuration.
    """
    
    def __init__(
        self,
        database_url: str,
        pool_size: int = 10,
        max_overflow: int = 20,
        pool_timeout: int = 30,
        pool_recycle: int = 3600,
        echo: bool = False
    ):
        """
        Initialize database session manager.
        
        Args:
            database_url: PostgreSQL connection URL (async format)
            pool_size: Number of connections to maintain in the pool
            max_overflow: Maximum number of connections to create beyond pool_size
            pool_timeout: Seconds to wait before giving up on getting a connection
            pool_recycle: Seconds after which to recycle connections
            echo: Whether to log SQL statements
        """
        self.engine = create_async_engine(
            database_url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            pool_recycle=pool_recycle,
            echo=echo
        )
        
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        
        logger.info(
            f"Database session manager initialized with pool_size={pool_size}, "
            f"max_overflow={max_overflow}"
        )
    
    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Async context manager for database sessions.
        
        Automatically handles session lifecycle with proper cleanup.
        Commits on success, rolls back on exception.
        
        Usage:
            async with db_manager.session() as session:
                user = await session.get(User, user_id)
                # ... perform operations
        
        Yields:
            AsyncSession: Database session
        
        Raises:
            OperationalError: If database connection fails after retries
        """
        session = self.session_factory()
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Session error, rolling back: {e}")
            raise
        finally:
            await session.close()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    async def execute_with_retry(self, session: AsyncSession, query):
        """
        Execute a query with automatic retry on connection errors.
        
        Implements exponential backoff retry strategy:
        - Attempt 1: Immediate
        - Attempt 2: Wait 2 seconds
        - Attempt 3: Wait 4 seconds
        
        Args:
            session: Database session
            query: SQLAlchemy query to execute
        
        Returns:
            Query result
        
        Raises:
            OperationalError: If all retry attempts fail
        """
        try:
            result = await session.execute(query)
            return result
        except OperationalError as e:
            logger.error(f"Database connection error: {e}")
            raise
    
    async def close(self):
        """
        Close the database engine and all connections.
        
        Should be called on application shutdown.
        """
        await self.engine.dispose()
        logger.info("Database engine closed")


# Global session manager instance (to be initialized by application)
_session_manager: DatabaseSessionManager | None = None


def init_db(
    database_url: str,
    pool_size: int = 10,
    max_overflow: int = 20,
    pool_timeout: int = 30,
    pool_recycle: int = 3600,
    echo: bool = False
) -> DatabaseSessionManager:
    """
    Initialize the global database session manager.
    
    Should be called once during application startup.
    
    Args:
        database_url: PostgreSQL connection URL (async format)
        pool_size: Number of connections to maintain in the pool
        max_overflow: Maximum number of connections to create beyond pool_size
        pool_timeout: Seconds to wait before giving up on getting a connection
        pool_recycle: Seconds after which to recycle connections
        echo: Whether to log SQL statements
    
    Returns:
        DatabaseSessionManager: Initialized session manager
    """
    global _session_manager
    _session_manager = DatabaseSessionManager(
        database_url=database_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_recycle=pool_recycle,
        echo=echo
    )
    return _session_manager


def get_db_manager() -> DatabaseSessionManager:
    """
    Get the global database session manager.
    
    Returns:
        DatabaseSessionManager: Global session manager instance
    
    Raises:
        RuntimeError: If database has not been initialized
    """
    if _session_manager is None:
        raise RuntimeError(
            "Database not initialized. Call init_db() first."
        )
    return _session_manager


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Convenience function to get a database session.
    
    Usage:
        async with get_session() as session:
            user = await session.get(User, user_id)
    
    Yields:
        AsyncSession: Database session
    
    Raises:
        RuntimeError: If database has not been initialized
    """
    manager = get_db_manager()
    async with manager.session() as session:
        yield session
