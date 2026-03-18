Assistant HTTP API methods.
Base path: /hs/assistant/v1

1) GET /getinfo
   Returns this help text.

2) GET /system/staff
   Returns staff list.
   Response: status, staff

3) POST /user/register
   Required JSON: messenger, user_id, phone, name, surname, inn, grand_key
   Optional JSON: email
   Errors: 400, 409, 500

4) GET /user/assets?user_id=<number>
   Returns user assets.
   Errors: 400, 404, 500

5) GET /user/status?user_id=<number>
   Returns user status.
   Errors: 400, 404, 500

6) POST /tickets/log
   Required JSON: ticket_id, messenger, user_id, staff_id, type, status, created_at, updated_at
   Optional JSON: history_link, comment
   Errors: 400, 404, 500

7) POST /assets/check_key
   Required JSON: grand_key, user_id
   Response status: available | conflict
   Errors: 400, 500

8) POST /assets/check_inn
   Required JSON: messenger, user_id, inn
   Errors: 400, 404, 500

9) POST /user/assets/update
   Required JSON: messenger, user_id, asset_type, action, value
   asset_type: inn | grand_key
   action: add | remove
   Errors: 400, 404, 409, 500

10) POST /system/staff/update
    Required JSON: messenger, user_id, action
    Optional JSON: role, position, is_active, reserves
    action: upsert | deactivate
    Errors: 400, 404, 500

11) POST /assets/resolve_conflict
    Required JSON: key_number, action, new_user_phone, old_user_phone
    Optional JSON: reason
    action: transfer | reject
    Errors: 400, 404, 500

12) POST /user/change_phone
    Required JSON: messenger (or messenger_type), user_id, old_phone, new_phone, staff_id
    Errors: 400, 404, 409, 500

13) POST /system/audit_log
    Required JSON: messenger, action_type
    Optional JSON: action_timestamp, user_id, staff_id, ticket_id, action_details
    Errors: 400, 500

14) GET /tickets/<ticket_id>/history
    Returns ticket history.
    Errors: 400, 404, 500

15) POST /system/webhook_retry/run
    Optional JSON: limit, max_attempts
    Response: status, message, limit, max_attempts, checked, processed, succeeded, failed, skipped_max_attempts
    Errors: 500

16) GET /system/webhook_retry/status
    Optional query: max_attempts
    Response: total, queued, success, failed, dead_letter, queued_at_max_attempts

17) Webhook bridge via POST /system/audit_log
    action_type routed to outgoing webhook:
    registration_status, registration_decision, registration_approved, registration_rejected,
    manager_assignment, subscription_status_change, ticket_reassignment, payment_confirmed




Изменения в текущих методах API, новые методы
Доработка метода POST user/register/

Добавление поля email (при регистрации пользователь опционально может ввести email), флаг messenger

Сценарий: Вызывается в конце воронки регистрации, когда пользователь заполнил профиль.

Формат запроса (JSON):

{

"messenger": "max", // Обязательно: telegram или max

"user_id": 12345678, // ID в мессенджере (BigInt)

"phone": "79991234567", // Сотовый номер (ключевой ID)

"name": "Мария",

"surname": "Иванова",

"email": "ivanova@mail.ru", // Опционально: может быть null

"inn": "1655060636", // ИНН организации

"grand_key": "00000_00001" // Номер ключа

}

Доработка метода POST /tickets/log регистрирует обращение пользователя в периодическом регистре сведений.

Текущие параметры:

- ticket_id (string, обязательное) - идентификатор обращения

- user_id (number, обязательное) - идентификатор пользователя

- type (string, обязательное) - тип обращения из перечисления ай_ТипОбращения (Счет, Техподдержка, Продление, Конфликт ключа, Перенос номера)

- status (string, обязательное) - статус обращения из перечисления ай_СтатусыОбращений (Новое, В работе, Ожидание клиента, Закрыто, Отменено)

- history_link (string, необязательное) - ссылка на историю чата

- comment (string, необязательное) - комментарий сотрудника

Проблема

Текущая реализация метода не позволяет передать важную информацию для полноценного аудита действий с заявками.

Когда вызывается ботом:

При создании заявки.
При взятии заявки в работу сотрудником.
При переназначении (трансфере) заявки на другого сотрудника.
При закрытии или отмене заявки.
Недостающие данные:

1. Отсутствие информации о сотруднике

  - В боте заявки назначаются на конкретных сотрудников (assigned_staff_id)

  - Действия с заявками выполняются сотрудниками (назначение, изменение статуса, закрытие)

  - Метод не принимает идентификатор сотрудника, что не позволяет отследить, кто именно выполнил действие

2. Отсутствие временных меток

  - В боте все записи имеют created_at и updated_at для отслеживания истории изменений

  - Метод не принимает временные метки, что затрудняет синхронизацию данных между системами

  - Невозможно точно определить, когда было создано или изменено обращение в боте

Предлагаемая доработка: добавить следующие параметры в тело запроса:

json

{

  "ticket_id": "TKT_12345",

  "user_id": 123456789,

  "type": "Техподдержка",

  "status": "Новое",

  "history_link": "https://...",

  "comment": "Клиент запросил помощь",

 

  // НОВЫЕ ПАРАМЕТРЫ:

"messenger": "max", // или "telegram"

  "staff_id": 987654321, // ID сотрудника

  "created_at": "2026-02-27T10:30:00Z", // Дата создания

  "updated_at": "2026-02-27T10:35:00Z" // Дата обновления

}

Доработка метода: Управление справочником сотрудников (POST /system/staff/update)

Цель: Синхронизация изменений в штате сотрудников, произведенных через интерфейс администратора в боте, с базой 1С/CRM.

Когда вызывается ботом:

При добавлении нового сотрудника.
При изменении роли, подписи или должности.
При настройке/изменении цепочки резервных сотрудников.
При деактивации сотрудника (увольнение/лишение прав).
Формат запроса (JSON):

{

"messenger": "max", // или "telegram"

"user_id": 987654321, // ID сотрудника в мессенджере

"name": "Маркова Виктория", // ФИО для системы

"role": "Техподдержка", // Роль (Менеджер, Техподдержка, Администратор)

"position": "Ведущий специалист", // Должность для подписи

"is_active": true, // Статус (false при деактивации)

"reserves": [11223344, 55667788], // Массив ID резервных сотрудников (обновляет РС ай_РезервныеСотрудники)

"action": "upsert" // upsert (создать/обновить) или deactivate

}

Новый метод: Управление активами пользователя (ИНН и Ключи)

Сценарий: Вызывается, когда пользователь нажимает «Добавить ИНН», «Удалить ИНН», «Добавить Ключ» или «Удалить Ключ» в меню «Мой профиль». Перед добавлением Бот будет предварительно обращаться к API вызвав методы /assets/check_key, /assets/check_inn (при его наличии).

URL: POST /api/v1/user/assets/update

Method: POST

Тело запроса:

JSON

{

"messenger": "max", // или "telegram"

"user_id": 123456789,

"asset_type": "inn", // или "grand_key"

"action": "add", // или "remove"

"value": "1655060636", // сам номер ИНН или номер ключа

}

Ответы (Response):

200 OK: Изменение успешно внесено.

{"status": "success", "message": "Ассет успешно привязан/удален"}

Новый метод: Решение конфликта ключа (POST /assets/resolve_conflict)

Когда вызывается ботом:
Когда администратор в интерфейсе Бота нажимает одну из кнопок в уведомлении о конфликте: [✅ Передать ключ новому] или [❌ Отказать новому].

Формат запроса (JSON):

{

"key_number": "00000_01010", // Номер ключа

"action": "transfer", // transfer или reject

"new_user_phone": "79991234567", // Телефон того, КТО ХОЧЕТ забрать ключ

"old_user_phone": "79001112233", // Телефон того, У КОГО забирают ключ

"user_id ": "telegram", // С какого мессенджера пришел запрос

"messenger_type": "max", // С какого мессенджера пришел запрос

}

Логика обработки на стороне 1С:

Сценарий 1: action": "transfer" (Передача ключа)

Поиск: находит ключ 00000_01010.

Отвязка: удаляет связь этого ключа со старым владельцем

Привязка: создает новую связь ключа с новым владельцем

Логирование: В CRM фиксируется событие: «Ключ перенесен от Контакта А к Контакту Б администратором таким-то».

Ответ: {"status": "ok", "message": "Ключ успешно перенесен в 1С"}.

Сценарий 2: action": "reject" (Отказ в переносе)

Логирование: просто фиксирует попытку несанкционированного добавления ключа в истории

Без изменений: Связи ключа в базе остаются прежними.

Ответ: {"status": "ok", "message": "Попытка переноса отклонена"}.

Новый метод: Подтверждение смены номера (POST /user/change_phone)

Согласно ТЗ (14.6), смена номера возможна только через заявку в боте и ручное подтверждение админом. Когда админ одобряет смену, бот должен обновить данные в 1С.

Когда вызывается ботом: Когда администратор одобрил заявку пользователя на смену сотового номера.

Формат запроса (JSON):

{

"messenger_type": "telegram", // или "max"

"user_id": 12345678, // ID пользователя в мессенджере

"old_phone": "+79991112233", // Текущий номер в базе

"new_phone": "+79994445566", // Новый подтвержденный номер

"staff_id ": "989653576" // Кто одобрил смену

}

Логика на стороне 1С:

1С находит контакт по old_phone.

Обновляет в карточке номер телефона на new_phone.

Если в 1С заведены Личные Кабинеты или другие привязки к телефону - они тоже обновляются автоматически.

Новый метод: Глобальный лог событий (POST /system/audit_log)

Цель: Создание единого хранилища всех значимых действий в боте внутри базы 1С/CRM.

Когда вызывается ботом: При каждом значимом событии (регистрация, изменение настроек, действия со штатом, календарь и т.д.).

Формат запроса (JSON):

{

"messenger": "telegram", // или "max"

"action_timestamp": "2026-02-27T12:00:00Z", // Время события

"action_type": "staff_deactivated", // Строка

// Идентификаторы (теперь передаем id для связи в 1С)

"user_id ": "31515115", // Опционально (если действие связано с клиентом)

"staff_id": "51515685", // Опционально (если действие совершил сотрудник)

"ticket_id": "TKT_12345", // Опционально (если действие связано с заявкой)

// Детализация (произвольные данные в формате JSON)

"action_details": {

"reason": "Уволен по собственному желанию",

"changed_by_id": "5525235264", // Кто именно (админ) совершил действие

"old_value": "active",

"new_value": "inactive"

}