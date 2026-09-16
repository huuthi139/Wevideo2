/**
 * Injected into MAIN world on labs.google — has access to window.grecaptcha
 * Also intercepts TRPC fetch responses to capture fresh signed media URLs.
 */
const SITE_KEY = '6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV';

// ─── XHR Interceptor (for file uploads) ─────────────────────
const _xhrOpen = XMLHttpRequest.prototype.open;
const _xhrSend = XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.open = function (method, url, ...rest) {
  this.__sniffUrl = url;
  this.__sniffMethod = method;
  return _xhrOpen.call(this, method, url, ...rest);
};
XMLHttpRequest.prototype.send = function (body) {
  try {
    const url = this.__sniffUrl || '';
    if (url.includes('googleapis.com') || url.includes('labs.google') || url.includes('storage.google')) {
      window.postMessage({
        type: '__FLOWKIT_SNIFF__',
        url,
        body: typeof body === 'string' ? body : `(binary ${body?.size || body?.byteLength || '?'} bytes)`,
        method: this.__sniffMethod || 'POST',
      }, '*');
    }
  } catch {}
  return _xhrSend.call(this, body);
};

// [SỬA 15/09 #2] batchexecute là JSON LỒNG → "=" "&" "/" bị escape NHÂN ĐÔI ("\\u003d").
// Chuẩn hoá NGAY TẠI ĐÂY (injected nạp thẳng từ đĩa, không cần reload extension) để regex URL
// trong background.js không bị cắt cụt ở "?Expires" → thiếu Signature → tải 403.
function __normEsc(t) {
  return String(t).replace(/\\+\//g, '/').replace(/\\+u0026/gi, '&').replace(/\\+u003d/gi, '=');
}
// ─── TRPC Response Monitor ─────────────────────────────────
// Monkey-patch fetch to intercept TRPC responses containing media URLs.
// Fresh signed GCS URLs are extracted and forwarded to the agent.

const _originalFetch = window.fetch;
window.fetch = async function (...args) {
  try {
    const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';

    // ─── SNIFF ALL outgoing requests (catch upload) ─────────
    {
      let bodyText = '';
      if (args[1]?.body) {
        const b = args[1].body;
        if (typeof b === 'string') bodyText = b.length > 5000 ? b.slice(0, 200) + `...(${b.length} chars)` : b;
        else if (b instanceof FormData) bodyText = `(FormData: ${[...b.keys()].join(', ')})`;
        else if (b instanceof Blob) bodyText = `(Blob ${b.size} bytes, type=${b.type})`;
        else if (b instanceof ArrayBuffer) bodyText = `(ArrayBuffer ${b.byteLength} bytes)`;
        else if (b instanceof ReadableStream) bodyText = '(ReadableStream)';
        else bodyText = JSON.stringify(b)?.slice(0, 2000) || '(unknown)';
      }
      window.postMessage({
        type: '__FLOWKIT_SNIFF__',
        url, body: bodyText, method: args[1]?.method || 'GET',
      }, '*');
    }
  } catch {}

  const response = await _originalFetch.apply(this, args);
  try {
    const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
    // [DIAG 14/09] Bắt request/response CHỨA prompt của mình (__WANTPROMPT) → biết submit đi đâu.
    try {
      const wp = window.__WANTPROMPT;
      if (wp) {
        let rq = ''; const b = args[1] && args[1].body;
        if (typeof b === 'string') rq = b; else if (b) rq = '(' + ((b.constructor && b.constructor.name) || 'body') + ')';
        const reqHit = rq.indexOf(wp) >= 0;
        const apiish = /\/trpc\/|batchexecute|generat|GenerateVideo|StartMedia|createMedia|runFlow/i.test(url);
        if (reqHit || apiish) {
          response.clone().text().then((rt) => {
            if (reqHit || (rt && rt.indexOf(wp) >= 0)) {
              window.__FLOWLOG2 = window.__FLOWLOG2 || [];
              window.__FLOWLOG2.push({ u: String(url).slice(-72), rh: reqHit, m: (args[1] && args[1].method) || 'GET', req: rq.slice(0, 260), res: rt.slice(0, 360) });
              if (window.__FLOWLOG2.length > 8) window.__FLOWLOG2.shift();
            }
          }).catch(() => {});
        }
      }
    } catch (e) {}
    // Only intercept TRPC calls on labs.google that return project/flow data
    // [VÁ RIÊNG 11/09] Flow v2 (flow.google.com) không còn tRPC — media URL nằm
    // trong response RPC `/_/AiSandboxAngularFrontend/data/batchexecute`.
    if ((url.includes('/fx/api/trpc/') || url.includes('/data/batchexecute')) && response.ok) {
      const clone = response.clone();
      clone.text().then(text => {
        // [VÁ RIÊNG 18/08] Google đổi CDN sang flow-content.google; chỉ dò host cũ
        // thì không bắt được URL nào và việc tải video hỏng trong im lặng.
        if (text.includes('storage.googleapis.com/ai-sandbox-videofx/')
            || text.includes('flow-content.google/')) {
          try { window.__FLOWLOG = (window.__FLOWLOG || []); window.__FLOWLOG.push({ u: String(url).slice(-60), t: Date.now(), body: text }); if (window.__FLOWLOG.length > 10) window.__FLOWLOG.shift(); } catch (e) {}
          window.dispatchEvent(new CustomEvent('TRPC_MEDIA_URLS', {
            detail: { url, body: __normEsc(text) },
          }));
        }
      }).catch(() => {});
    }
  } catch {}
  return response;
};


window.addEventListener('GET_CAPTCHA', async ({ detail }) => {
  const { requestId, pageAction } = detail;
  try {
    await waitForGrecaptcha();
    const token = await window.grecaptcha.enterprise.execute(SITE_KEY, {
      action: pageAction,
    });
    window.dispatchEvent(new CustomEvent('CAPTCHA_RESULT', {
      detail: { requestId, token },
    }));
  } catch (e) {
    window.dispatchEvent(new CustomEvent('CAPTCHA_RESULT', {
      detail: { requestId, error: e.message },
    }));
  }
});

function waitForGrecaptcha(timeout = 10000) {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    const check = () => {
      if (window.grecaptcha?.enterprise?.execute) return resolve();
      if (Date.now() - start > timeout) return reject(new Error('grecaptcha not available'));
      setTimeout(check, 200);
    };
    check();
  });
}

// ─── Video Upload Handler ───────────────────────────────────
window.addEventListener('UPLOAD_VIDEO', async ({ detail }) => {
  const { requestId, videoBase64, projectId } = detail;
  try {
    // Convert base64 to Blob
    const byteChars = atob(videoBase64);
    const byteArray = new Uint8Array(byteChars.length);
    for (let i = 0; i < byteChars.length; i++) {
      byteArray[i] = byteChars.charCodeAt(i);
    }
    const blob = new Blob([byteArray], { type: 'video/mp4' });

    // Step 1: POST start — get session URL
    const startResp = await _originalFetch('/fx/api/upload-video?action=start', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'X-Upload-Project-Id': projectId || '',
        'X-Upload-Content-Type': 'video/mp4',
        'X-Upload-Content-Length': blob.size.toString(),
      },
    });
    const sessionUrl = startResp.headers.get('X-Upload-Session-Url') || '';
    const startData = await startResp.json().catch(() => ({}));
    // sessionUrl may be in header OR in response body
    const finalSessionUrl = sessionUrl || startData.sessionUrl || '';
    startData._sessionUrl = finalSessionUrl;
    startData._status = startResp.status;

    if (!finalSessionUrl) {
      window.dispatchEvent(new CustomEvent('UPLOAD_VIDEO_RESULT', {
        detail: { requestId, error: 'NO_SESSION_URL', startData },
      }));
      return;
    }

    // Step 2: PUT directly to GCS session URL with resumable upload headers
    const uploadResp = await _originalFetch(finalSessionUrl, {
      method: 'PUT',
      body: blob,
      headers: {
        'Content-Type': 'video/mp4',
        'X-Goog-Upload-Command': 'upload, finalize',
        'X-Goog-Upload-Offset': '0',
      },
    });
    const uploadData = await uploadResp.json().catch(() => ({}));
    uploadData._status = uploadResp.status;

    window.dispatchEvent(new CustomEvent('UPLOAD_VIDEO_RESULT', {
      detail: { requestId, startData, uploadData, status: uploadResp.status },
    }));
  } catch (e) {
    window.dispatchEvent(new CustomEvent('UPLOAD_VIDEO_RESULT', {
      detail: { requestId, error: e.message },
    }));
  }
});

// ─── [FLOW V2 — 11/09/2026] UI DRIVER cho flow.google.com ─────────────────────
// Flow v2 không còn API `aisandbox-pa` + Bearer; trang chỉ gọi `…/data/batchexecute`
// bằng XHR (cookie + at=). Driver này KHÔNG dựng lại RPC: nó lái UI (chip cài đặt →
// Slate editor → nút gửi) rồi NGHE response batchexecute để ghép prompt ↔ media và lấy
// URL video (`as29s` → payload[7][0][8] = https://flow-content.google/video/<id>?sig).
// Giao thức với content.js: window event `FLOW_UI_GENERATE` → `FLOW_UI_GENERATE_RESULT`.
// Quan sát thật 11/09: submit=`YhhmEf` (RES [null, credits, [[mediaId,…,[title,ts,…,opId]]]]),
// poll=`jwpduf([[opId]])` (không mang URL), credits=`nzlxg` (RES [credits,…]).
(() => {
  if (window.__flowAgentDriver) return;
  const D = { listeners: new Set(), lastCredits: null };
  window.__flowAgentDriver = D;

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const _XHR = window.XMLHttpRequest;  // giữ ctor gốc cho replay as29s (tránh vòng wrap của fetch)
  const norm = (s) => String(s || '').normalize('NFKC').replace(/\s+/g, ' ').trim().toLowerCase();
  const unesc = (t) => String(t || '').replace(/\\u0026/g, '&').replace(/\\\//g, '/');
  const stripPrefix = (t) => String(t || '').replace(/^\)\]\}'\s*/, '');
  const mkErr = (code, msg) => { const e = new Error(msg || code); e.code = code; return e; };

  // wrb.fr rows → [{rpc, payload}]
  function parseRows(text) {
    const out = [];
    for (const line of stripPrefix(text).split('\n')) {
      if (!line.startsWith('[[')) continue;
      let arr; try { arr = JSON.parse(line); } catch (e) { continue; }
      for (const it of arr) {
        if (Array.isArray(it) && it[0] === 'wrb.fr' && typeof it[1] === 'string') {
          let p = null; try { p = JSON.parse(it[2]); } catch (e) {}
          out.push({ rpc: it[1], payload: p });
        }
      }
    }
    return out;
  }

  function broadcast(url, reqBody, resText, fromXhr) {
    const rpc = (String(url).match(/rpcids=([^&]+)/) || [])[1] || '';
    // Flow v2 dùng XHR → hook fetch cũ (TRPC_MEDIA_URLS) không thấy; bổ sung cho XHR.
    if (fromXhr) {
      try {
        if (resText.includes('flow-content.google/') || resText.includes('storage.googleapis.com/ai-sandbox-videofx/')) {
          window.dispatchEvent(new CustomEvent('TRPC_MEDIA_URLS', { detail: { url, body: __normEsc(resText) } }));
        }
      } catch (e) {}
    }
    // Credits quan sát được: nzlxg → [credits,…] ; YhhmEf → [null, credits, …]
    try {
      if (rpc === 'nzlxg' || rpc === 'YhhmEf') {
        for (const r of parseRows(resText)) {
          if (r.rpc === 'nzlxg' && Array.isArray(r.payload) && typeof r.payload[0] === 'number') D.lastCredits = r.payload[0];
          if (r.rpc === 'YhhmEf' && Array.isArray(r.payload) && typeof r.payload[1] === 'number') D.lastCredits = r.payload[1];
        }
        if (D.lastCredits !== null) window.dispatchEvent(new CustomEvent('FLOW_CREDITS_OBSERVED', { detail: { credits: D.lastCredits } }));
      }
    } catch (e) {}
    for (const fn of D.listeners) { try { fn(rpc, resText, reqBody || ''); } catch (e) {} }
  }

  // Hook XHR (request body + response) — chỉ batchexecute
  const _xo = XMLHttpRequest.prototype.open, _xs = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u, ...rest) { this.__faUrl = String(u || ''); return _xo.call(this, m, u, ...rest); };
  XMLHttpRequest.prototype.send = function (body) {
    const u = this.__faUrl || '';
    try {
      const wp = window.__WANTPROMPT;
      if (wp) {
        let rq = ''; if (typeof body === 'string') rq = body; else if (body) rq = '(' + ((body.constructor && body.constructor.name) || 'body') + ')';
        if (rq.indexOf(wp) >= 0) {
          this.addEventListener('load', () => { try { window.__FLOWLOG2 = window.__FLOWLOG2 || []; window.__FLOWLOG2.push({ u: 'XHR ' + String(u).slice(-64), rh: true, req: rq.slice(0, 260), res: String(this.responseText || '').slice(0, 360) }); if (window.__FLOWLOG2.length > 8) window.__FLOWLOG2.shift(); } catch (e) {} });
        }
      }
    } catch (e) {}
    if (u.includes('/data/batchexecute')) {
      let rb = ''; try { rb = typeof body === 'string' ? body : (body ? String(body) : ''); } catch (e) {}
      // [FLOW V2] Lưu template as29s (URL + body có at=token) để REPLAY lấy URL video khi cần —
      // tránh phải click mở tile (tile-click qua synthetic event không điều hướng router ổn định).
      if (u.includes('rpcids=as29s') && rb) D.as29sTemplate = { url: u, body: rb };
      this.addEventListener('load', () => { try { broadcast(u, rb, String(this.responseText || ''), true); } catch (e) {} });
    }
    return _xs.call(this, body);
  };
  // Hook fetch (phòng khi Flow đổi sang fetch) — không dispatch TRPC_MEDIA_URLS (hook cũ ở trên đã lo)
  const _f = window.fetch;
  window.fetch = async function (...a) {
    const res = await _f.apply(this, a);
    try {
      const u = typeof a[0] === 'string' ? a[0] : ((a[0] && a[0].url) || '');
      if (u.includes('/data/batchexecute')) {
        let rb = ''; try { const b = a[1] && a[1].body; rb = typeof b === 'string' ? b : (b ? String(b) : ''); } catch (e) {}
        res.clone().text().then((t) => broadcast(u, rb, t, false)).catch(() => {});
      }
    } catch (e) {}
    return res;
  };

  // ── DOM helpers: dò theo text/role (locale-tolerant), KHÔNG theo class ──
  // Query xuyên shadow DOM (app dùng custom element <flow-…>)
  // Quét shadow host tối đa 1 lần/800ms (quét '*' mỗi query làm popoverRoot chậm hàng chục giây)
  let _shadowCache = { t: 0, roots: [] };
  function shadowRoots() {
    const now = Date.now();
    if (now - _shadowCache.t > 800) { const roots = []; for (const el of document.querySelectorAll('*')) { if (el.shadowRoot) roots.push(el.shadowRoot); } _shadowCache = { t: now, roots }; }
    return _shadowCache.roots;
  }
  function deepAll(sel, root) {
    const out = []; const scope = root || document;
    try { scope.querySelectorAll(sel).forEach((e) => out.push(e)); } catch (e) {}
    for (const sr of shadowRoots()) { if (root && root !== document && !(root.contains && root.contains(sr.host))) continue; try { sr.querySelectorAll(sel).forEach((e) => out.push(e)); } catch (e) {} }
    return out;
  }
  const $$ = deepAll;
  // Overlay position:fixed có offsetParent=null → dùng getClientRects thay vì offsetParent
  const visible = (el) => { if (!el) return false; try { if (!el.getClientRects().length) return false; const cs = getComputedStyle(el); return cs.visibility !== 'hidden' && cs.display !== 'none'; } catch (e) { return false; } };
  const up = (el) => (el && (el.parentElement || (el.getRootNode && el.getRootNode().host))) || null;
  // Tab/nút của Flow có ligature icon đứng trước text ("videocam video", "crop_16_9 16:9") → khớp đuôi
  const RE_VIDEO = /video$/i;   // neo đuôi: "videocamvideo" (icon dính liền) vẫn khớp
  // textContent (không ép layout như innerText); khớp regex TRƯỚC rồi mới kiểm visible (đắt hơn)
  const textOf = (el) => norm(el && el.textContent);
  // Nhãn = textContent TRỪ phần ligature icon (mat-icon / material-symbols): "videocamVideo" → "video",
  // "crop_16_916:9" → "16:9". Fallback innerText (có khoảng trắng do layout) cho regex (^|\s)…$.
  function labelOf(el) {
    if (!el) return '';
    let t = el.textContent || '';
    try { el.querySelectorAll('mat-icon,[class*="material-symbols"],[class*="material-icons"],[class*="mat-icon"]').forEach((ic) => { t = t.replace(ic.textContent || '', ' '); }); } catch (e) {}
    return norm(t);
  }
  // KHÔNG fallback innerText: innerText ép layout cho TỪNG nút (gallery có hàng trăm nút) → chậm hàng chục giây
  const findBtn = (re, root) => $$('button,[role="button"],[role="tab"],[role="option"],[role="menuitem"]', root).find((b) => re.test(labelOf(b)) && visible(b));
  // [FLOW V2 11/09] Native .click() — Angular Material NHẬN native click ổn định; synthetic pointer/
  // mouse events chập chờn (mở popover lúc được lúc không). Đã đo: chip.click() mở popover 100%.
  function realClick(el) { try { el.click(); } catch (e) {} }
  async function waitFor(fn, ms, step) { const t0 = Date.now(); while (Date.now() - t0 < ms) { const v = fn(); if (v) return v; await sleep(step || 150); } return null; }
  const projectId = () => { const m = location.pathname.match(/\/project\/([0-9a-f-]{36})/i); return m ? m[1] : null; };
  // Thanh prompt của Flow v2 là <flow-base-prompt-box> (KHÔNG có <form>): container = tổ tiên
  // gần nhất của nút gửi có chứa contenteditable.
  function promptForm() {
    const sub = $$('button[type="submit"]').find(visible);
    let form = null;
    if (sub) { let el = up(sub), hops = 0; while (el && hops < 10) { if (el.querySelector && el.querySelector('[contenteditable="true"]')) { form = el; break; } el = up(el); hops++; } }
    return { form, sub };
  }
  function editorEl() { const { form } = promptForm(); return ($$('[contenteditable="true"]', form || document).find(visible)) || $$('[contenteditable="true"]').find(visible) || null; }
  function chipBtn() {
    const { form, sub } = promptForm(); if (!form) return null;
    const btns = $$('button', form).filter((b) => visible(b) && b !== sub).reverse();
    // Ưu tiên aria-label (vi: "Điều kiện kích hoạt cài đặt"), rồi tới text chip
    return btns.find((b) => /cài đặt|setting/i.test(b.getAttribute('aria-label') || ''))
      || btns.find((b) => /(giây|\bx[1-4]\b|video|hình ảnh|nano|omni|16:9|9:16|720p|360p|crop_)/i.test(textOf(b))) || null;
  }
  const chipText = () => { const c = chipBtn(); return c ? norm(c.innerText) : ''; };

  // [WEVIDEO 16/09] Composer Flow mới có chip "tác nhân" (agent mode): prompt đi qua Gemini agent → vẽ
  // storyboard trước, xếp hàng video, tự chọn 10s → driver hỏng. Khi agent BẬT, chip cài đặt không còn
  // text chế độ ("video · 720p · 8 giây x1") → nhận diện bằng đó rồi bấm nút "tác nhân" để tắt.
  const RE_CHIP_MODE = /(giây|\bx[1-4]\b|video|hình ảnh|image|16:9|9:16|720p|360p)/i;
  const agentOn = () => { const c = chipBtn(); return !(c && RE_CHIP_MODE.test(textOf(c))); };
  const agentBtn = () => {
    const { form } = promptForm();
    const all = $$('button,[role="button"]', form || document).filter(visible);
    return all.find((b) => /^(tác nhân|agent)$/i.test(labelOf(b)))
      || all.find((b) => /tác nhân|agent/i.test((b.getAttribute('aria-label') || '') + ' ' + labelOf(b)) && !/chỉ dẫn|instruction/i.test(b.getAttribute('aria-label') || '')) || null;
  };
  async function ensureAgentOff() {
    for (let a = 0; a < 3 && agentOn(); a++) {
      const b = agentBtn(); if (!b) break;
      realClick(b); await waitFor(() => !agentOn(), 5000);
    }
    return !agentOn();
  }
  // [WEVIDEO 16/09] Cài đặt composer MỚI qua popover radio: chế độ (hình ảnh|video) → tỉ lệ (16:9|9:16)
  // → thời lượng (N giây, chỉ video) → x1. Trả {chip, set} để engine kiểm/log. Gọi TRƯỚC khi gõ prompt
  // (đổi cài đặt làm composer re-render → gõ sau mới an toàn).
  async function applySettings2(kind, aspect, duration) {
    await openPopover();
    const lab = (b) => norm(labelOf(b));
    const radios = () => $$('[role="radio"]').filter(visible);
    const isChk = (b) => !!b && (b.getAttribute('aria-checked') === 'true' || b.getAttribute('aria-selected') === 'true');
    const lastBy = (re) => { const m = radios().filter((b) => re.test(lab(b))); return m[m.length - 1] || null; };
    const pick = async (re, tag) => {
      let b = lastBy(re); if (!b) return tag + '=KHÔNG THẤY';
      if (!isChk(b)) { realClick(b); await sleep(600); b = lastBy(re) || b; }
      return tag + '=' + lab(b) + (isChk(b) ? '✓' : '?');
    };
    const set = [];
    set.push(await pick(kind === 'image' ? /^(hình ảnh|image)$/i : /^video$/i, 'mode'));
    if (!(await waitFor(isOpen, 2500))) await openPopover();   // đổi chế độ → popover re-render
    set.push(await pick(aspect === '16:9' ? /^16:9$/ : /^9:16$/, 'asp'));
    if (kind !== 'image') {
      const dsec = [4, 6, 8, 10].includes(Number(duration)) ? Number(duration) : 8;
      set.push(await pick(new RegExp('^' + dsec + '\\s*(giây|s|sec)'), 'dur'));
    }
    set.push(await pick(/^x1$/i, 'n'));
    const save = $$('button').find((b) => visible(b) && /^(lưu|save)$/i.test(norm(labelOf(b))));
    if (save) { realClick(save); await sleep(600); } else { pressEsc(); await sleep(300); await closePopover(); }
    return { chip: chipText(), set: set.join(' ') };
  }
  // Popover = tổ tiên gần nhất của nút "x1" có chứa cả tab "video" lẫn nút "N giây"
  function popoverRoot() {
    const x1 = $$('button,[role="tab"],[role="option"]').find((b) => visible(b) && /^x1$/i.test(textOf(b)));
    if (!x1) return null;
    let el = up(x1), hops = 0;
    while (el && hops < 12) {
      // Chế độ Ảnh không có hàng "N giây" → chỉ đòi tab Video để nhận diện popover
      if (findBtn(RE_VIDEO, el)) return el;
      el = up(el); hops++;
    }
    return null;
  }
  // [FLOW UI mới 14/09] Popover cài đặt = các role=radio (aspect 16:9/9:16 + count x1..x4). Mở khi thấy radio.
  const isOpen = () => !!$$('[role="radio"]').find((b) => visible(b) && /^(16:9|9:16|x[1-9])$/.test(norm(labelOf(b))));
  // [DIAG 14/09] Liệt kê MỌI nút trong thanh prompt (aria-label ~ text) để soi khi selector trượt.
  function barDiag() {
    const { form, sub } = promptForm();
    if (!form) {
      const nsub = $$('button[type="submit"]').filter(visible).length;
      const nbtn = $$('button,[role="button"]').filter(visible).length;
      const ned = $$('[contenteditable="true"]').filter(visible).length;
      const all = $$('button,[role="button"]').filter(visible)
        .map((b) => ((b.getAttribute('aria-label') || '') + '|' + norm(labelOf(b))).slice(0, 26))
        .slice(0, 28).join(' ');
      return '(no form; #submit=' + nsub + ' #btn=' + nbtn + ' #edit=' + ned + ') [' + all + ']';
    }
    return $$('button', form).filter(visible).map((b) => {
      const al = (b.getAttribute('aria-label') || '').slice(0, 26);
      const tx = norm(labelOf(b)).slice(0, 20);
      return (b === sub ? 'SUB<' : '<') + al + '|' + tx + '>';
    }).join(' ');
  }
  // [FLOW UI mới] Bấm chip "Cài đặt" (toggle) → chờ popover radio hiện. Native click tin cậy.
  async function openPopover() {
    for (let a = 0; a < 6; a++) {
      if (isOpen()) return true;
      const c = await waitFor(chipBtn, 3000);
      if (!c) throw mkErr('NO_SETTINGS_CHIP', 'openPopover vòng ' + a + ' @ ' + location.pathname + ' — nút thanh: ' + barDiag());
      realClick(c); await waitFor(isOpen, 2500);
    }
    throw mkErr('NO_POPOVER', 'không mở popover cài đặt — ' + barDiag());
  }
  // [FLOW V2 11/09] Đóng bằng phím Escape (click editor để đóng gây lệch focus → insertPrompt hỏng).
  function pressEsc() { for (const t of ['keydown', 'keyup']) { const ev = { key: 'Escape', code: 'Escape', keyCode: 27, which: 27, bubbles: true, cancelable: true }; try { document.dispatchEvent(new KeyboardEvent(t, ev)); } catch (e) {} try { (editorEl() || document.body).dispatchEvent(new KeyboardEvent(t, ev)); } catch (e) {} } }
  async function closePopover() { for (let a = 0; a < 5 && isOpen(); a++) { pressEsc(); await waitFor(() => !isOpen(), 1500); } }
  async function clickIn(root, re, code) {
    const b = findBtn(re, root); if (!b) throw mkErr(code, 'không thấy nút khớp ' + re);
    realClick(b); await sleep(250); return b;
  }
  // [FLOW UI mới 14/09] Cài đặt qua radio. Popover có 2 khối: ẢNH (aspect 16:9/4:3/1:1/3:4/9:16 + count)
  // rồi VIDEO (aspect chỉ 16:9/9:16 + count x1..x4). Khối VIDEO đứng SAU → lấy "lần xuất hiện cuối".
  // KHÔNG có chọn thời lượng ở UI mới → bỏ qua duration. App luôn 9:16 + x1 (đúng mặc định video).
  async function applySettings(aspect, duration) {
    await openPopover();
    const wantA = aspect === '16:9' ? '16:9' : '9:16';
    const lab = (b) => norm(labelOf(b));
    const isChk = (b) => b.getAttribute('aria-checked') === 'true';
    const radios = () => $$('[role="radio"]').filter(visible);
    const lastByLabel = (l) => { const m = radios().filter((b) => lab(b) === l); return m[m.length - 1] || null; };
    const setDone = [];
    const isSel = (b) => b && (b.getAttribute('aria-checked') === 'true' || b.getAttribute('aria-selected') === 'true');
    // 1) CHẾ ĐỘ = video. Composer mặc định "hình ảnh" (nano banana) → phải bật "video" để ra CLIP
    //    (model video mặc định của account, vd omni). Bật TRƯỚC khi chèn prompt (re-render xong mới gõ).
    const modeBtn = (want) => $$('[role="radio"],[role="tab"],[role="menuitemradio"],[role="option"],button,[role="button"]')
      .filter(visible).find((b) => lab(b) === want);
    let vm = modeBtn('video');
    if (vm && !isSel(vm)) { realClick(vm); await sleep(1500); vm = modeBtn('video'); }
    setDone.push('mode=video' + (vm ? (isSel(vm) ? '✓' : '(clicked)') : 'KHÔNG THẤY'));
    // 2) aspect VIDEO (radio cuối khớp — khối video đứng sau khối ảnh) + 3) count x1 (app luôn n=1)
    const a = lastByLabel(wantA);
    if (a) { if (!isChk(a)) { realClick(a); await sleep(350); } setDone.push('asp=' + wantA + (isChk(a) ? '✓' : '?')); }
    else setDone.push('asp=KHÔNG THẤY');
    const c = lastByLabel('x1');
    if (c) { if (!isChk(c)) { realClick(c); await sleep(350); } setDone.push('x1' + (isChk(c) ? '✓' : '?')); }
    // 4) đóng popover: nút "lưu" nếu có, không thì Escape
    const save = $$('button').find((b) => visible(b) && /^lưu$/i.test(norm(labelOf(b))));
    if (save) { realClick(save); await sleep(600); } else { pressEsc(); await sleep(300); await closePopover(); }
    if (!a) throw mkErr('NO_ASPECT', 'không thấy radio aspect ' + wantA + ' — ' + barDiag());
    return 'newUI ' + setDone.join(' ');
  }
  function fiberEditor(el) {
    const key = Object.keys(el).find((k) => k.startsWith('__reactFiber$')); let f = key ? el[key] : null; let hops = 0;
    while (f && hops < 50) {
      for (const bag of [f.memoizedProps, f.memoizedState, f.stateNode]) {
        if (!bag || typeof bag !== 'object') continue;
        for (const v of Object.values(bag)) { if (v && typeof v === 'object' && typeof v.insertText === 'function') return v; }
      }
      f = f.return; hops++;
    }
    return null;
  }
  async function clearEditor() { const el = editorEl(); if (!el) return; el.focus(); try { document.execCommand('selectAll', false, null); document.execCommand('delete', false, null); } catch (e) {} await sleep(100); }
  // [FLOW UI mới] Gõ TRUSTED qua background (chrome.debugger Input.insertText) — editor mới bỏ synthetic.
  function requestTextInsert(text) {
    return new Promise((resolve) => {
      const rid = 'ti' + Date.now() + '_' + Math.random().toString(36).slice(2);
      const h = (e) => { if (e.detail && e.detail.rid === rid) { window.removeEventListener('FLOW_INSERT_TEXT_DONE', h); resolve(e.detail); } };
      window.addEventListener('FLOW_INSERT_TEXT_DONE', h);
      window.dispatchEvent(new CustomEvent('FLOW_INSERT_TEXT', { detail: { rid, text } }));
      setTimeout(() => { window.removeEventListener('FLOW_INSERT_TEXT_DONE', h); resolve({ ok: false, error: 'ti-timeout' }); }, 20000);
    });
  }
  async function insertPrompt(text) {
    await closePopover();  // đóng popover để editor không bị che
    const el = editorEl(); if (!el) throw mkErr('NO_EDITOR', 'không thấy ô prompt (contenteditable)');
    el.focus(); await sleep(150);
    await clearEditor(); el.focus(); await sleep(120);
    const putCaret = () => { try { const s = window.getSelection(); const r = document.createRange(); r.selectNodeContents(el); r.collapse(false); s.removeAllRanges(); s.addRange(r); } catch (e) {} };
    putCaret();
    const ok = () => norm(el.innerText).includes(norm(text).slice(0, 24));
    let via = '';
    // 1) TRUSTED insert qua debugger (chuẩn cho editor mới — model mới nhận)
    el.focus(); putCaret();
    const res = await requestTextInsert(text); via = 'dbg:' + (res && res.ok ? 'ok' : (res && res.error) || '?'); await sleep(500);
    // 2) fallback fiber (Slate cũ nếu còn)
    if (!ok()) { const ed = fiberEditor(el); if (ed) { try { el.focus(); putCaret(); ed.insertText(text); via += '+fiber'; } catch (e) {} await sleep(200); } }
    // 3) fallback execCommand
    if (!ok()) { try { el.focus(); putCaret(); document.execCommand('insertText', false, text); el.dispatchEvent(new InputEvent('input', { inputType: 'insertText', data: text, bubbles: true })); } catch (e) {} await sleep(200); via += '+exec'; }
    if (!ok()) throw mkErr('PROMPT_INSERT_FAILED', 'via=' + via + ' editor="' + norm(el.innerText).slice(0, 60) + '"');
    return via;
  }
  function decodeReq(reqBody) { try { const m = String(reqBody || '').match(/f\.req=([^&]*)/); return m ? decodeURIComponent(m[1].replace(/\+/g, ' ')) : String(reqBody || ''); } catch (e) { return String(reqBody || ''); } }
  // Ghép prompt ↔ media: đúng response YhhmEf có REQUEST chứa prompt của mình (fail-closed)
  function armCorrelation(prompt, ms) {
    const want = norm(prompt);
    // f.req là JSON → prompt có ký tự ngoài ASCII/dấu nháy bị escape (\uXXXX, \") → so cả bản escape
    const wantJson = norm(JSON.stringify(String(prompt || '')).slice(1, -1));
    return new Promise((resolve, reject) => {
      let done = false;
      const seen = {};        // [DIAG] rpc -> số lần thấy
      const mine = [];        // [DIAG] rpc mà REQUEST chứa prompt của mình (+ mẫu payload)
      const timer = setTimeout(() => {
        if (done) return; done = true; D.listeners.delete(fn);
        let ed = '';
        try { ed = norm((editorEl() || {}).innerText || '').slice(0, 60); } catch (e) {}
        reject(mkErr('CORRELATION_TIMEOUT', 'editorNow="' + ed + '" ins[' + (window.__INSINFO || '?') + '] seen=' + JSON.stringify(seen) + ' | mine=' + JSON.stringify(mine).slice(0, 400)));
      }, ms);
      const fn = (rpc, resText, reqBody) => {
        if (done) return;
        seen[rpc] = (seen[rpc] || 0) + 1;
        const reqN = norm(decodeReq(reqBody));
        const isMine = reqN.includes(want) || reqN.includes(wantJson);
        if (isMine) {                       // [DIAG] chụp cấu trúc mọi row của RPC submission
          for (const r of parseRows(resText)) {
            if (Array.isArray(r.payload)) mine.push({ rpc: r.rpc, p: JSON.stringify(r.payload).slice(0, 220) });
          }
        }
        if (rpc !== 'YhhmEf' || !isMine) return;
        for (const r of parseRows(resText)) {
          if (r.rpc !== 'YhhmEf' || !Array.isArray(r.payload)) continue;
          const credits = r.payload[1]; const item = r.payload[2] && r.payload[2][0];
          const mediaId = item && item[0]; const meta = item && item[3];
          done = true; clearTimeout(timer); D.listeners.delete(fn);
          if (!mediaId) { reject(mkErr('SUBMIT_REJECTED', 'YhhmEf không trả mediaId: ' + String(JSON.stringify(r.payload)).slice(0, 160))); return; }
          resolve({ mediaId, opId: meta && meta[4], title: meta && meta[0], credits });
          return;
        }
      };
      D.listeners.add(fn);
    });
  }
  const ERR_RE = /(PUBLIC_ERROR[A-Z_]*|[A-Z_]*_FAILED|[A-Z_]*_FAILURE|SEXUALLY_EXPLICIT|CHILD_SAFETY|[A-Z_]*QUOTA[A-Z_]*|RATE_LIMIT[A-Z_]*|CAPTCHA[A-Z_]*)/;
  const _UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
  // REPLAY 1 lần lệnh as29s (same-origin flow.google.com, cookie đi kèm) với mediaId cần → URL video
  // [7][0][8], hoặc null nếu CHƯA render xong / lỗi mạng. KHÔNG dựng lại RPC: copy nguyên request thật
  // của trang (D.as29sTemplate) rồi CHỈ thay UUID mediaId ở đầu f.req.
  async function fetchVideoUrlOnce(ids) {
    const tpl = D.as29sTemplate;
    if (!tpl || !_UUID.test(tpl.body)) return null;
    const idList = (Array.isArray(ids) ? ids : [ids]).filter(Boolean).map((x) => String(x).toLowerCase());
    // [FLOW V2 11/09] URL video nằm dưới OPERATION id (meta[4]), KHÔNG phải submit mediaId → thử id đầu.
    const body = tpl.body.replace(_UUID, idList[0]);
    // [FLOW V2 11/09] DÙNG XHR, KHÔNG dùng fetch: window.fetch bị injected.js (2 lớp) + extension
    // khác (TobyFlow) wrap chồng → gọi qua fetch gây ĐỆ QUY VÔ HẠN (Maximum call stack). XHR thô
    // (_XHR lưu từ document_start) không dính vòng đó.
    let text;
    try {
      text = await new Promise((resolve, reject) => {
        const x = new _XHR();
        x.open('POST', tpl.url, true);
        x.setRequestHeader('content-type', 'application/x-www-form-urlencoded;charset=UTF-8');
        x.withCredentials = true;
        x.onload = () => (x.status >= 200 && x.status < 300) ? resolve(x.responseText || '') : reject(new Error('as29s HTTP ' + x.status));
        x.onerror = () => reject(new Error('as29s network'));
        x.send(body);
      });
    } catch (e) { return null; }
    for (const row of parseRows(text)) {
      if (row.rpc !== 'as29s' || !Array.isArray(row.payload)) continue;
      if (!idList.includes(String(row.payload[0]).toLowerCase())) continue;
      const u = row.payload[7] && row.payload[7][0] && row.payload[7][0][8];
      if (typeof u === 'string' && u.includes('/video/')) return u;
    }
    return null;
  }
  // Poll replay tới khi có URL (render xong) hoặc hết giờ. Bắt lỗi content-filter qua jwpduf nếu trang có poll.
  async function waitForVideoUrl(ids, ms) {
    // Cap 200s: clip 4-10s render ~40-90s; đừng để vượt timeout content.js (timeoutMs+10s).
    const deadline = Date.now() + Math.min(ms, 200000);
    const idArr = (Array.isArray(ids) ? ids : [ids]).filter(Boolean);
    const idHit = (t) => idArr.some((i) => t.includes(String(i)));
    let genErr = null;
    const errFn = (rpc, resText) => { if (rpc === 'jwpduf' && idHit(resText)) { const em = unesc(resText).match(ERR_RE); if (em) genErr = em[1]; } };
    D.listeners.add(errFn);
    try {
      await waitFor(() => D.as29sTemplate, 15000);
      while (Date.now() < deadline) {
        if (genErr) throw mkErr('GEN_FAILED:' + genErr, 'Flow báo lỗi ' + genErr + ' — không retry');
        const u = await fetchVideoUrlOnce(idArr);
        if (u) return u;
        await sleep(5000);
      }
      throw mkErr('COMPLETION_TIMEOUT', 'không thấy URL video (as29s replay theo opId/mediaId)');
    } finally { D.listeners.delete(errFn); }
  }

  // [OMNI] Bắt URL video từ response tRPC (window.__FLOWLOG log các response chứa media URL).
  function _extractVideoUrl(body) {
    if (!body) return null;
    // ĐÚNG regex background.js dùng; ưu tiên /video/ rồi mới /image/
    const RE = /https:\/\/(?:storage\.googleapis\.com\/ai-sandbox-videofx|flow-content\.google)\/(?:image|video)\/[0-9a-f-]{36}\?[^"'\s\\]+/g;
    const all = String(body).match(RE) || [];
    return all.find((u) => /\/video\//.test(u)) || null;   // CHỈ nhận video, bỏ image
  }
  async function omniWaitVideo(startN, ms) {
    const t0 = Date.now();
    while (Date.now() - t0 < ms) {
      const logs = window.__FLOWLOG || [];
      for (let i = Math.max(0, startN); i < logs.length; i++) {
        const u = _extractVideoUrl(logs[i].body);
        if (u) return { videoUrl: u, mediaId: 'omni-' + i };
      }
      await sleep(1500);
    }
    return null;
  }

  window.addEventListener('FLOW_UI_GENERATE', async (ev) => {
    const d = (ev && ev.detail) || {};
    const requestId = d.requestId;
    const reply = (x) => window.dispatchEvent(new CustomEvent('FLOW_UI_GENERATE_RESULT', { detail: Object.assign({ requestId }, x) }));
    try {
      if (String(d.prompt).trim() === '__VERSION__') {   // [WEVIDEO 16/09] bản injected đang chạy + tab (0 credit, dùng kèm dry_run)
        reply({ error: 'VERSION v=wevideo-16sep-1 url=' + location.pathname + ' agentOn=' + agentOn() + ' chip=' + chipText(), code: 'VERSION' });
        return;
      }
      if (String(d.prompt).trim() === '__TESTPING__') {   // test round-trip injected↔background (không debugger)
        const r = await requestTextInsert('__PING__');
        reply({ error: 'PING ' + JSON.stringify(r), code: 'PING' });
        return;
      }
      if (String(d.prompt).trim().startsWith('__FETCHBYTES__')) {   // echo URL (nhúng trong prompt) → SW tự tải bytes → media_blobs
        const fu = String(d.prompt).trim().slice('__FETCHBYTES__'.length).trim();
        const fmid = (fu.match(/\/(?:image|video)\/([0-9a-f-]{36})/) || [])[1] || d.mediaId;
        reply({ videoUrl: fu || undefined, mediaId: fmid || undefined });
        return;
      }
      if (String(d.prompt).trim() === '__PLAYTILE__') {   // click tile video mới nhất → Flow fetch URL /video/ (SW bắt)
        const tl = $$('flow-video-tile').filter(visible)[0] || document.querySelector('flow-video-tile');
        reply({ clicked: !!tl });   // trả lời TRƯỚC (click sẽ điều hướng sang /edit/ → huỷ injected)
        if (tl) { try { tl.scrollIntoView({ block: 'center' }); } catch (e) {} await sleep(200); realClick(tl); }
        return;
      }
      if (String(d.prompt).trim() === '__GALLERY__') {   // quay về gallery project (sau khi play_tile sang /edit/)
        const pid2 = projectId();
        reply({ back: true, projectId: pid2 });   // trả lời TRƯỚC khi điều hướng
        if (pid2 && /\/edit\//.test(location.pathname)) location.href = '/project/' + pid2;
        return;
      }
      if (String(d.prompt).trim() === '__CLICKNEXT__') {   // vượt trang chọn tài khoản (/404: "tiếp theo")
        await sleep(1200);
        const b = $$('button,[role="button"],a').filter(visible).find((x) => /tiếp theo|next|continue|tiếp tục/i.test((x.getAttribute('aria-label') || '') + ' ' + norm(labelOf(x))));
        if (b) { realClick(b); await sleep(2500); }
        reply({ error: 'CLICKNEXT clicked=' + (b ? 'yes' : 'no') + ' now=' + location.pathname, code: 'CLICKNEXT' });
        return;
      }
      if (String(d.prompt).trim() === '__VIDEOSCAN__') {   // [OMNI DIAG] soi mọi URL video khả kiến trên trang (0 credit)
        await sleep(1500);
        const RE = /https:\/\/(?:storage\.googleapis\.com\/ai-sandbox-videofx|flow-content\.google|[a-z0-9-]+\.googleusercontent\.com)\/(?:image|video)\/[0-9a-f-]{36}\?[^"'\s\\]+/g;
        const vids = $$('video').map((v) => ({ src: (v.currentSrc || v.src || '').slice(0, 60), poster: (v.poster || '').slice(0, 60) }));
        const srcs = [...$$('video,source').map((v) => v.src || v.currentSrc || '')].filter((u) => /^https?:/.test(u));
        let html = '';
        try { html = document.documentElement.outerHTML; } catch (e) {}
        const inHtml = [...new Set((html.match(RE) || []))];
        const flog = window.__FLOWLOG || [];
        let flogVid = [];
        for (const e of flog) { const m = String(e && e.body || '').match(RE); if (m) flogVid.push(...m); }
        flogVid = [...new Set(flogVid)];
        const dl = $$('button,[role="button"],a').filter(visible).filter((b) => /tải|download|lưu|save/i.test((b.getAttribute('aria-label') || '') + ' ' + norm(labelOf(b)))).map((b) => (b.getAttribute('aria-label') || norm(labelOf(b))).slice(0, 24));
        reply({ error: 'VIDEOSCAN nVideo=' + vids.length + ' vids=' + JSON.stringify(vids)
          + ' httpSrcs=' + JSON.stringify(srcs.slice(0, 4))
          + ' inHtmlVideo=' + JSON.stringify(inHtml.filter((u) => /\/video\//.test(u)).slice(0, 3))
          + ' inHtmlImage=' + JSON.stringify(inHtml.filter((u) => /\/image\//.test(u)).slice(0, 2))
          + ' flogLen=' + flog.length + ' flogVid=' + JSON.stringify(flogVid.slice(0, 3))
          + ' dlBtns=' + JSON.stringify([...new Set(dl)].slice(0, 6)), code: 'VIDEOSCAN' });
        return;
      }
      if (String(d.prompt).trim() === '__HOMEDUMP__') {   // dump mọi trang: link project + nút (tìm project hợp lệ / nút tạo mới)
        await sleep(3500);
        const links = [...new Set($$('a').filter(visible).map((a) => a.getAttribute('href') || '').filter((h) => /\/project\//.test(h)))].slice(0, 12);
        const btns = [...new Set($$('button,[role="button"]').filter(visible).map((b) => (b.getAttribute('aria-label') || norm(labelOf(b)) || '').slice(0, 32)).filter((t) => t))].slice(0, 45);
        reply({ error: 'HOMEDUMP url=' + location.pathname + ' | links=' + JSON.stringify(links) + ' | btns=' + JSON.stringify(btns), code: 'HOMEDUMP' });
        return;
      }
      const pid = projectId();
      if (!pid || /\/edit\//.test(location.pathname)) throw mkErr('NO_PROJECT_PAGE', 'cần tab đang ở flow.google.com/project/<id> (gallery), hiện: ' + location.pathname);
      const aspect = d.aspect === '16:9' ? '16:9' : '9:16';
      const duration = [4, 6, 8, 10].includes(Number(d.duration)) ? Number(d.duration) : 8;
      // [DIAG 14/09] Chụp cấu trúc: "__DUMP__" (fresh) · "__DUMP2__" (click chip rồi chụp popover).
      if (String(d.prompt).trim().startsWith('__DUMP')) {
        await waitFor(() => promptForm().sub || $$('[contenteditable="true"]').filter(visible).length, 15000);
        const bi = (b) => ({ al: (b.getAttribute('aria-label') || '').slice(0, 40), tx: norm(labelOf(b)).slice(0, 30), role: b.getAttribute('role') || '', ac: b.getAttribute('aria-checked') || b.getAttribute('aria-selected') || '' });
        if (String(d.prompt).trim() === '__DUMP2__') {
          const c = chipBtn(); if (c) { realClick(c); await sleep(1500); }
        }
        if (String(d.prompt).trim() === '__DUMP3__') {
          const c = chipBtn(); if (c) { realClick(c); await sleep(1500); }
          // click ô model VIDEO (aria-label chứa "tạo video") để bung danh sách model
          const mb = $$('button,[role="button"]').filter(visible).find((b) => /tạo video/i.test(b.getAttribute('aria-label') || ''));
          if (mb) { realClick(mb); await sleep(1500); }
          const items = $$('[role="menuitem"],[role="option"],[role="radio"],li,button').filter(visible)
            .map((b) => norm(labelOf(b))).filter((t) => t && t.length < 40);
          reply({ error: 'DUMP3 modelBtn=' + (mb ? 'yes' : 'no') + ' items=' + JSON.stringify([...new Set(items)].slice(0, 40)), code: 'DUMP3' });
          return;
        }
        if (String(d.prompt).trim() === '__DUMP6__') {   // soi component Angular của editor
          const el = editorEl();
          const out = { hasEl: !!el, tag: el && el.tagName, hasNg: !!window.ng, ngKeys: el ? Object.keys(el).filter((k) => /^__ng|^__react|^ng/i.test(k)) : [] };
          try {
            if (window.ng && el) {
              let node = el, comp = null, tries = 0;
              while (node && tries < 6 && !comp) { try { comp = window.ng.getComponent(node); } catch (e) {} node = node.parentElement; tries++; }
              if (comp) {
                out.comp = comp.constructor && comp.constructor.name;
                out.fields = Object.keys(comp).slice(0, 45);
                out.methods = Object.getOwnPropertyNames(Object.getPrototypeOf(comp) || {}).filter((m) => { try { return typeof comp[m] === 'function'; } catch (e) { return false; } }).slice(0, 35);
              } else out.comp = 'none';
            }
          } catch (e) { out.err = String(e).slice(0, 100); }
          reply({ error: 'DUMP6 ' + JSON.stringify(out).slice(0, 1500), code: 'DUMP6' });
          return;
        }
        if (String(d.prompt).trim() === '__DUMP5__') {   // soi cây fiber editor để tìm API chèn text
          const el = editorEl(); const out = { hasEl: !!el, tag: el && el.tagName, levels: [] };
          if (el) {
            const key = Object.keys(el).find((k) => k.startsWith('__reactFiber$') || k.startsWith('__reactProps$'));
            let f = key ? el[key] : null; let hop = 0;
            while (f && hop < 26) {
              const nm = (f.type && (f.type.displayName || f.type.name)) || (typeof f.type === 'string' ? f.type : '');
              const meths = [];
              for (const bag of [f.memoizedProps, f.memoizedState]) {
                if (!bag || typeof bag !== 'object') continue;
                for (const [k, v] of Object.entries(bag)) {
                  if (v && typeof v === 'object') {
                    const fns = Object.keys(v).filter((kk) => { try { return typeof v[kk] === 'function'; } catch (e) { return false; } });
                    if (fns.some((x) => /insert|apply|command|exec|setValue|onChange|children|selection|focus/i.test(x))) meths.push(k + ':{' + fns.slice(0, 12).join(',') + '}');
                  } else if (typeof v === 'function' && /insert|apply|command|exec|setValue/i.test(k)) meths.push(k + '()');
                }
              }
              if (nm || meths.length) out.levels.push({ h: hop, nm: String(nm).slice(0, 24), meths: meths.slice(0, 6) });
              f = f.return; hop++;
            }
          }
          reply({ error: 'DUMP5 ' + JSON.stringify(out).slice(0, 1500), code: 'DUMP5' });
          return;
        }
        const { form, sub } = promptForm();
        const dump = {
          url: location.pathname,
          nSubmit: $$('button[type="submit"]').filter(visible).length,
          nEditable: $$('[contenteditable="true"]').filter(visible).length,
          nBtn: $$('button,[role="button"],[role="tab"],[role="option"],[role="radio"],[role="menuitem"]').filter(visible).length,
          chip: (() => { const c = chipBtn(); return c ? bi(c) : null; })(),
          formBtns: form ? $$('button', form).filter(visible).map(bi) : [],
          tabs: $$('[role="tab"]').filter(visible).map((b) => norm(labelOf(b)).slice(0, 24)),
          allBtns: $$('button,[role="button"],[role="tab"],[role="option"],[role="radio"],[role="menuitem"]').filter(visible).map(bi).slice(0, 70),
        };
        reply({ error: 'DUMP ' + JSON.stringify(dump), code: 'DUMP' });
        return;
      }
      // chờ composer sẵn sàng (máy chậm/SPA render trễ)
      if (!(await waitFor(() => promptForm().sub, 25000)))
        throw mkErr('PROMPT_BAR_NOT_READY', 'thanh prompt chưa render sau 25s @ ' + location.pathname + ' — nút: ' + barDiag());
      if (!(await waitFor(chipBtn, 15000)))
        throw mkErr('NO_SETTINGS_CHIP', 'chip chưa render sau 15s @ ' + location.pathname + ' — nút: ' + barDiag());

      const putCaret = (el) => { try { const s = window.getSelection(); const r = document.createRange(); r.selectNodeContents(el); r.collapse(false); s.removeAllRanges(); s.addRange(r); } catch (e) {} };

      // [FLOW UI mới — OMNI] PHA 1: CHỈ focus ô soạn. KHÔNG mở popover / KHÔNG đổi model —
      // vì mở popover hay đổi model làm composer RE-RENDER → xoá prompt vừa gõ. Dùng MẶC ĐỊNH
      // của account (model omni 1.1 flash + video 9:16 + x1 — đã xác nhận qua dump).
      if (d.phase === 'prep') {
        await waitFor(() => promptForm().sub, 8000);
        // [WEVIDEO 16/09] tắt agent mode + áp cài đặt (chế độ/tỉ lệ/thời lượng) TRƯỚC khi focus & gõ prompt
        if (!(await ensureAgentOff())) throw mkErr('AGENT_MODE_ON', 'chip "tác nhân" đang bật, không tắt được — ' + barDiag());
        D.lastSettings = await applySettings2(d.kind, d.aspect, d.duration);
        const el = editorEl(); if (!el) throw mkErr('NO_EDITOR', 'không thấy ô prompt');
        el.focus(); await sleep(150); await clearEditor(); el.focus(); await sleep(150); putCaret(el);
        reply({ ready: true, projectId: pid });
        return;
      }
      // [FLOW UI mới] PHA 2: ô soạn đã có prompt (background gõ) → gửi + nghe kết quả.
      if (d.phase === 'submit') {
        const el = editorEl(); const txt = el ? norm(el.innerText) : '';
        const sub = await waitFor(() => { const s = promptForm().sub; return s && !s.disabled ? s : null; }, 6000);
        if (!sub) throw mkErr('SUBMIT_DISABLED', 'nút gửi không bấm được (editor="' + txt.slice(0, 40) + '")');
        if (!txt) throw mkErr('EMPTY_PROMPT', 'ô soạn RỖNG lúc gửi — prompt chưa vào');
        const stg = D.lastSettings || {};
        // [WEVIDEO 16/09] dryRun: KHÔNG bấm gửi (trước đây pha submit bỏ qua dryRun → tốn credit thật)
        if (d.dryRun) { await clearEditor(); reply({ dryRun: true, promptOk: true, editorText: txt.slice(0, 50), chipText: stg.chip, settings: stg.set, projectId: pid, credits: D.lastCredits }); return; }
        sub.click();
        await sleep(4000);   // [OMNI] để submit đăng ký + gen bắt đầu; ENGINE sẽ chờ URL video mới
        reply({ submitted: true, projectId: pid, editorText: txt.slice(0, 50), chipText: stg.chip, settings: stg.set });
        return;
      }

      // (không phase) — 1 pha cũ (fallback). kind=image → BỎ applySettings (dùng model ẢNH mặc định).
      const chip = (d.kind === 'image') ? 'imageMode(default)' : await applySettings(aspect, duration);
      const via = await insertPrompt(String(d.prompt || ''));
      if (d.dryRun) { await clearEditor(); reply({ dryRun: true, chipText: chip, promptOk: true, insertVia: via, projectId: pid, credits: D.lastCredits }); return; }
      // [OMNI 15/09] KHÔNG chờ correlation/URL ở injected (as29s replay hay timeout với omni).
      // Chỉ SUBMIT rồi trả submitted:true — ENGINE (ui.py) poll bridge.media_urls lấy URL mới.
      const el0 = editorEl(); const txt0 = el0 ? norm(el0.innerText) : '';
      const sub = await waitFor(() => { const s = promptForm().sub; return s && !s.disabled ? s : null; }, 3000);
      if (!sub) throw mkErr('SUBMIT_DISABLED', 'nút gửi không bấm được');
      if (!txt0) throw mkErr('EMPTY_PROMPT', 'ô soạn RỖNG lúc gửi — prompt chưa vào (via=' + via + ')');
      // URL media trên trang TRƯỚC submit (để nhận diện cái MỚI sau render). Quét cả outerHTML + <img> src/srcset.
      const _scanUrls = (kindRe) => {
        const RE = /https:\/\/(?:storage\.googleapis\.com\/ai-sandbox-videofx|flow-content\.google|[a-z0-9-]+\.googleusercontent\.com)\/(?:image|video)\/[0-9a-f-]{36}\?[^"'\s\\]+/g;
        let s = '';
        try { s = document.documentElement.outerHTML; } catch (e) {}
        try { for (const im of $$('img')) s += ' ' + (im.getAttribute('src') || '') + ' ' + (im.getAttribute('srcset') || ''); } catch (e) {}
        return [...new Set((s.match(RE) || []).filter((u) => kindRe.test(u)))];
      };
      const kindRe = d.kind === 'image' ? /\/image\// : /\/video\//;
      const kindTag = d.kind === 'image' ? 'image' : 'video';
      const before = _scanUrls(kindRe);
      sub.click();
      await sleep(4000);
      // Nhặt URL media MỚI từ DOM → trả về videoUrl để SW tự tải bytes (CDN cookie-gated, urllib 403).
      // Render omni: ảnh ~40-90s, video lâu hơn → chờ tới ~230s. URL hiện trong trpc trước DOM nên kiên nhẫn.
      const maxIter = d.kind === 'image' ? 75 : 115;
      let foundUrl = null;
      for (let k = 0; k < maxIter && !foundUrl; k++) {
        const now = _scanUrls(kindRe);
        const fresh = now.filter((u) => !before.includes(u));
        if (fresh.length) foundUrl = fresh[fresh.length - 1];
        else await sleep(2000);
      }
      const mid = foundUrl ? ((foundUrl.match(/\/(?:image|video)\/([0-9a-f-]{36})/) || [])[1] || null) : null;
      reply({ submitted: true, kind: kindTag, videoUrl: foundUrl || undefined, mediaId: mid || undefined, projectId: pid, editorText: txt0.slice(0, 50), chipText: chip, insertVia: via });
    } catch (e) {
      reply({ error: (e && e.message) || String(e), code: (e && e.code) || 'DRIVER_ERROR' });
    }
  });
  console.log('[Flow Agent] Flow v2 UI driver ready');
})();
