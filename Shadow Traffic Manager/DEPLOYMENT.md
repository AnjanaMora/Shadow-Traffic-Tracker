# Shadow Traffic — Production Deployment Guide & Runbook

This guide covers everything required to deploy **Shadow Traffic** to a production Linux VPS (Ubuntu/Debian) using Docker Compose, configure production environment secrets, set up SSL/TLS, and point the telemetry collector at real production websites.

---

## 1. Architecture & Port Layout

In a hardened production deployment, **only the reverse proxy ports (80 and 443) are exposed to the public Internet**. All internal microservices, databases, and forecasters communicate through an isolated Docker bridge network (`shadow-net`).

```text
       Public Internet (Users & Telemetry Collectors)
                            │
               HTTPS (443)  │  HTTP (80)
                            ▼
              ┌───────────────────────────┐
              │   Nginx Reverse Proxy     │
              │   (Dashboard Container)   │
              └─────────────┬─────────────┘
                            │
          ┌─────────────────┴─────────────────┐
          │  Internal Docker Bridge Network   │
          │           (shadow-net)            │
          └─────────────────┬─────────────────┘
                            │
       ┌────────────────────┼────────────────────┐
       ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────┐    ┌─────────────────┐
│ Backend API  │    │  Prediction  │    │  TimescaleDB    │
│ Gateway      │◄──►│  Engine      │    │  Hypertable DB  │
│ (Port 8000)  │    │  (Port 8001) │    │  (Port 5432)    │
└──────┬───────┘    └──────────────┘    └────────▲────────┘
       │                                         │
       └─────────────────────────────────────────┘
```

### Port Security Matrix
| Service | Container Port | Host Port (Production) | Exposed to Public? | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **Dashboard / Nginx** | `80` | `80` / `443` | **Yes** | Web UI, static bundles, `/api/` & `/ws/` reverse proxy |
| **Backend API Gateway** | `8000` | `8000` *(Optional)* | Only if external collectors push directly | Telemetry ingestion endpoint & WebSocket hub |
| **Prediction Engine** | `8001` | *Unexposed* | **NO** | Internal statistical & ML forecast API |
| **TimescaleDB** | `5432` | *Unexposed* | **NO** | PostgreSQL time-series hypertable storage |

---

## 2. VPS Hardware & OS Provisioning

### Recommended Minimum Specifications
- **CPU**: 2 vCPUs (x86_64)
- **Memory**: 4 GB RAM (2 GB swap file recommended)
- **Disk**: 40 GB NVMe / SSD
- **Operating System**: Ubuntu 22.04 LTS or Ubuntu 24.04 LTS

### Initial Server Hardening & Docker Installation
Connect to your VPS via SSH and execute:

```bash
# 1. Update OS packages
sudo apt-get update && sudo apt-get upgrade -y

# 2. Configure UFW firewall
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp comment "SSH"
sudo ufw allow 80/tcp comment "HTTP"
sudo ufw allow 443/tcp comment "HTTPS"
sudo ufw --force enable

# 3. Install Docker Engine and Docker Compose v2 plugin
sudo apt-get install -y ca-certificates curl gnupg lsb-release
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 4. Allow non-root user to manage Docker (optional)
sudo usermod -aG docker $USER
```

---

## 3. Deploying with Docker Compose

### Step 1: Clone the Repository
```bash
cd /opt
sudo git clone https://github.com/your-org/shadow-traffic.git
sudo chown -R $USER:$USER shadow-traffic
cd shadow-traffic
```

### Step 2: Initialize Production Environment Configuration
```bash
cp .env.production.example .env
```

Generate secure random secrets:
```bash
# Generate a cryptographic database password
DB_SECRET=$(openssl rand -hex 24)
sed -i "s/CHANGE_ME_TO_A_SECURE_RANDOM_PASSWORD_IN_PRODUCTION/$DB_SECRET/g" .env

# Generate a strong collector API key
API_KEY_SECRET=$(openssl rand -hex 20)
sed -i "s/CHANGE_ME_TO_A_CRYPTOGRAPHIC_COLLECTOR_KEY/$API_KEY_SECRET/g" .env
```

Edit `.env` and configure your domain and external alerting webhook:
```bash
nano .env
```
Key settings to verify:
- `ALERT_WEBHOOK_URL`: Your Slack / PagerDuty / OpsGenie webhook URL.
- `CORS_ALLOWED_ORIGINS`: Set to your production domain (e.g. `https://shadow.yourdomain.com`).
- `DEFAULT_API_KEY`: Record this key; you will need it when configuring external collectors.

### Step 3: Launch the Production Stack
```bash
docker compose -f docker-compose.prod.yml up -d --build
```

### Step 4: Verify Container Health
```bash
docker compose -f docker-compose.prod.yml ps
```
All containers (`shadow-timescaledb-prod`, `shadow-prediction-engine-prod`, `shadow-backend-prod`, `shadow-dashboard-prod`) should report `Up (healthy)`.

Inspect aggregated logs:
```bash
docker compose -f docker-compose.prod.yml logs -f --tail=50
```

---

## 4. Complete Environment Variables Reference

| Variable Name | Required? | Default / Example | Description |
| :--- | :---: | :--- | :--- |
| `ENVIRONMENT` | Yes | `production` | Active runtime profile (`development`, `staging`, `production`) |
| `LOG_LEVEL` | No | `warning` | Logging verbosity (`debug`, `info`, `warning`, `error`) |
| `LOG_FORMAT_JSON` | No | `true` | When `true`, outputs machine-readable JSON log lines |
| `POSTGRES_USER` | Yes | `shadow_admin` | TimescaleDB administrative username |
| `POSTGRES_PASSWORD` | Yes | *(Cryptographic secret)* | TimescaleDB master password |
| `POSTGRES_DB` | Yes | `shadow_traffic_prod` | TimescaleDB database name |
| `DATABASE_URL` | Yes | `postgresql+asyncpg://...` | SQLAlchemy async connection URI |
| `DATABASE_POOL_SIZE`| No | `30` | Async connection pool max connections |
| `BACKEND_PORT` | No | `8000` | Gateway host port |
| `DEFAULT_API_KEY` | Yes | *(Cryptographic secret)* | Shared authentication token for metric ingestion |
| `ALLOWED_API_KEYS` | Yes | *(Comma-separated list)* | Permitted API keys accepted by `/api/metrics` |
| `RATE_LIMIT_REQUESTS_PER_MINUTE` | No | `120` | Rate limiter limit per `site_id` |
| `CORS_ALLOWED_ORIGINS` | No | `https://shadow.domain.com` | Permitted origins for dashboard API calls |
| `ALERT_WEBHOOK_URL` | No | `https://hooks.slack.com/...` | Outbound webhook for Critical/Warning alerts |
| `ALERT_COOLDOWN_SECONDS` | No | `180` | Cooldown period between duplicate alerts |
| `HYSTERESIS_CONSECUTIVE_CHECKS` | No | `2` | Number of cycles a risk tier must persist before alerting |
| `PREDICTION_ENGINE_URL` | Yes | `http://prediction-engine:8001`| Internal endpoint to reach the forecaster |
| `FORECAST_HORIZON_MINUTES` | No | `20` | Forward prediction projection window |
| `BASELINE_EWMA_ALPHA` | No | `0.25` | Exponential decay weighting factor for seasonal baseline |
| `DASHBOARD_PORT` | No | `80` | Public HTTP port exposed on the host |
| `SITE_ID` | Yes | `prod-main-cluster` | Identifier for the primary monitored service |
| `COLLECTOR_MODE` | Yes | `tail-log` or `simulate` | Mode of the telemetry collector agent |

---

## 5. Pointing the Collector at a Real Production Website

In production, you do not want synthetic simulated traffic — you want live telemetry collected from your real web application. Shadow Traffic supports two real-world collection modes:

### Mode 1: Tailing Real Nginx / Apache Access Logs

This is the recommended non-invasive mode. The collector continuously tails access log files, parses response times and HTTP status codes, aggregates them into 5-second windows, and pushes canonical `MetricEvent` payloads to the API gateway.

#### Step 1: Configure Nginx Log Format
In your web server's `/etc/nginx/nginx.conf`, ensure `$request_time` (response latency in seconds) is recorded in the access log:

```nginx
http {
    # Custom combined format including upstream response time
    log_format shadow_traffic '$remote_addr - $remote_user [$time_local] '
                              '"$request" $status $body_bytes_sent '
                              '"$http_referer" "$http_user_agent" '
                              'rt=$request_time uct="$upstream_connect_time" uht="$upstream_header_time" urt="$upstream_response_time"';

    access_log /var/log/nginx/access.log shadow_traffic;
}
```
Reload Nginx: `sudo nginx -s reload`.

#### Step 2: Run the Collector on the Web Server Host (Systemd Daemon)
If your monitored website runs on a separate server from Shadow Traffic:

1. Copy the `collector/` and `shared/` directories to the target web server:
   ```bash
   sudo mkdir -p /opt/shadow-collector
   sudo rsync -avz --exclude 'node_modules' shared collector user@webserver.com:/opt/shadow-collector/
   ```

2. Set up Python environment:
   ```bash
   cd /opt/shadow-collector
   python3 -m venv venv
   source venv/bin/activate
   pip install -e shared/python
   pip install -r collector/requirements.txt
   ```

3. Create the Systemd service unit at `/etc/systemd/system/shadow-collector.service`:
   ```ini
   [Unit]
   Description=Shadow Traffic Telemetry Collector Agent
   After=network.target nginx.service
   Wants=network-online.target

   [Service]
   Type=simple
   User=www-data
   Group=www-data
   WorkingDirectory=/opt/shadow-collector
   Environment="PATH=/opt/shadow-collector/venv/bin"
   Environment="BACKEND_API_URL=https://shadow.yourdomain.com"
   Environment="API_KEY=YOUR_CRYPTOGRAPHIC_COLLECTOR_KEY"
   Environment="SITE_ID=prod-ecommerce-web"
   Environment="COLLECTOR_MODE=tail-log"
   Environment="LOG_FILE_PATH=/var/log/nginx/access.log"
   Environment="REPORT_INTERVAL_SECONDS=5.0"
   Environment="LOG_LEVEL=info"
   ExecStart=/opt/shadow-collector/venv/bin/python -m collector.src.agent
   Restart=always
   RestartSec=5s

   # Security sandboxing
   NoNewPrivileges=true
   ProtectSystem=full
   ProtectHome=true

   [Install]
   WantedBy=multi-user.target
   ```

4. Enable and start the collector daemon:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable shadow-collector
   sudo systemctl start shadow-collector
   sudo journalctl -u shadow-collector -f
   ```

---

### Mode 2: Scraping a Prometheus Metrics Endpoint

If your web application or ingress controller already exposes a Prometheus `/metrics` endpoint (e.g. via FastAPI-Prometheus, Spring Boot Actuator, or Nginx Ingress Controller):

Configure these environment variables for the collector:
```bash
COLLECTOR_MODE=scrape-prometheus
PROMETHEUS_METRICS_URL=https://api.yourdomain.com/metrics
SITE_ID=prod-api-service
REPORT_INTERVAL_SECONDS=5.0
```

The scraper polls the standard Prometheus metric keys:
- `http_requests_total` (calculates `request_rate` and `error_rate_percent`)
- `http_request_duration_seconds` (calculates `avg_response_time_ms`)
- Active connection gauges (calculates `active_users`)

---

## 6. SSL / TLS Setup (HTTPS & Secure WebSockets)

To serve the dashboard and WebSocket feeds over secure HTTPS (`wss://`), place a reverse proxy with automated Let's Encrypt certificates in front of Docker Compose.

### Option A: Using Caddy (Easiest, Automated SSL)
Install Caddy on the VPS host:
```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install -y caddy
```

Configure `/etc/caddy/Caddyfile`:
```caddy
shadow.yourdomain.com {
    # Reverse proxy to the Docker Dashboard/Nginx container on port 80
    reverse_proxy localhost:80 {
        header_up Host {host}
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-Port {server_port}
    }
}
```
Reload Caddy: `sudo systemctl reload caddy`. Caddy will automatically provision and renew TLS certificates.

---

## 7. Production Observability with Grafana & Loki

For centralized log searching and indexing across all microservices:

1. Launch the monitoring overlay:
   ```bash
   docker compose -f docker-compose.prod.yml -f monitoring/docker-compose.monitoring.yml up -d
   ```

2. Access Grafana:
   Navigate to `http://<YOUR_VPS_IP>:3001` (Default credentials: `admin` / `admin`).

3. Add Loki Data Source:
   - Go to **Connections > Data Sources > Add data source > Loki**.
   - URL: `http://loki:3100`.
   - Click **Save & Test**.

4. Run Structured Log Queries:
   In Grafana **Explore**, filter logs by service and risk level using LogQL:
   ```logql
   {job="shadow-traffic", service="shadow-backend"} |= "Warning"
   ```
   Or query by monitored site:
   ```logql
   {site_id="prod-ecommerce-web"} | json | level="WARNING"
   ```

---

## 8. Backup & Disaster Recovery Runbook

### Backing Up TimescaleDB Hypertables
Automate daily backups using cron:

```bash
#!/usr/bin/env bash
# /opt/scripts/backup-shadow-db.sh
set -eo pipefail

BACKUP_DIR="/var/backups/shadow-traffic"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

docker exec -t shadow-timescaledb-prod pg_dump -U shadow_admin shadow_traffic_prod | gzip > "$BACKUP_DIR/shadow_db_$TIMESTAMP.sql.gz"

# Retain last 14 days of backups
find "$BACKUP_DIR" -type f -name "shadow_db_*.sql.gz" -mtime +14 -delete
echo "[$(date)] Backup completed: shadow_db_$TIMESTAMP.sql.gz"
```

Make executable and add to crontab:
```bash
chmod +x /opt/scripts/backup-shadow-db.sh
sudo crontab -e
# Add line: 0 2 * * * /opt/scripts/backup-shadow-db.sh >> /var/log/shadow-backup.log 2>&1
```

### Restoring from Backup
```bash
# 1. Unzip the backup file
gunzip -k /var/backups/shadow-traffic/shadow_db_20260922_020000.sql.gz

# 2. Restore into TimescaleDB container
cat /var/backups/shadow-traffic/shadow_db_20260922_020000.sql | docker exec -i shadow-timescaledb-prod psql -U shadow_admin -d shadow_traffic_prod
```

### Zero-Downtime Rolling Service Update
To deploy updated container code without interrupting traffic:
```bash
git pull origin main
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d --no-deps backend
docker compose -f docker-compose.prod.yml up -d --no-deps prediction-engine
docker compose -f docker-compose.prod.yml up -d --no-deps dashboard
```
