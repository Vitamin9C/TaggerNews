# TaggerNews Deployment Guide

This guide covers deploying TaggerNews to a VPS (Virtual Private Server) running Ubuntu/Debian.

## Architecture Overview

TaggerNews is a Hacker News aggregator with AI-powered summaries. It runs as a single FastAPI process with built-in APScheduler background jobs:

| Job               | Default Interval | Description                                            |
| ----------------- | ---------------- | ------------------------------------------------------ |
| Continuous scrape | 2 min            | Polls HN API for new items since the last known ID     |
| Backfill scrape   | 5 min            | Walks backward through older HN items in batches       |
| Recovery          | 5 min            | Retries stories that failed summarization or tagging   |
| Agent analysis    | Weekly           | Analyzes tag taxonomy health and proposes improvements |

All jobs share the PostgreSQL database. Summarization and tagging call the OpenAI API (GPT-4o-mini by default).

## Prerequisites

- VPS with Ubuntu 22.04+ or Debian 12+
- Minimum specs: 1 vCPU, 1GB RAM, 20GB storage
- Domain name (optional, for HTTPS)
- SSH access to your server
- OpenAI API key with billing enabled (summarization costs ~$0.01-0.05/day at default scrape rates)

## 1. Server Setup

### Update System

```bash
sudo apt update && sudo apt upgrade -y
```

### Install Required Packages

```bash
sudo apt install -y \
    docker.io \
    docker-compose \
    nginx \
    certbot \
    python3-certbot-nginx \
    git \
    ufw
```

### Enable Docker

```bash
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker $USER
```

Log out and back in for group changes to take effect.

## 2. Firewall Configuration

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

## 3. Clone and Configure Application

### Clone Repository

```bash
cd /opt
sudo mkdir taggernews
sudo chown $USER:$USER taggernews
git clone <your-repo-url> taggernews
cd taggernews
```

### Create Environment File

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

**Required** production values:

```env
# Environment
ENVIRONMENT=production

# Database (password must match POSTGRES_PASSWORD below)
DATABASE_URL=postgresql+asyncpg://postgres:YOUR_STRONG_PASSWORD@postgres:5432/taggernews
POSTGRES_PASSWORD=YOUR_STRONG_PASSWORD

# OpenAI API Key (required for summarization and tagging)
OPENAI_API_KEY=sk-your-production-key

# API Authentication (protects write endpoints like /refresh, agent approve/execute)
API_KEY=your-random-secret-key-here
```

**Optional** tuning (shown with defaults):

```env
# HN Scraper
HN_API_BASE_URL=https://hacker-news.firebaseio.com/v0
SCRAPE_INTERVAL_MINUTES=5
TOP_STORIES_COUNT=30

# Enhanced Scraper Tuning
SCRAPER_BACKFILL_BATCH_SIZE=100
SCRAPER_BACKFILL_MAX_BATCHES=50
SCRAPER_BACKFILL_DAYS_PROD=30
SCRAPER_CONTINUOUS_BATCH_SIZE=50
SCRAPER_CONTINUOUS_INTERVAL_MINUTES=2
SCRAPER_BACKFILL_INTERVAL_MINUTES=5
SCRAPER_RATE_LIMIT_DELAY_MS=50

# Recovery
RECOVERY_INTERVAL_MINUTES=5

# Summarization
SUMMARIZATION_MODEL=gpt-4o-mini
SUMMARIZATION_BATCH_SIZE=5

# Agent Configuration (tag taxonomy management)
AGENT_ANALYSIS_WINDOW_DAYS=30
AGENT_MIN_TAG_USAGE=3
AGENT_MAX_PROPOSALS_PER_RUN=10
AGENT_OPENAI_MODEL=gpt-4o-mini
AGENT_RUN_INTERVAL_WEEKS=1
AGENT_ENABLE_AUTO_APPROVE=false
AGENT_AUTO_APPROVE_MAX_AFFECTED=5
```

### Create Production Docker Compose

Create `docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    container_name: taggernews-db
    restart: always
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: taggernews
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./database/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - taggernews-net

  app:
    build: .
    container_name: taggernews-app
    restart: always
    ports:
      - "127.0.0.1:8000:8000"
    env_file:
      - .env
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - ./templates:/app/templates:ro
      - ./static:/app/static:ro
    networks:
      - taggernews-net

volumes:
  postgres_data:

networks:
  taggernews-net:
    driver: bridge
```

## 4. Database Setup

The database schema is initialized in two stages:

1. **init.sql** - Base tables and triggers, run automatically on first `postgres` container start via the `/docker-entrypoint-initdb.d/` mount
2. **Alembic migrations** - Schema changes added after initial release

```bash
# Build the app image
docker-compose -f docker-compose.prod.yml build

# Start postgres first (triggers init.sql on first run)
docker-compose -f docker-compose.prod.yml up -d postgres

# Wait for postgres to be ready, then run migrations
docker-compose -f docker-compose.prod.yml run --rm app alembic upgrade head
```

## 5. Start Application

```bash
docker-compose -f docker-compose.prod.yml up -d
```

Verify it's running:

```bash
docker-compose -f docker-compose.prod.yml ps
docker-compose -f docker-compose.prod.yml logs -f app
```

You should see log lines for "Starting TaggerNews application" and the scheduler starting its jobs.

## 6. Nginx Reverse Proxy

### Create Nginx Config

```bash
sudo nano /etc/nginx/sites-available/taggernews
```

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        proxy_read_timeout 86400;
    }

    location /static/ {
        alias /opt/taggernews/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

### Enable Site

```bash
sudo ln -s /etc/nginx/sites-available/taggernews /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## 7. SSL/TLS with Let's Encrypt

```bash
sudo certbot --nginx -d your-domain.com
```

Follow the prompts. Certbot will automatically configure HTTPS.

### Auto-Renewal

Certbot sets up auto-renewal by default. Test it:

```bash
sudo certbot renew --dry-run
```

## 8. Systemd Service (Optional)

For automatic startup on server reboot, create `/etc/systemd/system/taggernews.service`:

```ini
[Unit]
Description=TaggerNews Docker Compose
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/taggernews
ExecStart=/usr/bin/docker-compose -f docker-compose.prod.yml up -d
ExecStop=/usr/bin/docker-compose -f docker-compose.prod.yml down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

Enable:

```bash
sudo systemctl enable taggernews
sudo systemctl start taggernews
```

## 9. Maintenance

### View Logs

```bash
# Application logs
docker-compose -f docker-compose.prod.yml logs -f app

# Database logs
docker-compose -f docker-compose.prod.yml logs -f postgres

# Filter for scraper activity
docker-compose -f docker-compose.prod.yml logs app | grep -i "scrape\|backfill\|continuous"
```

### Restart Services

```bash
docker-compose -f docker-compose.prod.yml restart app
```

### Update Application

```bash
cd /opt/taggernews
git pull origin main
docker-compose -f docker-compose.prod.yml build
docker-compose -f docker-compose.prod.yml run --rm app alembic upgrade head
docker-compose -f docker-compose.prod.yml up -d
```

### Database Backup

```bash
# Create backup
docker exec taggernews-db pg_dump -U postgres taggernews > backup_$(date +%Y%m%d).sql

# Restore backup
docker exec -i taggernews-db psql -U postgres taggernews < backup_20260101.sql
```

### Automated Daily Backups

Add to crontab (`crontab -e`):

```bash
0 3 * * * docker exec taggernews-db pg_dump -U postgres taggernews | gzip > /opt/taggernews/backups/backup_$(date +\%Y\%m\%d).sql.gz
0 4 * * * find /opt/taggernews/backups -mtime +30 -delete
```

### Clean Up Docker

```bash
# Remove unused images
docker image prune -a

# Remove unused volumes (careful - don't run while services are stopped!)
docker volume prune
```

## 10. Monitoring

### Basic Health Check

Add to crontab (`crontab -e`):

```bash
*/5 * * * * curl -sf http://localhost:8000/ > /dev/null || echo "TaggerNews down" | mail -s "Alert" your@email.com
```

### Resource Monitoring

```bash
# View container stats
docker stats taggernews-app taggernews-db
```

## Troubleshooting

### Application Won't Start

1. Check logs: `docker-compose -f docker-compose.prod.yml logs app`
2. Verify environment: `docker-compose -f docker-compose.prod.yml config`
3. Check database connectivity: `docker-compose -f docker-compose.prod.yml exec postgres pg_isready -U postgres`

### Database Connection Errors

1. Ensure postgres is healthy: `docker-compose -f docker-compose.prod.yml ps`
2. Verify `DATABASE_URL` format matches the `POSTGRES_PASSWORD` you set
3. Check postgres logs for authentication failures

### Nginx 502 Bad Gateway

1. Ensure app container is running: `docker ps`
2. Verify the app binds to `127.0.0.1:8000`: `curl http://127.0.0.1:8000/`
3. Check app logs for startup errors

### OpenAI API Errors

1. Verify `OPENAI_API_KEY` is set correctly in `.env`
2. Check API quota/billing at https://platform.openai.com/usage
3. Review summarizer logs: `docker-compose -f docker-compose.prod.yml logs app | grep -i "openai\|summariz"`

### Scraper Not Collecting Stories

1. Check scheduler is running: look for "Starting scheduled" in logs
2. Verify HN API is reachable from container: `docker-compose -f docker-compose.prod.yml exec app curl -s https://hacker-news.firebaseio.com/v0/maxitem.json`
3. Check scraper state: query the `scraper_state` table for `current_item_id` and `status`

## Security Checklist

- [ ] Strong database password (not default `postgres`)
- [ ] `.env` file has restricted permissions (`chmod 600 .env`)
- [ ] Firewall enabled with only necessary ports open (22, 80, 443)
- [ ] SSL/TLS configured for production domain
- [ ] App port bound to `127.0.0.1` only (not exposed to public)
- [ ] Regular database backups configured
- [ ] Docker images kept up to date
- [ ] OpenAI API key has billing limits set
