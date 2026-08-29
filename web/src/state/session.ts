/** Who the browser is signed in as — the caller's own vault, nothing else. */
import { createSignal } from "solid-js";
import { api } from "../lib/api";
import type { Session } from "../lib/types";

export const [session, setSession] = createSignal<Session | null>(null);

export async function loadSession() {
  try {
    setSession(await api.session());
  } catch {
    /* offline — leave the vault controls hidden */
  }
}

/** Drop the session cookie and land back on the access-key page. */
export async function signOut() {
  await api.logout();
  location.replace("/");
}
