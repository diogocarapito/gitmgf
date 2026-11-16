"""Scheduler entry point: `python -m app.scheduler` (its own container, same image)."""

import logging
from collections.abc import Callable
from typing import Any

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app import jobs

log = logging.getLogger("gitmgf.scheduler")
TZ = "Europe/Lisbon"


def safe(fn: Callable[[], Any]) -> Callable[[], None]:
    def run() -> None:
        try:
            result = fn()
            log.info("job %s ok: %s", fn.__name__, result)
        except Exception:
            log.exception("job %s failed", fn.__name__)

    run.__name__ = fn.__name__
    return run


def build() -> BlockingScheduler:
    scheduler = BlockingScheduler(
        timezone=TZ, job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300}
    )
    scheduler.add_job(safe(jobs.send_outbox), IntervalTrigger(minutes=1), id="send_outbox")
    scheduler.add_job(safe(jobs.recompute_scores), IntervalTrigger(minutes=15), id="recompute_scores")
    scheduler.add_job(safe(jobs.rotate_salt), CronTrigger(hour=0, minute=0, timezone="UTC"), id="rotate_salt")
    scheduler.add_job(safe(jobs.sync_github), CronTrigger(hour=3, minute=30, timezone=TZ), id="sync_github")
    scheduler.add_job(safe(jobs.prune), CronTrigger(hour=4, minute=0, timezone=TZ), id="prune")
    scheduler.add_job(safe(jobs.cert_expiry), CronTrigger(hour=5, minute=0, timezone=TZ), id="cert_expiry")
    scheduler.add_job(safe(jobs.mod_digest), CronTrigger(hour=8, minute=0, timezone=TZ), id="mod_digest")
    scheduler.add_job(safe(jobs.heartbeat), IntervalTrigger(minutes=5), id="heartbeat")
    return scheduler


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    log.info("scheduler starting")
    build().start()


if __name__ == "__main__":
    main()
