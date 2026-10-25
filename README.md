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
