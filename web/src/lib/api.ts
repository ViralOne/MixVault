/** Thin typed wrappers around the Python API. One place for every endpoint. */
import type {
  AiSearchResponse, ChatMessage, CreatorRecipe, HistoryEntry, Meta, Recipe,
  RecipeSlim, SearchResponse, Session, ShopItem, Substitution,
} from "./types";

/**
 * A 401 means the access key cookie is gone or was revoked — go back to the door.
 * Guarded so a burst of failing requests cannot turn into a reload loop.
 */
const BOUNCE_KEY = "mv:bounced";

function bounceIfUnauthorized(r: Response) {
  if (r.status !== 401) return;
  const last = Number(sessionStorage.getItem(BOUNCE_KEY) || 0);
  if (Date.now() - last > 5000) {
    sessionStorage.setItem(BOUNCE_KEY, String(Date.now()));
    location.replace("/");
  }
  throw new Error("unauthorized");
}

/**
 * Read the body as JSON, tolerating a response that isn't.
 *
 * A 413, a 502 from a proxy or a crashed handler answers with text or nothing at
 * all; `r.json()` on that throws a parse error that says nothing useful. Callers
 * look at `error`, so put something legible there instead.
 */
async function parse<T>(r: Response): Promise<T> {
  const text = await r.text();
  try {
    return JSON.parse(text) as T;
  } catch {
    const reason = r.ok ? "Unexpected reply from the server" : `${r.status} ${r.statusText}`.trim();
    return { error: reason } as T;
  }
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path);
  bounceIfUnauthorized(r);
  return parse<T>(r);
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, {
    method: "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  bounceIfUnauthorized(r);
  return parse<T>(r);
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
    post<{ ok?: boolean; error?: string }>("/api/recipe/edit/" + encodeURIComponent(id), data),
  deleteRecipe: (id: string) =>
    post<{ ok?: boolean; error?: string }>("/api/recipe/delete/" + encodeURIComponent(id)),
  restoreBackup: (data: unknown) => post<{ ok: boolean }>("/api/import/restore", data),

  poll: () => get<{ shopping_count: number; favorites_count: number }>("/api/poll"),

  session: () => get<Session>("/api/session"),
  createVault: (label: string) =>
    post<{ ok?: boolean; key?: string; id?: string; error?: string }>("/api/auth/new", { label }),
  logout: () => post<{ ok: boolean }>("/api/auth/logout", {}),
};
