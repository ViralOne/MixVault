/**
 * Step analysis for cooking mode.
 *
 * Recipes mix two very different kinds of instruction:
 *   1. Thermomix steps  — "5 Sek./Stufe 5 zerkleinern", "chop 10 sec/speed 5"
 *   2. Hands-on steps   — "Backofen vorheizen", "in 16 Scheiben schneiden", "servieren"
 *
 * The machine steps get the bowl/blade animation; the hands-on ones get their own
 * scene (cutting board, tap, oven, fridge …). The recipe corpus is multilingual,
 * so every keyword group carries the common EN/DE/ES/FR/IT/RO/PT/NL/PL/CS/TR terms.
 */

export type StepMode = "thermomix" | "manual";

export type ManualAction =
  | "oven" | "chill" | "stove" | "drain" | "wash" | "chop" | "knead"
  | "whisk" | "tray" | "fill" | "serve" | "rest" | "store" | "prep";

export interface StepMeta {
  mode: StepMode;
  /** Primary hands-on action (always set for manual steps). */
  action: ManualAction;
  /** Every detected hands-on action, most defining first. */
  actions: ManualAction[];
  temp: number;
  speed: number;
  secs: number;
  weight: number;
  isPour: boolean;
  isChop: boolean;
  isCook: boolean;
}

/**
 * Machine markers. Two families, because the corpus is inconsistent:
 * `TM_PARAM` catches "speed 5" / "Stufe 5" style settings (some rows ship an empty
 * value, e.g. "1 min./100°C//vel. ."), `TM_VOCAB` catches words that only ever
 * appear in a machine instruction — the bowl, the accessories, the brand names.
 */
export const TM_PARAM =
  /\b(?:speed|vel|vitez[aă]|stufe|velocidad|velocit[àa]|vitesse|snelheid|hastighed|hastighet|sebesség|fokozat|stopień|prędkoś\w*|rychlost|hız|obr|obrot\w*)\b\.?\s*[\d.,/]*/i;

export const TM_VOCAB = new RegExp(
  [
    String.raw`\bturbo\b`, String.raw`varoma`, String.raw`thermomix`, String.raw`bimby`, String.raw`\btm\d`,
    // the mixing bowl, per language
    String.raw`mixtopf\w*`, String.raw`mixing bowl`, String.raw`closed lid`, String.raw`measuring cup`,
    String.raw`\bvaso\b`, String.raw`\bcopo\b`, String.raw`(?:dans|du|le) le? ?bol\b`, String.raw`boccale`,
    String.raw`mengbeker`, String.raw`mikserskål\w*`, String.raw`naczyni\w* miksując\w*`,
    String.raw`mixovací nádob\w*`, String.raw`karıştırma kab\w*`, String.raw`\bvasul\b`, String.raw`bolul mixer\w*`,
    // accessories
    String.raw`butterfly`, String.raw`mariposa`, String.raw`schmetterling`, String.raw`farfalla`,
    String.raw`spatula`, String.raw`spatel`, String.raw`espátula`, String.raw`espatula`, String.raw`spatule`,
    String.raw`gobelet doseur`, String.raw`gareinsatz`, String.raw`cestillo`, String.raw`cestello`,
    String.raw`simmering basket`, String.raw`internal steamer`, String.raw`panier (?:de )?cuisson`,
    String.raw`mandolin\w*`, String.raw`lâmina`, String.raw`lame du couteau`, String.raw`cuchilla`,
    String.raw`messerabdeckung`,
    // machine-only modes
    String.raw`mode mixage`, String.raw`mode p[ée]tri\w*`, String.raw`sens inverse`, String.raw`linkslauf`,
    String.raw`giro a la izquierda`, String.raw`reverse\s*(?:blade|mode)`, String.raw`vel\s*espiga`,
    String.raw`modo espiga`, String.raw`teigstufe`, String.raw`dough mode`,
    // other locales' bowl names
    String.raw`wadah pencampur`, String.raw`bekas pengadun`, String.raw`主鍋`, String.raw`主锅`,
    String.raw`攪拌杯`, String.raw`料理機`, String.raw`速度`, String.raw`逆轉`,
    String.raw`渦輪`, String.raw`蝴蝶棒`, String.raw`刀片`, String.raw`揉麵模式`,
  ].join("|"),
  "i",
);

/** Ordered most-defining first: the first group that matches drives the animation. */
export const ACTION_PATTERNS: [ManualAction, RegExp][] = [
  ["oven", /\b(oven\w*|backofen|backblech|backen|bäck\w*|back(?:e|en|t)\b|bake[sd]?|baking|roast\w*|broil|preheat\w*|vorheiz\w*|horn[eoa]\w*|precalent\w*|forno|inforn\w*|enfourn\w*|four\b|préchauff\w*|cuire au four|cuptor\w*|coace\w*|coaceț\w*|precălz\w*|gratin\w*|grill\w*|piekarni\w*|upiec|pečic\w*|fırın\w*|pişir\w* fırın|panggang\w*|panaskan oven|memanggang|troub\w*|předehř\w*)\b/i],
  ["chill", /\b(fridge|refrigerat\w*|refriger\w*|chill\w*|freez\w*|frozen|kühlschrank|kühl\w* stell\w*|gefrierschrank|gefrierfach|einfrier\w*|gefrieren|tiefkühl\w*|frigorífico|nevera|congel\w*|frigo\w*|réfrigérat\w*|frigider\w*|koelkast|lodówk\w*|chladnič\w*|buzdolab\w*|dondurucu|kulkas|lemari es|bekukan)\b/i],
  ["stove", /\b(frying pan|saucepan|skillet|stovetop|stove|\bhob\b|deep.?fry\w*|pan.?fry\w*|sauté\w*|saute\w*|\bsear\b|pfanne\w*|\btopf\w*|herdplatte|anbrat\w*|brate\w*|sartén|cazo\b|olla\b|fre[íi]r|sofre[íi]r|poêle|casserole|faire revenir|padella|pentola|soffrigg\w*|tigai\w*|cratiț\w*|prăj\w*|koekenpan|patelni\w*|pánv\w*|tencere|tava\b|panci|kuali|didihkan|wajan)\b/i],
  ["drain", /\b(drain\w*|strain\w*|sieve|colander|sift\w*|escurr\w*|colador|cuel\w*|cernid\w*|égout\w*|passoire|tamis\w*|abtropf\w*|abgieß\w*|abgies\w*|sieb\w*|scolar\w*|colino|setacci\w*|scurg\w*|strecoar\w*|zeef|odcedź\w*|süz\w*)\b/i],
  ["wash", /\b(wash\w*|rinse[sd]?|rinsing|clean under|soak\w*|einweich\w*|wasch\w*|abspül\w*|spül\w*|lav[aeáo]\w*|enjuag\w*|remoj\w*|hidrat\w*|rinç\w*|tremp\w*|sciacqu\w*|ammoll\w*|spăl\w*|clăt\w*|înmuia\w*|umyj\w*|opláchn\w*|yıka\w*|cuci\w*|bilas\w*)\b/i],
  ["chop", /\b(chop\w*|cut|cuts|cutting board|slice[sd]?|slicing|dice[sd]?|mince[sd]?|julienne|quarter\w*|halve[sd]?|knife|peel\w*|schneid\w*|schnitt\w*|hack\w*|brett\w*|messer\b|würfel\w*|schäl\w*|cort[aeáo]\w*|pic[aeáo]\w*|tabla\b|cuchillo|pel[aeáo]\w*|troce\w*|coup[eéaz]\w*|hach[eéaz]\w*|planche|couteau|épluch\w*|tagli\w*|affett\w*|tarl\w*|coltello|tagliere|taie|felii?\w*|tocător|cuțit|curăț\w*|snijd\w*|pokrój|nakrájej|doğra\w*|dilimle\w*|potong\w*|cincang\w*|iris\w*|noż\w*|rozci\w*|rozdrobni\w*)\b/i],
  ["knead", /\b(knead\w*|roll out|rolling pin|work the dough|shape the dough|ausroll\w*|teigroll\w*|nudelholz|amas[aeáo]\w*|extend\w* la masa|rodillo|étal\w*|rouleau|pétri\w*|impast\w*|stend\w*|matterello|frământ\w*|întinde aluat\w*|uitrol\w*|deegroller|wałk\w*|váleč\w*|hamuru aç\w*)\b/i],
  ["whisk", /\b(whisk\w*|whip\w*|beat\w*|fold in|stir\w*|by hand|with a (?:spoon|fork|whisk)|schlag\w*|rühr\w*|unterheb\w*|verquirl\w*|bat[aeií]\w* a mano|mont\w* con varillas|mezcl\w* con|fouett\w*|batt[eiou]\w*|mélang\w* à la main|remu[eé]\w*|mescol\w*|sbatt\w*|amestec\w*|bate cu|klop\w*|ubij\w*|ušlehej|çırp\w*|kocok\w*|aduk\w*|movimientos envolventes|wymiesza\w*)\b/i],
  ["tray", /\b(line\w*(?: a| the)? (?:tin|tray|sheet|mould|mold|pan)|grease[sd]?|greasing|parchment|baking paper|baking tray|baking sheet|butter (?:a|the) (?:tin|dish)|backpapier|einfett\w*|ausleg\w*|belegen|forr[aeo]\w*|papel de horn\w*|engras\w*|bandeja|chemis\w*|papier sulfuris\w*|beurr\w*|teglia|carta da forno|imburr\w*|infarin\w*|hârtie de copt|unge cu|bakpapier|invet\w*|papier do piecz\w*|pečicí papír|yağla\w*|alasi\w*|nampan)\b/i],
  ["fill", /\b(pour into|pour over|transfer to|spoon into|spread into|fill\w*|tip into|vert[aeiou]\w*|vierta|vaci[aeé]\w*|volc\w*|molde|gieß\w*|einfüll\w*|umfüll\w*|füll\w*|kastenform|springform|vers[aeé]\w*|moule|répart\w*|versare|stampo|distribu\w*|toarn\w*|turnaț\w*|giet\w*|przel\w*|nalij|dök\w*)\b/i],
  ["serve", /\b(serve[sd]?|serving|plate up|garnish\w*|sprinkle over|decorat\w*|dust with|enjoy|bon app|servier\w*|anricht\w*|garnier\w*|bestreu\w*|guten appetit|sirv[ae]\w*|serv[aeií]\w*|decor\w*|espolvore\w*|adorn\w*|dress\w*|garnir|saupoudr\w*|guarn\w*|spolver\w*|presar\w*|opdien\w*|podawa\w*|servír\w*|servis|sajikan|hidangkan|taburi|nikmati)\b/i],
  ["rest", /\b(let (?:it )?(?:rest|stand|cool|sit)|leave to (?:rise|rest|prove|cool)|set aside|cover and|marinat\w*|prove for|rise for|ruhen|gehen lassen|abkühl\w*|abgedeckt|quellen|zur seite stell\w*|reserv\w*|repos\w*|dej[ae]\w* enfriar|enfri[ae]\w*|macer\w*|laisser (?:repos|refroid)\w*|refroid\w*|couvr\w*|ripos\w*|lievit\w*|raffredd\w*|las[aăiț]\w* (?:la )?(?:dospit|odihn|răci)\w*|deopart\w*|laat (?:rusten|rijzen)|odstaw\w*|nech\w* odpoč\w*|dinlen\w*|soğut\w*|sisihkan|diamkan|dinginkan)\b/i],
  ["store", /\b(airtight|store in|storage|sterili[sz]ed jar|keeps? for|in the pantry|aufbewahr\w*|luftdicht|haltbar|einmachglas|hermétic\w*|tarro|frasco|conserv\w*|bocal|barattolo|borcan|păstr\w*|bewaar\w*|słoik|sklenic\w*|kavanoz|hava almayan|simpan dalam|wadah tertutup)\b/i],
  ["prep", /.^/], // never matches — "prep" is the fallback
];

/** CJK text has no \b word boundaries, so those keywords need their own pass. */
export const CJK_PATTERNS: Partial<Record<ManualAction, RegExp>> = {
  oven: /烤箱|烘烤|預熱|烘焙/,
  chill: /冰箱|冷藏|冷凍/,
  stove: /鍋中|平底鍋|煎鍋|炒鍋/,
  drain: /過篩|瀝乾|過濾/,
  wash: /清洗|洗淨|沖洗/,
  chop: /切碎|切片|切塊|切成/,
  knead: /揉麵|擂/,
  whisk: /打發|拌入|攪拌均勻/,
  tray: /烤盤|烘焙紙|模具中/,
  fill: /倒入|裝入|填入/,
  serve: /盛盤|享用|裝飾|即可食用/,
  rest: /靜置|放涼|冷卻/,
  store: /密封|保存/,
};

const POUR_RE = /\b(add|pour|stir in|adăuga|adaug\w*|ajouter|añadir|aggiungere|hinzufügen|zugeben|tilsæt|toevoegen|dodaj|ekle|adicionar|加入)\b/i;
const CHOP_RE = /\b(chop|blend|mix|grate|grind|crush|toca|hacher|picar|tritare|hacken|hakke|raspen|siekać|doğra|tocat|triturar|切碎)\b/i;
const COOK_RE = /\b(cook|heat|boil|simmer|steam|sauté|bake|fry|găti|cuire|cocinar|cuocere|kochen|koge|koken|gotować|pişir|cozer|cozinhar|煮|蒸)\b/i;

export function parseStep(txt: string): StepMeta {
  const t = txt.toLowerCase();

  const temp = Number(
    (t.match(/(\d+)\s*°\s*c/) || [])[1] || 0,
  );
  const speed = Number(
    (t.match(
      /(?:speed|vitez[aă]|geschwindigkeit|stufe|velocidad|velocità|vitesse|hastighet|snelheid|hastighed|sebesség|rychlost|prędkość|hız|سرعة)\s*\.?\s*(\d+)/,
    ) ||
      t.match(/\bvel\.?\s*(\d+)/) ||
      t.match(/(\d+)\s*(?:speed|vitez[aă]|geschwindigkeit|velocidad|velocità|vitesse)/) ||
      [])[1] || 0,
  );
  const minM = t.match(/(\d+)\s*min/);
  const secM = t.match(/(\d+)\s*sec/);
  const hourM = t.match(/(\d+)\s*(?:h\b|hour|hora|heure|stunde|or[ăe])/);
  const secs =
    (hourM ? +hourM[1] * 3600 : 0) + (minM ? +minM[1] * 60 : 0) + (secM ? +secM[1] : 0);
  const weight = Number((t.match(/(\d+)\s*g\b/) || [])[1] || 0);

  const isThermomix = TM_PARAM.test(t) || TM_VOCAB.test(t);
  const actions = isThermomix
    ? []
    : ACTION_PATTERNS.filter(([a, re]) => re.test(t) || CJK_PATTERNS[a]?.test(txt)).map(([a]) => a);

  return {
    mode: isThermomix ? "thermomix" : "manual",
    action: actions[0] ?? "prep",
    actions,
    temp,
    speed,
    secs,
    weight,
    isPour: POUR_RE.test(t),
    isChop: CHOP_RE.test(t),
    isCook: COOK_RE.test(t) || temp > 0,
  };
}

export const ACTION_LABELS: Record<ManualAction, string> = {
  oven: "Oven",
  chill: "Chill",
  stove: "Stovetop",
  drain: "Drain",
  wash: "Wash",
  chop: "Cut",
  knead: "Knead",
  whisk: "Whisk",
  tray: "Prep tin",
  fill: "Transfer",
  serve: "Serve",
  rest: "Rest",
  store: "Store",
  prep: "By hand",
};
