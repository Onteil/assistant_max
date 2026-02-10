# Скрипт для запуска линтера и форматтера

# Активация виртуального окружения
.\venv\Scripts\Activate.ps1

# Проверка и автоисправление
Write-Host "Запуск проверки кода..." -ForegroundColor Green
ruff check . --fix

# Форматирование кода
Write-Host "`nФорматирование кода..." -ForegroundColor Green
ruff format .

Write-Host "`nГотово!" -ForegroundColor Green
