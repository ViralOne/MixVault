import { For, Show, createSignal } from "solid-js";
import { api } from "../lib/api";
import { FALLBACK_IMG, FLAGS, TRANSLATE_LANGS, diffLabel, difficulty, fmtTime, scaleText } from "../lib/format";
import { parseStep } from "../lib/steps";
import { askNotificationPermission } from "../lib/device";
import { doSearch } from "../state/browse";
import { startCooking } from "../state/cooking";
import {
  addTag, deleteRecipe, editing, openRecipe, recipe, removeTag, saveNote, scale, setEditing,
  setScale, shareRecipe, similar, tags, toggleFavorite,
} from "../state/recipe";
import { setView } from "../state/router";
import { addRecipe, items as shopItems } from "../state/shopping";
import { showToast } from "../state/toast";
import {
  IconCart, IconCheck, IconChevronLeft, IconClock, IconEdit, IconGlobe, IconPlay, IconPlus,
  IconShare, IconSwap, IconTrash,
} from "./Icons";
import { showSubstitutions } from "./SubstitutionPopover";
import EditRecipeForm from "./EditRecipeForm";

export default function DetailView() {
  const [checked, setChecked] = createSignal<Set<number>>(new Set());
  const [translating, setTranslating] = createSignal(false);
  const [targetLang, setTargetLang] = createSignal(localStorage.getItem("translateLang") || "");

  const r = recipe;
  const diff = () => {
    const rec = r();
    return rec ? difficulty(rec.totalTime, rec.steps.length) : "easy";
  };
  const inShopList = () => {
    const rec = r();
    return !!rec && shopItems().some((i) => i.recipe_id === rec.id);
  };

  const toggleChecked = (i: number) => {
    const next = new Set(checked());
    next.has(i) ? next.delete(i) : next.add(i);
    setChecked(next);
  };

  async function translate() {
    const rec = r();
    const lang = targetLang();
    if (!rec || !lang) {
      showToast("Select a language");
      return;
    }
    if (lang === rec.lang) {
      showToast("Already in that language");
      return;
    }
    localStorage.setItem("translateLang", lang);
    setTranslating(true);
    try {
      const d = await api.translate(rec.id, lang);
      if (d.error) showToast(d.error);
      else await openRecipe(d.id);
    } catch {
      showToast("Translation failed");
    } finally {
      setTranslating(false);
    }
  }

  return (
    <Show when={r()}>
      {(rec) => (
        <>
          <div class="detail-header">
            <button type="button" class="btn-back" aria-label="Back" onClick={() => setView("browse")}>
              <IconChevronLeft />
            </button>
            <h1>{rec().name}</h1>
            <button
              type="button" class="fav-btn" classList={{ active: !!rec().is_favorite }}
              aria-label="Favorite" aria-pressed={!!rec().is_favorite}
              onClick={() => void toggleFavorite()}
            >
              <span class="heart">{rec().is_favorite ? "♥" : "♡"}</span>
            </button>
            <button type="button" class="fav-btn" title="Edit recipe" onClick={() => setEditing(!editing())}>
              <IconEdit size={16} />
            </button>
            <button type="button" class="fav-btn" title="Share recipe" onClick={shareRecipe}>
              <IconShare size={16} />
            </button>
            <button
              type="button" class="fav-btn" title="Delete recipe"
              onClick={async () => {
                if (await deleteRecipe()) {
                  setView("browse");
                  void doSearch(true);
                }
              }}
            >
              <IconTrash size={16} />
            </button>
          </div>

          <div class="detail-scroll">
            <Show when={!editing()} fallback={<EditRecipeForm />}>
              <Show when={rec().image}>
                <div class="hero-wrap">
                  <img
                    class="hero-img" src={rec().image} alt={rec().name}
                    onError={(e) => (e.currentTarget.style.display = "none")}
                  />
                </div>
              </Show>

              <div class="detail-body">
                <h2>{rec().name}</h2>

                <div class="meta-row">
                  <Show when={rec().totalTime}>
                    <span class="meta-pill"><IconClock size={16} />{fmtTime(rec().totalTime)}</span>
                  </Show>
                  <Show when={rec().yield}>
                    <span class="meta-pill">{rec().yield}</span>
                  </Show>
                  <span class="meta-pill">{FLAGS[rec().country] || ""} {rec().country}</span>
                  <span class={`meta-pill diff-badge diff-${diff()}`}>{diffLabel(diff())}</span>
                  <Show when={rec().cook_count}>
                    <span class="meta-pill">👨‍🍳 Cooked {rec().cook_count}×</span>
                  </Show>
                </div>

                <div class="tags-row">
                  <For each={tags()}>
                    {(t) => (
                      <span class="tag-pill">
                        {t}
                        <button type="button" class="tag-x" aria-label={`Remove tag ${t}`} onClick={() => void removeTag(t)}>×</button>
                      </span>
                    )}
                  </For>
                  <button
                    type="button" class="tag-add-btn" title="Add tag"
                    onClick={() => {
                      const t = prompt("Enter tag:");
                      if (t) void addTag(t);
                    }}
                  >
                    <IconPlus size={14} />
                  </button>
                </div>

                <div class="section-label">Ingredients</div>
                <div class="scaler-row">
                  <For each={[0.5, 1, 2, 3]}>
                    {(f) => (
                      <button
                        type="button" class="scaler-btn" classList={{ active: scale() === f }}
                        onClick={() => setScale(f)}
                      >
                        ×{f === 0.5 ? "½" : f}
                      </button>
                    )}
                  </For>
                </div>

                <button
                  type="button" class="shop-add-inline" classList={{ added: inShopList() }}
                  onClick={() => void addRecipe(rec(), scale())}
                >
                  <Show when={inShopList()} fallback={<><IconCart size={16} /> Add to shopping list</>}>
                    <IconCheck size={16} /> Added
                  </Show>
                </button>

                <ul class="ing-list">
                  <For each={rec().ingredients}>
                    {(ig, i) => (
                      <li
                        class="ing-item" classList={{ checked: checked().has(i()) }}
                        onClick={() => toggleChecked(i())}
                        onContextMenu={(e) => {
                          e.preventDefault();
                          void showSubstitutions(ig, e, rec().name);
                        }}
                      >
                        <span class="check-circle">✓</span>
                        <Show
                          when={rec().ingredient_icons?.[i()]}
                          fallback={<span class="ing-icon-placeholder" />}
                        >
                          <img
                            class="ing-icon" src={rec().ingredient_icons![i()]!} width="28" height="28" alt=""
                            onError={(e) => (e.currentTarget.style.display = "none")}
                          />
                        </Show>
                        <span class="ing-text">{scaleText(ig, scale())}</span>
                        <button
                          type="button" class="ing-sub" title="Find substitute"
                          onClick={(e) => {
                            e.stopPropagation();
                            void showSubstitutions(ig, e, rec().name);
                          }}
                        >
                          <IconSwap size={14} />
                        </button>
                      </li>
                    )}
                  </For>
                </ul>

                <Show when={rec().nutrition?.calories}>
                  <div class="section-label">Nutrition</div>
                  <div class="nutrition-grid">
                    <div class="nut-card">
                      <div class="val">{rec().nutrition!.calories!.replace(" kcal", "")}</div>
                      <div class="label">kcal</div>
                    </div>
                    <div class="nut-card">
                      <div class="val">{rec().nutrition!.protein || "-"}</div>
                      <div class="label">Protein</div>
                    </div>
                    <div class="nut-card">
                      <div class="val">{rec().nutrition!.carbs || "-"}</div>
                      <div class="label">Carbs</div>
                    </div>
                    <div class="nut-card">
                      <div class="val">{rec().nutrition!.fat || "-"}</div>
                      <div class="label">Fat</div>
                    </div>
                  </div>
                </Show>

                <button
                  type="button" class="cook-btn"
                  onClick={() => {
                    askNotificationPermission();
                    startCooking(rec());
                  }}
                >
                  <IconPlay size={22} />
                  Start Cooking · {rec().steps.length} steps
                </button>

                <div class="translate-row">
                  <select
                    class="filter-select" style={{ flex: 1 }} value={targetLang()}
                    onChange={(e) => setTargetLang(e.currentTarget.value)}
                    aria-label="Translate to"
                  >
                    <option value="">🌐 Translate to…</option>
                    <For each={TRANSLATE_LANGS}>{(l) => <option value={l.code}>{l.label}</option>}</For>
                  </select>
                  <button type="button" class="cook-btn" disabled={translating()} onClick={() => void translate()}>
                    <Show when={translating()} fallback={<><IconGlobe size={16} /> Translate</>}>
                      <span class="translate-spinner" />Translating…
                    </Show>
                  </button>
                </div>

                <div class="section-label">Preparation</div>
                <div class="steps-preview">
                  <For each={rec().steps}>
                    {(s, i) => (
                      <div class="step-preview-item">
                        <span class="step-num">{i() + 1}</span>
                        <span>{s}</span>
                        <Show when={parseStep(s).mode === "manual"}>
                          <span class="sp-mode" title="Hands-on step — no Thermomix">by hand</span>
                        </Show>
                      </div>
                    )}
                  </For>
                </div>

                <Show when={similar().length > 0}>
                  <div class="section-label">You might also like</div>
                  <div class="similar-row">
                    <For each={similar()}>
                      {(s) => (
                        <button type="button" class="similar-card" onClick={() => void openRecipe(s.id)}>
                          <img
                            src={s.image || FALLBACK_IMG} loading="lazy" alt=""
                            onError={(e) => (e.currentTarget.src = FALLBACK_IMG)}
                          />
                          <div class="sc-name">{s.name}</div>
                        </button>
                      )}
                    </For>
                  </div>
                </Show>

                <div class="section-label">Notes</div>
                <textarea
                  class="note-input" placeholder="Add your notes about this recipe…"
                  value={rec().note || ""}
                  onBlur={(e) => void saveNote(e.currentTarget.value)}
                />
              </div>
            </Show>
          </div>
        </>
      )}
    </Show>
  );
}
