// Images for social media, drawn in the reader's browser when asked for, in the
// layout of the server's cards (sejmomat/card.py): an MP's term (turnout, missed
// votes, breaks of the club line, speeches, characteristic words) or latest sitting,
// and two side by side: MP with MP, club with club (the "Grafiki do udostępnienia"
// window, static/share.js). The PNG is handed over as a download and nothing is
// kept: the canvas and the file's address are dropped right after.
//
// window.SejmomatCards: mp(data, kind), compareMps(a, b), compareClubs(a, b) give a
// canvas; save(canvas, file) hands it over.
window.SejmomatCards = (() => {
  const W = 1200, MIN_H = 675, PAD = 64, GAP = 24, FOOT = 96;
  const BG = "#ffffff", SURFACE = "#f3f3f3", TEXT = "#0b0c0c", MUTED = "#484949", LINE = "#cecece";
  const YES = "#1f7a4d", NO = "#b3261e", ABSTAIN = "#9a6b00", NOT_CAST = "#6b6b70";
  const BRAND = "#1d70b8", LINK = "#1a65a6", FOOT_BG = "#0b0c0c", FOOT_TEXT = "#ffffff";
  const FAMILY = '"Source Sans 3", sans-serif', HEADING = '"Source Serif 4", serif';
  const font = (weight, size) => `${weight === "bold" || weight === "heading" ? 700 : 400} ${size}px ${weight === "heading" ? HEADING : FAMILY}`;
  let fontsReady;
  const loadFonts = () => fontsReady ??= Promise.all([
    document.fonts.load('400 28px "Source Sans 3"'),
    document.fonts.load('700 28px "Source Sans 3"'),
    document.fonts.load('700 64px "Source Serif 4"'),
  ]).catch((error) => { fontsReady = null; throw error; });
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
  // A photo covers its rectangular slot, keeping its proportions.
  const photoBox = (d, photo, x, top, w, h, r = 0) => {
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

  const masthead = (d, logo) => {
    d.fillStyle = FOOT_BG;
    d.fillRect(0, 0, W, 88);
    d.fillStyle = BRAND;
    d.fillRect(0, 82, W, 6);
    if (logo) {
      const h = 30, w = logo.width * h / logo.height;
      d.drawImage(logo, PAD, 26, w, h);
    }
    d.textBaseline = "middle";
    text(d, "sejmomat.pl", W - PAD, 42, font("bold", 26), FOOT_TEXT, "right");
    d.textBaseline = "top";
  };
  const header = (d, data, context, subtitle, photo) => {
    const photoW = photo ? 150 : 0, room = W - 2 * PAD - (photo ? photoW + 32 : 0);
    let y = 128;
    d.textBaseline = "top";
    d.font = font("heading", 64);
    for (const line of wrap(d, data.name, room, 2)) {
      text(d, line, PAD, y, font("heading", 64), TEXT);
      y += 84;
    }
    d.font = font("regular", 26);
    for (const line of wrap(d, `${context} · ${subtitle}`, room, 3)) {
      text(d, line, PAD, y + 8, font("regular", 26), MUTED);
      y += 36;
    }
    if (photo) {
      const h = Math.round(photoW * 1.25);
      photoBox(d, photo, W - PAD - photoW, 132, photoW, h);
      y = Math.max(y, 132 + h);
    }
    return y + 40;
  };
  const summaryRows = (d, y, rows) => {
    const width = W - 2 * PAD, rowH = 104;
    rows.forEach(([number, label, color, badge], i) => {
      const ty = y + i * rowH;
      d.fillStyle = i % 2 === 0 ? SURFACE : BG;
      d.fillRect(PAD, ty, width, rowH);
      d.fillStyle = LINE;
      d.fillRect(PAD, ty, width, 1);
      d.font = font("regular", 28);
      wrap(d, label, width - 360, 2).forEach((line, j) =>
        text(d, line, PAD + 24, ty + 22 + j * 34, font("regular", 28), TEXT));
      text(d, String(number), W - PAD - 24, ty + 16, font("heading", 54), color, "right");
      if (badge) text(d, `TOP ${badge}%`, W - PAD - 24, ty + 76, font("bold", 20), LINK, "right");
    });
    d.fillStyle = LINE;
    d.fillRect(PAD, y + rows.length * rowH, width, 1);
    return y + rows.length * rowH + 32;
  };
  const bar = (d, x, y, width, parts, height = 26) => {
    const total = parts.reduce((t, [n]) => t + n, 0) || 1;
    d.save();
    d.beginPath();
    d.rect(x, y, width, height);
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
  const footer = (canvas, y) => {
    const height = Math.max(MIN_H, y + 32 + FOOT);
    const out = Object.assign(document.createElement("canvas"), { width: W, height });
    const d = out.getContext("2d");
    d.fillStyle = BG;
    d.fillRect(0, 0, W, height);
    d.drawImage(canvas, 0, 0);
    d.fillStyle = BG;
    d.fillRect(0, height - FOOT, W, FOOT);
    d.fillStyle = LINE;
    d.fillRect(PAD, height - FOOT, W - 2 * PAD, 2);
    d.textBaseline = "middle";
    const lead = "Zobacz więcej na ";
    text(d, lead, PAD, height - 44, font("regular", 25), MUTED);
    d.font = font("regular", 25);
    text(d, "sejmomat.pl", PAD + d.measureText(lead).width, height - 44, font("bold", 28), LINK);
    text(d, "Dane: API Sejmu RP", W - PAD, height - 44, font("regular", 24), MUTED, "right");
    return out;
  };
  const panel = (d, y, height) => {
    d.fillStyle = SURFACE;
    d.fillRect(PAD, y, W - 2 * PAD, height);
  };

  const term = (d, data, photo) => {
    const t = data.term, top = t.top || {};
    let y = header(d, data, "Podsumowanie kadencji · poseł na Sejm", data.subtitle, photo);
    y = summaryRows(d, y, [
      [pct(t.turnout), `udział w głosowaniach (${t.cast} z ${t.eligible})`, TEXT, top.turnout],
      [t.missed, "opuszczonych głosowań", t.missed ? ABSTAIN : TEXT],
      [t.rebels, `wyłamań z linii klubu (${pct(t.rebelRate)})`, TEXT],
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
      text(d, "Charakterystyczne słowa w wystąpieniach", x0, ty, font("bold", 22), MUTED);
      ty += 44;
      for (const row of rows) {
        for (const [w, rx2, cw] of row) {
          rounded(d, x0 + rx2, ty, cw, 46, 0, BG, LINE);
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
    let y = header(d, data, "Ostatnie posiedzenie Sejmu", [data.club, `${s.sitting}. posiedzenie`, when].filter(Boolean).join(" · "), photo);
    y = summaryRows(d, y, [
      [s.total, "głosowań", TEXT], [s.Y, "razy za", YES], [s.N, "razy przeciw", NO],
      [s.A, "razy wstrzymał(a) się", ABSTAIN], [s.X, s.X === s.total ? "opuszczone: wszystkie" : "opuszczonych głosowań", s.X ? ABSTAIN : TEXT],
      [s.rebel, "razy wbrew linii klubu", TEXT],
    ]);
    const x = PAD + 28, width = W - 2 * PAD - 56;
    panel(d, y, 28 + 38 + 26 + 16 + 40 + 18);
    let ty = y + 28;
    text(d, "Głosy posła na tym posiedzeniu", x, ty, font("bold", 22), MUTED);
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
    await loadFonts();
    const [canvas, d] = blank();
    const [photo, logo] = await Promise.all([loadPhoto(data.photo), loadLogo(data.logo)]);
    masthead(d, logo);
    const y = (kind === "sitting" ? sitting : term)(d, data, photo);
    return footer(canvas, y);
  };

  // Equal value columns use one table grammar; colour never favours a club or MP.
  const versus = (d, y, rows) => {
    const labelW = 450, valueW = (W - 2 * PAD - labelW) / 2, rowH = 96;
    rows.forEach(([label, a, b, show = String, neutral = false], i) => {
      const ty = y + i * rowH;
      d.fillStyle = i % 2 === 0 ? SURFACE : BG;
      d.fillRect(PAD, ty, W - 2 * PAD, rowH);
      d.fillStyle = LINE;
      d.fillRect(PAD, ty, W - 2 * PAD, 1);
      d.textBaseline = "top";
      d.font = font("regular", 26);
      wrap(d, label, labelW - 40, 2).forEach((line, j) => text(d, line, PAD + 20, ty + 18 + 32 * j, font("regular", 26), TEXT));
      for (const [value, col] of [[a, 0], [b, 1]]) {
        const x = PAD + labelW + valueW * (col + 1) - 20;
        text(d, show(value), x, ty + 22, font(!neutral && a !== b && value === Math.max(a, b) ? "heading" : "regular", 42), TEXT, "right");
      }
    });
    d.fillStyle = LINE;
    d.fillRect(PAD, y + rows.length * rowH, W - 2 * PAD, 1);
    return y + rows.length * rowH + GAP;
  };
  const pair = (d, context, left, right, photos) => {
    const [title, period] = context.split(" · ");
    d.textBaseline = "top";
    text(d, title, PAD, 128, font("heading", 58), TEXT);
    text(d, period || "", PAD, 208, font("regular", 26), MUTED);
    const labelW = 450, colW = (W - 2 * PAD - labelW) / 2;
    let bottom = 260;
    [left, right].forEach((who, i) => {
      const x = PAD + labelW + i * colW + 12;
      let y = 260;
      if (photos) {
        photoBox(d, photos[i], x, y, 80, 100);
        y += 120;
      }
      let nameSize = 32;
      d.font = font("heading", nameSize);
      while (nameSize > 24 && who.name.split(/\s+/).some((word) => d.measureText(word).width > colW - 32)) {
        d.font = font("heading", --nameSize);
      }
      for (const line of wrap(d, who.name, colW - 32, 4)) {
        text(d, line, x, y, font("heading", nameSize), TEXT);
        y += nameSize + 10;
      }
      d.font = font("regular", 24);
      for (const line of wrap(d, who.sub || "", colW - 32, 2)) {
        text(d, line, x, y + 4, font("regular", 24), MUTED);
        y += 32;
      }
      bottom = Math.max(bottom, y);
    });
    return bottom + 32;
  };

  // a, b: {name, sub, photo, turnout, brokeLine, speeches, questions, signedMotions, clubSwitches}
  const compareMps = async (a, b, logoSrc) => {
    await loadFonts();
    const [canvas, d] = blank();
    const [pa, pb, logo] = await Promise.all([loadPhoto(a.photo), loadPhoto(b.photo), loadLogo(logoSrc)]);
    masthead(d, logo);
    let y = pair(d, "Porównanie posłów · X kadencja", a, b, [pa, pb]);
    y = versus(d, y, [
      ["udział w głosowaniach", a.turnout, b.turnout, pct],
      ["wystąpienia na sali plenarnej", a.speeches, b.speeches],
      ["interpelacje i zapytania", a.questions, b.questions],
      ["wyłamania z linii klubu", a.brokeLine, b.brokeLine, String, true],
      ["podpisane poprawki i wnioski", a.signedMotions, b.signedMotions],
    ]);
    return footer(canvas, y);
  };

  // a, b: {name, sub, members, cohesion, effectiveness, turnout, speeches, questions}; agreement: {rate, votes} or null
  const compareClubs = async (a, b, agreement, logoSrc) => {
    await loadFonts();
    const [canvas, d] = blank();
    const logo = await loadLogo(logoSrc);
    masthead(d, logo);
    let y = pair(d, "Porównanie klubów · X kadencja", a, b, null);
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
    return footer(canvas, y);
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
