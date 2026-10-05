(() => {
  const RUN_BOOT_LIMIT = 50;
  const originalFetch = window.fetch.bind(window);

  function runListRequest(input, init) {
    let request;
    try {
      request = input instanceof Request ? new Request(input, init) : new Request(input, init);
    } catch {
      return null;
    }
    const url = new URL(request.url, window.location.href);
    if (
      request.method !== "GET"
      || url.origin !== window.location.origin
      || url.pathname !== "/api/v1/runs"
      || url.search
    ) return null;
    return request;
  }

  function publishPage(payload) {
    const items = Array.isArray(payload?.items) ? payload.items : [];
    const snapshot = {
      items,
      next_cursor: payload?.next_cursor || null,
      has_more: Boolean(payload?.has_more),
    };
    window.__veritasRunPageFeed = snapshot;
    window.dispatchEvent(new CustomEvent("veritas:run-page-reset", { detail: snapshot }));
    return snapshot;
  }

  async function boundedRunFetch(request) {
    const pageUrl = new URL("/api/v1/run-pages", window.location.origin);
    pageUrl.searchParams.set("limit", String(RUN_BOOT_LIMIT));
    const response = await originalFetch(pageUrl.toString(), {
      method: "GET",
      headers: request.headers,
      credentials: request.credentials,
      mode: request.mode === "navigate" ? "same-origin" : request.mode,
      cache: "no-store",
      redirect: request.redirect,
      referrer: request.referrer,
      referrerPolicy: request.referrerPolicy,
      signal: request.signal,
    });
    if (!response.ok) return response;
    const snapshot = publishPage(await response.json());

    // The body representation changes from a page envelope to the legacy array,
    // so entity headers must be rebuilt rather than copied from the upstream body.
    return new Response(JSON.stringify(snapshot.items), {
      status: response.status,
      statusText: response.statusText,
      headers: {
        "Cache-Control": "no-store",
        "Content-Type": "application/json",
        "X-Veritas-Run-Page": "1",
      },
    });
  }

  window.fetch = function veritasRunPagedFetch(input, init) {
    const request = runListRequest(input, init);
    if (!request) return originalFetch(input, init);
    return boundedRunFetch(request);
  };
})();
