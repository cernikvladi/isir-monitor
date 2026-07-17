import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import BackgroundTasks, FastAPI

from app.db import Base, SessionLocal, engine
from app import models  # noqa: F401 - ensures models are registered on Base
from app.isir_client import get_last_podnet_id
from app.sync import bootstrap, run_sync_cycle

logger = logging.getLogger(__name__)

# Popis_WS_1 1.7 recommends at least a 10 minute interval between requests
# from one client; default sits comfortably above that.
SYNC_INTERVAL_MINUTES = int(os.getenv("SYNC_INTERVAL_MINUTES", "15"))

app = FastAPI()
scheduler = BackgroundScheduler()


def _scheduled_sync_tick() -> None:
    """Runs on every scheduler interval. bootstrap() is idempotent: on a cold
    cursor it does the one-time backfill (binary search + full drain, which
    can run long), and on every call after that it's just an unbounded drain
    of whatever's new - a single cheap no-op call once caught up. Because the
    job has max_instances=1, a slow first run simply causes later ticks to be
    skipped rather than overlap."""
    session = SessionLocal()
    try:
        count = bootstrap(session)
        logger.info("sync tick ingested %d events", count)
    except Exception:
        logger.exception("sync tick failed")
    finally:
        session.close()


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    scheduler.add_job(
        _scheduled_sync_tick,
        "interval",
        minutes=SYNC_INTERVAL_MINUTES,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()


@app.on_event("shutdown")
def shutdown() -> None:
    scheduler.shutdown(wait=False)


@app.get("/")
def root():
    return {"status": "ISIR Monitor running"}


@app.get("/health")
def health():
    return {"database": "configured"}


@app.get("/isir/last-id")
def isir_last_id():
    return {"last_id": get_last_podnet_id()}


@app.get("/sync/status")
def sync_status():
    session = SessionLocal()
    try:
        state = session.get(models.SyncState, 1)
        return {
            "last_processed_id": state.last_processed_id if state else None,
            "updated_at": state.updated_at if state else None,
            "current_isir_last_id": get_last_podnet_id(),
        }
    finally:
        session.close()


@app.post("/sync/bootstrap")
def sync_bootstrap(background_tasks: BackgroundTasks):
    """Kick off the backfill immediately instead of waiting for the next
    scheduled tick. Runs in the background since a full backfill can take a
    long time; poll /sync/status to watch progress."""

    def _run():
        session = SessionLocal()
        try:
            count = bootstrap(session)
            logger.info("manual bootstrap ingested %d events", count)
        finally:
            session.close()

    background_tasks.add_task(_run)
    return {"status": "started"}


@app.post("/sync/run")
def sync_run():
    """Run one bounded, synchronous sync cycle - useful for manual testing."""
    session = SessionLocal()
    try:
        count = run_sync_cycle(session)
        return {"ingested": count}
    finally:
        session.close()
