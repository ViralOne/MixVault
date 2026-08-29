import { For, Show, createSignal, onMount } from "solid-js";
import { api } from "../lib/api";
import { FLAGS } from "../lib/format";
import type { Meta } from "../lib/types";
import {
  aiMode, clearFilters, country, doAiSearch, doNutritionSearch, doSearch, favOn, hasFilters,
  historyOn, lang, nutOpen, nutrition, query, setAiMode, setCountry, setLang, setNutOpen,
  setNutrition, setQuery, setTag, tag, toggleFavFilter, toggleHistory, resultInfo,
} from "../state/browse";
import { open as shopOpen, togglePanel, uncheckedCount } from "../state/shopping";
import { session, signOut } from "../state/session";
import { IconCart, IconLogo, IconMore, IconDice, IconSearch, IconSparkles, IconSwitchVault } from "./Icons";

export default function TopBar(props: { onRandom: () => void; onSettings: () => void }) {
  const [meta, setMeta] = createSignal<Meta | null>(null);
  const [tags, setTags] = createSignal<{ tag: string; count: number }[]>([]);
  let searchTimer: ReturnType<typeof setTimeout>;

  onMount(() => {
    void api.meta().then(setMeta);
    void api.tagsList().then((d) => setTags(d.tags || []));
  });

  const onInput = (v: string) => {
    setQuery(v);
    clearTimeout(searchTimer);
    if (aiMode()) return;
    searchTimer = setTimeout(() => void doSearch(true), 300);
  };

  return (
    <div class="top-bar">
      <div class="top-row">
        <div class="logo">
          <IconLogo size={28} />
          <span>MixVault</span>
        </div>

        <div class="search-wrap">
          <IconSearch class="search-icon" />
          <input
            class="search-input" type="search" id="search" autocomplete="off"
            placeholder={aiMode() ? 'Ask AI: "I have rice and chicken…"' : "Search recipes…"}
            value={query()}
            onInput={(e) => onInput(e.currentTarget.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && aiMode()) {
                e.preventDefault();
                void doAiSearch();
              }
            }}
          />
          <button
            type="button" class="ai-toggle" classList={{ active: aiMode() }}
            title="Ask AI" aria-pressed={aiMode()}
            onClick={() => setAiMode(!aiMode())}
          >
            <IconSparkles size={14} />
          </button>
        </div>

        <button type="button" class="icon-btn" title="Surprise me" onClick={props.onRandom}>
          <IconDice />
        </button>
        <button
          type="button" class="icon-btn" title="Shopping list" aria-label="Shopping list"
          style={{ position: "relative" }} aria-expanded={shopOpen()}
          onClick={togglePanel}
        >
          <IconCart />
          <Show when={uncheckedCount() > 0}>
            <span class="shop-badge" aria-live="polite">{uncheckedCount()}</span>
          </Show>
        </button>
        <Show when={session()?.multi_user}>
          <button
            type="button" class="icon-btn"
            title={`Switch vault (signed in as ${session()!.label || "this vault"})`}
            aria-label="Switch vault"
            onClick={() => void signOut()}
          >
            <IconSwitchVault />
          </button>
        </Show>
        <button type="button" class="icon-btn" title="Settings" onClick={props.onSettings}>
          <IconMore />
        </button>
      </div>

      <div class="filter-row">
        <select
          class="filter-select" classList={{ "has-value": !!country() }}
          value={country()}
          onChange={(e) => {
            setCountry(e.currentTarget.value);
            setQuery("");
            void doSearch(true);
          }}
        >
          <option value="">🌍 All{meta() ? ` (${meta()!.total.toLocaleString()})` : " Countries"}</option>
          <For each={meta()?.countries || []}>
            {(c) => (
              <option value={c.country}>
                {(FLAGS[c.country] || "") + " " + c.country} ({c.count.toLocaleString()})
              </option>
            )}
          </For>
        </select>

        <select
          class="filter-select" classList={{ "has-value": !!lang() }}
          value={lang()}
          onChange={(e) => {
            setLang(e.currentTarget.value);
            setQuery("");
            void doSearch(true);
          }}
        >
          <option value="">🗣 All Languages</option>
          <For each={meta()?.languages || []}>
            {(l) => <option value={l.lang}>{l.name} ({l.count.toLocaleString()})</option>}
          </For>
        </select>

        <button type="button" class="chip-filter fav" classList={{ active: favOn() }} onClick={() => void toggleFavFilter()}>
          {favOn() ? "♥" : "♡"} Favorites
        </button>
        <button type="button" class="chip-filter" classList={{ active: historyOn() }} onClick={() => void toggleHistory()}>
          ⏱ History
        </button>
        <button type="button" class="chip-filter" classList={{ active: nutOpen() }} onClick={() => setNutOpen(!nutOpen())}>
          🥗 Nutrition
        </button>

        <Show when={tags().length > 0}>
          <select
            class="filter-select" classList={{ "has-value": !!tag() }}
            value={tag()}
            onChange={(e) => {
              setTag(e.currentTarget.value);
              void doSearch(true);
            }}
          >
            <option value="">🏷 All Tags</option>
            <For each={tags()}>{(t) => <option value={t.tag}>{t.tag} ({t.count})</option>}</For>
          </select>
        </Show>

        <Show when={hasFilters()}>
          <button type="button" class="clear-btn" onClick={() => void clearFilters()}>✕ Clear</button>
        </Show>
      </div>

      <Show when={nutOpen()}>
        <div class="nut-filter">
          <div class="nut-group">
            <label for="nut-cal">Max kcal</label>
            <input
              id="nut-cal" type="number" placeholder="500" value={nutrition().cal}
              onInput={(e) => setNutrition({ ...nutrition(), cal: e.currentTarget.value })}
            />
          </div>
          <div class="nut-group">
            <label for="nut-prot">Min protein (g)</label>
            <input
              id="nut-prot" type="number" placeholder="20" value={nutrition().prot}
              onInput={(e) => setNutrition({ ...nutrition(), prot: e.currentTarget.value })}
            />
          </div>
          <div class="nut-group">
            <label for="nut-carbs">Max carbs (g)</label>
            <input
              id="nut-carbs" type="number" placeholder="50" value={nutrition().carbs}
              onInput={(e) => setNutrition({ ...nutrition(), carbs: e.currentTarget.value })}
            />
          </div>
          <div class="nut-group">
            <label for="nut-fat">Max fat (g)</label>
            <input
              id="nut-fat" type="number" placeholder="30" value={nutrition().fat}
              onInput={(e) => setNutrition({ ...nutrition(), fat: e.currentTarget.value })}
            />
          </div>
          <button type="button" onClick={() => void doNutritionSearch()}>Filter</button>
        </div>
      </Show>

      <div class="result-info">
        <strong>{resultInfo().lead}</strong> {resultInfo().tail}
      </div>
    </div>
  );
}
