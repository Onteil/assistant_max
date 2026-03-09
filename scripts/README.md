# Scripts Directory

This directory contains utility scripts and tools for managing the i-TAT bot application.

## Structure

```
scripts/
├── celery/           # Celery management scripts
├── utils/            # Database and user management utilities
├── generate_*.py     # Diagram generation scripts
└── *.ps1, *.sh       # Shell scripts for common tasks
```

## Celery Management (`celery/`)

Scripts for managing Celery workers and tasks:

- `start_celery_beat.py` - Start Celery beat scheduler
- `start_celery_worker.py` - Start Celery worker
- `restart_celery_worker.py` - Restart Celery worker
- `clear_celery_redis.py` - Clear Celery data from Redis
- `check_celery_status.py` - Check Celery worker status
- `check_celery_tasks.py` - List scheduled Celery tasks
- `debug_celery_task.py` - Debug specific Celery task
- `check_task_result.py` - Check Celery task result
- `stop_all_celery.ps1` - Stop all Celery processes (PowerShell)

## Utility Scripts (`utils/`)

Database and user management utilities:

### User Management
- `add_staff_member.py` - Add a user as staff member
- `find_test_user.py` - Find test users in database
- `check_specific_user.py` - Check specific user details
- `check_user_22.py` - Check user with ID 22
- `check_nps_users.py` - Check NPS survey users
- `reset_user_status.py` - Reset user registration status
- `update_staff_max_id.py` - Update staff MAX messenger ID

### Registration Management
- `manage_registration.py` - Manage user registrations
- `send_registration_webhook.py` - Send registration webhook
- `send_rejection_webhook.py` - Send rejection webhook

### Ticket & Escalation
- `add_test_escalation.py` - Add test escalation
- `check_ticket_37.py` - Check ticket #37 details
- `check_staff_member.py` - Check staff member details

### System Management
- `init_admins.py` - Initialize admin users
- `change_work_mode.py` - Change work mode (calendar)
- `check_action_logs.py` - Check action logs
- `analyze_max_api_structure.py` - Analyze MAX API structure

## Diagram Generation

- `generate_er_diagram.py` - Generate ER diagram
- `generate_interactive_diagram.py` - Generate interactive diagram
- `generate_mermaid_diagram.py` - Generate Mermaid diagram

## Shell Scripts

- `generate_diagrams.ps1` / `.sh` - Generate all diagrams
- `lint.ps1` - Run linter (Ruff)
- `migrate.ps1` - Run database migrations

## Usage

All scripts should be run from the project root directory:

```bash
# Activate virtual environment first
. .\venv\Scripts\Activate.ps1  # Windows PowerShell
# or
source venv/bin/activate  # Linux/Mac

# Run a script
python scripts/utils/add_staff_member.py
python scripts/celery/start_celery_worker.py
```

## Notes

- All Python scripts automatically add the project root to `sys.path`
- Scripts use imports from the root level (e.g., `from constants import ...`)
- Database scripts require active database connection (check `.env` file)
- Celery scripts require Redis connection
