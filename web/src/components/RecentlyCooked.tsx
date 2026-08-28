/**
 * "Recently cooked" carousel — replaces the old stacked Recently Cooked / Cook Again
 * rows (cooking history already lives behind the History filter).
 */
import { For, Show, createEffect, createSignal, onCleanup, onMount } from "solid-js";
import { api } from "../lib/api";
import { FALLBACK_IMG, fmtTime, relTime } from "../lib/format";
import type { HistoryEntry } from "../lib/types";
import { historyOn, openHistory } from "../state/browse";
import { IconArrowRight, IconChevronLeft, IconChevronRight, IconHistory } from "./Icons";

interface Card extends HistoryEntry {
  times: number;
}

/** Newest cook per recipe, with a repeat count. */
function dedupe(history: HistoryEntry[]): Card[] {
  const byId = new Map<string, Card>();
  for (const h of history) {
    const seen = byId.get(h.recipe.id);
    if (seen) seen.times++;
    else byId.set(h.recipe.id, { ...h, times: 1 });
  }
  return [...byId.values()];
}

export default function RecentlyCooked(props: { onOpen: (id: string) => void; reloadKey: number }) {
  const [cards, setCards] = createSignal<Card[]>([]);
  const [uniqueCount, setUniqueCount] = createSignal(0);
  const [atStart, setAtStart] = createSignal(true);
  const [atEnd, setAtEnd] = createSignal(false);
  const [scrollable, setScrollable] = createSignal(false);
  let track!: HTMLDivElement;

  async function load() {
    try {
      const d = await api.history();
      const all = dedupe(d.history || []);
      setUniqueCount(all.length);
      setCards(all.slice(0, 14));
      requestAnimationFrame(sync);
    } catch {
      /* offline — leave the rail empty */
    }
  }

  function sync() {
    if (!track) return;
    const max = track.scrollWidth - track.clientWidth;
    setAtStart(track.scrollLeft <= 2);
    setAtEnd(track.scrollLeft >= max - 2);
    setScrollable(max > 4);
  }

  function scrollBy(direction: 1 | -1) {
    track?.scrollBy({ left: direction * Math.max(192, track.clientWidth * 0.8), behavior: "smooth" });
  }

  onMount(() => {
    void load();
    addEventListener("resize", sync);
    onCleanup(() => removeEventListener("resize", sync));
  });

  // Re-fetch whenever we come back to browse or a cook is logged.
  createEffect(() => {
    props.reloadKey;
    void load();
  });

  let debounce: ReturnType<typeof setTimeout>;
  const onScroll = () => {
    clearTimeout(debounce);
    debounce = setTimeout(sync, 60);
  };

  return (
    <Show when={cards().length > 0 && !historyOn()}>
      <section class="carousel" aria-labelledby="recent-heading">
        <div class="carousel-head">
          <h2 class="carousel-title" id="recent-heading">
            <IconHistory />
            Recently cooked
            <span class="carousel-count">{uniqueCount()}</span>
          </h2>
          <div class="carousel-actions">
            <Show when={scrollable()}>
              <button
                type="button" class="carousel-arrow" aria-label="Scroll left"
                disabled={atStart()} onClick={() => scrollBy(-1)}
              >
                <IconChevronLeft />
              </button>
              <button
                type="button" class="carousel-arrow" aria-label="Scroll right"
                disabled={atEnd()} onClick={() => scrollBy(1)}
              >
                <IconChevronRight />
              </button>
            </Show>
            <button type="button" class="carousel-link" onClick={() => void openHistory()}>
              View all
              <IconArrowRight />
            </button>
          </div>
        </div>

        <div
          class="carousel-track"
          classList={{ "at-start": atStart(), "at-end": atEnd() }}
          ref={track}
          onScroll={onScroll}
          role="list"
          tabindex="0"
          aria-label="Recently cooked recipes"
        >
          <For each={cards()}>
            {(c) => (
              <button type="button" class="rc-card" role="listitem" onClick={() => props.onOpen(c.recipe.id)}>
                <div class="rc-media">
                  <img
                    src={c.recipe.image || FALLBACK_IMG} loading="lazy" alt=""
                    onError={(e) => (e.currentTarget.src = FALLBACK_IMG)}
                  />
                  <span class="rc-when">{relTime(c.cooked_at)}</span>
                  <Show when={c.times > 1}>
                    <span class="rc-times">×{c.times}</span>
                  </Show>
                </div>
                <div class="rc-body">
                  <div class="rc-name">{c.recipe.name}</div>
                  <div class="rc-meta">
                    <Show when={fmtTime(c.recipe.totalTime)}>
                      <span>{fmtTime(c.recipe.totalTime)}</span>
                      <span class="dot" />
                    </Show>
                    <span>{c.recipe.stepCount} steps</span>
                  </div>
                </div>
              </button>
            )}
          </For>
        </div>
      </section>
    </Show>
  );
}
