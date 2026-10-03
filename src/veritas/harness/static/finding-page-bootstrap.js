(() => {
  const FINDING_BOOT_LIMIT = 50;
  const originalFetch = window.fetch.bind(window);

  function findingListRequest(input, init) {
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
      || url.pathname !== "/api/v1/findings"
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
      total: Number(payload?.total) || items.length,
      severity_counts: payload?.severity_counts && typeof payload.severity_counts === "object"
        ? payload.severity_counts
        : {},
    };
    window.__veritasFindingPageFeed = snapshot;
    window.dispatchEvent(new CustomEvent("veritas:finding-page-reset", { detail: snapshot }));
    return snapshot;
  }

  async function boundedFindingFetch(request) {
    const pageUrl = new URL("/api/v1/finding-pages", window.location.origin);
    pageUrl.searchParams.set("limit", String(FINDING_BOOT_LIMIT));
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
        "X-Veritas-Finding-Page": "1",
      },
    });
  }

  window.fetch = function veritasFindingPagedFetch(input, init) {
    const request = findingListRequest(input, init);
    if (!request) return originalFetch(input, init);
    return boundedFindingFetch(request);
  };
})();
