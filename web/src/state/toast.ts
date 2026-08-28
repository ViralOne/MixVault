import { createSignal } from "solid-js";

export interface ToastAction {
  label: string;
  onClick: () => void;
}

export interface ToastState {
  msg: string;
  action?: ToastAction;
}

const [toast, setToast] = createSignal<ToastState | null>(null);
let timer: ReturnType<typeof setTimeout> | undefined;

export function showToast(msg: string, action?: ToastAction) {
  setToast({ msg, action });
  clearTimeout(timer);
  timer = setTimeout(() => setToast(null), 4000);
}

export function hideToast() {
  clearTimeout(timer);
  setToast(null);
}

export { toast };
