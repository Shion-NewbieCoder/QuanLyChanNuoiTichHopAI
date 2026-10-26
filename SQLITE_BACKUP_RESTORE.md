# Sao lưu và khôi phục SQLite cho demo local

Hướng dẫn này áp dụng cho database source Django và database portable. Hai database là hai file riêng; sao lưu một file không sao lưu file còn lại. Không có backup tự động.

## 1. Xác định đúng database

### Django source / F5

Trong `backend/config/settings.py`, Django dùng `DJANGO_DEMO_DB_PATH` nếu biến này có trong environment của tiến trình; nếu không, mặc định là `backend/db.sqlite3`. `tools/run_demo.py` kế thừa environment của VS Code/người chạy và khởi động với working directory `backend`, vì vậy đường dẫn tương đối cũng được giải quyết từ thư mục đó.

Từ PowerShell tại project root, có thể hỏi Django settings chính xác mà không kết nối hoặc sửa database:

```powershell
$projectRoot = (Resolve-Path .).Path
Push-Location (Join-Path $projectRoot 'backend')
$dbPath = (& ..\.venv\Scripts\python.exe -c 'import os; os.environ.setdefault("DJANGO_SECRET_KEY", "path-resolution-only"); os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings"); import django; django.setup(); from django.conf import settings; from pathlib import Path; print(Path(settings.DATABASES["default"]["NAME"]).resolve())').Trim()
$commandResult = $LASTEXITCODE
Pop-Location
if ($commandResult -ne 0 -or -not $dbPath) { throw 'Không đọc được đường dẫn database từ Django settings.' }
$dbPath
```

Chạy lệnh trong cùng environment với F5. Nếu `DJANGO_DEMO_DB_PATH` được đặt trong environment của VS Code, giữ nguyên giá trị đó khi xác định và dùng database. Lệnh chỉ đặt secret giả bên trong tiến trình dò đường dẫn; không in hoặc lưu secret.

### Portable

Portable ghi database vào `data/db.sqlite3` cạnh `DEMO.exe`. Với bản giải nén mặc định, đó là `DEMO_PORTABLE/data/db.sqlite3`; nếu chuyển thư mục portable thì đường dẫn đi theo vị trí mới của EXE. `tools/portable_demo.py` đặt `DJANGO_DEMO_DB_PATH` riêng cho tiến trình portable. Đây không nhất thiết là database ở `backend/db.sqlite3`.

```powershell
$exePath = (Resolve-Path .\DEMO_PORTABLE\DEMO.exe).Path
$portableDbPath = Join-Path (Split-Path -Parent $exePath) 'data\db.sqlite3'
```

## 2. Tạo backup

Khuyến nghị dùng helper `tools/sqlite_backup.py`. Helper dùng Python standard library và SQLite Online Backup API để tạo snapshot nhất quán, kể cả khi SQLite đang dùng WAL. Tên file có timestamp đến microsecond; nếu tên đã tồn tại, helper từ chối ghi đè.

Ví dụ backup database source, sau khi đã chạy lệnh xác định `$dbPath` ở trên:

```powershell
$backupDir = Join-Path $env:USERPROFILE 'LivestockDemoBackups\source'
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
.\.venv\Scripts\python.exe tools\sqlite_backup.py backup --database $dbPath --backup-dir $backupDir
```

Để backup portable, dùng `$portableDbPath` thay cho `$dbPath` và chọn thư mục riêng, ví dụ `LivestockDemoBackups\portable`. Giữ nguyên đường dẫn snapshot helper in ra; đừng đổi tên thành tên của một backup cũ.

Ưu tiên helper để backup nhất quán, kể cả khi SQLite đang dùng WAL. Nếu tự sao chép bằng Explorer, chỉ làm sau khi đã dừng ứng dụng và mọi tiến trình dùng database, đồng thời SQLite đã đóng sạch. Không copy riêng file `.sqlite3` khi DB đang chạy hoặc khi chưa xác nhận SQLite đã đóng sạch. Không hướng dẫn hay cố gắng copy bộ sidecar khi chưa biết database đã dừng; không tự xóa WAL/SHM.

## 3. Khôi phục

1. Dừng F5 bằng `Ctrl+C`, hoặc đóng cửa sổ `DEMO.exe`; dừng mọi tiến trình khác đang đọc/ghi file đó. Không restore khi còn server, SQLite Browser hoặc tiến trình ghi khác.
2. Xác định lại đúng `$dbPath` hoặc `$portableDbPath`. Chọn snapshot mong muốn bằng đường dẫn đầy đủ.
3. Chạy helper. Restore bị từ chối nếu file đích còn `-wal` hoặc `-shm`; đóng mọi ứng dụng dùng DB và để SQLite đóng/checkpoint đúng cách rồi thử lại. Không tự xóa sidecar. Helper kiểm tra sidecar trước khi mở DB đích để tạo snapshot safety và kiểm tra lại ngay trước khi thay thế. Các kiểm tra này không chứng minh rằng không còn tiến trình đang sử dụng database; người dùng vẫn phải dừng tất cả tiến trình dùng DB. Helper tạo snapshot safety có timestamp trong `--backup-dir`, dựng và kiểm tra bản khôi phục ở file tạm cùng thư mục, rồi mới thay thế database đích. Nếu thao tác sau khi tạo safety backup thất bại, thông báo lỗi sẽ chỉ đường dẫn safety backup. Nếu database đích chưa tồn tại thì không có safety backup cũ để tạo.

```powershell
$snapshotPath = 'C:\Users\<user>\LivestockDemoBackups\source\db-backup-<timestamp>.sqlite3'
.\.venv\Scripts\python.exe tools\sqlite_backup.py restore --database $dbPath --backup $snapshotPath --backup-dir $backupDir
```

Thay đường dẫn ví dụ bằng đường dẫn thật đã nhận từ lệnh backup. Với portable, dùng `$portableDbPath` và thư mục backup portable tương ứng. Giữ cả snapshot đã chọn lẫn `*-before-restore-*.sqlite3` mà helper tạo; helper không ghi đè backup đã có.

## 4. Xác minh sau khôi phục

Khi ứng dụng vẫn đang dừng, chạy kiểm tra chỉ đọc:

```powershell
.\.venv\Scripts\python.exe tools\sqlite_backup.py verify --database $dbPath
```

Kết quả cần có `INTEGRITY_CHECK: ok`. Có thể dùng `$portableDbPath` cho portable. Không chạy `migrate`, `seed_demo` hoặc launcher để “kiểm tra restore”: F5 source và portable launcher đều có thể migrate/seed, tức là có thể thay đổi database sau khi restore. Chỉ khởi động ứng dụng sau khi đã hoàn tất kiểm tra và giữ lại các backup an toàn.

## Giới hạn

Backup chỉ chứa dữ liệu database. Nó không chứa API key, environment variables, source code, dependencies hoặc các file upload/media nằm ngoài SQLite; vì vậy backup không thay thế source code hay bản portable. Bảo quản file backup riêng và cẩn thận vì nó có thể chứa dữ liệu người dùng trong database.
