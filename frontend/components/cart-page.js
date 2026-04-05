"use client";

import { useEffect, useState } from "react";
import { getCart, removeFromCart } from "../lib/cart";
import { formatCurrency } from "../lib/format";
import { getProductImage } from "../lib/product-images";
import { PortalShellV2 } from "./portal-shell-v2";

export function CartPage() {
  const [items, setItems] = useState([]);

  useEffect(() => {
    const syncCart = () => setItems(getCart());
    syncCart();
    window.addEventListener("storage", syncCart);
    window.addEventListener("portal-cart-updated", syncCart);

    return () => {
      window.removeEventListener("storage", syncCart);
      window.removeEventListener("portal-cart-updated", syncCart);
    };
  }, []);

  return (
    <PortalShellV2>
      <section className="surface">
        <div className="section-head">
          <div>
            <p className="eyebrow">Моя корзина</p>
            <h2>Выбранные позиции</h2>
          </div>
        </div>

        {items.length ? (
          <div className="stack-list">
            {items.map((item) => (
              <div className="list-card" key={item.id}>
                <img alt={item.title} className="cart-thumb" src={getProductImage(item)} />
                <div>
                  <strong>{item.title}</strong>
                  <p className="muted-copy">{item.category}</p>
                  <p className="muted-copy">{item.averagePrice ? formatCurrency(item.averagePrice) : "Цена будет уточнена"}</p>
                </div>
                <button className="ghost-button" onClick={() => setItems(removeFromCart(item.id))} type="button">
                  Удалить
                </button>
              </div>
            ))}
          </div>
        ) : (
          <p className="muted-copy">Корзина пока пустая. Добавьте товары из поиска или каталога.</p>
        )}
      </section>
    </PortalShellV2>
  );
}
