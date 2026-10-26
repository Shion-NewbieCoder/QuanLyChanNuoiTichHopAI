# Hệ thống quản lý chăn nuôi có tích hợp AI

Đây là dự án học thuật chạy cục bộ để quản lý dữ liệu chăn nuôi, thống kê từ dữ liệu nguồn và trình bày các báo cáo AI có kiểm soát. Django Dashboard là giao diện chức năng chính; thư mục React/Vite hiện là scaffold và ranh giới tích hợp frontend, không phải một giao diện CRUD nghiệp vụ hoàn chỉnh.

## Cách chạy dành cho giảng viên

Giải nén đầy đủ bộ nộp bài, giữ nguyên thư mục `DEMO_PORTABLE` và `_internal`
bên trong. Bản portable dành cho Windows x64; Python đã được đóng gói sẵn.
Không cần cài Python, pip, venv, Node/npm, Docker hay quyền quản trị.

**Cách A — mở trực tiếp:** vào `DEMO_PORTABLE`, double-click **DEMO.exe**.
Không cần VS Code và không cần nhập lệnh terminal.

**Cách B — VS Code chạy mã nguồn:** mở thư mục gốc project rồi nhấn **F5**.
Cấu hình **Run Livestock Management (Django source)** chạy `tools/run_demo.py`
trên mã Django trong `backend/`, không chạy EXE. Bootstrap tự tạo `.venv` lần đầu,
cài requirements khi danh sách hoặc môi trường dependencies thay đổi, chạy migration
và seed dữ liệu demo, rồi mở trang đăng nhập tại `http://127.0.0.1:8000/login/`.
Không cần OpenRouter API key để khởi động hoặc dùng các chức năng ngoài AI; không có
AI live nào được gọi khi khởi động. Các chức năng AI vẫn đọc credential từ environment
khi được sử dụng và hiển thị thông báo an toàn nếu chưa cấu hình.

Giữ phiên F5 đang chạy trong lúc dùng ứng dụng; nhấn **Ctrl+C** trong terminal để dừng.
Nếu cổng 8000 đang bận, bootstrap báo `PORT_UNAVAILABLE` và hướng dẫn đóng server cũ;
nó không tự dừng process khác. Nếu trình duyệt không tự mở, truy cập URL đăng nhập ở trên.
`RUN_DEMO.bat` cũng tiếp tục chạy bootstrap source theo cách tương tự.
Không commit secret. AI live cần Internet và có thể lỗi do provider hoặc quota.
Đăng nhập Manager hoặc Technician rồi mở `/ai/` để dùng ba tính năng hiện có.

Giao diện quản lý và Bootstrap dùng tài nguyên cục bộ, không cần Internet.
AI chưa cấu hình sẽ hiển thị thông báo an toàn; không có kết quả AI giả.
Dữ liệu portable được giữ tại `DEMO_PORTABLE/data/db.sqlite3`; sao lưu tệp này để giữ dữ liệu portable.

Tài khoản demo:

```text
Username: demo_manager
Password: DemoOnly-2026!
Username: demo_technician
Password: DemoOnly-2026!
Username: demo_employee
Password: DemoOnly-2026!
```

Tài khoản trên chỉ phục vụ chấm bài/thực hành, không dùng cho production.

## Dành cho phát triển mã nguồn

Cần Python 3.12+ để sửa/chạy mã nguồn hoặc build EXE. `RUN_DEMO.bat` vẫn là
tiện ích chạy **mã nguồn** cho lập trình viên: tạo `.venv`, cài requirements,
migrate và seed. Lần cài dependencies đầu cần mạng hoặc pip cache đầy đủ.
F5 chạy trực tiếp mã nguồn Django; không cần build lại EXE sau khi sửa mã.

Để build trên Windows x64, chạy **BUILD_DEMO.bat** ở gốc dự án. Công cụ dùng
`.venv` phát triển, cài PyInstaller theo `packaging/requirements-build.txt`,
đọc `packaging/DEMO.spec`, tạo `DEMO_PORTABLE/DEMO.exe` cùng runtime bên cạnh.
Đóng EXE trước khi build lại. Build giữ nguyên thư mục `DEMO_PORTABLE/data`;
khi chuẩn bị bản nộp mới, chỉ đưa dữ liệu demo sạch theo chủ ý của bạn.
Giảng viên **không chạy BUILD_DEMO.bat**.

Runtime sinh ra được Git bỏ qua. Nếu chỉ clone Git, lập trình viên phải build
trước; khi nộp bài, đính kèm **toàn bộ DEMO_PORTABLE**, không chỉ tệp EXE.
Mã nguồn dự án vẫn giữ nguyên để xem xét.

Kiểm thử portable dành cho lập trình viên:
`.\.venv\Scripts\python.exe packaging\verify_portable.py`.
Harness sao chép riêng runtime ra TEMP có dấu/khoảng trắng, giới hạn PATH
cho EXE, kiểm tra HTTP/SQLite/process và lưu bằng chứng vào `build/`.
Chi tiết kết quả và giới hạn kiểm chứng: [PORTABLE_DEMO_REPORT.md](PORTABLE_DEMO_REPORT.md).

## Chức năng đã triển khai

- Đăng nhập bằng Django session và phân quyền theo vai trò.
- API quản lý đàn, cá thể, nhóm vật nuôi và chuồng.
- API nhật ký chăm sóc, thức ăn và thuốc.
- API lịch vaccine, bản ghi tiêm, tăng trưởng, sinh sản và xuất bán.
- Thống kê tăng trưởng, chi phí, tỷ lệ hao hụt và doanh thu suy ra từ dữ liệu nguồn.
- AI nhắc lịch vaccine và chăm sóc, tóm tắt đàn và báo cáo tăng trưởng.
- Chatbot hỏi đáp dữ liệu chăn nuôi, là phần mở rộng theo yêu cầu bổ sung của giảng viên.
- Django Dashboard tại `/dashboard/`.
- Giao diện Django đầy đủ cho danh sách, chi tiết, thêm, sửa và xác nhận xóa
  các dữ liệu nghiệp vụ; tìm kiếm/lọc/sắp xếp và nút thao tác theo vai trò.
- Lệnh `seed_demo` tạo dữ liệu demo xác định, an toàn khi chạy lặp.
- React/Vite scaffold có helper gọi API cùng origin.

## Sử dụng giao diện quản lý

Sau khi chạy Django source bằng F5, đăng nhập bằng tài khoản demo. Sidebar dẫn đến các trang HTML sau,
không cần chạy React/Vite:

| Mục | Đường dẫn |
|---|---|
| Tổng quan | `/dashboard/` |
| Đàn / Cá thể / Nhóm | `/herds/`, `/animals/`, `/animal-groups/` |
| Chuồng trại | `/pens/` |
| Nhật ký chăm sóc / Lịch chăm sóc | `/care/`, `/care-schedules/` |
| Thức ăn / Thuốc | `/feed/`, `/medicine/` |
| Lịch vaccine / Lần tiêm | `/vaccines/`, `/vaccination-records/` |
| Tăng trưởng / Sinh sản / Xuất bán | `/growth/`, `/reproduction/`, `/sales/` |
| Thống kê / AI | `/statistics/`, `/ai/` |

Các mục nghiệp vụ có nút **Thêm bản ghi**, **Xem**, **Sửa**, **Xóa** theo quyền.
Xóa cần xác nhận bằng POST; dữ liệu đang được tham chiếu không bị xóa.
Form chuồng yêu cầu đúng một đối tượng đàn/nhóm/cá thể. Form giữ giá trị và
hiển thị lỗi khi dữ liệu không hợp lệ. Trạng thái vaccine và lịch chăm sóc có danh mục cố định;
các trường văn bản tự do khác giữ nguyên hợp đồng hiện có.

Trang danh sách gửi `search`, exact filters và `ordering` đến bộ lọc backend
đã có; phân trang 20 dòng. Thống kê tổng hợp toàn bộ dữ liệu đã ghi nhận qua
services hiện có. AI trả kết quả trong trang HTML, không lưu kết quả vào CSDL;
khi chưa cấu hình provider hoặc provider gặp lỗi, trang hiển thị thông báo an toàn.
Trang AI Assistant có chatbot hỏi đáp dữ liệu chăn nuôi.

CSS có bố cục desktop/tablet/mobile, bảng cuộn ngang và danh mục thu gọn trên
màn hình nhỏ. Bootstrap 5.3.3 được lưu tại `backend/static/vendor/bootstrap/`
kèm giấy phép MIT, dùng được offline. Kiểm thử UI: `python manage.py test apps.dashboard.tests_ui`.
Chi tiết triển khai và xác minh: [UI_COMPLETION_REPORT.md](UI_COMPLETION_REPORT.md).

## Công nghệ sử dụng

- Backend: Python 3.12+, Django 6.1.1, Django REST Framework 3.18.1.
- Cơ sở dữ liệu: SQLite.
- Dashboard: Django Templates, Bootstrap 5.
- Frontend scaffold: React, Vite.
- AI: `PromptSpec` → `AIOrchestrator` → provider adapter; OpenRouter là primary live provider KT3, OpenAI là adapter tùy chọn; cấu hình qua biến môi trường.

## Cấu trúc chính

```text
QuanLyChanNuoiGiaSucAI/
├── RUN_DEMO.bat
├── tools/run_demo.py
├── .vscode/launch.json, tasks.json
├── 01_requirements_chan_nuoi_ai.md
├── 02_design_chan_nuoi_ai.md
├── 03_implementation_plan_chan_nuoi_ai_reviewed.md
├── 04_implementation_chan_nuoi_ai_final.md
├── 05_review_testing_chan_nuoi_ai_final.md
├── 06_final_delivery_chan_nuoi_ai_final.md
├── FINAL_REPORT.md
├── backend/
│   ├── manage.py
│   ├── requirements.txt
│   ├── .env.example
│   ├── config/
│   ├── apps/
│   │   ├── users, herds, pens, care
│   │   ├── vaccinations, growth, reproduction, sales
│   │   └── statistics, ai, dashboard
│   ├── templates/
│   └── static/
└── frontend/
    ├── package.json
    ├── package-lock.json
    ├── vite.config.js
    └── src/
```

Các thư mục `.venv/`, `__pycache__/`, `frontend/node_modules/`, `frontend/dist/`, file `.env` và database SQLite cục bộ được loại khỏi gói mã nguồn bằng `.gitignore`.

## Điều kiện cần

- Giảng viên: Windows x64 và bộ `DEMO_PORTABLE` đầy đủ; trình duyệt mặc định.
- Phát triển mã nguồn/build: Python 3.12+; bootstrap tạo virtual environment
  và cài dependencies khi cần.
- Optional frontend development: Node.js và npm chỉ khi cần chạy/build React/Vite
  scaffold.
- Optional live AI: source đã có OpenRouter/OpenAI adapters; cần cấu hình environment
  hợp lệ và kết nối mạng; không bắt buộc cho dashboard/core demo.
- PowerShell chỉ cần cho các ví dụ development thủ công bên dưới.

Portable và source bootstrap tạo random `DJANGO_SECRET_KEY` chỉ trong process environment,
không in hoặc ghi secret ra file. Django management/dashboard chạy khi
chưa cấu hình AI; live generation dùng adapter hiện có và credential từ environment.
Việc source hỗ trợ live AI không khẳng định gói portable đã được cập nhật hoặc chứa API key.
Source bootstrap khi thất bại hiển thị
`PYTHON_MISSING`, `VENV_CREATE_FAILED`, `PIP_INSTALL_FAILED`, `MIGRATION_FAILED`,
`SEED_FAILED`, `SERVER_START_FAILED` hoặc `PORT_UNAVAILABLE` cùng next action;
bootstrap không dừng process khác đang chiếm port 8000.

## Cài đặt backend

Từ thư mục gốc dự án:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### Biến môi trường

| Biến | Bắt buộc | Mặc định | Mục đích |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | Có, để khởi động Django | Không có | Secret của Django; phải tự đặt ngoài source. |
| `DJANGO_DEBUG` | Không | `false` | Đặt `1` cho môi trường local/demo. |
| `DJANGO_ALLOWED_HOSTS` | Không | `127.0.0.1,localhost` | Danh sách host cách nhau bằng dấu phẩy. |
| `DJANGO_DEMO_DB_PATH` | Không | `backend/db.sqlite3` | Portable tự đặt đường dẫn `data/db.sqlite3` cạnh EXE. |
| `DJANGO_PORTABLE_DEMO` | Không | `false` | Portable tự bật thẻ thông tin tài khoản demo trên trang đăng nhập. |
| `AI_PROVIDER` | Không để khởi động; cần cho live AI | Rỗng | Chọn `openrouter` cho primary KT3; `openai` là adapter tùy chọn. |
| `OPENROUTER_API_KEY` | Cần khi gọi OpenRouter | Không có | Credential ngoài source, cung cấp qua environment; không commit. |
| `OPENROUTER_MODEL` | Không | `nvidia/nemotron-3-ultra-550b-a55b:free` | Model cố định đã được kiểm thử live trong KT3. |

Ví dụ cấu hình local trong phiên PowerShell hiện tại:

```powershell
$env:DJANGO_SECRET_KEY = "<your-local-secret>"
$env:DJANGO_DEBUG = "1"
$env:DJANGO_ALLOWED_HOSTS = "127.0.0.1,localhost"
```

`backend/.env.example` là mẫu tên biến. Source hiện tại dùng `os.getenv` và **không tự động nạp file `.env`**; cần export biến trong shell hoặc dùng công cụ quản lý environment của máy chạy. Không đưa secret thật vào README, source hoặc Git.

## Database, dữ liệu demo và chạy Django

Sau khi đã đặt `DJANGO_SECRET_KEY` và đang ở `backend/`:

```powershell
python manage.py migrate
python manage.py seed_demo
python manage.py runserver 127.0.0.1:8000
```

`seed_demo` chỉ chạy khi `DJANGO_DEBUG=1`; lệnh từ chối khi `DEBUG=False`, không flush dữ liệu ngoài demo và an toàn khi chạy lặp.

Các URL chính:

- Đăng nhập: `http://127.0.0.1:8000/login/`
- Dashboard: `http://127.0.0.1:8000/dashboard/`
- API nghiệp vụ: `http://127.0.0.1:8000/api/`

### Truy vấn danh sách API

Các list endpoint nghiệp vụ hỗ trợ `?search=<text>`, exact filters theo
từng resource và `?ordering=<field>`/`?ordering=-<field>`. Các field được
phép:

| Resource | Search | Exact filters | Ordering |
|---|---|---|---|
| Herd | `code`, `name`, `animal_type`, `status` | `status`, `animal_type`, `management_mode` | `code`, `name`, `quantity` |
| Animal | `code`, `status` | `herd`, `status` | `code` |
| AnimalGroup | `code`, `name`, `status` | `herd`, `status` | `code`, `name`, `quantity` |
| Pen | `code`, `name`, `location`, `description`, `status` | `herd`, `animal_group`, `animal`, `status` | `code`, `name` |
| CareLog | `activity`, `notes` | `herd` | `recorded_at` |
| FeedRecord | `feed_type`, `notes` | `herd` | `recorded_at`, `quantity` |
| MedicineRecord | `medicine`, `notes` | `herd` | `recorded_at`, `dose` |
| VaccineSchedule | `vaccine` | `target`, `status` | `scheduled_date`, `vaccine` |
| VaccinationRecord | `notes` | `schedule` | `actual_date` |
| GrowthRecord | `notes` | `target` | `measurement_date`, `weight` |
| ReproductionRecord | `event_type`, `result`, `notes` | `target` | `event_date` |
| SaleRecord | `notes` | `target` | `sale_date`, `amount` |

Các tham số có thể kết hợp trên cùng request. Query chỉ giới hạn
kết quả mà role hiện tại được phép đọc; nó không thay đổi RBAC.

## Tài khoản demo

Các tài khoản được tạo bởi `python manage.py seed_demo` chỉ dành cho demo học thuật cục bộ:

| Username | Vai trò | Password |
|---|---|---|
| `demo_manager` | quản lý | `DemoOnly-2026!` |
| `demo_technician` | kỹ thuật viên | `DemoOnly-2026!` |
| `demo_employee` | nhân viên | `DemoOnly-2026!` |

Đây là credential demo công khai theo `PD-SEED-001`, không phải credential production và không được dùng để suy ra tài khoản production.

## Phân quyền

Phân quyền được kiểm tra ở backend; việc ẩn nút trên giao diện không thay thế authorization.

- Quản lý: CRUD rộng trên tài nguyên nghiệp vụ hiện có.
- Kỹ thuật viên: đọc dữ liệu master; có quyền tác nghiệp create/read/update ở care, vaccine, growth và reproduction; không được xóa.
- Nhân viên: đọc dữ liệu master, vaccine, growth, reproduction và sales; có thể create/read care; không được update/delete care.
- Statistics và AI: chỉ quản lý và kỹ thuật viên.
- Delete trên tài nguyên nghiệp vụ hiện có: chỉ quản lý.
- User không có vai trò được công nhận: bị từ chối trên business API, Statistics và AI.
- Nếu có nhiều vai trò, precedence là `quản lý > kỹ thuật viên > nhân viên`.

## Chức năng AI

Ba chức năng AI trong đề gốc là **AI Reminder** (nhắc lịch chăm sóc và tiêm phòng), **AI Herd Summary**
(tóm tắt đàn) và **AI Growth Report** (báo cáo tăng trưởng). Chatbot hỏi đáp dữ liệu chăn nuôi
là phần mở rộng theo yêu cầu bổ sung của giảng viên, tách biệt với ba chức năng đó.

Chatbot chỉ hỗ trợ câu hỏi về dữ liệu đã ghi nhận trong hệ thống. Backend chọn các nguồn
được phép và giới hạn số bản ghi trước khi chuyển dữ liệu cần thiết vào luồng trả lời. Backend
dùng bộ nhận diện phạm vi dựa trên từ khóa hiện tại; các câu được nhận diện rõ là ngoài phạm vi
sẽ bị từ chối trước khi truy vấn nguồn hoặc gọi provider. Bộ nhận diện không bảo đảm phân loại
đúng mọi cách diễn đạt. Một số thống kê đàn như
đếm, nhiều nhất và ít nhất được tính trực tiếp từ database. Nếu dữ liệu không đủ, chatbot phải
nêu rõ; câu trả lời chỉ mang tính tham khảo, không chẩn đoán, kê thuốc, dự báo hay tư vấn chuyên môn.
Chat không ghi tin nhắn/câu trả lời vào database và không thay đổi business data; hội thoại chỉ
tồn tại tạm thời trên trang hiện tại.

Lịch chăm sóc được nhập tại `/care-schedules/` theo đàn, hoạt động, ngày dự kiến và trạng thái;
cảnh báo theo ngày chỉ được tính khi xem. Mục `/care/` lưu nhật ký đã thực hiện. Chatbot hiện
chưa tra cứu lịch chăm sóc; với câu hỏi rõ về lịch, chatbot hướng dẫn mở màn lịch hoặc dùng
**Nhắc lịch**. Reminder dùng cả lịch vaccine và lịch chăm sóc đã lưu; không tự tạo lịch từ nhật ký.

Các endpoint hiện có:

```text
POST /api/ai/reminders
POST /api/ai/herd-summary
POST /api/ai/growth-report
POST /api/ai/chat
```

AI chỉ nhận factual data đã được giảm thiểu theo contract và quyền người dùng. Output chỉ dùng để trình bày, không thay đổi business record, không ghi lịch sử AI vào database và luôn qua validation/safety boundary. `source_count`, các metric tăng trưởng và phân loại lịch vaccine/chăm sóc do application kiểm soát, không do AI quyết định.

Project có thể khởi động, chạy dashboard, seed và tests khi chưa cấu hình provider. Regression tests dùng fake/injected provider và không gọi mạng. `seed_demo` không gọi AI.

Source đã triển khai live provider support: **OpenRouter** là primary provider KT3, với model cố định đã thử nghiệm **`nvidia/nemotron-3-ultra-550b-a55b:free`**. **OpenAI** vẫn là adapter tùy chọn. Các feature dùng `PromptSpec` tách chỉ dẫn, dữ liệu nguồn có cấu trúc và output constraints; gọi provider qua `AIOrchestrator`, không gọi trực tiếp từ UI.

Cấu hình primary provider qua environment: `AI_PROVIDER`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`; Django cần `DJANGO_SECRET_KEY`. Secrets phải nằm ngoài source/Git, không commit và không nhúng vào `DEMO.exe`. Không coi việc adapter tồn tại là bảo đảm portable đã được cấu hình live AI.

AI chỉ cung cấp thông tin tham khảo, không thay thế bác sĩ thú y/kỹ sư chăn nuôi. Kết quả là transient, không ghi đè dữ liệu nghiệp vụ. Live inference không được bảo đảm luôn thành công: cấu hình, giới hạn provider, timeout hoặc response không hợp lệ được xử lý bằng lỗi an toàn.

Minh chứng thử nghiệm **V1 → V2 → V3**, gồm kết quả và giới hạn thực tế, nằm tại [KT3_AI_PROMPT_EXPERIMENTS.md](KT3_AI_PROMPT_EXPERIMENTS.md). Đánh giá prompt KT3 này chỉ áp dụng cho ba chức năng gốc trước khi mở rộng lịch chăm sóc; không phải kết quả đánh giá chatbot hay Reminder V4. Phiên bản hiện tại trong source: **Reminder V4, Herd Summary V3, Growth Report V2**. Reminder V4 chỉ được kiểm thử offline bằng provider giả trong lượt mở rộng này; chưa có kiểm thử AI live mới.

## React/Vite scaffold

Giao diện nghiệp vụ chính vẫn là Django Dashboard. Để chạy scaffold frontend riêng:

```powershell
cd frontend
npm install
npm run dev
```

Build production:

```powershell
npm run build
```

Project chưa cấu hình script lint; không có lệnh `npm run lint`. API helper hiện dùng đường dẫn cùng origin, session cookie và CSRF token cho unsafe request.

## Minh chứng sử dụng AI khi lập trình

Các prompt/response tiêu biểu, mapping phần code được hỗ trợ, human review,
correction và test evidence được ghi trung thực tại
[AI_CODING_EVIDENCE.md](AI_CODING_EVIDENCE.md). Tài liệu đó là representative
evidence, không phải transcript đầy đủ và không suy diễn model name,
timestamp hay code ownership.

## Kiểm thử và xác minh

Backend, từ `backend/` với `DJANGO_SECRET_KEY` đã đặt:

```powershell
python manage.py test apps --verbosity 1
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py showmigrations
```

Frontend, từ `frontend/`:

```powershell
npm run build
```

Evidence của lần kiểm tra ngày 2026-09-08 (mốc lịch sử):

- Backend sau UI pass: `288/288` tests PASS (266 regression cũ + 22 UI).
- Focused UI: `22/22` tests PASS; 15 trang chính đã kiểm tra qua HTTP có đăng nhập.
- Django system check: PASS.
- Migration drift: NONE; toàn bộ migrations đã áp dụng.
- `seed_demo`: PASS và idempotent.
- Security regression: `57/57` focused tests PASS.
- Vite production build: PASS.
- Frontend lint: NOT CONFIGURED.

### Cập nhật workspace ngày 2026-10-17

Sau mốc trên, chatbot hỏi đáp dữ liệu chăn nuôi được bổ sung theo yêu cầu của giảng viên.
Ở workspace hiện tại, `apps.ai.test_chat` đạt 41/41 và `apps` đạt 438/438; Django check,
migration drift check và `git diff --check` đều đạt. Smoke test F5 qua Django source đã kiểm tra
câu hỏi đếm đàn, đàn nhiều nhất và đàn ít nhất. Đây là kiểm tra source hiện tại, không phải kiểm tra
bản portable. Không có AI live test mới; đánh giá prompt KT3 vẫn chỉ áp dụng cho ba chức năng gốc.

## Ghi chú bảo mật và giới hạn

- Bản bàn giao hướng tới local academic demo với SQLite; chưa triển khai public production.
- `DJANGO_SECRET_KEY` bắt buộc và phải được đặt qua environment.
- Không có JWT/localStorage token flow; hệ thống dùng Django session.
- CSRF, template autoescaping, server-side RBAC, centralized safe errors và AI output validation đang được áp dụng.
- React/Vite chỉ là scaffold, không phải business UI hoàn chỉnh.
- Live AI dùng adapters đã có nhưng vẫn cần credential/configuration ngoài source và provider khả dụng; không bảo đảm mọi inference thành công.
- AI chỉ là thông tin tham khảo, không chẩn đoán bệnh hoặc thay thế bác sĩ thú y/kỹ sư chăn nuôi.

```text
DEPLOYMENT_STATUS: NOT_DEPLOYED
```

## Trạng thái quản lý mã nguồn trước khi nộp

Repository Git cục bộ được khởi tạo tại đúng root dự án trong bước chuẩn bị Final Delivery ngày 2026-09-08. Snapshot hiện tại được chia thành các commit mới, có nội dung rõ ràng cho backend, frontend và tài liệu; các commit này không được trình bày như lịch sử phát triển trước đó. Chưa cấu hình hoặc xác minh Git remote/GitHub và đề bài không bắt buộc remote để chạy demo cục bộ.
