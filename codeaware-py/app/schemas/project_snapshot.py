"""Internal DTOs for the bounded C1-E local project snapshot."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


SnapshotFileKind = Literal["readme", "manifest", "entrypoint", "source"]


class SnapshotFile(BaseModel):
    path: str
    kind: SnapshotFileKind
    size_bytes: int
    content: str
    truncated: bool = False


class SkippedSnapshotPath(BaseModel):
    path: str
    reason: Literal["denied", "gitignored", "binary", "unsupported"]


class ProjectSnapshot(BaseModel):
    snapshot_hash: str
    file_count: int
    total_bytes: int
    generated_at: datetime
    truncated: bool
    tree: list[str]
    files: list[SnapshotFile]
    skipped: list[SkippedSnapshotPath]
    prompt_payload: str
