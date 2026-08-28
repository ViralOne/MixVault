import { For, Show, createSignal, onCleanup, onMount } from "solid-js";
import type { StepMeta } from "../../lib/steps";

/** Counts up to the target weight the way the machine's scale does. */
function WeightCounter(props: { target: number }) {
  const [value, setValue] = createSignal(0);
  onMount(() => {
    const inc = Math.max(1, Math.floor(props.target / 30));
    const iv = setInterval(() => {
      setValue((v) => {
        const next = Math.min(props.target, v + inc);
        if (next >= props.target) clearInterval(iv);
        return next;
      });
    }, 30);
    onCleanup(() => clearInterval(iv));
  });
  return <div class="weight-display">{value()}</div>;
}

export default function ThermomixScene(props: { meta: StepMeta; step: number; progress: number }) {
  const CIRC = 2 * Math.PI * 54;
  const bladeSpeed = () => (props.meta.isChop ? "0.8s" : props.meta.isCook ? "4s" : "2s");
  const tempHeight = () => (props.meta.temp ? Math.min(100, props.meta.temp / 2) + "%" : "0%");
  const speedAngle = () => (props.meta.speed ? (props.meta.speed / 10) * 270 - 135 : -135);

  return (
    <div class="cook-anim">
      <Show when={props.meta.temp > 0}>
        <div class="anim-side">
          <div class="label">Temp</div>
          <div class="temp-gauge">
            <div class="temp-fill" style={{ height: tempHeight() }} />
          </div>
          <div class="value">{props.meta.temp}°</div>
        </div>
      </Show>

      <div class="anim-center">
        <Show when={props.meta.isCook}>
          <div class="steam-wrap">
            <div class="steam" /><div class="steam" /><div class="steam" /><div class="steam" />
          </div>
        </Show>
        <Show when={props.meta.isPour}>
          <div class="pour-wrap">
            <div class="drop" /><div class="drop" /><div class="drop" />
          </div>
        </Show>

        <svg class="ring-svg" viewBox="0 0 120 120" aria-hidden="true">
          <circle class="ring-bg" cx="60" cy="60" r="54" />
          <circle
            class="ring-fg" cx="60" cy="60" r="54"
            stroke-dasharray={String(CIRC)} stroke-dashoffset={String(CIRC - CIRC * props.progress)}
          />
        </svg>

        <div class="blade-wrap">
          <svg class="blade-svg" style={{ "animation-duration": bladeSpeed() }} viewBox="0 0 64 64" aria-hidden="true">
            <circle cx="32" cy="32" r="6" fill="#555" />
            <circle cx="32" cy="32" r="3" fill="#333" />
            <For each={[0, 60, 120, 180, 240, 300]}>
              {(a) => (
                <path
                  d="M32 26C32 26 38 14 32 8C26 14 32 26 32 26Z"
                  fill={a % 120 ? "#555" : "#666"}
                  transform={`rotate(${a} 32 32)`}
                />
              )}
            </For>
          </svg>
        </div>

        <div class="step-circle">{props.step + 1}</div>
      </div>

      <Show when={props.meta.speed > 0}>
        <div class="anim-side">
          <div class="label">Speed</div>
          <div class="speed-dial">
            <svg viewBox="0 0 60 60" aria-hidden="true">
              <circle cx="30" cy="30" r="26" fill="none" stroke="#333" stroke-width="3" />
              <For each={[1, 3, 5, 7, 10]}>
                {(n) => {
                  const rad = ((n / 10) * 270 - 135) * (Math.PI / 180);
                  return (
                    <text
                      x={30 + 22 * Math.cos(rad)} y={30 + 22 * Math.sin(rad)}
                      fill="#555" font-size="7" text-anchor="middle" dominant-baseline="middle"
                    >
                      {n}
                    </text>
                  );
                }}
              </For>
              <line
                class="speed-needle" x1="30" y1="30"
                x2={30 + 20 * Math.cos((speedAngle() * Math.PI) / 180)}
                y2={30 + 20 * Math.sin((speedAngle() * Math.PI) / 180)}
                stroke="#66bb6a" stroke-width="2" stroke-linecap="round"
              />
              <circle cx="30" cy="30" r="3" fill="#66bb6a" />
            </svg>
          </div>
          <div class="value">{props.meta.speed}</div>
        </div>
      </Show>

      <Show when={props.meta.weight > 0}>
        <div class="anim-side">
          <div class="label">Weight</div>
          <WeightCounter target={props.meta.weight} />
          <div class="label">grams</div>
        </div>
      </Show>
    </div>
  );
}
