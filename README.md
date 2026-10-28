## Quick start

Chạy toàn bộ môi trường phát triển (backend + PostgreSQL/PostGIS/pgRouting) bằng Docker. Không cần cài Python hay PostgreSQL trên máy.

### Yêu cầu

- [Git](https://git-scm.com/)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/macOS) hoặc Docker Engine + Compose v2 (Linux)

Kiểm tra đã cài đủ:

```bash
git --version
docker --version
docker compose version
```

### Chạy lần đầu

**1. Clone repo**

```bash
git clone <repo-url>
cd safe-route-hcmc
```

**2. Tạo file `.env`** (file này nằm ngoài git, mỗi người tự tạo)

```bash
# macOS / Linux
cp .env.example .env

# Windows PowerShell
Copy-Item .env.example .env
```

Mở `.env` và đổi `DB_PASSWORD` thành mật khẩu của bạn (chỉ dùng chữ và số, tránh ký tự đặc biệt như `@ : / # ?`).

**3. Khởi động** (mở Docker Desktop trước; lần đầu tải image mất vài phút)

```bash
docker compose up --build
```

Khi log hiện `database system is ready to accept connections` và `Uvicorn running on http://0.0.0.0:8000` là đã chạy xong.

**4. Kiểm tra** (mở cửa sổ terminal thứ hai)

| Địa chỉ                         | Kết quả mong đợi                   |
| ------------------------------- | ---------------------------------- |
| http://localhost:8000/health    | `{"status":"ok","env":"local"}`    |
| http://localhost:8000/health/db | Phiên bản `postgis` và `pgrouting` |
| http://localhost:8000/docs      | Trang Swagger của API              |

**5. Chạy test**

```bash
docker compose exec backend pytest
```

Kết quả mong đợi: tất cả test `passed`.

**6. Dừng**

Nhấn `Ctrl+C` ở cửa sổ đang chạy, sau đó:

```bash
docker compose down
```

### Lệnh thường dùng

| Việc cần làm                               | Lệnh                                                             |
| ------------------------------------------ | ---------------------------------------------------------------- |
| Chạy nền                                   | `docker compose up -d`                                           |
| Xem log backend                            | `docker compose logs -f backend`                                 |
| Khởi động lại backend                      | `docker compose restart backend`                                 |
| Vào psql của DB                            | `docker compose exec db psql -U <DB_USER> -d <DB_NAME>`          |
| Xem extension đã cài                       | `docker compose exec db psql -U <DB_USER> -d <DB_NAME> -c "\dx"` |
| Xóa sạch dữ liệu DB và khởi tạo lại        | `docker compose down -v`                                         |
| Chạy kèm frontend (khi đã có project Vite) | `docker compose --profile frontend up --build`                   |

`<DB_USER>` và `<DB_NAME>` là giá trị trong file `.env` của bạn (mặc định `saferoute`).

### Nạp dữ liệu

**1. Dữ liệu trạm, mưa, triều (tự động)**

4 file CSV trong `data/clean/` được nạp tự động bởi `database/init/02_schema.sql` và `03_load_csv.sql` khi volume DB còn trống. Nếu DB đã tạo từ trước khi có các file này, khởi tạo lại:

```bash
docker compose down -v
docker compose up -d --build
```

Kiểm tra số dòng (mong đợi `stations` = 16, `rain_10min` = 13938, `rain_daily` = 39702, `tide_daily` = 20453):

```bash
docker compose exec db psql -U <DB_USER> -d <DB_NAME> -c "SELECT count(*) FROM stations"
```

**2. Bản đồ đường phố Thủ Đức (chạy tay, 1–3 phút)**

```bash
docker compose exec db bash /scripts/load_osm.sh
```

Script tải đường phố khu Thủ Đức từ Overpass (lỗi thì tự chuyển sang mirror `overpass.kumi.systems`) vào `data/osm/thuduc.osm`, nạp vào bảng `ways` / `ways_vertices_pgr` bằng osm2pgrouting, rồi tạo bảng `segment_station` (mỗi đoạn đường → trạm mưa và trạm triều gần nhất). Đã có file OSM thì không tải lại; muốn tải mới thì xoá `data/osm/thuduc.osm`.

Kiểm tra (vào psql: `docker compose exec db psql -U <DB_USER> -d <DB_NAME>`):

```sql
-- Số đoạn đường (> 0, hiện khoảng 25 nghìn)
SELECT count(*) FROM ways;

-- Trạm gần nhất của từng đoạn; d_mua_m, d_trieu_m tính bằng mét
SELECT * FROM segment_station LIMIT 5;

-- Thử tìm đường A* (pgRouting 4.0) giữa 2 đỉnh, cost = thời gian (giây)
SELECT * FROM pgr_aStar(
  'SELECT gid AS id, source, target, cost_s AS cost, reverse_cost_s AS reverse_cost,
          x1, y1, x2, y2 FROM ways',
  (SELECT id FROM ways_vertices_pgr ORDER BY the_geom <-> ST_SetSRID(ST_MakePoint(106.7558, 10.8448), 4326) LIMIT 1),
  (SELECT id FROM ways_vertices_pgr ORDER BY the_geom <-> ST_SetSRID(ST_MakePoint(106.79, 10.81), 4326) LIMIT 1),
  directed => true);
```

**3. (Tuỳ chọn) Rủi ro giả để code routing/frontend trước**

```bash
docker compose exec db psql -U <DB_USER> -d <DB_NAME> -f /seed/seed_fake_risk.sql
```

### Cấu trúc thư mục

```
safe-route-hcmc/
├── backend/            # FastAPI: api, risk, routing, explain, ingestion
│   ├── app/
│   └── tests/
├── frontend/           # React + Vite + MapLibre
├── database/
│   ├── init/           # SQL khởi tạo (chạy lần đầu khi volume trống)
│   └── seed/           # dữ liệu mẫu nhỏ
├── docs/               # kiến trúc, quyết định kỹ thuật (ADR)
├── scripts/            # script tải và nạp dữ liệu
├── docker-compose.yml
└── .env.example
```

### Quy ước làm việc

- Không push trực tiếp lên `main`. Tạo nhánh từ `main` mới nhất: `git switch -c feature/<ten-ngan>`, sau đó mở Pull Request và nhờ ít nhất 1 người review.
- Commit theo dạng `feat:`, `fix:`, `docs:`, `chore:` (ví dụ `feat: add risk matrix lookup`).
- Không commit `.env`, khóa AWS, hoặc dữ liệu dung lượng lớn (OSM, DEM, file xls). Chia sẻ dữ liệu lớn qua Drive và ghi link vào `docs/`.
- File thử nghiệm cá nhân đặt trong thư mục `scratch/` (đã được `.gitignore` bỏ qua).

### Xử lý lỗi thường gặp

| Triệu chứng                                                                                 | Cách xử lý                                                                                                                                          |
| ------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `error during connect` / không kết nối được Docker                                          | Mở Docker Desktop và đợi nó chạy xong, rồi thử lại.                                                                                                 |
| `manifest unknown` khi tải image DB                                                         | Tag không tồn tại: chọn tag khác trên Docker Hub và đặt `DB_IMAGE` trong `.env`.                                                                    |
| Cổng 5432 hoặc 8000 bị chiếm                                                                | Đổi `DB_PORT` hoặc `BACKEND_PORT` trong `.env` (ví dụ 5433).                                                                                        |
| `password authentication failed` sau khi đổi `DB_PASSWORD`                                  | Volume vẫn giữ mật khẩu cũ: `docker compose down -v` rồi chạy lại.                                                                                  |
| `function pgr_version() does not exist`                                                     | Script khởi tạo chưa chạy: `docker compose down -v` rồi chạy lại.                                                                                   |
| Windows: `bind: An attempt was made to access a socket in a way forbidden...` khi tải image | Chạy `wsl --shutdown`, mở lại Docker Desktop. Nếu vẫn lỗi, mở PowerShell bằng quyền Administrator và chạy `net stop winnat` rồi `net start winnat`. |
| Sửa code mà backend không tự reload (Windows)                                               | `docker compose restart backend`.                                                                                                                   |
| Git Bash: `bash: C:/Program Files/Git/scripts/load_osm.sh: No such file or directory`        | Git Bash tự đổi đường dẫn `/scripts/...`. Chạy lệnh trong PowerShell, hoặc thêm `MSYS_NO_PATHCONV=1` phía trước lệnh.                               |
| `load_osm.sh` báo `$'\r': command not found`                                                | File bị đổi sang CRLF. Mở file trong VS Code, bấm `CRLF` ở góc dưới phải, chọn `LF` rồi lưu.                                                       |
