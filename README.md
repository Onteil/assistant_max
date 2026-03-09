# i-TAT Bot Application

Multi-messenger bot application supporting Telegram and MAX messenger for i-TAT service management.

## Project Structure

```
i-tat-bot/
├── alembic/              # Database migrations
├── api/                  # FastAPI application and admin panel
├── bots/                 # Bot implementations
│   ├── max_bot/         # MAX messenger bot
│   └── tg_bot/          # Telegram bot
├── celery_app/          # Celery tasks and configuration
├── database/            # Database models and session management
├── docs/                # Project documentation
├── scripts/             # Utility scripts and tools
│   ├── celery/         # Celery management scripts
│   └── utils/          # Database and user management utilities
├── services/            # Business logic and external API clients
├── tests/               # Test suite
│   ├── manual/         # Manual test scripts
│   ├── unit/           # Unit tests
│   └── integration/    # Integration tests
├── utils/               # Shared utilities
├── constants.py         # Application constants and configuration
├── loaders.py           # Bot and dispatcher initialization
└── main.py              # Application entry point
```

## Core Files

- `main.py` - FastAPI application entry point, webhook handlers
- `loaders.py` - Bot instances and dispatcher initialization
- `constants.py` - Environment variables and application constants
- `alembic.ini` - Database migration configuration
- `pyproject.toml` - Project metadata and dependencies
- `requirements.txt` - Python dependencies

## Quick Start

### Development Setup

#### Prerequisites

- Python 3.11+
- PostgreSQL
- Redis (optional, for production)

#### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/aistrategiya/Aytat-bot.git
   cd Aytat-bot
   ```

2. Create virtual environment:
   ```bash
   python -m venv venv
   ```

3. Activate virtual environment:
   ```bash
   # Windows PowerShell
   . .\venv\Scripts\Activate.ps1
   
   # Linux/Mac
   source venv/bin/activate
   ```

4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

5. Configure environment:
   ```bash
   cp .env.dist .env
   # Edit .env with your configuration
   ```

6. Run migrations:
   ```bash
   alembic upgrade head
   ```

### Production Deployment

For production deployment on Ubuntu/Debian server:

```bash
# Quick automated installation
wget https://raw.githubusercontent.com/aistrategiya/Aytat-bot/main/deployment/install.sh
sudo bash install.sh
```

Or follow the detailed guide:

📖 **[Complete Deployment Guide](deployment/QUICK_START.md)** | 📖 **[Руководство на русском](DEPLOYMENT_RU.md)**

The deployment includes:
- Automated installation script
- systemd services for FastAPI, Celery worker, and Celery beat
- Nginx configuration
- SSL certificate setup
- Security hardening

See `deployment/` directory for:
- `INDEX.md` - Documentation navigation
- `QUICK_START.md` - Step-by-step deployment guide
- `DEPLOYMENT_CHECKLIST.md` - Deployment verification checklist
- `COMMANDS_CHEATSHEET.md` - Command reference
- `README.md` - Complete deployment documentation

### Running the Application

```bash
# Start FastAPI application
python main.py

# Start Celery worker (separate terminal)
python scripts/celery/start_celery_worker.py

# Start Celery beat (separate terminal)
python scripts/celery/start_celery_beat.py
```

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run specific test categories
pytest tests/unit/
pytest tests/integration/

# Run with coverage
pytest --cov=. --cov-report=html
```

### Code Quality

```bash
# Run linter
.\scripts\lint.ps1

# Or manually
ruff check .
```

### Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1
```

## Scripts

See `scripts/README.md` for detailed documentation on available utility scripts.

### Common Scripts

```bash
# User management
python scripts/utils/add_staff_member.py
python scripts/utils/find_test_user.py

# Celery management
python scripts/celery/start_celery_worker.py
python scripts/celery/check_celery_status.py

# Diagram generation
python scripts/generate_interactive_diagram.py
```

## Documentation

Comprehensive documentation is available in the `docs/` directory:

- `docs/api/` - External API references (i-TAT, MAX)
- `docs/architecture/` - System design and structure
- `docs/scenarios/` - Business logic and user flows
- `docs/MAX-API/` - MAX API library documentation

See `docs/README.md` for the complete documentation index.

## Tech Stack

- **Python 3.11+** - Primary language
- **FastAPI** - Web framework
- **PostgreSQL** - Database
- **SQLAlchemy 2.0** - ORM
- **Alembic** - Migrations
- **Redis** - Caching and FSM storage
- **Celery** - Background tasks
- **Aiogram 3.24.0** - Telegram bot framework
- **maxapi** - MAX messenger bot framework

## Environment Variables

Key environment variables (see `.env.dist` for complete list):

- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection string
- `TELEGRAM_BOT_TOKEN` - Telegram bot token
- `MAX_BOT_TOKEN` - MAX bot token
- `WEBHOOK_PATH_TG` - Telegram webhook path
- `WEBHOOK_PATH_MAX` - MAX webhook path
- `ITAT_API_BASE_URL` - i-TAT API base URL
- `ITAT_API_USERNAME` - i-TAT API username
- `ITAT_API_PASSWORD` - i-TAT API password

## Contributing

1. Create a feature branch
2. Make your changes
3. Run tests and linter
4. Submit a pull request

## License

[Add license information]

## Support

For issues and questions, please refer to the project documentation or contact the development team.
