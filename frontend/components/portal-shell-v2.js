"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getCart } from "../lib/cart";
import { clearSession, usePortalSession } from "../lib/session";

export function PortalShellV2({ children }) {
  const router = useRouter();
  const pathname = usePathname();
  const session = usePortalSession();
  const [cartCount, setCartCount] = useState(0);

  useEffect(() => {
    const syncCart = () => setCartCount(getCart().length);
    syncCart();
    window.addEventListener("storage", syncCart);
    window.addEventListener("portal-cart-updated", syncCart);

    return () => {
      window.removeEventListener("storage", syncCart);
      window.removeEventListener("portal-cart-updated", syncCart);
    };
  }, []);

  const navItems = [
    { href: "/", label: "Поиск" },
    { href: "/catalog", label: "Каталог" },
    { href: "/cart", label: `Корзина${cartCount ? ` (${cartCount})` : ""}` },
    { href: session ? "/account" : "/login", label: session ? "Личный кабинет" : "Войти" },
  ];

  const accountLabel =
    session?.contact_name ||
    session?.organization_name ||
    session?.user_id ||
    "";

  return (
    <div className="page-shell">
      <header className="topbar">
        <div className="brand-block">
          <Link className="brand-mark" href="/">
            SP
          </Link>
          <div>
            <p className="eyebrow">Smart Search Portal</p>
            <h1 className="brand-title">Портал поставщиков</h1>
          </div>
        </div>

        <nav aria-label="Основная навигация" className="main-nav">
          {navItems.map((item) => {
            const active = pathname === item.href;
            return (
              <Link className={`nav-link${active ? " active" : ""}`} href={item.href} key={item.href}>
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="header-account-block">
          {session ? (
            <>
              <Link className={`account-chip${pathname === "/account" ? " active" : ""}`} href="/account">
                <span className="account-chip-label">Заказчик</span>
                <strong>{accountLabel}</strong>
              </Link>
              <button
                className="button-link header-logout"
                onClick={() => {
                  clearSession();
                  router.push("/");
                }}
                type="button"
              >
                Выйти
              </button>
            </>
          ) : (
            <Link className="account-chip ghost" href="/login">
              <span className="account-chip-label">Вход</span>
              <strong>Войти как заказчик</strong>
            </Link>
          )}
        </div>
      </header>

      <main className="page-content">{children}</main>
    </div>
  );
}
