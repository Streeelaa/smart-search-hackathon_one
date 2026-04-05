export function formatNumber(value) {
  return new Intl.NumberFormat("ru-RU").format(value || 0);
}

export function formatCurrency(value) {
  if (!value) {
    return "—";
  }

  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatPercent(value) {
  return `${Math.round((value || 0) * 100)}%`;
}

export function normalizeAttributes(attributes) {
  const raw = attributes?.raw;
  if (!raw) {
    return [];
  }

  return String(raw)
    .split(/[;,]/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 10);
}
