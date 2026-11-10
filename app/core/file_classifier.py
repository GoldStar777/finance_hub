import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

@dataclass
class FileClassificationResult:
    mime_type: str
    extension: str
    document_type: str  # 'receipt', 'statement', 'statement_screenshot', 'unsupported', 'unreadable'
    type_label: str
    is_image: bool
    is_pdf: bool
    is_tabular: bool  # csv, tsv, xlsx
    is_supported: bool
    details: str

def inspect_file_signature(content: bytes, filename: str = "") -> Tuple[str, str, bool]:
    """
    Inspects magic bytes / file signature to determine true MIME type without trusting file extension.
    Returns (mime_type, normalized_extension, is_binary).
    """
    if not content:
        return "application/x-empty", "", False

    header_16 = content[:16]

    # 1. Images
    # PNG: 89 50 4E 47 0D 0A 1A 0A
    if header_16.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png", True

    # JPEG: FF D8 FF
    if header_16.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg", True

    # GIF: GIF87a or GIF89a
    if header_16.startswith(b"GIF87a") or header_16.startswith(b"GIF89a"):
        return "image/gif", ".gif", True

    # TIFF: II*\x00 (little-endian) or MM\x00* (big-endian)
    if header_16.startswith(b"II*\x00") or header_16.startswith(b"MM\x00*"):
        return "image/tiff", ".tiff", True

    # WebP: RIFF....WEBP
    if header_16.startswith(b"RIFF") and len(content) >= 12 and content[8:12] == b"WEBP":
        return "image/webp", ".webp", True

    # HEIC / HEIF / ISO Media (ftypheic, ftypmif1, etc.)
    if len(content) >= 12 and content[4:8] == b"ftyp":
        brand = content[8:12].lower()
        if brand in (b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1"):
            return "image/heic", ".heic", True

    # 2. PDF: %PDF-
    if header_16.startswith(b"%PDF"):
        return "application/pdf", ".pdf", True

    # 3. ZIP-based archives: PK\x03\x04
    if header_16.startswith(b"PK\x03\x04"):
        # Check if it's an Excel .xlsx workbook safely
        try:
            with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
                namelist = zf.namelist()
                if any("xl/workbook.xml" in n or "xl/worksheets/" in n for n in namelist):
                    return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx", True
                if any("word/document.xml" in n for n in namelist):
                    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx", True
        except Exception:
            pass
        return "application/zip", ".zip", True

    # 4. Dangerous / Executable binaries
    # ELF: \x7fELF
    if header_16.startswith(b"\x7fELF"):
        return "application/x-executable", "", True
    # Windows PE: MZ
    if header_16.startswith(b"MZ"):
        return "application/x-dosexec", ".exe", True
    # macOS Mach-O headers
    if header_16[:4] in (b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe"):
        return "application/x-mach-binary", "", True

    # 5. Text / Delimited data check
    # Check if bytes can be decoded as text without null bytes
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text_sample = content[:4096].decode(enc)
            if "\x00" in text_sample:
                # Null byte indicates binary content
                break

            # Analyze text delimiters
            lines = [l for l in text_sample.splitlines() if l.strip()]
            if lines:
                first_line = lines[0]
                commas = first_line.count(",")
                tabs = first_line.count("\t")
                semicolons = first_line.count(";")
                pipes = first_line.count("|")

                max_delim_count = max(commas, tabs, semicolons, pipes)
                if max_delim_count >= 1 and len(lines) >= 1:
                    if tabs > commas and tabs > semicolons:
                        return "text/tab-separated-values", ".tsv", False
                    elif commas > 0:
                        return "text/csv", ".csv", False
                    elif semicolons > 0:
                        return "text/csv", ".csv", False
                    elif pipes > 0:
                        return "text/csv", ".csv", False

                return "text/plain", ".txt", False
        except UnicodeDecodeError:
            continue

    # Default fallback for unknown binary
    ext = Path(filename).suffix.lower() if filename else ""
    return "application/octet-stream", ext, True

def classify_uploaded_file(content: bytes, filename: str = "") -> FileClassificationResult:
    """
    Classifies an uploaded file by content signature and determines the appropriate extraction route.
    """
    mime_type, detected_ext, is_binary = inspect_file_signature(content, filename)
    file_ext = Path(filename).suffix.lower() if filename else detected_ext

    # Image formats
    if mime_type.startswith("image/"):
        return FileClassificationResult(
            mime_type=mime_type,
            extension=detected_ext or file_ext,
            document_type="image",  # Will be refined to 'receipt' or 'statement_screenshot' after OCR analysis
            type_label="Image Document",
            is_image=True,
            is_pdf=False,
            is_tabular=False,
            is_supported=True,
            details=f"Detected image ({mime_type})"
        )

    # PDF documents
    if mime_type == "application/pdf":
        return FileClassificationResult(
            mime_type=mime_type,
            extension=".pdf",
            document_type="pdf",  # Will be refined to 'statement' or 'receipt'
            type_label="PDF Document",
            is_image=False,
            is_pdf=True,
            is_tabular=False,
            is_supported=True,
            details="Standard PDF document"
        )

    # Excel spreadsheets
    if mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
        return FileClassificationResult(
            mime_type=mime_type,
            extension=".xlsx",
            document_type="statement",
            type_label="Excel Spreadsheet (.xlsx)",
            is_image=False,
            is_pdf=False,
            is_tabular=True,
            is_supported=True,
            details="Microsoft Excel OpenXML spreadsheet"
        )

    # Delimited tabular text (CSV / TSV)
    if mime_type in ("text/csv", "text/tab-separated-values"):
        label = "CSV Statement" if mime_type == "text/csv" else "TSV Statement"
        return FileClassificationResult(
            mime_type=mime_type,
            extension=detected_ext or ".csv",
            document_type="statement",
            type_label=label,
            is_image=False,
            is_pdf=False,
            is_tabular=True,
            is_supported=True,
            details=f"Delimited text statement ({mime_type})"
        )

    # Plain text that might be CSV/TSV without header commas
    if mime_type == "text/plain":
        return FileClassificationResult(
            mime_type=mime_type,
            extension=".txt",
            document_type="unsupported",
            type_label="Plain Text Document",
            is_image=False,
            is_pdf=False,
            is_tabular=False,
            is_supported=False,
            details="Plain text without standard tabular formatting"
        )

    # Executable or unsupported binary files
    return FileClassificationResult(
        mime_type=mime_type,
        extension=file_ext,
        document_type="unsupported",
        type_label="Unsupported Document",
        is_image=False,
        is_pdf=False,
        is_tabular=False,
        is_supported=False,
        details=f"File format ({mime_type}) is not automatically parsed. Preserved for manual attachment."
    )

