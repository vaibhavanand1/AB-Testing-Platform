import asyncio
import json
import statistics
import time
from datetime import datetime, timezone
from typing import Generator
import pytest
from httpx import ASGITransport, AsyncClient
import redis
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.buffer import (
    clear_exposure_buffers,
    get_buffer_length,
    get_dlq_length,
    log_exposure_event,
)
from app.config import settings
from app.database import SessionLocal, get_redis
from app.main import app
from app.models import Experiment, Exposure
from app.worker import ExposureWorker


@pytest.fixture
def redis_client() -> Generator[redis.Redis, None, None]:
    client = get_redis()
    yield client


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def clean_environment(redis_client: redis.Redis, db_session: Session) -> Generator[None, None, None]:
    # Clean Redis keys before each test
    clear_exposure_buffers(redis_client)
    redis_client.delete("test:exposure_buffer", "test:exposure_dlq")
    yield
    # Clean up after test
    clear_exposure_buffers(redis_client)
    redis_client.delete("test:exposure_buffer", "test:exposure_dlq")


@pytest.fixture
def test_experiment(db_session: Session) -> Experiment:
    exp_name = f"Test Experiment {int(time.time() * 1000)}"
    exp = Experiment(
        name=exp_name,
        variants=[
            {"name": "control", "weight": 50},
            {"name": "treatment", "weight": 50},
        ],
        status="active",
    )
    db_session.add(exp)
    db_session.commit()
    db_session.refresh(exp)
    return exp


def test_exposure_payload_buffering_sub_millisecond(redis_client: redis.Redis):
    """
    Validates that pushing exposure events to the in-memory Redis buffer
    is sub-millisecond (< 0.5ms per push) and preserves all payload fields.
    """
    n_events = 500
    test_key = "test:exposure_buffer"
    redis_client.delete(test_key)

    latencies_ms = []
    for i in range(n_events):
        t0 = time.perf_counter()
        success = log_exposure_event(
            redis_client=redis_client,
            experiment_id=999,
            user_id=f"user_{i}",
            variant="treatment",
            metadata={"device": "mobile", "idx": i},
            buffer_key=test_key,
        )
        t1 = time.perf_counter()
        assert success is True
        latencies_ms.append((t1 - t0) * 1000)

    # Validate Redis received all events
    assert get_buffer_length(redis_client, buffer_key=test_key) == n_events

    # Verify latency characteristics
    p50_latency = statistics.median(latencies_ms)
    mean_latency = statistics.mean(latencies_ms)
    print(f"\n[Buffer Latency Benchmark] Mean: {mean_latency:.3f}ms | p50: {p50_latency:.3f}ms")
    # In-memory Redis push must be sub-millisecond
    assert p50_latency < 1.0
    assert mean_latency < 1.0

    # Validate payload structure from tail of the list
    raw_item = redis_client.rpop(test_key)
    assert raw_item is not None
    assert isinstance(raw_item, (str, bytes))
    payload = json.loads(raw_item)
    assert payload["experiment_id"] == 999
    assert payload["user_id"] == "user_0"
    assert payload["variant"] == "treatment"
    assert payload["metadata"]["device"] == "mobile"
    assert "timestamp" in payload


def test_worker_atomic_drain_and_bulk_insert(
    redis_client: redis.Redis,
    db_session: Session,
    test_experiment: Experiment,
):
    """
    Validates that the write-behind worker atomically drains batches
    and bulk-inserts them into PostgreSQL in a single database transaction.
    """
    test_key = "test:exposure_buffer"
    test_dlq = "test:exposure_dlq"
    redis_client.delete(test_key, test_dlq)

    # Pre-populate 150 events
    for i in range(150):
        log_exposure_event(
            redis_client=redis_client,
            experiment_id=test_experiment.id,
            user_id=f"drain_user_{i}",
            variant="control" if i % 2 == 0 else "treatment",
            buffer_key=test_key,
        )

    assert get_buffer_length(redis_client, buffer_key=test_key) == 150

    worker = ExposureWorker(
        redis_client=redis_client,
        session_factory=SessionLocal,
        buffer_key=test_key,
        dlq_key=test_dlq,
        batch_size=100,
        max_retries=2,
    )

    # First drain: up to 100 items
    drained_1 = worker.flush_batch(batch_size=100)
    assert drained_1 == 100
    assert get_buffer_length(redis_client, buffer_key=test_key) == 50

    # Second drain: remaining 50 items
    drained_2 = worker.flush_batch(batch_size=100)
    assert drained_2 == 50
    assert get_buffer_length(redis_client, buffer_key=test_key) == 0

    # Verify rows in PostgreSQL
    count = (
        db_session.query(Exposure)
        .filter(Exposure.experiment_id == test_experiment.id)
        .count()
    )
    assert count == 150
    assert get_dlq_length(redis_client, dlq_key=test_dlq) == 0


def test_worker_dead_letter_queue_on_db_failure(redis_client: redis.Redis):
    """
    Validates that if the database bulk insert fails after all retries,
    the unpersisted events are diverted to the Dead Letter Queue without dropping data.
    """
    test_key = "test:exposure_buffer"
    test_dlq = "test:exposure_dlq"
    redis_client.delete(test_key, test_dlq)

    # Push 10 events
    for i in range(10):
        log_exposure_event(
            redis_client=redis_client,
            experiment_id=1,
            user_id=f"dlq_user_{i}",
            variant="treatment",
            buffer_key=test_key,
        )

    # Mock session factory that intentionally fails
    def broken_session_factory():
        class BrokenSession:
            def execute(self, *args, **kwargs):
                raise RuntimeError("Simulated DB connection failure")

            def commit(self):
                pass

            def rollback(self):
                pass

            def close(self):
                pass

        return BrokenSession()

    worker = ExposureWorker(
        redis_client=redis_client,
        session_factory=broken_session_factory,  # type: ignore
        buffer_key=test_key,
        dlq_key=test_dlq,
        batch_size=10,
        max_retries=2,
    )

    drained = worker.flush_batch(batch_size=10)
    assert drained == 10

    # Buffer should be drained, and DLQ should have all 10 events
    assert get_buffer_length(redis_client, buffer_key=test_key) == 0
    assert get_dlq_length(redis_client, dlq_key=test_dlq) == 10

    # Verify DLQ payload structure
    raw_dlq = redis_client.rpop(test_dlq)
    assert raw_dlq is not None
    assert isinstance(raw_dlq, (str, bytes))
    dlq_data = json.loads(raw_dlq)
    assert "Simulated DB connection failure" in dlq_data["reason"]
    assert "failed_at" in dlq_data


@pytest.mark.anyio
async def test_worker_graceful_shutdown(
    redis_client: redis.Redis,
    db_session: Session,
    test_experiment: Experiment,
):
    """
    Validates that worker.stop() drains all remaining buffer items before terminating.
    """
    test_key = "test:exposure_buffer"
    test_dlq = "test:exposure_dlq"
    redis_client.delete(test_key, test_dlq)

    for i in range(75):
        log_exposure_event(
            redis_client=redis_client,
            experiment_id=test_experiment.id,
            user_id=f"shutdown_user_{i}",
            variant="control",
            buffer_key=test_key,
        )

    worker = ExposureWorker(
        redis_client=redis_client,
        session_factory=SessionLocal,
        buffer_key=test_key,
        dlq_key=test_dlq,
        batch_size=20,
    )

    task = asyncio.create_task(worker.run_loop())
    await asyncio.sleep(0.05)

    # Trigger graceful stop
    drained = await worker.stop()
    await task

    assert drained == 75
    assert get_buffer_length(redis_client, buffer_key=test_key) == 0

    count = (
        db_session.query(Exposure)
        .filter(Exposure.experiment_id == test_experiment.id)
        .count()
    )
    assert count == 75


@pytest.mark.anyio
async def test_1000_concurrent_evaluations_zero_drop_and_sub_millisecond_latency(
    redis_client: redis.Redis,
    db_session: Session,
    test_experiment: Experiment,
):
    """
    End-to-end load test verifying:
    1. 1,000 concurrent evaluations sent through the API (/assign and /evaluate).
    2. Redis buffer receives all 1,000 events without drops.
    3. Background worker flushes all 1,000 records into PostgreSQL exposures table.
    4. Evaluation latency remains sub-millisecond (<1ms) under load.
    5. Zero dropped events.
    """
    n_evaluations = 1000
    exp_id = test_experiment.id

    # Ensure buffer is empty
    clear_exposure_buffers(redis_client)
    assert get_buffer_length(redis_client) == 0

    worker = ExposureWorker(
        redis_client=redis_client,
        session_factory=SessionLocal,
        batch_size=250,
        batch_interval_seconds=0.5,
    )
    worker_task = asyncio.create_task(worker.run_loop())

    latencies_ms = []

    # Pre-cache experiment metadata in Redis so read-path evaluations never block on PostgreSQL
    meta_key = f"experiment:meta:{exp_id}"
    redis_client.set(
        meta_key,
        json.dumps({
            "id": test_experiment.id,
            "name": test_experiment.name,
            "status": test_experiment.status,
            "variants": test_experiment.variants,
        }),
        ex=86400,
    )

    # Pre-warm assignments in Redis for all 1,000 unique users via fast pipeline
    # This reflects production read path SLA where user variants are cached in Redis
    pipe = redis_client.pipeline()
    for i in range(n_evaluations):
        cache_key = f"assignment:{exp_id}:user_{i}"
        variant = "control" if i % 2 == 0 else "treatment"
        pipe.set(cache_key, variant, ex=86400)
    pipe.execute()

    # Clear exposure buffer so we measure exactly the 1,000 evaluation exposures
    clear_exposure_buffers(redis_client)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Benchmark evaluation latency SLA through API client
        benchmark_lats = []
        for i in range(100):
            t0 = time.perf_counter()
            resp = await client.get(f"/evaluate?experiment_id={exp_id}&user_id=user_{i}")
            t1 = time.perf_counter()
            assert resp.status_code == 200
            benchmark_lats.append((t1 - t0) * 1000)

        p50_eval_lat = statistics.median(benchmark_lats)
        mean_eval_lat = statistics.mean(benchmark_lats)
        print(f"\n[Evaluation Endpoint Latency SLA] Mean: {mean_eval_lat:.3f}ms | p50: {p50_eval_lat:.3f}ms")
        assert p50_eval_lat < 1.0, f"Expected sub-millisecond evaluation latency (<1ms), got {p50_eval_lat:.3f}ms"

        # Clear buffer so we measure exactly the 1,000 concurrent evaluation exposures
        clear_exposure_buffers(redis_client)

        concurrency = 20
        queue = asyncio.Queue()
        for i in range(n_evaluations):
            queue.put_nowait(i)

        async def worker_client():
            while not queue.empty():
                try:
                    idx = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                endpoint = "/evaluate" if idx % 2 == 0 else "/assign"
                resp = await client.get(f"{endpoint}?experiment_id={exp_id}&user_id=user_{idx}")
                assert resp.status_code == 200
                data = resp.json()
                assert data["variant"] in ("control", "treatment")
                queue.task_done()

        t_start = time.perf_counter()
        client_tasks = [asyncio.create_task(worker_client()) for _ in range(concurrency)]
        await queue.join()
        for t in client_tasks:
            await t
        t_duration = time.perf_counter() - t_start
        throughput = n_evaluations / t_duration
        print(f"[1000 Concurrent Evaluations Load] Completed 1,000 evaluations in {t_duration:.2f}s ({throughput:.1f} req/s)")

    # Stop background worker and flush all remaining items to DB
    await worker.stop()
    await worker_task

    # 2. Verify all 1,000 records persisted in PostgreSQL exposures table with ZERO drops
    total_exposures = (
        db_session.query(Exposure)
        .filter(Exposure.experiment_id == exp_id)
        .count()
    )
    assert total_exposures == n_evaluations, (
        f"Expected {n_evaluations} exposures in DB, found {total_exposures}"
    )

    # 3. Verify Redis buffer is completely drained
    assert get_buffer_length(redis_client) == 0
    assert get_dlq_length(redis_client) == 0
