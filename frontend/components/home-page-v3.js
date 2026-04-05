"use client";

import { useDeferredValue, useEffect, useState } from "react";
import { createEvent, fetchJson } from "../lib/api";
import { addToCart } from "../lib/cart";
import { formatCurrency, formatNumber, normalizeAttributes } from "../lib/format";
import { getProductImage } from "../lib/product-images";
import { PortalShell } from "./portal-shell";

function SearchGuidance({ categories, onPick, query }) {
  if (!categories.length) {
    return null;
  }

  return (
    <div className="suggestion-card">
      <p className="suggestion-title">Где искать «{query}»</p>
      <div className="suggestion-column">
        {categories.map((category) => (
          <button className="suggestion-row" key={category.category} onClick={() => onPick(category.category)} type="button">
            <span className="suggestion-main">Искать в категории: {category.category}</span>
            <span className="suggestion-side">{formatNumber(category.count)}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function ProductSuggestions({ items, onPick }) {
  if (!items.length) {
    return null;
  }

  return (
    <div className="suggestion-card">
      <p className="suggestion-title">Подходящие товары</p>
      <div className="suggestion-column">
        {items.map((item) => (
          <button className="suggestion-row" key={`${item.type}-${item.id || item.title}`} onClick={() => onPick(item)} type="button">
            <span className="suggestion-main">{item.title}</span>
            <span className="suggestion-side">{item.category || "товар"}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function SearchCard({ item, isActive, onAddToCart, onOpen, onFavorite }) {
  const attrs = normalizeAttributes(item.product.attributes).slice(0, 3);

  return (
    <article className={`search-card${isActive ? " active" : ""}`}>
      <div className="card-layout">
        <div className="card-media-wrap">
          <img alt={item.product.title} className="card-media" src={getProductImage(item.product)} />
        </div>

        <div className="card-body">
          <p className="card-category-line">{item.product.category}</p>
          <h3 className="card-title">{item.product.title}</h3>

          <div className="card-meta-row">
            <span className="badge-soft">ID {item.product.id}</span>
          </div>

          {attrs.length ? (
            <ul className="plain-list">
              {attrs.map((attribute) => (
                <li key={attribute}>{attribute}</li>
              ))}
            </ul>
          ) : (
            <p className="muted-copy">Описание товара появится здесь, когда по позиции есть атрибуты.</p>
          )}
        </div>
      </div>

      <div className="card-actions-row">
        <button className="button-neutral" onClick={onOpen} type="button">
          Открыть карточку
        </button>
        <button className="button-neutral" onClick={onAddToCart} type="button">
          В корзину
        </button>
        <button className="button-link" onClick={onFavorite} type="button">
          В избранное
        </button>
      </div>
    </article>
  );
}

export function HomePageV3() {
  const [overview, setOverview] = useState(null);
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState(8);
  const [activeCategory, setActiveCategory] = useState("");
  const [searchResponse, setSearchResponse] = useState(null);
  const [selectedItem, setSelectedItem] = useState(null);
  const [selectedInsights, setSelectedInsights] = useState(null);
  const [categorySuggestions, setCategorySuggestions] = useState([]);
  const [productSuggestions, setProductSuggestions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadingOverview, setLoadingOverview] = useState(true);
  const [error, setError] = useState("");
  const deferredQuery = useDeferredValue(query);

  useEffect(() => {
    let cancelled = false;

    fetchJson("/portal/overview", { searchParams: { limit_categories: 12, limit_users: 1 } })
      .then((response) => {
        if (!cancelled) {
          setOverview(response);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError("Не удалось загрузить стартовые категории.");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingOverview(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!deferredQuery || deferredQuery.trim().length < 2) {
      setCategorySuggestions([]);
      setProductSuggestions([]);
      return;
    }

    let cancelled = false;
    const controller = new AbortController();

    Promise.all([
      fetchJson("/search/disambiguate", {
        searchParams: { q: deferredQuery, limit: 6 },
        signal: controller.signal,
      }),
      fetchJson("/search/suggest", {
        searchParams: { q: deferredQuery, limit: 4 },
        signal: controller.signal,
      }),
    ])
      .then(([categories, products]) => {
        if (cancelled) {
          return;
        }

        setCategorySuggestions(categories);
        setProductSuggestions(products.filter((item) => item.type === "product"));
      })
      .catch(() => {
        if (!cancelled) {
          setCategorySuggestions([]);
          setProductSuggestions([]);
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

  async function runSearch(nextQuery = query, nextCategory = activeCategory) {
    const cleanQuery = nextQuery.trim();
    if (!cleanQuery) {
      setError("Введите поисковый запрос.");
      return;
    }

    try {
      setLoading(true);
      setError("");
      const response = await fetchJson("/search", {
        searchParams: {
          q: cleanQuery,
          category: nextCategory,
          limit,
        },
      });

      setSearchResponse(response);
      setSelectedItem(response.items?.[0] || null);

      void createEvent({
        user_id: "portal-web",
        event_type: "search",
        query: cleanQuery,
        metadata: nextCategory ? { category: nextCategory } : {},
      }).catch(() => null);
    } catch {
      setError("Не удалось выполнить поиск.");
    } finally {
      setLoading(false);
    }
  }

  function handleCategorySuggestion(category) {
    setActiveCategory(category);
    void runSearch(query, category);
  }

  function handleProductSuggestion(item) {
    setQuery(item.title);
    setCategorySuggestions([]);
    setProductSuggestions([]);
    void runSearch(item.title, activeCategory);
  }

  function openItem(item) {
    setSelectedItem(item);
    void createEvent({
      user_id: "portal-web",
      event_type: "click",
      item_id: item.product.id,
      query: searchResponse?.query || query || null,
    }).catch(() => null);
  }

  function addItemToCart(item) {
    addToCart({
      id: item.product.id,
      title: item.product.title,
      category: item.product.category,
      averagePrice: selectedItem?.product.id === item.product.id ? selectedInsights?.average_price : null,
    });
  }

  function favoriteItem(item) {
    void createEvent({
      user_id: "portal-web",
      event_type: "favorite",
      item_id: item.product.id,
      query: searchResponse?.query || query || null,
    }).catch(() => null);
  }

  return (
    <PortalShell>
      <section className="search-surface">
        <div className="search-form-grid">
          <div className="field-stack field-grow">
            <label className="field-label" htmlFor="portal-search">
              Что ищем
            </label>
            <input
              className="field-control large"
              id="portal-search"
              onChange={(event) => {
                setQuery(event.target.value);
                setSearchResponse(null);
                setSelectedItem(null);
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  void runSearch();
                }
              }}
              placeholder="Например: масло, ноутбук, перчатки"
              value={query}
            />
          </div>

          <div className="field-stack field-compact">
            <label className="field-label" htmlFor="search-limit">
              Показывать
            </label>
            <select className="field-control" id="search-limit" onChange={(event) => setLimit(Number(event.target.value))} value={limit}>
              <option value="8">8</option>
              <option value="12">12</option>
              <option value="16">16</option>
            </select>
          </div>

          <button className="button-primary search-submit" disabled={loading} onClick={() => void runSearch()} type="button">
            {loading ? "Поиск..." : "Найти"}
          </button>
        </div>

        {activeCategory ? (
          <div className="inline-row">
            <span className="badge-soft badge-accent">Категория: {activeCategory}</span>
            <button className="button-link" onClick={() => setActiveCategory("")} type="button">
              Сбросить
            </button>
          </div>
        ) : null}

        {deferredQuery?.trim().length >= 2 && !searchResponse ? (
          <div className="suggestions-layout">
            <SearchGuidance categories={categorySuggestions} onPick={handleCategorySuggestion} query={deferredQuery} />
            <ProductSuggestions items={productSuggestions} onPick={handleProductSuggestion} />
          </div>
        ) : null}
      </section>

      {error ? <div className="feedback-box error-box">{error}</div> : null}

      {!searchResponse ? (
        <section className="surface-block">
          <div className="section-topline">
            <span className="section-kicker">Популярные категории</span>
          </div>
          <div className="category-chip-list">
            {(overview?.featured_categories || []).map((category) => (
              <button
                className="category-choice"
                key={category.category}
                onClick={() => {
                  setQuery(category.category);
                  setActiveCategory(category.category);
                  void runSearch(category.category, category.category);
                }}
                type="button"
              >
                <span>{category.category}</span>
                <strong>{formatNumber(category.count)}</strong>
              </button>
            ))}
          </div>

          {loadingOverview ? <p className="muted-copy">Загружаем популярные категории...</p> : null}
        </section>
      ) : (
        <section className="search-results-layout">
          <div className="results-main">
            <div className="results-inline-meta">
              <strong>{formatNumber(searchResponse.total)} найдено</strong>
              <span>по запросу «{searchResponse.query}»</span>
              {searchResponse.corrected_query && searchResponse.corrected_query !== searchResponse.query ? (
                <span>исправлено на «{searchResponse.corrected_query}»</span>
              ) : null}
            </div>

            {searchResponse.facets?.length ? (
              <div className="facet-inline-row">
                {searchResponse.facets.slice(0, 8).map((facet) => (
                  <button
                    className={`badge-soft badge-filter${activeCategory === facet.category ? " selected" : ""}`}
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
            ) : null}

            <div className="search-card-list">
              {searchResponse.items.map((item) => (
                <SearchCard
                  isActive={selectedItem?.product.id === item.product.id}
                  item={item}
                  key={item.product.id}
                  onAddToCart={() => addItemToCart(item)}
                  onFavorite={() => favoriteItem(item)}
                  onOpen={() => openItem(item)}
                />
              ))}
            </div>
          </div>

          <aside className="product-side-panel">
            {selectedItem ? (
              <>
                <span className="section-kicker">Карточка товара</span>
                <img alt={selectedItem.product.title} className="side-media" src={getProductImage(selectedItem.product)} />
                <h2 className="side-title">{selectedItem.product.title}</h2>
                <p className="side-category">{selectedItem.product.category}</p>

                <div className="side-stats">
                  <div className="side-stat">
                    <span>ID</span>
                    <strong>{selectedItem.product.id}</strong>
                  </div>
                  <div className="side-stat">
                    <span>Контрактов</span>
                    <strong>{formatNumber(selectedInsights?.contracts_count)}</strong>
                  </div>
                  <div className="side-stat">
                    <span>Средняя цена</span>
                    <strong>{formatCurrency(selectedInsights?.average_price)}</strong>
                  </div>
                </div>

                <div className="side-section">
                  <h3>Атрибуты</h3>
                  <ul className="plain-list">
                    {normalizeAttributes(selectedItem.product.attributes).map((attribute) => (
                      <li key={attribute}>{attribute}</li>
                    ))}
                  </ul>
                </div>
              </>
            ) : (
              <p className="muted-copy">Откройте карточку товара, чтобы посмотреть детали.</p>
            )}
          </aside>
        </section>
      )}
    </PortalShell>
  );
}
