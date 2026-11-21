// SVG cutting diagrams for sheets and boards. Returns markup strings.
import { len } from "./units.js";

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

export function sheetSvg(stock, i, { width = 340, light = false } = {}) {
  const [sx, sy] = stock.sheet;
  const k = width / sx, h = sy * k;
  const fg = light ? "#222" : "#e6e6e6", line = light ? "#666" : "#5a5a5a", fill = light ? "#efe6d2" : "#3a3326";
  const rects = stock.layouts[i].rects.map((r) => {
    const x = r.x * k, y = r.y * k, w = r.w * k, hh = r.h * k;
    const big = w > 54 && hh > 22;
    return `<g><title>${esc(r.label)} ${len(r.w, { bare: true })} × ${len(r.h, { bare: true })}</title>
      <rect x="${x}" y="${y}" width="${w}" height="${hh}" fill="${fill}" stroke="${line}"/>
      ${big ? `<text x="${x + w / 2}" y="${y + hh / 2}" fill="${fg}" font-size="10" text-anchor="middle" dominant-baseline="middle">${esc(r.label.length > 22 ? r.label.slice(0, 21) + "…" : r.label)}</text>` : ""}</g>`;
  }).join("");
  return `<svg class="layout" viewBox="-1 -1 ${width + 2} ${h + 2}" width="${width}" height="${h}" role="img" aria-label="Sheet ${i + 1} layout">
    <rect x="0" y="0" width="${width}" height="${h}" fill="none" stroke="${line}" stroke-dasharray="3 3"/>${rects}</svg>`;
}

export function boardSvg(stock, i, { width = 340, light = false } = {}) {
  const L = stock.stock_length, k = width / L, h = 18;
  const b = stock.detail[i];
  const fg = light ? "#222" : "#e6e6e6", line = light ? "#666" : "#5a5a5a", fill = light ? "#efe6d2" : "#3a3326";
  let x = 0;
  const parts = b.cuts.map((c, j) => {
    const w = c * k;
    const s = `<g><title>${esc(b.labels?.[j] || "")} ${len(c)}</title><rect x="${x}" y="0" width="${w}" height="${h}" fill="${fill}" stroke="${line}"/>
      ${w > 40 ? `<text x="${x + w / 2}" y="${h / 2}" fill="${fg}" font-size="10" text-anchor="middle" dominant-baseline="middle">${len(c, { bare: true })}</text>` : ""}</g>`;
    x += w + 3 * k;
    return s;
  }).join("");
  return `<svg class="layout" viewBox="-1 -1 ${width + 2} ${h + 2}" width="${width}" height="${h}" role="img" aria-label="Board ${i + 1}">
    <rect x="0" y="0" width="${width}" height="${h}" fill="none" stroke="${line}" stroke-dasharray="3 3"/>${parts}</svg>`;
}
