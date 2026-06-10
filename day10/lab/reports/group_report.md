# Báo Cáo Cá Nhân Tổng Hợp — Lab Day 10: Data Pipeline & Data Observability

**Người thực hiện:** Linh
**Vai trò (Day 10):** Ingestion, Cleaning & Quality, Embed, Monitoring/Docs

**Ngày nộp:** 2026-06-10
**Repo:** local lab workspace
**Ghi chú:** Bài làm cá nhân; file này thay cho báo cáo nhóm và liên kết với `reports/individual/linh.md`.

---

> **Nộp tại:** `reports/group_report.md` và `reports/individual/linh.md`
> **Deadline commit:** xem `SCORING.md` (code/trace sớm; report có thể muộn hơn nếu được phép).  
> Phải có **run_id**, **đường dẫn artifact**, và **bằng chứng before/after** (CSV eval hoặc screenshot).

---

## 1. Pipeline tổng quan (150–200 từ)

> Nguồn raw là gì (CSV mẫu / export thật)? Chuỗi lệnh chạy end-to-end? `run_id` lấy ở đâu trong log?

**Tóm tắt luồng:**

Pipeline đọc `data/raw/policy_export_dirty.csv` hoặc nguồn TXT canonical trong `data/docs`, ghi `run_id`, đếm raw/cleaned/quarantine, áp dụng rule trong `transform/cleaning_rules.py`, chạy expectation trong `quality/expectations.py`, rồi publish snapshot sang Chroma collection. Run nộp bài CSV là `after-fix-final`: `raw_records=247`, `cleaned_records=33`, `quarantine_records=214`, manifest ở `artifacts/manifests/manifest_after-fix-final.json`. Smoke test TXT cũng pass: `txt-file-smoke` đọc một file TXT có `raw_records=7`, và `txt-dir-smoke` đọc cả thư mục `data/docs` có `raw_records=34`. Pipeline dùng upsert theo `chunk_id` và prune vector không còn trong cleaned.

**Lệnh chạy một dòng (copy từ README thực tế của nhóm):**

`python etl_pipeline.py run --run-id after-fix-final && python eval_retrieval.py --out artifacts/eval/eval_after_fix.csv && python grading_run.py --out artifacts/eval/grading_run.jsonl`

---

## 2. Cleaning & expectation

> Baseline đã có nhiều rule (allowlist, ngày ISO, HR stale, refund, dedupe…). Bài cá nhân này thêm **≥3 rule mới** + **≥2 expectation mới**. Khai báo expectation nào **halt**.

### 2a. Bảng metric_impact (bắt buộc — chống trivial)

| Rule / Expectation mới (tên ngắn) | Trước (số liệu) | Sau / khi inject (số liệu) | Chứng cứ (log / CSV / file) |
|-----------------------------------|------------------|-----------------------------|-------------------------------|
| `access_control_sop` allowlist + `required_doc_ids_present` | baseline quarantine `access_control_sop=8`, missing source trong cleaned | final cleaned có `access_control_sop=6`, expectation `missing=[]` | `artifacts/cleaned/cleaned_after-fix-final.csv`, log `after-fix-final` |
| `stale_hr_2025_annual_leave_content` | baseline halt `hr_leave_no_stale_10d_annual violations=2` | final expectation OK, quarantine reason count `8` | `artifacts/logs/run_baseline-before.log`, `artifacts/quarantine/quarantine_after-fix-final.csv` |
| `dirty_text_marker` | marker `Nội dung không rõ ràng`/`!!!` có thể lọt nếu unique | final quarantine reason count `8`, expectation `dirty_marker_rows=0` | `quality/expectations.py`, final quarantine CSV |
| `exported_at_iso_datetime` | raw có `YYYY/MM/DDT...` trong `exported_at` | final expectation `invalid_exported_at=0`, timestamp normalized | `artifacts/cleaned/cleaned_after-fix-final.csv` |
| `sla_p1_no_other_priority_chunks` | eval trước fix fail `q_p1_escalation`, top1 P2; `q_p1_update_frequency` top1 FAQ | final 21/21 public eval pass, P1 escalation/update top1 `sla_p1_2026` | `artifacts/eval/eval_after_fix.csv` |

**Rule chính (baseline + mở rộng):**

- Allowlist chỉ nhận nguồn hợp lệ và đã thêm `access_control_sop`.
- Chuẩn hóa `effective_date` (`YYYY-MM-DD`, `DD/MM/YYYY`) và `exported_at` (`YYYY/MM/DDT...` -> ISO).
- Quarantine missing text/date, unknown doc_id, duplicate text sau khi canonicalize.
- Fix refund stale `14 ngày làm việc` thành `7 ngày làm việc` khi chạy chuẩn.
- Quarantine HR 2025 theo nội dung (`bản HR 2025`, `10 ngày phép năm`).
- Quarantine marker dữ liệu bẩn và non-P1 chunk trong snapshot `sla_p1_2026`.

**Ví dụ 1 lần expectation fail (nếu có) và cách xử lý:**

Baseline `python etl_pipeline.py run --run-id baseline-before` halt ở `hr_leave_no_stale_10d_annual FAIL :: violations=2`. Tôi thêm rule `stale_hr_2025_annual_leave_content`, rerun final thì expectation HR pass và eval `q_hr_annual_leave_under3` không còn hit forbidden.

---

## 3. Before / after ảnh hưởng retrieval hoặc agent (200–250 từ)

> Bắt buộc: inject corruption (Sprint 3) — mô tả + dẫn `artifacts/eval/…` hoặc log.

**Kịch bản inject:**

Chạy có chủ đích `python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate` để bỏ rule fix refund và vẫn embed dù expectation halt. Sau đó chạy `python eval_retrieval.py --out artifacts/eval/eval_after_inject_bad.csv`, rồi chạy lại pipeline chuẩn `after-fix-final` và eval sạch.

**Kết quả định lượng (từ CSV / bảng):**

Inject xấu: `artifacts/eval/eval_after_inject_bad.csv` có `q_refund_window` với `hits_forbidden=yes`, top preview chứa "14 ngày làm việc". Sau fix công khai: `artifacts/eval/eval_after_fix.csv` có 21/21 dòng `contains_expected=yes`, 0 dòng `hits_forbidden=yes`, 0 dòng `top1_doc_expected=no`. Các câu then chốt đều đúng: `q_refund_window`, `q_hr_annual_leave_under3`, `q_access_level4`, `q_p1_escalation`, `q_p1_update_frequency`.

---

## 4. Freshness & monitoring (100–150 từ)

> SLA bạn chọn, ý nghĩa PASS/WARN/FAIL trên manifest mẫu.

SLA freshness đang đặt 24h ở `contracts/data_contract.yaml`. Run `after-fix-final` FAIL freshness vì `latest_exported_at=2026-04-11T00:00:00`, trong khi chạy lab ngày 2026-06-10; đây là snapshot lab cũ, không phải lỗi clean. Khi dùng source thật, FAIL này phải tạo alert cho owner nguồn để refresh export trước khi agent dùng corpus.

---

## 5. Liên hệ Day 09 (50–100 từ)

> Dữ liệu sau embed có phục vụ lại multi-agent Day 09 không? Nếu có, mô tả tích hợp; nếu không, giải thích vì sao tách collection.

Day 09 agent có thể dùng lại Chroma collection `day10_kb` bằng `CHROMA_DB_PATH=./chroma_db` và `CHROMA_COLLECTION=day10_kb`. Điểm khác biệt là Day 10 chỉ publish dữ liệu đã qua quarantine/expectation, nên agent không còn đọc chunk stale HR 2025 hoặc refund 14 ngày.

---

## 6. Rủi ro còn lại & việc chưa làm

- Chưa có Great Expectations/pydantic validation thật.
- Freshness mới đo từ manifest publish, chưa đo riêng ingest watermark.
- Cần đổi `Linh`/repo local thành họ tên và link repo thật nếu LMS yêu cầu.
