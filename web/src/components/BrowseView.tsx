import { Show, createSignal } from "solid-js";
import { api } from "../lib/api";
import { canLoadMore, doSearch, loading } from "../state/browse";
import { clearCookState, resumeCooking, resumeHint } from "../state/cooking";
import { IconChevronUp, IconPlay } from "./Icons";
import RecentlyCooked from "./RecentlyCooked";
import RecipeGrid from "./RecipeGrid";

export default function BrowseView(props: { onOpen: (id: string) => void; recentKey: number }) {
  const [showTop, setShowTop] = createSignal(false);
  let scroller!: HTMLDivElement;

  const onScroll = () => {
    setShowTop(scroller.scrollTop > 400);
    if (!loading() && canLoadMore() && scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 400) {
      void doSearch(false);
    }
  };

  return (
    <>
      <div class="recipes-wrap" ref={scroller} onScroll={onScroll}>
        <Show when={resumeHint()}>
          {(hint) => (
            <div
              class="continue-banner" role="button" tabindex="0"
              onClick={() => void resumeCooking(hint().id, hint().step)}
              onKeyDown={(e) => e.key === "Enter" && void resumeCooking(hint().id, hint().step)}
            >
              <span class="cb-icon"><IconPlay size={22} /></span>
              <div class="cb-text">
                <div class="cb-title">Continue: {hint().name}</div>
                <div class="cb-sub">Step {hint().step + 1} of {hint().total}</div>
              </div>
              <button
                type="button" class="cb-dismiss" title="Dismiss"
                onClick={(e) => {
                  e.stopPropagation();
                  clearCookState();
                }}
              >
                ×
              </button>
            </div>
          )}
        </Show>

        <RecentlyCooked onOpen={props.onOpen} reloadKey={props.recentKey} />
        <RecipeGrid onOpen={props.onOpen} />
      </div>

      <button
        type="button" class="back-top" classList={{ show: showTop() }} aria-label="Back to top"
        onClick={() => scroller.scrollTo({ top: 0, behavior: "smooth" })}
      >
        <IconChevronUp size={20} />
      </button>
    </>
  );
}

/** Opens a random recipe. */
export async function pickRandom(onOpen: (id: string) => void) {
  const d = await api.random();
  if (d.recipes?.[0]) onOpen(d.recipes[0].id);
}
