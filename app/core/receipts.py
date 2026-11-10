"""Profile-scoped receipt path validation, resolution, and URL helpers."""

from __future__ import annotations

import copy
import mimetypes
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from fastapi import HTTPException, status
from fastapi.responses import FileResponse

from app import config as app_config
from app.core import profiles as profiles_module
from app.core.profiles import ProfileMetadata


def build_transaction_receipt_url(
    transaction_id: int,
    leg: str = "source",
    download: bool = False,
) -> str:
    """Return the API endpoint path for a transaction's receipt attachment."""
    base = f"/api/transactions/{transaction_id}/receipt"
    params: List[str] = []
    if leg == "destination":
        params.append("leg=destination")
    if download:
        params.append("download=true")
    return f"{base}?{'&'.join(params)}" if params else base


def build_staging_receipt_url(item_id: int, download: bool = False) -> str:
    """Return the API endpoint path for a staging item's receipt preview."""
    base = f"/api/staging/{item_id}/receipt"
    return f"{base}?download=true" if download else base


def normalize_transfer_provenance_urls(
    provenance: Optional[Dict[str, Any]],
    transaction_id: int,
) -> Optional[Dict[str, Any]]:
    """Return a copy of provenance metadata with current receipt endpoints instead of legacy /static links."""
    if not provenance or not isinstance(provenance, dict):
        return provenance

    normalized = copy.deepcopy(provenance)
    for leg_key, leg_name in (("source_leg", "source"), ("destination_leg", "destination")):
        leg = normalized.get(leg_key)
        if isinstance(leg, dict):
            if leg.get("receipt_path"):
                leg["receipt_url"] = build_transaction_receipt_url(transaction_id, leg=leg_name)
            else:
                leg["receipt_url"] = None
    return normalized


def _has_traversal_or_control(raw_path: str) -> bool:
    if "\x00" in raw_path:
        return True
    normalized_slashes = raw_path.replace("\\", "/")
    parts = [part for part in normalized_slashes.split("/") if part]
    return ".." in parts


def _contains_symlink_escape(candidate: Path, raw_root: Path, resolved_root: Path) -> bool:
    """Reject symlinks anywhere between the permitted directory root and the target file."""
    matched_root: Optional[Path] = None
    for root in (raw_root, resolved_root):
        try:
            candidate.relative_to(root)
            matched_root = root
            break
        except ValueError:
            continue

    if matched_root is None:
        return True

    cursor = matched_root
    for part in candidate.relative_to(matched_root).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            return True
    return False


def _permitted_roots(profile: ProfileMetadata) -> List[Path]:
    return [profile.receipts_dir, profile.staging_receipts_dir]


def resolve_profile_receipt_file(
    raw_path: Optional[str],
    profile: ProfileMetadata,
) -> Optional[Path]:
    """Resolve a stored receipt path strictly inside the active profile's permitted directories.

    Returns the resolved existing regular file Path, or None if missing, unsafe,
    symlink-escaped, or outside the active profile's receipt/staging directories.
    """
    if not raw_path or not isinstance(raw_path, str):
        return None

    cleaned = raw_path.strip()
    if not cleaned or _has_traversal_or_control(cleaned):
        return None

    allowed_roots = _permitted_roots(profile)
    resolved_roots: List[Tuple[Path, Path]] = [(root, root.resolve()) for root in allowed_roots]

    raw_obj = Path(cleaned)
    candidates: List[Path] = []

    if raw_obj.is_absolute():
        candidates.append(raw_obj)
    else:
        data_roots: List[Path] = [profiles_module.DATA_DIR]
        if app_config.DATA_DIR != profiles_module.DATA_DIR:
            data_roots.append(app_config.DATA_DIR)

        for data_root in data_roots:
            candidates.append(data_root / cleaned)

        posix_parts = PurePosixPath(cleaned.replace("\\", "/")).parts
        if len(posix_parts) > 1 and posix_parts[0] == "receipts":
            candidates.append(profile.receipts_dir / Path(*posix_parts[1:]))
        elif len(posix_parts) > 1 and posix_parts[0] == "staging_receipts":
            candidates.append(profile.staging_receipts_dir / Path(*posix_parts[1:]))

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)

        try:
            resolved_candidate = candidate.resolve()
        except OSError:
            continue

        for raw_root, resolved_root in resolved_roots:
            if not resolved_candidate.is_relative_to(resolved_root):
                continue

            if _contains_symlink_escape(candidate, raw_root, resolved_root):
                continue

            if resolved_candidate.exists() and resolved_candidate.is_file():
                return resolved_candidate

    return None


def guess_receipt_media_type(file_path: Path) -> str:
    """Guess Content-Type for an archived or staged receipt attachment."""
    media_type, _ = mimetypes.guess_type(str(file_path))
    return media_type or "application/octet-stream"


def build_content_disposition(filename: str, download: bool = False) -> str:
    """Format an RFC-safe Content-Disposition header for inline preview or attachment download."""
    disposition = "attachment" if download else "inline"
    ascii_fallback = filename.encode("ascii", errors="ignore").decode("ascii").replace('"', "_") or "receipt"
    utf8_encoded = quote(filename, safe="")
    return f'{disposition}; filename="{ascii_fallback}"; filename*=UTF-8\'\'{utf8_encoded}'


def build_receipt_file_response(
    raw_path: Optional[str],
    profile: ProfileMetadata,
    download: bool = False,
) -> FileResponse:
    """Resolve an authorized receipt path in the active profile and return a FileResponse or 404."""
    resolved_file = resolve_profile_receipt_file(raw_path, profile)
    if resolved_file is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt file not found.",
        )

    media_type = guess_receipt_media_type(resolved_file)
    headers = {"Content-Disposition": build_content_disposition(resolved_file.name, download=download)}
    return FileResponse(path=resolved_file, media_type=media_type, headers=headers)
