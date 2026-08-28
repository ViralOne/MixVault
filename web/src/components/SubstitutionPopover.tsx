import { For, Show, createSignal, onCleanup } from "solid-js";
import { api } from "../lib/api";
import type { Substitution } from "../lib/types";

interface PopState {
  ingredient: string;
  x: number;
  y: number;
  items: Substitution[] | null;
}

const [pop, setPop] = createSignal<PopState | null>(null);

export async function showSubstitutions(ingredient: string, e: MouseEvent, context: string) {
  setPop({ ingredient, x: Math.min(e.clientX - 100, innerWidth - 320), y: e.clientY + 10, items: null });
  try {
    const d = await api.substitutions(ingredient, context);
    setPop((p) => (p ? { ...p, items: d.substitutions || [] } : p));
  } catch {
    setPop((p) => (p ? { ...p, items: [] } : p));
  }
}

export default function SubstitutionPopover() {
  const dismiss = (e: MouseEvent) => {
    if (!(e.target as HTMLElement)?.closest(".sub-popover")) setPop(null);
  };
  document.addEventListener("click", dismiss);
  onCleanup(() => document.removeEventListener("click", dismiss));

  return (
    <Show when={pop()}>
      {(p) => (
        <div class="sub-popover" style={{ top: p().y + "px", left: p().x + "px" }}>
          <Show when={p().items} fallback={<div style={{ "text-align": "center", padding: "8px" }}>⏳ Finding alternatives…</div>}>
            <Show when={p().items!.length > 0} fallback={<div>No substitutions found.</div>}>
              <div class="sub-head">Substitutes for {p().ingredient}</div>
              <For each={p().items!}>
                {(s) => (
                  <div class="sub-item">
                    <span class="sub-name">{s.sub}</span> <span class="sub-ratio">{s.ratio}</span>
                    <div class="sub-note">{s.note}</div>
                  </div>
                )}
              </For>
            </Show>
          </Show>
        </div>
      )}
    </Show>
  );
}
