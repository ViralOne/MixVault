/** The recipe currently open in the detail view. */
import { createSignal } from "solid-js";
import { api } from "../lib/api";
import { slugify } from "../lib/format";
import type { Recipe, RecipeSlim } from "../lib/types";
import { pushHash, setView } from "./router";
import { showToast } from "./toast";

export const [recipe, setRecipe] = createSignal<Recipe | null>(null);
export const [similar, setSimilar] = createSignal<RecipeSlim[]>([]);
export const [tags, setTags] = createSignal<string[]>([]);
export const [scale, setScale] = createSignal(1);
export const [editing, setEditing] = createSignal(false);

/** Loads a recipe and switches to the detail view. */
export async function openRecipe(id: string, opts: { skipHash?: boolean } = {}) {
  const r = await api.recipe(id);
  if (r.error || !r.id) return;
  setRecipe(r);
  setScale(1);
  setEditing(false);
  setSimilar([]);
  setTags([]);
  setView("detail");
  if (!opts.skipHash) pushHash(r.lang + "/" + slugify(r.name));
  void api.similar(id).then((d) => setSimilar(d.recipes || []));
  void api.tags(id).then((d) => setTags(d.tags || []));
}

export async function toggleFavorite() {
  const r = recipe();
  if (!r) return;
  const d = await api.toggleFavorite(r.id);
  setRecipe({ ...r, is_favorite: d.favorited });
}

export async function saveNote(note: string) {
  const r = recipe();
  if (!r) return;
  await api.saveNote(r.id, note);
}

export async function addTag(name: string) {
  const r = recipe();
  const t = name.trim();
  if (!r || !t || tags().includes(t)) return;
  const next = [...tags(), t];
  setTags(next);
  await api.saveTags(r.id, next);
}

export async function removeTag(name: string) {
  const r = recipe();
  if (!r) return;
  const next = tags().filter((t) => t !== name);
  setTags(next);
  await api.saveTags(r.id, next);
}

export async function deleteRecipe(): Promise<boolean> {
  const r = recipe();
  if (!r) return false;
  if (!confirm(`Delete "${r.name}"? This cannot be undone.`)) return false;
  const d = await api.deleteRecipe(r.id);
  if (!d.ok) {
    // e.g. a shared library recipe, which no single vault may remove
    showToast(d.error || "Could not delete this recipe");
    return false;
  }
  showToast("Recipe deleted");
  return true;
}

export function shareRecipe() {
  const r = recipe();
  if (!r) return;
  const url = location.origin + "/api/share/" + r.id;
  if (navigator.share) {
    void navigator.share({ title: r.name, url }).catch(() => {});
  } else {
    void navigator.clipboard.writeText(url);
    showToast("Share link copied!");
  }
}
