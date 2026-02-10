# I-TAT API Documentation

## Базовая информация

**Base URL:** `http://i1.i-tat.ru:33080/sa-001-itatka/hs/dispatcher/v1/`

**Авторизация:** HTTP Basic Auth
- Логин: `dispatcher`
- Пароль: (запросить у администратора)

**Справка:** [http://i1.i-tat.ru:33080/sa-001-itatka/hs/dispatcher/v1/getinfo](http://i1.i-tat.ru:33080/sa-001-itatka/hs/dispatcher/v1/getinfo)

**Примечание:** Все методы регистронезависимы.

---

## Методы API

### 1. GET /getinfo

Возвращает справку по сервису — описание методов и параметров.

**Endpoint:** `/getinfo`

**Метод:** `GET`

**Пример запроса:**
```
GET http://i1.i-tat.ru:33080/sa-001-itatka/hs/dispatcher/v1/getinfo/
```

---

### 2. GET /system/staff

Возвращает список активных сотрудников с учетными записями в мессенджерах.

**Endpoint:** `/system/staff`

**Метод:** `GET`

**Пример запроса:**
```
GET http://i1.i-tat.ru:33080/sa-001-itatka/hs/dispatcher/v1/system/staff/
```

**Ответ (успешный):**
```json
{
  "status": "ok",
  "staff": [
    {
      "user_id": 123456789,
      "name": "Иванов Иван Иванович",
      "role": "manager",
      "position": "Менеджер отдела продаж"
    }
  ]
}
```

**Поля объекта сотрудника:**
- `user_id` (number) - идентификатор пользователя в Telegram
- `name` (string) - имя пользователя (наименование из справочника Пользователи)
- `role` (string) - роль пользователя (строковое представление перечисления)
- `position` (string) - должность для подписи

**Ошибки:**
- `500` - внутренняя ошибка сервера