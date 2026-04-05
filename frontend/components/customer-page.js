"use client";

import { useEffect, useMemo, useState } from "react";
import { fetchJson } from "../lib/api";
import { formatCurrency, formatNumber, formatPercent } from "../lib/format";
import { PortalShell } from "./portal-shell";

export function CustomerPage({ userId }) {
  const [summary, setSummary] = useState(null);
  const [profile, setProfile] = useState(null);
  const [events, setEvents] = useState([]);
  const [query, setQuery] = useState("");
  const [searchResponse, setSearchResponse] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadPage() {
      try {
        setError("");
        const [usersResponse, profileResponse, eventsResponse] = await Promise.all([
          fetchJson("/users", { searchParams: { q: userId, limit: 10 } }),
          fetchJson(`/users/${userId}/profile`),
          fetchJson(`/users/${userId}/events`),
        ]);

        if (cancelled) {
          return;
        }

        setSummary(usersResponse.find((user) => user.user_id === userId) || null);
        setProfile(profileResponse);
        setEvents(eventsResponse);
      } catch {
        if (!cancelled) {
          setError("Не удалось загрузить профиль заказчика.");
        }
      }
    }

    loadPage();

    return () => {
      cancelled = true;
    };
  }, [userId]);

  const topCategories = useMemo(() => {
    if (!profile?.category_affinity) {
      return [];
    }

    return Object.entries(profile.category_affinity)
      .sort((left, right) => right[1] - left[1])
      .slice(0, 8);
  }, [profile]);

  async function handlePersonalizedSearch() {
    if (!query.trim()) {
      return;
    }

    try {
      const response = await fetchJson("/search", {
        searchParams: {
          q: query,
          user_id: userId,
          limit: 5,
        },
      });
      setSearchResponse(response);
    } catch {
      setSearchResponse(null);
    }
  }

  return (
    <PortalShell>
      <section className="hero-grid">
        <div className="surface elevated hero-panel">
          <p className="eyebrow">Профиль заказчика</p>
          <h2>{summary?.user_name || `Организация ${userId}`}</h2>
          <p className="lead-copy">{summary?.user_region || "Регион не указан"}</p>

          <div className="stat-grid">
            <div className="stat-card">
              <span>Контракты</span>
              <strong>{formatNumber(summary?.total_contracts || profile?.total_events)}</strong>
            </div>
            <div className="stat-card">
              <span>Средний чек</span>
              <strong>{formatCurrency(summary?.avg_price || profile?.average_price)}</strong>
            </div>
            <div className="stat-card">
              <span>Категории</span>
              <strong>{formatNumber(topCategories.length)}</strong>
            </div>
          </div>
        </div>

        <aside className="surface spotlight-panel">
          <p className="eyebrow">Основной интерес</p>
          <h3>{summary?.top_category || topCategories[0]?.[0] || "Пока нет данных"}</h3>
          <p className="muted-copy">
            Эта карточка показывает, как персонализация может смещать результаты в сторону привычных закупок организации.
          </p>
        </aside>
      </section>

      {error ? <div className="surface error-box">{error}</div> : null}

      <section className="showcase-grid">
        <div className="surface">
          <div className="section-head">
            <div>
              <p className="eyebrow">Категории</p>
              <h3>Профиль интересов</h3>
            </div>
          </div>
          <div className="stack-block">
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
        </div>

        <div className="surface">
          <div className="section-head">
            <div>
              <p className="eyebrow">Активность</p>
              <h3>Последние события</h3>
            </div>
          </div>
          <div className="timeline-list">
            {events.slice(0, 10).map((event) => (
              <div className="timeline-item" key={event.event_id}>
                <strong>{event.event_type}</strong>
                <p className="muted-copy">{event.query || event.metadata?.title || "Без текста"}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="surface">
        <div className="section-head">
          <div>
            <p className="eyebrow">Персонализированный поиск</p>
            <h3>Проверка выдачи для этой организации</h3>
          </div>
        </div>

        <div className="search-toolbar">
          <div className="field-block grow">
            <label htmlFor="profile-search">Запрос</label>
            <input
              className="field-input"
              id="profile-search"
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  void handlePersonalizedSearch();
                }
              }}
              placeholder="Например: шприц, фильтр, бумага"
              value={query}
            />
          </div>
          <button className="primary-button" onClick={() => void handlePersonalizedSearch()} type="button">
            Показать выдачу
          </button>
        </div>

        {searchResponse ? (
          <div className="stack-list">
            {searchResponse.items.map((item) => (
              <div className="list-card" key={item.product.id}>
                <div>
                  <strong>{item.product.title}</strong>
                  <p className="muted-copy">{item.product.category}</p>
                </div>
                <span className="soft-chip">Score {item.score.toFixed(1)}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="muted-copy">Введите запрос, чтобы увидеть, как срабатывает персонализация для этого профиля.</p>
        )}
      </section>
    </PortalShell>
  );
}
