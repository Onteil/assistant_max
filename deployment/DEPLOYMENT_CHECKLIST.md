# i-TAT Bot Deployment Checklist

Use this checklist to ensure all steps are completed during deployment.

## Pre-Deployment

- [ ] Server provisioned (Ubuntu 20.04+ or Debian 11+)
- [ ] SSH access configured
- [ ] Domain name configured (if using)
- [ ] SSL certificate obtained (Let's Encrypt recommended)

## System Setup

- [ ] System packages installed:
  ```bash
  sudo apt update
  sudo apt install -y python3 python3-venv python3-pip postgresql redis-server nginx git
  ```

- [ ] PostgreSQL database created:
  ```bash
  sudo -u postgres psql
  CREATE DATABASE itat_bot;
  CREATE USER itat_user WITH PASSWORD 'secure_password';
  GRANT ALL PRIVILEGES ON DATABASE itat_bot TO itat_user;
  \q
  ```

- [ ] Redis server running:
  ```bash
  sudo systemctl start redis-server
  sudo systemctl enable redis-server
  ```

- [ ] Redis password configured (optional but recommended):
  ```bash
  sudo nano /etc/redis/redis.conf
  # Uncomment and set: requirepass your_redis_password
  sudo systemctl restart redis-server
  ```

## Application Setup

- [ ] Project directory created:
  ```bash
  sudo mkdir -p /opt/i-tat-bot
  sudo chown $USER:$USER /opt/i-tat-bot
  ```

- [ ] Code deployed to server:
  ```bash
  cd /opt
  sudo git clone https://github.com/aistrategiya/Aytat-bot.git i-tat-bot
  sudo chown -R $USER:$USER /opt/i-tat-bot
  cd i-tat-bot
  ```

- [ ] Virtual environment created:
  ```bash
  cd /opt/i-tat-bot
  python3 -m venv venv
  source venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt
  ```

- [ ] Environment file configured:
  ```bash
  cp .env.example .env
  nano .env
  ```

- [ ] Required environment variables set in .env:
  - [ ] `MAX_BOT_TOKEN` - MAX messenger bot token
  - [ ] `TG_BOT_TOKEN` - Telegram bot token (if using)
  - [ ] `DATABASE_URL` - PostgreSQL connection string
  - [ ] `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`
  - [ ] `HOST` - Public webhook URL
  - [ ] `WEBHOOK_PATH_MAX` - MAX webhook path
  - [ ] `ITAT_API_BASE_URL`, `ITAT_API_USERNAME`, `ITAT_API_PASSWORD`
  - [ ] `ADMIN_SECRET_KEY` - Generate with: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
  - [ ] `WEBHOOK_API_KEY` - Generate with: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
  - [ ] `ADMIN_USERNAME`, `ADMIN_PASSWORD` - Change from defaults
  - [ ] `INITIAL_ADMINS` - Configure initial administrators

- [ ] Database migrations applied:
  ```bash
  source venv/bin/activate
  alembic upgrade head
  ```

- [ ] Google Service Account configured (if using):
  ```bash
  # Upload service account JSON to services/google/secret.json
  ```

## Service Installation

- [ ] Systemd services installed:
  ```bash
  cd /opt/i-tat-bot/deployment
  sudo bash setup-services.sh
  ```

- [ ] Services enabled:
  ```bash
  sudo systemctl enable i-tat-bot
  sudo systemctl enable i-tat-celery-worker
  sudo systemctl enable i-tat-celery-beat
  ```

- [ ] Services started:
  ```bash
  sudo systemctl start i-tat-bot
  sudo systemctl start i-tat-celery-worker
  sudo systemctl start i-tat-celery-beat
  ```

- [ ] Services status verified:
  ```bash
  sudo systemctl status i-tat-bot
  sudo systemctl status i-tat-celery-worker
  sudo systemctl status i-tat-celery-beat
  ```

## Nginx Configuration

- [ ] Nginx configuration created:
  ```bash
  sudo nano /etc/nginx/sites-available/i-tat-bot
  # Copy configuration from deployment/README.md
  ```

- [ ] Site enabled:
  ```bash
  sudo ln -s /etc/nginx/sites-available/i-tat-bot /etc/nginx/sites-enabled/
  sudo nginx -t
  sudo systemctl reload nginx
  ```

- [ ] SSL certificate configured (Let's Encrypt):
  ```bash
  sudo apt install certbot python3-certbot-nginx
  sudo certbot --nginx -d your-domain.com
  ```

## Firewall Configuration

- [ ] UFW firewall configured:
  ```bash
  sudo ufw allow 22/tcp   # SSH
  sudo ufw allow 80/tcp   # HTTP
  sudo ufw allow 443/tcp  # HTTPS
  sudo ufw enable
  ```

## Webhook Configuration

- [ ] MAX webhook set:
  ```bash
  # Webhook is automatically set on application startup
  # Verify in logs: sudo journalctl -u i-tat-bot -n 50 | grep webhook
  ```

- [ ] Telegram webhook set (if using):
  ```bash
  # Webhook is automatically set on application startup
  ```

- [ ] Webhook URL accessible from internet:
  ```bash
  curl https://your-domain.com/max/webhook
  # Should return 405 Method Not Allowed (POST required)
  ```

## Testing

- [ ] Application accessible:
  ```bash
  curl http://localhost:8453/
  ```

- [ ] Admin panel accessible:
  - Open: https://your-domain.com/admin
  - Login with ADMIN_USERNAME and ADMIN_PASSWORD

- [ ] Bot responds to commands:
  - Send `/start` to MAX bot
  - Verify bot responds

- [ ] Celery worker processing tasks:
  ```bash
  cd /opt/i-tat-bot
  source venv/bin/activate
  python scripts/celery/check_celery_status.py
  ```

- [ ] Celery beat scheduling tasks:
  ```bash
  sudo journalctl -u i-tat-celery-beat -n 20
  # Should show scheduled tasks
  ```

- [ ] Database connection working:
  ```bash
  psql -h localhost -U itat_user -d itat_bot -c "SELECT COUNT(*) FROM users;"
  ```

## Monitoring Setup

- [ ] Log rotation configured:
  ```bash
  sudo cp deployment/logrotate/i-tat-celery /etc/logrotate.d/i-tat-celery
  sudo logrotate --debug /etc/logrotate.d/i-tat-celery
  ```

- [ ] Monitoring tools installed (optional):
  ```bash
  # htop for process monitoring
  sudo apt install htop
  
  # netdata for system monitoring
  bash <(curl -Ss https://my-netdata.io/kickstart.sh)
  ```

## Security Hardening

- [ ] Default credentials changed in .env
- [ ] SSH key-based authentication configured
- [ ] Root login disabled:
  ```bash
  sudo nano /etc/ssh/sshd_config
  # Set: PermitRootLogin no
  sudo systemctl restart sshd
  ```

- [ ] Fail2ban installed (optional):
  ```bash
  sudo apt install fail2ban
  sudo systemctl enable fail2ban
  sudo systemctl start fail2ban
  ```

- [ ] Database access restricted to localhost
- [ ] Redis password set and configured
- [ ] File permissions verified:
  ```bash
  sudo chown -R razrab:razrab /opt/i-tat-bot/media
  sudo chown -R razrab:razrab /opt/i-tat-bot/logs
  sudo chmod 600 /opt/i-tat-bot/.env
  ```

## Backup Configuration

- [ ] Database backup script created:
  ```bash
  sudo nano /usr/local/bin/backup-itat-db.sh
  ```
  ```bash
  #!/bin/bash
  BACKUP_DIR="/opt/backups/itat-bot"
  mkdir -p $BACKUP_DIR
  sudo -u postgres pg_dump itat_bot | gzip > $BACKUP_DIR/itat_bot_$(date +%Y%m%d_%H%M%S).sql.gz
  # Keep only last 30 days
  find $BACKUP_DIR -name "*.sql.gz" -mtime +30 -delete
  ```
  ```bash
  sudo chmod +x /usr/local/bin/backup-itat-db.sh
  ```

- [ ] Backup cron job configured:
  ```bash
  sudo crontab -e
  # Add: 0 2 * * * /usr/local/bin/backup-itat-db.sh
  ```

- [ ] Media files backup configured:
  ```bash
  # Add to backup script or use rsync
  rsync -av /opt/i-tat-bot/media/ /opt/backups/itat-bot/media/
  ```

## Documentation

- [ ] Deployment details documented:
  - Server IP/hostname
  - Database credentials (stored securely)
  - API keys and tokens (stored securely)
  - Domain name and SSL certificate info

- [ ] Team notified of deployment
- [ ] Access credentials shared securely

## Post-Deployment

- [ ] Monitor logs for errors:
  ```bash
  sudo journalctl -u i-tat-bot -f
  sudo journalctl -u i-tat-celery-worker -f
  ```

- [ ] Test all bot features:
  - User registration
  - Ticket creation (invoice, support)
  - Admin commands
  - NPS surveys
  - Escalations

- [ ] Verify scheduled tasks running:
  ```bash
  # Check Celery beat schedule
  sudo journalctl -u i-tat-celery-beat --since "1 hour ago"
  ```

- [ ] Monitor resource usage:
  ```bash
  htop
  df -h
  free -h
  ```

## Rollback Plan

In case of issues, document rollback steps:

1. Stop new services:
   ```bash
   sudo systemctl stop i-tat-celery-beat
   sudo systemctl stop i-tat-celery-worker
   sudo systemctl stop i-tat-bot
   ```

2. Restore previous code version:
   ```bash
   cd /opt/i-tat-bot
   git log --oneline -10  # Find previous working commit
   git checkout <previous-commit-hash>
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. Restore database (if needed):
   ```bash
   sudo -u postgres psql itat_bot < backup_YYYYMMDD_HHMMSS.sql
   # Or rollback migrations:
   cd /opt/i-tat-bot
   source venv/bin/activate
   alembic downgrade -1  # Rollback one migration
   ```

4. Start services:
   ```bash
   sudo systemctl start i-tat-bot
   sudo systemctl start i-tat-celery-worker
   sudo systemctl start i-tat-celery-beat
   ```

## Notes

- Deployment date: _______________
- Deployed by: _______________
- Server: _______________
- Issues encountered: _______________
- Resolution: _______________
