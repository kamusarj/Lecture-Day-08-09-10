"""
Expectation suite đơn giản (không bắt buộc Great Expectations).

Sinh viên có thể thay bằng GE / pydantic / custom — miễn là có halt có kiểm soát.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Tuple


@dataclass
class ExpectationResult:
    name: str
    passed: bool
    severity: str  # "warn" | "halt"
    detail: str


REQUIRED_DOC_IDS = frozenset(
    {
        "policy_refund_v4",
        "sla_p1_2026",
        "it_helpdesk_faq",
        "hr_leave_policy",
        "access_control_sop",
    }
)


def _parse_iso_datetime(value: str) -> bool:
    try:
        datetime.fromisoformat((value or "").strip().replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def run_expectations(
    cleaned_rows: List[Dict[str, Any]],
    *,
    require_required_doc_ids: bool = True,
) -> Tuple[List[ExpectationResult], bool]:
    """
    Trả về (results, should_halt).

    should_halt = True nếu có bất kỳ expectation severity halt nào fail.
    """
    results: List[ExpectationResult] = []

    # E1: có ít nhất 1 dòng sau clean
    ok = len(cleaned_rows) >= 1
    results.append(
        ExpectationResult(
            "min_one_row",
            ok,
            "halt",
            f"cleaned_rows={len(cleaned_rows)}",
        )
    )

    # E2: không doc_id rỗng
    bad_doc = [r for r in cleaned_rows if not (r.get("doc_id") or "").strip()]
    ok2 = len(bad_doc) == 0
    results.append(
        ExpectationResult(
            "no_empty_doc_id",
            ok2,
            "halt",
            f"empty_doc_id_count={len(bad_doc)}",
        )
    )

    # E3: policy refund không được chứa cửa sổ sai 14 ngày (sau khi đã fix)
    bad_refund = [
        r
        for r in cleaned_rows
        if r.get("doc_id") == "policy_refund_v4"
        and "14 ngày làm việc" in (r.get("chunk_text") or "")
    ]
    ok3 = len(bad_refund) == 0
    results.append(
        ExpectationResult(
            "refund_no_stale_14d_window",
            ok3,
            "halt",
            f"violations={len(bad_refund)}",
        )
    )

    # E4: chunk_text đủ dài
    short = [r for r in cleaned_rows if len((r.get("chunk_text") or "")) < 8]
    ok4 = len(short) == 0
    results.append(
        ExpectationResult(
            "chunk_min_length_8",
            ok4,
            "warn",
            f"short_chunks={len(short)}",
        )
    )

    # E5: effective_date đúng định dạng ISO sau clean (phát hiện parser lỏng)
    iso_bad = [
        r
        for r in cleaned_rows
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", (r.get("effective_date") or "").strip())
    ]
    ok5 = len(iso_bad) == 0
    results.append(
        ExpectationResult(
            "effective_date_iso_yyyy_mm_dd",
            ok5,
            "halt",
            f"non_iso_rows={len(iso_bad)}",
        )
    )

    # E6: không còn marker phép năm cũ 10 ngày trên doc HR (conflict version sau clean)
    bad_hr_annual = [
        r
        for r in cleaned_rows
        if r.get("doc_id") == "hr_leave_policy"
        and "10 ngày phép năm" in (r.get("chunk_text") or "")
    ]
    ok6 = len(bad_hr_annual) == 0
    results.append(
        ExpectationResult(
            "hr_leave_no_stale_10d_annual",
            ok6,
            "halt",
            f"violations={len(bad_hr_annual)}",
        )
    )

    # E7: đủ 5 source chính để retrieval không mất coverage ở câu hỏi ẩn/công khai
    present_doc_ids = {str(r.get("doc_id") or "").strip() for r in cleaned_rows}
    missing_doc_ids = sorted(REQUIRED_DOC_IDS - present_doc_ids)
    ok7 = len(missing_doc_ids) == 0 if require_required_doc_ids else True
    detail7 = f"missing={missing_doc_ids}"
    if not require_required_doc_ids:
        detail7 = f"skipped_single_source present={sorted(present_doc_ids)}"
    results.append(
        ExpectationResult(
            "required_doc_ids_present",
            ok7,
            "halt",
            detail7,
        )
    )

    # E8: exported_at phải parse được sau clean để freshness monitor đáng tin
    bad_exported_at = [
        r
        for r in cleaned_rows
        if not _parse_iso_datetime(str(r.get("exported_at") or ""))
    ]
    ok8 = len(bad_exported_at) == 0
    results.append(
        ExpectationResult(
            "exported_at_iso_datetime",
            ok8,
            "halt",
            f"invalid_exported_at={len(bad_exported_at)}",
        )
    )

    # E9: marker dữ liệu bẩn không được lọt vào cleaned snapshot
    dirty_markers = [
        r
        for r in cleaned_rows
        if (r.get("chunk_text") or "").lstrip().lower().startswith(("nội dung không rõ ràng:", "!!!"))
    ]
    ok9 = len(dirty_markers) == 0
    results.append(
        ExpectationResult(
            "no_dirty_text_markers",
            ok9,
            "halt",
            f"dirty_marker_rows={len(dirty_markers)}",
        )
    )

    # E10: chunk_id unique để upsert/prune giữ snapshot ổn định
    chunk_ids = [str(r.get("chunk_id") or "") for r in cleaned_rows]
    duplicate_chunk_ids = len(chunk_ids) - len(set(chunk_ids))
    ok10 = duplicate_chunk_ids == 0
    results.append(
        ExpectationResult(
            "unique_chunk_id",
            ok10,
            "halt",
            f"duplicate_chunk_ids={duplicate_chunk_ids}",
        )
    )

    # E11: collection này phục vụ SLA P1, không embed chunk P2/P3/P4 gây nhiễu ranking
    non_p1_sla = [
        r
        for r in cleaned_rows
        if r.get("doc_id") == "sla_p1_2026"
        and (r.get("chunk_text") or "").strip().lower().startswith(("ticket p2:", "ticket p3:", "ticket p4:"))
    ]
    ok11 = len(non_p1_sla) == 0
    results.append(
        ExpectationResult(
            "sla_p1_no_other_priority_chunks",
            ok11,
            "halt",
            f"non_p1_chunks={len(non_p1_sla)}",
        )
    )

    halt = any(not r.passed and r.severity == "halt" for r in results)
    return results, halt
