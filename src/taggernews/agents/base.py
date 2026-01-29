"""Base agent class for taxonomy management agents."""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from taggernews.infrastructure.models import AgentRunModel


class BaseAgent(ABC):
    """Base class for all taxonomy agents.

    Provides common functionality for:
    - Session management
    - Run tracking (create/complete/fail records)
    - Logging
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize agent with database session.

        Args:
            session: AsyncSession for database operations
        """
        self.session = session
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Execute agent logic.

        Args:
            context: Input context for the agent

        Returns:
            Result data from agent execution
        """
        pass

    async def _create_run_record(self, run_type: str) -> AgentRunModel:
        """Create agent run tracking record.

        Args:
            run_type: Type of run ('analysis', 'proposal', 'execution')

        Returns:
            Created AgentRunModel instance
        """
        run = AgentRunModel(
            run_type=run_type,
            status="running",
            started_at=datetime.now(),
        )
        self.session.add(run)
        await self.session.flush()
        self.logger.info(f"Created agent run record: id={run.id}, type={run_type}")
        return run

    async def _complete_run(
        self, run: AgentRunModel, result_data: dict[str, Any]
    ) -> None:
        """Mark run as completed with result data.

        Args:
            run: The AgentRunModel to update
            result_data: Results from the agent execution
        """
        run.status = "completed"
        run.completed_at = datetime.now()
        run.result_data = result_data
        self.logger.info(f"Completed agent run: id={run.id}")

    async def _fail_run(self, run: AgentRunModel, error_message: str) -> None:
        """Mark run as failed with error message.

        Args:
            run: The AgentRunModel to update
            error_message: Description of the failure
        """
        run.status = "failed"
        run.completed_at = datetime.now()
        run.error_message = error_message
        self.logger.error(f"Failed agent run: id={run.id}, error={error_message}")
