"use client";

import { useDeferredValue, useEffect, useMemo, useState } from "react";
import { createEvent, fetchJson } from "../lib/api";
import { addToCart } from "../lib/cart";
import { formatCurrency, formatNumber, normalizeAttributes } from "../lib/format";
import { PortalShell } from "./portal-shell";

const PAGE_SIZE = 12;

function CatalogListCard({ item, isActive, onAddToCart, onFavorite, onOpen }) {
  return (
    <article className={`catalog-list-card${isActive ? " active" : ""}`}>
      <p className="card-category-line">{item.product.category}</p>
      <h3 className="card-title">{item.product.title}</h3>

      <div className="inline-row">
        <span className="badge-soft">{formatNumber(item.insights.contracts_count)} контрактов</span>
        <span className="badge-soft">{formatCurrency(item.insights.average_price)}</span>
      </div>

      <ul className="plain-list">
        {normalizeAttributes(item.product.attributes).slice(0, 3).map((attribute) => (
          <li key={attribute}>{attribute}</li>
        ))}
      </ul>

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

export function CatalogPageV2() {
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
          setError("Каталог временно недоступен.");
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

  function favoriteItem(item) {
    void createEvent({
      user_id: "portal-web",
      event_type: "favorite",
      item_id: item.product.id,
      metadata: { source: "catalog" },
    }).catch(() => null);
  }

  return (
    <PortalShell>
      <section className="catalog-v2-layout">
        <aside className="catalog-sidebar">
          <div className="surface-block">
            <span className="section-kicker">Навигация</span>
            <h2 className="panel-title">Категории</h2>

            <div className="field-stack">
              <label className="field-label" htmlFor="category-search">
                Поиск категории
              </label>
              <input
                className="field-control"
                id="category-search"
                onChange={(event) => setCategoryQuery(event.target.value)}
                placeholder="Например: канцелярия"
                value={categoryQuery}
              />
            </div>

            <div className="catalog-category-list">
              <button
                className={`catalog-category-item${!activeCategory ? " active" : ""}`}
                onClick={() => {
                  setActiveCategory("");
                  setPage(0);
                }}
                type="button"
              >
                <span>Все категории</span>
              </button>

              {categories.map((category) => (
                <button
                  className={`catalog-category-item${activeCategory === category.category ? " active" : ""}`}
                  key={category.category}
                  onClick={() => {
                    setActiveCategory(category.category);
                    setPage(0);
                  }}
                  type="button"
                >
                  <span>{category.category}</span>
                  <strong>{formatNumber(category.count)}</strong>
                </button>
              ))}
            </div>
          </div>
        </aside>

        <div className="catalog-content">
          <section className="surface-block">
            <div className="catalog-header-line">
              <div>
                <span className="section-kicker">Каталог</span>
                <h2 className="panel-title">Товары и позиции</h2>
              </div>
              <span className="badge-soft">Страница {page + 1}</span>
            </div>

            <div className="field-stack">
              <label className="field-label" htmlFor="catalog-query">
                Поиск по названию
              </label>
              <input
                className="field-control"
                id="catalog-query"
                onChange={(event) => {
                  setQuery(event.target.value);
                  setPage(0);
                }}
                placeholder="Фильтр по названию товара"
                value={query}
              />
            </div>
          </section>

          {error ? <div className="feedback-box error-box">{error}</div> : null}

          <div className="catalog-list">
            {items.map((item) => (
              <CatalogListCard
                isActive={selectedItem?.product.id === item.product.id}
                item={item}
                key={item.product.id}
                onAddToCart={() =>
                  addToCart({
                    id: item.product.id,
                    title: item.product.title,
                    category: item.product.category,
                    averagePrice: item.insights.average_price,
                  })
                }
                onFavorite={() => favoriteItem(item)}
                onOpen={() => setSelectedItem(item)}
              />
            ))}
          </div>

          {!loading && !items.length ? <div className="feedback-box">По этому фильтру ничего не найдено.</div> : null}

          <div className="surface-block pager-v2">
            <button className="button-neutral" disabled={page === 0} onClick={() => setPage((value) => value - 1)} type="button">
              Назад
            </button>
            <button className="button-neutral" disabled={!canGoNext} onClick={() => setPage((value) => value + 1)} type="button">
              Дальше
            </button>
          </div>
        </div>

        <aside className="catalog-detail">
          <div className="surface-block sticky-panel">
            {selectedItem ? (
              <>
                <span className="section-kicker">Подробности</span>
                <h2 className="side-title">{selectedItem.product.title}</h2>
                <p className="side-category">{selectedItem.product.category}</p>

                <div className="side-stats">
                  <div className="side-stat">
                    <span>Контрактов</span>
                    <strong>{formatNumber(selectedItem.insights.contracts_count)}</strong>
                  </div>
                  <div className="side-stat">
                    <span>Средняя цена</span>
                    <strong>{formatCurrency(selectedItem.insights.average_price)}</strong>
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
              <p className="muted-copy">Выберите товар, чтобы открыть карточку.</p>
            )}
          </div>
        </aside>
      </section>

      {loading ? <div className="feedback-box">Загружаем каталог...</div> : null}
    </PortalShell>
  );
}
