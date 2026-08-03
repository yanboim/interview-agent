// 全局轻提示状态：info/success/error 的入队、自动消失与手动关闭。
import { defineStore } from "pinia";

export type ToastKind = "info" | "success" | "error";

export interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

let nextId = 1;

export const useToastStore = defineStore("toast", {
  state: () => ({
    toasts: [] as Toast[],
  }),
  actions: {
    show(message: string, kind: ToastKind = "info", ttl = 4500) {
      const id = nextId++;
      this.toasts.push({ id, kind, message });
      if (ttl > 0) {
        window.setTimeout(() => this.dismiss(id), ttl);
      }
      return id;
    },
    dismiss(id: number) {
      const index = this.toasts.findIndex((t) => t.id === id);
      if (index >= 0) this.toasts.splice(index, 1);
    },
  },
});
