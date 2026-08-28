/**
 * Hands-on step scenes — the animation shown when a step does not use the Thermomix.
 * Each scene mimics the real gesture (rocking knife, running tap, closing jar lid…)
 * so the cook can tell at a glance what the step is asking for.
 */
import { For, Show, type JSX } from "solid-js";
import type { ManualAction, StepMeta } from "../../lib/steps";

const Surface = () => <path class="ma-surface" d="M18 116 H162" />;

/* ── knife rocking on a board ── */
const Chop = () => (
  <>
    <Surface />
    <rect class="ma-board" x="30" y="96" width="120" height="14" rx="5" />
    <rect class="ma-board-edge" x="30" y="96" width="120" height="4" rx="2" />
    <circle class="ma-food ma-slice" cx="52" cy="89" r="6" />
    <circle class="ma-food ma-slice" cx="68" cy="89" r="6" style={{ "animation-delay": ".72s" }} />
    <circle class="ma-food ma-slice" cx="84" cy="89" r="6" style={{ "animation-delay": "1.44s" }} />
    <g class="ma-knife">
      <path class="ma-steel" d="M34 82 L48 70 L120 70 L120 82 Z" />
      <rect class="ma-handle" x="118" y="69" width="34" height="12" rx="6" />
      <rect class="ma-board-edge" x="120" y="73" width="30" height="2" rx="1" />
    </g>
  </>
);

/* ── tap running over produce ── */
const Wash = () => (
  <>
    <path d="M38 20 V42 H88" stroke="#90a4ae" stroke-width="7" fill="none" stroke-linecap="round" />
    <rect class="ma-steel-dark" x="84" y="42" width="9" height="11" rx="2" />
    <path class="ma-water-stroke ma-stream" d="M88.5 55 V88" />
    <path class="ma-steel" d="M52 90 h74 a37 37 0 0 1 -74 0 z" />
    <rect class="ma-steel-dark" x="50" y="86" width="78" height="6" rx="3" />
    <circle class="ma-food" cx="76" cy="96" r="9" />
    <circle class="ma-food" cx="98" cy="98" r="7" />
    <For each={[-14, -6, 7, 15]}>
      {(dx, i) => (
        <circle
          class="ma-water ma-splash" cx="88" cy="92" r={i() % 2 ? 2 : 2.6}
          style={{ "--dx": dx + "px", "animation-delay": i() * 0.27 + "s" }}
        />
      )}
    </For>
    <Surface />
  </>
);

/* ── oven preheating ── */
const Oven = (props: { meta: StepMeta }) => (
  <>
    <For each={[64, 88, 112]}>
      {(x, i) => (
        <path
          class="ma-heat-stroke ma-heat" d={`M${x} 26 q6 -7 12 0 q6 7 12 0`}
          style={{ "animation-delay": i() * 0.8 + "s" }}
        />
      )}
    </For>
    <rect class="ma-body" x="36" y="34" width="108" height="80" rx="8" />
    <path d="M36 54 H144" stroke="#444" stroke-width="2" />
    <circle cx="126" cy="44" r="7" fill="#3a3a3a" stroke="#555" stroke-width="1.5" />
    <line class="ma-dial" x1="126" y1="44" x2="126" y2="38.5" stroke="#ffb74d" stroke-width="2" stroke-linecap="round" />
    <rect x="48" y="62" width="84" height="44" rx="5" fill="#33241a" />
    <rect class="ma-oven-glow" x="48" y="62" width="84" height="44" rx="5" fill="#ff8a65" opacity=".55" />
    <path d="M56 96 H124" stroke="#ff7043" stroke-width="2" opacity=".5" />
    <Show when={props.meta.temp > 0}>
      <text class="ma-label" x="90" y="88" text-anchor="middle">{props.meta.temp}°C</text>
    </Show>
    <Surface />
  </>
);

/* ── fridge / freezer ── */
const Chill = () => (
  <>
    <rect class="ma-body" x="56" y="18" width="70" height="96" rx="8" />
    <path d="M56 54 H126" stroke="#444" stroke-width="2" />
    <rect x="116" y="32" width="4" height="14" rx="2" fill="#90a4ae" />
    <rect x="116" y="62" width="4" height="14" rx="2" fill="#90a4ae" />
    <rect class="ma-cold-pulse" x="60" y="58" width="62" height="52" rx="6" fill="#4fc3f7" />
    <For each={[[72, 62], [90, 60], [104, 64], [84, 66]]}>
      {([x, y], i) => (
        <g transform={`translate(${x} ${y})`}>
          <g class="ma-flake" style={{ "animation-delay": i() * 0.7 + "s" }}>
            <path
              d="M0 -4 V4 M-3.5 -2 L3.5 2 M3.5 -2 L-3.5 2"
              stroke="#b3e5fc" stroke-width="1.4" stroke-linecap="round" fill="none"
            />
          </g>
        </g>
      )}
    </For>
    <Surface />
  </>
);

/* ── colander tipping into a bowl ── */
const Drain = () => (
  <>
    <path class="ma-steel" d="M58 96 h64 a32 32 0 0 1 -64 0 z" />
    <rect class="ma-steel-dark" x="56" y="92" width="68" height="6" rx="3" />
    <g class="ma-colander">
      <path class="ma-steel-dark" d="M48 58 h84 a42 30 0 0 1 -84 0 z" />
      <ellipse class="ma-food" cx="90" cy="63" rx="30" ry="5" />
      <For each={[62, 76, 90, 104, 118]}>{(x) => <circle cx={x} cy="70" r="2" fill="#111" />}</For>
      <For each={[70, 84, 98, 112]}>{(x) => <circle cx={x} cy="78" r="1.8" fill="#111" />}</For>
    </g>
    <For each={[70, 84, 98, 110]}>
      {(x, i) => (
        <ellipse
          class="ma-water ma-fall" cx={x} cy="84" rx="1.8" ry="3.4"
          style={{ "animation-delay": i() * 0.22 + "s" }}
        />
      )}
    </For>
    <Surface />
  </>
);

/* ── whisking by hand ── */
const Whisk = () => (
  <>
    <g class="ma-whisk">
      <rect class="ma-handle" x="86" y="22" width="9" height="32" rx="4.5" />
      <path d="M90.5 54 q-13 14 0 30 q13 -16 0 -30" fill="none" stroke="#b0bec5" stroke-width="2.2" />
      <path d="M90.5 54 q-6 16 0 30 q6 -14 0 -30" fill="none" stroke="#90a4ae" stroke-width="2" />
    </g>
    <path class="ma-steel" d="M46 84 h88 a44 44 0 0 1 -88 0 z" />
    <rect class="ma-steel-dark" x="44" y="80" width="92" height="6" rx="3" />
    <ellipse class="ma-food-alt" cx="90" cy="88" rx="38" ry="7" />
    <path class="ma-swirl" d="M72 92 a18 7 0 0 0 36 0" fill="none" stroke="#ffcc80" stroke-width="2" />
    <Surface />
  </>
);

/* ── rolling out dough ── */
const Knead = () => (
  <>
    <ellipse class="ma-dough" cx="90" cy="106" rx="42" ry="12" fill="#f0dcb4" />
    <g class="ma-pin">
      <rect x="58" y="74" width="64" height="16" rx="8" fill="#d7a86e" />
      <rect class="ma-handle" x="44" y="79" width="16" height="6" rx="3" />
      <rect class="ma-handle" x="120" y="79" width="16" height="6" rx="3" />
      <path d="M74 76 V88 M90 76 V88 M106 76 V88" stroke="#c1935a" stroke-width="1.5" />
    </g>
    <Surface />
  </>
);

/* ── pan on the hob ── */
const Stove = () => (
  <>
    <For each={[70, 90, 108]}>
      {(x, i) => (
        <ellipse
          class="ma-wisp" cx={x} cy="64" rx="5" ry="7" fill="#eceff1"
          style={{ "animation-delay": i() * 0.85 + "s" }}
        />
      )}
    </For>
    <path class="ma-steel-dark" d="M46 82 h72 v6 a11 11 0 0 1 -11 11 H57 a11 11 0 0 1 -11 -11 z" />
    <rect class="ma-steel" x="43" y="78" width="78" height="5" rx="2.5" />
    <rect class="ma-handle" x="118" y="79" width="34" height="7" rx="3.5" />
    <ellipse class="ma-food" cx="82" cy="86" rx="20" ry="5" />
    <g>
      <path class="ma-flame" d="M68 112 q10 -26 22 0 q-11 12 -22 0" fill="#ff7043" />
      <path class="ma-flame" d="M92 112 q7 -18 15 0 q-7 9 -15 0" fill="#ff8a65" style={{ "animation-delay": ".14s" }} />
      <path class="ma-flame" d="M76 112 q6 -15 12 0 q-6 8 -12 0" fill="#ffca28" style={{ "animation-delay": ".21s" }} />
    </g>
    <path class="ma-surface" d="M56 116 H124" />
  </>
);

/* ── pouring into a tin ── */
const Fill = () => (
  <>
    <path class="ma-steel" d="M102 74 h50 l-7 36 h-36 z" />
    <path class="ma-food-alt ma-level" d="M105 88 h44 l-5 20 h-34 z" />
    <g class="ma-jug">
      <path class="ma-glass" d="M24 52 h34 v28 a10 10 0 0 1 -10 10 H34 a10 10 0 0 1 -10 -10 z" />
      <path class="ma-glass" d="M58 56 l14 5 -14 7" />
      <path d="M24 60 a11 11 0 0 0 -13 11" stroke="#90a4ae" stroke-width="3" fill="none" />
      <rect x="28" y="66" width="26" height="20" rx="4" fill="#ffb74d" opacity=".65" />
    </g>
    <path
      class="ma-pour-stream" d="M74 66 q20 8 28 26"
      fill="none" stroke="#ffb74d" stroke-width="4.5" stroke-linecap="round"
    />
    <Surface />
  </>
);

/* ── lining / greasing a tin ── */
const Tray = () => (
  <>
    <g class="ma-brush">
      <rect class="ma-handle" x="86" y="30" width="8" height="26" rx="4" />
      <path d="M84 56 h12 l-2 12 h-8 z" fill="#ffcc80" />
    </g>
    <g class="ma-paper">
      <rect x="44" y="70" width="92" height="22" rx="3" fill="#f5ead6" opacity=".92" />
      <path d="M44 76 H136" stroke="#e0d3ba" stroke-width="1.5" />
    </g>
    <rect class="ma-steel-dark" x="32" y="86" width="116" height="24" rx="5" />
    <rect class="ma-steel" x="32" y="86" width="116" height="6" rx="3" />
    <Surface />
  </>
);

/* ── covered bowl resting, clock ticking ── */
const Rest = () => (
  <>
    <For each={["z", "z", "z"]}>
      {(z, i) => (
        <g transform={`translate(${40 + i() * 8} ${56 - i() * 6})`}>
          <text
            class="ma-zzz" fill="#78909c" font-size={String(11 + i() * 3)} font-weight="700"
            style={{ "animation-delay": i() + "s" }}
          >
            {z}
          </text>
        </g>
      )}
    </For>
    <path class="ma-steel" d="M52 88 h76 a38 38 0 0 1 -76 0 z" />
    <path class="ma-steel-dark" d="M50 88 a41 26 0 0 1 80 0 z" />
    <circle class="ma-handle" cx="90" cy="60" r="5" />
    <circle cx="144" cy="42" r="17" fill="#1c1c1c" stroke="#444" stroke-width="2" />
    <For each={[0, 90, 180, 270]}>
      {(a) => {
        const rad = (a * Math.PI) / 180;
        return (
          <circle cx={144 + 12 * Math.sin(rad)} cy={42 - 12 * Math.cos(rad)} r="1.2" fill="#666" />
        );
      }}
    </For>
    <g class="ma-clock-hand">
      <rect x="143" y="30" width="2" height="12" rx="1" fill="#ffb74d" />
    </g>
    <Surface />
  </>
);

/* ── plating up ── */
const Serve = () => (
  <>
    <For each={[74, 90, 106]}>
      {(x, i) => (
        <ellipse
          class="ma-wisp" cx={x} cy="56" rx="5" ry="8" fill="#eceff1"
          style={{ "animation-delay": i() * 0.85 + "s" }}
        />
      )}
    </For>
    <For each={[70, 84, 98, 110]}>
      {(x, i) => (
        <rect
          class="ma-sprinkle" x={x} y="60" width="2.4" height="5" rx="1.2"
          fill={i() % 2 ? "#9ccc65" : "#aed581"}
          style={{ "animation-delay": i() * 0.4 + "s" }}
        />
      )}
    </For>
    <path class="ma-food-alt" d="M62 96 q28 -28 56 0 z" />
    <circle cx="82" cy="88" r="2.6" fill="#7cb342" />
    <circle cx="98" cy="84" r="2.2" fill="#7cb342" />
    <ellipse cx="90" cy="100" rx="52" ry="11" fill="#cfd8dc" />
    <ellipse cx="90" cy="98" rx="38" ry="7" fill="#eceff1" />
    <rect class="ma-steel" x="20" y="78" width="3" height="32" rx="1.5" />
    <path class="ma-steel" d="M154 78 v14 a3 3 0 0 1 -6 0 v-14" />
    <rect class="ma-steel" x="150" y="92" width="3" height="18" rx="1.5" />
    <Surface />
  </>
);

/* ── sealing a jar ── */
const Store = () => (
  <>
    <g class="ma-lid">
      <rect class="ma-steel-dark" x="58" y="40" width="64" height="13" rx="4" />
      <rect class="ma-steel" x="58" y="40" width="64" height="4" rx="2" />
    </g>
    <g class="ma-seal">
      <path d="M128 48 l8 -6 M128 56 l9 0 M126 40 l6 -8" stroke="#ffd54f" stroke-width="2" stroke-linecap="round" fill="none" />
    </g>
    <rect class="ma-glass" x="62" y="54" width="56" height="58" rx="9" />
    <rect x="67" y="74" width="46" height="34" rx="7" fill="#ffb74d" opacity=".75" />
    <rect x="72" y="82" width="16" height="4" rx="2" fill="#fff" opacity=".25" />
    <Surface />
  </>
);

/* ── generic hands-on prep ── */
const Prep = () => (
  <>
    <circle class="ma-food ma-drop-in" cx="72" cy="62" r="7" />
    <circle class="ma-food-alt ma-drop-in" cx="90" cy="56" r="6" style={{ "animation-delay": ".55s" }} />
    <circle class="ma-food ma-drop-in" cx="108" cy="62" r="7.5" style={{ "animation-delay": "1.1s" }} />
    <path class="ma-steel" d="M46 84 h88 a44 44 0 0 1 -88 0 z" />
    <rect class="ma-steel-dark" x="44" y="80" width="92" height="6" rx="3" />
    <Surface />
  </>
);

const SCENES: Record<ManualAction, (props: { meta: StepMeta }) => JSX.Element> = {
  chop: Chop,
  wash: Wash,
  oven: Oven,
  chill: Chill,
  drain: Drain,
  whisk: Whisk,
  knead: Knead,
  stove: Stove,
  fill: Fill,
  tray: Tray,
  rest: Rest,
  serve: Serve,
  store: Store,
  prep: Prep,
};

export default function ManualScene(props: { meta: StepMeta }) {
  const Scene = () => SCENES[props.meta.action] ?? Prep;
  return (
    <div class="manual-anim">
      <svg viewBox="0 0 180 130" role="img" aria-label={`${props.meta.action} step illustration`}>
        {Scene()({ meta: props.meta })}
      </svg>
    </div>
  );
}
