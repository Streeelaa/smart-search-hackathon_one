"use client";

import { useDeferredValue, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchJson } from "../lib/api";
import { formatCurrency, formatNumber } from "../lib/format";
import { setSession, usePortalSession } from "../lib/session";
import { PortalShellV2 } from "./portal-shell-v2";

export function LoginPage() {
  const router = useRouter();
  const session = usePortalSession();
  const [query, setQuery] = useState("");
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pendingUserId, setPendingUserId] = useState("");
  const [error, setError] = useState("");
  const deferredQuery = useDeferredValue(query);

  useEffect(() => {
    let cancelled = false;

    fetchJson("/users", {
      searchParams: {
        q: deferredQuery,
        limit: 12,
      },
    })
      .then((response) => {
        if (!cancelled) {
          setUsers(response);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setUsers([]);
          setError("Не удалось загрузить список заказчиков.");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [deferredQuery]);

  async function handleLogin(userId) {
    try {
      setPendingUserId(userId);
      setError("");
      const account = await fetchJson("/auth/login", {
        init: {
          method: "POST",
          body: JSON.stringify({
            user_id: userId,
            role: "customer",
          }),
        },
      });
      setSession(account);
      router.push("/account");
    } catch {
      setError("Не удалось войти в личный кабинет выбранного заказчика.");
    } finally {
      setPendingUserId("");
    }
  }

  return (
    <PortalShellV2>
      <section className="account-hero-grid">
        <div className="surface-block">
          <span className="section-kicker">Вход в кабинет</span>
          <h2 className="panel-title">Выберите заказчика</h2>
          <p className="muted-copy">
            В этой версии можно войти под профилем организации из существующей базы заказчиков. После входа поиск и популярные категории
            начнут подстраиваться под историю закупок выбранного заказчика.
          </p>

          {session?.organization_name ? (
            <div className="inline-row">
              <span className="badge-soft badge-accent">Сейчас выбран: {session.organization_name}</span>
            </div>
          ) : null}

          <div className="field-stack top-gap">
            <label className="field-label" htmlFor="login-search">
              Найти организацию
            </label>
            <input
              className="field-control large"
              id="login-search"
              onChange={(event) => {
                setLoading(true);
                setQuery(event.target.value);
              }}
              placeholder="ИНН, название организации или регион"
              value={query}
            />
          </div>
        </div>

        <aside className="surface-block">
          <span className="section-kicker">Что изменится после входа</span>
          <div className="account-value-list">
            <div className="account-value-item">
              <strong>Персональная выдача</strong>
              <p className="muted-copy">Поиск начинает учитывать профиль закупок заказчика и его приоритетные категории.</p>
            </div>
            <div className="account-value-item">
              <strong>Избранное и история</strong>
              <p className="muted-copy">Сохраняются просмотренные товары, избранные позиции и поисковые сессии.</p>
            </div>
            <div className="account-value-item">
              <strong>Личный кабинет</strong>
              <p className="muted-copy">Появляется внутренний раздел с профилем, рекомендациями и активностью пользователя.</p>
            </div>
          </div>
        </aside>
      </section>

      {error ? <div className="feedback-box error-box">{error}</div> : null}

      <section className="surface-block">
        <div className="section-topline">
          <span className="section-kicker">Организации</span>
        </div>

        <div className="login-list">
          {users.map((user) => (
            <button
              className="login-user-card"
              key={user.user_id}
              onClick={() => void handleLogin(user.user_id)}
              type="button"
            >
              <div className="login-user-main">
                <strong>{user.user_name}</strong>
                <p className="muted-copy">{user.user_region || "Регион не указан"}</p>
                <div className="inline-row compact">
                  <span className="badge-soft">ИНН {user.user_id}</span>
                  {user.top_category ? <span className="badge-soft">{user.top_category}</span> : null}
                </div>
              </div>
              <div className="login-user-side">
                <span>{formatNumber(user.total_contracts)} контрактов</span>
                <strong>{formatCurrency(user.avg_price)}</strong>
                <span className="button-neutral inline-button">
                  {pendingUserId === user.user_id ? "Входим..." : "Войти"}
                </span>
              </div>
            </button>
          ))}
        </div>

        {!loading && !users.length ? <p className="muted-copy">По этому фильтру заказчики не найдены.</p> : null}
        {loading ? <p className="muted-copy">Загружаем заказчиков...</p> : null}
      </section>
    </PortalShellV2>
  );
}
