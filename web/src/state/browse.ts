/** Browse view: search text, filters, result list and paging. */
import { createSignal } from "solid-js";
import { api } from "../lib/api";
import type { RecipeSlim } from "../lib/types";

const LIMIT = 60;

export const [query, setQuery] = createSignal("");
export const [country, setCountry] = createSignal("");
export const [lang, setLang] = createSignal("");
export const [tag, setTag] = createSignal("");
export const [favOn, setFavOn] = createSignal(false);
export const [historyOn, setHistoryOn] = createSignal(false);
export const [nutOpen, setNutOpen] = createSignal(false);
export const [aiMode, setAiMode] = createSignal(false);

export const [recipes, setRecipes] = createSignal<RecipeSlim[]>([]);
export const [total, setTotal] = createSignal(0);
export const [offset, setOffset] = createSignal(0);
export const [loading, setLoading] = createSignal(false);
export const [resultInfo, setResultInfo] = createSignal<{ lead: string; tail?: string }>({ lead: "" });

export const [nutrition, setNutrition] = createSignal({ cal: "", prot: "", carbs: "", fat: "" });

export const hasFilters = () =>
  !!country() || !!lang() || !!tag() || favOn() || nutOpen() || historyOn();

export const canLoadMore = () => offset() < total();

function buildParams(off: number) {
  const p = new URLSearchParams();
  const q = query().trim();
  if (q) p.set("q", q);
  if (country()) p.set("country", country());
  if (lang()) p.set("lang", lang());
  if (tag()) p.set("tag", tag());
  if (favOn()) p.set("favorites", "1");
  p.set("limit", String(LIMIT));
  p.set("offset", String(off));
  return p;
}

export async function doSearch(reset: boolean) {
  if (loading()) return;
  setLoading(true);
  try {
    const off = reset ? 0 : offset();
    const data = await api.search(buildParams(off));
    setTotal(data.total);
    setOffset(data.offset + data.recipes.length);
    setResultInfo({ lead: data.total.toLocaleString(), tail: "recipes" });
    setRecipes(reset ? data.recipes : [...recipes(), ...data.recipes]);
  } finally {
    setLoading(false);
  }
}

export async function doAiSearch() {
  const q = query().trim();
  if (!q || loading()) return;
  setLoading(true);
  setRecipes([]);
  setResultInfo({ lead: "✨ AI thinking…" });
  try {
    const d = await api.aiSearch(q);
    if (d.error) {
      setResultInfo({ lead: d.error });
      setRecipes([]);
      return;
    }
    setTotal(d.total);
    setOffset(d.total);
    setResultInfo({
      lead: `✨ ${d.total}`,
      tail: `recipes for ${d.keywords.join(", ")}${d.langs?.length ? " (" + d.langs.join(", ") + ")" : ""}`,
    });
    setRecipes(d.recipes);
  } catch {
    setResultInfo({ lead: "AI search failed" });
    setRecipes([]);
  } finally {
    setLoading(false);
  }
}

export async function toggleHistory() {
  const on = !historyOn();
  setHistoryOn(on);
  if (!on) {
    await doSearch(true);
    return;
  }
  if (loading()) return;
  setLoading(true);
  setRecipes([]);
  try {
    const d = await api.history();
    const list = (d.history || []).map((h) => h.recipe);
    setTotal(list.length);
    setOffset(list.length);
    setResultInfo({ lead: `⏱ ${list.length}`, tail: "cooked recipes" });
    setRecipes(list);
  } finally {
    setLoading(false);
  }
}

export async function openHistory() {
  if (!historyOn()) await toggleHistory();
}

export async function doNutritionSearch() {
  if (loading()) return;
  setLoading(true);
  setRecipes([]);
  try {
    const n = nutrition();
    const p = new URLSearchParams();
    if (n.cal) p.set("max_calories", n.cal);
    if (n.prot) p.set("min_protein", n.prot);
    if (n.carbs) p.set("max_carbs", n.carbs);
    if (n.fat) p.set("max_fat", n.fat);
    if (lang()) p.set("lang", lang());
    p.set("limit", "60");
    const data = await api.nutritionSearch(p);
    setTotal(data.total);
    setOffset(data.total);
    setResultInfo({ lead: `🥗 ${data.total}`, tail: "recipes matching nutrition goals" });
    setRecipes(data.recipes);
  } finally {
    setLoading(false);
  }
}

export async function toggleFavFilter() {
  setFavOn(!favOn());
  if (historyOn()) setHistoryOn(false);
  await doSearch(true);
}

export async function clearFilters() {
  setCountry("");
  setLang("");
  setTag("");
  setFavOn(false);
  setHistoryOn(false);
  setNutOpen(false);
  setNutrition({ cal: "", prot: "", carbs: "", fat: "" });
  await doSearch(true);
}
