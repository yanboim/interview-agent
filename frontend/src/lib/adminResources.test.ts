import { describe, expect, it } from "vitest";
import {
  resourceExposureLabel,
  resourceStatusLabel,
} from "@/lib/adminResources";

describe("admin resource labels", () => {
  it("keeps unknown health distinct from configured and healthy states", () => {
    expect(resourceStatusLabel("healthy")).toBe("正常");
    expect(resourceStatusLabel("configured")).toBe("已配置");
    expect(resourceStatusLabel("unknown")).toBe("未探测");
  });

  it("makes public and private exposure explicit", () => {
    expect(resourceExposureLabel("public_gateway")).toBe("公网网关");
    expect(resourceExposureLabel("private_network")).toBe("内部网络");
  });
});
