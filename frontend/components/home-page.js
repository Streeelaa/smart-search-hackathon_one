"use client";

import Link from "next/link";
import { useDeferredValue, useEffect, useMemo, useState, useTransition } from "react";
import { createEvent, fetchJson } from "../lib/api";
import { addToCart } from "../lib/cart";
import { formatCurrency, formatNumber, normalizeAttributes } from "../lib/format";
import { PortalShell } from "./portal-shell";

const DEFAULT_LIMIT = 8;

function ResultCard({ item, onAddToCart, onOpen, onFavorite }) {
  const attrs = normalizeAttributes(item.product.attributes);

  return (
    <article className="result-card">
      <div className="result-header">
        <div>
          <p className="result-category">{item.product.category}</p>
          <h3>{item.product.title}</h3>
        </div>
        <div className="score-chip">{item.score.toFixed(1)}</div>
      </div>

      <div className="chip-row">
        <span className="soft-chip">ID {item.product.id}</span>
        {item.reasons?.slice(0, 3).map((reason) => (
          <span className="soft-chip" key={reason}>
            {reason}
          </span>
        ))}
      </div>

      {attrs.length ? (
        <ul className="plain-list">
          {attrs.slice(0, 3).map((attribute) => (
            <li key={attribute}>{attribute}</li>
          ))}
        </ul>
      ) : (
        <p className="muted-copy">Атрибуты товара будут показаны после открытия карточки.</p>
      )}

      <div className="actions-row">
        <button className="secondary-button" onClick={onOpen} type="button">
          Открыть карточку
        </button>
        <button className="secondary-button" onClick={onAddToCart} type="button">
          В корзину
        </button>
        <button className="ghost-button" onClick={onFavorite} type="button">
          В избранное
        </button>
      </div>
    </article>
  );
}

function SearchSuggestionList({ suggestions, onPick }) {
  if (!suggestions.length) {
    return null;
  }

  return (
    <div className="surface suggestion-panel">
      {suggestions.map((suggestion) => (
        <button
          className="suggestion-item"
          key={`${suggestion.type}-${suggestion.id || suggestion.title}`}
          onClick={() => onPick(suggestion)}
          type="button"
        >
          <span>
            <strong>{suggestion.title}</strong>
            {suggestion.category ? ` · ${suggestion.category}` : ""}
          </span>
          <span className="muted-copy">
            {suggestion.type === "product" ? "товар" : `категория${suggestion.count ? ` · ${suggestion.count}` : ""}`}
          </span>
        </button>
      ))}
    </div>
  );
}

export function HomePage() {
  const [overview, setOverview] = useState(null);
  const [users, setUsers] = useState([]);
  const [selectedUserId, setSelectedUserId] = useState("");
  const [profile, setProfile] = useState(null);
  const [query, setQuery] = useState("");
  const [activeCategory, setActiveCategory] = useState("");
  const [limit, setLimit] = useState(DEFAULT_LIMIT);
  const [suggestions, setSuggestions] = useState([]);
  const [searchResponse, setSearchResponse] = useState(null);
  const [selectedItem, setSelectedItem] = useState(null);
  const [selectedInsights, setSelectedInsights] = useState(null);
  const [loadingOverview, setLoadingOverview] = useState(true);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState("");
  const [isPending, startTransition] = useTransition();
  const deferredQuery = useDeferredValue(query);

  useEffect(() => {
    let cancelled = false;

    async function loadInitial() {
      try {
        setLoadingOverview(true);
        const [overviewResponse, usersResponse] = await Promise.all([
          fetchJson("/portal/overview"),
          fetchJson("/users", { searchParams: { limit: 12 } }),
        ]);

        if (cancelled) {
          return;
        }

        setOverview(overviewResponse);
        setUsers(usersResponse);
        setSelectedUserId((current) => current || overviewResponse.featured_users?.[0]?.user_id || usersResponse[0]?.user_id || "");
      } catch {
        if (!cancelled) {
          setError("Не удалось загрузить портал. Проверьте, запущен ли FastAPI на 8000 порту.");
        }
      } finally {
        if (!cancelled) {
          setLoadingOverview(false);
        }
      }
    }

    loadInitial();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedUserId) {
      setProfile(null);
      return;
    }

    let cancelled = false;

    fetchJson(`/users/${selectedUserId}/profile`)
      .then((response) => {
        if (!cancelled) {
          setProfile(response);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setProfile(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedUserId]);

  useEffect(() => {
    if (!deferredQuery || deferredQuery.trim().length < 2) {
      setSuggestions([]);
      return;
    }

    let cancelled = false;
    const controller = new AbortController();

    fetchJson("/search/suggest", {
      searchParams: { q: deferredQuery, limit: 6 },
      signal: controller.signal,
    })
      .then((response) => {
        if (!cancelled) {
          setSuggestions(response);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSuggestions([]);
        }
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [deferredQuery]);

  useEffect(() => {
    if (!selectedItem?.product?.id) {
      setSelectedInsights(null);
      return;
    }

    let cancelled = false;

    fetchJson(`/catalog/items/${selectedItem.product.id}/insights`)
      .then((response) => {
        if (!cancelled) {
          setSelectedInsights(response);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSelectedInsights(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedItem]);

  const selectedUser = useMemo(
    () => users.find((user) => user.user_id === selectedUserId) || overview?.featured_users?.find((user) => user.user_id === selectedUserId),
    [overview?.featured_users, selectedUserId, users],
  );

  const topCategories = useMemo(() => {
    if (!profile?.category_affinity) {
      return [];
    }

    return Object.entries(profile.category_affinity)
      .sort((left, right) => right[1] - left[1])
      .slice(0, 5);
  }, [profile]);

  async function runSearch(nextQuery = query, nextCategory = activeCategory) {
    const cleanQuery = nextQuery.trim();
    if (!cleanQuery) {
      setError("Введите поисковый запрос.");
      return;
    }

    try {
      setError("");
      setIsSearching(true);
      const response = await fetchJson("/search", {
        searchParams: {
          q: cleanQuery,
          user_id: selectedUserId,
          category: nextCategory,
          limit,
        },
      });

      startTransition(() => {
        setSearchResponse(response);
        setSelectedItem(response.items?.[0] || null);
      });

      void createEvent({
        user_id: selectedUserId || "portal-web",
        event_type: "search",
        query: cleanQuery,
        metadata: nextCategory ? { category: nextCategory } : {},
      }).catch(() => null);
    } catch {
      setError("Поиск не выполнился. Проверьте, что API доступен.");
    } finally {
      setIsSearching(false);
    }
  }

  function handleSuggestionPick(suggestion) {
    const nextQuery = suggestion.type === "product" ? suggestion.title : query || suggestion.title;
    const nextCategory = suggestion.type === "category" ? suggestion.title : activeCategory;
    setQuery(nextQuery);
    setActiveCategory(nextCategory);
    void runSearch(nextQuery, nextCategory);
  }

  function handleOpenItem(item) {
    setSelectedItem(item);
    void createEvent({
      user_id: selectedUserId || "portal-web",
      event_type: "click",
      item_id: item.product.id,
      query: searchResponse?.query || query || null,
      metadata: { category: item.product.category },
    }).catch(() => null);
  }

  function handleFavorite(item) {
    void createEvent({
      user_id: selectedUserId || "portal-web",
      event_type: "favorite",
      item_id: item.product.id,
      query: searchResponse?.query || query || null,
      metadata: { title: item.product.title },
    }).catch(() => null);
  }

  function handleAddToCart(item) {
    addToCart({
      id: item.product.id,
      title: item.product.title,
      category: item.product.category,
      averagePrice: selectedInsights?.product_id === item.product.id ? selectedInsights.average_price : null,
    });
  }

  return (
    <PortalShell>
      <section className="hero-grid">
        <div className="hero-panel surface elevated">
          <p className="eyebrow">Клиентский сайт</p>
          <h2>Поиск по товарам, категориям и профилям заказчиков на живых данных закупок</h2>
          <p className="lead-copy">
            Новый интерфейс работает поверх существующего FastAPI-бэкенда, а Streamlit можно оставить как внутреннюю
            админскую и demo-панель.
          </p>

          <div className="stat-grid">
            <div className="stat-card">
              <span>Товаров</span>
              <strong>{formatNumber(overview?.stats?.products_count)}</strong>
            </div>
            <div className="stat-card">
              <span>Организаций</span>
              <strong>{formatNumber(overview?.stats?.profiles_count)}</strong>
            </div>
            <div className="stat-card">
              <span>Категорий</span>
              <strong>{formatNumber(overview?.stats?.categories_count)}</strong>
            </div>
            <div className="stat-card">
              <span>Событий</span>
              <strong>{formatNumber(overview?.stats?.events_count)}</strong>
            </div>
          </div>
        </div>

        <aside className="surface spotlight-panel">
          <p className="eyebrow">Активный заказчик</p>
          <select className="field-input" onChange={(event) => setSelectedUserId(event.target.value)} value={selectedUserId}>
            <option value="">Без персонализации</option>
            {users.map((user) => (
              <option key={user.user_id} value={user.user_id}>
                {user.user_name}
              </option>
            ))}
          </select>

          {selectedUser ? (
            <>
              <h3>{selectedUser.user_name}</h3>
              <p className="muted-copy">{selectedUser.user_region || "Регион не указан"}</p>
              <div className="chip-row">
                <span className="soft-chip">{formatNumber(selectedUser.total_contracts)} контрактов</span>
                <span className="soft-chip">Средний чек {formatCurrency(selectedUser.avg_price)}</span>
              </div>
              {selectedUserId ? (
                <Link className="text-link" href={`/customers/${selectedUserId}`}>
                  Открыть профиль организации
                </Link>
              ) : null}
            </>
          ) : (
            <p className="muted-copy">Выберите профиль, чтобы включить персонализацию выдачи.</p>
          )}

          {topCategories.length ? (
            <div className="stack-block">
              <h4>Топ категорий</h4>
              {topCategories.map(([category, score]) => (
                <div className="meter-row" key={category}>
                  <span>{category}</span>
                  <div className="meter-track">
                    <div className="meter-fill" style={{ width: `${Math.min(score * 100, 100)}%` }} />
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </aside>
      </section>

      <section className="surface search-panel">
        <div className="search-toolbar">
          <div className="field-block grow">
            <label htmlFor="portal-search">Что ищем</label>
            <input
              className="field-input"
              id="portal-search"
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  void runSearch();
                }
              }}
              placeholder="Например: ноутбук Lenovo, канцелярия, медицинские перчатки..."
              value={query}
            />
          </div>

          <div className="field-block compact">
            <label htmlFor="search-limit">Показывать</label>
            <select className="field-input" id="search-limit" onChange={(event) => setLimit(Number(event.target.value))} value={limit}>
              <option value="6">6</option>
              <option value="8">8</option>
              <option value="12">12</option>
            </select>
          </div>

          <button className="primary-button" disabled={isSearching} onClick={() => void runSearch()} type="button">
            {isSearching ? "Ищем..." : "Найти"}
          </button>
        </div>

        {activeCategory ? (
          <div className="chip-row">
            <span className="soft-chip accent-chip">Фильтр: {activeCategory}</span>
            <button className="ghost-inline" onClick={() => setActiveCategory("")} type="button">
              Сбросить
            </button>
          </div>
        ) : null}

        <SearchSuggestionList onPick={handleSuggestionPick} suggestions={suggestions} />
      </section>

      {error ? <div className="surface error-box">{error}</div> : null}

      {!searchResponse ? (
        <section className="showcase-grid">
          <div className="surface">
            <div className="section-head">
              <div>
                <p className="eyebrow">Популярные направления</p>
                <h3>Стартовые категории</h3>
              </div>
            </div>

            <div className="tile-grid">
              {overview?.featured_categories?.map((category) => (
                <button
                  className="category-tile"
                  key={category.category}
                  onClick={() => {
                    setActiveCategory(category.category);
                    setQuery((current) => current || category.category);
                    void runSearch(query || category.category, category.category);
                  }}
                  type="button"
                >
                  <strong>{category.category}</strong>
                  <span>{formatNumber(category.count)} позиций</span>
                </button>
              ))}
            </div>
          </div>

          <div className="surface">
            <div className="section-head">
              <div>
                <p className="eyebrow">Профили</p>
                <h3>Организации из базы</h3>
              </div>
            </div>

            <div className="stack-list">
              {(overview?.featured_users || []).map((user) => (
                <div className="list-card" key={user.user_id}>
                  <div>
                    <strong>{user.user_name}</strong>
                    <p className="muted-copy">{user.top_category || "Категория не указана"}</p>
                  </div>
                  <Link className="text-link" href={`/customers/${user.user_id}`}>
                    Профиль
                  </Link>
                </div>
              ))}
            </div>
          </div>
        </section>
      ) : (
        <section className="results-layout">
          <div className="results-column">
            <div className="surface section-banner">
              <div>
                <p className="eyebrow">Результаты</p>
                <h3>{searchResponse.total} найдено</h3>
              </div>
              <div className="chip-row">
                <span className="soft-chip">Запрос: {searchResponse.query}</span>
                {searchResponse.corrected_query && searchResponse.corrected_query !== searchResponse.query ? (
                  <span className="soft-chip">Исправлено: {searchResponse.corrected_query}</span>
                ) : null}
                <span className="soft-chip">{searchResponse.search_time_ms.toFixed(0)} мс</span>
              </div>
            </div>

            {searchResponse.facets?.length ? (
              <div className="surface">
                <div className="section-head">
                  <div>
                    <p className="eyebrow">Фасеты</p>
                    <h3>Быстрые фильтры</h3>
                  </div>
                </div>
                <div className="chip-row">
                  {searchResponse.facets.map((facet) => (
                    <button
                      className={`soft-chip button-chip${activeCategory === facet.category ? " selected" : ""}`}
                      key={facet.category}
                      onClick={() => {
                        setActiveCategory(facet.category);
                        void runSearch(query || searchResponse.query, facet.category);
                      }}
                      type="button"
                    >
                      {facet.category} · {facet.count}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="result-grid">
              {searchResponse.items.map((item) => (
                <ResultCard
                  item={item}
                  key={item.product.id}
                  onAddToCart={() => handleAddToCart(item)}
                  onFavorite={() => handleFavorite(item)}
                  onOpen={() => handleOpenItem(item)}
                />
              ))}
            </div>
          </div>

          <aside className="surface detail-panel">
            {selectedItem ? (
              <>
                <p className="eyebrow">Карточка товара</p>
                <h3>{selectedItem.product.title}</h3>
                <p className="muted-copy">{selectedItem.product.category}</p>

                <div className="chip-row">
                  <span className="soft-chip">ID {selectedItem.product.id}</span>
                  <span className="soft-chip">Score {selectedItem.score.toFixed(1)}</span>
                </div>

                <div className="stack-block">
                  <h4>Контрактная статистика</h4>
                  <div className="detail-stat">
                    <span>Контрактов</span>
                    <strong>{formatNumber(selectedInsights?.contracts_count)}</strong>
                  </div>
                  <div className="detail-stat">
                    <span>Средняя цена</span>
                    <strong>{formatCurrency(selectedInsights?.average_price)}</strong>
                  </div>
                </div>

                <div className="stack-block">
                  <h4>Причины показа</h4>
                  <div className="chip-row">
                    {selectedItem.reasons?.map((reason) => (
                      <span className="soft-chip" key={reason}>
                        {reason}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="stack-block">
                  <h4>Атрибуты</h4>
                  <ul className="plain-list">
                    {normalizeAttributes(selectedItem.product.attributes).map((attribute) => (
                      <li key={attribute}>{attribute}</li>
                    ))}
                  </ul>
                </div>
              </>
            ) : (
              <p className="muted-copy">Откройте карточку товара, чтобы увидеть детали, цену и контрактную активность.</p>
            )}
          </aside>
        </section>
      )}

      {loadingOverview || isPending ? <div className="surface loading-box">Обновляем данные портала...</div> : null}
    </PortalShell>
  );
}
