# Последовательность вызовов i-TAT API при регистрации в MAX боте

## Процесс регистрации (команда /start)

Во время регистрации нового пользователя в MAX боте вызываются **три метода** i-TAT API в следующей последовательности:

### 1. **POST /assets/check_inn** - Проверка ИНН организации

**Когда вызывается:** После того, как пользователь вводит ИНН организации

**Файл:** `bots/max_bot/handlers/user/registration.py` (функция `process_inn`)

**Параметры запроса:**
```json
{
  "messenger": "max",
  "inn": "1234567890"
}
```

**Примечание:** `user_id` НЕ передается, так как пользователь еще не зарегистрирован в i-TAT

**Цель:** Проверить, что ИНН существует и валиден в базе i-TAT

---

### 2. **POST /assets/check_key** - Проверка конфликта ключа

**Когда вызывается:** После того, как пользователь вводит номер ключа Гранд-сметы

**Файл:** `bots/max_bot/handlers/user/registration.py` (функция `process_key`)

**Параметры запроса:**
```json
{
  "grand_key": "MG123456"
}
```

**Примечание:** `user_id` НЕ передается, так как пользователь еще не зарегистрирован в i-TAT

**Цель:** Проверить, не занят ли ключ другим пользователем

**Возможные ответы:**
- `{"status": "available"}` - ключ свободен, регистрация продолжается
- `{"status": "conflict", "owner": "Иван Иванов +7912-XXX-XX-89"}` - ключ занят, пользователю предлагается выбор:
  - Ввести другой ключ
  - Продолжить с конфликтом (ключ будет добавлен со статусом `PENDING_REVIEW`)

---

### 3. **POST /user/register** - Регистрация пользователя

**Когда вызывается:** После успешного прохождения всех шагов регистрации (телефон, имя, email, ИНН, ключ)

**Файл:** `bots/max_bot/handlers/user/registration.py` (функция `submit_registration`)

**Параметры запроса:**
```json
{
  "messenger": "max",
  "user_id": 123456789,
  "phone": "+79991234567",
  "name": "Иван",
  "surname": "Иванов",
  "inn": "1234567890",
  "grand_key": "MG123456",
  "email": "ivan@example.com"
}
```

**Примечание:** На этом этапе `user_id` (MAX user ID) уже передается, так как пользователь создан в локальной БД

**Цель:** Зарегистрировать пользователя в системе i-TAT

**После успешной регистрации:**
- Статус пользователя в локальной БД меняется на `PENDING`
- Пользователь видит сообщение о том, что регистрация отправлена на проверку
- FSM состояние очищается

---

## Схема процесса

```
/start
  ↓
[Ввод телефона]
  ↓
[Ввод имени]
  ↓
[Ввод email (опционально)]
  ↓
[Ввод ИНН]
  ↓
✅ API: POST /assets/check_inn (без user_id)
  ↓
[Ввод ключа]
  ↓
✅ API: POST /assets/check_key (без user_id)
  ↓
[Если конфликт - выбор действия]
  ↓
✅ API: POST /user/register (с user_id)
  ↓
[Статус: PENDING]
```

---

## Важные детали

### Почему user_id не передается в check_inn и check_key?

На момент проверки ИНН и ключа пользователь:
- ✅ Создан в локальной БД бота (есть внутренний `id`)
- ✅ Имеет MAX user ID (из мессенджера)
- ❌ **НЕ зарегистрирован в системе i-TAT**

Поэтому методы `check_inn` и `check_key` были обновлены, чтобы принимать `user_id` как **опциональный параметр**.

### Когда user_id передается?

`user_id` передается в методы проверки только когда пользователь **уже зарегистрирован** в i-TAT:
- В потоке создания счета (invoice flow)
- В потоке редактирования профиля (profile flow)
- В потоке технической поддержки (support flow)

---

## Изменения в коде (2024-03-24)

### services/i_tat_service.py

```python
# ДО изменений
async def check_inn(self, messenger: str, user_id: int, inn: str):
    payload = {"messenger": messenger, "user_id": user_id, "inn": inn}

async def check_key_conflict(self, grand_key: str, user_id: int | None = None):
    if user_id is None:
        raise ValueError("user_id is required")
    payload = {"grand_key": grand_key, "user_id": user_id}

# ПОСЛЕ изменений
async def check_inn(self, messenger: str, inn: str, user_id: int | None = None):
    payload = {"messenger": messenger, "inn": inn}
    if user_id is not None:
        payload["user_id"] = user_id

async def check_key_conflict(self, grand_key: str, user_id: int | None = None):
    payload = {"grand_key": grand_key}
    if user_id is not None:
        payload["user_id"] = user_id
```

### bots/max_bot/handlers/user/registration.py

```python
# ДО изменений (закомментировано)
# api_response = await itat_client.check_inn(
#     messenger="max",
#     user_id=max_user_id,  # ❌ Передавался user_id
#     inn=inn
# )

# ПОСЛЕ изменений (раскомментировано)
api_response = await itat_client.check_inn(
    messenger="max",
    inn=inn  # ✅ user_id не передается
)
```

---

## Тестирование

Для проверки работы регистрации:

1. Запустить бота: `/start`
2. Пройти все шаги регистрации
3. Проверить логи на наличие вызовов:
   - `[MOCK] Checking INN: inn=..., user=None, messenger=max`
   - `[MOCK] Checking key conflict: key=..., user=None`
   - `[MOCK] Registering user: user_id=..., phone=...`

4. Убедиться, что регистрация завершается успешно со статусом `PENDING`


---

## Изменения в API (2026-03-24)

### POST /tickets/log - staff_id теперь обязателен

**Проблема:** API начал возвращать ошибку 400 с сообщением "Отсутствует обязательный параметр: staff_id"

**Решение:** Параметр `staff_id` теперь обязателен для всех вызовов `/tickets/log`

**Использование:**
- Для действий сотрудников: передавайте реальный `staff_id`
- Для действий пользователя/системы: передавайте `staff_id = 0`

**Примеры:**

```python
# Создание заявки пользователем
await api_client.log_ticket(
    ticket_id="TKT_12345",
    messenger="max",
    user_id=123456789,
    staff_id=0,  # ← Обязательно! 0 = действие пользователя
    ticket_type="Техподдержка",
    status="Новое",
    comment="Заявка создана через MAX бот"
)

# Назначение заявки на сотрудника
await api_client.log_ticket(
    ticket_id="TKT_12345",
    messenger="max",
    user_id=123456789,
    staff_id=987654321,  # ← ID сотрудника
    ticket_type="Техподдержка",
    status="В работе",
    comment="Назначено на менеджера"
)
```

**Обновленные файлы:**
- `bots/max_bot/utils/itat_logging.py` - добавлен `staff_id=0` для пользовательских действий
- `docs/api/I-TAT-API-REFERENCE.md` - обновлена документация
