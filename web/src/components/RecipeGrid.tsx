import { For, Show } from "solid-js";
import { FALLBACK_IMG, FLAGS, diffLabel, difficulty, fmtTime } from "../lib/format";
import type { RecipeSlim } from "../lib/types";
import { canLoadMore, doSearch, favOn, loading, offset, recipes, total } from "../state/browse";

function RecipeCard(props: { r: RecipeSlim; onOpen: (id: string) => void }) {
  const diff = () => difficulty(props.r.totalTime, props.r.stepCount);
  return (
    <button type="button" class="recipe-card" onClick={() => props.onOpen(props.r.id)}>
      <div class="thumb">
        <img
          src={props.r.image || FALLBACK_IMG} alt={props.r.name} loading="lazy"
          onError={(e) => (e.currentTarget.src = FALLBACK_IMG)}
        />
        <Show when={props.r.totalTime}>
          <span class="time-badge">{fmtTime(props.r.totalTime)}</span>
        </Show>
        <span class="country-flag">{FLAGS[props.r.country] || ""}</span>
        <span class={`diff-badge diff-${diff()}`}>{diffLabel(diff())}</span>
        <Show when={props.r.hasNote}>
          <span class="note-badge" title="Has notes">📝</span>
        </Show>
      </div>
      <div class="card-body">
        <div class="name">{props.r.name}</div>
        <div class="card-meta">
          {props.r.yield ? props.r.yield + " · " : ""}
          {props.r.stepCount} steps
        </div>
        <span class="collection-tag">{props.r.collection}</span>
      </div>
    </button>
  );
}

function Skeletons() {
  return (
    <For each={Array.from({ length: 12 })}>
      {() => (
        <div class="skeleton-card">
          <div class="sk-img" />
          <div class="sk-line" />
          <div class="sk-line short" />
        </div>
      )}
    </For>
  );
}

export default function RecipeGrid(props: { onOpen: (id: string) => void }) {
  const empty = () => !loading() && recipes().length === 0;
  return (
    <div class="recipes">
      <Show when={!(loading() && recipes().length === 0)} fallback={<Skeletons />}>
        <For each={recipes()}>{(r) => <RecipeCard r={r} onOpen={props.onOpen} />}</For>
        <Show when={canLoadMore() && recipes().length > 0}>
          <div class="load-more">
            <button type="button" onClick={() => void doSearch(false)} disabled={loading()}>
              {loading() ? "Loading…" : `Load more (${(total() - offset()).toLocaleString()} left)`}
            </button>
          </div>
        </Show>
      </Show>
      <Show when={empty()}>
        <div class="no-results">
          <Show
            when={favOn()}
            fallback={<p>No recipes found.</p>}
          >
            <p class="nr-icon">♡</p>
            <p>No favorites yet</p>
            <p class="nr-hint">Open a recipe and tap the heart to save it here</p>
          </Show>
        </div>
      </Show>
    </div>
  );
}
