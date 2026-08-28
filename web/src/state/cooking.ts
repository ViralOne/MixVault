/** Cooking mode: step cursor, timer, wake lock, voice and cross-device resume. */
import { createSignal } from "solid-js";
import { api } from "../lib/api";
import { beep, notify, releaseWake, requestWake, speak, startVoice, vibrate } from "../lib/device";
import { parseStep } from "../lib/steps";
import type { Recipe } from "../lib/types";
import { pushHash, setView, view } from "./router";
import { slugify } from "../lib/format";

export const [cookRecipe, setCookRecipe] = createSignal<Recipe | null>(null);
export const [step, setStep] = createSignal(0);
export const [dir, setDir] = createSignal(1);
export const [remaining, setRemaining] = createSignal<number | null>(null);
export const [timerDone, setTimerDone] = createSignal(false);
export const [listening, setListening] = createSignal(false);

/** Server-backed "continue cooking" hint shown on the browse view. */
export const [resumeHint, setResumeHint] = createSignal<{ id: string; step: number; name: string; total: number } | null>(null);

let timer: ReturnType<typeof setInterval> | undefined;
let voice: { stop: () => void } | null = null;
let loggedCook = "";

export const totalSteps = () => cookRecipe()?.steps.length ?? 0;
export const isDone = () => step() >= totalSteps();

function clearTimer() {
  clearInterval(timer);
  timer = undefined;
}

function startTimer(secs: number) {
  clearTimer();
  setRemaining(secs);
  setTimerDone(false);
  timer = setInterval(() => {
    const next = (remaining() ?? 0) - 1;
    setRemaining(next);
    if (next <= 0) {
      clearTimer();
      setRemaining(0);
      setTimerDone(true);
      beep();
      vibrate([200, 100, 200]);
      const r = cookRecipe();
      if (r) notify("Timer done!", `${r.name} — Step ${step() + 1}`);
    }
  }, 1000);
}

function applyStep() {
  const r = cookRecipe();
  if (!r) return;
  const s = r.steps[step()];
  if (s === undefined) {
    setRemaining(null);
    return;
  }
  const meta = parseStep(s);
  if (meta.secs > 0) startTimer(meta.secs);
  else {
    clearTimer();
    setRemaining(null);
    setTimerDone(false);
  }
}

function persist() {
  const r = cookRecipe();
  if (r && view() === "cooking" && step() < r.steps.length) {
    localStorage.setItem("cookState", JSON.stringify({ id: r.id, step: step() }));
    void api.cookingStateSave(r.id, step());
  }
}

export function clearCookState() {
  localStorage.removeItem("cookState");
  void api.cookingStateSave(null);
  setResumeHint(null);
}

function logCooked(r: Recipe) {
  if (loggedCook === r.id) return;
  loggedCook = r.id;
  void api.markCooked(r.id);
}

export function startCooking(r: Recipe) {
  setCookRecipe(r);
  loggedCook = "";
  setStep(0);
  setDir(1);
  setView("cooking");
  applyStep();
  void requestWake();
  pushHash(`cook/${r.id}/0`);
  persist();
}

export function exitCooking() {
  clearTimer();
  stopVoice();
  releaseWake();
  setView("detail");
  localStorage.removeItem("cookState");
  const r = cookRecipe();
  if (r) pushHash(r.lang + "/" + slugify(r.name));
}

export function stepNav(delta: number) {
  const r = cookRecipe();
  if (!r) return;
  // Past the last step the "Done" button just leaves cooking mode.
  if (step() >= r.steps.length && delta > 0) {
    logCooked(r);
    exitCooking();
    return;
  }
  const next = Math.max(0, step() + delta);
  setDir(delta);
  setStep(next);
  vibrate(50);
  if (next >= r.steps.length) {
    clearTimer();
    setRemaining(null);
    logCooked(r);
    clearCookState();
  } else {
    applyStep();
    persist();
  }
  pushHash(`cook/${r.id}/${next}`);
}

/** Enter cooking mode directly at a step (hash route / resume banner). */
export async function resumeCooking(id: string, atStep: number) {
  let r = cookRecipe();
  if (!r || r.id !== id) {
    const fetched = await api.recipe(id);
    if (fetched.error || !fetched.id) {
      setView("browse");
      return;
    }
    r = fetched;
    setCookRecipe(fetched);
    loggedCook = "";
  }
  setStep(Math.min(atStep, r.steps.length));
  setDir(1);
  setView("cooking");
  applyStep();
  void requestWake();
  persist();
}

export async function loadResumeHint() {
  try {
    const d = await api.cookingStateGet();
    if (!d.recipe_id) {
      setResumeHint(null);
      return;
    }
    const r = await api.recipe(d.recipe_id);
    if (!r.name) return;
    setResumeHint({ id: d.recipe_id, step: d.step, name: r.name, total: r.steps.length });
  } catch {
    /* offline — no hint */
  }
}

export function toggleVoice() {
  if (voice) {
    stopVoice();
    return;
  }
  voice = startVoice({
    next: () => stepNav(1),
    back: () => stepNav(-1),
    repeat: () => {
      const r = cookRecipe();
      if (r) speak(r.steps[step()] ?? "");
    },
    onStop: () => {
      voice = null;
      setListening(false);
    },
  });
  setListening(!!voice);
}

export function stopVoice() {
  voice?.stop();
  voice = null;
  setListening(false);
}

export function onLeaveCooking() {
  clearTimer();
  stopVoice();
  releaseWake();
}
