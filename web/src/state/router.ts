/**
 * Hash routing. Three shapes:
 *   ''                  → browse
 *   '#/<lang>/<slug>'    → recipe detail (resolved through search)
 *   '#/cook/<id>/<step>' → cooking mode at a given step
 */
import { createSignal } from "solid-js";

export type View = "browse" | "detail" | "cooking";

export const [view, setViewSignal] = createSignal<View>("browse");

/** Set by the app so the router can drive recipe loading / cooking without a cycle. */
interface RouterHooks {
  openRecipe: (id: string, opts?: { skipHash?: boolean }) => Promise<void>;
  resumeCooking: (id: string, step: number) => Promise<void>;
  onEnterBrowse: () => void;
  onLeaveCooking: () => void;
  findRecipeId: (lang: string, slug: string) => Promise<string | null>;
}

let hooks: RouterHooks | null = null;
export const registerRouter = (h: RouterHooks) => (hooks = h);

export function setView(next: View) {
  const prev = view();
  if (prev === "cooking" && next !== "cooking") hooks?.onLeaveCooking();
  setViewSignal(next);
  if (next === "browse") hooks?.onEnterBrowse();
}

export function pushHash(h: string) {
  const nh = h ? "#/" + h : "";
  if (location.hash !== nh) history.pushState(null, "", nh || location.pathname);
}

export async function handleHash() {
  const h = location.hash.replace(/^#\/?/, "");
  if (!h) {
    setView("browse");
    return;
  }
  const cookMatch = h.match(/^cook\/(.+)\/(\d+)$/);
  if (cookMatch) {
    await hooks?.resumeCooking(cookMatch[1], Number(cookMatch[2]));
    return;
  }
  const parts = h.split("/");
  if (parts.length >= 2) {
    const id = await hooks?.findRecipeId(parts[0], parts.slice(1).join("/"));
    if (id) {
      await hooks?.openRecipe(id, { skipHash: true });
      return;
    }
  }
  setView("browse");
}

export function initRouter() {
  addEventListener("popstate", () => void handleHash());
  addEventListener("hashchange", () => void handleHash());
}
