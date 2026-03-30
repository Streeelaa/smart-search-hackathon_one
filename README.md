# Smart Search Hackathon

MVP backend на FastAPI для персонализированного поиска по каталогу продукции.

## Что уже есть

- keyword-поиск с нормализацией текста
- correction layer для опечаток
- внешний словарь синонимов в data/synonyms.json
- внешний каталог товаров в data/catalog.json
- логирование событий пользователя
- динамический профиль пользователя
- персонализированное ранжирование
- semantic retrieval
- гибридный поиск: keyword + semantic
- rerank-слой поверх retrieval-кандидатов
- переключаемое хранилище: memory или SQLAlchemy
- fallback с sentence-transformers на TF-IDF, если модель не загрузилась
- встроенная оценка качества поиска на демо-кейсах

## Структура

- main.py — точка входа
- app/api.py — эндпоинты FastAPI
- app/schemas.py — Pydantic-схемы
- app/repository.py — in-memory данные, события и профили
- app/settings.py — конфигурация через переменные окружения
- app/db.py — SQLAlchemy engine и инициализация БД
- app/db_models.py — SQLAlchemy-модели для товаров и событий
- app/search.py — keyword, hybrid и персонализированное ранжирование
- app/semantic.py — semantic retrieval и fallback-индексация
- app/reranker.py — rerank top-кандидатов с fallback на heuristic scoring
- app/demo_scenarios.py — готовые сценарии показа для жюри
- streamlit_app.py — интерактивный веб-интерфейс для демо
- data/synonyms.json — редактируемая база синонимов
- data/catalog.json — редактируемый каталог демо-товаров
- docs/bpmn.md — BPMN-черновик бизнес-процесса
- docs/demo-script.md — готовый сценарий демонстрации
- docs/presentation-outline.md — структура презентации

## Запуск

```bash
venv\Scripts\activate.bat
uvicorn main:app --reload
```

Swagger UI: http://127.0.0.1:8000/docs

Для демо-интерфейса Streamlit:

```bash
streamlit run streamlit_app.py
```

## Основные эндпоинты

- GET /health
- GET /catalog/items
- GET /catalog/items/{item_id}
- GET /search?q=ноутбук&user_id=user-1&mode=hybrid
- GET /search/synonyms
- GET /search/semantic/status
- GET /search/reranker/status
- GET /storage/status
- POST /admin/import/catalog
- POST /admin/import/events
- POST /events
- GET /users/{user_id}/profile
- GET /users/{user_id}/events
- GET /metrics/evaluate
- GET /metrics/compare

## Режимы поиска

- keyword — только лексический поиск
- semantic — только semantic retrieval
- hybrid — объединение keyword и semantic слоя

## Примеры

```bash
curl http://127.0.0.1:8000/health
curl "http://127.0.0.1:8000/search?q=ноут&user_id=user-1&mode=hybrid"
curl "http://127.0.0.1:8000/search?q=настольный%20компьютер&mode=semantic"
curl http://127.0.0.1:8000/search/synonyms
curl http://127.0.0.1:8000/search/semantic/status
curl http://127.0.0.1:8000/search/reranker/status
curl http://127.0.0.1:8000/storage/status
curl -X POST http://127.0.0.1:8000/admin/import/catalog ^
  -H "Content-Type: application/json" ^
  -d "{\"path\":\"data/catalog.json\",\"replace_existing\":true}"
curl -X POST http://127.0.0.1:8000/admin/import/events ^
  -H "Content-Type: application/json" ^
  -d "{\"path\":\"data/sample_events.json\",\"replace_existing\":false}"
curl -X POST http://127.0.0.1:8000/events ^
  -H "Content-Type: application/json" ^
  -d "{\"user_id\":\"user-1\",\"event_type\":\"click\",\"item_id\":6}"
curl http://127.0.0.1:8000/users/user-1/profile
curl http://127.0.0.1:8000/metrics/evaluate
curl http://127.0.0.1:8000/metrics/compare
```

## Как расширять словарь

Открой data/synonyms.json и добавляй новые ключи и варианты без изменения Python-кода.

Пример:

```json
"сканер": ["сканирующее устройство", "scan"]
```

## Как расширять каталог

Открой data/catalog.json и добавляй новые товары в виде JSON-объектов. После перезапуска сервера они попадут в поиск.

## Импорт реальных данных

Сервис умеет загружать каталог и события из JSON или CSV через admin-endpoints.

Для каталога ожидаются колонки или поля вроде:

- id, item_id, product_id
- sku, ste_id, code
- title, name, product_name
- category
- description
- price
- tags
- aliases

Для событий ожидаются поля:

- user_id
- event_type
- item_id или product_id
- query

Остальные поля из CSV автоматически складываются в attributes или metadata.

## Нейросетевая модель

Сейчас semantic-слой пытается использовать модель sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2.

Почему выбрана она:

- быстрее и легче для MVP, чем крупные retrieval-модели
- хорошо подходит для русско-английских коротких запросов
- проще для первого локального запуска

Если модель не загрузится, сервис автоматически переключится на TF-IDF fallback и продолжит работать.

Для локальной разработки можно управлять поведением через переменные окружения:

- STORAGE_BACKEND=memory — текущее in-memory хранилище
- STORAGE_BACKEND=sql — хранение в БД через SQLAlchemy
- DATABASE_URL=sqlite:///C:/path/to/smart_search.db — локальная SQLite база
- DATABASE_URL=postgresql+psycopg://user:password@host:5432/dbname — PostgreSQL
- SEED_DEMO_DATA=true — автоматически засеять демо-данные при пустой БД

- SEMANTIC_BACKEND=tfidf — не пытаться качать нейросетевую модель
- SEMANTIC_BACKEND=auto — сначала попытаться загрузить модель, потом fallback
- SEMANTIC_MODEL_NAME=<model_id> — подставить другой Hugging Face model id

Для reranker доступны такие же настройки:

- RERANKER_BACKEND=heuristic — безопасный локальный режим без скачивания модели
- RERANKER_BACKEND=auto — попытаться загрузить cross-encoder, иначе fallback
- RERANKER_BACKEND=cross-encoder — принудительно использовать cross-encoder
- RERANKER_MODEL_NAME=<model_id> — подставить другой reranker model id

Если захочешь усилить качество, следующая замена модели:

1. BAAI/bge-m3
2. intfloat/multilingual-e5-large-instruct

## Что дальше

Следующий этап для усиления MVP:

1. загрузить реальные данные организаторов в текущий pipeline
2. заменить in-memory хранилище на PostgreSQL
3. при необходимости заменить retrieval и rerank на более сильные модели
4. подготовить BPMN и презентационный сценарий
5. финально отполировать demo-flow для жюри
