import type { JSX } from "solid-js";

type P = { class?: string; size?: number };

const svg = (children: JSX.Element, p: P, opts: { fill?: boolean; width?: number } = {}) => (
  <svg
    class={p.class}
    width={p.size ?? 18}
    height={p.size ?? 18}
    viewBox="0 0 24 24"
    fill={opts.fill ? "currentColor" : "none"}
    stroke={opts.fill ? "none" : "currentColor"}
    stroke-width={opts.width ?? 2}
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    {children}
  </svg>
);

export const IconLogo = (p: P) => svg(<><circle cx="12" cy="12" r="10" /><path d="M8 12l2 2 4-4" /></>, p);
export const IconSearch = (p: P) => svg(<><circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" /></>, p);
export const IconSparkles = (p: P) => svg(<><path d="M12 2L2 7l10 5 10-5-10-5z" /><path d="M2 17l10 5 10-5" /><path d="M2 12l10 5 10-5" /></>, p);
export const IconDice = (p: P) => svg(<><rect x="2" y="2" width="20" height="20" rx="3" /><circle cx="8" cy="8" r="1.5" fill="currentColor" /><circle cx="16" cy="16" r="1.5" fill="currentColor" /><circle cx="12" cy="12" r="1.5" fill="currentColor" /></>, p);
export const IconCart = (p: P) => svg(<><circle cx="9" cy="21" r="1" /><circle cx="20" cy="21" r="1" /><path d="M1 1h4l2.68 13.39a2 2 0 002 1.61h9.72a2 2 0 002-1.61L23 6H6" /></>, p);
export const IconMore = (p: P) => svg(<><circle cx="12" cy="12" r="1" /><circle cx="12" cy="5" r="1" /><circle cx="12" cy="19" r="1" /></>, p);
export const IconClock = (p: P) => svg(<><circle cx="12" cy="12" r="10" /><path d="M12 6v6l4 2" /></>, p);
export const IconHistory = (p: P) => svg(<><path d="M3 3v5h5" /><path d="M3.05 13A9 9 0 106 5.3L3 8" /><path d="M12 7v5l4 2" /></>, p);
export const IconPlay = (p: P) => svg(<polygon points="5 3 19 12 5 21 5 3" />, p, { fill: true });
export const IconChevronLeft = (p: P) => svg(<path d="M15 18l-6-6 6-6" />, p, { width: 2.5 });
export const IconChevronRight = (p: P) => svg(<path d="M9 18l6-6-6-6" />, p, { width: 2.5 });
export const IconChevronUp = (p: P) => svg(<polyline points="18 15 12 9 6 15" />, p, { width: 2.5 });
export const IconArrowRight = (p: P) => svg(<path d="M5 12h14M13 6l6 6-6 6" />, p);
export const IconPlus = (p: P) => svg(<><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></>, p);
export const IconEdit = (p: P) => svg(<><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" /></>, p);
export const IconShare = (p: P) => svg(<><circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" /><line x1="8.59" y1="13.51" x2="15.42" y2="17.49" /><line x1="15.41" y1="6.51" x2="8.59" y2="10.49" /></>, p);
export const IconTrash = (p: P) => svg(<><polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" /></>, p);
export const IconCheck = (p: P) => svg(<polyline points="20 6 9 17 4 12" />, p, { width: 2.5 });
export const IconSwap = (p: P) => svg(<><polyline points="17 1 21 5 17 9" /><path d="M3 11V9a4 4 0 014-4h14" /><polyline points="7 23 3 19 7 15" /><path d="M21 13v2a4 4 0 01-4 4H3" /></>, p);
export const IconDownload = (p: P) => svg(<><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" /></>, p);
export const IconMoon = (p: P) => svg(<path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />, p);
export const IconSun = (p: P) => svg(<><circle cx="12" cy="12" r="5" /><line x1="12" y1="1" x2="12" y2="3" /><line x1="12" y1="21" x2="12" y2="23" /><line x1="4.22" y1="4.22" x2="5.64" y2="5.64" /><line x1="18.36" y1="18.36" x2="19.78" y2="19.78" /><line x1="1" y1="12" x2="3" y2="12" /><line x1="21" y1="12" x2="23" y2="12" /><line x1="4.22" y1="19.78" x2="5.64" y2="18.36" /><line x1="18.36" y1="5.64" x2="19.78" y2="4.22" /></>, p);
export const IconWand = (p: P) => svg(<><path d="M12 3v18M3 12h18" /><circle cx="12" cy="12" r="3" /></>, p);
export const IconGlobe = (p: P) => svg(<><circle cx="12" cy="12" r="10" /><path d="M2 12h20M12 2a15 15 0 010 20 15 15 0 010-20" /></>, p);

/* Hands-on action glyphs, used by the step chips */
export const IconKnife = (p: P) => svg(<><path d="M4 20l7-7" /><path d="M14 3l7 7-6 2-3-3z" /></>, p);
export const IconOven = (p: P) => svg(<><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M3 9h18" /><circle cx="7" cy="6" r="1" fill="currentColor" /><rect x="6" y="12" width="12" height="6" rx="1" /></>, p);
export const IconSnow = (p: P) => svg(<><path d="M12 2v20M4 6l16 12M20 6L4 18" /></>, p);
export const IconDrop = (p: P) => svg(<path d="M12 2s6 7 6 11a6 6 0 01-12 0c0-4 6-11 6-11z" />, p);
export const IconPan = (p: P) => svg(<><path d="M3 11h13v2a5 5 0 01-5 5H8a5 5 0 01-5-5z" /><path d="M16 13h5" /></>, p);
export const IconFilter = (p: P) => svg(<><path d="M5 4h14l-5 7v6l-4 2v-8z" /></>, p);
export const IconWhisk = (p: P) => svg(<><path d="M12 3v8" /><path d="M9 11h6l-1 8H10z" /></>, p);
export const IconRoll = (p: P) => svg(<><rect x="4" y="9" width="16" height="6" rx="3" /><path d="M2 12h2M20 12h2" /></>, p);
export const IconTin = (p: P) => svg(<><path d="M4 8h16l-2 11H6z" /><path d="M3 8l2-3h14l2 3" /></>, p);
export const IconPour = (p: P) => svg(<><path d="M4 6h8v6a4 4 0 01-4 4H8a4 4 0 01-4-4z" /><path d="M12 8h3a2 2 0 010 4h-3" /><path d="M17 16v4" /></>, p);
export const IconPlate = (p: P) => svg(<><ellipse cx="12" cy="15" rx="9" ry="4" /><path d="M8 9c1-2 7-2 8 0" /></>, p);
export const IconJar = (p: P) => svg(<><rect x="6" y="7" width="12" height="14" rx="2" /><path d="M8 7V4h8v3" /></>, p);
export const IconBowl = (p: P) => svg(<><path d="M3 11h18a9 9 0 01-18 0z" /><path d="M8 7c0-2 8-2 8 0" /></>, p);
export const IconMachine = (p: P) => svg(<><path d="M5 4h14l-1 6H6z" /><path d="M7 10l1 9h8l1-9" /><path d="M12 4v6" /></>, p);
