"""
Cleaning rules — raw export → cleaned rows + quarantine.

Baseline gồm các failure mode mở rộng (allowlist doc_id, parse ngày, HR stale version).
Sinh viên thêm ≥3 rule mới: mỗi rule phải ghi `metric_impact` (xem README — chống trivial).
"""

from __future__ import annotations

import csv
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Khớp export hợp lệ trong lab (mở rộng khi nhóm thêm doc mới — phải đồng bộ contract).
ALLOWED_DOC_IDS = frozenset(
    {
        "policy_refund_v4",
        "sla_p1_2026",
        "it_helpdesk_faq",
        "hr_leave_policy",
        "access_control_sop",
    }
)

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DMY_SLASH = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_EXPORTED_AT_SLASH = re.compile(r"^(\d{4})/(\d{2})/(\d{2})(T.*)$")
_TXT_EFFECTIVE_DATE = re.compile(r"^Effective Date:\s*(.+?)\s*$", re.MULTILINE)
_TXT_SECTION = re.compile(r"(?=^=== .+ ===$)", re.MULTILINE)
_DIRTY_TEXT_MARKERS = ("nội dung không rõ ràng:", "!!!")


def _norm_text(s: str) -> str:
    return " ".join((s or "").strip().split()).lower()


def _stable_chunk_id(doc_id: str, chunk_text: str, seq: int) -> str:
    h = hashlib.sha256(f"{doc_id}|{chunk_text}|{seq}".encode("utf-8")).hexdigest()[:16]
    return f"{doc_id}_{seq}_{h}"


def _normalize_effective_date(raw: str) -> Tuple[str, str]:
    """
    Trả về (iso_date, error_reason).
    iso_date rỗng nếu không parse được.
    """
    s = (raw or "").strip()
    if not s:
        return "", "empty_effective_date"
    if _ISO_DATE.match(s):
        return s, ""
    m = _DMY_SLASH.match(s)
    if m:
        dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
        return f"{yyyy}-{mm}-{dd}", ""
    return "", "invalid_effective_date_format"


def _normalize_exported_at(raw: str) -> Tuple[str, str]:
    """
    Trả về (iso_datetime, error_reason). Cho phép sửa lỗi YYYY/MM/DDTHH:MM:SS
    trong export nhưng vẫn halt nếu timestamp không parse được.
    """
    s = (raw or "").strip()
    if not s:
        return "", "missing_exported_at"
    m = _EXPORTED_AT_SLASH.match(s)
    if m:
        s = f"{m.group(1)}-{m.group(2)}-{m.group(3)}{m.group(4)}"
    try:
        datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return "", "invalid_exported_at_format"
    return s, ""


def _has_dirty_text_marker(text: str) -> bool:
    norm = _norm_text(text)
    return any(norm.startswith(marker) for marker in _DIRTY_TEXT_MARKERS)


def _has_stale_hr_2025_annual_leave(text: str) -> bool:
    norm = _norm_text(text)
    if "bản hr 2025" in norm:
        return True
    return "10 ngày phép năm" in norm


def _collapse_repeated_workday_words(text: str) -> str:
    previous = None
    cleaned = text
    while previous != cleaned:
        previous = cleaned
        cleaned = cleaned.replace("làm việc làm việc", "làm việc")
    return cleaned


def _canonicalize_sla_p1_text(text: str) -> str:
    norm = _norm_text(text)
    if "escalation p1" in norm and "10 phút" in norm:
        return (
            "Ticket P1 escalation: nếu không có phản hồi với ticket P1 sau 10 phút, "
            "hệ thống tự động escalate lên Senior Engineer."
        )
    if "thông báo stakeholder p1" in norm and "30 phút" in norm:
        return (
            "Trong sự cố P1, thông tin tiến độ được cập nhật mỗi 30 phút cho stakeholder "
            "cho đến khi resolve."
        )
    return text


def load_raw_csv(path: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({k: (v or "").strip() for k, v in r.items()})
    return rows


def _file_exported_at(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat()


def _txt_effective_date(text: str) -> str:
    m = _TXT_EFFECTIVE_DATE.search(text)
    return (m.group(1) if m else "").strip()


def _txt_chunks(text: str) -> List[str]:
    chunks: List[str] = []
    parts = [p.strip() for p in _TXT_SECTION.split(text) if p.strip()]
    for part in parts:
        lines = [
            line.strip()
            for line in part.splitlines()
            if line.strip() and not line.startswith(("Source:", "Department:", "Effective Date:", "Access:"))
        ]
        chunk = " ".join(lines).strip()
        if chunk:
            chunks.append(chunk)
    return chunks


def load_raw_txt(path: Path) -> List[Dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    effective_date = _txt_effective_date(text)
    exported_at = _file_exported_at(path)
    doc_id = path.stem
    rows: List[Dict[str, str]] = []
    for seq, chunk in enumerate(_txt_chunks(text), start=1):
        rows.append(
            {
                "chunk_id": f"{doc_id}_txt_{seq}",
                "doc_id": doc_id,
                "chunk_text": chunk,
                "effective_date": effective_date,
                "exported_at": exported_at,
            }
        )
    return rows


def load_raw_records(path: Path) -> List[Dict[str, str]]:
    if path.is_dir():
        rows: List[Dict[str, str]] = []
        for child in sorted(path.iterdir()):
            if child.suffix.lower() == ".csv":
                rows.extend(load_raw_csv(child))
            elif child.suffix.lower() == ".txt":
                rows.extend(load_raw_txt(child))
        return rows
    if path.suffix.lower() == ".csv":
        return load_raw_csv(path)
    if path.suffix.lower() == ".txt":
        return load_raw_txt(path)
    raise ValueError(f"unsupported raw input type: {path}")


def clean_rows(
    rows: List[Dict[str, str]],
    *,
    apply_refund_window_fix: bool = True,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Trả về (cleaned, quarantine).

    Baseline (mở rộng theo narrative Day 10):
    1) Quarantine: doc_id không thuộc allowlist (export lạ / catalog sai).
    2) Chuẩn hoá effective_date sang YYYY-MM-DD; quarantine nếu không parse được.
    3) Quarantine: chunk hr_leave_policy có effective_date < 2026-01-01 (bản HR cũ / conflict version).
    4) Quarantine: chunk_text rỗng hoặc effective_date rỗng sau chuẩn hoá.
    5) Chuẩn hoá exported_at sang ISO datetime; quarantine nếu không parse được.
    6) Quarantine marker dữ liệu bẩn ("Nội dung không rõ ràng", "!!!").
    7) Quarantine HR 2025 theo nội dung, kể cả khi effective_date bị export nhầm sang 2026.
    8) Quarantine chunk SLA khác P1 trong export P1 để tránh nhiễu retrieval.
    9) Canonical hoá câu P1 escalation/update theo tài liệu nguồn.
    10) Fix stale refund: policy_refund_v4 chứa '14 ngày làm việc' → 7 ngày.
    11) Sửa cụm lặp "làm việc làm việc" rồi loại trùng nội dung chunk_text (giữ bản đầu).
    """
    quarantine: List[Dict[str, Any]] = []
    seen_text: set[str] = set()
    cleaned: List[Dict[str, Any]] = []
    seq = 0

    for raw in rows:
        doc_id = raw.get("doc_id", "")
        text = raw.get("chunk_text", "")
        eff_raw = raw.get("effective_date", "")
        exported_at = raw.get("exported_at", "")

        if doc_id not in ALLOWED_DOC_IDS:
            quarantine.append({**raw, "reason": "unknown_doc_id"})
            continue

        eff_norm, eff_err = _normalize_effective_date(eff_raw)
        if eff_err == "empty_effective_date":
            quarantine.append({**raw, "reason": "missing_effective_date"})
            continue
        if eff_err == "invalid_effective_date_format":
            quarantine.append({**raw, "reason": eff_err, "effective_date_raw": eff_raw})
            continue

        exported_norm, exported_err = _normalize_exported_at(exported_at)
        if exported_err:
            quarantine.append({**raw, "reason": exported_err, "exported_at_raw": exported_at})
            continue

        if doc_id == "hr_leave_policy" and eff_norm < "2026-01-01":
            quarantine.append(
                {
                    **raw,
                    "reason": "stale_hr_policy_effective_date",
                    "effective_date_normalized": eff_norm,
                }
            )
            continue

        if not text:
            quarantine.append({**raw, "reason": "missing_chunk_text"})
            continue

        if _has_dirty_text_marker(text):
            quarantine.append({**raw, "reason": "dirty_text_marker"})
            continue

        if doc_id == "hr_leave_policy" and _has_stale_hr_2025_annual_leave(text):
            quarantine.append({**raw, "reason": "stale_hr_2025_annual_leave_content"})
            continue

        if doc_id == "sla_p1_2026" and _norm_text(text).startswith(("ticket p2:", "ticket p3:", "ticket p4:")):
            quarantine.append({**raw, "reason": "non_p1_sla_chunk"})
            continue

        fixed_text = _collapse_repeated_workday_words(text)
        if doc_id == "sla_p1_2026":
            fixed_text = _canonicalize_sla_p1_text(fixed_text)
        if apply_refund_window_fix and doc_id == "policy_refund_v4":
            if "14 ngày làm việc" in fixed_text:
                fixed_text = fixed_text.replace(
                    "14 ngày làm việc",
                    "7 ngày làm việc",
                )
                fixed_text += " [cleaned: stale_refund_window]"

        key = _norm_text(fixed_text)
        if key in seen_text:
            quarantine.append({**raw, "reason": "duplicate_chunk_text"})
            continue
        seen_text.add(key)

        seq += 1
        cleaned.append(
            {
                "chunk_id": _stable_chunk_id(doc_id, fixed_text, seq),
                "doc_id": doc_id,
                "chunk_text": fixed_text,
                "effective_date": eff_norm,
                "exported_at": exported_norm,
            }
        )

    return cleaned, quarantine


def write_cleaned_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("chunk_id,doc_id,chunk_text,effective_date,exported_at\n", encoding="utf-8")
        return
    fieldnames = ["chunk_id", "doc_id", "chunk_text", "effective_date", "exported_at"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def write_quarantine_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("chunk_id,doc_id,chunk_text,effective_date,exported_at,reason\n", encoding="utf-8")
        return
    keys: List[str] = []
    seen_k: set[str] = set()
    for r in rows:
        for k in r.keys():
            if k not in seen_k:
                seen_k.add(k)
                keys.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore", restval="")
        w.writeheader()
        for r in rows:
            w.writerow(r)
