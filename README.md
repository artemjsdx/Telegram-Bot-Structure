# Channel AI Bot

Telegram-бот, который мониторит посты в твоём канале, переписывает их с помощью ИИ через **FavoriteAPI** и заменяет оригинальный пост переработанной версией.

## Возможности

- Привязка FavoriteAPI (любой Gemini-модели)
- Выбор модели ИИ из списка
- Пользовательский промпт для обработки постов
- Системный промпт с инструкциями Telegram HTML-форматирования (вкл/выкл)
- Мониторинг нескольких пользователей с разными каналами
- Умная замена: text-only → edit (сохраняет просмотры), медиа → delete+resend
- Поддержка медиа: фото, видео, документы, GIF

## Быстрый старт

### 1. Клонируй репозиторий

```bash
git clone https://github.com/artemjsdx/Telegram-Bot-Structure.git
cd Telegram-Bot-Structure
```

### 2. Установи зависимости

```bash
pip install -r requirements.txt
```

На Termux (Android):
```bash
pkg install python
pip install -r requirements.txt
```

### 3. Создай .env файл

```bash
cp .env.example .env
```

Заполни:
```
BOT_TOKEN=ваш_токен_бота
DB_PATH=data/bot.db
```

### 4. Запусти бота

```bash
cd bot
python3 main.py
```

Для запуска в фоне (Termux):
```bash
cd bot
nohup python3 main.py > ../bot_run.log 2>&1 &
```

## Настройка через бота

1. **`/start`** — пошаговая настройка:
   - URL FavoriteAPI (например `https://xxxx.trycloudflare.com`)
   - API ключ (`fa_sk_...`)
   - Выбор модели ИИ
   - Ввод промпта
   - Вкл/выкл системного промпта

2. **`/bind_channel`** — привязать Telegram-канал:
   - Добавь бота как администратора в канал
   - Перешли любой пост из канала боту

3. Готово! Бот переписывает новые посты автоматически.

## Команды

| Команда | Описание |
|---------|----------|
| `/start` | Настройка бота |
| `/bind_channel` | Привязать канал |
| `/settings` | Изменить настройки |
| `/status` | Статус мониторинга |
| `/cancel` | Отменить действие |
| `/help` | Справка |

## Структура проекта

```
├── bot/
│   ├── main.py              # Точка входа
│   ├── config.py            # Загрузка .env
│   ├── db/
│   │   └── storage.py       # SQLite хранение настроек
│   ├── core/
│   │   ├── ai_client.py     # Клиент FavoriteAPI
│   │   ├── formatter.py     # Загрузка системного промпта
│   │   ├── monitor.py       # Обработка новых постов
│   │   └── replacer.py      # Замена постов в канале
│   └── handlers/
│       ├── setup.py         # /start — настройка
│       ├── channel.py       # /bind_channel
│       └── settings.py      # /settings
├── system_prompt/
│   └── telegram_formatting.txt  # Системный промпт с HTML-тегами
├── .env.example
├── requirements.txt
└── plan.txt                 # Полный план проекта
```

## FavoriteAPI

Бот работает через [FavoriteAPI](https://t.me/SamGPTrobot) — self-hosted прокси к Gemini.

Поддерживаемые модели:
- `gemini-3.0-flash-thinking` (рекомендуется)
- `gemini-3.0-flash`
- `gemini-2.5-flash-thinking`
- `gemini-2.5-flash`
- `gemini-2.5-mini`

## Telegram HTML форматирование

Системный промпт обучает ИИ использовать:
- `<b>жирный</b>`, `<i>курсив</i>`, `<u>подчёркивание</u>`
- `<blockquote>цитата</blockquote>`
- `<tg-spoiler>спойлер</tg-spoiler>`
- `<code>код</code>`, `<s>зачёркнутый</s>`

## Стек

- Python 3.11+
- python-telegram-bot 22.x
- httpx (async HTTP)
- aiosqlite (SQLite)
- python-dotenv

## Лицензия

MIT — свободное использование и модификация.
