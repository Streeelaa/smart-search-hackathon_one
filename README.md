# Умный поиск продукции — zakupki.mos.ru

Персонализированная поисковая система для портала закупок Москвы.
Гибридный поиск с коррекцией опечаток, раскрытием синонимов, семантическим пониманием запросов и персонализацией по истории пользователя.

## Ключевые возможности

| Возможность | Описание |
|---|---|
| Коррекция опечаток | монитр -> монитор (rapidfuzz + difflib) |
| Синонимы и жаргон | системник -> системный блок, ПК, компьютер, десктоп |
| Аббревиатуры | МФУ -> многофункциональное устройство, ИБП -> UPS |
| Морфология | ноутбуки = ноутбук = ноутбуков (pymorphy3) |
| Семантический поиск | E5-large (1024-dim), multilingual |
| Реранкинг | BGE-reranker-v2-m3 cross-encoder + heuristic fallback |
| LTR (Learning to Rank) | LightGBM lambdarank на 9 фичах |
| Персонализация | Профили на основе кликов, покупок, избранного |
| Гибридный режим | keyword + semantic + rerank + LTR + personalization |
| Кеширование | SHA256-based .npy cache эмбеддингов |

## Данные

- Каталог: 170 товаров в 18 категориях
- Синонимы: 136 групп (аббревиатуры, жаргон, разговорные формы)
- События: 543 пользовательских события от 5 профилей
- Evaluation: 20 тестовых кейсов, 5 метрик (Hit@3, MRR@10, NDCG@10, Precision@3, Recall@10)
- Demo-сценарии: 5 готовых сценариев для жюри

## Архитектура (Pipeline)

```
Запрос пользователя
  |
[1] Токенизация + морфологическая нормализация (pymorphy3)
  |
[2] Коррекция опечаток (rapidfuzz, score_cutoff=78)
  |
[3] Расширение синонимами (136 групп из data/synonyms.json)
  |
[4] Параллельный retrieval:
    - Keyword: лексический скоринг по полям (title x3, aliases x2.7, tags x2)
    - Semantic: cosine similarity через E5-large эмбеддинги
  |
[5] Reranking (BGE cross-encoder или heuristic fallback)
  |
[6] LTR boost (LightGBM lambdarank, 9 features)
  |
[7] Персонализация (category/tag affinity + ценовая близость)
  |
Ранжированные результаты
```

## Технологический стек

- Backend: FastAPI + Uvicorn
- Frontend: Streamlit (интерактивный demo UI)
- Семантика: sentence-transformers (intfloat/multilingual-e5-large, 1024-dim)
- Реранкер: cross-encoder (BAAI/bge-reranker-v2-m3)
- LTR: LightGBM lambdarank
- Морфология: pymorphy3 (LRU кеш 4096 токенов)
- Нечёткий поиск: rapidfuzz
- Хранилище: In-memory / SQLAlchemy (SQLite / PostgreSQL)
- Тесты: pytest (34 теста)

## Структура проекта

```
main.py                  - Точка входа (uvicorn)
streamlit_app.py         - Web UI для демо
requirements.txt
app/
  api.py                 - FastAPI endpoints
  schemas.py             - Pydantic модели
  search.py              - Гибридный поиск + персонализация
  semantic.py            - E5-large с кешированием
  reranker.py            - BGE cross-encoder / heuristic
  ltr.py                 - LightGBM Learning-to-Rank
  text_processing.py     - Токенизация, морфология, коррекция
  synonyms.py            - Расширение синонимами
  repository.py          - In-memory / SQL хранилище
  evaluation.py          - 20 кейсов, 5 метрик
  demo_scenarios.py      - 5 demo-сценариев
  ingestion.py           - Импорт каталогов и событий
  settings.py            - Переменные окружения
  db.py / db_models.py   - SQLAlchemy
  catalog_loader.py      - Загрузка каталога
data/
  catalog.json           - 170 товаров
  synonyms.json          - 136 групп синонимов
  sample_events.json     - 543 события
models/
  ltr_model.txt          - Обученная LTR модель
tests/
  test_search.py         - 34 pytest теста
scripts/
  train_ltr.py           - Обучение LTR модели
  generate_catalog.py    - Генерация каталога
  generate_synonyms.py   - Генерация синонимов
  generate_events.py     - Генерация событий
  smoke_test.py          - Быстрая проверка
docs/
  bpmn.md
  demo-script.md
  presentation-outline.md
```

## Быстрый старт

```bash
# Активация виртуального окружения
venv\Scripts\activate.bat    # Windows
source venv/bin/activate     # Linux/Mac

# Установка зависимостей
pip install -r requirements.txt

# Запуск API-сервера
uvicorn main:app --reload

# Запуск Web UI (в отдельном терминале)
streamlit run streamlit_app.py

# Запуск тестов
pytest tests/ -v

# Обучение LTR модели
python scripts/train_ltr.py
```

- API Swagger: http://127.0.0.1:8000/docs
- Streamlit UI: http://localhost:8501

## Основные эндпоинты

- GET /health
- GET /catalog/items
- GET /search?q=ноутбук&user_id=user-1&mode=hybrid
- GET /search/synonyms
- GET /search/semantic/status
- GET /search/reranker/status
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

## Переменные окружения

- STORAGE_BACKEND=memory|sql
- DATABASE_URL=sqlite:///path/to/db
- SEED_DEMO_DATA=true|false
- SEMANTIC_BACKEND=auto|tfidf
- SEMANTIC_MODEL_NAME=intfloat/multilingual-e5-large
- RERANKER_BACKEND=heuristic|auto|cross-encoder
- RERANKER_MODEL_NAME=BAAI/bge-reranker-v2-m3
- EMBEDDING_CACHE_DIR=.cache
- LTR_MODEL_PATH=models/ltr_model.txt

## Масштабирование

- PostgreSQL через STORAGE_BACKEND=sql
- Redis для кеша горячих запросов
- Elasticsearch/OpenSearch для >100к товаров
- GPU inference (sentence-transformers автоматически используют CUDA)
- Kubernetes: stateless FastAPI горизонтально масштабируется
