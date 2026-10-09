import asyncio
import json
import logging
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, cast
import redis
from sqlalchemy import Table, insert
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.database import SessionLocal, engine, get_redis
from app.models import Exposure

logger = logging.getLogger(__name__)


class ExposureWorker:
    """
    Asynchronous, resilient Write-Behind Worker that drains exposures from
    the in-memory Redis buffer and bulk-inserts them into PostgreSQL in single transactions.
    """

    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        session_factory: Optional[sessionmaker[Session]] = None,
        buffer_key: Optional[str] = None,
        dlq_key: Optional[str] = None,
        batch_size: Optional[int] = None,
        batch_interval_seconds: Optional[float] = None,
        max_retries: Optional[int] = None,
        poll_interval_seconds: float = 0.05,
    ):
        self.redis_client = redis_client or get_redis()
        self.session_factory = session_factory or SessionLocal
        self.buffer_key = buffer_key or settings.exposure_buffer_key
        self.dlq_key = dlq_key or settings.exposure_dlq_key
        self.batch_size = batch_size or settings.exposure_batch_size
        self.batch_interval_seconds = (
            batch_interval_seconds or settings.exposure_batch_interval_seconds
        )
        self.max_retries = max_retries or settings.exposure_max_retries
        self.poll_interval_seconds = poll_interval_seconds

        self.running = False
        self._flush_event: Optional[asyncio.Event] = None

    def get_buffer_length(self) -> int:
        try:
            return self.redis_client.llen(self.buffer_key)
        except redis.RedisError as e:
            logger.error(f"Error checking Redis buffer length: {e}")
            return 0

    def get_dlq_length(self) -> int:
        try:
            return self.redis_client.llen(self.dlq_key)
        except redis.RedisError as e:
            logger.error(f"Error checking DLQ length: {e}")
            return 0

    def trigger_flush(self) -> None:
        """Signal the worker loop to flush immediately without waiting for poll interval."""
        if self._flush_event is not None:
            self._flush_event.set()

    def _atomic_drain_raw(self, count: int) -> List[str]:
        """
        Atomically drains up to `count` items from the Redis list buffer.
        Uses Redis 6.2+ RPOP key count, with fallback to an atomic Lua script.
        """
        if count <= 0:
            return []

        try:
            # Redis 6.2+ native RPOP with count
            raw = self.redis_client.rpop(self.buffer_key, count=count)
            if not raw:
                return []
            if isinstance(raw, list):
                return [x.decode("utf-8") if isinstance(x, bytes) else x for x in raw]
            return [raw.decode("utf-8") if isinstance(raw, bytes) else raw]
        except redis.ResponseError:
            # Fallback Lua script for Redis versions where RPOP count is unsupported
            lua_drain = """
            local key = KEYS[1]
            local count = tonumber(ARGV[1])
            local items = {}
            for i = 1, count do
                local val = redis.call('RPOP', key)
                if not val then break end
                table.insert(items, val)
            end
            return items
            """
            result = self.redis_client.eval(lua_drain, 1, self.buffer_key, count)
            if not result or not isinstance(result, list):
                return []
            return [x.decode("utf-8") if isinstance(x, bytes) else x for x in result]
        except redis.RedisError as e:
            logger.error(f"Redis error during atomic drain: {e}")
            return []

    def _persist_records_with_retry(self, records: List[Dict[str, Any]], raw_items: List[str]) -> bool:
        """
        Bulk inserts parsed records into PostgreSQL in a single database transaction.
        Applies exponential backoff retries and routes to DLQ on persistent failure.
        """
        attempt = 0
        last_error = ""
        while attempt < self.max_retries:
            attempt += 1
            session: Session = self.session_factory()
            try:
                # Core table insert ensures multi-row bulk insert in 1 SQL statement
                stmt = insert(cast(Table, Exposure.__table__))
                session.execute(stmt, records)
                session.commit()
                return True
            except Exception as e:
                session.rollback()
                last_error = str(e)
                logger.warning(
                    f"PostgreSQL bulk insert failed (attempt {attempt}/{self.max_retries}): {e}"
                )
                if attempt < self.max_retries:
                    # Exponential backoff: 0.1s, 0.2s, 0.4s...
                    time.sleep(0.1 * (2 ** (attempt - 1)))
                else:
                    logger.error(
                        f"Bulk insert permanently failed after {self.max_retries} attempts. Routing {len(raw_items)} events to DLQ: {e}"
                    )
            finally:
                session.close()

        # Permanent failure: divert all unwritten raw items to Dead Letter Queue
        self._route_to_dlq(
            raw_items,
            reason=f"PostgreSQL insert failed after {self.max_retries} retries: {last_error}",
        )
        return False

    def _route_to_dlq(self, raw_items: List[str], reason: str) -> None:
        """Diverts failed items to Dead-Letter Queue with incident metadata."""
        if not raw_items:
            return
        logger.warning(f"Routing {len(raw_items)} events to DLQ '{self.dlq_key}' (reason: {reason})")
        dlq_entries = []
        for raw in raw_items:
            entry = {
                "payload": raw,
                "reason": reason,
                "failed_at": datetime.now(timezone.utc).isoformat(),
            }
            dlq_entries.append(json.dumps(entry))
        try:
            self.redis_client.lpush(self.dlq_key, *dlq_entries)
        except redis.RedisError as e:
            logger.critical(f"FATAL: Failed to write to DLQ '{self.dlq_key}': {e}")

    def flush_batch(self, batch_size: Optional[int] = None) -> int:
        """
        Drains up to `batch_size` items from the Redis buffer and persists them.
        Returns the number of events processed.
        """
        limit = batch_size or self.batch_size
        raw_items = self._atomic_drain_raw(limit)
        if not raw_items:
            return 0

        valid_records: List[Dict[str, Any]] = []
        corrupted_items: List[str] = []

        for raw in raw_items:
            try:
                item = json.loads(raw)
                ts = datetime.fromisoformat(item["timestamp"])
                valid_records.append({
                    "experiment_id": item["experiment_id"],
                    "user_id": item["user_id"],
                    "variant": item["variant"],
                    "timestamp": ts,
                    "metadata": item.get("metadata"),
                })
            except Exception as parse_err:
                logger.error(f"Malformed exposure event payload: {parse_err}; payload: {raw}")
                corrupted_items.append(raw)

        if corrupted_items:
            self._route_to_dlq(corrupted_items, reason="Malformed JSON / invalid timestamp format")

        if valid_records:
            self._persist_records_with_retry(valid_records, raw_items)

        return len(raw_items)

    def flush_all(self) -> int:
        """
        Synchronously flushes all buffered events until Redis buffer is completely drained.
        Used during graceful shutdown or integration test teardown.
        """
        total = 0
        while True:
            drained = self.flush_batch(self.batch_size)
            if drained == 0:
                break
            total += drained
        return total

    async def run_loop(self) -> None:
        """
        Asynchronous worker loop that runs continuously, flushing when batch size
        is reached or when batch interval has elapsed.
        """
        self.running = True
        self._flush_event = asyncio.Event()
        last_flush_time = time.monotonic()
        logger.info(
            f"ExposureWorker started: buffer='{self.buffer_key}', batch_size={self.batch_size}, interval={self.batch_interval_seconds}s"
        )

        while self.running:
            try:
                try:
                    await asyncio.wait_for(
                        self._flush_event.wait(),
                        timeout=self.poll_interval_seconds,
                    )
                    self._flush_event.clear()
                except asyncio.TimeoutError:
                    pass

                if not self.running:
                    break

                buffer_len = self.get_buffer_length()
                now = time.monotonic()
                time_elapsed = (now - last_flush_time) >= self.batch_interval_seconds

                if buffer_len >= self.batch_size or (buffer_len > 0 and time_elapsed):
                    # Drain in chunks up to batch_size until buffer is below threshold
                    while self.running and self.get_buffer_length() > 0:
                        flushed = self.flush_batch(self.batch_size)
                        if flushed == 0:
                            break
                        if self.get_buffer_length() < self.batch_size and not (time.monotonic() - last_flush_time >= self.batch_interval_seconds):
                            break
                    last_flush_time = time.monotonic()

            except asyncio.CancelledError:
                logger.info("ExposureWorker task cancelled.")
                break
            except Exception as e:
                logger.exception(f"Unexpected error in ExposureWorker run loop: {e}")
                await asyncio.sleep(self.poll_interval_seconds)

    async def stop(self) -> int:
        """
        Graceful shutdown hook: stops loop and drains all remaining events in the buffer.
        """
        self.running = False
        if self._flush_event is not None:
            self._flush_event.set()
        logger.info("Gracefully shutting down ExposureWorker, draining remaining buffer...")
        drained = self.flush_all()
        logger.info(f"ExposureWorker stopped. Successfully drained {drained} remaining events.")
        return drained
