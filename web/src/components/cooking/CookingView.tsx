import { For, Show, createMemo, onCleanup, onMount } from "solid-js";
import { fmtSecs } from "../../lib/format";
import { ACTION_LABELS, type ManualAction, parseStep } from "../../lib/steps";
import {
  cookRecipe, dir, exitCooking, isDone, listening, remaining, step, stepNav, timerDone,
  toggleVoice, totalSteps,
} from "../../state/cooking";
import {
  IconBowl, IconChevronLeft, IconDrop, IconFilter, IconJar, IconKnife, IconMachine, IconOven,
  IconPan, IconPlate, IconPour, IconRoll, IconSnow, IconTin, IconWhisk, IconClock,
} from "../Icons";
import ManualScene from "./ManualScene";
import ThermomixScene from "./ThermomixScene";

const ACTION_ICONS: Record<ManualAction, (p: { size?: number }) => ReturnType<typeof IconKnife>> = {
  chop: IconKnife, wash: IconDrop, oven: IconOven, chill: IconSnow, drain: IconFilter,
  whisk: IconWhisk, knead: IconRoll, stove: IconPan, fill: IconPour, tray: IconTin,
  rest: IconClock, serve: IconPlate, store: IconJar, prep: IconBowl,
};

function DoneScreen(props: { name: string }) {
  const colors = ["#4caf50", "#66bb6a", "#81c784", "#fff", "#a5d6a7"];
  const confetti = Array.from({ length: 20 }, (_, i) => {
    const a = Math.random() * Math.PI * 2;
    const d = 40 + Math.random() * 60;
    return {
      cx: Math.cos(a) * d + "px",
      cy: Math.sin(a) * d + "px",
      color: colors[i % colors.length],
      delay: Math.random() * 0.3 + "s",
    };
  });
  return (
    <div class="done-screen">
      <div class="done-anim">
        <svg class="done-check-svg" viewBox="0 0 100 100" aria-hidden="true">
          <circle class="done-circle" cx="50" cy="50" r="45" transform="rotate(-90 50 50)" />
          <polyline class="done-check" points="30,52 44,65 70,38" />
        </svg>
        <div class="confetti-wrap">
          <For each={confetti}>
            {(c) => (
              <div
                class="confetti"
                style={{ "--cx": c.cx, "--cy": c.cy, background: c.color, "animation-delay": c.delay }}
              />
            )}
          </For>
        </div>
      </div>
      <h2>Bon Appétit!</h2>
      <p>{props.name} is ready.</p>
    </div>
  );
}

export default function CookingView() {
  const meta = createMemo(() => {
    const r = cookRecipe();
    const s = r?.steps[step()];
    return s ? parseStep(s) : null;
  });
  const progress = () => (totalSteps() > 0 ? step() / totalSteps() : 0);

  const onKey = (e: KeyboardEvent) => {
    if (e.key === "ArrowRight" || e.key === "ArrowDown") {
      e.preventDefault();
      stepNav(1);
    } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
      e.preventDefault();
      stepNav(-1);
    }
  };

  let touchX = 0;
  const onTouchStart = (e: TouchEvent) => (touchX = e.touches[0].clientX);
  const onTouchEnd = (e: TouchEvent) => {
    const d = e.changedTouches[0].clientX - touchX;
    if (Math.abs(d) > 60) stepNav(d > 0 ? -1 : 1);
  };

  onMount(() => {
    addEventListener("keydown", onKey);
    onCleanup(() => removeEventListener("keydown", onKey));
  });

  return (
    <Show when={cookRecipe()}>
      {(r) => (
        <>
          <div class="cook-header">
            <button type="button" class="btn-back" aria-label="Exit cooking" onClick={exitCooking}>
              <IconChevronLeft />
            </button>
            <h1>{r().name}</h1>
            <button
              type="button" class="mic-btn" classList={{ listening: listening() }}
              title="Voice control" aria-pressed={listening()} onClick={toggleVoice}
            >
              🎤
            </button>
            <span class="awake"><span class="awake-dot" />ON</span>
          </div>

          <div class="progress-bar">
            <For each={r().steps}>
              {(_, i) => (
                <div
                  class="progress-seg"
                  classList={{ done: i() < step(), active: i() === step() }}
                />
              )}
            </For>
          </div>

          <div
            class="step-content"
            onTouchStart={onTouchStart}
            onTouchEnd={onTouchEnd}
          >
            <Show when={!isDone()} fallback={<DoneScreen name={r().name} />}>
              <div class={`step-inner ${dir() >= 0 ? "slide-left" : "slide-right"}`}>
                <Show when={meta()}>
                  {(m) => (
                    <>
                      <div class="mode-row">
                        <Show
                          when={m().mode === "manual"}
                          fallback={
                            <span class="mode-chip tm"><IconMachine size={13} />Thermomix</span>
                          }
                        >
                          {(() => {
                            const Icon = ACTION_ICONS[m().action];
                            return (
                              <span class="mode-chip manual">
                                <Icon size={13} />
                                {ACTION_LABELS[m().action]} · by hand
                              </span>
                            );
                          })()}
                          <For each={m().actions.slice(1, 3)}>
                            {(a) => {
                              const Icon = ACTION_ICONS[a];
                              return (
                                <span class="extra-chip">
                                  <Icon size={12} />
                                  {ACTION_LABELS[a]}
                                </span>
                              );
                            }}
                          </For>
                        </Show>
                      </div>

                      <Show
                        when={m().mode === "manual"}
                        fallback={<ThermomixScene meta={m()} step={step()} progress={progress()} />}
                      >
                        <ManualScene meta={m()} />
                      </Show>

                      <Show when={remaining() !== null}>
                        <div class="timer-display">
                          <div class="timer-time" classList={{ urgent: (remaining() ?? 0) <= 10 }}>
                            {fmtSecs(Math.max(0, remaining() ?? 0))}
                          </div>
                          <div class="label">remaining</div>
                        </div>
                      </Show>
                    </>
                  )}
                </Show>

                <div class="step-label">Step {step() + 1} of {totalSteps()}</div>
                <div class="step-text">{r().steps[step()]}</div>
              </div>
            </Show>
          </div>

          <div class="step-nav">
            <button type="button" class="step-btn step-prev" disabled={step() <= 0} onClick={() => stepNav(-1)}>
              Previous
            </button>
            <button
              type="button" class="step-btn step-next" classList={{ "pulse-alert": timerDone() }}
              onClick={() => stepNav(1)}
            >
              {isDone() ? "Done" : step() === totalSteps() - 1 ? "Finish" : "Next →"}
            </button>
          </div>
        </>
      )}
    </Show>
  );
}
