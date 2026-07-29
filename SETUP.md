# SafeOut — инструкция по запуску

## 1. Получить токен бота

1. Открыть Telegram, написать @BotFather
2. `/newbot` → придумать имя → получить токен (выглядит как `7123456789:AAF...`)
3. Скопировать токен

## 2. Настроить переменные окружения

```bash
cp .env.example .env
```

Открыть `.env` и вставить токен:
```
BOT_TOKEN=7123456789:AAF...
```

Остальное можно оставить как есть для локального запуска.

## 3. Запустить локально

```bash
# Установить Docker Desktop (если нет): https://docs.docker.com/desktop/mac/install/

# Запустить всё
docker compose up --build

# Бот будет работать сразу после старта
```

## 4. Деплой на Railway (рекомендуется)

1. Зарегистрироваться на [railway.app](https://railway.app)
2. New Project → Deploy from GitHub repo
3. Добавить сервисы: PostgreSQL, Redis (кнопка + New в Railway)
4. В настройках бота добавить переменные из `.env`
5. Railway автоматически соберёт и запустит

## 5. SMS (Twilio) — опционально

1. [twilio.com](https://twilio.com) → бесплатный аккаунт
2. Получить: Account SID, Auth Token, телефонный номер
3. Добавить в `.env`:
   ```
   TWILIO_ACCOUNT_SID=...
   TWILIO_AUTH_TOKEN=...
   TWILIO_FROM_NUMBER=+1234567890
   ```

## 6. Email (SendGrid) — опционально

1. [sendgrid.com](https://sendgrid.com) → бесплатный аккаунт (100 писем/день)
2. Создать API key
3. Добавить в `.env`:
   ```
   SENDGRID_API_KEY=SG....
   SENDGRID_FROM_EMAIL=alert@yourdomain.com
   ```

## 7. Хранилище файлов (Cloudflare R2) — сейчас не используется

Файлы (фото, скрины, голосовые) хранятся как Telegram `file_id`: бот не скачивает и не загружает их сам,
`api/routes.py` при показе страницы тревоги проксирует их через Bot API. `storage/files.py` (загрузка в S3/R2)
оставлен как готовый, но не подключённый путь — если понадобится своё хранилище, нужно будет:
1. Завести бакет (например [cloudflare.com](https://cloudflare.com) → R2)
2. Добавить `S3_*` переменные в `.env`
3. В `bot/handlers/newdate.py` вернуть вызов `upload_bytes(...)` вместо сохранения `file_id`,
   и в `api/routes.py` — `public_url(...)` вместо прокси-роута `/alert/{token}/files/{id}`.

## Структура проекта

```
safeout/
├── main.py              — точка входа бота
├── bot/
│   ├── handlers/        — команды (/start, /newdate, /contacts)
│   ├── keyboards/       — кнопки
│   └── middlewares/     — база данных, i18n
├── core/
│   ├── models.py        — таблицы БД
│   ├── tasks.py         — Celery (таймеры, эскалация)
│   ├── notifications.py — SMS и email (не подключены по умолчанию, см. .env.example)
│   └── config.py        — настройки
├── api/routes.py        — веб-страница для доверенных контактов
├── storage/files.py     — S3/R2-загрузка, не подключена по умолчанию (см. пункт 7)
└── templates/alert.html — страница тревоги
```
