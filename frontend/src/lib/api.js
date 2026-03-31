const DEFAULT_API_BASE_URL = "https://code-review-env.onrender.com";

function trimTrailingSlash(value) {
  return value.replace(/\/+$/, "");
}

function ensureLeadingSlash(value) {
  return value.startsWith("/") ? value : `/${value}`;
}

export const API_BASE_URL = trimTrailingSlash(
  import.meta.env.PUBLIC_API_BASE_URL || DEFAULT_API_BASE_URL,
);

export function buildApiUrl(path) {
  return `${API_BASE_URL}${ensureLeadingSlash(path)}`;
}

export async function fetchJson(path, options = {}) {
  const response = await fetch(buildApiUrl(path), {
    headers: { "Content-Type": "application/json", ...(options.headers ?? {}) },
    ...options,
  });

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "Request failed.");
  }

  return data;
}
