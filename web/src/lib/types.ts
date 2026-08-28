/** Shapes returned by the Python API (see lib/db.py::slim_row and lib/handlers/*). */

export interface RecipeSlim {
  id: string;
  name: string;
  country: string;
  lang: string;
  collection: string;
  image: string;
  totalTime: string; // ISO-8601 duration, e.g. "PT1H5M"
  yield: string;
  stepCount: number;
  hasNote: boolean;
}

export interface Nutrition {
  calories?: string;
  protein?: string;
  carbs?: string;
  fat?: string;
}

export interface Recipe extends Omit<RecipeSlim, "stepCount"> {
  ingredients: string[];
  steps: string[];
  ingredient_icons?: (string | null)[];
  nutrition?: Nutrition;
  keywords?: string;
  categories?: string[];
  note?: string;
  is_favorite?: boolean;
  cook_count?: number;
  /** True when this recipe lives in your vault rather than the shared library. */
  private?: boolean;
  /** False for shared library recipes while access keys are in use. */
  editable?: boolean;
}

export interface HistoryEntry {
  recipe: RecipeSlim;
  cooked_at: string; // "YYYY-MM-DD HH:MM:SS" in UTC
}

export interface ShopItem {
  id: number;
  item: string;
  checked: 0 | 1 | boolean;
  recipe_id: string;
  recipe_name: string;
}

export interface Meta {
  total: number;
  countries: { country: string; count: number }[];
  languages: { lang: string; name: string; count: number }[];
}

export interface SearchResponse {
  recipes: RecipeSlim[];
  total: number;
  offset: number;
}

export interface AiSearchResponse {
  recipes: RecipeSlim[];
  total: number;
  keywords: string[];
  langs?: string[];
  error?: string;
}

export interface CreatorRecipe {
  name: string;
  ingredients?: string[];
  steps?: string[];
  categories?: string[];
  keywords?: string;
  image?: string;
  country?: string;
  lang?: string;
  collection?: string;
  [key: string]: unknown;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface Substitution {
  sub: string;
  ratio: string;
  note: string;
}

/** What the server will tell a signed-in client about its own session. */
export interface Session {
  multi_user: boolean;
  signed_in: boolean;
  label: string;
  signup_enabled: boolean;
}
