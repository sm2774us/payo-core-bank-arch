"""Outbox relay: polls unrelayed OutboxEvent rows and publishes them to Kafka.

Runs as a separate process/container (see docker-compose.yml, service
`outbox-relay`) so a slow or unavailable Kafka broker never blocks the API's
request/response path — the ledger write already committed; this just makes
it visible to downstream consumers (mint/burn engine, sanctions gate, etc.).

At-least-once delivery to Kafka + an idempotent consumer on the other side is
the standard, defensible pattern for exactly-once *effects* without requiring
distributed transactions across Postgres and Kafka.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.config import get_settings
from app.domain.models import OutboxEvent
from app.infra import db as db_module

logger = logging.getLogger("outbox_relay")


class KafkaPublisher:
    """Thin interface so tests can substitute an in-memory fake instead of a
    real broker. Real implementation: aiokafka's AIOKafkaProducer."""

    async def publish(self, topic: str, key: str, value: bytes) -> None:  # pragma: no cover
        raise NotImplementedError


class InMemoryPublisher(KafkaPublisher):
    def __init__(self) -> None:
        self.published: list[tuple[str, str, bytes]] = []

    async def publish(self, topic: str, key: str, value: bytes) -> None:
        self.published.append((topic, key, value))


async def relay_once(publisher: KafkaPublisher, batch_size: int = 100) -> int:
    settings = get_settings()
    relayed = 0
    async with db_module.SessionLocal() as session:
        result = await session.execute(
            select(OutboxEvent)
            .where(OutboxEvent.relayed_at.is_(None))
            .order_by(OutboxEvent.created_at)
            .limit(batch_size)
        )
        events = result.scalars().all()
        for event in events:
            await publisher.publish(
                topic=settings.outbox_topic,
                key=event.aggregate_id,
                value=json.dumps(
                    {"event_type": event.event_type, "payload": json.loads(event.payload)}
                ).encode(),
            )
            event.relayed_at = datetime.now(timezone.utc)
            relayed += 1
        if events:
            await session.commit()
    return relayed


async def run_forever(publisher: KafkaPublisher, poll_interval_seconds: float = 1.0) -> None:  # pragma: no cover
    while True:
        n = await relay_once(publisher)
        if n:
            logger.info("relayed %d outbox events", n)
        await asyncio.sleep(poll_interval_seconds)
