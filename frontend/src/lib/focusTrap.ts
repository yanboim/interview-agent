// 对话框焦点陷阱：Tab 在容器内循环、Escape 关闭，保证键盘可访问性。
const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function handleDialogKeydown(
  event: KeyboardEvent,
  container: HTMLElement | null,
  onEscape?: () => void,
) {
  if (event.key === "Escape" && onEscape) {
    event.preventDefault();
    onEscape();
    return;
  }
  if (event.key !== "Tab" || !container) return;
  const focusable = Array.from(
    container.querySelectorAll<HTMLElement>(FOCUSABLE),
  ).filter((element) => !element.hidden);
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}
