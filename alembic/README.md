# Alembic Migrations

Управление миграциями базы данных для проекта АЙТАТ-Диспетчер.

## Установка

Все зависимости уже установлены:
- alembic
- aiogram
- asyncpg

## Конфигурация

Alembic настроен для работы с:
- Асинхронным подключением через asyncpg
- URL базы данных из `.env` файла через `constants.py`
- Автоматическим форматированием миграций через ruff

## Основные команды

### Создание новой миграции (автогенерация)
```powershell
.\venv\Scripts\Activate.ps1
alembic revision --autogenerate -m "описание изменений"
```

### Создание пустой миграции
```powershell
alembic revision -m "описание изменений"
```

### Применение миграций
```powershell
# Применить все миграции
alembic upgrade head

# Применить конкретную миграцию
alembic upgrade <revision_id>

# Применить следующую миграцию
alembic upgrade +1
```

### Откат миграций
```powershell
# Откатить одну миграцию
alembic downgrade -1

# Откатить до конкретной миграции
alembic downgrade <revision_id>

# Откатить все миграции
alembic downgrade base
```

### Просмотр истории
```powershell
# Текущая версия БД
alembic current

# История миграций
alembic history

# Подробная история
alembic history --verbose
```

## Структура

```
alembic/
├── versions/          # Файлы миграций
├── env.py            # Конфигурация окружения (настроен для async)
├── script.py.mako    # Шаблон для новых миграций
└── README.md         # Этот файл
```

## Важно

⚠️ **Перед применением миграций:**
1. Убедитесь, что структура моделей в `database/models.py` финальная
2. Проверьте сгенерированную миграцию перед применением
3. Сделайте бэкап базы данных (если продакшн)

## Workflow

1. Изменяете модели в `database/models.py`
2. Создаете миграцию: `alembic revision --autogenerate -m "add user table"`
3. Проверяете сгенерированный файл в `alembic/versions/`
4. Применяете миграцию: `alembic upgrade head`

## Примеры

### Добавление новой таблицы
```python
# В database/models.py добавляете новую модель
class NewTable(Base):
    __tablename__ = "new_table"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
```

```powershell
# Создаете миграцию
alembic revision --autogenerate -m "add new_table"

# Применяете (когда готовы)
alembic upgrade head
```

### Изменение существующей таблицы
```python
# Изменяете модель в database/models.py
class User(Base):
    # ... существующие поля
    new_field = Column(String, nullable=True)  # новое поле
```

```powershell
alembic revision --autogenerate -m "add new_field to user"
alembic upgrade head
```

## Troubleshooting

### Ошибка подключения к БД
Проверьте `DB_URL` в `.env` файле

### Миграция не применяется
```powershell
# Проверьте текущую версию
alembic current

# Проверьте историю
alembic history
```

### Конфликт миграций
```powershell
# Откатите до нужной версии
alembic downgrade <revision_id>

# Примените заново
alembic upgrade head
```
