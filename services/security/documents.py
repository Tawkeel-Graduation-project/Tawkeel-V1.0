"""File upload validation and injection-in-document handling (SCRUM-391)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from services.security.trust import (
    DOCUMENT_TAG,
    detect_injection_signals,
    wrap_data_block,
)

ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".docx", ".txt"})
DEFAULT_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MiB

_PDF_MAGIC = b"%PDF-"
_DOCX_MAGIC = b"PK\x03\x04"


class DocumentSecurityError(ValueError):
    """Raised when an uploaded file fails extension, size, path, or magic checks."""


@dataclass(frozen=True)
class ValidatedDocument:
    """Result of validating an uploaded file."""

    filename: str
    extension: str
    size_bytes: int


def validate_uploaded_file(
    filename: str,
    content: bytes,
    *,
    max_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> ValidatedDocument:
    """Validate filename, extension, size, and magic bytes for V1 uploads.

    V1 accepts typed PDF, DOCX, and plain UTF-8 TXT files only (no OCR, no
    executables, no HTML/SVG scripts).
    """
    if not filename or "\x00" in filename:
        raise DocumentSecurityError("Invalid filename")
    if ".." in filename or "/" in filename or "\\" in filename:
        raise DocumentSecurityError("Path traversal characters are not allowed")

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise DocumentSecurityError(f"Unsupported file extension: {ext or 'none'}")

    if not content:
        raise DocumentSecurityError("Uploaded file is empty")
    if len(content) > max_bytes:
        raise DocumentSecurityError("Uploaded file exceeds maximum allowed size")

    if ext == ".pdf" and not content.startswith(_PDF_MAGIC):
        raise DocumentSecurityError("File content does not match PDF signature")
    if ext == ".docx" and not content.startswith(_DOCX_MAGIC):
        raise DocumentSecurityError("File content does not match DOCX signature")
    if ext == ".txt":
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DocumentSecurityError("TXT file must be valid UTF-8") from exc

    return ValidatedDocument(
        filename=filename,
        extension=ext,
        size_bytes=len(content),
    )


def prepare_document_for_llm(
    extracted_text: str, *, filename: str
) -> tuple[str, list[str]]:
    """Scan extracted document text for injection signals and wrap in <document>."""
    signals = detect_injection_signals(extracted_text)
    wrapped = wrap_data_block(
        DOCUMENT_TAG,
        extracted_text,
        attributes={"name": filename},
    )
    return wrapped, signals
