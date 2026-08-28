import { createSignal } from "solid-js";
import { api } from "../lib/api";
import { openRecipe, recipe, setEditing } from "../state/recipe";
import { showToast } from "../state/toast";

export default function EditRecipeForm() {
  const r = recipe()!;
  const [name, setName] = createSignal(r.name);
  const [image, setImage] = createSignal(r.image || "");
  const [yieldText, setYieldText] = createSignal(r.yield || "");
  const [ings, setIngs] = createSignal(r.ingredients.join("\n"));
  const [steps, setSteps] = createSignal(r.steps.join("\n"));
  const [saving, setSaving] = createSignal(false);

  async function save() {
    setSaving(true);
    try {
      await api.editRecipe(r.id, {
        name: name().trim(),
        image: image().trim(),
        yield: yieldText().trim(),
        ingredients: ings().split("\n").filter((l) => l.trim()),
        steps: steps().split("\n").filter((l) => l.trim()),
      });
      showToast("Recipe updated");
      setEditing(false);
      await openRecipe(r.id, { skipHash: true });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div class="edit-form">
      <h2>Edit Recipe</h2>

      <label for="edit-name">Name</label>
      <input id="edit-name" value={name()} onInput={(e) => setName(e.currentTarget.value)} />

      <label for="edit-image">Image URL</label>
      <input id="edit-image" value={image()} onInput={(e) => setImage(e.currentTarget.value)} />

      <label for="edit-yield">Yield</label>
      <input id="edit-yield" value={yieldText()} onInput={(e) => setYieldText(e.currentTarget.value)} />

      <label for="edit-ings">Ingredients (one per line)</label>
      <textarea id="edit-ings" rows="8" value={ings()} onInput={(e) => setIngs(e.currentTarget.value)} />

      <label for="edit-steps">Steps (one per line)</label>
      <textarea id="edit-steps" rows="10" value={steps()} onInput={(e) => setSteps(e.currentTarget.value)} />

      <button type="button" class="save" disabled={saving()} onClick={() => void save()}>
        {saving() ? "Saving…" : "Save Changes"}
      </button>
    </div>
  );
}
