# Runbook — Lab Day 10 (incident tối giản)

---

## Symptom

User hoặc agent trả lời sai do context stale/nhiễu, ví dụ:

- Refund trả lời "14 ngày" thay vì "7 ngày làm việc".
- HR trả lời "10 ngày phép năm" cho nhân viên dưới 3 năm thay vì "12 ngày phép năm".
- Access Control không trả lời được Level 4 vì `access_control_sop` bị quarantine nhầm.
- P1 escalation/update lấy nhầm chunk P2 hoặc FAQ, làm top-1 sai doc.

---

## Detection

- Pipeline halt nếu expectation `refund_no_stale_14d_window`, `hr_leave_no_stale_10d_annual`, `required_doc_ids_present`, `exported_at_iso_datetime`, `no_dirty_text_markers`, hoặc `sla_p1_no_other_priority_chunks` fail.
- Eval công khai: `artifacts/eval/eval_after_fix.csv` phải có `contains_expected=yes`, `hits_forbidden=no`, `top1_doc_expected=yes`.
- Manifest final: `artifacts/manifests/manifest_after-fix-final.json`.
- Freshness: `freshness_check=FAIL` khi `latest_exported_at` quá SLA 24h; với data mẫu ngày `2026-04-11`, FAIL là expected vào `2026-06-10`.

---

## Diagnosis

| Bước | Việc làm | Kết quả mong đợi |
|------|----------|------------------|
| 1 | Kiểm tra `artifacts/logs/run_<run_id>.log` | Có `raw_records`, `cleaned_records`, `quarantine_records`, expectation OK/FAIL |
| 2 | Kiểm tra `artifacts/manifests/*.json` | `run_id`, `latest_exported_at`, `cleaned_csv`, `chroma_collection` khớp run |
| 3 | Mở `artifacts/quarantine/*.csv` | Reason code giải thích record bị loại, ví dụ `stale_hr_2025_annual_leave_content` |
| 4 | Chạy `python eval_retrieval.py --out artifacts/eval/eval_after_fix.csv` | Không có fail ở `contains_expected`, `hits_forbidden`, `top1_doc_expected` |
| 5 | Nếu grading fail | Chạy lại pipeline chuẩn, đảm bảo `embed_prune_removed` không bỏ qua vector cũ |
| 6 | Kiểm tra ingest TXT nếu cần | `python etl_pipeline.py run --raw data/docs` phải có `raw_source_type=directory` và đủ 5 nguồn |

---

## Mitigation

- Sửa rule/allowlist trong `transform/cleaning_rules.py`, sau đó chạy `python etl_pipeline.py run --run-id <id>`.
- Nếu nguồn là TXT canonical, chạy `python etl_pipeline.py run --raw data/docs --run-id <id>` để publish cả thư mục, hoặc `--raw data/docs/<file>.txt` để kiểm tra một source đơn.
- Không dùng `--skip-validate` cho run nộp bài; option này chỉ dùng để tạo evidence inject.
- Nếu vector cũ gây nhiễu, rerun pipeline chuẩn để prune ID không còn trong cleaned snapshot.
- Nếu freshness FAIL vì source thật quá cũ, thông báo owner nguồn và tạm đánh dấu corpus stale cho agent.

---

## Prevention

- Đồng bộ `contracts/data_contract.yaml` khi thêm nguồn hợp lệ.
- Giữ expectation halt cho stale refund, stale HR, missing doc coverage và non-P1 chunk.
- Theo dõi freshness theo `latest_exported_at` trong manifest; alert `#data-observability` khi quá SLA.
- Lưu before/after eval để reviewer thấy rule mới có tác động đo được, không phải rule trivial.
