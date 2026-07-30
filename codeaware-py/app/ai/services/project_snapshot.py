"""Safe, deterministic, read-only local project snapshot for C1-E."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import stat
import time
from datetime import datetime, timezone
from pathlib import Path

from pathspec import PathSpec

from app.core.config import settings
from app.core.exceptions import BusinessException
from app.schemas.project_snapshot import (
    ProjectSnapshot,
    SkippedSnapshotPath,
    SnapshotFile,
)

SNAPSHOT_DISABLED = "AI_README_SNAPSHOT_DISABLED"
ROOTS_UNAVAILABLE = "AI_README_SNAPSHOT_ROOTS_UNAVAILABLE"
PROJECT_PATH_INVALID = "AI_README_PROJECT_PATH_INVALID"
PROJECT_NOT_FOUND = "AI_README_PROJECT_NOT_FOUND"
PROJECT_NOT_DIRECTORY = "AI_README_PROJECT_NOT_DIRECTORY"
PROJECT_OUTSIDE_ROOTS = "AI_README_PROJECT_OUTSIDE_ALLOWED_ROOTS"
SYMLINK_NOT_ALLOWED = "AI_README_SYMLINK_NOT_ALLOWED"
NON_REGULAR_FILE = "AI_README_NON_REGULAR_FILE"
SNAPSHOT_EMPTY = "AI_README_SNAPSHOT_EMPTY"
SNAPSHOT_LIMIT_EXCEEDED = "AI_README_SNAPSHOT_LIMIT_EXCEEDED"
SNAPSHOT_READ_FAILED = "AI_README_SNAPSHOT_READ_FAILED"
TRUNCATION_MARKER = "\n[TRUNCATED_BY_C1_SNAPSHOT_LIMIT]\n"

_DENIED_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".cache",
    ".next",
    "coverage",
    "dist",
    "build",
    "target",
}
_SECRET_NAMES = {
    ".npmrc",
    ".pypirc",
    "credentials",
    "credentials.json",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
    "secrets.json",
    "secrets.yaml",
    "secrets.yml",
}
_SECRET_SUFFIXES = {".cer", ".crt", ".der", ".key", ".p12", ".pfx", ".pem"}
_TEXT_SUFFIXES = {
    ".bash",
    ".c",
    ".cfg",
    ".conf",
    ".cpp",
    ".cs",
    ".css",
    ".dockerfile",
    ".go",
    ".gradle",
    ".h",
    ".hpp",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".kts",
    ".md",
    ".mdx",
    ".php",
    ".properties",
    ".py",
    ".pyi",
    ".rb",
    ".rs",
    ".rst",
    ".scala",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
    ".zsh",
}
_MANIFEST_NAMES = {
    "cargo.lock",
    "cargo.toml",
    "compose.yaml",
    "compose.yml",
    "docker-compose.yaml",
    "docker-compose.yml",
    "dockerfile",
    "go.mod",
    "go.sum",
    "makefile",
    "package-lock.json",
    "package.json",
    "pnpm-lock.yaml",
    "pom.xml",
    "procfile",
    "pyproject.toml",
    "requirements.txt",
    "settings.gradle",
    "settings.gradle.kts",
    "uv.lock",
    "yarn.lock",
}
_ENTRYPOINT_PATHS = {
    "app/main.py",
    "main.py",
    "src/app.ts",
    "src/app.tsx",
    "src/index.js",
    "src/index.ts",
    "src/main.java",
    "src/main.js",
    "src/main.py",
    "src/main.rs",
    "src/main.ts",
    "src/main.tsx",
}


class ProjectSnapshotService:
    """Builds a bounded prompt payload without writing to the source project."""

    def __init__(
        self,
        *,
        enabled: bool,
        allowed_roots: list[Path],
        max_files: int,
        max_file_bytes: int,
        max_total_bytes: int,
        max_prompt_chars: int,
        timeout_seconds: float,
    ) -> None:
        self.enabled = enabled
        self.allowed_roots = allowed_roots
        self.max_files = max_files
        self.max_file_bytes = max_file_bytes
        self.max_total_bytes = max_total_bytes
        self.max_prompt_chars = max_prompt_chars
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_settings(cls) -> "ProjectSnapshotService":
        return cls(
            enabled=settings.ai_readme_snapshot_enabled,
            allowed_roots=list(settings.local_project_roots),
            max_files=settings.ai_readme_snapshot_max_files,
            max_file_bytes=settings.ai_readme_snapshot_max_file_bytes,
            max_total_bytes=settings.ai_readme_snapshot_max_total_bytes,
            max_prompt_chars=settings.ai_readme_snapshot_max_prompt_chars,
            timeout_seconds=settings.ai_readme_snapshot_timeout_seconds,
        )

    def capability(self) -> tuple[bool, str]:
        if not self.enabled:
            return False, "disabled"
        if not self._canonical_allowed_roots():
            return False, "roots_unavailable"
        return True, "available"

    async def build(self, project_path: str) -> ProjectSnapshot:
        enabled, reason = self.capability()
        if not enabled:
            raise BusinessException(
                SNAPSHOT_DISABLED if reason == "disabled" else ROOTS_UNAVAILABLE
            )
        try:
            async with asyncio.timeout(self.timeout_seconds):
                return await asyncio.to_thread(self._build_sync, project_path)
        except TimeoutError as exc:
            raise BusinessException(SNAPSHOT_LIMIT_EXCEEDED) from exc

    def _canonical_allowed_roots(self) -> list[Path]:
        roots: list[Path] = []
        for raw_root in self.allowed_roots:
            try:
                if not raw_root.is_absolute() or raw_root.is_symlink():
                    continue
                root = raw_root.resolve(strict=True)
                if root.is_dir():
                    roots.append(root)
            except (OSError, RuntimeError):
                continue
        return roots

    def _resolve_project_root(self, project_path: str) -> Path:
        raw = Path(project_path)
        if not project_path.strip() or not raw.is_absolute():
            raise BusinessException(PROJECT_PATH_INVALID)
        try:
            if raw.is_symlink():
                raise BusinessException(SYMLINK_NOT_ALLOWED)
            root = raw.resolve(strict=True)
        except FileNotFoundError as exc:
            raise BusinessException(PROJECT_NOT_FOUND) from exc
        except BusinessException:
            raise
        except (OSError, RuntimeError) as exc:
            raise BusinessException(SNAPSHOT_READ_FAILED) from exc
        if not root.is_dir():
            raise BusinessException(PROJECT_NOT_DIRECTORY)
        if not any(self._is_within(root, allowed) for allowed in self._canonical_allowed_roots()):
            raise BusinessException(PROJECT_OUTSIDE_ROOTS)
        return root

    @staticmethod
    def _is_within(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    def _build_sync(self, project_path: str) -> ProjectSnapshot:
        started = time.monotonic()
        project_root = self._resolve_project_root(project_path)
        ignore_spec = self._load_gitignore(project_root)
        skipped: list[SkippedSnapshotPath] = []
        candidates: list[tuple[str, Path, int]] = []
        total_bytes = 0

        for current_root, dir_names, file_names in os.walk(
            project_root,
            topdown=True,
            onerror=self._raise_read_failed,
            followlinks=False,
        ):
            self._check_deadline(started)
            current = Path(current_root)
            kept_dirs: list[str] = []
            for dir_name in sorted(dir_names):
                path = current / dir_name
                relative = path.relative_to(project_root).as_posix()
                if path.is_symlink():
                    raise BusinessException(SYMLINK_NOT_ALLOWED)
                if dir_name.lower() in _DENIED_DIR_NAMES:
                    skipped.append(SkippedSnapshotPath(path=relative, reason="denied"))
                    continue
                if ignore_spec and ignore_spec.match_file(f"{relative}/"):
                    skipped.append(SkippedSnapshotPath(path=relative, reason="gitignored"))
                    continue
                kept_dirs.append(dir_name)
            dir_names[:] = kept_dirs

            for file_name in sorted(file_names):
                self._check_deadline(started)
                path = current / file_name
                relative = path.relative_to(project_root).as_posix()
                if path.is_symlink():
                    raise BusinessException(SYMLINK_NOT_ALLOWED)
                if self._is_denied_file(file_name):
                    skipped.append(SkippedSnapshotPath(path=relative, reason="denied"))
                    continue
                if relative == ".gitignore":
                    skipped.append(SkippedSnapshotPath(path=relative, reason="unsupported"))
                    continue
                if ignore_spec and ignore_spec.match_file(relative):
                    skipped.append(SkippedSnapshotPath(path=relative, reason="gitignored"))
                    continue
                if not self._is_supported_text_path(relative):
                    skipped.append(SkippedSnapshotPath(path=relative, reason="unsupported"))
                    continue
                try:
                    metadata = path.lstat()
                except OSError as exc:
                    raise BusinessException(SNAPSHOT_READ_FAILED) from exc
                if not stat.S_ISREG(metadata.st_mode):
                    raise BusinessException(NON_REGULAR_FILE)
                if metadata.st_size > self.max_file_bytes:
                    raise BusinessException(SNAPSHOT_LIMIT_EXCEEDED)
                if len(candidates) >= self.max_files:
                    raise BusinessException(SNAPSHOT_LIMIT_EXCEEDED)
                total_bytes += metadata.st_size
                if total_bytes > self.max_total_bytes:
                    raise BusinessException(SNAPSHOT_LIMIT_EXCEEDED)
                candidates.append((relative, path, metadata.st_size))

        readable: list[SnapshotFile] = []
        for relative, path, size_bytes in candidates:
            self._check_deadline(started)
            content = self._read_utf8_regular_file(path)
            if content is None:
                skipped.append(SkippedSnapshotPath(path=relative, reason="binary"))
                continue
            readable.append(
                SnapshotFile(
                    path=relative,
                    kind=self._classify(relative),
                    size_bytes=size_bytes,
                    content=content,
                )
            )
        if not readable:
            raise BusinessException(SNAPSHOT_EMPTY)

        readable.sort(key=lambda item: (self._kind_rank(item.kind), item.path.casefold(), item.path))
        tree = sorted((item.path for item in readable), key=lambda value: (value.casefold(), value))
        files, truncated, prompt_payload = self._fit_prompt(tree, readable)
        if not files:
            raise BusinessException(SNAPSHOT_LIMIT_EXCEEDED)
        snapshot_hash = hashlib.sha256(prompt_payload.encode("utf-8")).hexdigest()
        skipped.sort(key=lambda item: (item.path.casefold(), item.path, item.reason))
        return ProjectSnapshot(
            snapshot_hash=snapshot_hash,
            file_count=len(files),
            total_bytes=sum(item.size_bytes for item in files),
            generated_at=datetime.now(timezone.utc),
            truncated=truncated,
            tree=tree,
            files=files,
            skipped=skipped,
            prompt_payload=prompt_payload,
        )

    def _load_gitignore(self, project_root: Path) -> PathSpec | None:
        path = project_root / ".gitignore"
        try:
            if not path.exists():
                return None
            if path.is_symlink():
                raise BusinessException(SYMLINK_NOT_ALLOWED)
            content = self._read_utf8_regular_file(path)
            if content is None:
                return None
            return PathSpec.from_lines("gitwildmatch", content.splitlines())
        except BusinessException:
            raise
        except OSError as exc:
            raise BusinessException(SNAPSHOT_READ_FAILED) from exc

    def _read_utf8_regular_file(self, path: Path) -> str | None:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
            with os.fdopen(descriptor, "rb") as stream:
                metadata = os.fstat(stream.fileno())
                if not stat.S_ISREG(metadata.st_mode):
                    raise BusinessException(NON_REGULAR_FILE)
                if metadata.st_size > self.max_file_bytes:
                    raise BusinessException(SNAPSHOT_LIMIT_EXCEEDED)
                payload = stream.read(self.max_file_bytes + 1)
        except BusinessException:
            raise
        except OSError as exc:
            raise BusinessException(SNAPSHOT_READ_FAILED) from exc
        if len(payload) > self.max_file_bytes:
            raise BusinessException(SNAPSHOT_LIMIT_EXCEEDED)
        if b"\x00" in payload[:8192]:
            return None
        try:
            return payload.decode("utf-8")
        except UnicodeDecodeError:
            return None

    def _fit_prompt(
        self,
        tree: list[str],
        readable: list[SnapshotFile],
    ) -> tuple[list[SnapshotFile], bool, str]:
        complete_payload = self._serialize_prompt_payload(tree, readable, False)
        if len(complete_payload) <= self.max_prompt_chars:
            return readable, False, complete_payload

        selected: list[SnapshotFile] = []
        for item in readable:
            full = [*selected, item]
            payload = self._serialize_prompt_payload(tree, full, True)
            if len(payload) <= self.max_prompt_chars:
                selected = full
                continue

            low, high = 0, len(item.content)
            best: SnapshotFile | None = None
            while low <= high:
                midpoint = (low + high) // 2
                candidate = item.model_copy(
                    update={
                        "content": item.content[:midpoint] + TRUNCATION_MARKER,
                        "truncated": True,
                    }
                )
                candidate_payload = self._serialize_prompt_payload(
                    tree,
                    [*selected, candidate],
                    True,
                )
                if len(candidate_payload) <= self.max_prompt_chars:
                    best = candidate
                    low = midpoint + 1
                else:
                    high = midpoint - 1
            if best is not None:
                selected.append(best)
            break

        payload = self._serialize_prompt_payload(tree, selected, True)
        if len(payload) > self.max_prompt_chars:
            return [], True, payload
        return selected, True, payload

    @staticmethod
    def _serialize_prompt_payload(
        tree: list[str],
        files: list[SnapshotFile],
        truncated: bool,
    ) -> str:
        value = {
            "tree": tree,
            "files": [
                {
                    "path": item.path,
                    "kind": item.kind,
                    "size_bytes": item.size_bytes,
                    "truncated": item.truncated,
                    "content": item.content,
                }
                for item in files
            ],
            "truncated": truncated,
        }
        canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return canonical.replace("<", "\\u003c").replace(">", "\\u003e")

    def _check_deadline(self, started: float) -> None:
        if time.monotonic() - started > self.timeout_seconds:
            raise BusinessException(SNAPSHOT_LIMIT_EXCEEDED)

    @staticmethod
    def _raise_read_failed(_: OSError) -> None:
        raise BusinessException(SNAPSHOT_READ_FAILED)

    @staticmethod
    def _is_denied_file(file_name: str) -> bool:
        lowered = file_name.lower()
        return (
            lowered.startswith(".env")
            or lowered in _SECRET_NAMES
            or Path(lowered).suffix in _SECRET_SUFFIXES
        )

    @staticmethod
    def _is_supported_text_path(relative: str) -> bool:
        path = Path(relative)
        lowered_name = path.name.lower()
        if lowered_name.startswith("readme"):
            return True
        if lowered_name in _MANIFEST_NAMES:
            return True
        if lowered_name.startswith(("requirements", "docker-compose", "compose.")):
            return True
        if lowered_name.startswith(("build.gradle", "settings.gradle", "tsconfig")):
            return True
        return path.suffix.lower() in _TEXT_SUFFIXES

    @staticmethod
    def _classify(relative: str) -> str:
        path = Path(relative)
        lowered_name = path.name.lower()
        lowered_path = relative.lower()
        if lowered_name.startswith("readme"):
            return "readme"
        if (
            lowered_name in _MANIFEST_NAMES
            or lowered_name.startswith(("requirements", "docker-compose", "compose."))
            or lowered_name.startswith(("build.gradle", "settings.gradle", "tsconfig"))
        ):
            return "manifest"
        if lowered_path in _ENTRYPOINT_PATHS:
            return "entrypoint"
        return "source"

    @staticmethod
    def _kind_rank(kind: str) -> int:
        return {"readme": 0, "manifest": 1, "entrypoint": 2, "source": 3}[kind]
