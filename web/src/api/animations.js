// Client for the animation API.
//
// The only module that knows URLs and wire formats. Views work with the values
// it returns, so a change to the API surface lands in one file.

const BASE = "/api/v1/animations";

// The API answers 202 and expects polling. That holds whether the backend
// renders inline or hands off to a worker, so nothing here has to change when
// it does.
const POLL_INTERVAL_MS = 1200;
const POLL_TIMEOUT_MS = 5 * 60 * 1000;

const TERMINAL = new Set(["succeeded", "failed"]);

export function isTerminal(job) {
  return TERMINAL.has(job?.status);
}

export class ApiError extends Error {
  constructor(message, code, requestId) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.requestId = requestId;
  }
}

async function request(path, options = {}) {
  const { base = BASE, ...init } = options;
  let response;
  try {
    response = await fetch(`${base}${path}`, {
      headers: { Accept: "application/json", ...init.headers },
      ...init,
    });
  } catch (cause) {
    throw new ApiError("Could not reach the server.", "network_error");
  }

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(
      body?.message ?? `${response.status} ${response.statusText}`,
      body?.code ?? "http_error",
      response.headers.get("X-Request-ID"),
    );
  }
  return body;
}

export function createAnimation(prompt, quality) {
  return request("", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, quality }),
  });
}

export function getAnimation(id) {
  return request(`/${encodeURIComponent(id)}`);
}

export function listAnimations({ limit = 20, offset = 0 } = {}) {
  return request(`?limit=${limit}&offset=${offset}`);
}

export function getAnimationSource(id) {
  return request(`/${encodeURIComponent(id)}/source`);
}

/** What this deployment supports; a small instance cannot afford every quality. */
export function getCapabilities() {
  return request("/capabilities", { base: "/api/v1" });
}

/** Poll until the job reaches a terminal state, reporting each change. */
export async function waitForJob(id, onUpdate, { signal } = {}) {
  const deadline = Date.now() + POLL_TIMEOUT_MS;

  for (;;) {
    if (signal?.aborted) return null;
    const job = await getAnimation(id);
    onUpdate?.(job);
    if (isTerminal(job)) return job;
    if (Date.now() > deadline) {
      throw new ApiError("Timed out waiting for the render.", "poll_timeout");
    }
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
  }
}
