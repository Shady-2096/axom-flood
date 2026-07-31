"""Shared provenance and reviewed-geometry guards for external raster sources.

The external adapters deliberately do not own a mutable "latest" file. They
produce content-addressed source revisions which a later publication layer may
reference. A parser failure therefore cannot erase or replace the bytes that
caused it.

Likewise, a display point or an unreviewed administrative outline is never
accepted as an analytical boundary. Callers must provide an explicitly reviewed
geometry reference before preparing a zonal, reach, scene/AOI, or terrain join.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"[^a-z0-9._-]+")


class ProvenanceError(ValueError):
    """Raised when bytes do not match their declared immutable revision."""


class GeometryReviewRequired(ValueError):
    """Raised when an analytical spatial operation lacks reviewed geometry."""


def require_aware(moment: datetime, field: str) -> datetime:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError(f"{field} must include a UTC offset")
    return moment


def parse_aware_datetime(value: str, field: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO 8601 date-time") from exc
    return require_aware(parsed, field)


@dataclass(frozen=True, slots=True)
class SourceRevision:
    """Identity of one exact upstream response body."""

    source_id: str
    source_url: str
    fetched_at: datetime
    sha256: str
    byte_length: int
    media_type: str

    def __post_init__(self) -> None:
        require_aware(self.fetched_at, "fetched_at")
        if not self.source_id.strip():
            raise ValueError("source_id must not be empty")
        if not self.source_url.startswith(("https://", "fixture://")):
            raise ValueError("source_url must be an HTTPS or fixture URL")
        if not _SHA256.fullmatch(self.sha256):
            raise ValueError("sha256 must be a lowercase 64-character digest")
        if self.byte_length < 0:
            raise ValueError("byte_length must be non-negative")
        if not self.media_type:
            raise ValueError("media_type must not be empty")

    @classmethod
    def capture(
        cls,
        content: bytes,
        *,
        source_id: str,
        source_url: str,
        fetched_at: datetime,
        media_type: str,
    ) -> SourceRevision:
        return cls(
            source_id=source_id,
            source_url=source_url,
            fetched_at=fetched_at,
            sha256=hashlib.sha256(content).hexdigest(),
            byte_length=len(content),
            media_type=media_type,
        )

    def verify(self, content: bytes) -> None:
        digest = hashlib.sha256(content).hexdigest()
        if digest != self.sha256 or len(content) != self.byte_length:
            raise ProvenanceError(
                f"{self.source_id} bytes do not match revision {self.sha256}"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_url": self.source_url,
            "fetched_at": self.fetched_at.isoformat(),
            "sha256": self.sha256,
            "byte_length": self.byte_length,
            "media_type": self.media_type,
        }


@dataclass(frozen=True, slots=True)
class GeometryReference:
    """A content-addressed analytical geometry and its human-review state."""

    geometry_id: str
    sha256: str
    review_status: str
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None

    def __post_init__(self) -> None:
        if not self.geometry_id.strip():
            raise ValueError("geometry_id must not be empty")
        if not _SHA256.fullmatch(self.sha256):
            raise ValueError("geometry sha256 must be a lowercase 64-character digest")
        if self.review_status not in {"reviewed", "unreviewed"}:
            raise ValueError("review_status must be reviewed or unreviewed")
        if self.reviewed_at is not None:
            require_aware(self.reviewed_at, "reviewed_at")

    def require_reviewed(self, purpose: str) -> None:
        if (
            self.review_status != "reviewed"
            or self.reviewed_at is None
            or not (self.reviewed_by or "").strip()
        ):
            raise GeometryReviewRequired(
                f"{purpose} requires a content-addressed geometry with reviewer and review time"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "geometry_id": self.geometry_id,
            "sha256": self.sha256,
            "review_status": self.review_status,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "reviewed_by": self.reviewed_by,
        }


def write_immutable_revision(
    content: bytes,
    *,
    directory: Path,
    revision: SourceRevision,
    suffix: str,
) -> Path:
    """Atomically publish source bytes under their digest without overwriting.

    A retry of the same response is idempotent. If a file already exists under
    the digest but does not contain the same bytes, publication fails loudly.
    """

    revision.verify(content)
    safe_source = _SAFE_ID.sub("-", revision.source_id.casefold()).strip("-")
    if not safe_source:
        raise ValueError("source_id has no filesystem-safe characters")
    if not suffix.startswith(".") or "/" in suffix:
        raise ValueError("suffix must be a simple extension beginning with '.'")

    target_dir = directory / safe_source
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{revision.sha256}{suffix}"
    if target.exists():
        revision.verify(target.read_bytes())
        return target

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{revision.sha256}.",
        suffix=".tmp",
        dir=target_dir,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            revision.verify(target.read_bytes())
        return target
    finally:
        temporary.unlink(missing_ok=True)
