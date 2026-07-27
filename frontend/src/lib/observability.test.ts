// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";

const trackEvent = vi.fn();

vi.mock("@/api/analytics", () => ({ trackEvent }));

describe("client observability", () => {
  beforeEach(() => {
    trackEvent.mockReset();
  });

  it("does not submit protected events until authentication is available", async () => {
    const { startClientObservability } = await import("@/lib/observability");
    let authenticated = false;

    startClientObservability(
      () => "user-1",
      () => authenticated,
    );
    window.dispatchEvent(new ErrorEvent("error", { message: "anonymous" }));
    expect(trackEvent).not.toHaveBeenCalled();

    authenticated = true;
    window.dispatchEvent(new ErrorEvent("error", { message: "authenticated" }));
    expect(trackEvent).toHaveBeenCalledWith(
      "user-1",
      "client.error",
      expect.objectContaining({ message: "authenticated" }),
    );
  });
});
