"""
Callback Data Factories

Паттерн: Type-safe callback data с использованием CallbackData фабрик
- Используйте короткие префиксы (экономия байтов в callback_data)
- Документируйте назначение каждого поля
- Используйте Optional для необязательных параметров
- action: str - для определения типа действия (view, select, delete и т.д.)
"""

from aiogram.filters.callback_data import CallbackData


class OrganizationCallback(CallbackData, prefix="org"):
    """
    Callback data для выбора организации.

    Поля:
    - action: Тип действия ('select', 'add_new', 'skip', 'page')
    - inn: ИНН организации (опционально)
    - page: Номер страницы для пагинации (опционально)
    """

    action: str
    inn: str | None = None
    page: int | None = None


class KeyCallback(CallbackData, prefix="key"):
    """
    Callback data для выбора GS_Key.

    Поля:
    - action: Тип действия ('toggle', 'add_new', 'done', 'skip', 'page')
    - key_id: ID ключа GS_Key (опционально)
    - page: Номер страницы для пагинации (опционально)
    """

    action: str
    key_id: int | None = None
    page: int | None = None


class DeliveryCallback(CallbackData, prefix="dlv"):
    """
    Callback data для выбора способа доставки.

    Поля:
    - method: Способ доставки ('telegram', 'email')
    """

    method: str


class ProfileCallback(CallbackData, prefix="prof"):
    """
    Callback data для действий в профиле.

    Поля:
    - action: Тип действия ('add_inn', 'add_key', 'change_phone', 'toggle_notif', 'back')
    """

    action: str


class ExampleItemCallback(CallbackData, prefix="item"):
    """
    Пример фабрики для работы с элементами списка.

    Поля:
    - action: Тип действия ('view', 'select', 'delete', 'edit')
    - item_id: ID элемента (опционально для действий типа 'list')
    - page: Номер страницы для пагинации (опционально)
    """

    action: str
    item_id: int | None = None
    page: int | None = None


class ExampleNavigationCallback(CallbackData, prefix="nav"):
    """
    Пример фабрики для навигации между разделами.

    Поля:
    - action: Тип действия ('back', 'forward', 'cancel')
    - from_section: Откуда пришел пользователь (для контекстного возврата)
    - data: Дополнительные данные (опционально)
    """

    action: str
    from_section: str | None = None
    data: str | None = None
