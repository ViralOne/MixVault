import { Show } from "solid-js";
import { hideToast, toast } from "../state/toast";

export default function Toast() {
  return (
    <div class="toast" classList={{ show: !!toast() }} role="status" aria-live="polite">
      <Show when={toast()}>
        {(t) => (
          <>
            {t().msg}
            <Show when={t().action}>
              {(a) => (
                <button
                  type="button"
                  onClick={() => {
                    a().onClick();
                    hideToast();
                  }}
                >
                  {a().label}
                </button>
              )}
            </Show>
          </>
        )}
      </Show>
    </div>
  );
}
