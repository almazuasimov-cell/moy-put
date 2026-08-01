# Voice Diary — «Мой путь»

Персональный AI-дневник с голосовым вводом для Android.

## Возможности

- 🎤 Голосовые записи (Whisper STT)
- 🧠 AI-обработка: настроение, теги, саммари, вопросы для размышления (DeepSeek)
- 📊 Статистика: график настроения, топ-тегов, streak дней
- 🔍 AI-поиск по дневнику (RAG)
- 📖 Автоматическая биография на основе всех записей

## Стек

- **Бэкенд:** FastAPI + SQLite + DeepSeek API + OpenAI Whisper
- **Фронтенд:** Flutter (Android)
- **AI:** DeepSeek (структурирование, поиск, биография) + Whisper (распознавание голоса)

## Структура проекта

```
voice-diary/
├── backend/          # FastAPI сервер
│   ├── main.py       # API (500+ строк)
│   ├── requirements.txt
│   └── venv/
├── flutter_app/      # Flutter приложение (скоро)
└── README.md
```

## Быстрый старт (бэкенд)

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Установи API-ключи в .env:
# DEEPSEEK_API_KEY=sk-...
# OPENAI_API_KEY=sk-...

uvicorn main:app --host 0.0.0.0 --port 8001
```

API будет доступен на `http://localhost:8001`.

## API-эндпоинты

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/auth/register` | Регистрация |
| POST | `/auth/login` | Вход |
| POST | `/stt/transcribe` | Голос → текст |
| POST | `/entries/process` | AI-обработка текста |
| POST | `/entries` | Создать запись |
| GET | `/entries` | Список записей |
| GET | `/entries/{id}` | Одна запись |
| PUT | `/entries/{id}` | Редактировать |
| DELETE | `/entries/{id}` | Удалить |
| POST | `/search` | AI-поиск по дневнику |
| POST | `/biography/generate` | Сгенерировать биографию |
| GET | `/biography` | Получить биографию |
| PUT | `/biography` | Редактировать биографию |
| GET | `/stats` | Статистика |
| GET | `/health` | Проверка |

## Лицензия

MIT
