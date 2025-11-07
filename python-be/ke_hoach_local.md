## Kế hoạch triển khai pipeline dựng video tự động (local-first)

### 1. Phạm vi & mục tiêu
- Chỉ tập trung cho repo `video-be`, làm việc thuần local và chạy toàn bộ qua `run_all.bat`.
- Không sử dụng `local_pipeline.py`.
- Thiết kế theo hướng “scale-ready”: khi cần có thể tách thành API/service và giao tiếp với `video-fe`, nhưng toàn bộ logic hiện nằm ở `video-be`.

### 2. Luồng tổng quát
1. **Nhập liệu video**: người dùng đặt trực tiếp file nguồn vào thư mục “inbox” (`python-be/data/input/footage.mp4` mặc định hoặc `data/input/<slug>.mp4` nếu tự đặt tên); `run_all.bat` đọc thẳng từ đây.
2. **TIỀN XỬ LÝ – Auto-Editor**  
   - Script BE gọi `auto-editor` để cắt bỏ khoảng trống.  
   - Quy ước tên file output (ví dụ `data/processed/<slug>_ae.mp4`) để những bước sau dễ tham chiếu.  
   - Lưu metadata (fps, duration, cut list) vào JSON kèm theo.
3. **TRANSCRIPT – Whisper**  
   - Từ file đã tiền xử lý, chạy Whisper (CLI hoặc API local).  
   - Lưu transcript + timestamps dạng JSON/segment list (`data/transcripts/<slug>.json`).  
   - Lưu text thuần để LLM dễ xử lý.
4. **PHÂN TÍCH – Planner (Gemini)**  
   - Dùng lại script `plan_generation/make_plan.py` (Gemini) để sinh plan.  
   - Input: file SRT (`data/transcripts/<slug>.srt`), metadata, tùy chọn scene_map/catalog.  
   - Output: `plan_<slug>.json` gồm danh sách cảnh + thời gian cắt + ghi chú dựng.
5. **XUẤT – Plan JSON**  
   - Lưu plan thành JSON ngay trong `video-be` (ví dụ `data/plans/<slug>.json`).  
   - Chuẩn hóa schema để sau này BE có thể expose API hoặc đồng bộ sang `video-fe` khi cần.

### 3. Kiến trúc thư mục đề xuất (local)
```
video-be/
 ├─ run_all.bat
 ├─ python-be/
 │   ├─ app/ (chứa modules từng bước)
 │   ├─ configs/
 │   └─ ke_hoach_local.md (tài liệu này)
 └─ data/
     ├─ input/
     ├─ processed/
     ├─ transcripts/
     ├─ plans/
     └─ logs/
```

### 4. Chi tiết từng module BE
| Module | Mô tả | Công nghệ/Ghi chú |
|--------|-------|-------------------|
| `ingest` | Kiểm tra file nguồn, tạo slug/project id, validate định dạng | Python script + watchdog (nếu cần realtime) |
| `auto_editor_runner` | Gọi `auto-editor` CLI thông qua subprocess; parse log để lấy timestamps cắt | Cần config tham số (min clip length, silence threshold) |
| `transcriber` | Gọi Whisper (CLI/Python) -> trả transcript + segments (start/end/sec + text) | Ưu tiên model nhỏ (base/small) cho local |
| `planner_llm` | Wrapper gọi `plan_generation/make_plan.py` (Gemini) dựa trên SRT đã tạo | Cần `GEMINI_API_KEY`, hỗ trợ `--plan-*` args |
| `exporter` | Gom metadata, transcript, plan -> ghi file trong `data/plans` (và các artifact khác) | Sau này có thể thêm bước push ra API/FE |
| `orchestrator` | Điều phối tuần tự các bước, log trạng thái, retry, raise error | Sẵn sàng chuyển thành FastAPI route trong tương lai |

### 5. Hướng dẫn chạy local
1. Cài dependencies (Python env, auto-editor, Whisper, bất kỳ LLM client).  
2. Đặt video nguồn vào `data/input/<project>.mp4`.  
3. Chạy `run_all.bat` (script sẽ:
   - active env → gọi `python-be/app/orchestrator.py --input <path>`
   - in log ra console + ghi `data/logs/<project>.log`
4. Kết quả:  
   - Video đã cắt: `data/processed/<slug>_ae.mp4`  
   - Transcript: `data/transcripts/<slug>.json`, `.txt`, `.srt`  
   - Plan: `data/plans/<slug>.json` (đây là output chính để các hệ thống khác đọc tiếp)

### 6. Checklist để scale thành API
- [ ] Chuẩn hóa schema I/O (OpenAPI spec).  
- [ ] Trừu tượng hóa layer storage (S3/local).  
- [ ] Đóng gói từng module thành service nhỏ hoặc task queue.  
- [ ] Thêm queue (Redis/Rabbit) + worker nếu phải xử lý nhiều video song song.  
- [ ] Tách config environment (dev/local/prod).  
- [ ] Bổ sung auth & quota khi expose ra ngoài.

### 7. Công việc tiếp theo
1. Tạo skeleton cho từng module Python + config mẫu.  
2. Viết orchestrator CLI đọc tham số, log rõ ràng.  
3. Thiết lập Whisper + auto-editor (script kiểm tra dependency).  
4. Viết prompt + logic parse output LLM.  
5. Mock consumer đọc `data/plans/<slug>.json` (ví dụ script preview).  
6. Viết hướng dẫn README chi tiết để người khác tái tạo môi trường local.
