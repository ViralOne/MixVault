/** Shopping list panel state. */
import { createSignal } from "solid-js";
import { api } from "../lib/api";
import { scaleText } from "../lib/format";
import type { Recipe, ShopItem } from "../lib/types";
import { showToast } from "./toast";

export const [items, setItems] = createSignal<ShopItem[]>([]);
export const [open, setOpen] = createSignal(false);

let lastDeleted: ShopItem[] | null = null;

export const uncheckedCount = () => items().filter((i) => !i.checked).length;

export async function load() {
  const d = await api.shopping();
  setItems(d.items || []);
}

export function togglePanel() {
  const next = !open();
  setOpen(next);
  if (next) void load();
}

export async function toggleItem(id: number) {
  await api.shopToggle(id);
  await load();
}

export async function deleteItem(id: number) {
  await api.shopDelete(id);
  await load();
}

export async function addManual(text: string) {
  const v = text.trim();
  if (!v) return;
  await api.shopAdd([v]);
  await load();
  showToast("Item added");
}

export async function addRecipe(r: Recipe, scale: number) {
  if (items().some((i) => i.recipe_id === r.id)) {
    showToast("Already in shopping list");
    return;
  }
  const scaled = r.ingredients.map((ig) => scaleText(ig, scale));
  await api.shopAdd(scaled, r.id, r.name);
  await load();
  showToast(`${scaled.length} ingredient${scaled.length === 1 ? "" : "s"} added`);
}

async function clear(mode: "checked" | "all") {
  const d = await api.shopClear(mode);
  setItems(d.items || []);
  if (d.deleted?.length) {
    lastDeleted = d.deleted;
    showToast(`${d.deleted.length} items cleared`, { label: "Undo", onClick: () => void undo() });
  }
}

export const clearChecked = () => clear("checked");

export async function clearAll() {
  if (!confirm("Clear entire shopping list?")) return;
  await clear("all");
}

export async function undo() {
  if (!lastDeleted) return;
  await api.shopRestore(lastDeleted);
  lastDeleted = null;
  await load();
  showToast("Restored!");
}

export function share() {
  const unchecked = items().filter((i) => !i.checked);
  if (!unchecked.length) {
    showToast("Shopping list is empty");
    return;
  }
  const text = "Shopping List:\n" + unchecked.map((i) => "- " + i.item).join("\n");
  if (navigator.share) {
    void navigator.share({ title: "Shopping List", text }).catch(() => {});
  } else {
    void navigator.clipboard.writeText(text).then(() => showToast("List copied to clipboard"));
  }
}
