# Element Definitions & Layering Rules

This document outlines the various video elements used in the automation pipeline, their purposes, and the rules governing their placement and layering. These definitions are compiled from `video1.json`, `video2.json`, and other production metadata, providing a consistent framework for AI-generated video plans. For machine-readable constraints and validation rules, refer to [element_schema.md](element_schema.md).

## Element Families

### `broll`
- **Purpose** - Cung cấp cảnh quay bổ sung (b-roll) để minh họa hoặc củng cố ý tưởng đang được nói, giúp tăng cường sự hấp dẫn thị giác và truyền tải thông điệp hiệu quả hơn.
- **Layer** - `video` (thay thế hoặc phủ lên nguồn cấp dữ liệu chính của người nói).
- **Key fields** - `description` (mô tả nội dung b-roll), `context` (ngữ cảnh sử dụng), optional `tags` (các thẻ phân loại để tìm kiếm và khớp với kho tài sản).
- **Defaults** - Phát cho đến khi một phần tử lớp `video` khác xuất hiện hoặc dòng thời gian quay trở lại lớp `main`.

### `text_overlay`
- **Purpose** - Hiển thị văn bản trên màn hình với kiểu dáng thương hiệu, dùng để làm nổi bật thông tin quan trọng, tiêu đề, hoặc các điểm nhấn.
- **Layer** - `overlay` (lớp phủ).
- **Key fields** - `content` (nội dung văn bản), `style` (kiểu dáng hiển thị), `animation` (hiệu ứng động khi xuất hiện/biến mất).
- **Common styles** - `simple_text` (chỉ văn bản, đơn giản), `section_box` (hộp chứa văn bản kèm hiệu ứng động cho các đoạn chia điểm).
- **Defaults** - Duy trì hiển thị cho đến khi có lớp phủ tiếp theo hoặc thay đổi ngữ cảnh.

### `text_animation`
- **Purpose** - Tạo hiệu ứng hoạt hình cho văn bản, thường dùng để hiển thị số đếm, tiến trình, hoặc nhấn mạnh các từ khóa quan trọng.
- **Layer** - `overlay` (lớp phủ).
- **Key fields** - `content` (nội dung văn bản), `animation` (kiểu hoạt ảnh), `emphasis` (mức độ nhấn mạnh).
- **Common animations** - `count_up` (đếm lên), `typing_effect` (hiệu ứng gõ chữ), `flow_chart` (biểu đồ dòng chảy), `progression_arrow` (mũi tên tiến trình), `expansion_flow` (dòng chảy mở rộng), `fade_in_list` (danh sách mờ dần), `pulse` (hiệu ứng nhấp nháy).

### `sound_effect`
- **Purpose** - Sử dụng các tín hiệu âm thanh ngắn để nhấn mạnh các khoảnh khắc quan trọng, tạo cảm xúc hoặc tăng cường trải nghiệm người xem.
- **Layer** - `audio` (lớp âm thanh).
- **Key field** - `sound` (tham chiếu đến ID âm thanh trong `sfx_catalog.json`).
- **Common sounds** - `transition_rewind` (chuyển cảnh tua lại), `whoosh_standard` (tiếng vút tiêu chuẩn), `ui_pop` (tiếng pop giao diện người dùng), `money` (tiền), `success` (thành công), `fire` (lửa), `achievement` (thành tựu), `crash` (va chạm), `money_loss` (mất tiền), `typing` (gõ phím), `confusion` (bối rối), `expansion` (mở rộng), `emphasis_ding` (tiếng ding nhấn mạnh), `heartbeat_soft` (tiếng tim đập nhẹ).
- **Defaults** - Phát một lần với thời lượng được xác định bởi tài sản âm thanh gốc.

### `effect`
- **Purpose** - Tạo các chuyển động hình ảnh hoặc hiệu ứng chuyển cảnh giữa các clip, giúp video mượt mà và hấp dẫn hơn.
- **Layer** - `transition` (lớp chuyển cảnh).
- **Key fields** - `action` (hành động chuyển cảnh), `duration` (thời lượng hiệu ứng).
- **Common actions** - `zoom_in` (phóng to), `zoom_out` (thu nhỏ), `fade` (mờ dần), `slide_left` (trượt sang trái), `slide_right` (trượt sang phải), `push_in` (đẩy vào), `camera_shake` (rung máy ảnh).
- **Defaults** - Thời lượng từ 0.5-2.0 giây trừ khi được ghi đè bởi trường `duration`.

### `icon`
- **Purpose** - Sử dụng các biểu tượng đồ họa tĩnh hoặc có chuyển động tối thiểu để minh họa ý tưởng, cung cấp thông tin nhanh chóng hoặc tăng cường nhận diện thương hiệu.
- **Layer** - `overlay` (lớp phủ).
- **Key fields** - `content` (nội dung biểu tượng, thường là tên file hoặc ID), `context` (ngữ cảnh sử dụng).

### `speaker_intro`, `achievement_highlight`, `section_header`, `emphasis`
- **Purpose** - Các tín hiệu cấp cao chuyên biệt được sử dụng để giới thiệu người nói, làm nổi bật các cột mốc quan trọng, đánh dấu các phần hoặc làm nổi bật các từ khóa. Chúng xuất hiện trên lớp `main` hoặc `overlay`.
- **Usage Notes** - Sử dụng một cách tiết kiệm và liên kết chặt chẽ với các điểm nhấn trong các file `videos/*.md` để đảm bảo tính nhất quán và hiệu quả.

## Layer Stack

1. `main` - primary camera feed (baseline footage).
2. `video` - b-roll replacing or augmenting the main layer.
3. `overlay` - text, icons, and animated graphics.
4. `audio` - sound effects mixed with narration.
5. `transition` - temporary visual effects used between clips.

Respect layer priority to avoid stacking conflicts; only one dominant element per layer at a time.

## Synchronisation Notes

- Multiple elements can share the same timestamp; treat them as simultaneous but respect layer ordering.
- Transitions (`effect`) should begin before or exactly with the visual/text they introduce.
- Use `style` values to keep branding consistent (default: `highlighted_background` for critical callouts).
- Populate `context` to support catalog lookups (see [asset_catalogs.md](asset_catalogs.md)).
- Record `confidence` when available to support downstream thresholding (optional field in `element_schema.json`).

## Automation Rule Updates

- **Full-frame b-roll** – Every assigned `broll` clip now renders as a full-screen cover beneath overlays. Keep shot selection clear of critical on-screen action, because text overlays will always sit above this layer.
- **Compressed highlight copy** – Generated `noteBox`/`text_overlay` content must be distilled to 1–3 uppercase keywords (primary nouns/verbs). Dual-column highlights should keep each side within this limit.
- **Staggered overlays** – When both left/right supporting texts are present, the left column should appear a fraction earlier (≈0.2 s) to mirror the pacing demonstrated in Video 1.
