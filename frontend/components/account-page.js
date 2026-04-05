"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { fetchJson } from "../lib/api";
import { formatCurrency, formatNumber, formatPercent, normalizeAttributes } from "../lib/format";
import { getProductImage } from "../lib/product-images";
import { setSession, usePortalSession } from "../lib/session";
import { PortalShellV2 } from "./portal-shell-v2";

const TABS = [
  { id: "profile", label: "Профиль" },
  { id: "history", label: "История просмотров" },
  { id: "favorites", label: "Избранное" },
  { id: "sessions", label: "Поисковые сессии" },
];

function ProductRecordCard({ item, actionLabel, actionButton, onAction }) {
  return (
    <div className="account-product-card">
      <img alt={item.product.title} className="account-product-thumb" src={getProductImage(item.product)} />
      <div className="account-product-copy">
        <p className="card-category-line">{item.product.category}</p>
        <strong>{item.product.title}</strong>
        <div className="inline-row compact">
          <span className="badge-soft">{formatNumber(item.contracts_count)} контрактов</span>
          <span className="badge-soft">{formatCurrency(item.average_price)}</span>
        </div>
        {normalizeAttributes(item.product.attributes).length ? (
          <ul className="plain-list compact-list">
            {normalizeAttributes(item.product.attributes).slice(0, 2).map((attribute, index) => (
              <li key={`${attribute}-${index}`}>{attribute}</li>
            ))}
          </ul>
        ) : null}
      </div>
      {onAction ? (
        <button className={actionButton || "button-neutral"} onClick={() => onAction(item)} type="button">
          {actionLabel}
        </button>
      ) : null}
    </div>
  );
}

export function AccountPage() {
  const session = usePortalSession();
  const [dashboard, setDashboard] = useState(null);
  const [activeTab, setActiveTab] = useState("profile");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    contact_name: "",
    email: "",
    phone: "",
    job_title: "",
  });

  useEffect(() => {
    if (!session?.user_id) {
      setLoading(false);
      return;
    }

    let cancelled = false;

    async function loadAccount() {
      try {
        setLoading(true);
        setError("");
        const response = await fetchJson(`/users/${session.user_id}/dashboard`, {
          searchParams: {
            categories_limit: 8,
            products_limit: 6,
            favorites_limit: 12,
            history_limit: 12,
            sessions_limit: 12,
          },
        });

        if (!cancelled) {
          setDashboard(response);
          setForm({
            contact_name: response.account.contact_name || "",
            email: response.account.email || "",
            phone: response.account.phone || "",
            job_title: response.account.job_title || "",
          });
        }
      } catch {
        if (!cancelled) {
          setError("Не удалось загрузить данные личного кабинета.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadAccount();

    return () => {
      cancelled = true;
    };
  }, [session?.user_id]);

  const topCategories = useMemo(() => {
    if (!dashboard?.profile?.category_affinity) {
      return [];
    }

    return Object.entries(dashboard.profile.category_affinity)
      .sort((left, right) => right[1] - left[1])
      .slice(0, 6);
  }, [dashboard]);

  async function handleSaveProfile() {
    if (!session?.user_id) {
      return;
    }

    try {
      setSaving(true);
      setError("");
      const nextAccount = await fetchJson(`/users/${session.user_id}/account`, {
        init: {
          method: "PUT",
          body: JSON.stringify(form),
        },
      });
      setSession(nextAccount);
      setDashboard((current) => (current ? { ...current, account: nextAccount } : current));
    } catch {
      setError("Не удалось сохранить изменения в профиле.");
    } finally {
      setSaving(false);
    }
  }

  async function handleRemoveFavorite(item) {
    if (!session?.user_id) {
      return;
    }

    try {
      await fetchJson(`/users/${session.user_id}/favorites/${item.product.id}`, {
        init: { method: "DELETE" },
      });
      setDashboard((current) => {
        if (!current) {
          return current;
        }
        return {
          ...current,
          favorite_products: current.favorite_products.filter((entry) => entry.product.id !== item.product.id),
        };
      });
    } catch {
      setError("Не удалось обновить избранное.");
    }
  }

  if (!session?.user_id) {
    return (
      <PortalShellV2>
        <section className="surface-block empty-account-state">
          <span className="section-kicker">Личный кабинет</span>
          <h2 className="panel-title">Сначала войдите как заказчик</h2>
          <p className="muted-copy">
            Кабинет открывается поверх существующей системы поиска и работает от имени выбранной организации.
          </p>
          <Link className="button-primary inline-button" href="/login">
            Перейти ко входу
          </Link>
        </section>
      </PortalShellV2>
    );
  }

  return (
    <PortalShellV2>
      <section className="account-hero-grid">
        <div className="surface-block">
          <span className="section-kicker">Личный кабинет</span>
          <h2 className="panel-title">{dashboard?.account.organization_name || session.organization_name}</h2>
          <p className="muted-copy">{dashboard?.account.user_region || "Регион не указан"}</p>

          <div className="stat-grid three-up">
            <div className="stat-card">
              <span>Контрактов</span>
              <strong>{formatNumber(dashboard?.account.total_contracts)}</strong>
            </div>
            <div className="stat-card">
              <span>Средний чек</span>
              <strong>{formatCurrency(dashboard?.account.avg_price)}</strong>
            </div>
            <div className="stat-card">
              <span>Роль</span>
              <strong>{dashboard?.account.role || "customer"}</strong>
            </div>
          </div>
        </div>

        <aside className="surface-block">
          <span className="section-kicker">Профиль интересов</span>
          <div className="account-meter-list">
            {topCategories.map(([category, score]) => (
              <div className="meter-row large" key={category}>
                <span>{category}</span>
                <div className="meter-track">
                  <div className="meter-fill" style={{ width: `${Math.min(score * 100, 100)}%` }} />
                </div>
                <strong>{formatPercent(score)}</strong>
              </div>
            ))}
          </div>
        </aside>
      </section>

      {error ? <div className="feedback-box error-box">{error}</div> : null}

      <section className="account-layout">
        <aside className="surface-block account-sidebar">
          <div className="account-nav-list">
            {TABS.map((tab) => (
              <button
                className={`account-nav-item${activeTab === tab.id ? " active" : ""}`}
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                type="button"
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="account-side-info">
            <span className="section-kicker">Рекомендуем</span>
            <p className="muted-copy">После входа поиск и главная страница используют этот профиль заказчика для персонализации выдачи.</p>
          </div>
        </aside>

        <div className="account-main-column">
          {activeTab === "profile" ? (
            <section className="surface-block">
              <div className="section-topline">
                <span className="section-kicker">Профиль пользователя</span>
              </div>

              <div className="account-form-grid">
                <div className="field-stack">
                  <label className="field-label" htmlFor="contact-name">
                    Контактное лицо
                  </label>
                  <input
                    className="field-control"
                    id="contact-name"
                    onChange={(event) => setForm((current) => ({ ...current, contact_name: event.target.value }))}
                    value={form.contact_name}
                  />
                </div>

                <div className="field-stack">
                  <label className="field-label" htmlFor="job-title">
                    Должность
                  </label>
                  <input
                    className="field-control"
                    id="job-title"
                    onChange={(event) => setForm((current) => ({ ...current, job_title: event.target.value }))}
                    value={form.job_title}
                  />
                </div>

                <div className="field-stack">
                  <label className="field-label" htmlFor="email">
                    Email
                  </label>
                  <input
                    className="field-control"
                    id="email"
                    onChange={(event) => setForm((current) => ({ ...current, email: event.target.value }))}
                    value={form.email}
                  />
                </div>

                <div className="field-stack">
                  <label className="field-label" htmlFor="phone">
                    Телефон
                  </label>
                  <input
                    className="field-control"
                    id="phone"
                    onChange={(event) => setForm((current) => ({ ...current, phone: event.target.value }))}
                    value={form.phone}
                  />
                </div>
              </div>

              <div className="account-summary-grid">
                <div className="summary-card">
                  <span>Организация</span>
                  <strong>{dashboard?.account.organization_name}</strong>
                </div>
                <div className="summary-card">
                  <span>ИНН заказчика</span>
                  <strong>{dashboard?.account.user_id}</strong>
                </div>
                <div className="summary-card">
                  <span>Основная категория</span>
                  <strong>{dashboard?.account.top_category || "—"}</strong>
                </div>
              </div>

              <div className="inline-row top-gap">
                <button className="button-primary inline-button" disabled={saving} onClick={() => void handleSaveProfile()} type="button">
                  {saving ? "Сохраняем..." : "Сохранить профиль"}
                </button>
              </div>
            </section>
          ) : null}

          {activeTab === "history" ? (
            <section className="surface-block">
              <div className="section-topline">
                <span className="section-kicker">История просмотров</span>
              </div>
              <div className="account-product-list">
                {(dashboard?.viewed_products || []).map((item) => (
                  <ProductRecordCard item={item} key={item.product.id} />
                ))}
              </div>
              {!loading && !dashboard?.viewed_products?.length ? <p className="muted-copy">История просмотров пока пустая.</p> : null}
            </section>
          ) : null}

          {activeTab === "favorites" ? (
            <section className="surface-block">
              <div className="section-topline">
                <span className="section-kicker">Избранные товары</span>
              </div>
              <div className="account-product-list">
                {(dashboard?.favorite_products || []).map((item) => (
                  <ProductRecordCard
                    actionButton="button-link"
                    actionLabel="Убрать"
                    item={item}
                    key={item.product.id}
                    onAction={handleRemoveFavorite}
                  />
                ))}
              </div>
              {!loading && !dashboard?.favorite_products?.length ? <p className="muted-copy">В избранном пока нет товаров.</p> : null}
            </section>
          ) : null}

          {activeTab === "sessions" ? (
            <section className="surface-block">
              <div className="section-topline">
                <span className="section-kicker">Поисковые сессии</span>
              </div>
              <div className="account-session-list">
                {(dashboard?.search_sessions || []).map((sessionItem, index) => (
                  <div className="account-session-card" key={`${sessionItem.query}-${sessionItem.timestamp}-${index}`}>
                    <div>
                      <strong>{sessionItem.query}</strong>
                      <p className="muted-copy">
                        {sessionItem.category ? `Категория: ${sessionItem.category}` : "Без категории"}
                      </p>
                    </div>
                    <span className="badge-soft">{new Date(sessionItem.timestamp).toLocaleString("ru-RU")}</span>
                  </div>
                ))}
              </div>
              {!loading && !dashboard?.search_sessions?.length ? <p className="muted-copy">Поисковые сессии пока не сформированы.</p> : null}
            </section>
          ) : null}

          <section className="surface-block">
            <div className="section-topline">
              <span className="section-kicker">Популярные товары для этого заказчика</span>
            </div>
            <div className="account-product-list">
              {(dashboard?.popular_products || []).map((item) => (
                <ProductRecordCard item={item} key={item.product.id} />
              ))}
            </div>
          </section>
        </div>
      </section>
    </PortalShellV2>
  );
}
