"use client";

import { useEffect, useState } from "react";

const SESSION_KEY = "portal-user-session";

function isBrowser() {
  return typeof window !== "undefined";
}

export function getSession() {
  if (!isBrowser()) {
    return null;
  }

  try {
    const raw = window.localStorage.getItem(SESSION_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function setSession(session) {
  if (!isBrowser()) {
    return;
  }

  window.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  window.dispatchEvent(new CustomEvent("portal-session-updated"));
}

export function clearSession() {
  if (!isBrowser()) {
    return;
  }

  window.localStorage.removeItem(SESSION_KEY);
  window.dispatchEvent(new CustomEvent("portal-session-updated"));
}

export function usePortalSession() {
  const [session, setSessionState] = useState(null);

  useEffect(() => {
    const syncSession = () => setSessionState(getSession());
    syncSession();

    window.addEventListener("storage", syncSession);
    window.addEventListener("portal-session-updated", syncSession);

    return () => {
      window.removeEventListener("storage", syncSession);
      window.removeEventListener("portal-session-updated", syncSession);
    };
  }, []);

  return session;
}
