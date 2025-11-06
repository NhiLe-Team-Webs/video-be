# Quy trình Workflow Backend: Từ Video Đầu vào đến Video Cuối cùng cho Frontend

Quy trình workflow backend tự động hóa việc tạo video bắt đầu từ một tệp video đầu vào và kết thúc bằng việc chuẩn bị các tài nguyên cần thiết cho ứng dụng Remotion frontend để render video cuối cùng. Điểm khởi đầu chính của quy trình này được điều phối bởi script shell [`python-be/run_all.sh`](python-be/run_all.sh) (hoặc [`python-be/run_all.bat`](python-be/run_all.bat) trên Windows).

Dưới đây là mô tả chi tiết về các bước xử lý chính, bao gồm các tệp mã nguồn và hàm chịu trách nhiệm cho từng chức năng.

---

## 1. Khởi tạo và Đồng bộ hóa Cơ sở Kiến thức

*   **Mô tả kỹ thuật**: Bước này là nền tảng, đảm bảo rằng cơ sở kiến thức của hệ thống được cập nhật và sẵn sàng để sử dụng. Nó bao gồm việc thu thập, phân tích cú pháp, và chuyển đổi các tài liệu kiến thức thô (như các tệp Markdown chứa hướng dẫn, định nghĩa yếu tố, ví dụ mẫu và lược đồ JSON) thành một định dạng có cấu trúc. Quá trình này cũng tạo ra các nhúng vector (vector embeddings) cho nội dung văn bản, cho phép tìm kiếm ngữ nghĩa hiệu quả. Cuối cùng, dữ liệu có cấu trúc và các nhúng vector này được lưu trữ vào các tệp đầu ra đã được lưu vào bộ đệm để truy cập nhanh chóng bởi các thành phần khác.
*   **Tệp/Hàm chính**:
    *   [`python-be/run_all.sh`](python-be/run_all.sh): Kích hoạt bước này bằng lệnh: `$PYTHON data_processing/sync_knowledge_base.py` (Dòng 38).
    *   [`python-be/data_processing/sync_knowledge_base.py`](python-be/data_processing/sync_knowledge_base.py): Hàm `main()` là điểm vào, gọi `knowledge_base.sync_knowledge_base()`.
    *   [`python-be/knowledge_base/ingestion.py`](python-be/knowledge_base/ingestion.py):
        *   Lớp `KnowledgeBaseIngestor`: Quản lý toàn bộ quá trình nạp, xử lý, vector hóa và lưu trữ.
        *   Phương thức `load()`: Quét thư mục `knowledge-base/` để tìm các tệp `.md` và `.json`.
        *   Phương thức `_process_markdown()`: Sử dụng [`markdown_parser.py`](python-be/knowledge_base/markdown_parser.py) để phân tích cú pháp Markdown thành các đối tượng `KnowledgeDocument`.
        *   Phương thức `_process_json()`: Tải và xác thực các tệp JSON (bao gồm lược đồ), tính toán băm SHA256 để phát hiện thay đổi.
        *   Phương thức `vectorise()`: Sử dụng `Vectoriser` (từ [`python-be/knowledge_base/vector_store.py`](python-be/knowledge_base/vector_store.py)) để tạo nhúng vector cho các phần văn bản.
        *   Phương thức `persist()`: Lưu các tài liệu có cấu trúc và nhúng vector vào các tệp đầu ra.
    *   [`python-be/knowledge_base/markdown_parser.py`](python-be/knowledge_base/markdown_parser.py): Hàm `parse_markdown_document()` trích xuất front matter và phân đoạn nội dung Markdown thành các `MarkdownSection`.
    *   [`python-be/knowledge_base/models.py`](python-be/knowledge_base/models.py): Định nghĩa các mô hình dữ liệu Pydantic như `KnowledgeDocument`, `VectorisedChunk`, `DocumentType`, `GuidelineRule`, `ElementDefinition`, `ExampleSnippet`, `GlossaryTerm` để đảm bảo tính nhất quán dữ liệu.
    *   [`python-be/knowledge_base/vector_store.py`](python-be/knowledge_base/vector_store.py): Lớp `Vectoriser` chịu trách nhiệm tạo các nhúng vector từ văn bản.
*   **Luồng dữ liệu liên quan**: Các tệp Markdown và JSON thô (`knowledge-base/`) -> `KnowledgeDocument` và `VectorisedChunk` objects (trong bộ nhớ) -> Các tệp JSON có cấu trúc (`structured.json`, `embeddings.json`, `schema_cache.json`) trong `python-be/outputs/knowledge/`.

---

## 2. Xử lý Video Đầu vào (Cắt bỏ khoảng lặng và Tạo phụ đề)

*   **Mô tả kỹ thuật**: Video đầu vào thô được xử lý qua hai giai đoạn chính. Đầu tiên, thư viện `auto_editor` được sử dụng để phân tích âm thanh của video và tự động cắt bỏ các đoạn im lặng, tạo ra một phiên bản video cô đọng hơn. Sau đó, thư viện `whisper` của OpenAI được áp dụng cho video đã cắt để chuyển đổi giọng nói thành văn bản, tạo ra một tệp phụ đề SRT chi tiết.
*   **Tệp/Hàm chính**:
    *   [`python-be/run_all.sh`](python-be/run_all.sh):
        *   **Cắt bỏ khoảng lặng**: Dòng 43-51: `$PYTHON -m auto_editor "$SOURCE_VIDEO" -o "$AUTO_EDITOR_OUTPUT" ...`
        *   **Tạo phụ đề**: Dòng 56-62: `$PYTHON -m whisper "$AUTO_EDITOR_OUTPUT" --model small ...`
*   **Dữ liệu đầu vào**: `SOURCE_VIDEO` (được định nghĩa là `$SCRIPT_DIR/../public/input/input.mp4` hoặc đối số dòng lệnh đầu tiên).
*   **Dữ liệu đầu ra**:
    *   `AUTO_EDITOR_OUTPUT` (ví dụ: `python-be/outputs/stage1_cut.mp4`): Video đã được cắt bỏ khoảng lặng.
    *   `WHISPER_SRT` (ví dụ: `python-be/outputs/stage1_cut.srt`): Tệp phụ đề SRT của video đã cắt.

---

## 3. Tạo Bản đồ Cảnh (Scene Map) và Cửa sổ Huấn luyện (Training Windows)

*   **Mô tả kỹ thuật**: Từ tệp phụ đề SRT, hệ thống tiến hành phân tích nội dung để tạo ra một bản đồ cảnh chi tiết. Bản đồ cảnh này chứa siêu dữ liệu phong phú về các phân đoạn video, bao gồm các chủ đề chính, cảm xúc được phát hiện, điểm nổi bật tiềm năng, và các gợi ý cho chuyển động/hiệu ứng âm thanh. Đồng thời, các "cửa sổ huấn luyện" được chuẩn bị, đây là các đoạn văn bản được căn chỉnh theo thời gian từ phụ đề, có thể được sử dụng cho các tác vụ học máy tiếp theo hoặc để phân tích sâu hơn về cấu trúc nội dung.
*   **Tệp/Hàm chính**:
    *   [`python-be/run_all.sh`](python-be/run_all.sh):
        *   **Tạo bản đồ cảnh**: Dòng 73: `$PYTHON -m data_processing.generate_scene_map "$WHISPER_SRT" -o "$SCENE_MAP"`
        *   **Tạo cửa sổ huấn luyện**: Dòng 76: `$PYTHON -m data_processing.prepare_training_windows "$WHISPER_SRT" "$TRAINING_WINDOWS"`
    *   [`python-be/data_processing/generate_scene_map.py`](python-be/data_processing/generate_scene_map.py): Script này đọc tệp SRT và phân tích nó để tạo ra cấu trúc bản đồ cảnh.
    *   [`python-be/data_processing/prepare_training_windows.py`](python-be/data_processing/prepare_training_windows.py): Script này xử lý tệp SRT để tạo ra các cửa sổ huấn luyện.
*   **Dữ liệu đầu vào**: `WHISPER_SRT` (tệp phụ đề).
*   **Dữ liệu đầu ra**:
    *   `SCENE_MAP` (ví dụ: `python-be/outputs/scene_map.json`): Tệp JSON chứa bản đồ cảnh với siêu dữ liệu phân đoạn.
    *   `TRAINING_WINDOWS` (ví dụ: `python-be/outputs/training_windows.json`): Tệp JSON chứa dữ liệu được chuẩn bị cho huấn luyện.

---

## 4. Tạo Kế hoạch Video (Video Plan) bằng LLM (Gemini)

*   **Mô tả kỹ thuật**: Đây là bước cốt lõi nơi mô hình ngôn ngữ lớn (LLM) Gemini được sử dụng để tạo ra một kế hoạch chỉnh sửa video ban đầu. LLM nhận một lời nhắc (prompt) được xây dựng cẩn thận, bao gồm bản ghi phụ đề, các quy tắc chỉnh sửa, gợi ý lược đồ và ngữ cảnh phong phú từ cơ sở kiến thức và các danh mục tài sản. Phản hồi của LLM, một đối tượng JSON, sau đó được trích xuất và chuẩn hóa để đảm bảo tính nhất quán và tuân thủ cấu trúc dữ liệu mong muốn.
*   **Tệp/Hàm chính**:
    *   [`python-be/run_all.sh`](python-be/run_all.sh): Dòng 81: `$PYTHON -m plan_generation.make_plan_gemini "$WHISPER_SRT" "$PLAN_TMP" --scene-map "$SCENE_MAP"`
    *   [`python-be/plan_generation/make_plan_gemini.py`](python-be/plan_generation/make_plan_gemini.py):
        *   Hàm `main()`: Điều phối quá trình tạo kế hoạch.
        *   Hàm `build_prompt()`: Xây dựng lời nhắc cho LLM. Nó tích hợp `SrtEntry` (từ `parse_srt`), `scene_map` (từ `summarize_scene_map`), `broll_catalog`, `sfx_catalog`, `motion_rules` (tải từ `assets/`), và `KnowledgeService` (từ [`python-be/plan_generation/knowledge.py`](python-be/plan_generation/knowledge.py) và [`python-be/knowledge_base/repository.py`](python-be/knowledge_base/repository.py)) để cung cấp ngữ cảnh phong phú.
        *   Hàm `configure_client()`: Cấu hình client Gemini API bằng `GEMINI_API_KEY`.
        *   Hàm `extract_plan_json()`: Trích xuất đối tượng JSON từ phản hồi văn bản của LLM, xử lý các khối mã được rào.
        *   Hàm `normalize_plan()`: Chuẩn hóa cấu trúc kế hoạch JSON, đảm bảo các trường như `sourceStart`, `duration`, `transitionIn/Out`, `highlights` tuân thủ định dạng mong đợi và áp dụng các giá trị mặc định.
        *   Hàm `dump_plan()`: Lưu kế hoạch đã chuẩn hóa vào tệp JSON.
*   **Dữ liệu đầu vào**: `WHISPER_SRT` (phụ đề), `SCENE_MAP` (bản đồ cảnh), `assets/broll_catalog.json`, `assets/sfx_catalog.json`, `assets/motion_rules.json`, và dữ liệu từ cơ sở kiến thức đã đồng bộ hóa (thông qua `KnowledgeService`).
*   **Dữ liệu đầu ra**: `PLAN_TMP` (ví dụ: `python-be/outputs/plan.json`): Kế hoạch chỉnh sửa video thô ở định dạng JSON.

---

## 5. Làm giàu Kế hoạch Video (Enrich Plan)

*   **Mô tả kỹ thuật**: Kế hoạch video thô được tạo bởi LLM được làm giàu thêm. Bước này có thể bao gồm việc tự động gán các tài sản B-roll phù hợp từ danh mục, tinh chỉnh các hiệu ứng chuyển động dựa trên quy tắc, và thêm các gợi ý khác dựa trên phân tích sâu hơn về bản đồ cảnh và các danh mục tài sản. Mục tiêu là biến kế hoạch thô thành một kế hoạch chi tiết và hoàn chỉnh hơn, sẵn sàng cho việc render.
*   **Tệp/Hàm chính**:
    *   [`python-be/run_all.sh`](python-be/run_all.sh): Dòng 91: `$PYTHON -m plan_generation.enrich_plan "$PLAN_TMP" "$PLAN_ENRICHED" --scene-map "$SCENE_MAP"`
    *   [`python-be/plan_generation/enrich_plan.py`](python-be/plan_generation/enrich_plan.py): Hàm `main()` đọc kế hoạch thô, sử dụng bản đồ cảnh và các danh mục tài sản để thêm chi tiết và làm giàu kế hoạch. Logic làm giàu cụ thể sẽ nằm trong script này.
*   **Dữ liệu đầu vào**: `PLAN_TMP` (kế hoạch thô), `SCENE_MAP` (bản đồ cảnh), `broll_catalog.json`, `sfx_catalog.json`, `motion_rules.json`.
*   **Dữ liệu đầu ra**: `PLAN_ENRICHED` (ví dụ: `python-be/outputs/plan_enriched.json`): Kế hoạch video đã được làm giàu, sẵn sàng cho frontend.

---

## 6. Chuẩn bị Dữ liệu và Tài nguyên cho Frontend (Remotion App)

*   **Mô tả kỹ thuật**: Các tài nguyên chính cần thiết cho việc render video trên frontend được sao chép vào một thư mục công khai mà ứng dụng Remotion có thể truy cập trực tiếp. Điều này bao gồm video đã cắt và kế hoạch video đã làm giàu. Việc sao chép này đảm bảo rằng Remotion có tất cả các tệp cần thiết ở đúng vị trí để bắt đầu quá trình render.
*   **Tệp/Hàm chính**:
    *   [`python-be/run_all.sh`](python-be/run_all.sh):
        *   Dòng 96: `cp "$AUTO_EDITOR_OUTPUT" "$PUBLIC_INPUT/input.mp4"`
        *   Dòng 97: `cp "$PLAN_ENRICHED" "$PUBLIC_INPUT/plan.json"`
*   **Dữ liệu đầu vào**: `AUTO_EDITOR_OUTPUT` (video đã cắt), `PLAN_ENRICHED` (kế hoạch đã làm giàu).
*   **Dữ liệu đầu ra**:
    *   `public/input/input.mp4`: Video đã cắt, được đổi tên thành `input.mp4` cho Remotion.
    *   `public/input/plan.json`: Kế hoạch video đã làm giàu, được đổi tên thành `plan.json` cho Remotion.

---

## 7. Chuyển giao cho Frontend và Render Video Cuối cùng

*   **Mô tả kỹ thuật**: Sau khi tất cả dữ liệu và tài nguyên đã được backend chuẩn bị và đặt vào thư mục `public/input/`, quy trình chuyển giao cho ứng dụng Remotion frontend. Ứng dụng Remotion, một thư viện React để tạo video, sẽ đọc `input.mp4` và `plan.json` để xây dựng và render video cuối cùng. Các thành phần React của Remotion sẽ diễn giải kế hoạch JSON và kết hợp video, văn bản, hiệu ứng và âm thanh để tạo ra đầu ra cuối cùng.
*   **Tệp/Hàm chính**:
    *   [`python-be/run_all.sh`](python-be/run_all.sh): Dòng 102: `echo "[NEXT] Run: cd ../remotion-app && npm install && npm run render"` hướng dẫn người dùng chạy lệnh render Remotion.
    *   `remotion-app/src/index.ts`: Điểm khởi đầu của ứng dụng Remotion, đăng ký các composition video.
    *   `remotion-app/src/Root.tsx`: Thành phần gốc của Remotion, nơi dữ liệu kế hoạch được tải và các thành phần video được tổ chức.
    *   `remotion-app/src/hooks/usePlan.ts`: Một React hook để tải và phân tích cú pháp `plan.json` từ `public/input/`.
    *   `remotion-app/src/components/FinalComposition.tsx`: Thành phần Remotion chính chịu trách nhiệm render video dựa trên dữ liệu kế hoạch. Nó sử dụng các thành phần con khác (ví dụ: `SegmentClip`, `HighlightsLayer`, `SfxLayer`) để hiển thị các yếu tố video.
*   **Video cuối cùng được lưu trữ/xuất ra**: Video cuối cùng được tạo ra bởi lệnh `npm run render` của Remotion. Vị trí lưu trữ cụ thể sẽ phụ thuộc vào cấu hình trong `remotion-app/remotion.config.ts` và các đối số được truyền cho lệnh `render`, nhưng thường sẽ là một tệp video (ví dụ: `.mp4`) trong thư mục đầu ra của Remotion (ví dụ: `remotion-app/out/`).

---

## Vai trò và Tích hợp của Cơ sở Kiến thức trong Workflow

Cơ sở kiến thức đóng một vai trò trung tâm trong việc hướng dẫn và làm giàu quá trình tạo kế hoạch video, đảm bảo rằng đầu ra của AI không chỉ hợp lệ về mặt kỹ thuật mà còn phù hợp về mặt ngữ cảnh và tuân thủ các nguyên tắc chỉnh sửa.

### Vai trò chính:

1.  **Cung cấp Ngữ cảnh và Quy tắc**: Cơ sở kiến thức chứa các tài liệu như `planning_guidelines.md`, `element_definitions.md`, `glossary.md`, và `examples/patterns.md/.json`. Những tài liệu này định nghĩa các quy tắc chỉnh sửa, mục đích của các yếu tố video, định nghĩa thuật ngữ và các ví dụ về "thực hành tốt" và "thực hành xấu".
2.  **Hướng dẫn AI**: Thông tin này được sử dụng để xây dựng lời nhắc cho LLM (Gemini), giúp AI hiểu cách tạo ra các kế hoạch video chất lượng cao, tuân thủ các ràng buộc và phong cách mong muốn.
3.  **Tìm kiếm Ngữ nghĩa**: Các nhúng vector của nội dung kiến thức cho phép AI thực hiện tìm kiếm ngữ nghĩa, tìm kiếm các phần kiến thức liên quan nhất dựa trên ngữ cảnh của bản ghi phụ đề hoặc các phân đoạn video.

### Cách tích hợp và Điểm tương tác chính:

1.  **Đồng bộ hóa ban đầu**:
    *   **Tệp/Hàm**: [`python-be/data_processing/sync_knowledge_base.py`](python-be/data_processing/sync_knowledge_base.py) và [`python-be/knowledge_base/ingestion.py`](python-be/knowledge_base/ingestion.py).
    *   **Luồng dữ liệu**: Các tệp Markdown và JSON thô từ `knowledge-base/` được phân tích cú pháp, cấu trúc hóa và vector hóa. Dữ liệu này được lưu vào `python-be/outputs/knowledge/structured.json` và `python-be/outputs/knowledge/embeddings.json`.
    *   **Mục đích**: Chuẩn bị cơ sở kiến thức ở định dạng có thể truy cập và tìm kiếm được cho các bước tiếp theo.

2.  **Tạo lời nhắc cho LLM**:
    *   **Tệp/Hàm**: [`python-be/plan_generation/make_plan_gemini.py`](python-be/plan_generation/make_plan_gemini.py) (đặc biệt là hàm `build_prompt()`).
    *   **Luồng dữ liệu**:
        *   `KnowledgeService` (từ [`python-be/plan_generation/knowledge.py`](python-be/plan_generation/knowledge.py), sử dụng [`python-be/knowledge_base/repository.py`](python-be/knowledge_base/repository.py)) được khởi tạo để truy cập cơ sở kiến thức đã xử lý.
        *   `build_prompt()` sử dụng `knowledge_service.guideline_summaries()` để tìm kiếm các hướng dẫn liên quan dựa trên một đoạn trích bản ghi phụ đề.
        *   Các tóm tắt từ `broll_catalog.json`, `sfx_catalog.json`, `motion_rules.json` cũng được tải và đưa vào lời nhắc.
        *   Các ví dụ mẫu từ `examples/patterns.json` và `examples/patterns.md` được sử dụng để định hình `schema_hint` và `rules` trong lời nhắc, cung cấp cho AI các ví dụ cụ thể về cấu trúc và phong cách mong muốn.
    *   **Mục đích**: Cung cấp cho LLM một ngữ cảnh phong phú và các ràng buộc rõ ràng để tạo ra một kế hoạch video chất lượng cao, tuân thủ các nguyên tắc chỉnh sửa.

3.  **Học hỏi và Trích xuất thông tin của AI**:
    *   **Cơ chế học hỏi**: Mô hình AI (Gemini) không "học" theo nghĩa truyền thống từ cơ sở kiến thức trong thời gian chạy. Thay vào đó, nó được "hướng dẫn" thông qua kỹ thuật "in-context learning" (học trong ngữ cảnh). Bằng cách đưa các quy tắc, định nghĩa, ví dụ tích cực và tiêu cực trực tiếp vào lời nhắc, AI có thể áp dụng kiến thức này để tạo ra phản hồi phù hợp.
    *   **Trích xuất thông tin**: Khi `build_prompt()` gọi `knowledge_service.guideline_summaries()`, nó thực hiện tìm kiếm ngữ nghĩa trong kho vector (được xây dựng từ `embeddings.json`). Các đoạn văn bản kiến thức có nhúng vector gần nhất với nhúng vector của đoạn trích bản ghi phụ đề sẽ được truy xuất. Điều này cho phép AI trích xuất các hướng dẫn hoặc thông tin liên quan nhất từ cơ sở kiến thức để đưa vào lời nhắc.
    *   **Tương tác với `graph.py`**: Mặc dù không trực tiếp trong quá trình tạo lời nhắc, đồ thị kiến thức được xây dựng bởi [`python-be/knowledge_base/graph.py`](python-be/knowledge_base/graph.py) có thể được sử dụng trong các giai đoạn phát triển hoặc gỡ lỗi để hiểu cấu trúc kiến thức, hoặc trong tương lai có thể được sử dụng để thực hiện các truy vấn phức tạp hơn về mối quan hệ giữa các tài liệu.

---