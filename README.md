# Telegram Chat Bot

Готовый чат-бот для групп и привата:
- RU/UK язык с автоопределением + `/lang`
- картинки: `/pictures`, `/altushka` (канал альтушек, см. `ALTGIRLS_*` в `.env`); музыка: `/music` (`MUSIC_SOURCE_CHANNEL`, `MUSIC_POST_IDS`, по умолчанию канал [@muzlovonie](https://t.me/muzlovonie))
- GIF: `/gif`, `/randomgif`
- еда/таймер/статистика: `/pokushat` (`/eat`), `/my_poop`, `/obosrat`, `/kakapair` (случайная пара в ту же статистику), `/force_poop`
- реакция на "сосал?"
- `/pizdy @user` (шутливый сценарий + GIF)
- случайные ответы и шуточный "мут на сутки" (без реального бана)
- управление автоответом: `/autoreply 1|2|3|status` (тишина / каждое N-е от человека / на каждое сообщение; `AUTOREPLY_EVERY_N` в `.env`)
- callback_query для выбора языка
- модульная структура: `handlers/commands`, `handlers/messages`, `handlers/callbacks`

## 1) Установка

```bash
cd "d:\PROJECT\telegram-chat-bot"
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2) Настройка

```bash
copy .env.example .env
```

Открой `.env` и вставь токен:
- `BOT_TOKEN=...`
- `MODERATE_LINKS=true`
- `RANDOM_REPLY_CHANCE=0.2`
- `RANDOM_FAKE_MUTE_CHANCE=0.04`
- `RANDOM_MEDIA_CHANCE=0.13`
- `AUTO_REPLY_MODE=1|2|3`, опционально `AUTOREPLY_EVERY_N=10` (шаг для режима 2). Если в `.env` нет ни `AUTO_REPLY_MODE`, ни `AUTO_REPLY_ENABLED`, по умолчанию режим **2** (см. `config.py`)
- `MEDIA_PROBE_ATTEMPTS=3` (сколько ID проверять за один запрос медиа)
- стиль фраз по времени суток: файлы `custom_random_replies_*_l1|l2|l3.txt` и `BOT_TIMEZONE`

## 3) Запуск

```bash
py bot.py
```

### Деплой Railway (облако)

1. Зарегистрируйся на [railway.app](https://railway.app), привяжи GitHub.
2. **New Project → Deploy from GitHub** → выбери репозиторий с этой папкой (или вынеси `telegram-chat-bot` в отдельный репо).
3. **Variables** — скопируй сюда все пары из локального `.env` (как минимум `BOT_TOKEN`); приватные значения в Git не клади.
4. **Опционально, чтобы `bot_state.db` не обнулялся:** у сервиса **Add volume** → mount path ` /data` → в Variables: `BOT_STATE_DB_PATH=/data/bot_state.db`.
5. Деплой: стартовая команда уже в `railway.toml` — `python bot.py`. В логах должно появиться `Bot is running...`.

## Механика "Еда -> Бум"

- У каждого пользователя профиль хранится в `bot_state.db` (SQLite)
- Кулдаун еды: 30 минут
- Первая еда: автоматический результат через 60 минут
- Вторая/следующая еда: результат сразу
- Команды:
  - `/pokushat` или `/eat`
  - `/my_poop`
  - `/force_poop` (для админа)
- Список еды можно менять без кода в файле `poop_foods.txt`
  - формат строки: `ru_text|uk_text|bonus|tag`
  - `tag`: `normal`, `weird`, `spicy`, `inedible`
  - строки с `#` и пустые строки игнорируются

## 4) Важные настройки в Telegram

1. Добавь бота в группу.
2. Отключи privacy mode через `@BotFather`, чтобы бот видел сообщения.
3. Выдай права админа (минимум: удаление сообщений), если включена модерация ссылок.

## Примеры ответов (RU/UK)

- RU: "Привет! Я чат-бот."
- UK: "Привіт! Я чат-бот."
- RU: "⚠️ @user, ты слишком шумный. ШУТОЧНЫЙ мут на 24 часа..."
- UK: "⚠️ @user, ти занадто гучний. ЖАРТІВЛИВИЙ мут на 24 години..."

## Добавление новых GIF/картинок

- Предпочтительный способ: через каналы Telegram
  - `GIF_SOURCE_CHANNEL=@potyznigif`
  - `MEME_SOURCE_CHANNEL=@UaReichUa`
  - `GIF_POST_IDS=10,11,12`
  - `MEME_POST_IDS=21,22,23`
- `ALLOW_URL_FALLBACK=false` (чтобы бот не слал URL напрямую)
- Бот копирует случайный пост из канала в чат (`copy_message`)
- При `ALLOW_URL_FALLBACK=false` бот отправляет только контент из каналов и не подставляет URL

## Как узнать message_id постов канала

- Открой пост в канале и скопируй ссылку вида `https://t.me/channel_name/123`
- Число в конце (`123`) — это `message_id`
- Добавь эти числа через запятую в `.env`

## Команда /scan_channel

Чтобы не копировать id руками по одному, можно дать боту ссылки пачкой:

```bash
/scan_channel gif https://t.me/potyznigif/10 https://t.me/potyznigif/11
/scan_channel meme https://t.me/UaReichUa/21 https://t.me/UaReichUa/22
```

Бот вытащит `message_id` из ссылок и вернёт готовую строку для `.env`.

## Управление автоответом в чате

- `/autoreply 1` — бот молчит (без автоответов)
- `/autoreply 2` — реакция на каждое N-е сообщение **от одного человека** (N = `AUTOREPLY_EVERY_N` в `.env`, по умолчанию 10)
- `/autoreply 3` — реакция на каждое сообщение
- `/autoreply status` — текущий режим; в группах меняет только админ
- краткие алиасы: `off`→1, `on`→3

## Редактирование фраз по времени суток (без кода)

- Уровни `l1` (утро), `l2` (день), `l3` (вечер/ночь): `custom_random_replies_ru_l1.txt` и т.п.
- Общий запас: `custom_random_replies_ru.txt` / `custom_random_replies_uk.txt`
- Пустые строки и `#` игнорируются; после правок перезапусти бота

## Автозапуск в Windows

1. Открой PowerShell в папке проекта:
   - `cd "d:\PROJECT\telegram-chat-bot"`
2. Создай задачу автозапуска:
   - `powershell -ExecutionPolicy Bypass -File .\install-autostart.ps1`
3. Запусти задачу сразу (опционально):
   - `Start-ScheduledTask -TaskName TelegramChatBot`

Для удаления автозапуска:
- `Unregister-ScheduledTask -TaskName TelegramChatBot -Confirm:$false`
