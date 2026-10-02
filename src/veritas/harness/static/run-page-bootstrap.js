(() => {
  const nativeFetch = window.fetch.bind(window);
  const RUN_BOOT_LIMIT = 50;

  window.fetch = async (input, init) => {
    const method = String(
      init?.method || (input instanceof Request ? input.method : "GET")
    ).toUpperCase();
    const rawUrl = typeof input === "string" || input instanceof URL ? String(input) : input.url;
    const url = new URL(rawUrl, window.location.href);

    if (
      method === "GET"
      && url.origin === window.location.origin
      && url.pathname === "/api/v1/runs"
      && !url.search
    ) {
      const pageUrl = new URL("/api/v1/run-pages", window.location.origin);
      pageUrl.searchParams.set("limit", String(RUN_BOOT_LIMIT));
      const response = await nativeFetch(pageUrl.href, init);
      if (!response.ok) return response;
      const payload = await response.json();
      // The body is rewritten from a page envelope to an array, so entity headers must be rebuilt.
      const headers = new Headers({
        "Cache-Control": "no-store",
        "Content-Type": "application/json",
        "X-Veritas-Run-Page": "1",
      });
      return new Response(JSON.stringify(Array.isArray(payload.items) ? payload.items : []), {
        status: response.status,
        statusText: response.statusText,
        headers,
      });
    }

    return nativeFetch(input, init);
  };
})();
