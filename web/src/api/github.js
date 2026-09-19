// Client for the GitHub delegation API.
//
// Nothing here handles a token. The session lives in an HttpOnly cookie that
// the browser attaches by itself, which is why every call opts into credentials
// and none of them set an Authorization header — this module could not read the
// session even if it wanted to.

const BASE = "/api/v1";

// A plain navigation target, not something to fetch: GitHub has to render its
// own consent page, and the callback must arrive as a top-level request for the
// session cookie to be set on it.
export const LOGIN_URL = `${BASE}/auth/github/login`;

// Outcomes the callback hands back as ?connect=... Phrased for the person
// reading them, since some are ordinary (they pressed Cancel) rather than bugs.
export const CONNECT_MESSAGES = {
  denied: "You declined the request, so nothing was shared.",
  invalid_state: "That sign-in attempt expired or did not match. Please try again.",
  failed: "GitHub could not complete the sign-in. Please try again.",
  unavailable: "GitHub is unreachable right now. Try again in a moment.",
};

export class GitHubError extends Error {
  constructor(message, code) {
    super(message);
    this.name = "GitHubError";
    this.code = code;
  }
}

async function request(path, { method = "GET" } = {}) {
  let response;
  try {
    response = await fetch(`${BASE}${path}`, {
      method,
      // Without this the browser omits the session cookie and every call is
      // anonymous, including the ones that look like they should work.
      credentials: "include",
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new GitHubError("Could not reach the server.", "network_error");
  }

  if (response.status === 204) return null;

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new GitHubError(
      body?.message ?? `${response.status} ${response.statusText}`,
      body?.code ?? "http_error",
    );
  }
  return body;
}

/** Whether the feature exists here, and whether this browser has connected. */
export function getConnection() {
  return request("/auth/github/me");
}

export function listRepositories() {
  return request("/github/repos");
}

export function disconnect() {
  return request("/auth/github/logout", { method: "POST" });
}
