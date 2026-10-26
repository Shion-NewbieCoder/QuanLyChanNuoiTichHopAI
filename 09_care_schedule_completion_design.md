# FINAL-01 — Thiết kế tối thiểu để hoàn thiện lịch chăm sóc

> **FINAL-02 đã triển khai và commit tại `e3bf36a`; FINAL-03 bổ sung chatbot tra cứu lịch chăm sóc, ghi tại mục 9.** Phần 1–7 bên dưới lưu nguyên trạng phân tích và đề xuất của FINAL-01 ngày 2026-10-26; các câu “chưa triển khai/cần chốt” trong phần đó mô tả thời điểm viết thiết kế. Xem cập nhật triển khai ở mục 8. Ký hiệu **A** = đề gốc yêu cầu trực tiếp; **B** = quyết định/contract hiện hữu; **C** = đề xuất mới tại thời điểm FINAL-01.

## 1. Trạng thái repository được quan sát

- Git root và project root: `F:\Desktop\QuanLyChanNuoiAI` (dự án **QuanLyChanNuoiAI**); branch `master`; HEAD `09d8ac69c1d1f485d4285ced8d90473047655540`.
- `git status --short` lúc bắt đầu: rỗng. Không tìm thấy `AGENTS.md` trong repo hoặc thư mục cha được tìm kiếm. Chưa đối chiếu GitHub; không suy ra workspace trùng remote.
- Chỉ đọc tài liệu và source/test. Không chạy migrate, seed, server, launcher, AI live hay kiểm thử implementation trong lượt thiết kế này.

## 2. Đối chiếu yêu cầu với source

| Loại bằng chứng | Yêu cầu/quyết định và vị trí | Source/test quan sát được | Khoảng thiếu hoặc giới hạn |
|---|---|---|---|
| **A — đề gốc** | `Đề bài Dự Án.txt:14,21,30`: quản lý lịch chăm sóc; AI nhắc lịch chăm sóc **và** tiêm phòng; test lịch chăm sóc và AI. `01_requirements_chan_nuoi_ai.md:116,128` ghi `FR-CARE-001`, `FR-AI-001` là MUST. | Có nhật ký chăm sóc và lịch vaccine riêng. | Chưa có lịch chăm sóc để tạo/xem/cập nhật hoặc làm nguồn nhắc chăm sóc. |
| **B — quyết định nội bộ** | `01_requirements_chan_nuoi_ai.md:375-383`, `02_design_chan_nuoi_ai.md:370-388`, `03_implementation_plan_chan_nuoi_ai_reviewed.md:120`: TSK-021 chỉ dùng vaccine, hoãn care reminder cho đến khi có schedule model. `07_kt3_ai_integration_design.md:61-69` và `08_kt3_provider_amendment.md:86-94` giữ contract đó. | `backend/apps/ai/reminders.py:14-42` chỉ query `VaccineSchedule`; context chỉ có `vaccine_schedules`. | Deferred là giới hạn triển khai nội bộ, **không** phải bằng chứng giảng viên bỏ yêu cầu A. |
| **B — bản ghi thực tế** | `02_design_chan_nuoi_ai.md:159,178,220`: `CareLog` là nhật ký theo Herd. | `backend/apps/care/models.py:7-18` có `recorded_at`, `activity`, `notes`; `FeedRecord`/`MedicineRecord` ở cùng file là bản ghi đã dùng. API `backend/apps/care/views.py:10-40` và `urls.py:5-10` chỉ có log/feed/medicine. | Không có `CareSchedule` hay ngày dự kiến/trạng thái lịch. Không suy `CareLog` thành việc tương lai. |
| **B — lịch vaccine** | `01_requirements_chan_nuoi_ai.md:430-453` (OQ-005): phân loại ngày dẫn xuất cũng áp dụng cho lịch chăm sóc khi có thực thể lịch. | `backend/apps/vaccinations/models.py:4-29` có `VaccineSchedule`; `serializers.py:10-24` tính `overdue`, `due today`, `due soon`, `scheduled-not-yet-due`, bỏ completed/cancelled; `VaccinationRecord` lưu lần tiêm riêng. `tests_api.py:139-186` kiểm thử phân loại. | Quy tắc ngày có thể tái sử dụng, nhưng chưa có lịch chăm sóc để áp dụng. Không cần đổi vaccine. |
| **B — AI Reminder** | `PD-AI-REMINDER-001` cho scope `all` hoặc `herd`, ngày lọc inclusive, loại completed/cancelled, không nguồn thì không gọi provider. | `backend/apps/ai/serializers.py:20-39`, `views.py:28-37`, `reminders.py:14-42`, `prompts/reminders.py:7-43`; `backend/apps/ai/tests.py:163-207` kiểm tra vaccine, quyền, nguồn rỗng. `CURRENT_PROMPT` là V2 và chỉ nói VaccineSchedule. | Chưa chọn/gửi care schedule; prompt hiện hành không được dùng để diễn đạt nguồn mới khi chưa versioning/review. |
| **B — UI và quyền** | `01_requirements_chan_nuoi_ai.md:353-365`, `02_design_chan_nuoi_ai.md:557-565`: ma trận quyền các resource hiện hữu. | `backend/apps/dashboard/resources.py:56-72` có màn nhật ký `/care/` và vaccine `/vaccines/`; `forms.py:33-90`, `ui.py:74-171`, `ui_urls.py:10-17` tạo form/list/detail/CRUD từ registry. `backend/apps/users/permissions.py:24-61` có nhóm `care`, `vaccination`, `ai`; `tests_ui.py:90-132` và `test_role_permissions.py:138-163` kiểm tra quyền. | Chưa có resource/màn hình lịch chăm sóc hoặc badge cảnh báo cho lịch đó. Quyền của **resource mới** chưa được phê duyệt riêng. |
| **B — demo/chat** | `01_requirements_chan_nuoi_ai.md:416-428` chốt count của dữ liệu demo gốc. | `backend/apps/dashboard/management/commands/seed_demo.py:63-65,183-239` tạo CareLog lịch sử và VaccineSchedule; `tests_seed_demo.py:36-70` kiểm count. `backend/apps/ai/chat.py:45,347,378` dùng nguồn `care` từ CareLog (tối đa 10 bản ghi). | Chưa có seed care schedule. Chatbot hiện **không** truy vấn lịch chăm sóc; không dùng câu trả lời chat làm bằng chứng Reminder đã hoàn thiện. |

`05_review_testing_chan_nuoi_ai_final.md:199` và `06_final_delivery_chan_nuoi_ai_final.md:185` nhắc tới AI chăm sóc/tiêm phòng ở mức yêu cầu hoặc checklist; source nêu trên mới chứng minh phần vaccine. README chỉ là hướng dẫn hỗ trợ, không thay bằng chứng source.

## 3. Phương án khuyến nghị: thêm `CareSchedule` theo Herd

Một model lịch riêng trong `apps.care` tách kế hoạch tương lai khỏi `CareLog` ghi nhận hoạt động. Nó dùng `Herd` làm target như `CareLog` và Reminder hiện tại. Không thêm target đa hình, lịch lặp, email/SMS, tác vụ nền, lịch kiểm tra sức khỏe riêng hoặc chức năng chẩn đoán/tư vấn. Các lựa chọn gắn **C** dưới đây là đề xuất để sinh viên phê duyệt, không phải requirement đã duyệt.

### 3.1. Dữ liệu và validation

| Trường của `CareSchedule` | Đề xuất | Căn cứ |
|---|---|---|
| `id` | Khóa chính mặc định Django. | **C**, theo convention model hiện hữu. |
| `herd` | FK bắt buộc tới `Herd`, `on_delete=PROTECT`, không lọc theo trạng thái đàn. | **C** áp dụng phạm vi Herd-only; dựa trên **B**: `CareLog.herd`, `VaccineSchedule.target`, role-wide scope. |
| `activity` | `CharField(max_length=200)`, không rỗng/chỉ khoảng trắng; mô tả việc dự kiến, không phải bản ghi đã làm. | **C**, dùng giới hạn của `CareLog.activity` làm tiền lệ **B**. |
| `scheduled_date` | `DateField` bắt buộc, ngày ISO trên API; cho phép quá khứ để biểu thị quá hạn. | **C**, dùng tiền lệ `VaccineSchedule.scheduled_date` và OQ-005 **B**. |
| `status` | Bốn giá trị lưu `scheduled`, `due`, `completed`, `cancelled`; mặc định `scheduled`. | **C** áp dụng taxonomy mới; tái sử dụng taxonomy vaccine **B**. |

Serializer và model validation phải từ chối Herd không tồn tại, activity trống, ngày thiếu/sai và status lạ ở create/update. Không ép ngày phải ở tương lai, không suy ngày thành trạng thái lưu và không tự hoàn tất lịch khi tạo `CareLog`. Không đặt unique trên `(herd, activity, scheduled_date)` vì đề không cấm nhiều việc cùng ngày (**C**, cần chốt). Migration chỉ tạo bảng mới; không chuyển đổi hoặc viết lại `CareLog`, vaccine hay dữ liệu hiện có.

### 3.2. Trạng thái và lịch cần nhắc

- **B:** Áp dụng đúng OQ-005 trên ngày hiện tại (classifier vaccine đang dùng `date.today()`): trước hôm nay `overdue`, bằng hôm nay `due today`, 1–7 ngày tới `due soon`, xa hơn `scheduled-not-yet-due`. `completed`/`cancelled` không có cảnh báo. Phân loại là dữ liệu **dẫn xuất khi đọc**, không lưu DB (`01_requirements_chan_nuoi_ai.md:430-453`; vaccine implementation tại `backend/apps/vaccinations/serializers.py:10-24`).
- **C:** Chỉ `scheduled` và `due` là nguồn CareSchedule đủ điều kiện cho Reminder. Giữ nguyên persisted status khi ngày đổi; `due` không phải kết quả tự động từ đồng hồ. Với request không có ngày lọc, lấy cả lịch chưa đến hạn quá 7 ngày và gắn phân loại tương ứng, giống Reminder vaccine hiện hữu. Không thêm ngưỡng thời gian ngầm hoặc giới hạn latest-N.
- **C:** Hàm phân loại care schedule nhỏ, có tham số `today` để test, dùng cùng quy tắc OQ-005. Không sửa thuật toán hoặc taxonomy vaccine trong đợt này.

### 3.3. Quyền, API và giao diện

| Hành động | Quản lý | Kỹ thuật viên | Nhân viên | No-role/chưa đăng nhập |
|---|---|---|---|---|
| CareSchedule: tạo/đọc/sửa/xóa | C/R/U/D | C/R/U | C/R | Từ chối |
| AI Reminder: đọc kết quả | Được | Được | Từ chối | Từ chối |

Hàng CareSchedule là **C**, khuyến nghị gắn `permission_resource="care"` để tái sử dụng ma trận CareLog **B** tại `backend/apps/users/permissions.py:24-61`. Hàng AI Reminder giữ nguyên **B**. Không thêm ownership/farm scope; quyền đọc hiện hữu là toàn bộ resource theo role. CSRF/session và error envelope dùng convention hiện có.

- **C:** Thêm ModelViewSet và router `GET/POST /api/care-schedules/`, `GET/PATCH/PUT/DELETE /api/care-schedules/{id}/`; payload `herd`, `activity`, `scheduled_date`, `status`; response thêm `id` và `alert_classification` chỉ đọc. Search `activity`, exact filters `herd`/`status`, ordering `scheduled_date`/`activity`. Giữ chuẩn lỗi validation/permission hiện hữu.
- **C:** Đăng ký resource UI `/care-schedules/` với tiêu đề **Lịch chăm sóc**, cột đàn, hoạt động, ngày dự kiến, trạng thái lưu, cảnh báo dẫn xuất; các trang list/detail/create/edit/delete qua resource registry và form dùng serializer. Giữ `/care/` là **nhật ký chăm sóc**; nhãn điều hướng cần phân biệt hai mục. Trang lịch hiển thị cả empty state và badge cảnh báo. Không đổi KPI hay danh sách vaccine trên dashboard trong phương án tối thiểu.
- **B:** `ui_urls.py` và generic `ResourceForm` đã tạo route/form từ registry. Chỉ điều chỉnh `dashboard/ui.py` nếu cần dispatch hàm phân loại đúng model khi hiển thị `alert_classification`; không dùng nhầm helper vaccine như một contract của care.

### 3.4. Tích hợp AI Reminder và prompt

- **B giữ nguyên:** `POST /api/ai/reminders` nhận `scope=all|herd`, `target_id`, `start_date`, `end_date`; lọc ngày inclusive; chỉ quản lý/kỹ thuật viên. Query vaccine và projection của nó giữ nguyên.
- **C:** Cùng scope/ngày áp dụng độc lập cho `CareSchedule`; không lấy `CareLog`, `FeedRecord`, `MedicineRecord` làm lịch. Gửi hai danh sách tách loại vào context: `vaccine_schedules` như hiện tại và `care_schedules` gồm tối thiểu `herd_id`, `activity`, `scheduled_date`, persisted `status`, derived `alert_classification`. Không gửi notes, auth/user, business data khác hoặc AI output cũ.
- **C:** `source_count = len(vaccine_schedules) + len(care_schedules)` sau lọc; Herd identifier không tính. Chỉ khi **cả hai** rỗng mới giữ response 200 hiện có (`text=""`, `source_count=0`, notice `No qualifying reminder data.` kèm safety notice) và không lấy/call provider. Có ít nhất một lịch thì đi qua `AIOrchestrator` một lần; không ghi kết quả hay thay business records. Input guard và lỗi provider hiện hành không đổi.
- **C cần review trước triển khai:** Tạo định nghĩa `PromptSpec` Reminder phiên bản mới (đề xuất `reminders-v4`) mô tả riêng lịch chăm sóc và vaccine, yêu cầu giữ nguyên mã/ngày/status/phân loại, không chế lịch hoặc tư vấn. Giữ nguyên byte nội dung V1/V2/V3 và evidence KT3. Chỉ sau khi sinh viên duyệt prompt mới và test offline mới chuyển `CURRENT_PROMPT`; không dùng V2 vốn chỉ mô tả VaccineSchedule để trình bày nguồn care.

### 3.5. Demo, chatbot và dữ liệu cũ

- **C khuyến nghị tối thiểu:** Không sửa `seed_demo` trong lượt triển khai đầu; migration tạo bảng rỗng và người dùng có quyền tạo lịch qua API/UI. Test dùng fixture CareSchedule, giữ nguyên exact counts của seed gốc (`tests_seed_demo.py:36-70`). Nếu cần một lịch demo tự có để trình diễn AI, đó là quyết định dataset riêng: thêm hàng relative-date, idempotent và sửa seed tests mà không thay các count đã duyệt cho resource cũ.
- **B:** Không migrate `CareLog` thành schedule, không liên kết/auto-complete từ `CareLog`; VaccineSchedule và VaccinationRecord giữ nguyên.
- **C khuyến nghị:** Không thêm CareSchedule vào chatbot ở lượt triển khai này. `chat.py:45,347,378` hiện chọn `CareLog` cho nguồn `care`; vì vậy không được mô tả chatbot là nơi trả lời lịch chăm sóc mới. Nếu sau này yêu cầu chatbot tra lịch, cần một allowlisted collector và test phạm vi riêng; không để câu trả lời từ CareLog bị trình bày như kế hoạch.

## 4. Quy tắc theo nguồn phê duyệt

| Mã | Nhóm | Quy tắc/ranh giới |
|---|---|---|
| A1 | **A** | Có lịch chăm sóc quản lý được và kiểm thử được (`Đề bài Dự Án.txt:14,30`). |
| A2 | **A** | AI nhắc dựa trên lịch chăm sóc và tiêm phòng đã lưu (`Đề bài Dự Án.txt:21`). |
| B1 | **B** | Target ban đầu theo Herd và quyền theo role trên toàn resource; không thêm tenant/ownership (`01_requirements_chan_nuoi_ai.md:150,353-365`). |
| B2 | **B** | OQ-005 phân loại ngày, bỏ completed/cancelled; persisted status độc lập ngày (`01_requirements_chan_nuoi_ai.md:430-453`). |
| B3 | **B** | Reminder scope/ngày/empty contract, AI RBAC, transient output; PromptSpec/Orchestrator và provider guard hiện hữu (`01_requirements_chan_nuoi_ai.md:375-383`; `07_kt3_ai_integration_design.md:61-69`). |
| C1 | **C** | Model `CareSchedule` Herd-only và bộ trường/validation/trạng thái mục 3.1; không tự sinh lịch từ log. |
| C2 | **C** | Áp dụng ma trận `care` cho resource lịch mới; API và UI ở mục 3.3. |
| C3 | **C** | Chọn care schedules đủ điều kiện, projection riêng và cộng `source_count` như mục 3.4. |
| C4 | **C** | Prompt Reminder V4 mới và chuyển CURRENT sau review; không sửa V1/V2/V3. |
| C5 | **C** | Chưa thêm row seed hoặc chatbot collector trong lượt đầu; giữ dashboard KPI vaccine riêng. |

## 5. File dự kiến tác động ở lượt triển khai sau

| Mục | File dự kiến | Lý do |
|---|---|---|
| Schema/validation/API | `backend/apps/care/models.py`, migration mới trong `backend/apps/care/migrations/` (sau `0001_initial.py`), `backend/apps/care/serializers.py`, `backend/apps/care/views.py`, `backend/apps/care/urls.py`, có thể `backend/apps/domain_validation.py` | Model, validation, filter, endpoint và classifier. `backend/config/urls.py` đã include `apps.care.urls`, dự kiến không sửa. |
| UI | `backend/apps/dashboard/resources.py`, `backend/apps/dashboard/ui.py`; có thể nhãn ở template điều hướng nếu registry chưa đủ | Thêm màn lịch và cảnh báo dẫn xuất. `forms.py`/`ui_urls.py` là generic, dự kiến chỉ cần kiểm tra bằng test. `dashboard/views.py` và vaccine dashboard giữ nguyên. |
| Reminder | `backend/apps/ai/reminders.py`, `backend/apps/ai/prompts/reminders.py` | Thêm nguồn care và PromptSpec phiên bản mới **sau phê duyệt**. Request serializer/view/form `Reminder` hiện có dự kiến giữ nguyên. Không sửa provider/model/retry/timeout/guard. |
| Test | `backend/apps/care/tests.py`, `backend/apps/care/tests_api.py`, `backend/apps/ai/tests.py`, `backend/apps/ai/test_prompts.py`, `backend/apps/dashboard/tests_ui.py`, `backend/apps/users/tests/test_role_permissions.py` | Model/API, RBAC, UI, nguồn AI, empty/provider và prompt version. Seed tests chỉ đổi nếu quyết định bổ sung dữ liệu demo. |

Không dự kiến sửa chatbot, ba feature AI khác, `VaccineSchedule`/`VaccinationRecord`, dữ liệu cũ, launcher, packaging hoặc tài liệu lịch sử. Danh sách trên là dự kiến, chưa phải file đã sửa.

## 6. Ma trận kiểm thử và điều kiện nghiệm thu đề xuất

| Tầng | Kiểm thử bằng dữ liệu/fake provider, không gọi mạng | Điều kiện đạt |
|---|---|---|
| Model/migration | Tạo lịch hợp lệ; thiếu/sai Herd, activity trống, ngày sai, status lạ; ngày quá khứ; migration từ DB hiện hữu. | Chỉ bảng mới, bản ghi cũ nguyên vẹn; lỗi có cấu trúc; không biến CareLog thành lịch. |
| Phân loại | Cố định `today`; kiểm quá hạn/hôm nay/+7/+8 ngày, completed/cancelled; persisted status trước/sau đọc. | OQ-005 đúng ranh giới; không tự đổi status DB. |
| API/RBAC | CRUD/list/search/filter/order và session/CSRF; thử quản lý, kỹ thuật viên, nhân viên, no-role, chưa đăng nhập; từ chối action trái quyền. | Ma trận mục 3.3 đúng; không lộ dữ liệu cho role bị từ chối. |
| UI | Sidebar và list/detail/form/delete; empty/error state; derived badge; thử POST không hợp lệ và quyền từng role. | Lịch và nhật ký tách rõ; vaccine screen không đổi; không ghi bản ghi khi form lỗi. |
| Reminder | Fixture hai Herd; vaccine-only, care-only, cả hai, cả hai rỗng; lọc Herd/ngày inclusive; completed/cancelled; lịch future >7 ngày. | Context chỉ có hai projection được phép; `source_count` cộng đúng; không nguồn thì provider không được gọi; không đưa CareLog/nguồn đàn khác. |
| Prompt/safety | Fake provider kiểm prompt version và context; response lỗi/thiếu, no-write snapshot; giữ regression V1/V2/V3 và safety notice. | Chỉ PromptSpec mới được review mới dùng nguồn care; không AI live; provider contract cũ, ba feature khác và business records không đổi. |
| Demo/chat | Seed hiện hữu chạy lặp trong test; test chat hiện hữu. | Exact counts cũ giữ nguyên; không tuyên bố chatbot đã hỗ trợ lịch chăm sóc mới. Cách hỏi “lịch chăm sóc” hiện có thể chọn nguồn CareLog, nên cần một task chat riêng nếu muốn trả lời loại lịch mới. |

Gate đề xuất cho implementation tiếp theo: các mục **C1–C5 được sinh viên chốt**, migration drift check và Django check đạt; test care, vaccination, AI, dashboard/UI, role và full backend đạt; `git diff --check` đạt; review diff chỉ đúng phạm vi. Không gọi provider thật để chứng minh acceptance.

## 7. Câu hỏi cần sinh viên quyết định

1. **Chốt C1–C2:** Có đồng ý lịch chăm sóc tối thiểu gắn `Herd`, gồm `activity`, `scheduled_date`, bốn status như vaccine, và dùng quyền nhóm `care` (nhân viên được tạo/đọc) không? **Khuyến nghị: đồng ý** để tận dụng phạm vi và ma trận đang dùng; đề gốc không chỉ định các chi tiết này.
2. **Chốt C3–C4:** Có đồng ý mở rộng Reminder bằng danh sách `care_schedules` riêng, `source_count` cộng hai nguồn, và review một PromptSpec V4 trước khi chuyển `CURRENT_PROMPT` không? **Khuyến nghị: đồng ý**; V2 hiện chỉ nói vaccine nên không đủ cho nguồn mới.
3. **Chốt C5:** Demo có cần CareSchedule được seed sẵn và chatbot có phải trả lời về lịch ngay trong cùng lượt triển khai không? **Khuyến nghị: chưa** để giữ seed contract và chatbot allowlist hiện hữu; kiểm thử bằng fixture, nhập lịch qua UI/API khi demo. Nếu cần hai khả năng đó, xác định thành phạm vi bổ sung riêng trước khi sửa.

Các câu hỏi trên không cản trở kết luận khoảng thiếu và thiết kế này. Không nhóm quyết định **C** nào được trình bày là đã được phê duyệt.

## 8. Cập nhật FINAL-02 — 2026-10-26

Sinh viên đã phê duyệt C1–C5 với các chi tiết trong yêu cầu FINAL-02: lịch theo Herd, quyền nhóm `care`, nguồn Reminder tách `vaccine_schedules` và `care_schedules`, PromptSpec `reminders-v4`, giữ nguyên seed và chưa thêm collector lịch vào chatbot. Quyết định chatbot kèm theo: câu hỏi rõ về lịch chăm sóc được hướng dẫn sang `/care-schedules/` hoặc chức năng Nhắc lịch, không dùng `CareLog` để trình bày kế hoạch.

Implementation tại workspace: `CareSchedule` và migration `care.0002_careschedule` chỉ tạo bảng mới; API `/api/care-schedules/` và UI `/care-schedules/` dùng registry/form hiện hữu; cảnh báo phân loại được tính khi đọc, persisted status giữ nguyên. Reminder chọn lịch vaccine theo query cũ và lịch chăm sóc đủ điều kiện theo cùng scope/ngày inclusive, gửi hai danh sách tách biệt, `source_count` là tổng hai danh sách; không có nguồn thì không lấy provider. `CURRENT_PROMPT` của Reminder là V4; nội dung V1/V2/V3, Summary V3 và Growth V2 giữ nguyên. Chatbot chưa truy vấn `CareSchedule`.

Kiểm chứng bằng test DB và fake provider: focused test cho care/chat/Reminder/prompt/UI/dashboard đạt 142 test; phép thử migration cùng care/chat đạt 49 test; `python manage.py test apps` đạt 448 test sau khi cập nhật assertion nhãn sidebar. `python manage.py check` và `python manage.py makemigrations --check --dry-run` đạt, `git diff --check` đạt. Các suite chồng lặp, không cộng thành tổng độc lập. Migration được thử trên test DB và giữ bản ghi `Herd`/`CareLog` cũ. Không chạy migrate/seed trên database phát triển, không gọi AI live hoặc kiểm thử F5/manual UI.

Kiểm chứng cuối sau review A/B/C/D (2026-10-26): đã bổ sung `CareSchedule.save()` gọi `full_clean()` trước khi lưu, với regression test ORM từ chối `activity` toàn khoảng trắng và `status` sai, đồng thời chấp nhận ngày quá khứ và trim `activity`. Chatbot đã sửa hai trường hợp: câu hỏi đồng thời về nhật ký và lịch chăm sóc vẫn được hướng dẫn sang `/care-schedules/`; chuỗi follow-up “lịch đó” được nhận diện nhất quán khi truy ngược các lượt user. Test xác nhận nhánh hướng dẫn không truy vấn đàn, không gọi collector hoặc provider; câu chỉ hỏi nhật ký và ưu tiên từ chối ngoài phạm vi được giữ. Trong lượt kiểm chứng cuối này, `python manage.py test apps` đạt **451 test**, `python manage.py check` đạt (0 issue), `python manage.py makemigrations --check --dry-run` đạt (`No changes detected`), và `git diff --check` đạt. Số 142/49/448 ở đoạn trước là kết quả các lượt trước, không cộng với 451. Test dùng database test và provider giả; tại thời điểm lượt kiểm chứng offline này, F5/manual UI và AI live chưa được kiểm chứng. Không chạy migrate/seed trên database phát triển.

**Bằng chứng thủ công do sinh viên cung cấp sau lượt kiểm chứng offline (2026-10-26):** sinh viên chạy F5 và cung cấp ảnh giao diện cho lịch của `DEMO-HERD-001`, hoạt động `TEST-CARE-FINAL02 — Vệ sinh chuồng`. Với ngày dự kiến 26/10/2026 và trạng thái lưu `scheduled`, giao diện hiển thị “Đến hạn hôm nay”. Sau khi sửa ngày thành 25/10/2026 nhưng giữ `scheduled`, danh sách và chi tiết hiển thị “Quá hạn”. Sau khi đổi trạng thái thành `completed` và giữ ngày 25/10/2026, cả hai màn hiển thị “Đã thực hiện” và cảnh báo “—”. Ảnh chatbot với câu “Có lịch chăm sóc nào sắp tới?” cho thấy câu trả lời hướng sang Lịch chăm sóc hoặc Nhắc lịch, đúng giới hạn chat hiện tại. Đây là bằng chứng thao tác UI do sinh viên cung cấp, không phải lượt kiểm chứng F5 độc lập của người rà soát. Ảnh không chứng minh provider không được gọi; Reminder V4 chưa được kiểm chứng AI live. Không suy từ các ảnh này rằng các quyền hoặc màn UI khác đã được thử thủ công.

## 9. Bổ sung FINAL-03 — tra cứu lịch trong chatbot (2026-10-26)

**Phạm vi triển khai:** thay nhánh chỉ hướng dẫn bằng các truy vấn đọc trực tiếp `CareSchedule` cho ý định rõ về lịch sắp tới, hôm nay, quá hạn, lịch của đàn được nêu rõ, trạng thái hoàn thành/hủy, liệt kê và đếm. Các bộ lọc ngày, trạng thái và đàn được tạo bằng Django ORM cố định; không dùng lời model để chọn truy vấn. Kết quả không gọi provider hoặc collector chatbot, không ghi `CareLog` hay thay đổi trạng thái lịch. Câu hỗn hợp nhật ký và lịch tiếp tục được hướng dẫn tách riêng; câu hỏi không rõ điều kiện vẫn yêu cầu làm rõ.

**Quy ước mới riêng cho chat:** “Sắp tới là từ ngày mai đến hết ngày hôm nay +7 ngày, bao gồm hai đầu mốc”, theo `date.today()` như classifier lịch hiện có. Câu trả lời nêu hai ngày cụ thể. Hôm nay là đúng ngày hiện tại; quá hạn là ngày trước hôm nay. Những truy vấn theo thời gian chỉ gồm trạng thái `scheduled`/`due`; `completed`/`cancelled` được trả về khi người dùng nêu trạng thái hoặc yêu cầu liệt kê toàn bộ lịch. Trạng thái lưu không được thay đổi do truy vấn.

**Bổ sung sau review FINAL-03:** chỉ hỗ trợ bộ lọc ngày `hôm nay`, `sắp tới` và `quá hạn`; mốc như `ngày mai`, `tháng sau`, ngày cụ thể hoặc khoảng thời gian chưa hỗ trợ được yêu cầu làm rõ trước khi truy vấn. Quy ước này áp dụng cả câu nối tiếp. `toàn bộ/tất cả` là phạm vi trạng thái, tách khỏi thao tác đếm/liệt kê: “Đếm toàn bộ lịch chăm sóc” đếm mọi trạng thái khi không có bộ lọc thời gian/trạng thái; “Có bao nhiêu lịch chăm sóc?” đếm `scheduled`/`due` và nêu rõ nhóm này. Với bộ lọc thời gian, mặc định chỉ lấy `scheduled`/`due`, trừ khi người dùng chỉ rõ trạng thái.

`source_count` là tổng số bản ghi khớp với toàn bộ điều kiện lọc, tính trước giới hạn hiển thị. Nhãn trên kết quả rỗng, đếm và danh sách nêu ngày/khoảng ngày, trạng thái hoặc nhóm trạng thái thực tế, và đàn được lọc (nếu có). Không gọi kết quả đã loại trạng thái hoàn thành/hủy là “toàn bộ”. Nếu danh sách vượt quá 10 lịch, câu trả lời ghi số dòng đang hiển thị trên tổng số kết quả; phép đếm không bị giới hạn ở 10.

**Kiểm chứng trong lượt FINAL-03:** regression tests dùng test database, ngày cố định và không gọi mạng/provider thật. Bao phủ biên ngày hôm nay, ngày mai, hôm nay +7 ngày và ngày thứ tám; trạng thái terminal, lọc đàn, count/list, kết quả rỗng, follow-up đổi điều kiện, herd không tồn tại/mơ hồ và từ chối ngoài phạm vi. `source_count` trong các kết quả trực tiếp phản ánh tổng truy vấn đã lọc. Kết quả lệnh được ghi trong báo cáo lượt thực hiện này; đây không phải bằng chứng chạy F5/manual UI hay kiểm thử AI live.

**Kiểm chứng cuối FINAL-03 (2026-10-26):** bằng Python trong `.venv`, `python manage.py test apps` đạt **459 test**; đây là số của suite đã chạy, không cộng với suite chat chồng lặp. `python manage.py check` đạt (0 issue), `python manage.py makemigrations --check --dry-run` đạt (`No changes detected`), và `git diff --check` đạt. Đây là kiểm thử offline; không có AI live test.

**Manual evidence do sinh viên cung cấp (2026-10-26):** sinh viên chạy F5 và xác nhận năm tình huống trên UI: hỏi lịch `completed`; follow-up “Liệt kê lịch đó” giữ trạng thái completed; “Liệt kê toàn bộ lịch đó” mở rộng sang mọi trạng thái; “sắp tới” trả khoảng 27/10–02/11; câu hỏi ngày mai được hướng dẫn làm rõ. Sinh viên báo tiếng Việt trên UI hiển thị bình thường. Đây là bằng chứng thao tác do sinh viên cung cấp, không phải kiểm thử UI độc lập của người rà soát. Ảnh không tự chứng minh provider không được gọi; không có AI live test.

## 10. Cập nhật tài liệu và trạng thái demo (2026-10-26)

Source hiện tại giữ `CareSchedule` tách khỏi `CareLog`. Prompt đang được chọn là Reminder `reminders-v4`, Herd Summary `herd-summary-v3` và Growth Report `growth-report-v2`. Lịch sử đánh giá V1/V2/V3 chỉ là bằng chứng cho ba chức năng AI gốc; Reminder V4 chưa được kiểm chứng live.

Chatbot có nhánh truy vấn `CareSchedule` bằng Django ORM cố định. Phạm vi lịch hỗ trợ ngày hôm nay, khoảng “sắp tới” từ ngày mai đến hết ngày hôm nay +7 ngày (bao gồm hai đầu mốc), quá hạn, trạng thái rõ, đếm/liệt kê và follow-up đủ rõ. Mốc thời gian không hỗ trợ yêu cầu làm rõ; danh sách hiển thị tối đa 10 dòng sau khi đếm toàn bộ kết quả. Không bảo đảm chatbot hiểu mọi cách diễn đạt.

Kết quả gần nhất được ghi nhận: `python manage.py test apps` đạt **459 test** trong lượt FINAL-03; `tools.test_sqlite_backup` đạt **5 unittest** trong lượt FINAL-04 và là suite riêng. Không cộng các suite chồng lặp. Không có AI live test mới. Manual evidence do sinh viên cung cấp gồm (a) thao tác UI lịch chăm sóc FINAL-02 được ghi ở mục 8 và (b) các tình huống chatbot FINAL-03 được ghi ở mục 9; không suy rộng sang CRUD hoặc các quyền khác. Portable chưa được build lại/xác minh với thay đổi FINAL-02/FINAL-03; F5 hiện chạy Django source. Backup/restore được hướng dẫn tại `SQLITE_BACKUP_RESTORE.md`; lần kiểm chứng helper là trên bản sao trong thư mục tạm, không phải khôi phục database thật.
