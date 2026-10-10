/* Warm editorial café compositor. Server-owned inputs; never accepts remote URLs. */
(function () {
  "use strict";
  const VERSION = "canvas-modern-cafe-b1.0";
  const FONT = '"CampaignNoto", "CampaignKannada"';
  function failure(code) { throw new Error(code); }
  function controlled(url) {
    const parsed = new URL(url, location.origin);
    if (parsed.origin !== location.origin || !/^\/api\/(assets\/[-a-zA-Z0-9]+|render\/fonts\/(NotoSans|NotoSansKannada)\.ttf)$/.test(parsed.pathname) || parsed.search || parsed.hash) failure("CROSS_ORIGIN_ASSET");
    return parsed.href;
  }
  async function fonts(input, timeout) {
    const faces = [new FontFace("CampaignNoto", `url("${controlled(input.font_urls.latin)}")`, { weight: "100 900" }),
      new FontFace("CampaignKannada", `url("${controlled(input.font_urls.kannada)}")`, { weight: "100 900" })];
    let timer;
    try {
      await Promise.race([Promise.all(faces.map(face => face.load())), new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error("FONT_TIMEOUT")), timeout);
      })]);
      faces.forEach(face => document.fonts.add(face));
      await document.fonts.ready;
      if (faces.some(face => face.status !== "loaded")) failure("FONT_UNAVAILABLE");
    } catch (error) { failure(error.message === "FONT_TIMEOUT" ? "FONT_TIMEOUT" : "FONT_UNAVAILABLE"); }
    finally { clearTimeout(timer); }
  }
  async function image(url) {
    const picture = new Image();
    picture.src = controlled(url);
    try { await picture.decode(); } catch { failure("IMAGE_UNAVAILABLE"); }
    if (!picture.naturalWidth || !picture.naturalHeight) failure("IMAGE_UNAVAILABLE");
    return picture;
  }
  function metric(ctx, text) {
    const m = ctx.measureText(text);
    return { left: Math.max(0, m.actualBoundingBoxLeft), right: Math.max(m.width, m.actualBoundingBoxRight),
      ascent: Math.max(0, m.actualBoundingBoxAscent), descent: Math.max(0, m.actualBoundingBoxDescent) };
  }
  function width(ctx, text) { const m = metric(ctx, text); return m.left + m.right; }
  function wrap(ctx, text, maximum, segmenter) {
    const lines = [];
    // Preserve every code point; wrapping never normalizes, truncates or splits graphemes.
    for (const paragraph of text.split("\n")) {
      let line = "";
      const words = paragraph.match(/\S+\s*|\s+/gu) || [""];
      for (const word of words) {
        if (width(ctx, line + word) <= maximum) { line += word; continue; }
        if (line) { lines.push(line); line = ""; }
        if (width(ctx, word) <= maximum) { line = word; continue; }
        for (const { segment } of segmenter.segment(word)) {
          if (width(ctx, segment) > maximum) failure("GRAPHEME_OVERFLOW");
          if (width(ctx, line + segment) > maximum && line) { lines.push(line); line = ""; }
          line += segment;
        }
      }
      lines.push(line);
    }
    return lines;
  }
  function safeArea(input) {
    if (input.size === "story") return [72, 200, input.width - 144, input.height - 440];
    const m = input.size === "landscape" ? 48 : 64;
    return [m, m, input.width - 2 * m, input.height - 2 * m];
  }
  function contrast(foreground, background) {
    function luminance(hex) {
      const rgb = hex.match(/[a-f\d]{2}/gi).map(v => parseInt(v, 16) / 255).map(v => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
      return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
    }
    const a = luminance(foreground), b = luminance(background);
    return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
  }
  function layout(ctx, input, safe, logo, segmenter) {
    const [x, top, maximum, h] = safe;
    const landscape = input.size === "landscape";
    const story = input.size === "story";
    const minimum = landscape ? 24 : input.size === "story" ? 30 : 26;
    const logoSize = logo ? 56 : 0;
    // Prefer an editorial paper column; verbose/native copy retains a wider fallback.
    for (const column of landscape ? [true] : [true, false]) {
    const copyWidth = column ? Math.floor(maximum * 0.56) : maximum;
    for (let scale = 1; scale >= 0.65; scale -= 0.025) {
      function block(field, base, weight, firstBase) {
        let y = 0;
        const lines = [];
        const paragraphs = (input.fields[field] || "").split("\n");
        if (!input.fields[field]) return { lines, height: 0 };
        for (let i = 0; i < paragraphs.length; i++) {
          const fontSize = Math.max(minimum, Math.round((i === 0 && firstBase ? firstBase : base) * scale));
          const lineWeight = i === 0 && firstBase ? 900 : weight;
          ctx.font = `${lineWeight} ${fontSize}px ${FONT}`;
          for (const line of wrap(ctx, paragraphs[i], copyWidth, segmenter)) {
          const m = metric(ctx, line);
          const lineHeight = Math.max(fontSize * 1.36, m.ascent + m.descent + fontSize * 0.2);
          const lineX = x;
          lines.push({ field, text: line, x: lineX, draw_x: lineX + m.left, y, width: m.left + m.right,
            height: m.ascent + m.descent, font_size: fontSize, baseline: y + m.ascent,
            weight: lineWeight, offer: field === "body" && i === 0 });
          y += lineHeight;
          }
          if (i < paragraphs.length - 1) y += 5;
        }
        return { lines, height: y };
      }
      const headline = block("headline", landscape ? 36 : story ? 62 : 48, 700);
      const body = block("body", landscape ? 25 : story ? 33 : 27, 400,
        column ? (landscape ? 62 : story ? 110 : 96) : (story ? 88 : 72));
      const cta = block("cta", landscape ? 26 : story ? 36 : 29, 600);
      const tags = Object.keys(input.fields).filter(k => k.startsWith("hashtags.")).map(k => block(k, minimum, 400));
      const tagHeight = tags.reduce((sum, tag) => sum + tag.height, 0);
      const logoHeight = logo ? logoSize + 12 : 0;
      const copyHeight = logoHeight + headline.height + body.height + cta.height + tagHeight + 48;
      const artHeight = h - copyHeight - 36;
      if (column ? copyHeight > h : artHeight < (story ? 420 : 190)) continue;
      const lines = [];
      let y = top + logoHeight;
      function place(part) {
        for (const line of part.lines) lines.push({ ...line, y: line.y + y, baseline: line.baseline + y });
        y += part.height;
      }
      place(headline);
      y += 18;
      const art = column ? [x + maximum * 0.54, top + h * 0.1, maximum * 0.46, h * 0.9]
        : [x + 12, y, maximum - 24, artHeight];
      if (!column) y += artHeight + 20;
      place(body);
      y += 16;
      place(cta);
      for (const tag of tags) place(tag);
      const logoX = x;
      if (lines.every(line => line.x >= x && line.x + line.width <= x + maximum + 0.01 && line.y + line.height <= top + h))
        return { lines, art, column, copyWidth, logoBounds: logo ? [logoX, top, logoSize, logoSize] : null };
    }
    }
    failure("TEXT_OVERFLOW");
  }
  async function render(input, options = {}) {
    if (input.renderer_version !== VERSION || ![[1080, 1350], [1080, 1080], [1080, 1920], [1200, 630]].some(([w, h]) => w === input.width && h === input.height)) failure("LAYOUT_INVALID");
    if (!Intl.Segmenter) failure("GRAPHEME_ENGINE_MISSING");
    await fonts(input, options.fontTimeout || 8000);
    const background = await image(input.background_url);
    const logo = input.logo_url ? await image(input.logo_url) : null;
    const canvas = document.createElement("canvas");
    canvas.width = input.width; canvas.height = input.height;
    const ctx = canvas.getContext("2d", { alpha: false });
    if (!ctx) failure("CANVAS_UNAVAILABLE");
    const safe = safeArea(input);
    const result = layout(ctx, input, safe, logo, new Intl.Segmenter(input.language === "kn" ? "kn" : "en", { granularity: "grapheme" }));
    // One source image only: never duplicate the cup in a blurred full-bleed copy.
    ctx.fillStyle = "#F8EDD7"; ctx.fillRect(0, 0, input.width, input.height);
    const [ax, ay, aw, ah] = result.art;
    const shade = ctx.createLinearGradient(ax, ay, ax + aw, ay + ah);
    shade.addColorStop(0, "#152F22"); shade.addColorStop(1, "#24382A");
    ctx.fillStyle = shade;
    if (result.column) ctx.fillRect(ax, 0, input.width - ax, input.height);
    else ctx.fillRect(ax, ay, aw, ah);
    const imageWidth = result.column ? input.width - ax : aw;
    const imageHeight = result.column ? input.height - ay : ah;
    const scale = Math.min(imageWidth / background.width, imageHeight / background.height);
    const w = background.width * scale, h = background.height * scale;
    const photo = document.createElement("canvas");
    photo.width = Math.ceil(w); photo.height = Math.ceil(h);
    const photoCtx = photo.getContext("2d");
    if (!photoCtx) failure("CANVAS_UNAVAILABLE");
    photoCtx.drawImage(background, 0, 0, photo.width, photo.height);
    if (result.column) {
      // Blend only the outer edge; the complete hero stays within the source's central area.
      const fade = photoCtx.createLinearGradient(0, 0, 0, photo.height);
      fade.addColorStop(0, "rgba(0,0,0,0)"); fade.addColorStop(0.1, "rgba(0,0,0,1)");
      fade.addColorStop(1, "rgba(0,0,0,1)");
      photoCtx.globalCompositeOperation = "destination-in";
      photoCtx.fillStyle = fade; photoCtx.fillRect(0, 0, photo.width, photo.height);
    }
    ctx.drawImage(photo, ax + (imageWidth - w) / 2, ay + imageHeight - h, w, h);
    if (result.column) {
      const edge = safe[0] + result.copyWidth + 32;
      ctx.fillStyle = "#F8EDD7";
      ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(edge + 55, 0);
      ctx.bezierCurveTo(edge, input.height * 0.2, edge + 60, input.height * 0.45, edge + 12, input.height * 0.6);
      ctx.bezierCurveTo(edge + 2, input.height * 0.8, edge + 45, input.height * 0.9, edge + 25, input.height);
      ctx.lineTo(0, input.height); ctx.closePath(); ctx.fill();
    }
    // Seeded paper texture stays lighter than the contrast-tested darkest paper.
    let seed = 29;
    ctx.fillStyle = "#EFE1C5";
    for (let i = 0; i < 4500; i++) {
      seed = (seed * 1664525 + 1013904223) >>> 0; const px = seed % input.width;
      seed = (seed * 1664525 + 1013904223) >>> 0; const py = seed % input.height;
      if (px < (result.column ? safe[0] + result.copyWidth + 24 : input.width) &&
          (result.column || py < ay || py > ay + ah)) ctx.fillRect(px, py, 1.5, 1.5);
    }
    const offerLines = result.lines.filter(line => line.offer);
    if (offerLines.length) {
      const left = safe[0] - 18, right = safe[0] + result.copyWidth + 18;
      const top = offerLines[0].y - 14, bottom = offerLines.at(-1).y + offerLines.at(-1).height + 14;
      ctx.fillStyle = "#123C2B";
      ctx.beginPath(); ctx.moveTo(left + 12, top); ctx.lineTo(right - 30, top - 5);
      ctx.lineTo(right, top + 10); ctx.lineTo(right - 12, bottom - 10);
      ctx.lineTo(right - 32, bottom + 4); ctx.lineTo(left, bottom);
      ctx.lineTo(left + 10, top + 18); ctx.closePath(); ctx.fill();
      ctx.fillStyle = "#FBC844"; ctx.fillRect(left + 10, bottom + 3, result.copyWidth * 0.7, 5);
    }
    const ctaLines = result.lines.filter(line => line.field === "cta");
    if (ctaLines.length) {
      ctx.fillStyle = "#123C2B";
      ctx.beginPath(); ctx.roundRect(safe[0] - 12, ctaLines[0].y - 9, result.copyWidth + 24,
        ctaLines.at(-1).y + ctaLines.at(-1).height - ctaLines[0].y + 22, 16); ctx.fill();
    }
    if (logo) {
      const [x, y, maxW, maxH] = result.logoBounds;
      const factor = Math.min(maxW / logo.width, maxH / logo.height);
      ctx.drawImage(logo, x, y, logo.width * factor, logo.height * factor);
    }
    ctx.fillStyle = "#FFF4DF";
    let offerArea = 0;
    let matchedOffer = false;
    for (const line of result.lines) {
      ctx.font = `${line.weight} ${line.font_size}px ${FONT}`;
      ctx.fillStyle = line.offer ? "#FBC844" : line.field === "cta" ? "#F8EDD7" : "#123C2B";
      ctx.fillText(line.text, line.draw_x, line.baseline);
      // Exact approved offer strings, measured with the very font used to draw them.
      // Full forms split across wrapped lines stay unavailable; no inferred bounds.
      for (const form of new Set(input.offer_forms || [])) {
        let from = 0;
        while (form && (from = line.text.indexOf(form, from)) !== -1) {
          const metric = ctx.measureText(form);
          offerArea += (metric.actualBoundingBoxLeft + metric.actualBoundingBoxRight) *
            (metric.actualBoundingBoxAscent + metric.actualBoundingBoxDescent);
          matchedOffer = true;
          from += form.length;
        }
      }
    }
    const ratio = Math.min(contrast("#123C2B", "#FBC844"), contrast("#F8EDD7", "#123C2B"), contrast("#EFE1C5", "#123C2B"));
    if (ratio < 7) failure("CONTRAST_INVALID");
    let data;
    try { data = canvas.toDataURL("image/png"); } catch { failure("CANVAS_TAINTED"); }
    document.body.replaceChildren(canvas);
    return { png: data, validation: { passed: true, reasons: [], font_loaded: true, grapheme_engine: true,
      contrast: ratio, offer_area_ratio: matchedOffer ? Math.min(1, offerArea / (input.width * input.height)) : null,
      safe_area: safe, lines: result.lines.map(line => ({ field: line.field, text: line.text,
        x: line.x, y: line.y, width: line.width, height: line.height, font_size: line.font_size })),
      logo_bounds: result.logoBounds, renderer_version: VERSION } };
  }
  window.PosterCanvas = Object.freeze({ render, wrap, contrast, version: VERSION });
}());
