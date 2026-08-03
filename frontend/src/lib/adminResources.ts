// 管理端资源状态/暴露面的中文标签映射。
import type {
  AdminResourceExposure,
  AdminResourceStatus,
} from "@/types";

const statusLabels: Record<AdminResourceStatus, string> = {
  healthy: "正常",
  unavailable: "异常",
  configured: "已配置",
  disabled: "未启用",
  unknown: "未探测",
};

const exposureLabels: Record<AdminResourceExposure, string> = {
  public_gateway: "公网网关",
  loopback: "仅本机",
  private_network: "内部网络",
  external_provider: "外部服务",
};

export function resourceStatusLabel(status: AdminResourceStatus): string {
  return statusLabels[status];
}

export function resourceExposureLabel(
  exposure: AdminResourceExposure,
): string {
  return exposureLabels[exposure];
}
