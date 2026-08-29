import { Show, createSignal, type JSX } from "solid-js";
import { api } from "../lib/api";
import { session, signOut } from "../state/session";
import { IconPlus, IconCheck } from "./Icons";
import { showToast } from "../state/toast";
import { load as loadShopping } from "../state/shopping";
import { IconDownload, IconMoon, IconWand } from "./Icons";

function Overlay(props: { onClose: () => void; children: JSX.Element }) {
  return (
    <div
      class="modal-overlay"
      onClick={(e) => e.target === e.currentTarget && props.onClose()}
      role="presentation"
    >
      <div class="modal" role="dialog" aria-modal="true">{props.children}</div>
    </div>
  );
}

export function ImportModal(props: { onClose: () => void; onOpenRecipe: (id: string) => void }) {
  const [url, setUrl] = createSignal("");
  const [status, setStatus] = createSignal<JSX.Element>("");
  const [busy, setBusy] = createSignal(false);

  async function run() {
    const u = url().trim();
    if (!u) return;
    setBusy(true);
    setStatus("⏳ Importing…");
    try {
      const d = await api.importCookidoo(u);
      if (d.error) setStatus("❌ " + d.error);
      else {
        const open = () => {
          props.onClose();
          props.onOpenRecipe(d.id);
        };
        setStatus(
          <>
            {d.exists ? "Already exists!" : `✅ Imported "${d.name}" (${d.steps_generated} AI steps).`}{" "}
            <a href="#" onClick={(e) => { e.preventDefault(); open(); }}>View →</a>
          </>,
        );
      }
    } catch {
      setStatus("❌ Network error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Overlay onClose={props.onClose}>
      <h3>📥 Import from Cookidoo</h3>
      <input
        type="url" placeholder="Paste Cookidoo recipe URL…" value={url()}
        onInput={(e) => setUrl(e.currentTarget.value)} autofocus
      />
      <div class="status-line">{status()}</div>
      <div class="modal-btns">
        <button type="button" class="btn-cancel" onClick={props.onClose}>Cancel</button>
        <button type="button" class="btn-primary" disabled={busy()} onClick={() => void run()}>Import</button>
      </div>
    </Overlay>
  );
}

export function SettingsModal(props: {
  onClose: () => void;
  onOpenCreator: () => void;
  onOpenImport: () => void;
  onToggleDark: () => void;
  isDark: boolean;
}) {
  const [status, setStatus] = createSignal("");
  const [newKey, setNewKey] = createSignal("");
  const [copied, setCopied] = createSignal(false);
  const [minting, setMinting] = createSignal(false);

  async function createVault() {
    const label = prompt("Who is this vault for? (a name, just for your reference)");
    if (label === null) return;
    setMinting(true);
    try {
      const d = await api.createVault(label);
      if (!d.ok || !d.key) {
        showToast(d.error || "Could not create a vault");
        return;
      }
      setNewKey(d.key);
      setCopied(false);
    } finally {
      setMinting(false);
    }
  }

  async function copyKey() {
    await navigator.clipboard.writeText(newKey());
    setCopied(true);
  }

  async function restore(file: File | undefined) {
    if (!file) return;
    setStatus("Restoring…");
    try {
      const data = JSON.parse(await file.text());
      await api.restoreBackup(data);
      setStatus("✅ Restored successfully!");
      await loadShopping();
      showToast("Backup restored");
    } catch {
      setStatus("❌ Invalid backup file");
    }
  }

  return (
    <Overlay onClose={props.onClose}>
      <h3>Settings</h3>
      <div class="settings-stack">
        <button type="button" class="btn-primary" onClick={() => { props.onClose(); props.onOpenCreator(); }}>
          <IconWand size={16} /> Create Recipe with AI
        </button>
        <button type="button" class="btn-primary" onClick={() => { props.onClose(); props.onOpenImport(); }}>
          <IconDownload size={16} /> Import from URL
        </button>
        <button type="button" class="btn-neutral" onClick={props.onToggleDark}>
          <IconMoon size={16} /> {props.isDark ? "Switch to light mode" : "Switch to dark mode"}
        </button>
      </div>
      <hr />
      <div class="settings-stack">
        <button
          type="button" class="btn-neutral"
          onClick={() => {
            window.open("/api/export?format=json");
            showToast("Backup downloading…");
          }}
        >
          <IconDownload size={16} /> Download Backup
        </button>
      </div>
      <label class="field-label" for="restore-file">Restore from backup</label>
      <input
        id="restore-file" type="file" accept=".json"
        onChange={(e) => void restore(e.currentTarget.files?.[0])}
      />
      <div class="status-line">{status()}</div>
      <Show when={session()?.multi_user}>
        <hr />
        <div class="settings-stack">
          <button type="button" class="btn-neutral" disabled={minting()} onClick={() => void createVault()}>
            <IconPlus size={16} /> {minting() ? "Creating…" : "Create a vault key"}
          </button>
        </div>
        <Show when={newKey()}>
          <div class="keybox">{newKey()}</div>
          <div class="keybox-actions">
            <button type="button" class="btn-primary" onClick={() => void copyKey()}>
              <Show when={copied()} fallback="Copy key"><IconCheck size={14} /> Copied</Show>
            </button>
            <button type="button" class="btn-cancel" onClick={() => setNewKey("")}>Done</button>
          </div>
          <p class="keybox-warn">
            Shown once — it cannot be recovered. Whoever holds it opens that vault,
            so pass it on privately.
          </p>
        </Show>
        <div class="vault-row">
          <div>
            <div class="vault-label">{session()!.label || "This vault"}</div>
            <div class="vault-hint">Only this vault's data is visible here.</div>
          </div>
          <button type="button" class="btn-cancel" onClick={() => void signOut()}>Sign out</button>
        </div>
      </Show>
      <div class="modal-btns">
        <button type="button" class="btn-cancel" onClick={props.onClose}>Close</button>
      </div>
    </Overlay>
  );
}
