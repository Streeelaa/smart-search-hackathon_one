"use client";

import { useDeferredValue, useEffect, useMemo, useState } from "react";
import { createEvent, fetchJson } from "../lib/api";
import { addToCart } from "../lib/cart";
import { formatCurrency, formatNumber, normalizeAttributes } from "../lib/format";
import { PortalShell } from "./portal-shell";

const PAGE_SIZE = 18;

export function CatalogPage() {
  const [categories, setCategories] = useState([]);
  const [items, setItems] = useState([]);
  const [activeCategory, setActiveCategory] = useState("");
  const [query, setQuery] = useState("");
  const [categoryQuery, setCategoryQuery] = useState("");
  const [page, setPage] = useState(0);
  const [selectedItem, setSelectedItem] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const deferredQuery = useDeferredValue(query);
  const deferredCategoryQuery = useDeferredValue(categoryQuery);

  useEffect(() => {
    let cancelled = false;

    fetchJson("/catalog/categories", {
      searchParams: {
        q: deferredCategoryQuery,
        limit: 20,
      },
    })
      .then((response) => {
        if (!cancelled) {
          setCategories(response);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCategories([]);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [deferredCategoryQuery]);

  useEffect(() => {
    let cancelled = false;

    async function loadItems() {
      try {
        setLoading(true);
        setError("");
        const response = await fetchJson("/catalog/items", {
          searchParams: {
            category: activeCategory,
            q: deferredQuery,
            limit: PAGE_SIZE,
            offset: page * PAGE_SIZE,
          },
        });

        if (cancelled) {
          return;
        }

        setItems(response);
        setSelectedItem((current) => {
          if (!current) {
            return response[0] || null;
          }
          return response.find((item) => item.product.id === current.product.id) || response[0] || null;
        });
      } catch {
        if (!cancelled) {
          setError("Каталог пока не отвечает.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadItems();

    return () => {
      cancelled = true;
    };
  }, [activeCategory, deferredQuery, page]);

  const canGoNext = useMemo(() => items.length === PAGE_SIZE, [items.length]);

  function handleFavorite(item) {
    void createEvent({
      user_id: "portal-web",
      event_type: "favorite",
      item_id: item.product.id,
      metadata: { source: "catalog" },
    }).catch(() => null);
  }

  return (
    <PortalShell>
      <section className="catalog-layout">
        <aside className="surface sidebar-panel">
          <div className="section-head">
            <div>
              <p className="eyebrow">Навигация</p>
              <h2>Категории</h2>
            </div>
          </div>

          <div className="field-block">
            <label htmlFor="category-search">Поиск категории</label>
            <input
              className="field-input"
              id="category-search"
              onChange={(event) => setCategoryQuery(event.target.value)}
              placeholder="Например: канцелярия"
              value={categoryQuery}
            />
          </div>

          <div className="category-list">
            <button
              className={`category-link${!activeCategory ? " active" : ""}`}
              onClick={() => {
                setActiveCategory("");
                setPage(0);
              }}
              type="button"
            >
              Все категории
            </button>
            {categories.map((category) => (
              <button
                className={`category-link${activeCategory === category.category ? " active" : ""}`}
                key={category.category}
                onClick={() => {
                  setActiveCategory(category.category);
                  setPage(0);
                }}
                type="button"
              >
                <span>{category.category}</span>
                <span>{formatNumber(category.count)}</span>
              </button>
            ))}
          </div>
        </aside>

        <div className="results-column">
          <section className="surface">
            <div className="section-head">
              <div>
                <p className="eyebrow">Каталог</p>
                <h2>Товары и позиции</h2>
              </div>
              <div className="chip-row">
                {activeCategory ? <span className="soft-chip accent-chip">{activeCategory}</span> : null}
                <span className="soft-chip">Страница {page + 1}</span>
              </div>
            </div>

            <div className="search-toolbar">
              <div className="field-block grow">
                <label htmlFor="catalog-query">Поиск по названию</label>
                <input
                  className="field-input"
                  id="catalog-query"
                  onChange={(event) => {
                    setQuery(event.target.value);
                    setPage(0);
                  }}
                  placeholder="Фильтр по названию товара"
                  value={query}
                />
              </div>
            </div>
          </section>

          {error ? <div className="surface error-box">{error}</div> : null}

          <div className="catalog-grid">
            {items.map((item) => (
              <article className="catalog-card surface" key={item.product.id}>
                <div className="result-header">
                  <div>
                    <p className="result-category">{item.product.category}</p>
                    <h3>{item.product.title}</h3>
                  </div>
                </div>

                <div className="chip-row">
                  <span className="soft-chip">{formatNumber(item.insights.contracts_count)} контрактов</span>
                  <span className="soft-chip">{formatCurrency(item.insights.average_price)}</span>
                </div>

                <ul className="plain-list">
                  {normalizeAttributes(item.product.attributes).slice(0, 3).map((attribute) => (
                    <li key={attribute}>{attribute}</li>
                  ))}
                </ul>

                <div className="actions-row">
                  <button className="secondary-button" onClick={() => setSelectedItem(item)} type="button">
                    Подробнее
                  </button>
                  <button
                    className="secondary-button"
                    onClick={() =>
                      addToCart({
                        id: item.product.id,
                        title: item.product.title,
                        category: item.product.category,
                        averagePrice: item.insights.average_price,
                      })
                    }
                    type="button"
                  >
                    В корзину
                  </button>
                  <button className="ghost-button" onClick={() => handleFavorite(item)} type="button">
                    В избранное
                  </button>
                </div>
              </article>
            ))}
          </div>

          {!loading && !items.length ? (
            <div className="surface loading-box">По этому фильтру товары не найдены.</div>
          ) : null}

          <div className="surface pager-row">
            <button className="secondary-button" disabled={page === 0} onClick={() => setPage((current) => current - 1)} type="button">
              Назад
            </button>
            <button className="secondary-button" disabled={!canGoNext} onClick={() => setPage((current) => current + 1)} type="button">
              Дальше
            </button>
          </div>
        </div>

        <aside className="surface detail-panel">
          {selectedItem ? (
            <>
              <p className="eyebrow">Подробности</p>
              <h3>{selectedItem.product.title}</h3>
              <p className="muted-copy">{selectedItem.product.category}</p>

              <div className="detail-stat">
                <span>Контрактов</span>
                <strong>{formatNumber(selectedItem.insights.contracts_count)}</strong>
              </div>
              <div className="detail-stat">
                <span>Средняя цена</span>
                <strong>{formatCurrency(selectedItem.insights.average_price)}</strong>
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
            <p className="muted-copy">Выберите товар, чтобы открыть детальную карточку справа.</p>
          )}
        </aside>
      </section>

      {loading ? <div className="surface loading-box">Загружаем каталог...</div> : null}
    </PortalShell>
  );
}
