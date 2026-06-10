# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Linh
**Vai trò:** Cleaning & Quality / Embed evidence
**Ngày nộp:** 2026-06-10

## 1. Tôi phụ trách phần nào?

Tôi phụ trách phần làm sạch dữ liệu và chốt evidence chất lượng trước khi publish vào vector store. Các file/module tôi đứng tên theo ownership là `transform/cleaning_rules.py` (`clean_rows`, `_stable_chunk_id`, `_has_stale_hr_2025_annual_leave`, `_normalize_exported_at`), `quality/expectations.py` (`run_expectations`) và phần embed trong `etl_pipeline.py` (`cmd_embed_internal`). Tôi phối hợp với phần monitoring qua manifest `artifacts/manifests/manifest_after-fix-final.json`, vì freshness lấy từ `latest_exported_at`. Run nộp bài là `after-fix-final`: log ghi `raw_records=247`, `cleaned_records=33`, `quarantine_records=214`, `embed_upsert count=33 collection=day10_kb`.

## 2. Một quyết định kỹ thuật

Tôi chọn phân tầng rõ giữa `halt` và `warn`. Những lỗi có thể làm agent trả lời sai hoặc làm mất coverage thì phải `halt`: `refund_no_stale_14d_window`, `hr_leave_no_stale_10d_annual`, `required_doc_ids_present`, `exported_at_iso_datetime`, `no_dirty_text_markers`, `unique_chunk_id`, `sla_p1_no_other_priority_chunks`. Riêng `chunk_min_length_8` để `warn`, vì chunk ngắn chưa chắc sai nếu là câu FAQ hợp lệ; nó cần review nhưng không đáng chặn publish. Với idempotency, tôi dùng `chunk_id` ổn định theo `doc_id|chunk_text|seq`, sau đó Chroma `upsert` theo `chunk_id` và prune ID không còn trong snapshot. Bằng chứng final có `embed_prune_removed=14`, rồi rerun cùng `run_id=after-fix-final` chỉ còn `embed_prune_removed=1`, không phình index. Freshness được đo tại publish boundary từ manifest; run final FAIL đúng vì `latest_exported_at=2026-04-11T00:00:00`, quá SLA 24h vào ngày lab 2026-06-10.

## 3. Một lỗi hoặc anomaly đã xử lý

Anomaly chính tôi xử lý là dữ liệu policy cũ vẫn có thể lọt qua nếu chỉ dựa vào ngày. Ở `baseline-before`, pipeline dừng tại `expectation[hr_leave_no_stale_10d_annual] FAIL (halt) :: violations=2`; trong `cleaned_baseline-before.csv` còn chunk HR 2025 ghi “10 ngày phép năm”. Tôi thêm rule quarantine theo nội dung `_has_stale_hr_2025_annual_leave`, bắt cả marker “bản HR 2025” và cụm “10 ngày phép năm”, không chỉ `effective_date < 2026-01-01`. Sau fix, `quarantine_after-fix-final.csv` có `stale_hr_2025_annual_leave_content=8`, còn log `after-fix-final` ghi `expectation[hr_leave_no_stale_10d_annual] OK (halt) :: violations=0`. Tôi cũng giữ rule `dirty_text_marker=8` và `non_p1_sla_chunk=1` để tránh chunk bẩn làm nhiễu retrieval.

## 4. Bằng chứng trước / sau

Tôi dùng hai evidence retrieval. Khi cố tình inject lỗi bằng `run_id=inject-bad` với `--no-refund-fix --skip-validate`, log báo `refund_no_stale_14d_window FAIL (halt) :: violations=1` nhưng vẫn embed để demo; `artifacts/eval/eval_after_inject_bad.csv` có dòng:

`q_refund_window,policy_refund_v4,"...14 ngày làm việc...",yes,yes,yes,3`

Sau khi chạy chuẩn `run_id=after-fix-final`, `artifacts/eval/eval_after_fix.csv` đổi thành:

`q_refund_window,policy_refund_v4,"...7 ngày làm việc...",yes,no,yes,3`

Tổng eval public là 21/21 `contains_expected=yes`, 0 `hits_forbidden=yes`, 0 `top1_doc_expected=no`. File `artifacts/eval/grading_run.jsonl` cũng có 10 dòng, cả 10 `contains_expected=true`, `hits_forbidden=false`, `top1_doc_matches=true`.

## 5. Cải tiến tiếp theo

Nếu có thêm 2 giờ, tôi sẽ tách freshness thành hai boundary: ingest watermark lấy max `exported_at` ngay sau đọc raw và publish watermark sau clean/embed. Manifest sẽ ghi cả hai trường, để phân biệt source đã cũ với pipeline publish chậm hoặc rerun từ snapshot cũ.
