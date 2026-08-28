/**
 * Dev-only gallery of every hands-on scene (`#/dev/scenes` with `npm run dev`).
 * Tree-shaken out of production builds via `import.meta.env.DEV`.
 */
import { For } from "solid-js";
import { ACTION_LABELS, type ManualAction, type StepMeta } from "../../lib/steps";
import ManualScene from "./ManualScene";

const ACTIONS: ManualAction[] = [
  "chop", "wash", "oven", "chill", "drain", "whisk", "knead",
  "stove", "fill", "tray", "rest", "serve", "store", "prep",
];

const meta = (action: ManualAction): StepMeta => ({
  mode: "manual", action, actions: [action],
  temp: action === "oven" ? 180 : 0, speed: 0, secs: 0, weight: 0,
  isPour: false, isChop: false, isCook: false,
});

export default function SceneGallery() {
  return (
    <div style={{ background: "#111", color: "#fff", "min-height": "100dvh", padding: "24px" }}>
      <h1 style={{ "font-size": "16px", "margin-bottom": "16px" }}>Hands-on scenes</h1>
      <div style={{ display: "grid", "grid-template-columns": "repeat(auto-fill,minmax(240px,1fr))", gap: "20px" }}>
        <For each={ACTIONS}>
          {(a) => (
            <div style={{ border: "1px solid #333", "border-radius": "12px", padding: "12px" }}>
              <div style={{ "font-size": "11px", color: "#ffb74d", "text-transform": "uppercase", "letter-spacing": ".08em" }}>
                {a} — {ACTION_LABELS[a]}
              </div>
              <ManualScene meta={meta(a)} />
            </div>
          )}
        </For>
      </div>
    </div>
  );
}
