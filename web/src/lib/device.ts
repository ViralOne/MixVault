/** Thin wrappers around the device APIs cooking mode leans on. */

let wakeLock: WakeLockSentinel | null = null;

export async function requestWake() {
  try {
    if ("wakeLock" in navigator) wakeLock = await navigator.wakeLock.request("screen");
  } catch {
    /* denied or unsupported — cooking still works */
  }
}

export function releaseWake() {
  void wakeLock?.release();
  wakeLock = null;
}

export function vibrate(pattern: number | number[]) {
  try {
    navigator.vibrate?.(pattern);
  } catch {
    /* unsupported */
  }
}

export function beep() {
  try {
    const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    const ctx = new Ctx();
    const osc = ctx.createOscillator();
    osc.frequency.value = 800;
    osc.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.2);
  } catch {
    /* autoplay blocked */
  }
}

export function askNotificationPermission() {
  if ("Notification" in window && Notification.permission === "default") {
    void Notification.requestPermission();
  }
}

export function notify(title: string, body: string) {
  if ("Notification" in window && Notification.permission === "granted") {
    new Notification(title, { body, icon: "/favicon.svg" });
  }
}

export function speak(text: string) {
  try {
    speechSynthesis.speak(new SpeechSynthesisUtterance(text));
  } catch {
    /* unsupported */
  }
}

type SpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  start(): void;
  stop(): void;
  onresult: ((e: { results: { [i: number]: { [j: number]: { transcript: string } }; length: number } }) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
};

/** Continuous voice control: "next", "back", "repeat". */
export function startVoice(handlers: {
  next: () => void;
  back: () => void;
  repeat: () => void;
  onStop: () => void;
}): { stop: () => void } | null {
  const w = window as unknown as {
    SpeechRecognition?: new () => SpeechRecognitionLike;
    webkitSpeechRecognition?: new () => SpeechRecognitionLike;
  };
  const SR = w.SpeechRecognition || w.webkitSpeechRecognition;
  if (!SR) return null;
  let alive = true;
  const rec = new SR();
  rec.continuous = true;
  rec.interimResults = false;
  rec.onresult = (e) => {
    const t = e.results[e.results.length - 1][0].transcript.toLowerCase();
    if (t.includes("next") || t.includes("forward")) handlers.next();
    else if (t.includes("back") || t.includes("previous")) handlers.back();
    else if (t.includes("repeat")) handlers.repeat();
  };
  rec.onerror = () => {
    alive = false;
    handlers.onStop();
  };
  rec.onend = () => {
    if (alive) rec.start();
  };
  try {
    rec.start();
  } catch {
    return null;
  }
  return {
    stop: () => {
      alive = false;
      try {
        rec.stop();
      } catch {
        /* already stopped */
      }
    },
  };
}
