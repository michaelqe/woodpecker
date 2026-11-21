// Display units. Design files are always millimetres; this only changes what people see/type.
const KEY = "wp.unit";
let unit = "mm";
try { unit = localStorage.getItem(KEY) || "mm"; } catch { /* private mode */ }

export const UNITS = ["mm", "cm", "in"];
export const getUnit = () => unit;
export function setUnit(u) {
  unit = UNITS.includes(u) ? u : "mm";
  try { localStorage.setItem(KEY, unit); } catch { /* private mode */ }
}

function gcd(a, b) { return b ? gcd(b, a % b) : a; }

/** Inches to the nearest 1/16, e.g. 41 5/8″. */
function inches(mm) {
  const neg = mm < 0;
  const sixteenths = Math.round(Math.abs(mm) / 25.4 * 16);
  const whole = Math.floor(sixteenths / 16);
  let num = sixteenths % 16, den = 16;
  if (num) { const g = gcd(num, den); num /= g; den /= g; }
  const s = num ? (whole ? `${whole} ${num}/${den}` : `${num}/${den}`) : `${whole}`;
  return `${neg ? "-" : ""}${s}″`;
}

const num = (v, d = 1) => (Math.round(v * 10 ** d) / 10 ** d).toLocaleString("en-US", { maximumFractionDigits: d });

/** Format a length in mm for display. `bare` drops the unit for mm (tables say "mm"). */
export function len(mm, { bare = false } = {}) {
  if (mm == null || Number.isNaN(mm)) return "";
  if (unit === "in") return inches(mm);
  if (unit === "cm") return `${num(mm / 10)}${bare ? "" : " cm"}`;
  return `${num(mm)}${bare ? "" : " mm"}`;
}
export const dims = (arr, opts) => arr.map((v) => len(v, { bare: true })).join(" × ") + (unit === "in" ? "" : ` ${unit}`);
export const unitLabel = () => (unit === "in" ? "inches" : unit);

/**
 * Parse a typed length to mm. Accepts 18, 18mm, 1.8cm, 0.5m, 3/4", 2-1/2in, 2 1/2", 1' 6", 1ft 6 1/2in.
 * A bare number is in the current display unit. Returns null when it is not a plain length
 * (e.g. an expression like "base_w - 2 * ply"), so the caller can send it as an expression.
 */
export function parseLen(text) {
  const t = String(text).trim().replace(/″|”/g, '"').replace(/′|’/g, "'");
  let m = t.match(/^(-?\d+(?:\.\d+)?)\s*(mm|cm|m|in|"|ft|')?$/i);
  if (m) {
    const v = parseFloat(m[1]);
    const u = (m[2] || "").toLowerCase();
    if (u === "mm") return v;
    if (u === "cm") return v * 10;
    if (u === "m") return v * 1000;
    if (u === "in" || u === '"') return v * 25.4;
    if (u === "ft" || u === "'") return v * 304.8;
    return unit === "in" ? v * 25.4 : unit === "cm" ? v * 10 : v;
  }
  // feet + inches (+ fraction): 1' 6", 1ft 6 1/2in
  m = t.match(/^(\d+)\s*(?:'|ft)\s*(?:(\d+(?:\.\d+)?)?(?:[\s-]+(\d+)\/(\d+)|\s*(\d+)\/(\d+))?)?\s*(?:"|in)?$/i);
  if (m) {
    const ft = +m[1];
    const whole = m[2] ? +m[2] : 0;
    const frac = m[3] ? +m[3] / +m[4] : m[5] ? +m[5] / +m[6] : 0;
    return (ft * 12 + whole + frac) * 25.4;
  }
  // inches with a fraction: 3/4", 2-1/2in, 2 1/2"
  m = t.match(/^(?:(\d+)[\s-]+)?(\d+)\/(\d+)\s*(?:"|in)?$/i);
  if (m && +m[3]) return ((m[1] ? +m[1] : 0) + +m[2] / +m[3]) * 25.4;
  return null;
}
