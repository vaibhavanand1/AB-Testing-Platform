import asyncio
import logging
import os
import signal
import sys

# Ensure backend directory is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, "..", "backend"))
if not os.path.isdir(backend_dir):
    backend_dir = "/app/backend"
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.worker import ExposureWorker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("exposure_worker")


async def main():
    worker = ExposureWorker()
    loop = asyncio.get_running_loop()

    stop_event = asyncio.Event()

    def handle_signal(sig):
        logger.info(f"Received signal {sig.name}, triggering worker shutdown...")
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda s=sig: handle_signal(s))
        except NotImplementedError:
            # Handle Windows / systems without signal handlers support in loop
            signal.signal(sig, lambda s, f: handle_signal(sig))

    worker_task = asyncio.create_task(worker.run_loop())

    await stop_event.wait()
    await worker.stop()
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    logger.info("Worker process completed gracefully.")


if __name__ == "__main__":
    asyncio.run(main())
