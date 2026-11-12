"""
Alert engine: consumes events, evaluates rules, fires notifications.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

import asyncpg
from aiokafka import AIOKafkaConsumer
from omniscient_shared.kafka.topics import EVENTS, GROUP_ALERT_ENGINE
from omniscient_shared.models.event import Event

from .notifier import deliver
from .rules import compile_rule, compile_rule_llm, event_matches, normalize_rule

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

_BROKERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
_DB_URL = os.getenv("DATABASE_URL", "")


async def main() -> None:
    consumer = AIOKafkaConsumer(
        EVENTS,
        bootstrap_servers=_BROKERS,
        group_id=GROUP_ALERT_ENGINE,
        value_deserializer=lambda v: json.loads(v.decode()),
    )
    consumer_started = False
    db: asyncpg.Connection | None = None
    try:
        await consumer.start()
        consumer_started = True
        db = await asyncpg.connect(_DB_URL)
        log.info("alert engine started")
        async for msg in consumer:
            try:
                event = Event(**msg.value)
            except (TypeError, ValueError) as exc:
                log.warning("dropping malformed event message: %s", exc)
                continue
            await _evaluate(event, db)
    finally:
        if consumer_started:
            await consumer.stop()
        if db:
            await db.close()


async def _evaluate(event: Event, db: asyncpg.Connection) -> None:
    rules = await db.fetch(
        """
        SELECT ar.*
        FROM alert_rules ar
        JOIN cameras c ON c.owner_id = ar.owner_id
        WHERE c.id = $1 AND ar.is_active = TRUE
        """,
        event.camera_id,
    )

    person_label: str | None = None
    person_is_known: bool = False
    if event.person_id:
        row = await db.fetchrow(
            "SELECT label, is_known FROM persons WHERE id = $1", event.person_id
        )
        if row:
            person_label = row["label"]
            person_is_known = row["is_known"]

    object_category: str | None = None
    if event.object_id:
        row = await db.fetchrow(
            "SELECT category FROM tracked_objects WHERE id = $1", event.object_id
        )
        if row:
            object_category = row["category"]

    for rule_row in rules:
        compiled = rule_row["compiled_rule"]

        if compiled is None:
            compiled = compile_rule(rule_row["rule_text"])
            if not compiled:
                compiled = await compile_rule_llm(rule_row["rule_text"])
            compiled = normalize_rule(compiled)
            if not compiled:
                # An unknown or invalid rule must not degrade into a
                # match-all predicate. Keep it disabled until edited.
                compiled = {"_disabled": True}
            await db.execute(
                "UPDATE alert_rules SET compiled_rule = $1 WHERE id = $2",
                json.dumps(compiled),
                rule_row["id"],
            )
        else:
            compiled = normalize_rule(compiled)
            if not compiled:
                continue

        if not event_matches(
            event,
            compiled,
            person_label=person_label,
            person_is_known=person_is_known,
            object_category=object_category,
        ):
            continue

        user_row = await db.fetchrow(
            "SELECT fcm_token, phone FROM users WHERE id = $1",
            rule_row["owner_id"],
        )
        fcm_token = user_row["fcm_token"] if user_row else None
        phone = user_row["phone"] if user_row else None

        priority = rule_row["priority"]
        title = _title(priority, event)
        body = event.action_label

        delivery_id = await db.fetchval(
            """
            INSERT INTO alert_deliveries (rule_id, event_id, channels_sent)
            VALUES ($1, $2, $3)
            ON CONFLICT (rule_id, event_id) DO NOTHING
            RETURNING id
            """,
            rule_row["id"],
            event.id,
            [],
        )
        if delivery_id is None:
            log.info(
                "skipping duplicate alert delivery for rule %s/event %s",
                rule_row["id"],
                event.id,
            )
            continue

        sent = await deliver(
            channels=list(rule_row["channels"]),
            title=title,
            body=body,
            fcm_token=fcm_token,
            phone=phone,
        )

        await db.execute(
            "UPDATE alert_deliveries SET channels_sent = $1 WHERE id = $2",
            sent,
            delivery_id,
        )


def _title(priority: str, event: Event) -> str:
    if priority == "critical":
        return f"CRITICAL: {event.event_type.value.replace('_', ' ').title()}"
    return event.event_type.value.replace("_", " ").title()


if __name__ == "__main__":
    asyncio.run(main())
