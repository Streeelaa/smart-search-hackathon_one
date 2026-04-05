const CART_KEY = "portal-cart";

function isBrowser() {
  return typeof window !== "undefined";
}

export function getCart() {
  if (!isBrowser()) {
    return [];
  }

  try {
    const raw = window.localStorage.getItem(CART_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function setCart(items) {
  if (!isBrowser()) {
    return;
  }

  window.localStorage.setItem(CART_KEY, JSON.stringify(items));
  window.dispatchEvent(new CustomEvent("portal-cart-updated"));
}

export function addToCart(item) {
  const current = getCart();
  if (current.find((entry) => entry.id === item.id)) {
    return current;
  }

  const next = [...current, item];
  setCart(next);
  return next;
}

export function removeFromCart(itemId) {
  const next = getCart().filter((item) => item.id !== itemId);
  setCart(next);
  return next;
}
