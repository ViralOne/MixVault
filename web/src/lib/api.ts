/** Thin typed wrappers around the Python API. One place for every endpoint. */
import type {
  AiSearchResponse, ChatMessage, CreatorRecipe, HistoryEntry, Meta, Recipe,
  RecipeSlim, SearchResponse, ShopItem, Substitution,
} from "./types";

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path);
  return (await r.json()) as T;
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, {
    method: "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return (await r.json()) as T;
}

export const api = {
  meta: () => get<Meta>("/api/meta"),
  search: (params: URLSearchParams) => get<SearchResponse>("/api/recipes?" + params),
  random: () => get<SearchResponse>("/api/recipes?random=1"),
  recipe: (id: string) => get<Recipe & { error?: string }>("/api/recipe/" + encodeURIComponent(id)),
  similar: (id: string, limit = 8) =>
    get<{ recipes: RecipeSlim[] }>(`/api/similar/${encodeURIComponent(id)}?limit=${limit}`),
  nutritionSearch: (params: URLSearchParams) => get<SearchResponse>("/api/nutrition?" + params),
  history: () => get<{ history: HistoryEntry[] }>("/api/history"),
  markCooked: (id: string) => post<{ ok: boolean }>("/api/cooked/" + encodeURIComponent(id)),
  toggleFavorite: (id: string) => post<{ favorited: boolean }>("/api/favorite/" + encodeURIComponent(id)),

  cookingStateGet: () => get<{ recipe_id: string | null; step: number }>("/api/cooking-state"),
  cookingStateSave: (recipe_id: string | null, step = 0) =>
    post<{ ok: boolean }>("/api/cooking-state", { recipe_id, step }),

  note: (id: string) => get<{ note: string }>("/api/note/" + encodeURIComponent(id)),
  saveNote: (id: string, note: string) => post<{ ok: boolean }>("/api/note/" + encodeURIComponent(id), { note }),
  tags: (id: string) => get<{ tags: string[] }>("/api/tags/" + encodeURIComponent(id)),
  tagsList: () => get<{ tags: { tag: string; count: number }[] }>("/api/tags"),
  saveTags: (id: string, tags: string[]) => post<{ ok: boolean }>("/api/tags/" + encodeURIComponent(id), { tags }),

  shopping: () => get<{ items: ShopItem[] }>("/api/shopping"),
  shopAdd: (items: string[], recipe_id = "", recipe_name = "") =>
    post<{ ok: boolean }>("/api/shopping/add", { items, recipe_id, recipe_name }),
  shopToggle: (id: number) => post<{ ok: boolean }>("/api/shopping/toggle", { id }),
  shopDelete: (id: number) => post<{ ok: boolean }>("/api/shopping/delete", { id }),
  shopClear: (mode: "checked" | "all") =>
    post<{ items: ShopItem[]; deleted: ShopItem[] }>("/api/shopping/clear", { mode }),
  shopRestore: (items: ShopItem[]) => post<{ ok: boolean }>("/api/shopping/restore", { items }),

  aiSearch: (prompt: string) => post<AiSearchResponse>("/api/ai", { prompt }),
  aiChat: (messages: ChatMessage[]) =>
    post<{ reply: string; recipe?: CreatorRecipe; error?: string }>("/api/ai/create", { messages }),
  aiImages: (query: string) => post<{ images: { url: string; title?: string }[] }>("/api/ai/images", { query }),
  substitutions: (ingredient: string, context: string) =>
    post<{ substitutions: Substitution[] }>("/api/substitutions", { ingredient, context }),

  translate: (id: string, lang: string) =>
    post<{ id: string; error?: string }>("/api/translate/" + encodeURIComponent(id), { lang }),
  importCookidoo: (url: string) =>
    post<{ id: string; name: string; steps_generated: number; exists?: boolean; error?: string }>(
      "/api/import/cookidoo", { url }),
  importRecipe: (recipe: CreatorRecipe) =>
    post<{ ok: boolean; id: string; error?: string }>("/api/recipe/import", recipe),
  editRecipe: (id: string, data: Partial<Recipe>) =>
    post<{ ok: boolean }>("/api/recipe/edit/" + encodeURIComponent(id), data),
  deleteRecipe: (id: string) => post<{ ok: boolean }>("/api/recipe/delete/" + encodeURIComponent(id)),
  restoreBackup: (data: unknown) => post<{ ok: boolean }>("/api/import/restore", data),

  poll: () => get<{ shopping_count: number; favorites_count: number }>("/api/poll"),
};
