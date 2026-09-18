"""Idempotency-Key enforcement for mutating endpoints.

Pattern: client sends `Idempotency-Key: <uuid>`. We hash the request body and
look up (key). If found with the SAME body hash -> replay the stored response
(no re-execution). If found with a DIFFERENT hash -> 409 Conflict (client bug:
reusing a key for a different request). If not found -> caller executes the
operation, then we persist the result under this key in the SAME transaction.
"""
import hashlib
import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import IdempotencyKey


class IdempotencyConflict(Exception):
    """Same Idempotency-Key reused with a different request body."""


def hash_body(body: dict[str, Any]) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


async def get_cached_response(
    session: AsyncSession, key: str, body_hash: str
) -> tuple[int, str] | None:
    row = await session.get(IdempotencyKey, key)
    if row is None:
        return None
    if row.request_hash != body_hash:
        raise IdempotencyConflict(
            f"Idempotency-Key {key!r} was already used with a different request body"
        )
    return row.status_code, row.response_body


async def store_response(
    session: AsyncSession, key: str, body_hash: str, status_code: int, response_body: str
) -> None:
    session.add(
        IdempotencyKey(
            key=key,
            request_hash=body_hash,
            status_code=status_code,
            response_body=response_body,
        )
    )
