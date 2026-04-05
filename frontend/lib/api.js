const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

function buildUrl(path, searchParams) {
  const url = new URL(path, API_BASE_URL);
  if (searchParams) {
    Object.entries(searchParams).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, String(value));
      }
    });
  }
  return url.toString();
}

export async function fetchJson(path, { searchParams, signal, init } = {}) {
  const response = await fetch(buildUrl(path, searchParams), {
    ...init,
    signal,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }

  return response.json();
}

export async function createEvent(payload) {
  return fetchJson("/events", {
    init: {
      method: "POST",
      body: JSON.stringify(payload),
    },
  });
}

export { API_BASE_URL };
