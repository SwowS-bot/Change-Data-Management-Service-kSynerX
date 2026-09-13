import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.schemas.product import VietfulProductInput
from app.services.change_detection import ChangeDetectionEngine

logger = logging.getLogger("ScheduledPoller")

class CircuitState:
    CLOSED = "CLOSED"      # Normal operation
    OPEN = "OPEN"          # Failing, fast-drop or backoff
    HALF_OPEN = "HALF_OPEN"  # Testing recovery


class ScheduledPoller:
    """
    Scheduled Poller Engine:
    - Periodically queries inventory data from Vietful Inventory Service.
    - Sends fetched products to ChangeDetectionEngine.
    - Features built-in Circuit Breaker and Exponential Backoff for resilience.
    """

    def __init__(
        self,
        base_url: str = settings.VIETFUL_API_URL,
        interval_seconds: int = settings.POLLING_INTERVAL_SECONDS,
        max_backoff: float = 60.0
    ):
        self.base_url = base_url.rstrip("/")
        self.interval_seconds = interval_seconds
        self.max_backoff = max_backoff
        
        self.is_running = False
        self._task: Optional[asyncio.Task] = None
        
        # Resilience & Circuit Breaker metrics
        self.circuit_state = CircuitState.CLOSED
        self.consecutive_errors = 0
        self.error_threshold = 3
        self.current_backoff = 2.0
        
        # Operational metrics
        self.total_polls = 0
        self.successful_polls = 0
        self.failed_polls = 0
        self.last_poll_time: Optional[datetime] = None
        self.last_error_message: Optional[str] = None
        self.last_summary: Optional[Dict[str, Any]] = None

    def get_status(self) -> Dict[str, Any]:
        return {
            "is_running": self.is_running,
            "circuit_state": self.circuit_state,
            "target_url": f"{self.base_url}/api/v1/Products",
            "interval_seconds": self.interval_seconds,
            "consecutive_errors": self.consecutive_errors,
            "total_polls": self.total_polls,
            "successful_polls": self.successful_polls,
            "failed_polls": self.failed_polls,
            "last_poll_time": self.last_poll_time.isoformat() if self.last_poll_time else None,
            "last_error": self.last_error_message,
            "last_summary": self.last_summary
        }

    async def fetch_vietful_products(self, client: httpx.AsyncClient) -> List[VietfulProductInput]:
        """
        Queries Vietful Products API with timeout handling.
        """
        url = f"{self.base_url}/api/v1/Products?PageSize=100"
        response = await client.get(url, timeout=5.0)
        response.raise_for_status()
        raw_items = response.json()
        
        products: List[VietfulProductInput] = []
        for item in raw_items:
            try:
                products.append(VietfulProductInput(**item))
            except Exception as e:
                logger.warning(f"Error parsing product item from Vietful: {e}")
        return products

    async def poll_once(self) -> Optional[Dict[str, Any]]:
        """
        Executes a single polling iteration and records change metrics.
        Returns IngestionSummary dict or None if failure.
        """
        self.total_polls += 1
        self.last_poll_time = datetime.now(timezone.utc)

        try:
            async with httpx.AsyncClient() as client:
                products = await self.fetch_vietful_products(client)

            if not products:
                logger.info("Poller: No products received from Vietful")
                self._record_success()
                return None

            # Ingest through Exactly-Once Engine
            async with AsyncSessionLocal() as session:
                summary = await ChangeDetectionEngine.process_batch(
                    session=session,
                    products=products,
                    source="POLLING"
                )

            summary_dict = summary.model_dump()
            self._record_success(summary_dict)
            logger.info(
                f"Poller iteration completed: Total={summary.total_records}, "
                f"New={summary.inserted_count}, Updated={summary.updated_count}, "
                f"Deduplicated={summary.duplicate_count}"
            )
            return summary_dict

        except (httpx.HTTPError, httpx.TimeoutException, ConnectionError) as net_err:
            self._record_failure(f"Network error connecting to Vietful: {net_err}")
            return None
        except Exception as err:
            self._record_failure(f"Unexpected error during polling: {err}")
            return None

    def _record_success(self, summary: Optional[Dict[str, Any]] = None):
        self.successful_polls += 1
        self.consecutive_errors = 0
        self.current_backoff = 2.0
        self.circuit_state = CircuitState.CLOSED
        self.last_error_message = None
        if summary:
            self.last_summary = summary

    def _record_failure(self, error_msg: str):
        self.failed_polls += 1
        self.consecutive_errors += 1
        self.last_error_message = error_msg
        logger.warning(f"Poller failure ({self.consecutive_errors}): {error_msg}")

        if self.consecutive_errors >= self.error_threshold:
            self.circuit_state = CircuitState.OPEN
            self.current_backoff = min(self.current_backoff * 2, self.max_backoff)
            logger.error(
                f"Circuit breaker OPEN. Backing off for {self.current_backoff}s before next probe."
            )

    async def _loop(self):
        """Continuous background execution loop with adaptive backoff."""
        logger.info(f"ScheduledPoller loop started (Interval: {self.interval_seconds}s)")
        while self.is_running:
            try:
                await self.poll_once()
            except Exception as e:
                logger.error(f"Unhandled exception in poller loop: {e}", exc_info=True)

            # Determine sleep time based on circuit breaker status
            if self.circuit_state == CircuitState.OPEN:
                sleep_duration = self.current_backoff
            else:
                sleep_duration = self.interval_seconds

            try:
                await asyncio.sleep(sleep_duration)
            except asyncio.CancelledError:
                break

    def start(self):
        """Starts background poller task."""
        if not self.is_running:
            self.is_running = True
            self._task = asyncio.create_task(self._loop())
            logger.info("ScheduledPoller background task initiated")

    async def stop(self):
        """Gracefully stops background poller task."""
        if self.is_running:
            self.is_running = False
            if self._task:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            logger.info("ScheduledPoller background task terminated")


# Singleton instance
poller = ScheduledPoller()
