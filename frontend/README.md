# Frontend Portal

Отдельный клиентский сайт на Next.js для работы поверх существующего FastAPI API.

## Запуск

```bash
cd frontend
npm install
npm run dev
```

По умолчанию фронтенд ожидает API на `http://127.0.0.1:8000`.

Если нужен другой адрес, создайте `frontend/.env.local`:

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```
