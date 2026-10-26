# Checklist demo local

Đây là kịch bản đề xuất cho buổi trình bày, không phải xác nhận rằng mọi bước đã được chạy thủ công. Chỉ thực hiện thao tác khi người trình bày chủ động chuẩn bị demo; tài liệu này không tự khởi động server, gọi AI hay thay đổi dữ liệu.

## Trước buổi demo

- [ ] Mở repository bằng VS Code. Chuẩn bị environment local riêng; không ghi API key, Django secret hoặc giá trị secret vào tài liệu, ảnh chụp hay Git.
- [ ] Nếu cần giữ dữ liệu, làm theo [hướng dẫn backup/restore SQLite](SQLITE_BACKUP_RESTORE.md). Xác định database từ Django settings và environment của F5; source và portable có thể dùng database khác nhau.
- [ ] Dùng F5 để chạy Django source, chờ trang đăng nhập tại `http://127.0.0.1:8000/login/`, và dừng bằng Ctrl+C trong terminal khi kết thúc.
- [ ] Dùng tài khoản demo được `seed_demo` cung cấp: `demo_manager`, `demo_technician` hoặc `demo_employee` (vai trò tương ứng được mô tả trong README), hoặc tài khoản local đã được chuẩn bị. Không chép mật khẩu/secret vào checklist. Không suy diễn rằng quyền của một tài khoản đã được kiểm thử thủ công chỉ từ việc đăng nhập thành công.

## Trình tự trình bày gợi ý

- [ ] Đăng nhập; mở danh sách đàn, cá thể hoặc nhóm vật nuôi. Thử search/filter và một thao tác CRUD phù hợp với tài khoản. Dùng tài khoản có role thích hợp để trình bày khác biệt quyền; không thực hiện thay đổi dữ liệu ngoài kế hoạch demo.
- [ ] Mở Lịch chăm sóc, tạo hoặc chọn một lịch đã chuẩn bị, rồi trình bày cảnh báo theo ngày. `CareSchedule` là lịch riêng; `CareLog` là nhật ký hoạt động đã ghi nhận.
- [ ] Trên AI Assistant, thử các câu hỏi thống kê đàn như “Hiện có bao nhiêu đàn?”, “Đàn nào nhiều nhất?” và “Đàn nào ít nhất?”. Sau đó thử một câu hỏi lịch chăm sóc rõ ràng, chẳng hạn “Có lịch chăm sóc nào sắp tới?” hoặc hỏi theo mã đàn.
- [ ] Có thể giới thiệu Reminder, Herd Summary và Growth Report. Reminder hiện dùng prompt V4 và nhận lịch vaccine/chăm sóc; Summary dùng V3; Growth dùng V2. Khi gọi các chức năng AI này live cần provider, credential hợp lệ trong environment và Internet. Kết quả có thể thất bại an toàn; không cam kết provider sẽ trả lời thành công.

## Giới hạn bằng chứng hiện có

- [ ] Các bước CRUD/search/filter, phân quyền và ba chức năng AI ở trên là gợi ý demo; checklist này không khẳng định chúng đã được chạy thủ công trong lượt hiện tại.
- [ ] Manual evidence do sinh viên cung cấp gồm thao tác UI lịch chăm sóc FINAL-02 ở mục 8 và các tình huống chatbot FINAL-03 ở mục 9 của `09_care_schedule_completion_design.md`; không suy rộng sang CRUD tổng quát hoặc mọi quyền.
- [ ] Test offline dùng database test/fake provider; không chứng minh AI live. Không có AI live test mới; Reminder V4 chưa được kiểm chứng live.
- [ ] Các kiểm tra portable lịch sử chỉ áp dụng cho artifact tại thời điểm được ghi trong `PORTABLE_DEMO_REPORT.md`. Portable chưa được build lại/xác minh với thay đổi FINAL-02/FINAL-03 hiện tại; ưu tiên F5 source cho demo các phần này.
