# ClinicCare — Quản lý phòng khám

Ứng dụng quản lý bệnh nhân, bác sĩ và lịch khám được triển khai bằng Flask,
PostgreSQL, Docker Compose và Nginx. Bộ giám sát gồm Prometheus, Grafana,
Loki, Promtail, cAdvisor, Node Exporter và PostgreSQL Exporter.

## Truy cập nhanh và tài khoản dịch vụ

| Dịch vụ | Địa chỉ | Tài khoản | Mật khẩu |
| --- | --- | --- | --- |
| Website ClinicCare | <http://localhost:8082/login> | Tài khoản nhân viên được Admin cấp | Mật khẩu riêng của từng người dùng |
| pgAdmin | <http://localhost:5050> | Giá trị `PGADMIN_DEFAULT_EMAIL` trong `.env` | Giá trị `PGADMIN_DEFAULT_PASSWORD` trong `.env` |
| Grafana | <http://localhost:3000> | `admin` | Giá trị `GRAFANA_ADMIN_PASSWORD` trong `.env` |
| Prometheus | <http://localhost:9090> | Không yêu cầu đăng nhập | Không áp dụng |
| PostgreSQL (đăng ký trong pgAdmin) | Host `db`, port `5432` | `clinic_runtime` (database `clinicdb`) | Giá trị `APP_DB_PASSWORD` trong `.env` |

Thông tin đăng nhập pgAdmin và PostgreSQL là hai bộ thông tin riêng. pgAdmin
dùng `PGADMIN_DEFAULT_EMAIL`/`PGADMIN_DEFAULT_PASSWORD` để đăng nhập giao diện;
kết nối database dùng `APP_DB_USER`/`APP_DB_PASSWORD`. Không ghi mật khẩu thật
vào README, ảnh chụp hoặc Git.

Để kiểm tra hoặc cập nhật thông tin đăng nhập trên máy này, mở `.env`. Nếu
muốn xem các biến mật khẩu còn lại trong PowerShell, chạy lệnh sau từ thư mục
dự án; đừng chụp/chia sẻ đầu ra:

```powershell
$keys = 'PGADMIN_DEFAULT_EMAIL','PGADMIN_DEFAULT_PASSWORD','GRAFANA_ADMIN_USER','GRAFANA_ADMIN_PASSWORD','APP_DB_USER','APP_DB_PASSWORD','POSTGRES_DB'
Get-Content .env | ForEach-Object {
    if ($_ -match '^([^#=]+)=(.*)$' -and $keys -contains $matches[1]) {
        if ($matches[1] -like '*PASSWORD') { '{0}=<đã cấu hình>' -f $matches[1] }
        else { '{0}={1}' -f $matches[1], $matches[2] }
    }
}
```

Không gửi hoặc chụp lại đầu ra có mật khẩu. Website yêu cầu đăng nhập bằng tài
khoản ClinicCare; tạo Admin đầu tiên theo hướng dẫn bên dưới sau khi chạy
migration.

> Mật khẩu và khóa bí mật chỉ được lưu trong `.env` tại máy chạy dự án.
> Không đưa `.env` vào Git, ảnh chụp báo cáo hoặc nội dung gửi công khai.

### LogQL nhanh

Mở Grafana tại <http://localhost:3000>, chọn **Explore** rồi datasource
**Loki**. Dán từng truy vấn vào ô query và nhấn **Run query**:

```logql
{service_name="nginx"}
```

```logql
{service_name="app"} |~ "(?i)error|exception|traceback"
```

```logql
{service_name="db"} |~ "(?i)error|fatal|panic"
```

Truy vấn lỗi chỉ hiện dòng khớp; không có kết quả không có nghĩa là truy vấn
bị lỗi. Xem phần **Loki và LogQL** bên dưới để biết thêm về labels và log.

## Checklist demo theo yêu cầu

Toàn bộ ứng dụng và các dịch vụ phụ trợ được triển khai bằng Docker Compose.
Từ thư mục dự án, kiểm tra cấu hình và khởi động stack:

```powershell
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

Trong buổi demo, lần lượt trình bày:

1. **Website:** đăng nhập bằng tài khoản ClinicCare tại <http://localhost:8082>
   và giới thiệu các trang được phép theo vai trò.
2. **Database tool:** đăng nhập pgAdmin tại <http://localhost:5050>, mở server
   PostgreSQL và cho thấy database `clinicdb` cùng dữ liệu ứng dụng.
3. **Grafana:** mở <http://localhost:3000>, vào dashboard **ClinicCare -
   Overview** và giới thiệu metrics của ứng dụng, database, Nginx và hệ thống.
4. **LogQL:** vào **Explore → Loki**, chạy ba truy vấn trong phần
   **LogQL nhanh** ở phía trên README.
5. **Hardening:** chỉ ra các cấu hình non-root, read-only filesystem,
   `no-new-privileges`, giới hạn capabilities, network tách biệt, secrets trong
   `.env` và security headers. Website hiện chạy HTTP trên localhost; HTTPS
   chưa được cấu hình. Xem thêm phần **Hardening và giới hạn đã biết**.

Thư mục [`evidence/`](evidence/) lưu ảnh minh chứng. Trước khi chụp hoặc chia sẻ,
kiểm tra ảnh không để lộ mật khẩu, nội dung `.env` hay dữ liệu cá nhân.

## Kiến trúc

```mermaid
flowchart LR
  Browser -->|localhost:8082| Nginx
  Nginx --> Flask
  Flask --> PostgreSQL
  PgAdmin --> PostgreSQL
  Prometheus --> Flask
  Prometheus --> PostgreSQLExporter
  Prometheus --> cAdvisor
  Prometheus --> NodeExporter
  Grafana --> Prometheus
  Grafana --> Loki
  Promtail -->|Docker logs| Loki
```

- `frontend` nối Nginx với Flask; `backend` nối Flask, PostgreSQL, pgAdmin,
  PostgreSQL Exporter và Prometheus. PostgreSQL không publish cổng ra host.
- `monitoring` nối Prometheus, Grafana, Loki, Promtail và exporters.
- `host_access` là network bridge cho các giao diện cần publish; các cổng chỉ
  bind vào `127.0.0.1`. Network này cho phép outbound qua Docker bridge.
- PostgreSQL, pgAdmin, Prometheus, Grafana và Loki dùng named volumes để giữ
  dữ liệu khi container được thay mới. Không dùng `docker compose down -v`.
- Flask chạy bằng Gunicorn với user không đặc quyền. Nginx thêm các security
  headers cho website.

## Cây thư mục

```text
clinic-management/
├── .env.example
├── .gitattributes
├── .gitignore
├── docker-compose.yml
├── README.md
├── app/
│   ├── app.py
│   ├── database.py
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── static/
│   │   ├── cliniccare.css
│   │   ├── cliniccare.js
│   │   └── confirm-delete.js
│   └── templates/
│       ├── appointments.html
│       ├── base.html
│       ├── dashboard.html
│       ├── doctors.html
│       └── patients.html
├── database/
│   ├── init.sql
│   └── 02-create-runtime-roles.sql
├── evidence/
│   ├── 01-github-repository.png
│   ├── 02-github-commit-history.png
│   ├── 03-cliniccare-dashboard.png
│   ├── 04-docker-compose-logs.png
│   ├── 05-postgres-appointments-redacted.png
│   ├── 06-nginx-proxy-headers.png
│   ├── 07-http-response-headers.png
│   ├── 08-cliniccare-devtools.png
│   ├── 09-prometheus-targets.png
│   ├── 10-grafana-overview.png
│   ├── 11-grafana-prometheus-datasource.png
│   ├── 12-grafana-cpu-alert-rule.png
│   ├── 13-loki-explore-app.png
│   ├── 14-postgres-exporter-error-redacted.png
│   ├── 15-loki-nginx-logs.png
│   ├── 16-compose-hardening-grafana.png
│   ├── 17-docker-networks.png
│   └── 18-app-nonroot-user.png
├── nginx/
│   └── nginx.conf
└── monitoring/
    ├── alerts.yml
    ├── loki-config.yml
    ├── prometheus.yml
    ├── promtail-config.yml
    └── grafana/
        ├── dashboards/clinic-management.json
        └── provisioning/
            ├── dashboards/dashboards.yml
            └── datasources/datasources.yml
```

## Giao diện ClinicCare

- **Tổng quan** (`/dashboard`): tổng số bệnh nhân, bác sĩ, lịch khám, lịch
  trong ngày; biểu đồ 7 ngày và thống kê trạng thái được truy vấn từ
  PostgreSQL.
- **Bệnh nhân** (`/patients`) và **Bác sĩ** (`/doctors`): thêm, tìm kiếm,
  phân trang, sửa trong hộp thoại và xóa có xác nhận; dữ liệu vẫn dùng các
  bảng hiện có.
- **Lịch khám** (`/appointments`): tạo lịch, xem/sửa chi tiết, tìm kiếm,
  phân trang và cập nhật trạng thái.
- Bố cục co giãn trên desktop/điện thoại; stylesheet và JavaScript được phục
  vụ từ `app/static/`, không thêm thư viện frontend hoặc thay framework Flask.

## Dịch vụ và địa chỉ

| Dịch vụ | Địa chỉ từ máy chủ | Vai trò |
| --- | --- | --- |
| ClinicCare qua Nginx | <http://localhost:8082> | Website bệnh nhân, bác sĩ, lịch khám |
| pgAdmin | <http://localhost:5050> | Giao diện quản trị PostgreSQL |
| Prometheus | <http://localhost:9090> | Metrics, scrape targets và cảnh báo |
| Grafana | <http://localhost:3000> | Dashboard và truy vấn metrics/logs |
| Loki API | <http://localhost:3100/ready> | API lưu trữ log |
| Flask trực tiếp | Không publish | Chỉ truy cập nội bộ qua Nginx/Prometheus |
| PostgreSQL | Không publish | Chỉ truy cập qua network `backend` |
| Exporters | Không publish | Nginx, PostgreSQL, host và container metrics; Prometheus truy cập trên network nội bộ |

Các cổng host chỉ bind vào loopback (`127.0.0.1`), không chủ ý mở ra mạng LAN.

### Thông tin đăng nhập

- pgAdmin: dùng `PGADMIN_DEFAULT_EMAIL` và `PGADMIN_DEFAULT_PASSWORD` trong
  `.env`. Khi đăng ký máy chủ PostgreSQL trong pgAdmin, nhập host `db`, port
  `5432`, database `POSTGRES_DB`. Tài khoản `APP_DB_USER` có quyền CRUD trong
  schema `public`; `POSTGRES_USER` có quyền quản trị cao hơn. Dùng app role cho
  kết nối xem dữ liệu thông thường. Mật khẩu pgAdmin không phải mật khẩu
  PostgreSQL.
- Grafana: dùng `GRAFANA_ADMIN_USER` và `GRAFANA_ADMIN_PASSWORD` trong `.env`.
- Không ghi lại giá trị mật khẩu trong báo cáo. Nếu cần ảnh đăng nhập, che các
  trường thông tin xác thực.

### Đăng ký PostgreSQL server trong pgAdmin

Sau khi đăng nhập tại <http://localhost:5050>, chọn **Add New Server**.
Trong tab **General**, đặt tên dễ nhận biết, ví dụ `ClinicCare PostgreSQL`.
Trong tab **Connection**, nhập:

| Trường pgAdmin | Giá trị |
| --- | --- |
| Host name/address | `db` |
| Port | `5432` |
| Maintenance database | Giá trị `POSTGRES_DB` trong `.env` |
| Username | Giá trị `APP_DB_USER` trong `.env` |
| Password | Giá trị `APP_DB_PASSWORD` trong `.env` |

Nếu server đã được đăng ký, mở **Properties → Connection** để sửa các trường
trên; không tạo thêm server trùng tên. Khi hộp thoại kết nối yêu cầu mật khẩu,
nhập giá trị `APP_DB_PASSWORD` trong `.env` và chọn **Save Password** chỉ khi
muốn lưu credential trong hồ sơ pgAdmin cục bộ. Chỉ đọc các giá trị từ `.env`
cục bộ; không ghi chúng vào terminal dùng chung, ảnh chụp hoặc Git. Không cần
publish cổng PostgreSQL ra host vì pgAdmin kết nối qua Docker network.

## Cài đặt và khởi động

1. Cài Docker Desktop và bật Linux containers.
2. Tạo `.env` từ mẫu (nếu chưa có):

   ```powershell
   Copy-Item .env.example .env
   ```

3. Thay các giá trị mẫu trong `.env` bằng email hợp lệ và mật khẩu/secret
   riêng biệt, được sinh ngẫu nhiên bằng trình quản lý mật khẩu (ít nhất 32
   byte ngẫu nhiên cho mỗi secret). Không tái sử dụng mật khẩu giữa các dịch
   vụ. Giữ nguyên `.env` cục bộ; không commit file này.
4. Khởi động riêng PostgreSQL, áp dụng migration người dùng (an toàn khi chạy
   lại, không xóa hoặc khởi tạo lại volume), rồi build và khởi động các service:

   ```powershell
   docker compose config --quiet
   docker compose up -d db
   docker compose exec -T db sh -c 'psql --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --file /migrations/03-add-user-auth.sql'
   docker compose up -d --build
   docker compose ps
   ```

5. Tạo tài khoản Admin đầu tiên bằng prompt ẩn mật khẩu (không truyền mật khẩu
   trên command line hoặc ghi vào `.env`):

   ```powershell
   docker compose exec app flask --app app create-admin
   ```

   Sau đó đăng nhập tại <http://localhost:8082/login>. Chờ healthcheck của
   PostgreSQL và ứng dụng chuyển sang `healthy`.

Tạo `FLASK_SECRET_KEY` ngẫu nhiên mạnh cho môi trường thực tế; không chia sẻ
giá trị đó hoặc đưa `.env` vào Git. Ứng dụng mặc định chạy HTTP local với
`SESSION_COOKIE_SECURE=false`; đặt biến này thành `true` trong `.env` khi chạy
qua HTTPS để chỉ gửi cookie qua kết nối bảo mật.

Compose sẽ tạo/recreate các container khi cấu hình thay đổi; named volumes
không bị xóa bởi `up -d --build`. File `database/init.sql` chỉ được PostgreSQL
chạy khi khởi tạo data directory lần đầu, không phải cơ chế migration cho
database đã tồn tại. Ứng dụng sử dụng role `APP_DB_USER` có quyền CRUD, còn
PostgreSQL Exporter dùng role riêng chỉ được cấp `pg_monitor`. Khi database
đã tồn tại, cập nhật role cần được áp dụng tường minh bằng
`database/02-create-runtime-roles.sql`; không xóa volume.

### Đăng nhập và phân quyền

Không có đăng ký công khai hoặc tài khoản/mật khẩu mặc định. Lệnh
`flask --app app create-admin` hỏi username, họ tên và mật khẩu hai lần bằng
prompt không hiển thị mật khẩu; mật khẩu tối thiểu 12 ký tự và chỉ lưu dưới
dạng hash. Admin tạo và quản lý tài khoản nhân viên trong **Tài khoản**.

| Vai trò | Quyền chính |
| --- | --- |
| Admin | Truy cập dashboard; quản lý bệnh nhân, bác sĩ, lịch khám và tài khoản; đổi vai trò, khóa/mở khóa tài khoản. Không thể hạ quyền hoặc khóa Admin cuối cùng. |
| Doctor | Xem dashboard và lịch khám được phân công; xem thông tin bệnh nhân gắn với lịch của mình; cập nhật ghi chú và trạng thái lịch được giao. |
| Receptionist | Thêm/tìm/xem/sửa bệnh nhân; xem bác sĩ; tạo và quản lý lịch khám; hủy lịch chưa hoàn thành. Không được xóa bệnh nhân/bác sĩ hoặc quản lý tài khoản. |

Khi Admin tạo tài khoản Doctor, phải liên kết với một hồ sơ bác sĩ; mỗi hồ sơ
chỉ được gắn một tài khoản Doctor. Backend kiểm tra quyền cho từng route và
phạm vi lịch của bác sĩ, kể cả khi gửi request trực tiếp. Form POST, kể cả
đăng nhập/đăng xuất, được bảo vệ bằng CSRF. Khóa tài khoản sẽ làm mất hiệu lực
phiên ở request kế tiếp. `SESSION_COOKIE_SECURE=false` phù hợp HTTP local;
chỉ bật `true` sau khi website được phục vụ thực sự qua HTTPS.

#### Chạy kiểm thử Python không cần Docker

Ứng dụng kiểm thử dùng SQLite trong bộ nhớ; lệnh sau không cần Docker, Docker
Desktop, PostgreSQL đang chạy hoặc file `.env`. Cần cài `uv` và Python; chạy từ
thư mục `app`:

```powershell
Set-Location app
uv run --no-project --with-requirements requirements.txt python -m unittest discover -s tests -v
```

`uv` tự tải các thư viện Python khai báo trong `requirements.txt` vào môi
trường tạm, không sửa file dependency của dự án. Kết quả test này xác minh
luồng ứng dụng với SQLite cô lập; nó không thay thế kiểm thử migration trên
PostgreSQL hoặc kiểm thử toàn bộ stack Docker.

Chạy bộ kiểm thử trong container (sau khi build và khởi động stack):

```powershell
docker compose exec app python -m unittest discover -s tests -v
```

## Xác minh

### Website, database và headers

```powershell
Invoke-WebRequest http://localhost:8082/health
Invoke-WebRequest -Method Head http://localhost:8082/
docker compose ps
docker compose logs --tail 100 app db nginx pgadmin
```

`/health` trả HTTP 200 khi Flask truy vấn được PostgreSQL; lỗi kết nối trả
HTTP 503. Nginx cần trả các header `X-Content-Type-Options`,
`X-Frame-Options` và `Referrer-Policy`.

### Prometheus

Mở <http://localhost:9090/targets> và kiểm tra các job `prometheus`,
`clinic-app`, `nginx`, `postgresql`, `cadvisor` và `node-exporter` có trạng
thái `UP`. Nginx Exporter đọc endpoint `stub_status` chỉ mở trong Docker
network; hai panel Nginx trong dashboard hiển thị kết nối và request/giây.
Có thể kiểm tra API:

```powershell
Invoke-RestMethod http://localhost:9090/api/v1/targets
Invoke-WebRequest http://localhost:9090/-/healthy
```

### Grafana

Datasource Prometheus và Loki được provision tự động. Dashboard **ClinicCare -
Overview** được provision trong folder **ClinicCare**. CPU/RAM host, container,
Nginx, app, PostgreSQL và HTTP metrics có thể hiển thị. Trên Docker Desktop/Windows,
cAdvisor hiện chỉ cung cấp cgroup tổng hợp của Linux VM (không có nhãn từng
container); dashboard dùng tên panel **Docker VM cgroups** để phản ánh đúng
phạm vi đo. Nếu dashboard trống, kiểm tra targets, thời gian thu thập và log.

### Loki và LogQL

Promtail phát hiện container qua Docker socket; label `container` là tên
container đầy đủ từ Docker (ví dụ `clinic-management-db-1`), `service` và
`service_name` cùng lấy từ Docker Compose service label (ví dụ `db`), còn
`project` là `clinic-management`. Trong Grafana Explore, chọn datasource Loki
và khoảng thời gian phù hợp; ba truy vấn mẫu nằm ở phần **LogQL nhanh** gần đầu
README.

`|~` áp dụng regex case-insensitive `(?i)` lên nội dung log. Promtail được
giới hạn vào Compose project `clinic-management`, không đọc log của project
khác. Truy vấn không có kết quả trong time range chỉ có nghĩa là không tìm
thấy dòng khớp, không phải lỗi truy vấn.

```powershell
docker compose exec promtail /usr/bin/promtail --check-syntax --config.file=/etc/promtail/promtail-config.yml
docker compose config --quiet
docker compose restart promtail
docker compose ps promtail loki
Invoke-WebRequest http://localhost:3100/ready
Invoke-RestMethod http://localhost:3100/loki/api/v1/labels
docker compose logs --tail 100 loki promtail
```

Sau khi thêm label `service_name`, các lệnh trên đã được chạy; Promtail/Loki
đang hoạt động. Cả ba truy vấn LogQL mẫu trả `status=success`. Truy vấn log
Nginx và app có thể trả kết quả; truy vấn lỗi chỉ trả dòng nào thực sự khớp
trong khoảng thời gian chọn, nên kết quả rỗng không đồng nghĩa với lỗi truy vấn.

### Tình trạng bằng chứng đã chạy

| Kiểm tra | Kết quả thực tế |
| --- | --- |
| Compose config cuối cùng | `docker compose config --quiet`: hợp lệ |
| Stack | `docker compose up -d --build`: hoàn tất |
| Website trước khi bật đăng nhập | Các trang `/patients`, `/doctors`, `/appointments` từng trả HTTP 200 trong lần kiểm tra baseline. Hiện các trang quản lý yêu cầu đăng nhập; cần kiểm tra lại sau khi áp dụng migration và tạo tài khoản. |
| Python RBAC tests | `uv run --no-project --with-requirements requirements.txt python -m unittest discover -s tests -v` (chạy từ `app`): 11 tests passed trên SQLite trong bộ nhớ; không cần Docker. |
| Patient CRUD browser check | Tạo và đọc lại duy nhất bản ghi thử `VALIDATION-*`; hủy hộp thoại xác nhận giữ bản ghi; xác nhận xóa chỉ xóa bản ghi thử; truy vấn đếm sau cùng xác nhận không còn bản ghi `VALIDATION-*`; bản ghi bệnh nhân có trước vẫn còn |
| pgAdmin và PostgreSQL | pgAdmin `/misc/ping`: HTTP 200; server `ClinicCare PostgreSQL` dùng host `db`, database `clinicdb`, role `clinic_runtime`; đăng nhập PostgreSQL từ network/container pgAdmin bằng `APP_DB_PASSWORD` thành công. Giao diện pgAdmin vẫn cần nhập mật khẩu khi mở kết nối; ảnh cũ chưa chứng minh session database trong UI. |
| Prometheus | `/-/healthy`: HTTP 200; API kiểm tra 6/6 targets `UP`, gồm job `nginx` |
| Nginx Exporter | Target `UP`; Prometheus trả series `nginx_connections_active` và `nginx_http_requests_total` |
| PostgreSQL exporter | `pg_up=1`; app/exporter role không phải superuser, exporter có `pg_monitor` |
| Node Exporter | Target `UP`; 64 series CPU và 1 series RAM |
| Grafana | `/api/health`: HTTP 200; datasource Loki/Prometheus có health `OK`; dashboard UID `clinic-care-overview` tìm thấy qua API |
| Grafana dashboard | Dashboard JSON hợp lệ với 9 panel; gồm host, container, Nginx, app, PostgreSQL và HTTP. cAdvisor trả cgroup tổng hợp Docker VM, không phải từng container |
| Grafana Explore | Đã mở datasource Loki, query selector app và xem được kết quả log; khi reload, plugin `grafana-lokiexplore-app` v1.0.39 trả lỗi preload do `react/jsx-runtime` HTTP 404 từ module plugin; chưa sửa |
| Loki | `/ready`: HTTP 200 (`ready`); lần kiểm tra lặp lại sau một phản hồi 503 ban đầu trả 200, API labels hoạt động |
| `{container="clinic-management-app-1"}` | Loki API `status=success`, 1 stream trong cửa sổ 24 giờ |
| `{container="clinic-management-nginx-1"} |= "error"` | Loki API `status=success`, không có dòng khớp trong cửa sổ 24 giờ |
| `{container="clinic-management-db-1"} \|~ "(?i)error"` | Loki API `status=success`, 1 stream có 1 dòng khớp trong cửa sổ 24 giờ |
| Loki Explore screenshots | Query app và log Nginx trong `evidence/13-loki-explore-app.png` và `evidence/15-loki-nginx-logs.png` |
| Nginx headers | `nosniff`, `DENY`, `strict-origin-when-cross-origin` và CSP đã nhận |
| CSP delete confirmation | Static script cùng nguồn hoạt động; trình duyệt hiện hộp xác nhận, dismiss giữ nguyên bản ghi; script được tải HTTP 200 |
| HTTPS | Chưa cấu hình; môi trường hiện không có OpenSSL để tạo cert PEM cục bộ |

## Log, xử lý sự cố và dừng dịch vụ

```powershell
docker compose ps
docker compose logs --tail 100
docker compose logs -f app nginx db pgadmin prometheus grafana loki promtail
docker compose restart pgadmin
docker compose stop
docker compose up -d
```

- Không vào được pgAdmin: kiểm tra `PGADMIN_DEFAULT_EMAIL` có cú pháp email
  hợp lệ, `PGADMIN_DEFAULT_PASSWORD` không rỗng, xác nhận cổng host 5050 không
  bị chiếm; sau đó chạy `docker compose up -d --force-recreate pgadmin`.
- pgAdmin báo `no password supplied` khi mở server PostgreSQL: trong
  **Properties → Connection**, đặt host `db`, port `5432`, maintenance database
  `POSTGRES_DB`, username `APP_DB_USER`. Khi được hỏi, nhập
  `APP_DB_PASSWORD` (khác với mật khẩu đăng nhập pgAdmin). Lỗi này có thể xảy ra
  nếu hồ sơ server lưu user cũ hoặc password chưa được nhập; không cần sửa hay
  xóa database volume.
- Đăng nhập pgAdmin không được sau khi đổi `.env`: pgAdmin có thể giữ cấu hình
  khởi tạo trong volume. Không xóa volume; kiểm tra log và xử lý thay đổi thông
  tin xác thực theo thủ tục quản trị pgAdmin.
- App không healthy: xem `docker compose logs app db`; kiểm tra
  `DATABASE_URL` được tạo từ các biến PostgreSQL và `docker compose ps`.
- Nếu ứng dụng đã chạy trước khi role runtime được thêm, áp dụng
  `database/02-create-runtime-roles.sql` trước khi recreate app.
  Có thể áp dụng bằng PowerShell sau khi xác nhận `.env` có hai biến này. Lệnh
  không in hoặc đưa mật khẩu lên dòng lệnh:

  ```powershell
  $envValues = @{}
  Get-Content .env | ForEach-Object {
      if ($_ -match '^([^#=]+)=(.*)$') { $envValues[$matches[1]] = $matches[2] }
  }
  $dbUser = $envValues['POSTGRES_USER']
  $dbName = $envValues['POSTGRES_DB']
  if ([string]::IsNullOrWhiteSpace($dbUser) -or [string]::IsNullOrWhiteSpace($dbName)) {
      throw 'POSTGRES_USER hoặc POSTGRES_DB chưa được cấu hình trong .env'
  }
  docker compose exec -T db psql --set=ON_ERROR_STOP=1 --username $dbUser --dbname $dbName --file /docker-entrypoint-initdb.d/02-create-runtime-roles.sql
  ```

  Không chia sẻ đầu ra chứa thông tin xác thực và không xóa volume.
- Prometheus target `DOWN`: kiểm tra đúng target nội bộ và log của exporter.
- Loki không thấy log: kiểm tra `docker compose logs promtail loki`, quyền/khả
  năng truy cập Docker socket và label thực tế tại Grafana Explore.
- Nếu cổng đã bận, dừng tiến trình/dịch vụ chiếm cổng hoặc đổi port mapping và
  cập nhật bảng địa chỉ trước khi chạy lại Compose.

Để dừng mà vẫn giữ dữ liệu, dùng `docker compose stop`. `docker compose down`
(không có `-v`) cũng giữ named volumes; không sử dụng `docker compose down -v`.

## Hardening và giới hạn đã biết

- `.env` bị loại khỏi Git bởi `.gitignore`; `.env.example` chỉ có placeholders.
- Mỗi mật khẩu database/exporter/pgAdmin/Grafana và Flask secret cần được thay
  bằng giá trị ngẫu nhiên riêng, tối thiểu 32 byte; thay đổi `.env` không tự
  đổi password của database đã khởi tạo. Không ghi credential ra log hoặc Git.
  Trên máy phát triển hiện tại, sáu giá trị secret đã được xoay sang 32 byte
  ngẫu nhiên riêng; PostgreSQL roles, pgAdmin và Grafana đã được đồng bộ. Các
  giá trị chỉ nằm trong `.env` local và không được commit.
- PostgreSQL không publish cổng host. Dịch vụ chỉ giao tiếp qua network nội bộ.
- Network `frontend`, `backend` và `monitoring` là internal; cổng quản trị/
  metrics cần truy cập từ host chỉ bind vào `127.0.0.1`.
- Flask dùng role không-superuser chỉ có quyền CRUD; PostgreSQL Exporter dùng
  role riêng có quyền `pg_monitor`.
- Flask và Nginx chạy non-root. Filesystem của app, Nginx, exporters,
  Prometheus, Loki, Promtail, Node Exporter và Grafana đặt read-only; dữ liệu
  cần ghi chỉ nằm ở named volumes hoặc tmpfs. Các dịch vụ này bỏ Linux
  capabilities; nơi phù hợp bật `no-new-privileges`.
- pgAdmin, exporters, Prometheus, Loki, Node Exporter và Grafana chạy dưới
  user không-root theo image. Promtail là ngoại lệ chạy root do Docker socket/
  file log; PostgreSQL image cần quyền lúc khởi tạo và tự hạ quyền cho tiến
  trình database. pgAdmin cũng dùng một helper root bên cạnh web worker UID
  5050; `no-new-privileges`/bỏ capabilities làm hỏng startup helper nên không
  áp dụng cho pgAdmin.
- Prometheus/Grafana/pgAdmin/Nginx/Loki chỉ publish trên loopback.
- Certificate/key TLS tương lai được ignore (`nginx/certs/`, `*.crt`, `*.cer`,
  `*.pem`, `*.key`, `*.p12`, `*.pfx`); vẫn cần kiểm tra `git status` trước commit.
- Nginx bật `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy` và CSP; HTTP không bật HSTS vì chưa triển khai HTTPS.
- Promtail cần Docker socket để phát hiện container. Socket cấp quyền điều khiển
  Docker daemon ở mức cao; Promtail chạy root để đọc log và discovery bị giới
  hạn vào project này. Dù bỏ capabilities, quyền qua Docker socket vẫn rất cao.
  Chỉ chạy trên máy tin cậy, không mở Docker API ra mạng.
- cAdvisor cần đọc thông tin host/container; Node Exporter trên Docker Desktop
  phản ánh Linux VM thay vì toàn bộ Windows host. cAdvisor có quyền đọc các
  mount host ở chế độ read-only; đây là ngoại lệ cần thiết cho giám sát.
  cAdvisor ghi nhận thiếu `/sys/class/dmi/id/product_name`, nhưng target vẫn
  `UP`.
- Kiểm tra nhanh: `docker compose exec app id` và `docker compose exec nginx id`
  phải hiện UID khác `0`; `docker inspect --format
  '{{.HostConfig.ReadonlyRootfs}}' (docker compose ps -q nginx)` phải trả `true`.
  Để kiểm tra tất cả secret đạt 32 byte mà không in giá trị:

  ```powershell
  $keys = 'POSTGRES_PASSWORD','APP_DB_PASSWORD','POSTGRES_EXPORTER_PASSWORD','PGADMIN_DEFAULT_PASSWORD','FLASK_SECRET_KEY','GRAFANA_ADMIN_PASSWORD'
  $values = @{}
  Get-Content .env | ForEach-Object {
      if ($_ -match '^([^#=]+)=(.*)$' -and $keys -contains $matches[1]) {
          $values[$matches[1]] = $matches[2]
      }
  }
  foreach ($key in $keys) {
      '{0}: {1}' -f $key, $(if ($values[$key] -match '^[0-9a-f]{64,}$') { 'OK' } else { 'CHECK' })
  }
  ```

  Không in hoặc chia sẻ nội dung `.env`.
- Promtail đã hết vòng đời hỗ trợ upstream. Ở đây dùng theo yêu cầu bài tập;
  với triển khai mới cho production nên chuyển sang Grafana Alloy.
- Chưa có HTTPS tự ký trong cấu hình này. Trên môi trường hiện tại không tìm
  thấy listener TLS, chứng thư hoặc mount cert/key; HTTPS probe tới
  `https://localhost:8082/health` thất bại còn HTTP trả 200. Để triển khai sau:
  (1) tạo chứng thư có SAN `localhost` và private key bằng công cụ tin cậy như
  `mkcert` hoặc OpenSSL; (2) lưu cert/key trong thư mục cục bộ bị `.gitignore`
  loại trừ; (3) cấu hình Nginx listener 443 với `ssl_certificate` và
  `ssl_certificate_key`, mount read-only; (4) publish loopback port, ví dụ
  `127.0.0.1:8443:443`; (5) chạy `docker compose config --quiet`, recreate
  Nginx và xác minh `https://localhost:8443/health`. Chỉ coi là TLS tin cậy
  sau khi xác minh SAN/chuỗi chứng thư; không commit private key/certificate
  bí mật.
- Ở lần chạy Promtail đầu tiên, discovery chưa lọc Compose project và Loki đã
  nhận thử log từ project khác, đồng thời từ chối một số dòng quá cũ (HTTP 400).
  Đã thêm bộ lọc project; không xóa volume Loki, nên log đã lưu có thể còn đến
  khi retention 7 ngày tự hết hạn.
- Trong lúc Compose thay container, Promtail cũng ghi một số lỗi chuyển tiếp
  khi Docker target cũ biến mất; target mới được phát hiện sau đó. Kiểm tra
  cuối không thấy log Promtail mới trong 90 giây.
## GitHub và lịch sử commit

Repository hiện được cấu hình remote
[`dtc245300153-netizen/ClinicCare`](https://github.com/dtc245300153-netizen/ClinicCare)
trên nhánh `main`, đang theo dõi `origin/main`; `.env` bị ignore. Lịch sử hiện
có ba commit triển khai đầu tiên tương ứng các mốc yêu cầu, cùng các commit
cập nhật tiếp theo:

1. `c83e140 feat: deploy clinic app, PostgreSQL, pgAdmin and Nginx`
2. `09d839a feat: add Prometheus and Grafana monitoring`
3. `c635ee4 feat: add Loki log collection and harden services`
4. `35dea2d feat: update ClinicCare system`
5. `3b0b6ee docs: clarify ClinicCare deployment and GitHub status`

Các cập nhật mới nhất hoàn thiện metrics riêng cho Nginx và ghi rõ ba truy vấn
LogQL mẫu; xem commit mới nhất bằng `git log --oneline`.

**Lưu ý về tiêu chí tài khoản:** tên chủ repository hiện tại là
`dtc245300153-netizen`, không phải chuỗi MSSV nguyên dạng. Nếu giảng viên yêu
cầu username khớp tuyệt đối MSSV, cần xác nhận quy định và đổi tài khoản/
repository theo quyền của chủ sở hữu; không thể tự tạo hoặc đổi tài khoản thay
người dùng.

**Cảnh báo riêng tư quan trọng:** ghi chú lịch sử dự án cho biết một commit cũ
từng chứa ảnh giao diện có thông tin nhận dạng bệnh nhân. Việc xóa ảnh khỏi
working tree không xóa ảnh khỏi lịch sử Git. Vì remote hiện đã được cấu hình,
hãy kiểm tra lịch sử và repository GitHub trước khi nộp/chia sẻ. Nếu dữ liệu
nhận dạng còn ở commit đã push, cần phối hợp chủ repo để loại bỏ bằng cách
rewrite history và force-push có kiểm soát, đồng thời xử lý ảnh hưởng tới
clone khác. Không đưa dữ liệu bệnh nhân thật vào ảnh minh chứng. Không lưu
password/token trong Git; `.env` đang bị ignore.

## Ảnh minh chứng cho báo cáo

Thư mục `evidence/` chứa 18 ảnh minh chứng được cung cấp kèm báo cáo và sắp
xếp theo thứ tự hình trong báo cáo. Ảnh 03 và 05 đã dùng bản che tên tài khoản,
email và dữ liệu từng dòng trước khi đưa vào thư mục; ảnh 14 cũng đã loại bỏ
chuỗi secret. Các ảnh là bằng chứng tại thời điểm chụp, không khẳng định trạng
thái hiện tại của dịch vụ:

| Ảnh | Minh chứng | Trạng thái |
| --- | --- | --- |
| `evidence/01-github-repository.png` | Repository ClinicCare trên GitHub | Ảnh 1 trong báo cáo |
| `evidence/02-github-commit-history.png` | Lịch sử commit trên GitHub | Ảnh 2 trong báo cáo |
| `evidence/03-cliniccare-dashboard.png` | Dashboard ClinicCare; tên tài khoản đã che | Ảnh 3 trong báo cáo |
| `evidence/04-docker-compose-logs.png` | Docker Desktop/Compose logs | Ảnh 4 trong báo cáo |
| `evidence/05-postgres-appointments-redacted.png` | Truy vấn appointments; dữ liệu từng dòng/email đã che | Ảnh 5 trong báo cáo |
| `evidence/06-nginx-proxy-headers.png` | Cấu hình Nginx reverse proxy và security headers | Ảnh 6 trong báo cáo |
| `evidence/07-http-response-headers.png` | Response headers trên HTTP local | Ảnh 7 trong báo cáo |
| `evidence/08-cliniccare-devtools.png` | ClinicCare cùng DevTools/Network | Ảnh 8 trong báo cáo |
| `evidence/09-prometheus-targets.png` | Prometheus Targets tại thời điểm chụp | Ảnh 9 trong báo cáo |
| `evidence/10-grafana-overview.png` | Grafana ClinicCare Overview | Ảnh 10 trong báo cáo |
| `evidence/11-grafana-prometheus-datasource.png` | Datasource Prometheus trên Grafana | Ảnh 11 trong báo cáo |
| `evidence/12-grafana-cpu-alert-rule.png` | CPU alert rule và trạng thái thể hiện trong ảnh | Ảnh 12 trong báo cáo |
| `evidence/13-loki-explore-app.png` | Loki Explore với selector cho app | Ảnh 13 trong báo cáo |
| `evidence/14-postgres-exporter-error-redacted.png` | Lỗi postgres exporter; secret đã che | Ảnh 14 trong báo cáo |
| `evidence/15-loki-nginx-logs.png` | Log Nginx trong Loki Explore | Ảnh 15 trong báo cáo |
| `evidence/16-compose-hardening-grafana.png` | Compose hardening Grafana | Ảnh 16 trong báo cáo |
| `evidence/17-docker-networks.png` | Docker networks thuộc phạm vi ClinicCare | Ảnh 17 trong báo cáo |
| `evidence/18-app-nonroot-user.png` | App chạy với UID/GID 10001:10001 | Ảnh 18 trong báo cáo |

Ghi thời gian, URL, lệnh và kết quả thực tế cạnh mỗi ảnh trong báo cáo nộp;
không đưa thông tin định danh bệnh nhân hoặc credential vào ảnh.
