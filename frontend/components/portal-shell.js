"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { getCart } from "../lib/cart";

export function PortalShell({ children }) {
  const pathname = usePathname();
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
  ];

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

      </header>

      <main className="page-content">{children}</main>
    </div>
  );
}
