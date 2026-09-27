# Báo cáo kiểm chứng — 2026-09-27

Đây là kết quả thực thi khi tạo project, không phải kết quả của một workflow đã chạy trên tài khoản GitHub của bạn.

## Môi trường

- Mac Apple Silicon, Docker Engine 29.8.0, Docker Compose 5.5.1.
- Node 22 và Python 3.13 chạy trong container để kiểm tra đúng runtime của project.
- PostgreSQL 17.11 thật; không dùng SQLite.
- Compose local, test và diễn tập dùng project name/port/volume riêng. Không thay đổi lab khác đang chạy trên máy.
- Không truy cập VPS, tạo GitHub secret, đăng nhập GHCR, commit hay push repository.

## Đã chạy và pass

| Kiểm tra | Kết quả thực tế |
|---|---|
| Frontend dependency | Tạo lockfile và `npm ci` thành công |
| Frontend lint | ESLint 10 pass |
| TypeScript | `tsc --noEmit` pass |
| Production frontend build | Vite build pass |
| Backend dependencies/imports | Cài các version được pin, import API thành công |
| Backend lint | `ruff check .` pass |
| Unit/API tests | **11 passed**: health, DB error, version, create/get quiz, validation |
| PostgreSQL integration | **6 passed**: migration head, health, insert/select, question, cascade, FK, validation |
| Alembic | `upgrade head` từ DB trống; `alembic check` không thấy lệch schema/models |
| Test command dành cho người học | `bash scripts/test-local.sh` pass và tự dọn Compose test |
| Script orchestration | **9 tests passed**, gồm migration fail, backup fail, retry, health 200 chính xác, rollback sau failed candidate |
| Shell | Bash syntax và ShellCheck pass |
| GitHub Actions | actionlint 1.7.7 pass; kiểm tra syntax, expression và embedded shell |
| Compose | Local/test/production `config --quiet` pass |
| Dockerfiles | Build thành công cả `linux/arm64` và `linux/amd64`; imports backend và cú pháp Node trên AMD64 pass |
| Local startup | `docker compose ... up -d --build --wait` lên đủ 3 service healthy |
| Giao diện thật | Browser tạo quiz → thêm 4 đáp án → chọn A → hiển thị `Điểm: 1/1` |
| Volume | `down` rồi `up` tạo lại container; quiz đã tạo vẫn tồn tại |
| Health với DB bị tắt | Dừng riêng Postgres local: HTTP **503**, `Database unavailable`; khởi động lại thành công |
| HTTP qua frontend proxy | Smoke frontend → FastAPI → PostgreSQL pass |
| Smoke cleanup | Sau các lần smoke: số row có title `__smoke__...` bằng **0** |
| Secrets/config | `.env`, `.env.prod`, backup, state bị Git ignore; không có private key/token trong source |

Test suite có **một deprecation warning từ Starlette** về việc TestClient dùng `httpx` thay vì `httpx2`. Các test vẫn pass; warning không bị ẩn. Đây là dependency chỉ dùng cho test, không được đưa vào backend runtime image. Có thể chuyển test dependency khi học bài cập nhật package; hiện lockfile giữ bộ version đã kiểm chứng.

## Diễn tập CD và rollback thật trên Docker local

Dùng một registry Docker tạm chỉ bind `127.0.0.1:15000`, các app port `18002/18082`, PostgreSQL/volume riêng và file cấu hình ngoài repository. Chạy chính `deploy.sh`, `backup-db.sh`, `check-health.sh`, `smoke-test.sh` và `rollback.sh` của project.

Các điều chỉnh của môi trường thử:

- Bản copy của `compose.prod.yaml` đổi prefix image GHCR thành registry loopback; không thêm `build`.
- Ba chuỗi tag 40 ký tự `111...`, `222...`, `333...` chỉ là version thử, không phải Git commit thật.
- macOS không có util-linux `flock`, nên môi trường thử dùng một adapter nhỏ gọi `fcntl.flock` trên file descriptor. Tests orchestration riêng chạy trên Linux và dùng `flock` thật. Trên Ubuntu VPS, script dùng util-linux `flock` như README yêu cầu.
- Password của các DB kiểm tra được tạo tạm, không ghi vào project hay log báo cáo.
- Image cố tình lỗi được tạo từ thư mục tạm; lỗi đó không có trong source giao nộp.

| Bước diễn tập | Kết quả |
|---|---|
| Build/push version thử v1 vào registry local | Backend và frontend push thành công |
| Deploy v1 | Backup DB mới → pull → migration `0001` → start → health → smoke → success |
| Build/push/deploy v2 | Version API đổi sang `222...`; previous lưu `111...` |
| Deploy v3 có lỗi POST quiz | Health/version pass; smoke nhận HTTP **500**; deploy trả exit code khác 0 |
| State sau v3 fail | current=`333...`, previous=`222...`, last_successful=`222...` |
| Chạy rollback mặc định | Pull/run đúng v2; health/smoke pass; API trả `222...` |
| Đối chiếu image | Image ID của cả hai container bằng ID image v2 đã push/pull từ registry |
| Schema sau rollback | Vẫn revision `0001`; không chạy Alembic downgrade |
| Backup/restore | Tạo một row, chạy pg_dump, restore vào DB riêng `quiz_restore_check`, đọc được đúng row đó |

Các lỗi migration/backup/health trong orchestration được kiểm tra bằng test mô phỏng lệnh Docker để xác nhận script dừng đúng pha và giữ đúng state. Không gọi đó là deploy lỗi trên VPS thật. Riêng lỗi chức năng sau health, rollback image và backup/restore đã được thử với Docker/PostgreSQL/HTTP thật như bảng trên.

## Chưa kiểm chứng trên hạ tầng của bạn

| Chưa chạy | Vì sao | Cách bạn kiểm chứng |
|---|---|---|
| Workflow trên GitHub-hosted runner | Chưa có remote repository được cung cấp/push | Push project với `.github` ở root; quan sát bốn CI jobs và hai Docker builds |
| Push/pull GHCR bằng tài khoản của bạn | Không dùng credential thật | Giữ CD tắt, push main; kiểm tra hai package, SHA tag, visibility |
| SSH/scp tới VPS | Không có VPS được cấp quyền | Cấu hình ba secrets + known_hosts, thử SSH bằng user deploy |
| Ubuntu host và firewall thật | Chưa chạy trên VPS | Kiểm tra Docker/Compose/flock, `uname -m`, port truy cập và disk |
| End-to-end GitHub → GHCR → VPS | Cần bạn chủ động bật `DEPLOY_ENABLED` | Theo README: publish public packages → cấu hình VPS → bật CD → push main |
| Rollback với schema thay đổi phức tạp | Ngoài phạm vi schema v1 của lab | Làm Experiment 6 rồi 10; chỉ dùng migration tương thích và DB thử |

## Chạy lại các kiểm tra chính

Trên Mac, sau khi cấu hình `.env`:

```bash
bash scripts/test-local.sh
docker compose up -d --build --wait
ENV_FILE="$PWD/.env" COMPOSE_FILE="$PWD/compose.yaml" \
  COMPOSE_PROJECT_NAME=cicd-lab-2-local bash scripts/check-health.sh local
ENV_FILE="$PWD/.env" COMPOSE_FILE="$PWD/compose.yaml" \
  COMPOSE_PROJECT_NAME=cicd-lab-2-local bash scripts/smoke-test.sh local
```

Frontend trên máy có Node 22.13+: `cd frontend && npm ci && npm run lint && npm run typecheck && npm run build`.

Các container, registry, volume và DB do lần diễn tập này tạo được dọn sau kiểm tra. Project không chứa `.env` thật; bạn tự đặt password local trước khi chạy. Các image/cache build có thể còn để lần build tiếp theo nhanh hơn. Repository Git riêng đã được khởi tạo ở branch `main`, chưa có commit và chưa có remote.
