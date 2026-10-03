(() => {
  const AUDIT_BOOT_LIMIT = 50;
  const originalFetch = window.fetch.bind(window);

  function auditListRequest(input, init) {
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
      || url.pathname !== "/api/v1/audits"
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
      status_counts: payload?.status_counts && typeof payload.status_counts === "object"
        ? payload.status_counts
        : {},
    };
    window.__veritasAuditPageFeed = snapshot;
    window.dispatchEvent(new CustomEvent("veritas:audit-page-reset", { detail: snapshot }));
    return snapshot;
  }

  async function boundedAuditFetch(request) {
    const pageUrl = new URL("/api/v1/audit-pages", window.location.origin);
    pageUrl.searchParams.set("limit", String(AUDIT_BOOT_LIMIT));
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
        "X-Veritas-Audit-Page": "1",
      },
    });
  }

  window.fetch = function veritasAuditPagedFetch(input, init) {
    const request = auditListRequest(input, init);
    if (!request) return originalFetch(input, init);
    return boundedAuditFetch(request);
  };
})();
