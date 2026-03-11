# Migration management script for Alembic

param(
    [Parameter(Position=0)]
    [string]$Command = "help",
    
    [Parameter(Position=1)]
    [string]$Message = ""
)

# Activate virtual environment
.\venv\Scripts\Activate.ps1

switch ($Command) {
    "create" {
        if ($Message -eq "") {
            Write-Host "Error: migration message required" -ForegroundColor Red
            Write-Host "Example: .\migrate.ps1 create 'add user table'" -ForegroundColor Yellow
            exit 1
        }
        Write-Host "Creating migration: $Message" -ForegroundColor Green
        alembic revision --autogenerate -m $Message
    }
    
    "upgrade" {
        Write-Host "Applying migrations..." -ForegroundColor Green
        alembic upgrade head
    }
    
    "downgrade" {
        Write-Host "Rolling back last migration..." -ForegroundColor Yellow
        alembic downgrade -1
    }
    
    "current" {
        Write-Host "Current database version:" -ForegroundColor Cyan
        alembic current
    }
    
    "history" {
        Write-Host "Migration history:" -ForegroundColor Cyan
        alembic history --verbose
    }
    
    "help" {
        Write-Host @"
Usage: .\migrate.ps1 <command> [parameters]

Commands:
  create <message>  - Create new migration (autogenerate)
  upgrade           - Apply all migrations
  downgrade         - Rollback last migration
  current           - Show current database version
  history           - Show migration history
  help              - Show this help

Examples:
  .\migrate.ps1 create "add user table"
  .\migrate.ps1 upgrade
  .\migrate.ps1 current
"@ -ForegroundColor Cyan
    }
    
    default {
        Write-Host "Unknown command: $Command" -ForegroundColor Red
        Write-Host "Use '.\migrate.ps1 help' for help" -ForegroundColor Yellow
    }
}
