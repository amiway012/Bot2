from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


def captcha_kb(options: list) -> InlineKeyboardMarkup:
    rows = []
    row = []

    for animal in options:
        row.append(
            InlineKeyboardButton(
                text=animal["name"],
                callback_data=f"cap:{animal['slug']}",
            )
        )

        if len(row) == 2:
            rows.append(row)
            row = []

    if row:
        rows.append(row)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_panel_kb(level: int) -> ReplyKeyboardMarkup:
    keyboard = [
        [
            KeyboardButton(text="📋 Заблокированные"),
            KeyboardButton(text="🔇 Замученные"),
        ],
        [
            KeyboardButton(text="✅ Разблокировать по ID"),
            KeyboardButton(text="🔊 Размутить по ID"),
        ],
        [
            KeyboardButton(text="📊 Статистика"),
            KeyboardButton(text="⚙️ Отладка"),
        ],
        [
            KeyboardButton(text="☣️ Статистика флуда"),
        ],
    ]

    if level >= 100:
        keyboard.append([KeyboardButton(text="👑 Админы")])

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def message_admin_kb(target_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⛔ Заблокировать", callback_data=f"blk:{target_id}"),
                InlineKeyboardButton(text="🔇 Мут", callback_data=f"mut:{target_id}"),
            ],
            [
                InlineKeyboardButton(text="📝 Ответить", callback_data=f"ans:{target_id}"),
                InlineKeyboardButton(text="📜 История переписки", callback_data=f"his:{target_id}"),
            ],
        ]
    )


def mute_options_kb(target_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="1 ч", callback_data=f"mset:{target_id}:1"),
                InlineKeyboardButton(text="3 ч", callback_data=f"mset:{target_id}:3"),
                InlineKeyboardButton(text="6 ч", callback_data=f"mset:{target_id}:6"),
                InlineKeyboardButton(text="12 ч", callback_data=f"mset:{target_id}:12"),
            ],
            [
                InlineKeyboardButton(text="24 ч", callback_data=f"mset:{target_id}:24"),
                InlineKeyboardButton(text="48 ч", callback_data=f"mset:{target_id}:48"),
                InlineKeyboardButton(text="72 ч", callback_data=f"mset:{target_id}:72"),
            ],
            [
                InlineKeyboardButton(text="Своё число часов", callback_data=f"mset:{target_id}:custom"),
            ],
        ]
    )