# SAFE-ROUTE HCMC: Quyết định thiết kế phần Người B

Cập nhật theo `02_schema.sql`. Ký hiệu: ✅ đã chốt · 🔶 giả định tạm (chốt theo mặc định hợp lý, sửa sau nếu A/C/thầy yêu cầu khác) · 🟡 đề xuất, chờ xác nhận (chưa chốt) · ❓ còn mở.

## 1. Phạm vi phần B
| Mục của thầy | File | Trạng thái |
|---|---|---|
| 8. Prediction Service | `risk/logic.py`, `risk/compute.py` | `compute.py` bản mẫu, chưa chạy với DB thật |
| 10. Explainability Engine | `explain/engine.py` | xong, 29 test |
| 12. Scenario testing | `scripts/evaluate.py` | chưa làm |
| 2. Khảo sát người dùng | form + script hồi quy | form nháp, chưa pilot |
| 1. Khảo sát hiện trạng | Chương 1 Mục 1 | bản nháp, cần sửa mục 1.3.3 (trục báo động) |

Giao diện đã thống nhất: `segment_station` (A tạo, B đọc) · `road_segment_risk(segment_id, thoi_diem, risk)` (B ghi, C đọc) · `explain(fastest, safest) -> str` (B viết, C gọi) với dict có `time_min, length_km, risky_km, max_risk`.

## 2. Bảng quyết định

### Dữ liệu và hạ tầng
| # | Quyết định | TT |
|---|---|---|
| 1 | `stations(tram, loai)`: một trạm có thể vừa là trạm mưa vừa là trạm triều; mỗi đoạn đường gán trạm gần nhất **theo từng loại** bằng KNN `<->` trên `geography` | ✅ |
| 2 | Dữ liệu thiếu: dùng số đo có sẵn gần nhất trong CSV | ✅ |
| 3 | Kích hoạt: EventBridge → Lambda → `run()` | ✅ |
| 4 | `road_segment_risk` có `PRIMARY KEY (segment_id, thoi_diem)` nên upsert chạy lại không trùng dòng | ✅ |
| 5 | `segment_id` = `ways.gid` (osm2pgrouting) | ✅ |

### Tính rủi ro
| # | Quyết định | TT |
|---|---|---|
| 6 | Lõi là bảng ΔH × mưa theo VER2 (`BASE_TABLE`) | ✅ |
| 7 | Trục mức báo động là **tùy chọn**, cờ `use_alert_floor` mặc định **tắt**; khi bật dùng thẳng `tide_daily.muc_bao_dong` | ✅ |
| 8 | Giá trị `ALERT_FLOOR` là giả thuyết do nhóm đặt, không có nguồn; chỉ giữ nếu thử nghiệm có/không có sàn (ablation) ở kịch bản 3 cho thấy cải thiện | ✅ |
| 9 | Mưa: `rain_10min` là số đo 10 phút nên cộng dồn cửa sổ trượt 1h và 2h; mưa 2h quy đổi về thang 1h bằng `50/70`; lấy `max(tổng 1h, tổng 2h × 50/70)` | ✅ |
| 10 | Mực nước để tính ΔH = `dinh_trieu_m` (đỉnh triều trong ngày). Đây là cận trên bảo thủ vì `tide_daily` chỉ có số liệu theo ngày | ✅ |
| 11 | Dòng `nghi_van = true` bị bỏ qua, lấy ngày gần nhất không nghi vấn (cờ `skip_suspect_tide`) | ✅ |
| 12 | Decay: **trung bình hai hệ số** của trạm mưa và trạm triều (cờ `decay_mode`: `mean` hoặc `min`); `decay_factor(d) = 1` khi d ≤ 5 km, ngược lại `max(0,2; 5000/d)` | ✅ |
| 13 | Hằng số hiệu chỉnh mốc độ cao `datum_offset_m` (mặc định 0), cộng vào mực nước | 🔶 |
| 14 | Đoạn thiếu cao độ hoặc thiếu trạm thì **không ghi**, chỉ đếm trong `ComputeStats` | 🔶 |

### Cao độ đường
| # | Quyết định | TT |
|---|---|---|
| 15 | Nguồn cao độ đường đề xuất là DEM 30 m (SRTM hoặc Copernicus), lấy mẫu offline trong vùng MVP; nguồn/ảnh raster cuối cùng cần A xác nhận | 🟡 |
| 16 | Đề xuất lấy cao độ ở đầu, giữa, cuối đoạn và dùng giá trị thấp nhất để hạn chế bỏ sót điểm trũng; `after_osm.sql` hiện lấy tâm đoạn. Chờ A xác nhận khả năng triển khai | 🟡 |
| 17 | Giao diện dữ liệu là cột `elevation_m` trong `segment_station`; script hiện gán placeholder 1,5 m và tái tạo bảng khi chạy. Chốt tên cột; nguồn cao độ thật và cách nạp chưa chốt | 🔶 |

### Explainability Engine
| # | Quyết định | TT |
|---|---|---|
| 18 | Delta có dấu, không dùng `abs`; so sánh có dung sai `EPS_TIME=1 phút`, `EPS_KM=0,1 km`, `EPS_RISK=0,05` | ✅ |
| 19 | 11 ca A, B, C, D, E, F, G, H, I, J, X; thứ tự kiểm tra tách theo "có gì tốt hơn / tệ hơn" nên không chồng nhánh | ✅ |
| 20 | API B cung cấp `explain()` một câu và `explain_pair()` hai câu; đề xuất tích hợp mặc định gọi `explain()` theo contract hiện có. C xác nhận hàm được gọi và cách hiển thị | 🟡 |
| 21 | Ca X trả chuỗi rỗng và ghi log. Đề xuất C ẩn vùng giải thích khi chuỗi rỗng; xác nhận ở tích hợp | 🟡 |

### Khảo sát (mục 2)
| # | Quyết định | TT |
|---|---|---|
| 22 | Đo λ = β/α qua 9 câu chọn cặp tuyến (6 bình thường + 3 gấp), hồi quy logistic, sai số chuẩn theo cụm | 🟡 |
| 23 | Fastest: β = 0; Balanced: λ trung vị; Safest: λ ở P75-P90. Chỉ là giá trị khởi điểm, hiệu chỉnh bằng `evaluate.py` | 🟡 |
| 24 | Cỡ mẫu mục tiêu tối thiểu 30-40, tốt nhất 50, có ít nhất 10-15 shipper/tài xế; nếu thiếu so với yêu cầu 50-100 thì báo thầy | 🟡 |

## 2b. Điểm phối hợp A/C (đề xuất, chưa phải quyết định của họ)
Các mục này là đề xuất để phối hợp, không suy ra A/C đã đồng ý. Những phần thuộc B và đã có căn cứ trong schema/code được ghi riêng.

| Điểm | Giả định tạm | Nếu sai thì sửa ở |
|---|---|---|
| Cao độ (A) | Đề xuất DEM offline, mẫu 3 điểm lấy thấp nhất; chưa xác nhận nguồn DEM/cách gán. B chỉ phụ thuộc cột `elevation_m` | `scripts/after_osm.sql` (A); `compute.py` chỉ đọc cột |
| Vị trí trạm triều (A) | Báo cáo mẫu mô tả Phú An trong ví dụ; danh sách trạm thật cần đối chiếu dữ liệu. Không kết luận thay A về việc bỏ Bình Triều/Nhà Bè | `stations`/CSV và nội dung báo cáo |
| `RISKY_PROB` (C) | B đặt 0,7; báo cáo mẫu cũng dùng 0,7 cho màu rủi ro cao. C cần dùng cùng điều kiện `p > 0,7` khi tính `risky_km` | `RISKY_PROB` trong `explain/engine.py` và routing |
| Chuỗi rỗng từ `explain()` (C) | Contract B trả rỗng khi dữ liệu sai; đề xuất UI ẩn vùng giải thích | Tích hợp UI C |
| Đoạn không có dòng rủi ro (C) | Đề xuất đọc bản ghi mới nhất `thoi_diem <= t`; thiếu thì coi là 0 và log. B không ghi các đoạn bị bỏ do thiếu input | Routing C; quy tắc hiện có ở `compute_segment_risks()` |
| Một câu hay hai câu (C) | B có cả hai API; đề xuất gọi `explain()` một câu theo contract, `explain_pair()` là tùy chọn | C xác nhận khi tích hợp |
| `thoi_diem` và tần suất (A/C) | B làm tròn thời điểm xuống 10 phút và upsert. Lịch EventBridge, quy tắc chọn snapshot mới nhất và xử lý snapshot thiếu cần A/C thống nhất | `run()` (B), lịch triển khai (A), truy vấn routing (C) |
| Khóa mở rộng dict của `explain` | Contract hiện chỉ có `time_min, length_km, risky_km, max_risk`; giữ nguyên cho tương thích | Thống nhất contract B/C |

## 3. Luồng `compute.py`
```
thoi_diem
  ├─ mưa  : rain_10min -> tổng trượt 1h/2h theo từng trạm (neo tại số đo gần nhất nếu trạm mất dữ liệu)
  ├─ triều: tide_daily -> dòng mới nhất ≤ ngày của thoi_diem, bỏ nghi_van
  └─ mỗi đoạn (ways.gid):
       ΔH = dinh_trieu_m + datum_offset − elevation_m
       p  = flood_probability(ΔH, mưa, alert[nếu bật cờ])
       p *= decay(trạm mưa, trạm triều)
       -> upsert road_segment_risk(segment_id, thoi_diem, p)
```
Tách hai lớp: `compute_segment_risks()` là hàm thuần (test không cần DB); `load_inputs()`, `write_risks()`, `run()` làm việc với DB.

## 4. Giả định chưa kiểm chứng (cần đối chiếu)
1. ~~Schema `segment_station`~~ đã khớp `after_osm.sql`: một dòng mỗi đoạn, cột `tram_mua, d_mua_m, tram_trieu, d_trieu_m, elevation_m`. Trạm mưa chỉ chọn trong các trạm có dữ liệu `rain_10min`; trạm triều chọn trong mọi trạm loại `trieu`.
2. Phần SQL trong `compute.py` chưa chạy thử với DB thật.
3. `RISKY_PROB` phải trùng giữa phía routing và `explain/engine.py`, nếu không ca X báo lỗi oan (xem mục 2b).
4. Danh sách trạm: đối chiếu CSV/schema với báo cáo trước khi sửa nội dung về Bình Triều hoặc trạm tham chiếu.
5. Mốc độ cao của số liệu thủy văn có thể khác mốc của DEM; kiểm tra trước khi tin ngưỡng ΔH 0,2 m.

## 5. Hạn chế cần ghi vào báo cáo
- **Triều theo ngày:** `tide_daily` chỉ có đỉnh và chân trong ngày, nên ΔH dùng đỉnh triều cho cả ngày và đánh giá quá cao rủi ro ở giờ triều thấp. Hướng mở rộng: dùng chuỗi mực nước theo giờ hoặc nội suy đường triều giữa chân và đỉnh.
- **Cao độ placeholder 1,5 m:** khi chưa có DEM, mọi đoạn có cùng độ cao giả định nên khác biệt ΔH không phản ánh địa hình; kết quả chỉ để kiểm tra pipeline, chưa đánh giá được tuyến.
- **Khoảng cách và cao độ tính tại tâm đoạn** (`ST_Centroid`), một đoạn OSM dài chỉ có một giá trị.
- **DEM 30 m:** là mô hình bề mặt (có mái nhà, tán cây), cùng cỡ sai số với tín hiệu ở vùng phẳng. Kiểm tra bằng vài điểm ngập đã biết (chợ Thủ Đức, Linh Đông, Thảo Điền).
- **Số đo mưa có khoảng trống:** tổng trượt có thể thấp hơn thực tế khi thiếu một số mốc 10 phút trong cửa sổ.
- **`rain_daily` chưa dùng:** chỉ có tổng theo ngày, không phản ánh cường độ 1-2 giờ.
- Ngưỡng trong bảng ΔH/mưa, xác suất của ma trận, `ALERT_FLOOR`, EPS và λ do nhóm lựa chọn; không có nhãn ngập theo đoạn để hiệu chỉnh/kiểm định trực tiếp. Báo cáo mẫu nêu cấp triều Phú An 1,4/1,5/1,6 m, nhưng `muc_bao_dong` trong dữ liệu là cấp đã phân loại, không phải ngưỡng để B tự suy ra lại.

## 6. Việc tiếp theo
- [ ] Chạy thử `compute.run()` với DB thật, đối chiếu và sửa SQL nếu cần
- [ ] Chia sẻ đề xuất mục 2b với A/C để chốt giao diện phối hợp; hiện chưa ghi nhận xác nhận của họ trong repo
- [ ] Thống kê khoảng cách đoạn → trạm trong vùng MVP, xem decay có kích hoạt không
- [ ] Chính sách giữ dữ liệu: mỗi 10 phút ghi một dòng cho mỗi đoạn vào `road_segment_risk`, cần quy tắc xóa dữ liệu cũ khi chạy dài hạn
- [ ] Kiểm tra mốc độ cao của số liệu thủy văn so với DEM, đặt `datum_offset_m` nếu lệch
- [ ] Pilot form khảo sát với 5-8 người, rồi tung rộng (mục 22-24 chốt sau pilot)
- [ ] Viết `scripts/evaluate.py` (khung hàm đo trước, phần gọi routing sau), gồm ablation có/không có `ALERT_FLOOR`
- [ ] Sửa Chương 1: mục 1.3.3 (trục báo động tùy chọn), mục 1.4 (tham số do nhóm đặt), trạm triều tham chiếu
