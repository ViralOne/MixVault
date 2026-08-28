import { Show, createSignal, onCleanup, onMount } from "solid-js";
import { api } from "./lib/api";
import AiCreator from "./components/AiCreator";
import BrowseView, { pickRandom } from "./components/BrowseView";
import CookingView from "./components/cooking/CookingView";
import DetailView from "./components/DetailView";
import { ImportModal, SettingsModal } from "./components/Modals";
import ShoppingPanel from "./components/ShoppingPanel";
import SubstitutionPopover from "./components/SubstitutionPopover";
import TopBar from "./components/TopBar";
import Toast from "./components/Toast";
import { doSearch, favOn, historyOn } from "./state/browse";
import { exitCooking, loadResumeHint, onLeaveCooking, resumeCooking } from "./state/cooking";
import { openRecipe } from "./state/recipe";
import { handleHash, initRouter, registerRouter, setView, view } from "./state/router";
import { load as loadShopping, open as shopPanelOpen, togglePanel } from "./state/shopping";

export default function App() {
  const [dark, setDark] = createSignal(document.documentElement.classList.contains("dark"));
  const [settingsOpen, setSettingsOpen] = createSignal(false);
  const [importOpen, setImportOpen] = createSignal(false);
  const [creatorOpen, setCreatorOpen] = createSignal(false);
  // Bumped whenever the "recently cooked" rail should refresh.
  const [recentKey, setRecentKey] = createSignal(0);

  const open = (id: string) => void openRecipe(id);

  function toggleDark() {
    const next = !dark();
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("dark", next ? "1" : "0");
  }

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key !== "Escape") return;
    if (importOpen()) return setImportOpen(false);
    if (settingsOpen()) return setSettingsOpen(false);
    if (creatorOpen()) return setCreatorOpen(false);
    if (shopPanelOpen()) return togglePanel();
    if (view() === "cooking") return exitCooking();
    if (view() === "detail") return setView("browse");
  };

  onMount(() => {
    registerRouter({
      openRecipe,
      resumeCooking,
      onEnterBrowse: () => {
        setRecentKey((k) => k + 1);
        void loadResumeHint();
      },
      onLeaveCooking,
      findRecipeId: async (lang, slug) => {
        const p = new URLSearchParams({ q: slug.replace(/-/g, " "), lang, limit: "5" });
        const d = await api.search(p);
        return d.recipes?.[0]?.id ?? null;
      },
    });
    initRouter();

    void doSearch(true);
    void loadShopping();
    void loadResumeHint();
    if (location.hash.length > 2) void handleHash();

    addEventListener("keydown", onKeyDown);
    // Another device may have changed the shared list / favourites.
    const poll = setInterval(async () => {
      try {
        const d = await api.poll();
        const last = lastPoll;
        lastPoll = d;
        if (!last) return;
        if (d.shopping_count !== last.shopping_count) await loadShopping();
        if (d.favorites_count !== last.favorites_count && favOn() && !historyOn()) await doSearch(true);
      } catch {
        /* offline */
      }
    }, 30_000);

    onCleanup(() => {
      removeEventListener("keydown", onKeyDown);
      clearInterval(poll);
    });
  });

  let lastPoll: { shopping_count: number; favorites_count: number } | null = null;

  return (
    <>
      <div id="browse-view" class="view" classList={{ active: view() === "browse" }}>
        <TopBar onRandom={() => void pickRandom(open)} onSettings={() => setSettingsOpen(true)} />
        <BrowseView onOpen={open} recentKey={recentKey()} />
      </div>

      <div id="detail-view" class="view" classList={{ active: view() === "detail" }}>
        <DetailView />
      </div>

      <div id="cooking-view" class="view" classList={{ active: view() === "cooking" }}>
        <CookingView />
      </div>

      <ShoppingPanel />
      <AiCreator open={creatorOpen()} onClose={() => setCreatorOpen(false)} onOpenRecipe={open} />

      <Show when={importOpen()}>
        <ImportModal onClose={() => setImportOpen(false)} onOpenRecipe={open} />
      </Show>
      <Show when={settingsOpen()}>
        <SettingsModal
          onClose={() => setSettingsOpen(false)}
          onOpenCreator={() => setCreatorOpen(true)}
          onOpenImport={() => setImportOpen(true)}
          onToggleDark={toggleDark}
          isDark={dark()}
        />
      </Show>

      <SubstitutionPopover />
      <Toast />
    </>
  );
}
