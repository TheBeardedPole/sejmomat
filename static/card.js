// Images for social media, drawn in the reader's browser when asked for, in the
// layout of the server's cards (sejmomat/card.py): an MP's term (turnout, missed
// votes, breaks of the club line, speeches, characteristic words) or latest sitting,
// and two side by side: MP with MP, club with club (the "Grafiki do udostępnienia"
// window, static/share.js). The PNG is handed over as a download and nothing is
// kept: the canvas and the file's address are dropped right after.
//
// window.SejmomatCards: mp(data, kind), compareMps(a, b), compareClubs(a, b) give a
// canvas; save(canvas, file) hands it over. The MP page's own buttons are wired below.
window.SejmomatCards = (() => {
  const W = 1200, MIN_H = 675, PAD = 64, GAP = 20, FOOT = 132;
  const BG = "#fbfaf8", SURFACE = "#ffffff", TEXT = "#1d1d1f", MUTED = "#6b6b70", LINE = "#e4e2dd";
  const YES = "#1f7a4d", NO = "#b3261e", ABSTAIN = "#9a6b00", NOT_CAST = "#8a8a8f";
  const FOOT_BG = "#1d5fc4", FOOT_TEXT = "#ffffff", FOOT_MUTED = "#d3e2f8";
  const FAMILY = '"Noto Sans", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
  const font = (weight, size) => `${weight === "bold" ? 700 : 400} ${size}px ${FAMILY}`;
  const pct = (x) => `${(x * 100).toFixed(1).replace(".", ",")}%`;
  const day = new Intl.DateTimeFormat("pl", { day: "numeric", month: "long", year: "numeric" });
  const date = (iso) => day.format(new Date(`${iso.slice(0, 10)}T12:00:00`));

  // lines no wider than `width`; beyond `max` the last ends with an ellipsis
  const wrap = (d, text, width, max = Infinity) => {
    const lines = [];
    let line = "";
    for (const word of text.split(/\s+/).filter(Boolean)) {
      if (line && d.measureText(`${line} ${word}`).width > width) {
        lines.push(line);
        line = word;
      } else line = `${line} ${word}`.trim();
    }
    lines.push(line);
    if (lines.length > max) {
      lines.length = max;
      while (lines[max - 1] && d.measureText(`${lines[max - 1]}…`).width > width) lines[max - 1] = lines[max - 1].replace(/\s*\S+$/, "");
      lines[max - 1] += "…";
    }
    return lines;
  };
  const text = (d, s, x, y, f, color, align = "left") => {
    d.font = f;
    d.fillStyle = color;
    d.textAlign = align;
    d.fillText(s, x, y);
  };
  const rounded = (d, x, y, w, h, r, fill, stroke) => {
    d.beginPath();
    d.roundRect(x, y, w, h, r);
    d.fillStyle = fill;
    d.fill();
    if (stroke) {
      d.lineWidth = 2;
      d.strokeStyle = stroke;
      d.stroke();
    }
  };
  const loadLogo = (src) => new Promise((resolve) => {
    if (!src) return resolve(null);
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null);
    img.src = src;
  });
  const loadPhoto = (src) => new Promise((resolve) => {
    if (!src) return resolve(null);
    const img = new Image();
    img.crossOrigin = "anonymous";   // the Sejm's API allows it; without it the canvas could not be saved
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null);
    setTimeout(() => resolve(null), 8000);   // a slow photo server should not hold up the image
    img.src = src;
  });
  // a photo into a rounded box, covering it and keeping its proportions
  const photoBox = (d, photo, x, top, w, h, r = 18) => {
    d.save();
    d.beginPath();
    d.roundRect(x, top, w, h, r);
    d.clip();
    if (photo) {
      const scale = Math.max(w / photo.width, h / photo.height);
      d.drawImage(photo, x + (w - photo.width * scale) / 2, top, photo.width * scale, photo.height * scale);
    } else {
      d.fillStyle = LINE;
      d.fillRect(x, top, w, h);
    }
    d.restore();
  };

  // header with the photo on the right; returns where the content starts
  const header = (d, data, kicker, subtitle, photo) => {
    const photoW = photo ? 150 : 0, room = W - 2 * PAD - (photo ? photoW + 32 : 0);
    let y = PAD - 8;
    d.textBaseline = "top";
    text(d, kicker, PAD, y, font("bold", 24), MUTED);
    y += 40;
    d.font = font("bold", 68);
    for (const line of wrap(d, data.name, room, 2)) {
      text(d, line, PAD, y, font("bold", 68), TEXT);
      y += 92;
    }
    d.font = font("regular", 30);
    for (const line of wrap(d, subtitle, room, 2)) {
      text(d, line, PAD, y, font("regular", 30), MUTED);
      y += 42;
    }
    if (photo) {
      const h = Math.round(photoW * 1.25), top = PAD;
      photoBox(d, photo, W - PAD - photoW, top, photoW, h);
      y = Math.max(y, top + h + 8);
    }
    return y + 22;
  };
  const tiles = (d, y, rows) => {
    const tileW = Math.floor((W - 2 * PAD - 2 * GAP) / 3), tileH = 172;
    rows.forEach(([number, label, color, badge], i) => {
      const x = PAD + (i % 3) * (tileW + GAP), ty = y + Math.floor(i / 3) * (tileH + GAP);
      rounded(d, x, ty, tileW, tileH, 18, SURFACE, LINE);
      let size = 60;
      if (badge) {
        // "TOP N%" as a pill in the top right corner, in the site's blue; a
        // number too wide to sit beside it ("100,0%") is set smaller
        d.font = font("bold", 22);
        const label = `TOP ${badge}%`, bw = Math.round(d.measureText(label).width) + 28;
        for (; size > 40; size -= 2) {
          d.font = font("bold", size);
          if (d.measureText(String(number)).width <= tileW - 24 - 20 - bw - 12) break;
        }
        rounded(d, x + tileW - 20 - bw, ty + 22, bw, 36, 18, FOOT_BG);
        d.textBaseline = "middle";
        text(d, label, x + tileW - 20 - bw / 2, ty + 41, font("bold", 22), FOOT_TEXT, "center");
        d.textBaseline = "top";
      }
      // the number's baseline stays where a 60-pixel one has it
      d.textBaseline = "alphabetic";
      d.font = font("bold", 60);
      text(d, String(number), x + 24, ty + 12 + d.measureText(String(number)).fontBoundingBoxAscent, font("bold", size), color);
      d.textBaseline = "top";
      d.font = font("regular", 24);
      wrap(d, label, tileW - 48, 2).forEach((line, k) => text(d, line, x + 24, ty + 94 + k * 31, font("regular", 24), MUTED));
    });
    return y + Math.ceil(rows.length / 3) * (tileH + GAP) + GAP;
  };
  const bar = (d, x, y, width, parts, height = 26) => {
    const total = parts.reduce((t, [n]) => t + n, 0) || 1;
    d.save();
    d.beginPath();
    d.roundRect(x, y, width, height, height / 2);
    d.clip();
    d.fillStyle = LINE;
    d.fillRect(x, y, width, height);
    let bx = x;
    for (const [n, color] of parts) {
      const seg = Math.round(width * n / total);
      d.fillStyle = color;
      d.fillRect(bx, y, seg, height);
      bx += seg;
    }
    d.restore();
  };
  const footer = (canvas, y, logo) => {
    const height = Math.max(MIN_H, y + PAD - GAP + FOOT);
    const out = Object.assign(document.createElement("canvas"), { width: W, height });
    const d = out.getContext("2d");
    d.drawImage(canvas, 0, 0);
    d.fillStyle = FOOT_BG;
    d.fillRect(0, height - FOOT, W, FOOT);
    const mid = height - FOOT / 2 + 16, lead = "Zobacz więcej na ";
    d.textBaseline = "alphabetic";
    text(d, lead, PAD, mid, font("regular", 36), FOOT_TEXT);
    d.font = font("regular", 36);
    text(d, "sejmomat.pl", PAD + d.measureText(lead).width, mid, font("bold", 50), FOOT_TEXT);
    if (logo) {
      // the site's wordmark over the data credit, as on the site's own images (sejmomat/card.py)
      const lh = 40, lw = Math.round(logo.width * lh / logo.height);
      d.drawImage(logo, W - PAD - lw, height - FOOT + 30, lw, lh);
      text(d, "Dane: API Sejmu RP", W - PAD, height - 30, font("regular", 22), FOOT_MUTED, "right");
    } else {
      text(d, "Dane: API Sejmu RP", W - PAD, mid, font("regular", 24), FOOT_MUTED, "right");
    }
    return out;
  };
  const panel = (d, y, height) => rounded(d, PAD, y, W - 2 * PAD, height, 18, SURFACE, LINE);

  const term = (d, data, photo) => {
    const t = data.term, top = t.top || {};
    let y = header(d, data, "PODSUMOWANIE KADENCJI · POSEŁ NA SEJM", data.subtitle, photo);
    y = tiles(d, y, [
      [pct(t.turnout), `udział w głosowaniach (${t.cast} z ${t.eligible})`, TEXT, top.turnout],
      [t.missed, "opuszczonych głosowań", t.missed ? ABSTAIN : TEXT],
      [t.rebels, `wyłamań z linii klubu (${pct(t.rebelRate)})`, t.rebels ? NO : TEXT],
      [t.speeches, "wystąpień na sali plenarnej", TEXT, top.speeches],
      [t.questions, "interpelacji i zapytań poselskich", TEXT, top.questions],
      // how many of the amendments and motions the MP signed passed; neutral colour: few pass for the opposition
      ...(t.signed ? [[`${t.signedAdopted} z ${t.signed}`, "podpisanych poprawek i wniosków przeszło", TEXT]] : []),
    ].filter(([n]) => n !== undefined));
    if (Object.keys(top).length) {
      // what the badges mean (STANDING_NOTE in sejmomat/card.py)
      text(d, "TOP N% – w gronie N% obecnych posłów z najwyższym wynikiem", PAD, y - 6, font("regular", 22), MUTED);
      y += 34;
    }
    if (data.words.length) {
      // the characteristic words as chips, as many rows as they need
      d.font = font("regular", 28);
      const x0 = PAD + 28, width = W - 2 * PAD - 56, rows = [[]];
      let rx = 0;
      for (const w of data.words) {
        const cw = d.measureText(w).width + 36;
        if (rx + cw > width && rows.at(-1).length) {
          rows.push([]);
          rx = 0;
        }
        rows.at(-1).push([w, rx, cw]);
        rx += cw + 12;
      }
      panel(d, y, 28 + 44 + rows.length * 58 + 14);
      let ty = y + 28;
      text(d, "CHARAKTERYSTYCZNE SŁOWA W WYSTĄPIENIACH", x0, ty, font("bold", 22), MUTED);
      ty += 44;
      for (const row of rows) {
        for (const [w, rx2, cw] of row) {
          rounded(d, x0 + rx2, ty, cw, 46, 23, BG, LINE);
          text(d, w, x0 + rx2 + 18, ty + 7, font("regular", 28), TEXT);
        }
        ty += 58;
      }
      y = ty + 14 + GAP;
    }
    return y;
  };

  const sitting = (d, data, photo) => {
    const s = data.sitting;
    const when = s.first.slice(0, 10) === s.last.slice(0, 10) ? date(s.first) : `${date(s.first)} – ${date(s.last)}`;
    let y = header(d, data, "OSTATNIE POSIEDZENIE SEJMU", [data.club, `${s.sitting}. posiedzenie`, when].filter(Boolean).join(" · "), photo);
    y = tiles(d, y, [
      [s.total, "głosowań", TEXT], [s.Y, "razy za", YES], [s.N, "razy przeciw", NO],
      [s.A, "razy wstrzymał(a) się", ABSTAIN], [s.X, s.X === s.total ? "opuszczone: wszystkie" : "opuszczonych głosowań", s.X ? ABSTAIN : TEXT],
      [s.rebel, "razy wbrew linii klubu", s.rebel ? NO : TEXT],
    ]);
    const x = PAD + 28, width = W - 2 * PAD - 56;
    panel(d, y, 28 + 38 + 26 + 16 + 40 + 18);
    let ty = y + 28;
    text(d, "GŁOSY POSŁA NA TYM POSIEDZENIU", x, ty, font("bold", 22), MUTED);
    ty += 38;
    const parts = [[s.Y, YES, "za"], [s.N, NO, "przeciw"], [s.A, ABSTAIN, "wstrz."], [s.X, NOT_CAST, "nie głosował(a)"]];
    bar(d, x, ty, width, parts.map(([n, c]) => [n, c]));
    ty += 26 + 16;
    let tx = x;
    parts.forEach(([n, color, word], i) => {
      const s2 = `${n} ${word}`;
      text(d, s2, tx, ty, font("bold", 28), color);
      d.font = font("bold", 28);
      tx += d.measureText(s2).width;
      if (i < parts.length - 1) {
        text(d, "  ·  ", tx, ty, font("regular", 28), MUTED);
        d.font = font("regular", 28);
        tx += d.measureText("  ·  ").width;
      }
    });
    return ty + 40 + 18 + GAP;
  };

  const blank = (height = 3000) => {
    const canvas = Object.assign(document.createElement("canvas"), { width: W, height });
    const d = canvas.getContext("2d");
    d.fillStyle = BG;
    d.fillRect(0, 0, W, height);
    return [canvas, d];
  };

  const mp = async (data, kind) => {
    const [canvas, d] = blank();
    const [photo, logo] = await Promise.all([loadPhoto(data.photo), loadLogo(data.logo)]);
    const y = (kind === "sitting" ? sitting : term)(d, data, photo);
    return footer(canvas, y, logo);
  };

  // ---- two side by side: each figure a row, the two values at the ends with bars
  // growing from the middle towards them, in one colour for both (no side favoured);
  // the higher value in bold, except in a neutral row (breaks of the club line: more is
  // neither better nor worse), where both are drawn alike
  const versus = (d, y, rows) => {
    const x = PAD, width = W - 2 * PAD, rowH = 86, mid = W / 2, half = width / 2 - 150;
    panel(d, y, rows.length * rowH + 24);
    let ry = y + 12;
    rows.forEach(([label, a, b, show = (v) => String(v), neutral = false], i) => {
      if (i) {
        d.fillStyle = LINE;
        d.fillRect(x + 24, ry, width - 48, 1);
      }
      const max = Math.max(a, b) || 1, cy = ry + rowH / 2;
      d.textBaseline = "middle";
      text(d, label, mid, cy - 22, font("regular", 22), MUTED, "center");
      for (const [v, side] of [[a, -1], [b, 1]]) {
        const len = Math.round((half - 100) * (v / max));   // room left for a value as wide as "100,0%"
        d.fillStyle = FOOT_BG;
        d.globalAlpha = neutral ? 0.55 : v >= max ? 0.9 : 0.35;
        d.beginPath();
        d.roundRect(side < 0 ? mid - 24 - len : mid + 24, cy + 4, Math.max(len, 4), 14, 7);
        d.fill();
        d.globalAlpha = 1;
        text(d, show(v), side < 0 ? x + 28 : x + width - 28, cy + 8, font(!neutral && v >= max && a !== b ? "bold" : "regular", 40), TEXT, side < 0 ? "left" : "right");
      }
      ry += rowH;
    });
    d.textBaseline = "top";
    return ry + 12 + GAP;
  };
  // the two names at the top, each over its side, "vs" between them
  const pair = (d, kicker, left, right, photos) => {
    let y = PAD - 8;
    d.textBaseline = "top";
    text(d, kicker, W / 2, y, font("bold", 24), MUTED, "center");
    y += 52;
    const colW = (W - 2 * PAD - 120) / 2, ph = photos ? 150 : 0, pw = Math.round(ph * 0.8);
    const sides = [[left, PAD, "left"], [right, W - PAD, "right"]];
    let bottom = y;
    sides.forEach(([who, edge, align], i) => {
      let ty = y;
      if (photos) {
        photoBox(d, photos[i], align === "left" ? edge : edge - pw, ty, pw, ph, 16);
        ty += ph + 18;
      }
      d.font = font("bold", 46);
      for (const line of wrap(d, who.name, colW, 2)) {
        text(d, line, edge, ty, font("bold", 46), TEXT, align);
        ty += 58;
      }
      d.font = font("regular", 26);
      for (const line of wrap(d, who.sub || "", colW, 2)) {
        text(d, line, edge, ty, font("regular", 26), MUTED, align);
        ty += 36;
      }
      bottom = Math.max(bottom, ty);
    });
    d.textBaseline = "middle";
    rounded(d, W / 2 - 40, y + (photos ? ph / 2 : 30) - 30, 80, 60, 30, FOOT_BG);
    text(d, "vs", W / 2, y + (photos ? ph / 2 : 30), font("bold", 30), FOOT_TEXT, "center");
    d.textBaseline = "top";
    return bottom + 24;
  };

  // a, b: {name, sub, photo, turnout, brokeLine, speeches, questions, signedMotions, clubSwitches}
  const compareMps = async (a, b, logoSrc) => {
    const [canvas, d] = blank();
    const [pa, pb, logo] = await Promise.all([loadPhoto(a.photo), loadPhoto(b.photo), loadLogo(logoSrc)]);
    let y = pair(d, "PORÓWNANIE POSŁÓW · X KADENCJA", a, b, [pa, pb]);
    y = versus(d, y, [
      ["udział w głosowaniach", a.turnout, b.turnout, pct],
      ["wystąpienia na sali plenarnej", a.speeches, b.speeches],
      ["interpelacje i zapytania", a.questions, b.questions],
      ["wyłamania z linii klubu", a.brokeLine, b.brokeLine, String, true],
      ["podpisane poprawki i wnioski", a.signedMotions, b.signedMotions],
    ]);
    return footer(canvas, y, logo);
  };

  // a, b: {name, sub, members, cohesion, effectiveness, turnout, speeches, questions}; agreement: {rate, votes} or null
  const compareClubs = async (a, b, agreement, logoSrc) => {
    const [canvas, d] = blank();
    const logo = await loadLogo(logoSrc);
    let y = pair(d, "PORÓWNANIE KLUBÓW · X KADENCJA", a, b, null);
    const one = (v) => v.toFixed(1).replace(".", ",");
    y = versus(d, y, [
      ["posłów w klubie", a.members, b.members],
      ["spójność głosowań", a.cohesion, b.cohesion, pct],
      ["głosowania wygrane (skuteczność)", a.effectiveness, b.effectiveness, pct],
      ["średni udział posłów w głosowaniach", a.turnout, b.turnout, pct],
      ["wystąpienia na posła", a.speeches, b.speeches, one],
      ["interpelacje na posła", a.questions, b.questions, one],
    ]);
    if (agreement) {
      panel(d, y, 120);
      d.textBaseline = "middle";
      text(d, pct(agreement.rate), PAD + 32, y + 60, font("bold", 56), TEXT);
      d.font = font("bold", 56);
      const lx = PAD + 32 + d.measureText(pct(agreement.rate)).width + 24;
      text(d, "głosowań, w których oba kluby głosowały tak samo", lx, y + 44, font("regular", 26), TEXT);
      text(d, `spośród ${agreement.votes} głosowań, w których brały udział oba`, lx, y + 78, font("regular", 22), MUTED);
      d.textBaseline = "top";
      y += 120 + GAP;
    }
    return footer(canvas, y, logo);
  };

  const save = async (canvas, file) => {
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
    const url = URL.createObjectURL(blob);
    const a = Object.assign(document.createElement("a"), { href: url, download: `${file}.png` });
    document.body.append(a);
    a.click();
    a.remove();
    // the copy lives only until the download has started
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  };
  const toBlob = (canvas) => new Promise((resolve) => canvas.toBlob(resolve, "image/png"));

  return { mp, compareMps, compareClubs, save, toBlob };
})();

// the MP page's own buttons (templates/_cards.html, mp)
(() => {
  const box = document.querySelector(".card-downloads[data-mp]");
  if (!box) return;
  const data = JSON.parse(document.getElementById("mp-card").textContent);
  box.addEventListener("click", async (e) => {
    const button = e.target.closest("button[data-card]");
    if (!button || button.disabled) return;
    const caption = button.querySelector("span") || button, label = caption.textContent;
    button.disabled = true;
    caption.textContent = box.dataset.busy;
    try {
      await document.fonts?.ready;
      const canvas = await window.SejmomatCards.mp(data, button.dataset.card);
      await window.SejmomatCards.save(canvas, `${box.dataset.file}-${button.dataset.file}`);
      canvas.width = canvas.height = 0;
    } catch {
      box.querySelector(".card-error").hidden = false;
    } finally {
      button.disabled = false;
      caption.textContent = label;
    }
  });
})();
