# Báo cáo Windows portable demo

Ngày xác minh: 2026-09-09. Phạm vi: đóng gói và khởi động demo cục bộ.

## Kết quả bàn giao

Đã build `DEMO_PORTABLE/DEMO.exe` bằng PyInstaller 6.22.2, chế độ **onedir**,
Windows x64, kèm Python 3.14.6, Django 6.1.1 và DRF 3.18.1.
Chạy trực tiếp không cần Python/pip/venv/Node/VS Code hay tải thêm thành phần.
F5 và task VS Code cùng trỏ đến EXE này. Runtime không chạy `RUN_DEMO.bat`.

| Thành phần | Kích thước |
|---|---:|
| `DEMO.exe` | 7,195,361 byte (6.86 MiB) |
| Toàn bộ portable, trước lần chạy đầu | 48,257,426 byte (46.02 MiB), 3,616 tệp |

SHA-256 EXE: `ae093d7eb45acf839484da257397d5474202a77552414acbdb3a673e6d30ae4a`.
Thư mục phát hành `data/` hiện trống; không đưa database phát triển vào bộ này.
Toàn bộ runtime, build cache và log được Git bỏ qua. Khi nộp bài cần đính kèm
cả `DEMO_PORTABLE`, không chỉ EXE. Không tạo ZIP hoặc thay thế mã nguồn.

## Audit mã nguồn và giới hạn thay đổi

Đã đọc settings, URLs, environment, requirements, templates/static, migration,
`seed_demo`, launcher source, batch, cấu hình VS Code, README và Git.
Source ban đầu dùng `backend/db.sqlite3`, yêu cầu `DJANGO_SECRET_KEY`, hỗ trợ
`DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`; AI provider/key không bắt buộc cho core.
F5 cũ chạy `RUN_DEMO.bat`/Python. Bootstrap 5.3.3 trước đây phụ thuộc CDN.
Widget avatar có template riêng trong app dashboard, nên được đưa vào spec.

Packaging chỉ thêm hai cấu hình runtime: đường dẫn SQLite tùy chọn và cờ hiển
thị tài khoản demo. Login vẫn dùng Django LoginView/session/CSRF; không tự đăng nhập.
Templates chỉ đổi Bootstrap sang static cục bộ và thêm thẻ thông tin demo.
Không sửa model, serializer, CRUD, RBAC, thống kê, AI hay `seed_demo`.
Không tạo/sửa migration trong commit đóng gói.

Migration avatar `herds/0002_add_avatar_preferences` đã hoàn tất ở commit trước
`9f275c0` cho yêu cầu chọn hình đại diện; đây là một phần baseline được đóng gói,
không phải migration phát sinh từ công việc portable.

## Runtime và build

`tools/portable_demo.py` dùng `sys.frozen`/`sys._MEIPASS` cho tài nguyên;
SQLite nằm tại `data/db.sqlite3` bên cạnh EXE. Source vẫn mặc định dùng DB cũ.
Launcher tạo `secrets.token_urlsafe(48)` trong môi trường tiến trình; không in,
ghi `.env` hay nhúng secret cố định. Cấu hình local DEBUG, localhost và bỏ AI key/provider.
EXE chạy `call_command('migrate')`, `call_command('seed_demo')`, rồi runserver
`127.0.0.1:8000`, không autoreload, trong cùng tiến trình.

HTTP GET `/login/` phải trả 2xx/3xx trước `[DEMO_READY]` và trước khi gọi trình
duyệt mặc định. Deadline readiness là 30 giây, không chỉ kiểm tra cổng TCP.
Port bận báo `PORT_UNAVAILABLE`; launcher không giết tiến trình nào.
Lỗi thư mục không có quyền ghi có hướng dẫn `DATA_NOT_WRITABLE`.

`BUILD_DEMO.bat`/`tools/build_demo.py` chỉ dùng trên máy phát triển. Build dọn
thư mục đầu ra đã xác định ranh giới, chạy spec, thay `_internal`/EXE và giữ
`DEMO_PORTABLE/data`. Không đổi PATH hệ thống hoặc PowerShell execution policy.
Spec gom module project/Django/DRF, migration và management commands động;
hook Django riêng tránh hành vi copy database phát triển của hook mặc định.
Template gốc/app-local, static, timezone và giấy phép dependency đều có trong bộ.

Bootstrap được vendor từ bản 5.3.3, có MIT license, bỏ sourcemap comment.
Runtime có các giấy phép Python, Django, DRF, asgiref, sqlparse, tzdata và
PyInstaller tại `_internal/licenses`; giấy phép Bootstrap nằm cạnh static.

Tài liệu tham khảo build: [PyInstaller spec files](https://pyinstaller.org/en/stable/spec-files.html),
[PyInstaller usage](https://pyinstaller.org/en/latest/usage.html).

## Xác minh runtime độc lập

Harness phát triển: `packaging/verify_portable.py`. Chỉ copy `DEMO_PORTABLE`
ra `%TEMP%/Nhóm 08 Demo <mã riêng>/DEMO_PORTABLE`, ngoài repository, có dấu và
khoảng trắng. EXE được chạy với `PATH=C:\Windows\System32`; bỏ PYTHONHOME,
PYTHONPATH, VIRTUAL_ENV và AI credentials. Python chạy harness bên ngoài
tiến trình EXE chỉ làm kiểm thử, không thuộc dependency runtime.

| Kiểm tra | Kết quả |
|---|---|
| Lần chạy đầu từ DB chưa tồn tại | PASS: tạo DB, áp dụng đủ 28 migration, seed thành công |
| Seed accounts | Chính xác demo_manager/demo_technician/demo_employee, mật khẩu DemoOnly-2026! |
| Python runtime | CIM process tree chỉ có EXE/conhost; module Python DLL ở `_internal`, không có py/python/pip/Node con |
| Browser | `[BROWSER_OPENED]`, sau HTTP readiness; có GET tới đúng URL login có `next` |
| Templates | Login, dashboard; list/create/detail/edit/delete của 12 loại bản ghi; statistics; AI; 403/404 |
| Static | 13 tài nguyên được tham chiếu đều trả HTTP 200, gồm CSS/JS Bootstrap và tất cả avatar/icons |
| CRUD qua HTTP | Tạo đàn, xem, sửa, giữ sau restart, xóa; có session và CSRF thật |
| RBAC | Ba vai trò đăng nhập; manager được ghi; technician được tạo growth; employee bị từ chối; cả hai không được tạo đàn |
| Truy cập trái quyền | Nút được ẩn và GET/POST trực tiếp trả 403 |
| Lần chạy thứ hai | PASS: migration no-op, counts/users/history không đổi, dữ liệu người dùng được giữ |
| Xung đột cổng | EXE thứ hai thoát lỗi rõ ràng; EXE đầu vẫn phục vụ dashboard |
| Ctrl+C | Console riêng cho EXE: exit 0, `[DEMO_STOPPED]`, cổng được giải phóng cả hai lần |
| Lệnh F5 | Chạy nguyên command trong launch.json từ thư mục copy: HTTP/login/browser/shutdown PASS |

Cấu hình `node-terminal` được kiểm tra với schema của JavaScript Debugger có
sẵn trong VS Code 1.136.1 trên máy. Nó chạy một lệnh terminal; không gọi Node
của hệ thống. **Chưa tự động thao tác phím F5 trong GUI VS Code hoặc double-click
trong Explorer**. Đã chạy trực tiếp chính EXE bằng Windows process launcher và
chạy nguyên lệnh F5; không ghi nhận thao tác GUI chưa thực hiện là PASS.
Không kiểm tra bằng máy Windows thứ hai hoặc gỡ Python toàn hệ thống.

## Kiểm tra không truy cập được Internet

Ngoài lượt chạy với proxy không hoạt động, đã chạy bản sao EXE cuối cùng trong
sandbox hạn chế mạng, không dùng escalation. Cùng môi trường đó, HTTPS tới
`example.com` và CDN Bootstrap đều không kết nối được, còn HTTP loopback hoạt động.
`packaging/verify_offline.ps1` xác minh đăng nhập ba vai trò, 15 trang chính,
Bootstrap/static, CRUD đàn, thống kê và POST AI chưa cấu hình: **PASS**.
Không thay firewall hệ thống, network adapter, PATH hệ thống hoặc execution policy.
Browser mặc định ở ngoài sandbox; các tài nguyên trang đều là localhost.

Lượt offline dùng console redirect của công cụ nên bỏ qua tín hiệu Ctrl+C;
đã dừng đúng tiến trình test sau khi xác minh đường dẫn/PID. Điều này không được
tính là kiểm tra shutdown sạch. Shutdown sạch được xác minh riêng với console
Windows mới như bảng trên. Lúc đầu cổng 8000 còn do source demo cũ giữ; launcher
đã báo đúng lỗi, sau khi dừng phiên workspace cũ thì các lượt độc lập chạy đạt.

## Source regression và quét bộ phát hành

- `manage.py test apps --verbosity 1`: **294/294 PASS**, 35.737 giây.
- `manage.py check`: không có vấn đề.
- `manage.py makemigrations --check --dry-run`: không có thay đổi.
- `manage.py showmigrations`: toàn bộ 28 migration `[X]`.
- `packaging/inspect_release.py`: quét file vật lý, ZIP, CArchive và code PYZ.
- Không phát hiện đường dẫn máy phát triển theo các mẫu yêu cầu, khóa riêng/API
  theo mẫu kiểm tra, DB phát triển, `.env`, `.venv`, node_modules, Git metadata,
  cache/loose `.pyc`, log hay module kiểm thử project.
- `base_library.zip` chứa bytecode của Python runtime theo thiết kế PyInstaller;
  không có `.pyc` rời hoặc thư mục `__pycache__` trong bộ giao.
- Quét mẫu không thay thế kiểm toán mọi loại secret; mã launcher dùng secret ngẫu nhiên.

Bằng chứng máy đọc tại `build/portable-verification.json`,
`build/offline-verification.json`, `build/release-inventory.json`; console log
lần đầu/lần hai/lệnh F5 và source regression nằm cùng thư mục. Chúng được giữ
cục bộ, không commit dữ liệu kiểm thử hoặc binary vào Git.

## Kết luận

Đã hoàn thành implementation và các kiểm tra runtime/source kể trên. Có thể
bàn giao bộ portable cùng source. Giới hạn xác minh còn lại là thao tác GUI
F5/double-click thực tế và kiểm tra trên máy Windows khác; không có blocker code
được phát hiện. Không thay đổi nghiệp vụ hoặc mở rộng sang tính năng UI mới.

## Addendum — 2026-10-17 (workspace update after this report)

Các kết quả phía trên ghi lại lần xác minh portable ngày 2026-09-09; các ghi chú F5 trong phần đó
phản ánh cấu hình tại thời điểm ấy. Cấu hình F5 hiện tại trong `.vscode/launch.json` chạy Django
source bằng `python .\tools\run_demo.py`. Chạy `DEMO_PORTABLE/DEMO.exe` trực tiếp vẫn là lối
chạy portable riêng.

Sau báo cáo gốc, chatbot hỏi đáp dữ liệu chăn nuôi được bổ sung theo yêu cầu của giảng viên, bên
cạnh ba chức năng AI gốc Reminder, Herd Summary và Growth Report. Trong workspace hiện tại, kiểm tra
offline đạt: chat 41/41 test, toàn bộ `apps` 438/438 test, Django check, migration drift check và
`git diff --check`. F5 smoke test qua Django source bao gồm câu hỏi đếm đàn, đàn nhiều nhất và đàn
ít nhất. Các thay đổi source/test của Task 1 đã được đưa lên GitHub trong commit.

Không có AI live test mới. KT3 prompt evaluation trước đây chỉ áp dụng cho ba chức năng AI gốc,
không đánh giá chatbot. Báo cáo này không khẳng định `DEMO.exe` đã được build lại hoặc kiểm chứng
với chatbot mới; các test ở trên là kiểm tra source, không phải kiểm thử portable. Không có API key
nào được tuyên bố là đã đóng gói vào `DEMO.exe`.

## Cập nhật tài liệu FINAL-05 — 2026-10-26

Các kiểm tra portable trong phần báo cáo có ngày phía trên là kết quả lịch sử cho artifact và thời điểm đã nêu; chúng không xác minh bản portable với thay đổi FINAL-02/FINAL-03. Portable chưa được build lại hoặc kiểm tra lại hiện tại. F5 hiện chạy Django source qua `tools/run_demo.py`.

Ở source hiện tại, `CareSchedule` là lịch riêng với `CareLog`; Reminder dùng prompt `reminders-v4`, Herd Summary `herd-summary-v3`, Growth Report `growth-report-v2`. Chatbot truy vấn một số câu hỏi lịch bằng ORM cố định với bộ lọc ngày/trạng thái và follow-up được nhận diện; danh sách tối đa 10 dòng. Không bảo đảm hiểu mọi cách diễn đạt. Lịch sử đánh giá live V1/V2/V3 chỉ thuộc ba chức năng AI gốc; Reminder V4 chưa được kiểm chứng live và không có AI live test mới.

Kết quả gần nhất được ghi nhận cho source là 459 test `apps` trong lượt FINAL-03. Helper backup/restore đạt 5 unittest riêng trong lượt FINAL-04; các suite không được cộng nếu chồng lặp. Manual evidence do sinh viên cung cấp gồm thao tác UI lịch chăm sóc FINAL-02 tại mục 8 và chatbot FINAL-03 tại mục 9 của `09_care_schedule_completion_design.md`; không phải kiểm tra portable, CRUD tổng quát hay mọi quyền. Backup/restore được hướng dẫn tại `SQLITE_BACKUP_RESTORE.md`; phép thử restore được thực hiện trên bản sao trong thư mục tạm, không phải database portable thật.
