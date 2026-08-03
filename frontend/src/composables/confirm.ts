// 全局确认对话框组合式 API：以 Promise 形式等待用户「确认/取消」。
import { reactive } from "vue";

export interface ConfirmOptions {
  title: string;
  message?: string;
  /** 高亮显示的危险目标(如要删除的文件名)。 */
  detail?: string;
  confirmText?: string;
  cancelText?: string;
  danger?: boolean;
}

interface ConfirmState {
  open: boolean;
  options: ConfirmOptions;
  resolve: ((value: boolean) => void) | null;
}

const state = reactive<ConfirmState>({
  open: false,
  options: { title: "" },
  resolve: null,
});

/** 弹出确认对话框,返回用户是否确认。替代原生 window.confirm。 */
export function confirm(options: ConfirmOptions): Promise<boolean> {
  // 若已有对话框打开,先关闭旧的(拒绝)
  if (state.open && state.resolve) state.resolve(false);
  return new Promise((resolve) => {
    state.options = options;
    state.resolve = resolve;
    state.open = true;
  });
}

export function useConfirm() {
  return state;
}

export function answerConfirm(confirmed: boolean) {
  state.open = false;
  state.resolve?.(confirmed);
  state.resolve = null;
}
