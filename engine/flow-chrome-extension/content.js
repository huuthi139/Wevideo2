/**
 * Content script — bridge between background.js and injected.js
 * Injects injected.js into MAIN world to access window.grecaptcha
 */
(function () {
  const s = document.createElement('script');
  s.src = chrome.runtime.getURL('injected.js') + '?v=' + chrome.runtime.getManifest().version + '_wv16sep';   // [WEVIDEO 16/09] phá cache injected (reload extension KHÔNG tự làm mới resource này)
  s.onload = () => s.remove();
  (document.head || document.documentElement).appendChild(s);
})();

chrome.runtime.onMessage.addListener((msg, _, reply) => {
  if (msg.type !== 'GET_CAPTCHA') return;

  const { requestId, pageAction } = msg;

  const handler = (e) => {
    if (e.detail?.requestId === requestId) {
      window.removeEventListener('CAPTCHA_RESULT', handler);
      clearTimeout(timer);
      reply({ token: e.detail.token, error: e.detail.error });
    }
  };

  const timer = setTimeout(() => {
    window.removeEventListener('CAPTCHA_RESULT', handler);
    reply({ error: 'CONTENT_TIMEOUT' });
  }, 25000);

  window.addEventListener('CAPTCHA_RESULT', handler);

  window.dispatchEvent(new CustomEvent('GET_CAPTCHA', {
    detail: { requestId, pageAction },
  }));

  return true; // keep channel open for async reply
});

// ─── TRPC Media URL Monitor ─────────────────────────────────
// Forward intercepted TRPC responses with media URLs to background.js
window.addEventListener('TRPC_MEDIA_URLS', (e) => {
  const { url, body } = e.detail || {};
  if (!body) return;
  chrome.runtime.sendMessage({
    type: 'TRPC_MEDIA_URLS',
    trpcUrl: url,
    body,
  }).catch(() => {});
});

// ─── Aisandbox Request Sniffer (via postMessage from MAIN world) ──
window.addEventListener('message', (e) => {
  if (e.data?.type !== '__FLOWKIT_SNIFF__') return;
  const { url, body, method } = e.data;
  if (!url) return;
  chrome.runtime.sendMessage({
    type: 'SNIFFED_AISANDBOX_REQUEST',
    url,
    method,
    payload: body,
    timestamp: Date.now(),
  }).catch(() => {});
});

// ─── Video Upload Relay ─────────────────────────────────────
chrome.runtime.onMessage.addListener((msg, _, reply) => {
  if (msg.type !== 'UPLOAD_VIDEO') return;

  const { requestId, videoBase64, projectId } = msg;

  const handler = (e) => {
    if (e.detail?.requestId === requestId) {
      window.removeEventListener('UPLOAD_VIDEO_RESULT', handler);
      clearTimeout(timer);
      reply(e.detail);
    }
  };

  const timer = setTimeout(() => {
    window.removeEventListener('UPLOAD_VIDEO_RESULT', handler);
    reply({ error: 'UPLOAD_TIMEOUT' });
  }, 120000); // 2 min timeout for large uploads

  window.addEventListener('UPLOAD_VIDEO_RESULT', handler);

  window.dispatchEvent(new CustomEvent('UPLOAD_VIDEO', {
    detail: { requestId, videoBase64, projectId },
  }));

  return true; // keep channel open for async reply
});

// ─── [FLOW UI mới] Gõ prompt TRUSTED: injected.js → background (chrome.debugger Input.insertText) ───
window.addEventListener('FLOW_INSERT_TEXT', (e) => {
  const d = e.detail || {};
  const rid = d.rid;
  const done = (x) => window.dispatchEvent(new CustomEvent('FLOW_INSERT_TEXT_DONE', { detail: Object.assign({ rid }, x) }));
  try {
    chrome.runtime.sendMessage({ type: 'INSERT_TEXT', text: d.text }, (res) => {
      if (chrome.runtime.lastError) { done({ ok: false, error: 'cs-lastErr:' + chrome.runtime.lastError.message }); return; }
      done(res || { ok: false, error: 'cs-nores' });
    });
  } catch (err) { done({ ok: false, error: 'cs-throw:' + ((err && err.message) || err) }); }
});

// ─── [FLOW V2 11/09] UI generate relay: background ⇄ injected.js (MAIN world) ───
// Mirror khối GET_CAPTCHA: background gửi runtime message UI_GENERATE → dispatch window
// event FLOW_UI_GENERATE cho driver (injected.js) → chờ FLOW_UI_GENERATE_RESULT → reply.
chrome.runtime.onMessage.addListener((msg, _, reply) => {
  if (msg.type !== 'UI_GENERATE') return;
  const { requestId, params } = msg;
  const timeoutMs = Number(params && params.timeoutMs) || 420000;

  const handler = (e) => {
    if (e.detail?.requestId === requestId) {
      window.removeEventListener('FLOW_UI_GENERATE_RESULT', handler);
      clearTimeout(timer);
      reply(e.detail);
    }
  };
  const timer = setTimeout(() => {
    window.removeEventListener('FLOW_UI_GENERATE_RESULT', handler);
    reply({ requestId, error: 'CONTENT_TIMEOUT', code: 'CONTENT_TIMEOUT' });
  }, timeoutMs + 10000);

  window.addEventListener('FLOW_UI_GENERATE_RESULT', handler);
  window.dispatchEvent(new CustomEvent('FLOW_UI_GENERATE', {
    detail: Object.assign({ requestId }, params || {}),
  }));
  return true; // keep channel open for async reply
});
