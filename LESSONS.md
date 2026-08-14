# Lessons: dbt + Docker Compose

Tổng hợp các lỗi thực tế đã gặp trong dự án này (`elt/`) và kiến thức nền liên quan, để tra cứu lại khi cần.

---

## 1. Docker Compose — `depends_on` và các `condition`

`depends_on` mặc định chỉ đảm bảo **thứ tự khởi động container**, không đảm bảo service bên trong đã sẵn sàng. Compose Specification hỗ trợ 3 điều kiện:

| Condition | Chờ đến khi nào | Yêu cầu |
|---|---|---|
| `service_started` (mặc định) | Process trong container đã bắt đầu chạy | Không cần gì |
| `service_healthy` | Container báo trạng thái `healthy` | Service phải khai `healthcheck:` |
| `service_completed_successfully` | Container **chạy xong và thoát với exit code 0** | Dùng cho job "chạy một lần rồi thoát" (migration, seed, init script...) |

### Cú pháp rút gọn (list) = luôn là `service_started`

```yaml
elt_script:
  depends_on:
    - source
    - destination
```

Tương đương:

```yaml
elt_script:
  depends_on:
    source:
      condition: service_started
    destination:
      condition: service_started
```

### Cú pháp đầy đủ (map) — bắt buộc khi cần condition khác mặc định

```yaml
dbt:
  depends_on:
    elt_script:
      condition: service_completed_successfully
```

**Lỗi thực tế đã gặp:** ban đầu `dbt` dùng `depends_on: - elt_script` (dạng list → `service_started`). `elt_script` là container chạy dump + load rồi thoát; với `service_started`, Compose chỉ chờ container này **bắt đầu chạy** chứ không chờ nó **chạy xong**, nên `dbt run` có thể khởi động và đọc dữ liệu trước khi `elt_script` load xong vào `destination_db`. Sửa bằng cách đổi sang dạng map + `condition: service_completed_successfully`.

### Vì sao `source`/`destination` không dùng `service_healthy`?

Image `postgres` chính thức **không khai `HEALTHCHECK` sẵn**, nên `service_healthy` không dùng được trừ khi tự thêm:

```yaml
source:
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U postgres"]
    interval: 5s
    timeout: 3s
    retries: 5
```

Trong dự án này, thay vì thêm healthcheck, `elt_script.py` tự poll bằng `pg_isready` trong Python (`wait_for_postgres()`) — cách này vẫn đúng, chỉ là logic readiness nằm trong code thay vì trong compose file.

### `--exit-code-from` ngầm bật `--abort-on-container-exit`

Khi test thủ công bằng `docker compose up --exit-code-from dbt`, Compose sẽ **dừng toàn bộ stack ngay khi BẤT KỲ container nào thoát** — kể cả `elt_script` thoát bình thường (exit 0) cũng kích hoạt "Aborting on container exit...", có thể giết `dbt` giữa chừng do race condition. Đây không phải lỗi của file compose, mà là hệ quả của flag test. Muốn chạy nền an toàn: dùng `docker compose up -d` (không kèm `--exit-code-from`), rồi xem log riêng bằng `docker compose logs <service>`.

---

## 2. Docker Compose — các lỗi khác đã gặp

### Volume dữ liệu sống sót qua `down` (không có `-v`) và qua `--build`

- `docker compose down` chỉ xoá **container**, không xoá **volume** (kể cả volume ẩn danh của service) — dữ liệu Postgres vẫn còn khi container mới được tạo lại.
- `--build` chỉ rebuild **image**, không đụng tới volume.
- Postgres image chỉ chạy script trong `/docker-entrypoint-initdb.d/` **một lần duy nhất**, lúc data directory (PGDATA) còn rỗng. Nếu volume cũ còn dữ liệu, sửa `init.sql` xong mà không xoá volume thì script vẫn **không được chạy lại**.

→ Muốn ép Postgres khởi tạo lại từ đầu: `docker compose down -v`.

### Path init script gõ sai: `initdb.a` thay vì `initdb.d`

```yaml
# Sai — Postgres không nhận ra thư mục này, script không bao giờ chạy
- ./source_db_init/init.sql:/docker-entrypoint-initdb.a/init.sql

# Đúng
- ./source_db_init/init.sql:/docker-entrypoint-initdb.d/init.sql
```

Lỗi này im lặng — container vẫn start bình thường, chỉ là database rỗng, không có bảng nào.

### Ghim version image thay vì dùng `latest`

`postgres:latest` từng là Postgres 18 trong khi `postgresql-client` cài qua `apt-get` trên `python:3.8-slim` (Debian bookworm) chỉ là bản 15. `pg_dump` **từ chối dump từ server mới hơn chính nó**:

```
pg_dump: error: aborting because of server version mismatch
```

→ Ghim `postgres:15` để khớp version client, hoặc cài `pg_dump` mới hơn trong Dockerfile của `elt_script`.

### Biến môi trường override CLI flag một cách âm thầm

```yaml
dbt:
  environment:
    DBT_PROFILE: default   # sai — không tồn tại profile "default"
```

dbt map mỗi CLI flag global sang một biến môi trường `DBT_<TÊN_FLAG>` (đây là hành vi của Click-based CLI). `DBT_PROFILE` tương đương flag `--profile`, sẽ **ghi đè** `profile:` khai trong `dbt_project.yml`. Nếu giá trị không khớp tên profile trong `profiles.yml` → `Could not find profile named 'default'`.

→ Kiểm tra: tên profile trong `dbt_project.yml` (`profile: 'first_dbt'`), `profiles.yml` (key gốc `first_dbt:`), và mọi biến `DBT_PROFILE`/flag `--profile` phải khớp nhau tuyệt đối.

### `version:` ở đầu file compose

`version : '3'` đã obsolete từ lâu (Compose Specification không cần khai version nữa) — Compose sẽ cảnh báo và bỏ qua nó. Nên xoá hẳn dòng này, vừa hết cảnh báo vừa tránh giới hạn schema cũ (ví dụ một số cú pháp `depends_on` mở rộng cần Compose Specification mới nhất).

---

## 3. dbt — các lỗi đã gặp

### Model KHÔNG được kết thúc bằng dấu `;`

```sql
-- Sai
SELECT * FROM {{ source('destination_db', 'films') }};

-- Đúng
SELECT * FROM {{ source('destination_db', 'films') }}
```

dbt tự bọc nội dung model trong DDL của riêng nó, kiểu:

```sql
create table "destination_db"."public"."films__dbt_tmp" as (
    SELECT * FROM "destination_db"."public"."films";   -- dấu ; ở đây làm vỡ câu lệnh
)
```

Lỗi hiện ra là `syntax error at or near ";"` — dễ nhầm là lỗi cú pháp SQL thông thường, nhưng thực chất là do dấu `;` thừa bên trong dấu ngoặc `(...)`.

### Postgres: `"chuỗi"` (nháy kép) là identifier, không phải string literal

```sql
-- Sai — Postgres hiểu là tên cột/bảng "Excellent", sẽ báo column does not exist
CASE WHEN user_rating >= 4.5 THEN "Excellent" ELSE "Poor" END

-- Đúng — chuỗi ký tự phải dùng nháy đơn
CASE WHEN user_rating >= 4.5 THEN 'Excellent' ELSE 'Poor' END
```

Đây là khác biệt chuẩn ANSI SQL của Postgres (khác MySQL, nơi nháy kép thường được chấp nhận như chuỗi).

### `ref()`/`source()` phải khớp chính xác tên file / tên bảng khai trong `sources.yml`

```sql
-- Sai — file thực tế tên là film_actors.sql, không phải films_actors
LEFT JOIN {{ ref('films_actors') }} as fa
```

dbt không tự đoán/gợi ý tên gần đúng — sai một ký tự là lỗi "model không tồn tại" (hoặc parse error tuỳ phiên bản).

### `sources.yml` phải đúng cú pháp `version: 2`

```yaml
# Sai — "version 2" trở thành một key lạ, value null
version 2 : 

# Đúng
version: 2
```

### Model trùng tên với source table trong cùng schema — dễ mất constraint khi rerun loader

Trong dự án này, model `actors.sql` build ra bảng `public.actors` — **trùng tên** với bảng nguồn `public.actors` mà `elt_script` đã load (cùng `destination_db`, cùng schema `public`, vì `profiles.yml` không đặt custom schema/alias). `dbt run` tự xử lý được (build bảng tạm rồi swap tên), nhưng:

- `CREATE TABLE ... AS SELECT * FROM ...` **không copy PRIMARY KEY/constraint** từ bảng gốc.
- Nếu sau đó chạy lại `elt_script` (load lại dữ liệu từ `source_db`) trên bảng đã bị `dbt run` thay thế, sẽ **không còn PK để chặn trùng khoá** → dữ liệu bị nhân đôi âm thầm, các test `unique` trong dbt sẽ fail hàng loạt mà không có lỗi rõ ràng nào ở bước load.

→ Quy tắc an toàn: **không chạy lại `elt_script` sau khi `dbt run` đã chạy** trên cùng một volume. Muốn chạy lại từ đầu, luôn `docker compose down -v` trước.

### Profile phải khớp giữa 3 nơi

`dbt_project.yml` (`profile: 'first_dbt'`) ↔ `profiles.yml` (key gốc `first_dbt:`) ↔ biến môi trường/flag `DBT_PROFILE`/`--profile` (nếu có set) — cả ba phải trùng tên tuyệt đối, dbt không tự suy luận hay cảnh báo gợi ý khi lệch.

---

## 4. Checklist nhanh khi debug pipeline này

1. `docker compose logs <service>` để xem log thật, đừng đoán từ traceback ngắn gọn.
2. Nghi ngờ dữ liệu cũ/stale → `docker compose down -v` rồi `up` lại từ đầu.
3. Test lệnh `dbt` đơn lẻ mà không muốn kích hoạt lại `elt_script`: thêm `--no-deps`.
   ```bash
   docker compose run --rm --no-deps dbt test --profiles-dir /root --project-dir /dbt
   ```
4. Trên Windows + Git Bash, path kiểu `/root` bị MSYS tự dịch thành `C:/Program Files/Git/root`. Thêm `MSYS_NO_PATHCONV=1` trước lệnh `docker compose run ...` nếu gặp lỗi `Path '...' does not exist` với path bắt đầu bằng `/`.
