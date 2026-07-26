import { trackEvent } from "@/api/analytics";

let started = false;

export function startClientObservability(getUserId: () => string) {
  if (started) return;
  started = true;

  window.addEventListener("error", (event) => {
    trackEvent(getUserId(), "client.error", {
      message: event.message,
      source: event.filename,
      line: event.lineno,
      column: event.colno,
    });
  });
  window.addEventListener("unhandledrejection", (event) => {
    trackEvent(getUserId(), "client.unhandled_rejection", {
      reason: event.reason instanceof Error ? event.reason.message : String(event.reason),
    });
  });

  window.addEventListener(
    "load",
    () => {
      window.setTimeout(() => {
        const navigation = performance.getEntriesByType(
          "navigation",
        )[0] as PerformanceNavigationTiming | undefined;
        if (!navigation) return;
        trackEvent(getUserId(), "client.web_vital", {
          metric: "page_load",
          value: Math.round(navigation.loadEventEnd - navigation.startTime),
          route: location.pathname,
        });
      }, 0);
    },
    { once: true },
  );

  if ("PerformanceObserver" in window) {
    try {
      const observer = new PerformanceObserver((list) => {
        const entries = list.getEntries();
        const entry = entries[entries.length - 1];
        if (!entry) return;
        trackEvent(getUserId(), "client.web_vital", {
          metric: "lcp",
          value: Math.round(entry.startTime),
          route: location.pathname,
        });
      });
      observer.observe({ type: "largest-contentful-paint", buffered: true });
    } catch {
      // 老浏览器不支持该 entry type 时跳过。
    }
  }
}
