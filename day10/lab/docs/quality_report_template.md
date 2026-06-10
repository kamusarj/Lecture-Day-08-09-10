# Quality report — Lab Day 10 (nhóm)

**run_id:** `after-fix-final`
**Ngày:** 2026-06-10

---

## 1. Tóm tắt số liệu

| Chỉ số | Trước | Sau | Ghi chú |
|--------|-------|-----|---------|
| raw_records | 247 | 247 | Cùng raw CSV |
| cleaned_records | 40 | 33 | Sau fix loại HR 2025, marker bẩn, P2 trong snapshot P1; thêm access control hợp lệ |
| quarantine_records | 207 | 214 | Có reason code rõ trong `artifacts/quarantine/quarantine_after-fix-final.csv` |
| Expectation halt? | Có | Không | Baseline fail `hr_leave_no_stale_10d_annual`; final toàn bộ halt expectation OK |

---

## 2. Before / after retrieval (bắt buộc)

Dẫn chứng chính:

- Sau fix: `artifacts/eval/eval_after_fix.csv`
- Inject xấu: `artifacts/eval/eval_after_inject_bad.csv` sau khi chạy Sprint 3

**Câu hỏi then chốt:** refund window (`q_refund_window`)  
**Trước:** inject `--no-refund-fix --skip-validate` làm `q_refund_window` có `hits_forbidden=yes`; top preview là "Yêu cầu hoàn tiền được chấp nhận trong vòng 14 ngày làm việc kể từ xác nhận đơn."
**Sau:** `q_refund_window, top1_doc_id=policy_refund_v4, contains_expected=yes, hits_forbidden=no, top1_doc_expected=yes`.

**Merit (khuyến nghị):** versioning HR — `q_leave_version` (`contains_expected`, `hits_forbidden`, cột `top1_doc_expected`)

**Trước:** baseline run `baseline-before` halt vì `hr_leave_no_stale_10d_annual FAIL :: violations=2`.
**Sau:** public eval `q_hr_annual_leave_under3` trả `12 ngày phép năm`, `hits_forbidden=no`, `top1_doc_expected=yes`.

---

## 3. Freshness & monitor

Run `after-fix-final` ghi:

`freshness_check=FAIL {"latest_exported_at": "2026-04-11T00:00:00", "age_hours": 1445.318, "sla_hours": 24.0, "reason": "freshness_sla_exceeded"}`

Giải thích: SLA 24h áp dụng cho snapshot source. Dữ liệu lab cố định từ tháng 04/2026 nên FAIL là hợp lý vào 2026-06-10; transform vẫn pass và manifest giúp phát hiện corpus stale.

---

## 4. Corruption inject (Sprint 3)

Kịch bản: chạy `python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate` để embed dữ liệu refund stale 14 ngày dù expectation halt. Eval sau đó cho thấy `q_refund_window` bị `hits_forbidden=yes`. Chạy lại pipeline chuẩn `after-fix-final` prune `1` vector stale refund và eval sạch.

---

## 5. Hạn chế & việc chưa làm

- Chưa tích hợp Great Expectations/pydantic thật; expectation hiện là custom Python.
- Freshness mới đo boundary publish từ manifest, chưa đo cả ingest watermark riêng.
- Tên nhóm/thành viên cần điền trong `reports/group_report.md` trước khi nộp.
