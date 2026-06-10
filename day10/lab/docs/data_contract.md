# Data contract — Lab Day 10

> Bắt đầu từ `contracts/data_contract.yaml` — mở rộng và đồng bộ file này.

---

## 1. Nguồn dữ liệu (source map)

| Nguồn | Phương thức ingest | Failure mode chính | Metric / alert |
|-------|-------------------|-------------------|----------------|
| `policy_refund_v4` | CSV export `data/raw/policy_export_dirty.csv` hoặc TXT canonical `data/docs/policy_refund_v4.txt` | Chunk stale "14 ngày làm việc", duplicate sync, thiếu `effective_date` | `refund_no_stale_14d_window`, `hits_forbidden` trên `q_refund_window` |
| `sla_p1_2026` | CSV export từ support/SLA hoặc TXT canonical `data/docs/sla_p1_2026.txt` | Dòng P2/P3/P4 bị lẫn vào snapshot P1, wording Anh-Việt làm giảm ranking | `sla_p1_no_other_priority_chunks`, eval `q_p1_escalation`, `q_p1_update_frequency` |
| `it_helpdesk_faq` | CSV export từ FAQ IT hoặc TXT canonical `data/docs/it_helpdesk_faq.txt` | Chunk rỗng, duplicate, marker "Nội dung không rõ ràng" | `no_dirty_text_markers`, `chunk_min_length_8` |
| `hr_leave_policy` | CSV export HR hoặc TXT canonical `data/docs/hr_leave_policy.txt` | Bản HR 2025/10 ngày phép năm lọt vào export 2026 | `hr_leave_no_stale_10d_annual`, quarantine reason `stale_hr_2025_annual_leave_content` |
| `access_control_sop` | CSV export IT Security hoặc TXT canonical `data/docs/access_control_sop.txt` | Nguồn hợp lệ bị thiếu trong allowlist baseline, duplicate Level 4, row rỗng | `required_doc_ids_present`, doc count trong cleaned snapshot |

---

## 2. Schema cleaned

| Cột | Kiểu | Bắt buộc | Ghi chú |
|-----|------|----------|---------|
| chunk_id | string | Có | ID ổn định theo `doc_id`, nội dung sau clean và thứ tự snapshot |
| doc_id | string | Có | Phải thuộc allowlist trong `contracts/data_contract.yaml` và `transform/cleaning_rules.py` |
| chunk_text | string | Có | Tối thiểu 8 ký tự, không chứa marker bẩn, không chứa stale HR 2025 |
| effective_date | date | Có | Chuẩn `YYYY-MM-DD`; parser chấp nhận và chuẩn hóa `DD/MM/YYYY` từ raw |
| exported_at | datetime | Có | ISO datetime; parser chuẩn hóa lỗi `YYYY/MM/DDT...` |

---

## 3. Quy tắc quarantine vs drop

Record không đạt rule được ghi vào `artifacts/quarantine/quarantine_<run_id>.csv` với trường `reason`; pipeline không drop im lặng. Các lý do chính ở run `after-fix-final`: `unknown_doc_id=109`, `duplicate_chunk_text=52`, `stale_hr_policy_effective_date=22`, `stale_hr_2025_annual_leave_content=8`, `dirty_text_marker=8`, `missing_chunk_text=8`, `missing_effective_date=6`, `non_p1_sla_chunk=1`.

Owner nguồn phê duyệt merge lại bằng cách sửa export upstream hoặc cập nhật `ALLOWED_DOC_IDS` + contract nếu đó là nguồn hợp lệ. Không sửa bằng cách thêm flow đọc câu hỏi grading.

---

## 4. Phiên bản & canonical

Source of truth:

- Refund: `data/docs/policy_refund_v4.txt`, effective `2026-02-01`, cửa sổ hiện hành là 7 ngày làm việc.
- HR leave: `data/docs/hr_leave_policy.txt`, effective `2026-01-01`; bản 2025/10 ngày phép năm bị quarantine dù export có effective date 2026.
- Access control: `data/docs/access_control_sop.txt`, effective `2026-01-01`; `access_control_sop` là doc_id hợp lệ trong allowlist.

Pipeline hỗ trợ ingest TXT trực tiếp. Ví dụ: `python etl_pipeline.py run --raw data/docs/policy_refund_v4.txt` cho một source đơn lẻ, hoặc `python etl_pipeline.py run --raw data/docs` để đọc toàn bộ thư mục TXT canonical.
