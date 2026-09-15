from pathlib import Path
import re
from uuid import uuid4

from app.core.config import get_settings
from app.core.security import sanitize_filename, sniff_source_type
from app.db.models import Source, SourceChunk
from app.services.parsers import get_parser
from app.services.parsers.base import ParseResult

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 120


def save_upload(filename: str, data: bytes, content_type: str) -> Source:
    settings = get_settings()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise ValueError("file_too_large")
    if not data:
        raise ValueError("empty_file")
    source_type = sniff_source_type(filename, data[:16])
    safe = sanitize_filename(filename)
    
    source = Source(
        id=str(uuid4()),
        filename=filename,
        safe_filename=safe,
        source_type=source_type,
        content_type=content_type or "application/octet-stream",
        size_bytes=len(data),
    )
    dest_dir = settings.upload_dir / source.id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / safe
    dest.write_bytes(data)
    source.storage_path = str(dest)
    return source


def _chunk_text_cleanly(text: str, max_chunk_size: int = CHUNK_SIZE) -> list[tuple[int, int, str]]:
    """Chunk text cleanly respecting paragraph and sentence boundaries without truncating words."""
    cleaned = text.strip()
    if not cleaned:
        return []

    if len(cleaned) <= max_chunk_size:
        return [(0, len(cleaned), cleaned)]

    # Split on double newline (paragraphs) first
    paragraphs = re.split(r"(\n\s*\n+)", cleaned)
    chunks: list[tuple[int, int, str]] = []
    current_chunk = ""
    current_start = 0
    running_offset = 0

    for piece in paragraphs:
        if not piece:
            continue
        if len(current_chunk) + len(piece) <= max_chunk_size:
            if not current_chunk:
                current_start = running_offset
            current_chunk += piece
        else:
            if current_chunk.strip():
                chunks.append((current_start, current_start + len(current_chunk), current_chunk.strip()))
            if len(piece) > max_chunk_size:
                # Split large paragraphs by sentence boundaries
                sentences = re.split(r"(?<=[.!?])\s+", piece)
                sub_chunk = ""
                sub_start = running_offset
                for s in sentences:
                    if len(sub_chunk) + len(s) + 1 <= max_chunk_size:
                        if not sub_chunk:
                            sub_start = running_offset
                        sub_chunk = (sub_chunk + " " + s).strip()
                    else:
                        if sub_chunk.strip():
                            chunks.append((sub_start, sub_start + len(sub_chunk), sub_chunk.strip()))
                        sub_chunk = s.strip()
                        sub_start = running_offset
                if sub_chunk.strip():
                    current_chunk = sub_chunk
                    current_start = sub_start
                else:
                    current_chunk = ""
            else:
                current_chunk = piece
                current_start = running_offset
        running_offset += len(piece)

    if current_chunk.strip():
        chunks.append((current_start, current_start + len(current_chunk), current_chunk.strip()))

    return chunks


def persist_chunks(source: Source, parse: ParseResult) -> list[SourceChunk]:
    chunks: list[SourceChunk] = []
    idx = 1
    total_chars = 0
    for page in parse.pages:
        text = page.text.strip()
        total_chars += len(text)
        pieces = _chunk_text_cleanly(text, CHUNK_SIZE)
        for start, end, chunk_text in pieces:
            # Discard any incomplete trailing fragments or empty chunks
            if not chunk_text.strip():
                continue
            chunks.append(
                SourceChunk(
                    source_id=source.id,
                    chunk_id=f"c{idx}",
                    page=page.page,
                    section=page.section,
                    start_char=start,
                    end_char=end,
                    text=chunk_text,
                )
            )
            idx += 1
    source.page_count = parse.page_count
    source.char_count = total_chars
    source.extract_preview = (parse.pages[0].text[:800] if parse.pages else "")[:800]
    return chunks


def extract_source(source: Source) -> tuple[list[SourceChunk], list[str]]:
    if source.source_type == "url":
        parser = get_parser("url")
        result = parser.parse(source.origin_url or source.storage_path or "")
    else:
        path = source.storage_path
        if not path or not Path(path).exists():
            raise ValueError("Source file is missing")
        parser = get_parser(source.source_type)
        result = parser.parse(path)
    chunks = persist_chunks(source, result)
    return chunks, result.warnings
