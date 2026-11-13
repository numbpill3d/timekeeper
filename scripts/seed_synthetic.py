"""Seed deterministic, hardware-free events for a local Timekeeper demo.

The script never creates users, changes camera credentials, or deletes data.
It upserts one inactive fixture camera and five events owned by an existing
account. Re-running it is safe because IDs are deterministic per fixture.
"""

from __future__ import annotations

import argparse
import asyncio
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


async def seed(database_url: str, owner_id: UUID, fixture: str, start: datetime) -> None:
    camera_id = _id(owner_id, fixture, "camera")
    person_id = _id(owner_id, fixture, "person-john")
    object_id = _id(owner_id, fixture, "object-blue-toolbox")
    events = [
        ("person_entered", start, "John entered the kitchen", "kitchen", None),
        (
            "object_picked_up",
            start + timedelta(minutes=5),
            "John picked up the blue toolbox",
            "kitchen",
            object_id,
        ),
        (
            "object_moved",
            start + timedelta(minutes=9),
            "John moved the blue toolbox from the kitchen to the garage",
            "garage",
            object_id,
        ),
        (
            "object_placed",
            start + timedelta(minutes=11),
            "John placed the blue toolbox in the garage",
            "garage",
            object_id,
        ),
        (
            "person_exited",
            start + timedelta(minutes=15),
            "John left the garage",
            "garage",
            None,
        ),
    ]

    conn = await asyncpg.connect(database_url)
    try:
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
                camera_id,
                owner_id,
                f"Synthetic demo · {fixture}",
                "file:///tmp/timekeeper-synthetic-fixture.mp4",
                "kitchen → garage",
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
                camera_id,
                events[-1][1],
            )
            for index, (event_type, timestamp, action, location, event_object_id) in enumerate(events):
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
                    camera_id,
                    event_type,
                    timestamp,
                    person_id,
                    event_object_id,
                    location,
                    action,
                    '{"fixture":"synthetic"}',
                )
    finally:
        await conn.close()

    print(f"seeded synthetic fixture '{fixture}' for owner {owner_id}")
    print(f"camera: {camera_id}")
    print(f"events: {len(events)} from {events[0][1].isoformat()}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--owner-id",
        type=UUID,
        default=os.getenv("TIMEKEEPER_DEMO_OWNER_ID"),
        required=os.getenv("TIMEKEEPER_DEMO_OWNER_ID") is None,
        help="existing Timekeeper user UUID (or TIMEKEEPER_DEMO_OWNER_ID)",
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
    asyncio.run(seed(args.database_url, args.owner_id, args.fixture, _base_time(args.start)))


if __name__ == "__main__":
    main()
