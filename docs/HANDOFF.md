# Handoff kỹ thuật: `cicd-lab-2`

Ảnh chụp implementation trong workspace ngày 2026-09-27. Tài liệu này mô tả code hiện có để AI khác đọc và review; không thay thế kết quả chạy GitHub/VPS. Repo Git riêng đang ở branch `main`, chưa có commit, remote hay `.env` thật. Các file nguồn được chép **nguyên văn** ở phần cuối; mọi đường dẫn bên dưới tính từ root `cicd-lab-2/`.

## 1. Cây thư mục quan trọng

```text
cicd-lab-2/
├── .github/workflows/ci-cd.yml
├── .env.example                 # mẫu local; password để trống
├── .env.prod.example            # mẫu VPS; GHCR_OWNER và password cần điền
├── .gitignore
├── compose.yaml                 # build/run local
├── compose.test.yaml            # PostgreSQL test riêng + backend test image
├── compose.prod.yaml            # image GHCR, không build trên VPS
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── server.mjs                # static server + /api reverse proxy
│   └── src/{App.tsx,api.ts,main.tsx,style.css}
├── backend/
│   ├── Dockerfile
│   ├── requirements.in, requirements-dev.in
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/{env.py,versions/0001_initial.py}
│   ├── app/{database.py,main.py,models.py,schemas.py,smoke.py}
│   └── tests/{unit/test_api.py,integration/{conftest.py,test_postgres.py}}
├── scripts/
│   ├── {common,deploy,rollback,backup-db,check-health,smoke-test,test-local}.sh
│   └── tests/test_release_state.py
└── docs/{VERIFICATION,HANDOFF}.md
```

Đã bỏ qua `package-lock.json`, các Python lockfile `requirements*.txt`, cache và image/build output trong cây trên. Các lockfile **có trong repo** và được dùng bởi `npm ci`/`pip install`.

## 2. Luồng local đang được code thực hiện

1. Người chạy copy `.env.example` thành `.env`, tự đặt `POSTGRES_PASSWORD`, rồi chạy `docker compose up -d --build` tại root repo. Compose project name là `cicd-lab-2-local`; hai Dockerfile được build local với `APP_VERSION=${APP_VERSION:-local}`.
2. Compose tạo network mặc định và named volume `postgres_data`, chạy `postgres:17-alpine`. `pg_isready` phải healthy trước khi backend khởi động. PostgreSQL không publish cổng ra host.
3. Local `backend` override Dockerfile CMD bằng `alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000`. API kết nối `postgres:5432` bằng `POSTGRES_HOST=postgres` và credentials Compose truyền vào. API `GET /api/health` chạy SQL `SELECT 1`; DB lỗi trả HTTP 503. Host truy cập backend qua `127.0.0.1:8002` theo port mặc định.
4. Sau khi backend Docker healthcheck healthy, `frontend` chạy Node `server.mjs` trên cổng container 8080, publish mặc định `127.0.0.1:8082`. Vite đã tạo static files ở build stage. Browser tải UI; `frontend/src/api.ts` dùng URL tương đối `/api/...`; `server.mjs` proxy request đó tới `http://backend:8000` trên Compose network.
5. FastAPI dùng SQLAlchemy/psycopg tới PostgreSQL. UI gọi API để tạo/list/get quiz, thêm question, rồi chấm điểm trong browser. Quiz/question persist trong named volume; không có bảng lịch sử làm bài.

## 3. Ba file Compose

| File/service | Logic thực tế |
|---|---|
| `compose.yaml` / `postgres` | `postgres:17-alpine`; DB/user mặc định `quiz_lab`/`quiz`; password bắt buộc từ `.env`; named volume; healthcheck `pg_isready`; không publish DB port. |
| `compose.yaml` / `backend` | Build `./backend`, truyền build arg `APP_VERSION`; env DB host là service `postgres`; chạy Alembic trước Uvicorn; đợi Postgres healthy; publish loopback `BACKEND_PORT` mặc định 8002 → container 8000. |
| `compose.yaml` / `frontend` | Build `./frontend`, truyền cùng build arg; `BACKEND_URL=http://backend:8000`; đợi backend healthy; publish loopback `FRONTEND_PORT` mặc định 8082 → container 8080. |
| `compose.test.yaml` / `postgres` | DB `quiz_test` và user `quiz_test`, password literal `test-only` chỉ cho DB dùng rồi bỏ; data directory là `tmpfs`; không publish port; healthcheck riêng. |
| `compose.test.yaml` / `tests` | Build `backend` stage `test`; inject `DATABASE_URL`/`TEST_DATABASE_URL` tới `postgres:5432/quiz_test`; đợi DB healthy. Image test mặc định chạy migration, `alembic check`, toàn bộ pytest. `scripts/test-local.sh` gọi Compose này và dọn bằng `down --volumes`. |
| `compose.prod.yaml` / `postgres` | Cùng Postgres 17, named volume riêng theo project prod, `restart: unless-stopped`, env DB bắt buộc từ `.env.prod`; không publish 5432. |
| `compose.prod.yaml` / `backend` | **Không có `build`**. Image `ghcr.io/${GHCR_OWNER}/cicd-lab-2-backend:${IMAGE_TAG}`; env DB giống local; đợi Postgres healthy; bind `${BIND_ADDRESS:-0.0.0.0}:${BACKEND_PORT:-8002}:8000`. Dockerfile CMD chỉ chạy Uvicorn; migration thuộc `deploy.sh`. |
| `compose.prod.yaml` / `frontend` | **Không có `build`**. Image GHCR frontend cùng tag; runtime proxy `http://backend:8000`; chỉ đợi backend `service_started` vì deploy script tự retry/check health; bind `${BIND_ADDRESS:-0.0.0.0}:${FRONTEND_PORT:-8082}:8080`. |

## 4. GitHub Actions `.github/workflows/ci-cd.yml`

- Trigger: push trên mọi branch (`branches: ['**']`) và `pull_request`. Workflow `contents: read`; concurrency theo `github.ref`, `cancel-in-progress: false`.
- Bốn job **không khai báo `needs`** nên có thể chạy song song: `frontend-ci` (`npm ci`, lint, TypeScript typecheck, Vite build); `backend-ci` (Python 3.13, pip, Ruff, 11 unit/API tests); `integration-ci` (PostgreSQL 17 service trên Runner port 5432, migration, `alembic check`, 6 PostgreSQL integration tests); `config-ci` (ShellCheck/Bash syntax, ba Compose config, actionlint và 9 test mô phỏng release-state).
- `docker-build` có `needs: [frontend-ci, backend-ci, integration-ci, config-ci]`. Matrix `component: [backend, frontend]` tạo hai nhánh build cùng job. Nó set image tag thành `ghcr.io/${github.repository_owner,,}/cicd-lab-2-${component}:${GITHUB_SHA}` (owner lowercase), Buildx `linux/amd64`, build arg `APP_VERSION=${{ github.sha }}`, OCI source/revision labels. PR và branch khác main chỉ build. Push `main` login GHCR bằng `github.actor` + `GITHUB_TOKEN` (`packages: write`) rồi push. Nếu `docker buildx imagetools inspect` thấy SHA tag đã có, nó skip build/push tag đó trên rerun.
- `deploy` có `needs: [docker-build]` và job `if` yêu cầu **push + `refs/heads/main` + `vars.DEPLOY_ENABLED == 'true'`**. Job dùng GitHub environment `production`, concurrency riêng, `cancel-in-progress: false`. Trước SSH, `gh api` so sánh `GITHUB_SHA` với HEAD hiện tại của main và skip run cũ. Nó kiểm tra định dạng SHA/host/user, tạo private key và known_hosts tạm, bật strict host-key checking, tar **chỉ** `compose.prod.yaml` cùng `scripts/`, chuyển tới `/opt/cicd-lab-2/releases/<SHA>/`, rồi SSH chạy `DEPLOY_DIR=/opt/cicd-lab-2 bash scripts/deploy.sh <SHA>`.
- Deploy phụ thuộc kết quả của **cả hai nhánh matrix** qua `needs: [docker-build]`; không có bước build source trên VPS. GitHub Actions thật chưa được chạy trên repo này vì chưa có remote/commit.

## 5. Dockerfiles và version

| Dockerfile | Stage và command |
|---|---|
| `frontend/Dockerfile` | `build`: Node 22 Alpine, `npm ci`, copy source, `ARG APP_VERSION` → `ENV VITE_APP_VERSION`, `npm run build`. `runtime`: Node 22 Alpine, chỉ copy `dist` và `server.mjs`, chạy user `node`, `CMD ["node","server.mjs"]` trên 8080, healthcheck GET `/` HTTP 200. Version frontend được **Vite nhúng lúc build**; đổi env runtime không sửa JS đã build. |
| `backend/Dockerfile` | `base`: Python 3.13 slim, pip install lockfile runtime, copy `app`, `alembic`, `alembic.ini`, tạo/chạy `appuser`. `test`: kế thừa base, cài dependency dev, copy test, CMD `alembic upgrade head && alembic check && pytest`. `runtime`: kế thừa base, `ARG APP_VERSION` → `ENV APP_VERSION`, CMD Uvicorn trên 8000, Docker healthcheck kiểm HTTP 200 và JSON `{"status":"ok"}`. API `/api/version` đọc `APP_VERSION`. |

Compose local build trên Docker của Mac. CI build trên GitHub Runner rồi push hai image AMD64 lên GHCR. Prod Compose chỉ pull/run image GHCR tag SHA; `APP_VERSION` backend và `VITE_APP_VERSION` frontend được truyền lúc CI build.

## 6. `scripts/deploy.sh` — đúng thứ tự lệnh

1. `source common.sh` nạp `.env.prod`, đường dẫn, hàm Compose/state. Đọc SHA tham số, `validate_sha` yêu cầu 40 ký tự hex thường, `export IMAGE_TAG`, lấy `flock`, `load_state`, đặt ERR trap in log khi lỗi.
2. `compose config --quiet` để kiểm cấu hình; `compose up -d --wait --wait-timeout 90 postgres` để có DB healthy. Lần deploy đầu là DB trống.
3. Gọi `bash scripts/backup-db.sh`: `pg_dump` trước migration. Nếu backup lỗi thì script dừng trước pull.
4. `compose pull backend frontend`: tải hai image của SHA ứng viên.
5. `compose run --rm --no-deps backend alembic upgrade head`: container tạm dùng **chính backend image ứng viên** để migrate, khi app cũ vẫn đang chạy nếu đây là lần deploy sau.
6. Nếu SHA khác `LAST_SUCCESSFUL_VERSION`, gán `PREVIOUS_VERSION=LAST_SUCCESSFUL_VERSION`. Gán `CURRENT_VERSION=<candidate>` và `save_state` **trước** khi thay app.
7. `compose up -d --no-build --no-deps backend frontend` để thay container, rồi gọi `check-health.sh <SHA>` và `smoke-test.sh <SHA>` nối tiếp.
8. Chỉ sau khi cả hai check pass mới gán `LAST_SUCCESSFUL_VERSION=<SHA>`, `save_state`, log `SUCCESS`. Lỗi migration không ghi candidate vào state; lỗi sau bước 6 giữ current=candidate nhưng last_successful vẫn là bản tốt cũ. ERR trap in `compose ps` và 80 dòng logs; không tự rollback.

## 7. Các script còn lại

| Script | Logic cụ thể |
|---|---|
| `common.sh` | `set -Eeuo pipefail`; xác định `SCRIPT_ROOT`, `DEPLOY_DIR`, `ENV_FILE` mặc định `$DEPLOY_DIR/.env.prod`, `COMPOSE_FILE` mặc định release `compose.prod.yaml`, project prod và `STATE_DIR`; `source` file env do operator sở hữu rồi export biến; wrapper `docker compose`; kiểm SHA; `flock -n` trên `deploy.lock`; load/ghi `versions.env` qua file tạm + `mv`; in ps/log khi ERR. |
| `backup-db.sh` | `umask 077`; tạo `$DEPLOY_DIR/backups/<UTC timestamp>.<random>.dump.partial`; `compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom`; kiểm file không rỗng và `pg_restore --list`; đổi tên thành `.dump`, trap xóa `.partial` nếu fail. Backup nằm trên filesystem VPS, không có retention/backup cloud. |
| `check-health.sh` | Nhận expected version, export `IMAGE_TAG`; trên VPS curl `127.0.0.1:${BACKEND_PORT:-8002}`. `get_200` đòi HTTP **200 đúng**; dùng Python trong backend container parse JSON health phải `{"status":"ok"}` và version phải bằng tham số. Mặc định tối đa 20 lần, cách nhau 3 giây; cuối cùng in 100 dòng backend log và fail. |
| `smoke-test.sh` | Nhận expected version; kiểm host GET frontend `/` trả 200, rồi `compose exec -T backend python -m app.smoke http://frontend:8080 "$expected"`. Module Python kiểm HTML root, health, version, POST quiz 201, POST question 201, GET quiz, rồi xóa quiz có title UUID `__smoke__...` trong `finally` bằng SQLAlchemy. |
| `rollback.sh` | Lấy lock/state. Nếu không truyền SHA: current khác last_successful thì chọn last_successful, ngược lại chọn previous; thiếu target thì fail. Validate target, pull hai image cũ, gán `CURRENT_VERSION=target` và lưu **trước** `compose up --no-build`; chạy lại health + smoke. Nếu pass, previous=`old_successful` khi khác target, nếu không thì xóa previous; gán last_successful=target, lưu state. **Không chạy Alembic downgrade hoặc restore DB**. |

`scripts/test-local.sh` chỉ dành cho test: `docker compose -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests`, `trap` dọn DB/container test bằng `down --volumes`.

## 8. Migration và DB URL

- `backend/alembic.ini`: `script_location=%(here)s/alembic`, `prepend_sys_path=.`. `alembic/env.py` import models để đăng ký metadata, dùng `Base.metadata`, gọi `database_url()`, cấu hình online engine `NullPool` và Alembic transaction; có nhánh offline.
- Revision `0001_initial.py` tạo `quizzes(id,title,created_at)` và `questions(id,quiz_id,question_text,option_a..d,correct_answer)`. FK `questions.quiz_id → quizzes.id` có `ON DELETE CASCADE`, có index và CHECK A/B/C/D. `downgrade()` drop index, questions, quizzes. App không gọi `Base.metadata.create_all()`.
- `app/database.py`: nếu có `DATABASE_URL`, chỉ chấp nhận prefix `postgresql+psycopg://`; không thì `URL.create` từ `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST` (mặc định `postgres`), `POSTGRES_PORT` (mặc định 5432). API dùng engine cached với `pool_pre_ping=True`, connect timeout 3 giây. Alembic gọi cùng hàm URL nhưng tạo engine `NullPool` riêng.
- Local: Compose backend command chạy migration trước Uvicorn. `compose.test.yaml`: Dockerfile test CMD migrate → check → pytest. CI integration job: `DATABASE_URL` tới PostgreSQL service `127.0.0.1:5432`, migration/check trước pytest. CD: `deploy.sh` chạy migration bằng backend image mới sau backup/pull và trước `compose up` app. Production runtime container không tự migrate.

## 9. Deployment state

File thực tế là `$DEPLOY_DIR/state/versions.env`; trên VPS theo workflow mặc định là `/opt/cicd-lab-2/state/versions.env`. Ba biến được đọc cùng nhau và ghi atomic qua `save_state`:

| Biến | Ý nghĩa và thời điểm ghi |
|---|---|
| `CURRENT_VERSION` | SHA ứng viên được yêu cầu chạy. Deploy ghi sau migration pass, **trước** `compose up`/health/smoke. Rollback cũng ghi target trước `compose up`. Nó có thể khác image đang thực sự healthy sau một lỗi; dùng `/api/version`/`compose images` để kiểm tra thực trạng. |
| `PREVIOUS_VERSION` | Khi deploy SHA mới, nhận `LAST_SUCCESSFUL_VERSION` cũ. Khi redeploy đúng SHA đã thành công, giữ nguyên. Sau rollback thành công, nhận `old_successful` nếu khác target, hoặc thành chuỗi rỗng để không đưa candidate lỗi thành rollback mặc định lần sau. |
| `LAST_SUCCESSFUL_VERSION` | Chỉ cập nhật sau khi **cả health và smoke** pass ở cuối deploy/rollback. Nếu một bước fail trước đó, nó giữ SHA tốt đã biết. |

Trước deploy đầu tiên file có thể chưa tồn tại; `load_state` khởi tạo cả ba biến rỗng. Khi first deploy lỗi sau khi đổi container, chưa có target rollback mặc định.

## 10. Env và secrets theo nơi

| Nơi | Biến và nguồn | Secret? |
|---|---|---|
| Mac local | `.env` do người học copy từ `.env.example`: `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `FRONTEND_PORT`, `BACKEND_PORT`, `APP_VERSION`; Compose truyền DB fields vào container, build arg version vào Dockerfile. | `POSTGRES_PASSWORD` là secret local; `.env` bị Git ignore. |
| GitHub Runner CI | `GITHUB_SHA`, `github.repository_owner`, `github.actor`; `integration-ci` có `DATABASE_URL`, `TEST_DATABASE_URL` và password literal **chỉ cho DB test tạm**. `config-ci` dùng giá trị validation tạm. Job publish dùng `GITHUB_TOKEN` với `packages: write`. | `GITHUB_TOKEN` là token tạm do GitHub cấp. Password DB test là fixture trong YAML, không phải password production. |
| GitHub CD config | Repository variable `DEPLOY_ENABLED`; variable `VPS_KNOWN_HOSTS` chứa public host key. Job lấy `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY` từ Secrets; `GH_TOKEN=github.token` chỉ dùng `gh api` kiểm main HEAD. | Ba trường `VPS_*` nêu trên được lưu dưới dạng GitHub Secrets; private key và GitHub token là credentials. `VPS_KNOWN_HOSTS` là public metadata. |
| VPS | `/opt/cicd-lab-2/.env.prod`: `GHCR_OWNER`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `FRONTEND_PORT`, `BACKEND_PORT`, `BIND_ADDRESS`. `deploy.sh`/`rollback.sh` export `IMAGE_TAG` từ SHA tham số/state. Compose inject DB fields vào backend/postgres và `BACKEND_URL` vào frontend. | `POSTGRES_PASSWORD` của VPS là secret ở file local quyền hạn chế. Nếu GHCR packages để private, VPS còn cần credential Docker login riêng để pull; script không chứa credential này. |

`APP_VERSION` của backend được bake vào image; frontend `VITE_APP_VERSION` là public build-time string trong JS. Prod Compose không ghi đè hai giá trị đó. Không có `.env` hoặc `.env.prod` thật trong repo hiện tại.

## 11. Kiểm chứng đã có và giới hạn

Theo `docs/VERIFICATION.md`, đã chạy: `npm ci`/frontend lint/typecheck/build; Ruff; 11 backend unit/API tests; 6 integration tests với PostgreSQL thật; `alembic upgrade head` và `alembic check`; 9 release-state tests; ShellCheck, actionlint và cả ba Compose config; Docker build ARM64 và AMD64; local startup/UI; HTTP 503 khi dừng DB; smoke/cleanup; backup/restore có dữ liệu sang DB riêng. Một registry loopback đã được dùng để chạy deploy v1 → v2 → v3 lỗi POST (health pass, smoke fail) → rollback v2 bằng script thật. Image ID của container sau rollback trùng với image đã push/pull trong registry local. Tài nguyên rehearsal đã được dọn. Có một warning deprecation từ Starlette TestClient, tests vẫn pass.

**Chỉ static-check hoặc mô phỏng:** workflow được actionlint kiểm tra nhưng chưa chạy trên GitHub-hosted Runner; GHCR authentication/visibility, SSH/scp và VPS Ubuntu thật chưa có kiểm chứng. Các nhánh lỗi backup/migration/health trong release-state tests dùng lệnh Docker giả; đường deploy/rollback và lỗi smoke đã được diễn tập local với Docker/PostgreSQL/HTTP thật. Registry local, image tag 40 ký tự giả và adapter `flock` trên Mac thay cho GHCR/Git SHA/Ubuntu VPS trong diễn tập. Repo chưa có commit/remote nên chưa có SHA production thật.

## 12. Mười điểm đáng chú ý khi review implementation

1. Migration CD chạy **trước** khi thay backend, trong lúc app cũ có thể vẫn phục vụ. Migration drop/rename cột app cũ đang dùng có thể làm app cũ hỏng ngay cả trước `compose up`.
2. `rollback.sh` chỉ đổi image; schema PostgreSQL giữ nguyên. Sau migration phá tương thích, image cũ có thể không chạy được.
3. `CURRENT_VERSION` là candidate đã ghi trước health/smoke, không phải chứng nhận image thực sự healthy. Khi xử lý lỗi cần kiểm thêm `/api/version` và `docker compose images`.
4. Sau rollback về `LAST_SUCCESSFUL_VERSION`, `PREVIOUS_VERSION` có thể rỗng. Rollback xa hơn cần chỉ định SHA tương thích bằng tay; first failed deployment cũng chưa có rollback mặc định.
5. SHA tag trên GHCR là tên tag có thể bị người có quyền thay đổi. Workflow skip publish nếu inspect thấy tag; nếu inspect lỗi mạng/auth, bước đó coi như tag chưa có và thử build/push. Production pull theo tag SHA, không pin digest.
6. CI build `platforms: linux/amd64` cố định. VPS ARM64 cần đổi cấu hình build; Mac ARM64 local build thành công không chứng minh VPS ARM64 pull được image CI.
7. Deploy bật bằng `DEPLOY_ENABLED=true` nhưng nếu GHCR package chưa public hoặc VPS chưa login package private, `compose pull` fail. Workflow chưa được chạy trên tài khoản GitHub thật.
8. `smoke-test.sh` tạo row trong DB production. `app.smoke` cleanup trong `finally`, nhưng container bị kill hoặc DB mất kết nối trong cleanup có thể để lại row `__smoke__...`.
9. `pg_dump` lưu backup cùng VPS và chỉ `pg_restore --list` trong script; đó chưa phải kiểm tra restore/khả năng sống sót nếu mất disk VPS. Script không tự giới hạn số backup, nên disk có thể đầy.
10. Production mặc định bind frontend/backend trên `0.0.0.0` cổng trực tiếp, app không có authentication/HTTPS. File `.env.prod` được **source như Bash** trong `common.sh`, nên chỉ operator tin cậy được phép sửa file này; shell syntax/password cần tương thích cả Bash lẫn Compose.

## 13. Nguyên văn các file cốt lõi

Các khối dưới đây được chép từ source của repo tại thời điểm tạo tài liệu; phần tóm tắt phía trên không thay thế chúng.

### `.github/workflows/ci-cd.yml`

SHA-256 source: `218ccabd43ade4953fe171b934ec8378758d11dcd6fc853361914dab104e8d00`

```yaml
name: CI and CD

on:
  push:
    branches: ['**']
  pull_request:

permissions:
  contents: read

# Do not cancel an SSH deployment halfway through a migration.
concurrency:
  group: cicd-lab-2-${{ github.ref }}
  cancel-in-progress: false

jobs:
  frontend-ci:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false
      - uses: actions/setup-node@v7
        with:
          node-version: '22'
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - run: npm run lint
      - run: npm run typecheck
      - run: npm run build

  backend-ci:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false
      - uses: actions/setup-python@v7
        with:
          python-version: '3.13'
          cache: pip
          cache-dependency-path: backend/requirements-dev.txt
      - run: pip install -r requirements-dev.txt
      - run: ruff check .
      - run: pytest tests/unit

  integration-ci:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:17-alpine
        env:
          POSTGRES_DB: quiz_test
          POSTGRES_USER: quiz_test
          POSTGRES_PASSWORD: test-only
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U quiz_test -d quiz_test"
          --health-interval 3s
          --health-timeout 3s
          --health-retries 20
    env:
      DATABASE_URL: postgresql+psycopg://quiz_test:test-only@127.0.0.1:5432/quiz_test
      TEST_DATABASE_URL: postgresql+psycopg://quiz_test:test-only@127.0.0.1:5432/quiz_test
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false
      - uses: actions/setup-python@v7
        with:
          python-version: '3.13'
          cache: pip
          cache-dependency-path: backend/requirements-dev.txt
      - run: pip install -r requirements-dev.txt
      - name: Apply real migrations to real PostgreSQL
        run: alembic upgrade head
      - name: Models must match migrated schema
        run: alembic check
      - run: pytest tests/integration

  config-ci:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false
      - name: Check shell scripts and Compose files
        env:
          POSTGRES_PASSWORD: disposable-ci-only
          POSTGRES_USER: quiz
          POSTGRES_DB: quiz_lab
          GHCR_OWNER: validation-only
          IMAGE_TAG: ${{ github.sha }}
        run: |
          shellcheck -x scripts/*.sh
          for script in scripts/*.sh; do bash -n "$script"; done
          docker compose -f compose.yaml config --quiet
          docker compose -f compose.prod.yaml config --quiet
          docker compose -f compose.test.yaml config --quiet
      - name: Check GitHub Actions syntax
        run: docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:1.7.7 -color
      - name: Check deployment failure and rollback state
        run: python3 -m unittest discover -s scripts/tests -v

  docker-build:
    needs: [frontend-ci, backend-ci, integration-ci, config-ci]
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    strategy:
      fail-fast: false
      matrix:
        component: [backend, frontend]
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false
      - name: Set lowercase GHCR image name
        id: image
        env:
          OWNER: ${{ github.repository_owner }}
          COMPONENT: ${{ matrix.component }}
        run: echo "tag=ghcr.io/${OWNER,,}/cicd-lab-2-${COMPONENT}:${GITHUB_SHA}" >> "$GITHUB_OUTPUT"
      - uses: docker/setup-buildx-action@v4
      - name: Log in to GHCR with the short-lived workflow token
        if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        uses: docker/login-action@v4
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Preserve a previously published SHA tag on workflow reruns
        id: existing
        if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        env:
          IMAGE: ${{ steps.image.outputs.tag }}
        run: |
          if docker buildx imagetools inspect "$IMAGE" > /dev/null 2>&1; then
            echo 'found=true' >> "$GITHUB_OUTPUT"
            echo "Reusing the image previously built by CI: $IMAGE"
          fi
      - name: Build image; publish only for a push to main
        if: steps.existing.outputs.found != 'true'
        uses: docker/build-push-action@v7
        with:
          context: ./${{ matrix.component }}
          platforms: linux/amd64
          push: ${{ github.event_name == 'push' && github.ref == 'refs/heads/main' }}
          tags: ${{ steps.image.outputs.tag }}
          build-args: APP_VERSION=${{ github.sha }}
          labels: |
            org.opencontainers.image.source=https://github.com/${{ github.repository }}
            org.opencontainers.image.revision=${{ github.sha }}
          cache-from: type=gha,scope=${{ matrix.component }}
          cache-to: type=gha,mode=max,scope=${{ matrix.component }}

  deploy:
    needs: [docker-build]
    if: github.event_name == 'push' && github.ref == 'refs/heads/main' && vars.DEPLOY_ENABLED == 'true'
    runs-on: ubuntu-latest
    timeout-minutes: 20
    environment: production
    concurrency:
      group: cicd-lab-2-production
      cancel-in-progress: false
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false
      - name: Skip a stale run if main has moved forward
        id: head
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          head_sha=$(gh api "repos/$GITHUB_REPOSITORY/git/ref/heads/main" --jq .object.sha)
          if [[ "$head_sha" == "$GITHUB_SHA" ]]; then
            echo 'deploy=true' >> "$GITHUB_OUTPUT"
          else
            echo "Skipping stale commit $GITHUB_SHA; main is $head_sha"
          fi
      - name: Send deployment scripts, then deploy the exact commit images
        if: steps.head.outputs.deploy == 'true'
        env:
          VPS_HOST: ${{ secrets.VPS_HOST }}
          VPS_USER: ${{ secrets.VPS_USER }}
          VPS_SSH_KEY: ${{ secrets.VPS_SSH_KEY }}
          VPS_KNOWN_HOSTS: ${{ vars.VPS_KNOWN_HOSTS }}
        run: |
          set -euo pipefail
          [[ "$GITHUB_SHA" =~ ^[0-9a-f]{40}$ ]]
          [[ "$VPS_HOST" =~ ^[a-zA-Z0-9.-]+$ ]]
          [[ "$VPS_USER" =~ ^[a-zA-Z_][a-zA-Z0-9_-]*$ ]]
          [[ -n "$VPS_SSH_KEY" && -n "$VPS_KNOWN_HOSTS" ]]
          ssh_dir=$(mktemp -d)
          trap 'rm -rf "$ssh_dir"' EXIT
          printf '%s\n' "$VPS_SSH_KEY" > "$ssh_dir/key"
          printf '%s\n' "$VPS_KNOWN_HOSTS" > "$ssh_dir/known_hosts"
          chmod 600 "$ssh_dir/key" "$ssh_dir/known_hosts"
          ssh_options=(-i "$ssh_dir/key" -o "UserKnownHostsFile=$ssh_dir/known_hosts" -o StrictHostKeyChecking=yes -o BatchMode=yes -o ConnectTimeout=10)
          destination="$VPS_USER@$VPS_HOST"
          release="/opt/cicd-lab-2/releases/$GITHUB_SHA"
          tar -czf "$ssh_dir/deploy.tgz" compose.prod.yaml scripts
          # These paths intentionally expand on the runner; SHA was validated above.
          # shellcheck disable=SC2029
          ssh "${ssh_options[@]}" "$destination" "mkdir -p '$release'"
          scp "${ssh_options[@]}" "$ssh_dir/deploy.tgz" "$destination:$release/deploy.tgz"
          # shellcheck disable=SC2029
          ssh "${ssh_options[@]}" "$destination" \
            "cd '$release' && tar -xzf deploy.tgz && DEPLOY_DIR=/opt/cicd-lab-2 bash scripts/deploy.sh '$GITHUB_SHA'"
```

### `compose.yaml`

SHA-256 source: `78fbfe97587da5e867908a798c032179e8a4108bd424956119c73a8dc55a53fd`

```yaml
name: cicd-lab-2-local

services:
  postgres:
    image: postgres:17-alpine
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-quiz_lab}
      POSTGRES_USER: ${POSTGRES_USER:-quiz}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env first}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: [CMD-SHELL, 'pg_isready -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"']
      interval: 3s
      timeout: 3s
      retries: 20

  backend:
    build:
      context: ./backend
      args:
        APP_VERSION: ${APP_VERSION:-local}
    environment:
      POSTGRES_HOST: postgres
      POSTGRES_DB: ${POSTGRES_DB:-quiz_lab}
      POSTGRES_USER: ${POSTGRES_USER:-quiz}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env first}
    # Local convenience only. Production runs migration explicitly in deploy.sh.
    command: [sh, -c, 'alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000']
    depends_on:
      postgres:
        condition: service_healthy
    ports:
      - '127.0.0.1:${BACKEND_PORT:-8002}:8000'

  frontend:
    build:
      context: ./frontend
      args:
        APP_VERSION: ${APP_VERSION:-local}
    environment:
      BACKEND_URL: http://backend:8000
    depends_on:
      backend:
        condition: service_healthy
    ports:
      - '127.0.0.1:${FRONTEND_PORT:-8082}:8080'

volumes:
  postgres_data:
```

### `compose.test.yaml`

SHA-256 source: `f11ac089cb06d1b1b19cad0043677e3875bcd4f3b5f77fc71191172f461bae04`

```yaml
name: cicd-lab-2-test

services:
  postgres:
    image: postgres:17-alpine
    environment:
      POSTGRES_DB: quiz_test
      POSTGRES_USER: quiz_test
      # Disposable test database, no published port and no production data.
      POSTGRES_PASSWORD: test-only
    tmpfs:
      - /var/lib/postgresql/data
    healthcheck:
      test: [CMD-SHELL, 'pg_isready -U quiz_test -d quiz_test']
      interval: 2s
      timeout: 3s
      retries: 30
  tests:
    build:
      context: ./backend
      target: test
    environment:
      DATABASE_URL: postgresql+psycopg://quiz_test:test-only@postgres:5432/quiz_test
      TEST_DATABASE_URL: postgresql+psycopg://quiz_test:test-only@postgres:5432/quiz_test
    depends_on:
      postgres:
        condition: service_healthy
```

### `compose.prod.yaml`

SHA-256 source: `2e5e8cd47c54baab6f049362bc8c2f80307039ea6cecda3168b7d32d427bc785`

```yaml
name: cicd-lab-2-prod

# No build: on the VPS. IMAGE_TAG is the full commit SHA passed by deploy.sh.
services:
  postgres:
    image: postgres:17-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB:?Set POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER:?Set POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: [CMD-SHELL, 'pg_isready -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"']
      interval: 3s
      timeout: 3s
      retries: 20

  backend:
    image: ghcr.io/${GHCR_OWNER:?Set GHCR_OWNER}/cicd-lab-2-backend:${IMAGE_TAG:?Pass a commit SHA}
    restart: unless-stopped
    environment:
      POSTGRES_HOST: postgres
      POSTGRES_DB: ${POSTGRES_DB:?Set POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER:?Set POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD}
    depends_on:
      postgres:
        condition: service_healthy
    ports:
      - '${BIND_ADDRESS:-0.0.0.0}:${BACKEND_PORT:-8002}:8000'

  frontend:
    image: ghcr.io/${GHCR_OWNER:?Set GHCR_OWNER}/cicd-lab-2-frontend:${IMAGE_TAG:?Pass a commit SHA}
    restart: unless-stopped
    environment:
      BACKEND_URL: http://backend:8000
    depends_on:
      backend:
        # deploy.sh owns the explicit health retry and failure logging.
        condition: service_started
    ports:
      - '${BIND_ADDRESS:-0.0.0.0}:${FRONTEND_PORT:-8082}:8080'

volumes:
  postgres_data:
```

### `backend/Dockerfile`

SHA-256 source: `764206d3c7e6fdf6778dfec8adf627ef8c93bb67bdd3398c96b79e90017e5797`

```dockerfile
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home appuser
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
USER appuser

FROM base AS test
ENV PYTEST_ADDOPTS="-o cache_dir=/tmp/pytest-cache" RUFF_CACHE_DIR=/tmp/ruff-cache
USER root
COPY requirements-dev.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY tests ./tests
USER appuser
CMD ["sh", "-c", "alembic upgrade head && alembic check && pytest"]

FROM base AS runtime
ARG APP_VERSION=local
ENV APP_VERSION=${APP_VERSION}
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=6 \
    CMD python -c "import json,urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4); assert r.status == 200 and json.load(r) == {'status':'ok'}"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### `frontend/Dockerfile`

SHA-256 source: `6919c928d4a72a998afc7932a21b2333d8bc1c5d4207173e55176cf634787487`

```dockerfile
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG APP_VERSION=local
ENV VITE_APP_VERSION=${APP_VERSION}
RUN npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
COPY --from=build --chown=node:node /app/dist ./dist
COPY --chown=node:node server.mjs ./
USER node
ENV BACKEND_URL=http://backend:8000
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=6 \
    CMD node -e "fetch('http://127.0.0.1:8080/').then(r => process.exit(r.status === 200 ? 0 : 1)).catch(() => process.exit(1))"
CMD ["node", "server.mjs"]
```

### `scripts/deploy.sh`

SHA-256 source: `28c9a136606010f6f63548356c35ff1bab744dee6cc78ff6d987245e7434b884`

```bash
#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
set -Eeuo pipefail
# shellcheck source=common.sh
source "$(dirname "$0")/common.sh"
version=${1:?Usage: deploy.sh FULL_COMMIT_SHA}
validate_sha "$version"
export IMAGE_TAG=$version
lock_deployment
load_state
trap on_failure ERR

log "Deploy candidate: $version"
compose config --quiet
# First deploy initializes an empty DB; subsequent deploys keep the same volume.
compose up -d --wait --wait-timeout 90 postgres
bash "$SCRIPT_ROOT/scripts/backup-db.sh"
log 'Pulling the two images built by CI.'
compose pull backend frontend
log 'Migrating with the candidate backend image; old app is still running.'
compose run --rm --no-deps backend alembic upgrade head

# Record the candidate before replacing containers. If startup/health/smoke fails,
# rollback still knows the last version that passed all checks.
if [[ "$version" != "$LAST_SUCCESSFUL_VERSION" ]]; then
  PREVIOUS_VERSION=$LAST_SUCCESSFUL_VERSION
fi
CURRENT_VERSION=$version
save_state
compose up -d --no-build --no-deps backend frontend
bash "$SCRIPT_ROOT/scripts/check-health.sh" "$version"
bash "$SCRIPT_ROOT/scripts/smoke-test.sh" "$version"
LAST_SUCCESSFUL_VERSION=$version
save_state
log "SUCCESS: deployed $version"
```

### `scripts/common.sh`

SHA-256 source: `d29addcf77ffb1e746fc4b324731ad6d16373f56d73900510848de25b1920842`

```bash
#!/usr/bin/env bash
# Shared helpers. This file is sourced, never run by itself.
set -Eeuo pipefail

SCRIPT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
DEPLOY_DIR=${DEPLOY_DIR:-$SCRIPT_ROOT}
ENV_FILE=${ENV_FILE:-$DEPLOY_DIR/.env.prod}
COMPOSE_FILE=${COMPOSE_FILE:-$SCRIPT_ROOT/compose.prod.yaml}
COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME:-cicd-lab-2-prod}
STATE_DIR=$DEPLOY_DIR/state

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
log() { printf '[%s] %s\n' "$(date -u +%FT%TZ)" "$*"; }
[[ -f "$ENV_FILE" ]] || die "Missing $ENV_FILE; copy and configure the example first."
# Both Compose and Bash read this trusted, operator-owned file. Never download it.
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

compose() {
  docker compose --project-name "$COMPOSE_PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

validate_sha() { [[ "$1" =~ ^[0-9a-f]{40}$ ]] || die "Expected a full 40-character lowercase commit SHA: $1"; }

lock_deployment() {
  mkdir -p "$STATE_DIR"
  exec 9>"$DEPLOY_DIR/deploy.lock"
  flock -n 9 || die 'Another deploy/rollback is running.'
}

load_state() {
  CURRENT_VERSION='' PREVIOUS_VERSION='' LAST_SUCCESSFUL_VERSION=''
  if [[ -f "$STATE_DIR/versions.env" ]]; then
    while IFS='=' read -r key value; do
      [[ -z "$value" ]] || validate_sha "$value"
      case "$key" in
        CURRENT_VERSION) CURRENT_VERSION=$value ;;
        PREVIOUS_VERSION) PREVIOUS_VERSION=$value ;;
        LAST_SUCCESSFUL_VERSION) LAST_SUCCESSFUL_VERSION=$value ;;
        *) die "Unknown state key: $key" ;;
      esac
    done < "$STATE_DIR/versions.env"
  fi
}

save_state() {
  local temporary
  temporary=$(mktemp "$STATE_DIR/.versions.XXXXXX")
  printf 'CURRENT_VERSION=%s\nPREVIOUS_VERSION=%s\nLAST_SUCCESSFUL_VERSION=%s\n' \
    "$CURRENT_VERSION" "$PREVIOUS_VERSION" "$LAST_SUCCESSFUL_VERSION" > "$temporary"
  mv "$temporary" "$STATE_DIR/versions.env"
}

failure_logs() {
  log 'Deployment failed. Inspect /api/version and state/versions.env before recovery.'
  compose ps || true
  compose logs --tail=80 backend frontend postgres || true
}

on_failure() {
  local code=$?
  trap - ERR
  failure_logs
  exit "$code"
}
```

### `scripts/rollback.sh`

SHA-256 source: `43670153789d3fdaeba29918225f80cd46f8488628954c1a29842fbe25c3ac42`

```bash
#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
set -Eeuo pipefail
# shellcheck source=common.sh
source "$(dirname "$0")/common.sh"
lock_deployment
load_state
target=${1:-}
if [[ -z "$target" ]]; then
  if [[ "$CURRENT_VERSION" != "$LAST_SUCCESSFUL_VERSION" && -n "$LAST_SUCCESSFUL_VERSION" ]]; then
    target=$LAST_SUCCESSFUL_VERSION
  else
    target=$PREVIOUS_VERSION
  fi
fi
[[ -n "$target" ]] || die 'No previous successful image. Supply a known compatible SHA or fix forward.'
validate_sha "$target"
[[ "$target" != "$CURRENT_VERSION" ]] || die 'Target is already CURRENT_VERSION.'
export IMAGE_TAG=$target
trap on_failure ERR
log "Rolling back images to $target. Database schema will stay unchanged."
compose pull backend frontend
old_successful=$LAST_SUCCESSFUL_VERSION
CURRENT_VERSION=$target
save_state
compose up -d --no-build --no-deps backend frontend
bash "$SCRIPT_ROOT/scripts/check-health.sh" "$target"
bash "$SCRIPT_ROOT/scripts/smoke-test.sh" "$target"
# Never make a failed candidate the default target of a later rollback.
if [[ "$old_successful" != "$target" ]]; then
  PREVIOUS_VERSION=$old_successful
else
  PREVIOUS_VERSION=
fi
LAST_SUCCESSFUL_VERSION=$target
save_state
log "SUCCESS: image rollback to $target (no Alembic downgrade)."
```

### `scripts/backup-db.sh`

SHA-256 source: `d625e1cb972490695b70b1aafd2122e1c7317af7378e306920d8440e57fde87e`

```bash
#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
set -Eeuo pipefail
# shellcheck source=common.sh
source "$(dirname "$0")/common.sh"
umask 077
mkdir -p "$DEPLOY_DIR/backups"
temporary=$(mktemp "$DEPLOY_DIR/backups/$(date -u +%Y%m%dT%H%M%SZ).XXXXXX")
backup=$temporary.dump
trap 'rm -f "$backup.partial"' EXIT
mv "$temporary" "$backup.partial"
log 'Creating PostgreSQL backup before migration.'
compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom > "$backup.partial"
[[ -s "$backup.partial" ]] || die 'pg_dump produced an empty backup.'
compose exec -T postgres pg_restore --list < "$backup.partial" > /dev/null
mv "$backup.partial" "$backup"
log "Backup saved: $backup"
```

### `scripts/check-health.sh`

SHA-256 source: `6460fe8b3a02ab24021c12eaf404038ecb3a5a11f38fbe2260a49ba2d4fa48a8`

```bash
#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
set -Eeuo pipefail
# shellcheck source=common.sh
source "$(dirname "$0")/common.sh"
expected=${1:?Usage: check-health.sh EXPECTED_VERSION}
export IMAGE_TAG=$expected
url=http://127.0.0.1:${BACKEND_PORT:-8002}
attempts=${HEALTH_ATTEMPTS:-20}
delay=${HEALTH_DELAY:-3}
get_200() {
  local response status
  response=$(curl --silent --show-error --max-time 5 --write-out '\n%{http_code}' "$1") || return 1
  status=${response##*$'\n'}
  [[ "$status" == 200 ]] || { printf 'Expected HTTP 200, got %s\n' "$status" >&2; return 1; }
  printf '%s' "${response%$'\n'*}"
}
for ((attempt=1; attempt<=attempts; attempt++)); do
  if body=$(get_200 "$url/api/health") \
    && printf '%s' "$body" | compose exec -T backend python -c \
      'import json,sys; assert json.load(sys.stdin) == {"status":"ok"}' \
    && body=$(get_200 "$url/api/version") \
    && printf '%s' "$body" | compose exec -T backend python -c \
      'import json,sys; assert json.load(sys.stdin) == {"version":sys.argv[1]}' "$expected"; then
    log "Health and version passed: $expected"
    exit 0
  fi
  log "Health/version attempt $attempt/$attempts failed."
  sleep "$delay"
done
compose logs --tail=100 backend || true
die "Health/version did not pass for $expected"
```

### `scripts/smoke-test.sh`

SHA-256 source: `28657d651d53971e1b2f7602943c26a6b7ae436ebacc361de6d84bf68716231d`

```bash
#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
set -Eeuo pipefail
# shellcheck source=common.sh
source "$(dirname "$0")/common.sh"
expected=${1:?Usage: smoke-test.sh EXPECTED_VERSION}
export IMAGE_TAG=$expected
# Host port check, then real HTTP operations through the Docker service network.
status=$(curl --fail --silent --show-error --retry 5 --retry-connrefused --max-time 10 \
  --output /dev/null --write-out '%{http_code}' "http://127.0.0.1:${FRONTEND_PORT:-8082}/")
[[ "$status" == 200 ]] || die "Frontend returned HTTP $status, expected 200."
compose exec -T backend python -m app.smoke http://frontend:8080 "$expected"
```
