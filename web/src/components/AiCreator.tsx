import { For, Show, createSignal } from "solid-js";
import { api } from "../lib/api";
import type { ChatMessage, CreatorRecipe } from "../lib/types";
import { showToast } from "../state/toast";
import { IconChevronLeft, IconTrash } from "./Icons";

const GREETING =
  "Hi! I'm your recipe assistant. Tell me what you'd like to cook — ingredients you have, " +
  "cuisine preference, dietary needs — and I'll help you create a recipe.";

interface Bubble {
  from: "user" | "ai";
  text: string;
  variant?: "card" | "muted";
  images?: { url: string; title?: string }[];
}

export default function AiCreator(props: { open: boolean; onClose: () => void; onOpenRecipe: (id: string) => void }) {
  const [bubbles, setBubbles] = createSignal<Bubble[]>([{ from: "ai", text: GREETING }]);
  const [history, setHistory] = createSignal<ChatMessage[]>([]);
  const [draft, setDraft] = createSignal<CreatorRecipe | null>(null);
  const [image, setImage] = createSignal("");
  const [busy, setBusy] = createSignal(false);
  let input!: HTMLInputElement;
  let scroller!: HTMLDivElement;

  const push = (b: Bubble) => {
    setBubbles([...bubbles(), b]);
    requestAnimationFrame(() => (scroller.scrollTop = scroller.scrollHeight));
  };

  function reset() {
    setBubbles([{ from: "ai", text: GREETING }]);
    setHistory([]);
    setDraft(null);
    setImage("");
  }

  async function send(text: string) {
    const msg = text.trim();
    if (!msg || busy()) return;
    input.value = "";
    setBusy(true);
    push({ from: "user", text: msg });
    const convo: ChatMessage[] = [...history(), { role: "user", content: msg }];
    setHistory(convo);
    try {
      const d = await api.aiChat(convo);
      if (d.error) {
        push({ from: "ai", text: d.error, variant: "muted" });
        return;
      }
      setHistory([...convo, { role: "assistant", content: d.reply }]);
      push({ from: "ai", text: d.reply.replace(/```json[\s\S]*?```/g, "").trim() });
      if (d.recipe) {
        setDraft(d.recipe);
        push({
          from: "ai",
          variant: "card",
          text:
            `📋 ${d.recipe.name}\n${d.recipe.ingredients?.length || 0} ingredients · ` +
            `${d.recipe.steps?.length || 0} steps\nUse the buttons below to find an image and save.`,
        });
      }
    } catch {
      push({ from: "ai", text: "Something went wrong. Try again." });
    } finally {
      setBusy(false);
      input.focus();
    }
  }

  async function findImages() {
    const r = draft();
    if (!r) return;
    push({ from: "ai", text: "🔍 Searching for images…" });
    // An English name usually returns much better stock photos.
    let englishName = "";
    try {
      const tr = await api.aiChat([
        { role: "user", content: `Translate this recipe name to English in 2-3 words only, nothing else: "${r.name}"` },
      ]);
      englishName = (tr.reply || "").trim().replace(/['"]/g, "");
    } catch {
      /* fall back to the original name */
    }
    const queries = [r.name];
    if (englishName && englishName.length < 50) queries.push(englishName);
    if (r.categories?.length) queries.push(r.categories[0]);
    if (r.keywords) queries.push(r.keywords.split(",")[0].trim());

    const seen = new Set<string>();
    const found: { url: string; title?: string }[] = [];
    for (const q of queries) {
      try {
        const d = await api.aiImages(q);
        for (const img of d.images || []) {
          if (!seen.has(img.url)) {
            seen.add(img.url);
            found.push(img);
          }
        }
      } catch {
        /* try the next query */
      }
      if (found.length >= 8) break;
    }

    const rest = bubbles().slice(0, -1);
    setBubbles([
      ...rest,
      found.length
        ? { from: "ai", text: "Pick an image:", images: found.slice(0, 8) }
        : { from: "ai", text: "No images found. You can add an image URL after saving via Edit." },
    ]);
  }

  async function save() {
    const r = draft();
    if (!r) return;
    const payload: CreatorRecipe = {
      ...r,
      image: image() || "",
      country: r.country || "Custom",
      lang: r.lang || "en",
      collection: r.collection || "My Recipes",
    };
    const d = await api.importRecipe(payload);
    if (d.ok) {
      showToast("Recipe saved!");
      setDraft(null);
      push({ from: "ai", variant: "card", text: "✅ Saved!" });
      props.onOpenRecipe(d.id);
      props.onClose();
    } else {
      showToast(d.error || "Save failed");
    }
  }

  return (
    <>
      <div class="panel-overlay" classList={{ open: props.open }} onClick={props.onClose} aria-hidden="true" />
      <div class="side-panel creator" classList={{ open: props.open }} role="dialog" aria-label="Create recipe with AI" aria-modal="true">
        <div class="panel-header">
          <button type="button" class="btn-back" aria-label="Close" onClick={props.onClose}>
            <IconChevronLeft />
          </button>
          <h2>✨ Create Recipe</h2>
          <button type="button" class="icon-btn" title="New chat" onClick={reset}>
            <IconTrash size={15} />
          </button>
        </div>

        <div class="creator-messages" ref={scroller}>
          <For each={bubbles()}>
            {(b) => (
              <div class={`creator-msg ${b.from}${b.variant ? " " + b.variant : ""}`}>
                {b.text}
                <Show when={b.images}>
                  <div class="img-picker">
                    <For each={b.images}>
                      {(img) => (
                        <img
                          src={img.url} title={img.title || ""} alt=""
                          classList={{ selected: image() === img.url }}
                          onClick={() => setImage(img.url)}
                        />
                      )}
                    </For>
                  </div>
                </Show>
              </div>
            )}
          </For>
        </div>

        <div class="creator-actions">
          <button type="button" disabled={busy()} onClick={() => void send("Please generate the final recipe now.")}>
            📋 Generate Recipe
          </button>
          <button type="button" disabled={!draft()} onClick={() => void findImages()}>🖼 Find Image</button>
          <button type="button" class="save-btn" disabled={!draft()} onClick={() => void save()}>
            💾 Save Recipe
          </button>
        </div>

        <div class="creator-input">
          <input
            type="text" ref={input} placeholder="e.g. I have chicken, rice, and peppers…"
            disabled={busy()}
            onKeyDown={(e) => e.key === "Enter" && void send(e.currentTarget.value)}
          />
          <button type="button" disabled={busy()} onClick={() => void send(input.value)}>Send</button>
        </div>
      </div>
    </>
  );
}
