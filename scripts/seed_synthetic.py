"""Seed deterministic, hardware-free events for a local Timekeeper demo.

The script never creates users, changes camera credentials, or deletes data.
It upserts two inactive fixture cameras and five events owned by an existing
account. Re-running it is safe because IDs are deterministic per fixture.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid5

import asyncpg

_FIXTURE_NAMESPACE = UUID("f15e7b1e-7c87-4d7f-9b6b-3c6a6c6f2d42")


def _id(owner_id: UUID, fixture: str, kind: str) -> UUID:
    return uuid5(_FIXTURE_NAMESPACE, f"{owner_id}:{fixture}:{kind}")


def _base_time(value: str | None) -> datetime:
    if value is None:
        now = datetime.now(tz=UTC).replace(second=0, microsecond=0)
        return now - timedelta(minutes=20)
    parsed = datetime.fromisoformat(value)
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)).astimezone(UTC)


async def seed(
    database_url: str,
    owner_id: UUID | None,
    owner_email: str | None,
    fixture: str,
    start: datetime,
) -> None:
    conn = await asyncpg.connect(database_url)
    try:
        if owner_id is None:
            row = await conn.fetchrow(
                "SELECT id FROM users WHERE lower(email) = lower($1)", owner_email
            )
            if not row:
                raise ValueError("no Timekeeper account matches --owner-email")
            owner_id = UUID(str(row["id"]))

        camera_id = _id(owner_id, fixture, "camera")
        garage_camera_id = _id(owner_id, fixture, "camera-garage")
        person_id = _id(owner_id, fixture, "person-john")
        object_id = _id(owner_id, fixture, "object-blue-toolbox")
        await _seed_rows(
            conn,
            owner_id,
            camera_id,
            garage_camera_id,
            person_id,
            object_id,
            fixture,
            start,
        )
    finally:
        await conn.close()

    print(f"seeded synthetic fixture '{fixture}' for owner {owner_id}")
    print(f"cameras: {camera_id}, {garage_camera_id}")
    print(f"events: 5 from {start.isoformat()}")


async def _seed_rows(
    conn: asyncpg.Connection,
    owner_id: UUID,
    kitchen_camera_id: UUID,
    garage_camera_id: UUID,
    person_id: UUID,
    object_id: UUID,
    fixture: str,
    start: datetime,
) -> None:
    events = _story_events(
        start,
        kitchen_camera_id,
        garage_camera_id,
        person_id,
        object_id,
        fixture,
    )

    async with conn.transaction():
        await conn.execute(
            """
                INSERT INTO cameras
                    (id, owner_id, name, stream_url, protocol, location_label, is_active)
                VALUES ($1, $2, $3, $4, 'file', $5, FALSE)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    location_label = EXCLUDED.location_label,
                    is_active = FALSE
                """,
            kitchen_camera_id,
            owner_id,
            f"Synthetic demo · {fixture} · kitchen",
            "file:///tmp/timekeeper-synthetic-fixture.mp4",
            "kitchen",
        )
        await conn.execute(
            """
                INSERT INTO cameras
                    (id, owner_id, name, stream_url, protocol, location_label, is_active)
                VALUES ($1, $2, $3, $4, 'file', $5, FALSE)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    location_label = EXCLUDED.location_label,
                    is_active = FALSE
                """,
            garage_camera_id,
            owner_id,
            f"Synthetic demo · {fixture} · garage",
            "file:///tmp/timekeeper-synthetic-fixture.mp4",
            "garage",
        )
        await conn.execute(
            """
                INSERT INTO persons (id, owner_id, label, is_known)
                VALUES ($1, $2, 'John', TRUE)
                ON CONFLICT (id) DO UPDATE SET label = EXCLUDED.label, is_known = TRUE
                """,
            person_id,
            owner_id,
        )
        await conn.execute(
            """
                INSERT INTO tracked_objects (id, owner_id, category, label, last_camera_id, last_seen_at)
                VALUES ($1, $2, 'tool', 'blue toolbox', $3, $4)
                ON CONFLICT (id) DO UPDATE SET
                    label = EXCLUDED.label,
                    last_camera_id = EXCLUDED.last_camera_id,
                    last_seen_at = EXCLUDED.last_seen_at
                """,
            object_id,
            owner_id,
            garage_camera_id,
            events[-1]["timestamp"],
        )
        for index, event in enumerate(events):
            event_id = _id(owner_id, fixture, f"event-{index}")
            await conn.execute(
                """
                    INSERT INTO events
                        (id, camera_id, event_type, timestamp, person_id, object_id,
                         location_label, action_label, confidence, metadata, clip_path)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 0.98, $9::jsonb, NULL)
                    ON CONFLICT (id, timestamp) DO UPDATE SET
                        event_type = EXCLUDED.event_type,
                        person_id = EXCLUDED.person_id,
                        object_id = EXCLUDED.object_id,
                        location_label = EXCLUDED.location_label,
                        action_label = EXCLUDED.action_label,
                        confidence = EXCLUDED.confidence,
                        metadata = EXCLUDED.metadata
                    """,
                event_id,
                event["camera_id"],
                event["event_type"],
                event["timestamp"],
                event["person_id"],
                event["object_id"],
                event["location"],
                event["action"],
                json.dumps(event["metadata"]),
            )


def _story_events(
    start: datetime,
    kitchen_camera_id: UUID,
    garage_camera_id: UUID,
    person_id: UUID,
    object_id: UUID,
    fixture: str,
) -> list[dict]:
    """Return the deterministic five-event investigation story."""
    return [
        {
            "event_type": "person_entered",
            "timestamp": start,
            "action": "Person entered kitchen",
            "location": "kitchen",
            "camera_id": kitchen_camera_id,
            "person_id": person_id,
            "object_id": None,
            "metadata": {"fixture": "synthetic"},
        },
        {
            "event_type": "object_picked_up",
            "timestamp": start + timedelta(minutes=5),
            "action": "Blue toolbox picked up",
            "location": "kitchen",
            "camera_id": kitchen_camera_id,
            "person_id": person_id,
            "object_id": object_id,
            "metadata": {"fixture": "synthetic"},
        },
        {
            "event_type": "object_moved",
            "timestamp": start + timedelta(minutes=9),
            "action": "moved blue toolbox from kitchen to garage",
            "location": "garage",
            "camera_id": garage_camera_id,
            "person_id": person_id,
            "object_id": object_id,
            "metadata": {
                "fixture": "synthetic",
                "from_camera_name": f"Synthetic demo · {fixture} · kitchen",
                "to_camera_name": f"Synthetic demo · {fixture} · garage",
            },
        },
        {
            "event_type": "object_placed",
            "timestamp": start + timedelta(minutes=11),
            "action": "Blue toolbox placed at garage",
            "location": "garage",
            "camera_id": garage_camera_id,
            "person_id": person_id,
            "object_id": object_id,
            "metadata": {"fixture": "synthetic"},
        },
        {
            "event_type": "person_exited",
            "timestamp": start + timedelta(minutes=15),
            "action": "Person left garage",
            "location": "garage",
            "camera_id": garage_camera_id,
            "person_id": person_id,
            "object_id": None,
            "metadata": {"fixture": "synthetic"},
        },
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    owner_group = parser.add_mutually_exclusive_group()
    owner_group.add_argument(
        "--owner-id",
        type=UUID,
        default=os.getenv("TIMEKEEPER_DEMO_OWNER_ID"),
        help="existing Timekeeper user UUID (or TIMEKEEPER_DEMO_OWNER_ID)",
    )
    owner_group.add_argument(
        "--owner-email",
        default=os.getenv("TIMEKEEPER_DEMO_OWNER_EMAIL"),
        help="existing Timekeeper account email (or TIMEKEEPER_DEMO_OWNER_EMAIL)",
    )
    parser.add_argument("--fixture", default="toolbox-demo", help="stable fixture name")
    parser.add_argument(
        "--start",
        help="UTC ISO-8601 start time; defaults to 20 minutes ago",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        required=os.getenv("DATABASE_URL") is None,
        help="PostgreSQL URL (or DATABASE_URL)",
    )
    args = parser.parse_args()
    if args.owner_id is None and not args.owner_email:
        parser.error("provide --owner-id or --owner-email")
    asyncio.run(
        seed(
            args.database_url,
            args.owner_id,
            args.owner_email,
            args.fixture,
            _base_time(args.start),
        )
    )


if __name__ == "__main__":
    main()
