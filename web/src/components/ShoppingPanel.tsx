import { For, Show, createMemo } from "solid-js";
import { mergeShopItems } from "../lib/format";
import type { ShopItem } from "../lib/types";
import {
  addManual, clearAll, clearChecked, deleteItem, items, open, share, toggleItem, togglePanel,
  uncheckedCount,
} from "../state/shopping";
import { IconCart, IconChevronLeft, IconDownload, IconShare } from "./Icons";

/** Group by source recipe, then merge duplicate lines inside each group. */
function grouped(list: ShopItem[]) {
  const groups = new Map<string, ShopItem[]>();
  for (const i of list) {
    const key = i.recipe_id || "_manual";
    const bucket = groups.get(key);
    bucket ? bucket.push(i) : groups.set(key, [i]);
  }
  return [...groups.entries()].map(([key, list]) => ({
    key,
    label: key === "_manual" ? "" : list[0].recipe_name || key,
    merged: mergeShopItems(list),
  }));
}

export default function ShoppingPanel() {
  const groups = createMemo(() => grouped(items()));
  let manualInput!: HTMLInputElement;

  const submitManual = () => {
    void addManual(manualInput.value);
    manualInput.value = "";
  };

  return (
    <>
      <div class="panel-overlay" classList={{ open: open() }} onClick={togglePanel} aria-hidden="true" />
      <div class="side-panel shop" classList={{ open: open() }} role="dialog" aria-label="Shopping list" aria-modal="true">
        <div class="panel-header">
          <button type="button" class="btn-back" aria-label="Close" onClick={togglePanel}>
            <IconChevronLeft />
          </button>
          <h2>Shopping List</h2>
          <Show when={items().length > 0}>
            <span class="item-count">{uncheckedCount()} item{uncheckedCount() === 1 ? "" : "s"}</span>
          </Show>
        </div>

        <Show when={items().length > 0}>
          <div class="shop-actions">
            <button type="button" onClick={() => void clearChecked()}>Clear checked</button>
            <button type="button" class="clear-all" onClick={() => void clearAll()}>Clear all</button>
            <button type="button" onClick={() => window.open("/api/export?format=csv")}>
              <IconDownload size={14} /> Export
            </button>
            <button type="button" title="Share list" onClick={share}>
              <IconShare size={14} /> Share
            </button>
          </div>
        </Show>

        <div class="shop-add-row">
          <input
            type="text" ref={manualInput} placeholder="Add custom item…"
            onKeyDown={(e) => e.key === "Enter" && submitManual()}
            aria-label="Add custom item"
          />
          <button type="button" onClick={submitManual}>Add</button>
        </div>

        <div class="shop-items">
          <Show
            when={items().length > 0}
            fallback={
              <div class="shop-empty">
                <IconCart size={48} />
                <p>Your shopping list is empty</p>
                <p class="hint">Add ingredients from any recipe</p>
              </div>
            }
          >
            <For each={groups()}>
              {(g) => (
                <div class="shop-group">
                  <Show when={g.label}>
                    <div class="shop-group-label">{g.label}</div>
                  </Show>
                  <For each={g.merged}>
                    {(i) => (
                      <div class="shop-item" classList={{ checked: i.checked }}>
                        <span class="si-check" onClick={() => void toggleItem(i.id)}>✓</span>
                        <span class="si-text" onClick={() => void toggleItem(i.id)}>
                          {i.display}
                          <Show when={i.ids.length > 1}>
                            {" "}<small>(×{i.ids.length})</small>
                          </Show>
                        </span>
                        <button
                          type="button" class="si-del" title="Remove" aria-label={`Remove ${i.display}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            void deleteItem(i.id);
                          }}
                        >
                          ×
                        </button>
                      </div>
                    )}
                  </For>
                </div>
              )}
            </For>
          </Show>
        </div>
      </div>
    </>
  );
}
