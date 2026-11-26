"""Pure Markdown journal store for the Scriptorium.

Reads and writes daily entries (`YYYY-MM-DD.md`) in `GRIMOIRE_JOURNAL_DIR`,
strictly ignoring internal files prefixed with `_` (such as `_propagated.md`) or `.`.
"""

from __future__ import annotations

import os
import re
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from grimoire.config import JOURNAL_DIR as DEFAULT_JOURNAL_DIR
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MARKDOWN_STRIP_RE = re.compile(r"^[#>*`\-\s]+", re.MULTILINE)
_WHITESPACE_RE = re.compile(r"\s+")


def _count_words(text: str) -> int:
    if not text or not text.strip():
        return 0
    return len(text.split())


def _iso_mtime(path: Path) -> str:
    ts = path.stat().st_mtime
    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


def _make_preview(content: str, query: str | None = None, max_len: int = 140) -> str:
    """Generate a clean ~140-char snippet, centered on `query` when searching."""
    if not content or not content.strip():
        return ""
    cleaned = _MARKDOWN_STRIP_RE.sub("", content)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    if not cleaned:
        return ""

    if query and query.strip():
        q_lower = query.strip().lower()
        idx = cleaned.lower().find(q_lower)
        if idx > max_len // 2:
            start = max(0, idx - 45)
            # Snap forward to word boundary
            space_idx = cleaned.find(" ", start)
            if 0 < space_idx < idx:
                start = space_idx + 1
            window = cleaned[start : start + max_len]
            prefix = "…" if start > 0 else ""
            suffix = "…" if (start + max_len) < len(cleaned) else ""
            return f"{prefix}{window.rstrip()}{suffix}"

    if len(cleaned) <= max_len:
        return cleaned
    truncated = cleaned[:max_len]
    last_space = truncated.rfind(" ")
    if last_space > max_len * 0.6:
        truncated = truncated[:last_space]
    return truncated.rstrip(" ,;:-") + "…"


class JournalStore:
    """Filesystem-backed store for pure Markdown journal entries."""

    def __init__(self, journal_dir: Path | str | None = None) -> None:
        self.journal_dir = Path(journal_dir) if journal_dir else DEFAULT_JOURNAL_DIR

    def _validate_key(self, date_key: str) -> str:
        if not date_key or not isinstance(date_key, str):
            raise ValueError("Invalid journal entry key.")
        clean = date_key.strip()
        if clean.lower().endswith(".md"):
            clean = clean[:-3]
        if (
            not clean
            or clean.startswith("_")
            or clean.startswith(".")
            or "/" in clean
            or "\\" in clean
            or ".." in clean
            or any(ord(ch) < 32 for ch in clean)
        ):
            raise ValueError(f"Disallowed journal entry key: {date_key!r}")
        return clean

    def _resolve_path(self, date_key: str) -> tuple[str, Path]:
        clean = self._validate_key(date_key)
        base = self.journal_dir.resolve()
        target = (base / f"{clean}.md").resolve()
        if target.parent != base:
            raise ValueError(f"Journal path escapes root directory: {date_key!r}")
        return clean, target

    def _iter_entry_files(self) -> list[Path]:
        if not self.journal_dir.exists():
            return []
        files: list[Path] = []
        for p in self.journal_dir.iterdir():
            if not p.is_file():
                continue
            name = p.name
            if name.startswith("_") or name.startswith("."):
                continue
            if p.suffix.lower() != ".md":
                continue
            files.append(p)

        def _sort_key(path: Path) -> tuple[int, str, float]:
            stem = path.stem
            try:
                mtime = path.stat().st_mtime
            except OSError:
                mtime = 0.0
            if _ISO_DATE_RE.match(stem):
                return (1, stem, mtime)
            # Non-ISO markdown filenames sort by mtime below ISO-dated entries or alongside
            iso_from_mtime = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
            return (0, iso_from_mtime, mtime)

        files.sort(key=_sort_key, reverse=True)
        return files

    def _atomic_write_utf8(self, target: Path, content: str) -> None:
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=".tmp_grimoire_",
            suffix=".md",
            dir=str(self.journal_dir),
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(content)
                fh.flush()
                os.fsync(fh.fileno())
            # Retry briefly in case file sync momentarily holds a handle on Windows
            for attempt in range(4):
                try:
                    os.replace(tmp_path, target)
                    break
                except PermissionError:
                    if attempt == 3:
                        raise
                    time.sleep(0.06 * (attempt + 1))
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def list_entries(self, query: str | None = None) -> list[dict[str, Any]]:
        """List journal entries newest-first, optionally filtered by search query."""
        q = query.strip().lower() if query and query.strip() else None
        results: list[dict[str, Any]] = []
        for path in self._iter_entry_files():
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            date_str = path.stem
            if q:
                haystack_hit = (
                    q in date_str.lower()
                    or q in path.name.lower()
                    or q in content.lower()
                )
                if not haystack_hit:
                    continue

            results.append(
                {
                    "date": date_str,
                    "filename": path.name,
                    "word_count": _count_words(content),
                    "preview": _make_preview(content, query=query, max_len=140),
                    "updated_at": _iso_mtime(path),
                }
            )
        return results

    def get_entry(self, date_key: str) -> dict[str, Any]:
        """Read a single journal entry without creating missing files on disk."""
        clean, target = self._resolve_path(date_key)
        if not target.exists():
            return {
                "date": clean,
                "filename": f"{clean}.md",
                "content": "",
                "exists": False,
                "word_count": 0,
                "updated_at": None,
            }
        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = target.read_text(encoding="utf-8", errors="replace")
        return {
            "date": clean,
            "filename": target.name,
            "content": content,
            "exists": True,
            "word_count": _count_words(content),
            "updated_at": _iso_mtime(target),
        }

    def save_entry(self, date_key: str, content: str) -> dict[str, Any]:
        """Save entry atomically in UTF-8; avoids creating empty files if not yet created."""
        clean, target = self._resolve_path(date_key)
        text = content if content is not None else ""
        if not target.exists() and not text.strip():
            return {
                "date": clean,
                "filename": f"{clean}.md",
                "content": "",
                "exists": False,
                "word_count": 0,
                "updated_at": None,
            }
        self._atomic_write_utf8(target, text)
        return {
            "date": clean,
            "filename": target.name,
            "content": text,
            "exists": True,
            "word_count": _count_words(text),
            "updated_at": _iso_mtime(target),
        }

    def inscribe(
        self,
        date_key: str,
        text: str,
        *,
        source: str | None = None,
        spread_summary: str | None = None,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        """Append a chosen Oracle omen or Pythia quote as an atmospheric Markdown blockquote."""
        clean, target = self._resolve_path(date_key)
        cleaned_quote = (text or "").strip()
        if not cleaned_quote:
            raise ValueError("Cannot inscribe an empty passage.")

        now_label = timestamp or datetime.now().strftime("%H:%M")
        meta_parts = [p.strip() for p in (source, spread_summary, now_label) if p and p.strip()]
        attribution = " · ".join(meta_parts) if meta_parts else now_label

        raw_lines = cleaned_quote.splitlines()
        quoted_lines: list[str] = [f"> *From the Chasm — {attribution}*", ">"]
        for line in raw_lines:
            stripped_end = line.rstrip()
            if stripped_end:
                quoted_lines.append(f"> {stripped_end}")
            else:
                quoted_lines.append(">")
        blockquote_block = "\n".join(quoted_lines)

        existing = ""
        if target.exists():
            try:
                existing = target.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                existing = target.read_text(encoding="utf-8", errors="replace")

        if existing.strip():
            combined = existing.rstrip() + "\n\n" + blockquote_block + "\n"
        else:
            combined = blockquote_block + "\n"

        self._atomic_write_utf8(target, combined)
        return {
            "date": clean,
            "filename": target.name,
            "content": combined,
            "exists": True,
            "word_count": _count_words(combined),
            "updated_at": _iso_mtime(target),
        }
