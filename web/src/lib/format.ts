/** Pure formatting / parsing helpers shared across views. */
import type { ShopItem } from "./types";

export const FLAGS: Record<string, string> = {
  Argentina: "🇦🇷", Australia: "🇦🇺", Austria: "🇦🇹", Belgium: "🇧🇪", Brazil: "🇧🇷",
  Canada: "🇨🇦", Chile: "🇨🇱", China: "🇨🇳", Colombia: "🇨🇴", Cyprus: "🇨🇾",
  "Czech Republic": "🇨🇿", Denmark: "🇩🇰", France: "🇫🇷", Germany: "🇩🇪", Greece: "🇬🇷",
  Guatemala: "🇬🇹", Hungary: "🇭🇺", Iceland: "🇮🇸", Indonesia: "🇮🇩", Italy: "🇮🇹",
  Malaysia: "🇲🇾", Mexico: "🇲🇽", Netherland: "🇳🇱", Norway: "🇳🇴", Panama: "🇵🇦",
  Paraguay: "🇵🇾", Peru: "🇵🇪", Philippines: "🇵🇭", Poland: "🇵🇱", Portugal: "🇵🇹",
  Romania: "🇷🇴", "Saudi Arabia": "🇸🇦", Singapore: "🇸🇬", Spain: "🇪🇸", Sweden: "🇸🇪",
  Switzerland: "🇨🇭", Taiwan: "🇹🇼", Turkey: "🇹🇷", "United Kingdom": "🇬🇧", USA: "🇺🇸",
  Vietnam: "🇻🇳",
};

export const TRANSLATE_LANGS: { code: string; label: string }[] = [
  { code: "en", label: "English" }, { code: "de", label: "Deutsch" },
  { code: "fr", label: "Français" }, { code: "es", label: "Español" },
  { code: "it", label: "Italiano" }, { code: "pt", label: "Português" },
  { code: "ro", label: "Română" }, { code: "pl", label: "Polski" },
  { code: "nl", label: "Nederlands" }, { code: "cs", label: "Čeština" },
  { code: "tr", label: "Türkçe" }, { code: "zh", label: "中文" },
];

/** Neutral placeholder used when a remote recipe image 404s. */
export const FALLBACK_IMG =
  "data:image/svg+xml," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 60"><rect fill="#e5e7eb" width="80" height="60"/>' +
      '<g transform="translate(28,16)" fill="none" stroke="#9ca3af" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">' +
      '<path d="M12 2C6.5 2 2 6.5 2 12s10 14 10 14 10-8.5 10-14S17.5 2 12 2z"/><circle cx="12" cy="10" r="3"/></g></svg>',
  );

export function fmtTime(iso?: string): string {
  if (!iso) return "";
  const m = iso.match(/PT(?:(\d+)H)?(?:(\d+)M)?/);
  if (!m) return "";
  return (m[1] ? m[1] + "h " : "") + (m[2] ? m[2] + "min" : "");
}

export function timeToMin(iso?: string): number {
  if (!iso) return 0;
  const m = iso.match(/PT(?:(\d+)H)?(?:(\d+)M)?/);
  return Number(m?.[1] || 0) * 60 + Number(m?.[2] || 0);
}

export type Difficulty = "easy" | "medium" | "hard";

export function difficulty(time: string | undefined, steps: number): Difficulty {
  const m = timeToMin(time);
  if (steps <= 4 || m <= 20) return "easy";
  if (steps > 8 || m > 45) return "hard";
  return "medium";
}

export const diffLabel = (d: Difficulty) => ({ easy: "Easy", medium: "Medium", hard: "Hard" })[d];

export function slugify(s: string): string {
  return s
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/gi, "-")
    .replace(/^-|-$/g, "")
    .toLowerCase();
}

export function fmtSecs(s: number): string {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(sec).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

/** SQLite stores `datetime('now')`, i.e. UTC without a zone marker. */
export function utcDate(s: string): Date {
  return new Date(String(s).replace(" ", "T").replace(/Z?$/, "Z"));
}

export function relTime(s: string): string {
  const days = Math.floor((Date.now() - utcDate(s).getTime()) / 86_400_000);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return days + "d ago";
  if (days < 30) return Math.floor(days / 7) + "w ago";
  if (days < 365) return Math.floor(days / 30) + "mo ago";
  return Math.floor(days / 365) + "y ago";
}

/** Scale every number inside an ingredient line (handles decimals and fractions). */
export function scaleText(text: string, factor: number): string {
  if (factor === 1) return text;
  return text.replace(/(\d+[.,]\d+|\d+\/\d+|\d+)/g, (match) => {
    let num: number;
    if (match.includes("/")) {
      const [a, b] = match.split("/");
      num = parseFloat(a) / parseFloat(b);
    } else {
      num = parseFloat(match.replace(",", "."));
    }
    const scaled = num * factor;
    if (scaled % 1 === 0) return String(scaled);
    return scaled.toFixed(1).replace(/\.0$/, "");
  });
}

const FRACTIONS: Record<string, number> = { "½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 1 / 3, "⅔": 2 / 3 };

export interface ParsedIngredient {
  qty: number;
  unit: string;
  name: string;
}

export function parseIngredient(text: string): ParsedIngredient {
  const m = text.match(
    /^([\d.,/½¼¾⅓⅔]+)\s*(g|kg|ml|l|dl|cl|oz|lb|tsp|tbsp|cup|cups|piece|pieces|pcs|stk|stück|ks|buc)?\s*(.+)$/i,
  );
  if (!m) return { qty: 0, unit: "", name: text.trim().toLowerCase() };
  const raw = m[1].replace(",", ".");
  let qty: number;
  if (raw.includes("/")) {
    const [a, b] = raw.split("/");
    qty = parseFloat(a) / parseFloat(b);
  } else if (FRACTIONS[raw] !== undefined) {
    qty = FRACTIONS[raw];
  } else {
    qty = parseFloat(raw);
  }
  return { qty: qty || 0, unit: (m[2] || "").toLowerCase(), name: m[3].trim().toLowerCase() };
}

export interface MergedShopItem extends ParsedIngredient {
  id: number;
  ids: number[];
  checked: boolean;
  recipe_id: string;
  recipe_name: string;
  original: string;
  display: string;
}

/** Collapse duplicate ingredients within a group, summing quantities. */
export function mergeShopItems(items: ShopItem[]): MergedShopItem[] {
  const merged = new Map<string, Omit<MergedShopItem, "display" | "id">>();
  const order: string[] = [];
  for (const item of items) {
    const p = parseIngredient(item.item);
    const key = p.name + "|" + p.unit;
    const existing = merged.get(key);
    if (existing) {
      existing.qty += p.qty;
      existing.ids.push(item.id);
      if (!item.checked) existing.checked = false;
    } else {
      merged.set(key, {
        ...p, ids: [item.id], checked: !!item.checked,
        recipe_id: item.recipe_id, recipe_name: item.recipe_name, original: item.item,
      });
      order.push(key);
    }
  }
  return order.map((k) => {
    const m = merged.get(k)!;
    const qty = m.qty % 1 ? m.qty.toFixed(1) : String(m.qty);
    const display = m.qty > 0 ? `${qty}${m.unit ? " " + m.unit : ""} ${m.name}` : m.original;
    return { ...m, display, id: m.ids[0] };
  });
}
