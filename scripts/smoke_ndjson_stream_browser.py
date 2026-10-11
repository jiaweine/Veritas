"""Verify the browser transport boundary for the three live NDJSON interfaces."""

from __future__ import annotations

import argparse

from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser(description="Exercise split, EOF, and malformed NDJSON frames.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    args = parser.parse_args()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(args.base_url.rstrip("/") + "/#overview", wait_until="domcontentloaded")
        result = page.evaluate(
            """async () => {
              const { consumeNdjson } = await import("/static/ndjson-stream.js");
              const encoded = new TextEncoder().encode(
                '{"kind":"audit","detail":"审查"}\\r\\n\\n{"kind":"finish","detail":"✓"}'
              );
              const collected = [];
              const byteChunks = Array.from(encoded, (byte) => Uint8Array.of(byte));
              const response = new Response(new ReadableStream({
                start(controller) {
                  for (const part of byteChunks) controller.enqueue(part);
                  controller.close();
                }
              }));
              await consumeNdjson(response, (event) => collected.push(event));
              if (collected.length !== 2 ||
                  collected[0].detail !== "审查" ||
                  collected[1].kind !== "finish") {
                throw new Error("Split UTF-8 frame or final unterminated line was lost.");
              }

              let invalid = "";
              try {
                await consumeNdjson(new Response("{invalid}"), () => {});
              } catch (error) { invalid = String(error.message); }
              if (!invalid.includes("Malformed server event at line 1")) {
                throw new Error("Malformed server event was not reported.");
              }

              let noBody = "";
              try {
                await consumeNdjson({ body: null }, () => {});
              } catch (error) { noBody = String(error.message); }
              if (!noBody.includes("Live event streaming is unavailable")) {
                throw new Error("Missing streaming capability was not reported.");
              }

              let callbackError = "";
              try {
                await consumeNdjson(new Response('{"kind":"audit"}\\n'), () => {
                  throw new Error("Consumer failed");
                });
              } catch (error) { callbackError = String(error.message); }
              if (callbackError !== "Consumer failed") {
                throw new Error("Callback failure was not propagated.");
              }
              return { events: collected.length, unicode: true, eof: true,
                       malformed: true, stream_capability: true, callback_failure: true };
            }"""
        )
        browser.close()
        assert result == {
            "events": 2,
            "unicode": True,
            "eof": True,
            "malformed": True,
            "stream_capability": True,
            "callback_failure": True,
        }, result
        print("NDJSON browser protocol checks: " + str(result))


if __name__ == "__main__":
    main()
