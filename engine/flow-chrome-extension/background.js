/**
 * Flow Agent — Chrome Extension Background Service Worker
 *
 * Connects to local Python agent via WebSocket (agent runs WS server).
 * Captures bearer token, solves reCAPTCHA, proxies API calls through browser.
 */

const AGENT_WS_URL = 'ws://127.0.0.1:8001/ws';
let callbackUrl = 'http://127.0.0.1:3001/api/ext/callback';
// NOTE: This is a browser-restricted public API key — safe to ship in extension bundles.
const API_KEY = '';   // [17/09] gỡ key cũ hardcode (hằng số chết — không dùng ở đâu trong background.js)

let ws = null;
let flowKey = null;
let callbackSecret = null;  // Auth secret for HTTP callback, received from server on WS connect
let state = 'off'; // off | idle | running
let manualDisconnect = false;
let metrics = {
  tokenCapturedAt: null,
  requestCount: 0,   // captcha-consuming requests only (gen image/video/upscale)
  successCount: 0,
  failedCount: 0,
  lastError: null,
};

// ─── URL → Log Type Classifier ─────────────────────────────

// Visible log types — only these appear in the request log
const _VISIBLE_TYPES = new Set(['GEN_IMG', 'GEN_VID', 'GEN_VID_REF', 'UPSCALE', 'TRACKING', 'URL_REFRESH']);

function _classifyApiUrl(url) {
  if (url.includes('uploadImage'))                     return 'UPLOAD';
  if (url.includes('batchGenerateImages'))              return 'GEN_IMG';
  if (url.includes('UpsampleVideo'))                   return 'UPSCALE';
  if (url.includes('ReferenceImages'))                 return 'GEN_VID_REF';
  if (url.includes('batchAsyncGenerateVideo'))          return 'GEN_VID';
  if (url.includes('batchCheckAsync'))                  return 'POLL';
  if (url.includes('upsampleImage'))                   return 'UPS_IMG';
  if (url.includes('/media/'))                         return 'MEDIA';
  if (url.includes('/credits'))                        return 'CREDITS';
  return 'API';
}

// ─── Request Log ────────────────────────────────────────────

let requestLog = [];

function addRequestLog(entry) {
  requestLog.unshift(entry);
  if (requestLog.length > 100) requestLog.pop();
  broadcastRequestLog();
}

function updateRequestLog(id, updates) {
  const entry = requestLog.find((e) => e.id === id);
  if (entry) Object.assign(entry, updates);
  broadcastRequestLog();
}

function broadcastRequestLog() {
  chrome.runtime.sendMessage({ type: 'REQUEST_LOG_UPDATE', log: requestLog }).catch(() => {});
}

// ─── Startup ────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(init);
chrome.runtime.onStartup.addListener(init);
chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === 'reconnect') connectToAgent();
  if (alarm.name === 'keepAlive') keepAlive();
  if (alarm.name === 'flushOutbox') flushOutbox();
  if (alarm.name === 'token-refresh') {
    await captureTokenFromFlowTab();
  }
});

async function init() {
  const data = await chrome.storage.local.get(['flowKey', 'metrics', 'callbackSecret', 'callbackUrl']);
  if (data.flowKey) flowKey = data.flowKey;
  if (data.metrics) Object.assign(metrics, data.metrics);
  if (data.callbackSecret) callbackSecret = data.callbackSecret;
  if (data.callbackUrl) callbackUrl = data.callbackUrl;
  await loadOutbox();
  connectToAgent();
  chrome.alarms.create('keepAlive', { periodInMinutes: 0.4 });
  // Retry any responses left undelivered by a previous worker lifetime.
  chrome.alarms.create('flushOutbox', { periodInMinutes: 0.25 });
  flushOutbox();
}

// ─── Token Capture ──────────────────────────────────────────

chrome.webRequest.onBeforeSendHeaders.addListener(
  (details) => {
    if (!details?.requestHeaders?.length) return;
    const authHeader = details.requestHeaders.find(
      (h) => h.name?.toLowerCase() === 'authorization',
    );
    const value = authHeader?.value || '';
    if (!value.startsWith('Bearer ya29.')) return;

    const token = value.replace(/^Bearer\s+/i, '').trim();
    if (!token) return;

    // Always update — even if same token string, refresh the timestamp
    flowKey = token;
    metrics.tokenCapturedAt = Date.now();
    chrome.storage.local.set({ flowKey, metrics });
    console.log('[Flow Agent] Bearer token captured');

    // Notify agent
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'token_captured', flowKey }));
    }
  },
  { urls: ['https://aisandbox-pa.googleapis.com/*', 'https://labs.google/*'] },
  ['requestHeaders', 'extraHeaders'],
);

let _openingFlowTab = false;

async function captureTokenFromFlowTab() {
  const tabs = await chrome.tabs.query({
    url: ['https://labs.google/fx/tools/flow*', 'https://labs.google/fx/*/tools/flow*'],
  });
  if (!tabs.length) {
    if (_openingFlowTab) {
      console.log('[Flow Agent] Flow tab already opening, skipping');
      return;
    }
    _openingFlowTab = true;
    try {
      console.log('[Flow Agent] No Flow tab found — opening one in background');
      await chrome.tabs.create({ url: 'https://labs.google/fx/tools/flow', active: false });
      await sleep(3000);
      const retryTabs = await chrome.tabs.query({
        url: ['https://labs.google/fx/tools/flow*', 'https://labs.google/fx/*/tools/flow*'],
      });
      if (!retryTabs.length) {
        console.log('[Flow Agent] Flow tab not ready yet after open');
        return;
      }
      await chrome.scripting.executeScript({
        target: { tabId: retryTabs[0].id },
        files: ['content.js'],
      });
      console.log('[Flow Agent] Token refresh triggered on newly opened Flow tab');
    } catch (e) {
      console.error('[Flow Agent] Token refresh failed after opening tab:', e);
    } finally {
      _openingFlowTab = false;
    }
    return;
  }
  try {
    await chrome.scripting.executeScript({
      target: { tabId: tabs[0].id },
      files: ['content.js'],
    });
    console.log('[Flow Agent] Token refresh triggered on Flow tab');
  } catch (e) {
    console.error('[Flow Agent] Token refresh failed:', e);
  }
}

// ─── WebSocket to Agent ─────────────────────────────────────

function connectToAgent() {
  if (manualDisconnect) return;
  if (ws?.readyState === WebSocket.CONNECTING) return;
  if (ws?.readyState === WebSocket.OPEN) return;

  try {
    ws = new WebSocket(AGENT_WS_URL);
  } catch (e) {
    console.error('[Flow Agent] WS connect error:', e);
    scheduleReconnect();
    return;
  }

  ws.onopen = () => {
    console.log('[Flow Agent] Connected to agent');
    chrome.alarms.clear('reconnect');
    setState('idle');

    // Token refresh alarm — 45 min gives buffer before ~60 min expiry
    chrome.alarms.create('token-refresh', { periodInMinutes: 45 });

    // Send current state + resend token if we have one
    ws.send(JSON.stringify({
      type: 'extension_ready',
      flowKeyPresent: !!flowKey,
      bgVersion: 'p13-urlfix2',
      tokenAge: flowKey && metrics.tokenCapturedAt ? Date.now() - metrics.tokenCapturedAt : null,
    }));
    if (flowKey) {
      ws.send(JSON.stringify({ type: 'token_captured', flowKey }));
    }
    // Backend is reachable again — push any responses queued while it was down.
    flushOutbox();
  };

  ws.onmessage = async ({ data }) => {
    try {
      const msg = JSON.parse(data);

      if (msg.method === 'api_request') {
        await handleApiRequest(msg);
      } else if (msg.method === 'ui_generate') {
        // [FLOW V2 11/09] lái UI flow.google.com (không còn API aisandbox)
        await handleUiGenerate(msg);
      } else if (msg.method === 'trpc_request') {
        await handleTrpcRequest(msg);
      } else if (msg.method === 'upload_video') {
        await handleUploadVideo(msg);
      } else if (msg.method === 'solve_captcha') {
        await handleSolveCaptcha(msg);
      } else if (msg.method === 'get_status') {
        sendToAgent({
          id: msg.id,
          result: {
            state,
            flowKeyPresent: !!flowKey,
            manualDisconnect,
            tokenAge: metrics.tokenCapturedAt ? Date.now() - metrics.tokenCapturedAt : null,
            metrics,
          },
        });
      } else if (msg.method === 'pin_flow_tab') {
        // Ghim tab Flow đang dùng (ưu tiên tab active là flow; nếu không có thì tab project tìm được)
        let tab = null;
        try { tab = (await chrome.tabs.query({ active: true })).find((t) => /^https:\/\/flow\.google\.com\//.test(t.url || '')); } catch {}
        if (!tab) tab = await findFlowV2ProjectTab();
        if (tab && tab.id != null) { await setPinnedTabId(tab.id); sendToAgent({ id: msg.id, result: { pinned: true, tabId: tab.id, url: tab.url || null } }); }
        else sendToAgent({ id: msg.id, error: 'NO_FLOW_TAB: không thấy tab flow.google.com để ghim (mở 1 tab flow.google.com rồi thử lại)', code: 'NO_FLOW_PROJECT_TAB' });
      } else if (msg.method === 'unpin_flow_tab') {
        await clearPinnedTabId();
        sendToAgent({ id: msg.id, result: { pinned: false } });
      } else if (msg.method === 'get_pinned_tab') {
        const pid = await getPinnedTabId(); let url = null, valid = false;
        if (pid != null) { try { const t = await chrome.tabs.get(pid); url = t.url || null; valid = /^https:\/\/flow\.google\.com\//.test(url || ''); } catch { valid = false; } }
        sendToAgent({ id: msg.id, result: { pinned: pid != null, tabId: pid, url, valid } });
      } else if (msg.method === 'open_flow_tab') {
        // Python bridge asks us to open/focus a Flow tab
        console.log('[Flow Agent] Agent requested: open Flow tab');
        // [FLOW V2 11/09] Flow đã dời sang flow.google.com (labs.google redirect)
        const tabs = await chrome.tabs.query({
          url: ['https://flow.google.com/project/*', 'https://flow.google.com/*',
                'https://labs.google/fx/tools/flow*', 'https://labs.google/fx/*/tools/flow*'],
        });
        if (tabs.length) {
          // Tab exists — refresh it to trigger fresh API calls → token capture
          await chrome.tabs.reload(tabs[0].id);
          console.log('[Flow Agent] Refreshed existing Flow tab');
        } else {
          // No tab — open one (active so it loads properly)
          await chrome.tabs.create({ url: 'https://flow.google.com/', active: true });
          console.log('[Flow Agent] Opened new Flow tab');
        }
        // Wait for page to load and make API calls that trigger token capture
        await sleep(5000);
        // If token was captured by webRequest during page load, send it
        if (flowKey && ws?.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'token_captured', flowKey }));
          console.log('[Flow Agent] Sent stored token after tab open');
        } else {
          // Try reading from storage as fallback
          const data = await chrome.storage.local.get(['flowKey']);
          if (data.flowKey) {
            flowKey = data.flowKey;
            if (ws?.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({ type: 'token_captured', flowKey }));
              console.log('[Flow Agent] Sent token from storage after tab open');
            }
          }
        }
      } else if (msg.method === 'refresh_flow_tab') {
        // Python bridge asks us to refresh token
        console.log('[Flow Agent] Agent requested: refresh token');
        await captureTokenFromFlowTab();
        await sleep(3000);
        // Actively send token if we have one
        if (flowKey && ws?.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'token_captured', flowKey }));
          console.log('[Flow Agent] Sent token after refresh');
        } else {
          const data = await chrome.storage.local.get(['flowKey']);
          if (data.flowKey) {
            flowKey = data.flowKey;
            if (ws?.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({ type: 'token_captured', flowKey }));
              console.log('[Flow Agent] Sent token from storage after refresh');
            }
          }
        }
      } else if (msg.type === 'callback_config') {
        callbackSecret = msg.secret;
        callbackUrl = msg.callback_url;
        chrome.storage.local.set({ callbackSecret: msg.secret, callbackUrl: msg.callback_url });
        console.log('[Flow Agent] Received callback config:', callbackUrl);
      } else if (msg.type === 'callback_secret') {
        callbackSecret = msg.secret;
        chrome.storage.local.set({ callbackSecret: msg.secret });
        console.log('[Flow Agent] Received callback secret');
      } else if (msg.type === 'pong') {
        // keepalive response
      }
    } catch (e) {
      console.error('[Flow Agent] Message error:', e);
    }
  };

  ws.onclose = () => {
    setState('off');
    chrome.alarms.clear('token-refresh');
    if (!manualDisconnect) scheduleReconnect();
  };

  ws.onerror = (e) => {
    console.error('[Flow Agent] WS error:', e);
    metrics.lastError = 'WS_ERROR';
    chrome.storage.local.set({ metrics });
  };
}

function scheduleReconnect() {
  chrome.alarms.create('reconnect', { delayInMinutes: 0.083 }); // ~5s
}

function keepAlive() {
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'ping' }));
  } else {
    connectToAgent();
  }
}

function sendToAgent(msg) {
  // API responses (with msg.id) go through a durable outbox so a generated
  // result is never lost — persisted and retried until the agent acks it.
  if (msg.id) {
    enqueueResponse(msg);
    return;
  }
  // Non-response messages (ping, status, token) — best-effort over WS.
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(msg));
  }
}

// ─── Durable Response Outbox ────────────────────────────────
// A generated image/video result must survive a momentary backend hiccup or a
// service-worker restart. Every id-bearing response is persisted and retried
// with backoff until the agent confirms receipt, then dropped.

const MAX_DELIVERY_ATTEMPTS = 8;
let outbox = {};              // id -> { msg, attempts, nextAt }
let _flushingOutbox = false;

async function loadOutbox() {
  try {
    const { responseOutbox } = await chrome.storage.local.get('responseOutbox');
    if (responseOutbox && typeof responseOutbox === 'object') outbox = responseOutbox;
  } catch {}
}

function persistOutbox() {
  chrome.storage.local.set({ responseOutbox: outbox }).catch(() => {});
}

function enqueueResponse(msg) {
  outbox[msg.id] = { msg, attempts: 0, nextAt: 0 };
  persistOutbox();
  flushOutbox();
}

async function deliverOnce(entry) {
  try {
    const resp = await fetch(callbackUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(entry.msg),
    });
    // Any HTTP reply means the backend is reachable and has taken the response
    // (ok:true = matched a request, ok:false = unknown id / already handled).
    // Either way there is nothing to retry — only transport failures retry.
    if (resp.ok) return true;
    // 5xx / transient server error — retry.
    return false;
  } catch {
    // Network error: backend unreachable. Try WS as an immediate fallback but
    // keep the entry queued so a later flush can still deliver it.
    if (ws?.readyState === WebSocket.OPEN) {
      try { ws.send(JSON.stringify(entry.msg)); } catch {}
    }
    return false;
  }
}

async function flushOutbox() {
  if (_flushingOutbox) return;
  _flushingOutbox = true;
  try {
    const ids = Object.keys(outbox);
    if (!ids.length) return;
    const now = Date.now();
    for (const id of ids) {
      const entry = outbox[id];
      if (!entry) continue;
      if (entry.nextAt && entry.nextAt > now) continue;
      const delivered = await deliverOnce(entry);
      if (delivered) {
        delete outbox[id];
        persistOutbox();
        continue;
      }
      entry.attempts++;
      if (entry.attempts >= MAX_DELIVERY_ATTEMPTS) {
        console.error('[Flow Agent] Dropping response', id, 'after', entry.attempts, 'failed deliveries');
        delete outbox[id];
      } else {
        // Exponential backoff, capped at 30s.
        entry.nextAt = Date.now() + Math.min(30000, 1000 * 2 ** entry.attempts);
      }
      persistOutbox();
    }
  } finally {
    _flushingOutbox = false;
  }
}

// ─── reCAPTCHA Solving ──────────────────────────────────────

async function requestCaptchaFromTab(tabId, requestId, pageAction) {
  try {
    return await chrome.tabs.sendMessage(tabId, {
      type: 'GET_CAPTCHA',
      requestId,
      pageAction,
    });
  } catch (error) {
    const msg = error?.message || '';
    const shouldInject =
      msg.includes('Receiving end does not exist') ||
      msg.includes('Could not establish connection');
    if (!shouldInject) throw error;

    // Inject content script and retry
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ['content.js'],
    });
    await sleep(200);
    return await chrome.tabs.sendMessage(tabId, {
      type: 'GET_CAPTCHA',
      requestId,
      pageAction,
    });
  }
}

async function solveCaptcha(requestId, captchaAction) {
  const tabs = await chrome.tabs.query({
    url: ['https://labs.google/fx/tools/flow*', 'https://labs.google/fx/*/tools/flow*'],
  });

  if (!tabs.length) {
    // Auto-open Flow tab and wait briefly before returning error
    try {
      await chrome.tabs.create({ url: 'https://labs.google/fx/tools/flow', active: false });
      await sleep(3000);
      // Retry tab query after opening
      const retryTabs = await chrome.tabs.query({
        url: ['https://labs.google/fx/tools/flow*', 'https://labs.google/fx/*/tools/flow*'],
      });
      if (!retryTabs.length) return { error: 'NO_FLOW_TAB' };
      const resp = await Promise.race([
        requestCaptchaFromTab(retryTabs[0].id, requestId, captchaAction),
        new Promise((_, rej) => setTimeout(() => rej(new Error('CAPTCHA_TIMEOUT')), 30000)),
      ]);
      return resp;
    } catch (e) {
      return { error: e.message || 'NO_FLOW_TAB' };
    }
  }

  try {
    const resp = await Promise.race([
      requestCaptchaFromTab(tabs[0].id, requestId, captchaAction),
      new Promise((_, rej) => setTimeout(() => rej(new Error('CAPTCHA_TIMEOUT')), 30000)),
    ]);
    return resp;
  } catch (e) {
    return { error: e.message };
  }
}

async function handleSolveCaptcha(msg) {
  const { id, params } = msg;
  const result = await solveCaptcha(id, params?.captchaAction || 'VIDEO_GENERATION');

  // Standalone captcha solve counts as captcha-consuming
  metrics.requestCount++;
  if (result?.token) {
    metrics.successCount++;
  } else {
    metrics.failedCount++;
    metrics.lastError = result?.error || 'NO_TOKEN';
  }
  chrome.storage.local.set({ metrics });

  sendToAgent({ id, result });
}

// ─── [FLOW V2 11/09] UI generate: lái UI Flow v2 qua content.js/injected.js ────
// Flow v2 (flow.google.com) chỉ gọi batchexecute bằng cookie — không còn Bearer để
// proxy API. Thay vào đó: tìm tab project, nhờ content.js/injected.js lái UI và nghe
// response, rồi trả {mediaId, videoUrl, credits} về agent qua outbox như api_request.
const FLOW_V2_PROJECT_URLS = ['https://flow.google.com/project/*'];

// [FLOW V2 14/09] Nhớ project id gần nhất từ MỌI tab /project/<id> → tự điều hướng lại khi cần
chrome.tabs.onUpdated.addListener((_id, _info, tab) => {
  const m = ((tab && tab.url) || '').match(/flow\.google\.com\/project\/([0-9a-f-]{36})/i);
  if (m) chrome.storage.local.set({ lastProjectId: m[1] });
});
async function getLastProjectId() {
  try { const d = await chrome.storage.local.get('lastProjectId'); return d.lastProjectId || null; } catch { return null; }
}
// [PIN 17/09] Ghim 1 tab Flow: mọi lần gen chạy ĐÚNG tab này (không mở tab mới, không nhảy tab khác).
async function getPinnedTabId() { try { const d = await chrome.storage.local.get('pinnedTabId'); return (d.pinnedTabId != null) ? d.pinnedTabId : null; } catch { return null; } }
async function setPinnedTabId(id) { try { await chrome.storage.local.set({ pinnedTabId: id }); } catch {} }
async function clearPinnedTabId() { try { await chrome.storage.local.remove('pinnedTabId'); } catch {} }
async function resolvePinnedTab() {
  const pid = await getPinnedTabId();
  if (pid == null) return null;
  let t = null;
  try { t = await chrome.tabs.get(pid); } catch { t = null; }
  if (!t || !/^https:\/\/flow\.google\.com\//.test(t.url || '')) { await clearPinnedTabId(); return null; }  // tab đóng/đổi site → bỏ ghim
  if (t.discarded) { try { await chrome.tabs.reload(t.id); await waitTabComplete(t.id, 15000); } catch {} t = await chrome.tabs.get(t.id).catch(() => t); }
  // tab ghim đang ở /edit/ hoặc home → ĐƯA VỀ gallery project TRONG CHÍNH tab đó (không tạo tab mới)
  if (t && (!/\/project\/[0-9a-f-]{36}/i.test(t.url || '') || /\/edit\//.test(t.url || ''))) {
    const pid2 = (String(t.url || '').match(/\/project\/([0-9a-f-]{36})/i) || [])[1] || await getLastProjectId();
    if (pid2) { try { await chrome.tabs.update(t.id, { url: `https://flow.google.com/project/${pid2}` }); await waitTabComplete(t.id, 20000); t = await chrome.tabs.get(t.id).catch(() => t); } catch {} }
  }
  return t || null;
}
async function waitTabComplete(tabId, timeoutMs = 20000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    try { const t = await chrome.tabs.get(tabId); if (t && t.status === 'complete' && !t.discarded) return t; } catch { return null; }
    await sleep(400);
  }
  try { return await chrome.tabs.get(tabId); } catch { return null; }
}

async function findFlowV2ProjectTab() {
  // 0) [PIN 17/09] Tab đã GHIM thắng tất cả — luôn dùng đúng tab đó.
  const pinned = await resolvePinnedTab();
  if (pinned) return pinned;
  // 1) Tab /project/ đang mở (mọi cửa sổ). Discarded → reload để dùng lại.
  const tabs = await chrome.tabs.query({ url: FLOW_V2_PROJECT_URLS });
  const ok = tabs.filter((t) => t.url && !/\/edit\//.test(t.url));
  ok.sort((a, b) => (b.active ? 1 : 0) - (a.active ? 1 : 0));
  let tab = ok[0];
  if (tab) {
    if (tab.discarded) { try { await chrome.tabs.reload(tab.id); await waitTabComplete(tab.id, 15000); } catch {} }
    return await chrome.tabs.get(tab.id).catch(() => tab);
  }
  // 2) KHÔNG mở tab mới: tái dùng 1 tab flow.google.com bất kỳ (home/gallery) → điều hướng vào project đã nhớ.
  const pid = await getLastProjectId();
  if (pid) {
    const flows = (await chrome.tabs.query({ url: ['https://flow.google.com/*'] }))
      .filter((t) => t.url && !/\/edit\//.test(t.url));
    flows.sort((a, b) => (b.active ? 1 : 0) - (a.active ? 1 : 0));
    const reuse = flows[0];
    if (reuse) {
      try {
        await chrome.tabs.update(reuse.id, { url: `https://flow.google.com/project/${pid}` });
        await waitTabComplete(reuse.id, 20000);
        return await chrome.tabs.get(reuse.id);
      } catch {}
    }
  }
  return null;
}

async function sendUiGenerateToTab(tabId, requestId, params) {
  const msg = { type: 'UI_GENERATE', requestId, params };
  try {
    return await chrome.tabs.sendMessage(tabId, msg);
  } catch (error) {
    const m = error?.message || '';
    if (!(m.includes('Receiving end does not exist') || m.includes('Could not establish connection'))) throw error;
    // content.js chưa có trong tab (tab mở trước khi cài extension) → inject rồi thử lại
    await chrome.scripting.executeScript({ target: { tabId }, files: ['content.js'] });
    await sleep(300);
    return await chrome.tabs.sendMessage(tabId, msg);
  }
}

// [FLOW UI mới] Attach debugger + đưa tab ra trước. Gọi TRƯỚC pha prep để infobar không blur focus.
async function dbgAttach(tabId) {
  if (!chrome.debugger) return { ok: false, error: 'no debugger perm' };
  const dbg = { tabId };
  const withTimeout = (p, ms, l) => Promise.race([p, new Promise((_, rej) => setTimeout(() => rej(new Error('timeout ' + l)), ms))]);
  try {
    try { await withTimeout(chrome.debugger.attach(dbg, '1.3'), 6000, 'attach'); }
    catch (e) { if (!/already attached/i.test(String(e && e.message))) throw e; }
    try { await withTimeout(chrome.debugger.sendCommand(dbg, 'Page.bringToFront'), 5000, 'bringToFront'); } catch (e) {}
    // [KEY] ép trang luôn "focused" — editor Flow chặn cập nhật model khi document.hasFocus()=false
    // (qua SSH/headless Chrome không phải app foreground). Đây là cách Puppeteer làm.
    try { await withTimeout(chrome.debugger.sendCommand(dbg, 'Emulation.setFocusEmulationEnabled', { enabled: true }), 5000, 'focusEmu'); } catch (e) {}
    return { ok: true };
  } catch (e) { return { ok: false, error: (e && e.message) || String(e) }; }
}
// Gõ TỪNG PHÍM thật vào ô ĐANG FOCUS (injected prep đã focus đúng ô composer) — KHÔNG tự focus lại.
async function dbgType(tabId, text) {
  const dbg = { tabId };
  const send = (m, p) => Promise.race([chrome.debugger.sendCommand(dbg, m, p || {}), new Promise((_, rej) => setTimeout(() => rej(new Error('to ' + m)), 8000))]);
  try {
    const s = String(text || '');
    const codeOf = (ch) => {
      if (/[a-zA-Z]/.test(ch)) return { code: 'Key' + ch.toUpperCase(), vk: ch.toUpperCase().charCodeAt(0) };
      if (/[0-9]/.test(ch)) return { code: 'Digit' + ch, vk: ch.charCodeAt(0) };
      if (ch === ' ') return { code: 'Space', vk: 32 };
      if (ch === ',') return { code: 'Comma', vk: 188 };
      if (ch === '.') return { code: 'Period', vk: 190 };
      if (ch === '-') return { code: 'Minus', vk: 189 };
      return { code: '', vk: 0 };
    };
    for (const ch of s) {
      const { code, vk } = codeOf(ch);
      const base = { key: ch, code, text: ch, unmodifiedText: ch, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk };
      await send('Input.dispatchKeyEvent', Object.assign({ type: 'keyDown' }, base));
      await send('Input.dispatchKeyEvent', { type: 'keyUp', key: ch, code, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk });
    }
    await new Promise((r) => setTimeout(r, 500));
    // đọc ô đang focus SÂU NHẤT (xuyên shadow) = đúng ô injected đã focus
    const READ = "(function(){var a=document.activeElement;while(a&&a.shadowRoot&&a.shadowRoot.activeElement)a=a.shadowRoot.activeElement;return a?((a.innerText||a.textContent||'')+'|'+a.tagName).slice(0,50):'no-active'})()";
    let after = '?';
    try { const r = await send('Runtime.evaluate', { expression: READ, returnByValue: true }); after = r && r.result && r.result.value; } catch (e) { after = 'rd-err'; }
    return { ok: true, after };
  } catch (e) { return { ok: false, error: (e && e.message) || String(e) }; }
}
async function dbgDetach(tabId) { try { await chrome.debugger.detach({ tabId }); } catch (e) {} }

async function handleUiGenerate(msg) {
  const { id, params } = msg;
  const tab = await findFlowV2ProjectTab();
  if (!tab) {
    let diag = '';
    try {
      const all = await chrome.tabs.query({ url: ['https://flow.google.com/*'] });
      const pid = await getLastProjectId();
      diag = ' | lastPid=' + pid + ' | flowTabs=' + JSON.stringify(all.map((t) => ({ u: String(t.url || '').slice(-40), a: t.active, d: t.discarded })));
    } catch (e) { diag = ' | diagErr=' + (e && e.message); }
    sendToAgent({ id, error: 'NO_FLOW_TAB: extension không thấy tab flow.google.com nào (có thể khác profile)' + diag, code: 'NO_FLOW_PROJECT_TAB' });
    return;
  }
  setState('running');
  const logId = id;
  addRequestLog({ id: logId, type: 'GEN_VID', time: new Date().toISOString(), status: 'processing', error: null, outputUrl: null, url: tab.url, payloadSummary: String(params?.prompt || '').slice(0, 200) });
  try {
    // Tab phải foreground để click/gõ vào UI ổn định (TobyFlow cũng ép foreground)
    try { await chrome.tabs.update(tab.id, { active: true }); } catch {}
    const timeoutMs = (Number(params?.timeoutMs) || 420000) + 15000;
    let result;
    const isCmd = String(params?.prompt || '').trim().startsWith('__');
    if (!isCmd && params && params.prompt) {
      // [FLOW UI mới] attach TRƯỚC prep (infobar không blur) → prep (settings + focus ĐÚNG ô composer)
      // → gõ vào ô đang focus → submit → detach.
      const at = await dbgAttach(tab.id);
      if (!at.ok) throw new Error('debugger attach: ' + at.error);
      try {
        const prep = await Promise.race([
          sendUiGenerateToTab(tab.id, id + ':prep', Object.assign({}, params, { phase: 'prep' })),
          new Promise((_, rej) => setTimeout(() => rej(new Error('PREP_TIMEOUT')), 90000)),
        ]);
        if (!prep || prep.error) throw new Error('prep: ' + ((prep && prep.error) || 'no result'));
        const ins = await dbgType(tab.id, String(params.prompt || ''));
        if (!ins.ok) throw new Error('debugger type: ' + ins.error);
        result = await Promise.race([
          sendUiGenerateToTab(tab.id, id + ':submit', Object.assign({}, params, { phase: 'submit', insInfo: 'after=' + ins.after })),
          new Promise((_, rej) => setTimeout(() => rej(new Error('SUBMIT_TIMEOUT')), timeoutMs)),
        ]);
      } finally { await dbgDetach(tab.id); }
    } else {
      result = await Promise.race([
        sendUiGenerateToTab(tab.id, id, params || {}),
        new Promise((_, rej) => setTimeout(() => rej(new Error('UI_GENERATE_TIMEOUT')), timeoutMs)),
      ]);
    }
    if (!result || result.error) {
      const err = result?.error || 'NO_RESULT';
      metrics.requestCount++; metrics.failedCount++; metrics.lastError = err;
      updateRequestLog(logId, { status: 'failed', error: err });
      sendToAgent({ id, error: err, code: result?.code || 'DRIVER_ERROR' });
    } else {
      // [FLOW V2 11/09] Có URL video → tải bytes NGAY trong SW (cookie + host_permission), trả base64.
      if (result.videoUrl && !result.dryRun && !result.videoBase64) {
        const dl = await _downloadVideoBytes(result.videoUrl);
        if (dl.error) { result.downloadError = dl.error; }
        else { result.videoBase64 = dl.base64; result.videoBytes = dl.bytes; }
      }
      if (!result.dryRun) { metrics.requestCount++; metrics.successCount++; metrics.lastError = null; }
      updateRequestLog(logId, { status: 'success', outputUrl: result.videoUrl || null });
      sendToAgent({ id, result });
    }
  } catch (e) {
    metrics.requestCount++; metrics.failedCount++; metrics.lastError = e.message;
    updateRequestLog(logId, { status: 'failed', error: e.message });
    sendToAgent({ id, error: e.message || 'UI_GENERATE_FAILED', code: 'UI_GENERATE_FAILED' });
  } finally {
    chrome.storage.local.set({ metrics });
    setState('idle');
  }
}

// ─── API Request Proxy ──────────────────────────────────────

async function handleTrpcRequest(msg) {
  const { id, params } = msg;
  const { url, method = 'POST', headers = {}, body } = params;

  if (!url || !url.startsWith('https://labs.google/')) {
    sendToAgent({ id, error: 'INVALID_TRPC_URL' });
    return;
  }

  setState('running');
  // TRPC calls don't consume captcha — don't count in metrics

  const logId = id;
  const logType = url.includes('createProject') ? 'CREATE_PROJECT' : 'TRPC';
  // TRPC calls are silent — don't show in request log

  const fetchHeaders = { 'Content-Type': 'application/json', ...headers };
  if (flowKey) {
    fetchHeaders['authorization'] = `Bearer ${flowKey}`;
  }

  try {
    const resp = await fetch(url, {
      method,
      headers: fetchHeaders,
      body: body ? JSON.stringify(body) : undefined,
      credentials: 'include',
    });
    const data = await resp.json();
    chrome.storage.local.set({ metrics });
    updateRequestLog(logId, { status: 'success' });
    sendToAgent({ id, status: resp.status, data });
  } catch (e) {
    console.error('[Flow Agent] tRPC request failed:', e);
    chrome.storage.local.set({ metrics });
    updateRequestLog(logId, { status: 'failed', error: e.message || 'TRPC_FETCH_FAILED' });
    sendToAgent({ id, error: e.message || 'TRPC_FETCH_FAILED' });
  } finally {
    setState('idle');
  }
}


async function handleUploadVideo(msg) {
  const { id, params } = msg;
  const { videoBase64, projectId, videoSize } = params;

  try {
    const tabs = await chrome.tabs.query({ url: '*://labs.google/*' });
    if (!tabs.length) {
      sendToAgent({ id, error: 'NO_FLOW_TAB' });
      return;
    }

    const size = videoSize || (videoBase64 ? Math.floor(videoBase64.length * 3 / 4) : 0);

    // Get session URL via page context XHR (needs session cookies)
    const startResults = await chrome.scripting.executeScript({
      target: { tabId: tabs[0].id },
      world: 'MAIN',
      func: (projId, sz) => {
        return new Promise((resolve) => {
          const xhr = new XMLHttpRequest();
          xhr.open('POST', '/fx/api/upload-video?action=start');
          xhr.setRequestHeader('X-Upload-Project-Id', projId);
          xhr.setRequestHeader('X-Upload-Content-Type', 'video/mp4');
          xhr.setRequestHeader('X-Upload-Content-Length', sz.toString());
          xhr.withCredentials = true;
          xhr.onload = () => {
            let data;
            try { data = JSON.parse(xhr.responseText); } catch { data = {}; }
            resolve({
              sessionUrl: data.sessionUrl || xhr.getResponseHeader('X-Upload-Session-Url') || '',
              status: xhr.status,
            });
          };
          xhr.onerror = () => resolve({ error: 'POST_FAILED' });
          xhr.send();
        });
      },
      args: [projectId, size],
    });

    const step1 = startResults?.[0]?.result;
    if (!step1 || step1.error || !step1.sessionUrl) {
      sendToAgent({ id, error: step1?.error || 'NO_SESSION_URL' });
      return;
    }

    // Return sessionUrl + token — caller handles PUT
    sendToAgent({
      id,
      result: {
        sessionUrl: step1.sessionUrl,
        token: flowKey || '',
      },
    });
  } catch (e) {
    sendToAgent({ id, error: `UPLOAD_ERROR: ${e.message}` });
  }
}

async function handleApiRequest(msg) {
  const { id, params } = msg;
  const { url, method, headers, body, captchaAction } = params;

  if (!url) {
    sendToAgent({ id, error: 'MISSING_URL' });
    return;
  }

  if (!url.startsWith('https://aisandbox-pa.googleapis.com/')) {
    sendToAgent({ id, error: 'INVALID_URL' });
    return;
  }

  setState('running');
  const hasCaptcha = !!captchaAction;
  if (hasCaptcha) metrics.requestCount++;

  const logId = id;
  const logType = _classifyApiUrl(url);
  if (_VISIBLE_TYPES.has(logType)) {
    const payloadSummary = body ? JSON.stringify(body).slice(0, 200) : null;
    addRequestLog({ id: logId, type: logType, time: new Date().toISOString(), status: 'processing', error: null, outputUrl: null, url, payloadSummary });
  }

  try {
    // Step 1: Solve captcha if needed
    let captchaToken = null;
    if (captchaAction) {
      const captchaResult = await solveCaptcha(id, captchaAction);
      captchaToken = captchaResult?.token || null;
      if (!captchaToken) {
        // Cannot proceed without captcha — API will 403
        const err = captchaResult?.error || 'CAPTCHA_FAILED';
        console.error(`[Flow Agent] Captcha failed for ${captchaAction}: ${err}`);
        sendToAgent({ id, status: 403, error: `CAPTCHA_FAILED: ${err}` });
        if (hasCaptcha) { metrics.failedCount++; metrics.lastError = `CAPTCHA_FAILED: ${err}`; }
        chrome.storage.local.set({ metrics });
        updateRequestLog(logId, { status: 'failed', error: `CAPTCHA_FAILED: ${err}` });
        setState('idle');
        return;
      }
    }

    // Step 2: Inject captcha token into body
    let finalBody = body;
    if (captchaToken && finalBody) {
      finalBody = JSON.parse(JSON.stringify(finalBody)); // deep clone
      if (finalBody.clientContext?.recaptchaContext) {
        finalBody.clientContext.recaptchaContext.token = captchaToken;
      }
      if (finalBody.requests && Array.isArray(finalBody.requests)) {
        for (const req of finalBody.requests) {
          if (req.clientContext?.recaptchaContext) {
            req.clientContext.recaptchaContext.token = captchaToken;
          }
        }
      }
    }

    // Step 3: Use flowKey for auth
    const activeFlowKey = flowKey;
    if (!activeFlowKey) {
      sendToAgent({ id, status: 503, error: 'NO_FLOW_KEY' });
      if (hasCaptcha) { metrics.failedCount++; metrics.lastError = 'NO_FLOW_KEY'; }
      chrome.storage.local.set({ metrics });
      updateRequestLog(logId, { status: 'failed', error: 'NO_FLOW_KEY' });
      setState('idle');
      return;
    }

    const fetchHeaders = { ...(headers || {}) };
    fetchHeaders['authorization'] = `Bearer ${activeFlowKey}`;

    // Step 4: Make the API call from browser context
    const response = await fetch(url, {
      method: method || 'POST',
      headers: fetchHeaders,
      credentials: 'include',
      body: method === 'GET' ? undefined : JSON.stringify(finalBody),
    });

    let responseData;
    const responseText = await response.text();
    try {
      responseData = JSON.parse(responseText);
    } catch {
      responseData = responseText;
    }

    sendToAgent({
      id,
      status: response.status,
      data: responseData,
    });

    const responseSummary = responseText ? responseText.slice(0, 300) : null;
    if (response.ok) {
      if (hasCaptcha) { metrics.successCount++; metrics.lastError = null; }
      updateRequestLog(logId, { status: 'success', httpStatus: response.status, responseSummary });
    } else {
      if (hasCaptcha) { metrics.failedCount++; metrics.lastError = `API_${response.status}`; }
      updateRequestLog(logId, { status: 'failed', error: `API_${response.status}`, httpStatus: response.status, responseSummary });
    }
  } catch (e) {
    sendToAgent({
      id,
      status: 500,
      error: e.message || 'API_REQUEST_FAILED',
    });
    if (hasCaptcha) { metrics.failedCount++; metrics.lastError = e.message; }
    updateRequestLog(logId, { status: 'failed', error: e.message || 'API_REQUEST_FAILED' });
  }

  chrome.storage.local.set({ metrics });
  setState('idle');
}

// ─── State & Popup ──────────────────────────────────────────

function setState(newState) {
  state = newState;
  const badges = { idle: '●', running: '▶', off: '○' };
  const colors = { idle: '#22c55e', running: '#f59e0b', off: '#6b7280' };
  chrome.action.setBadgeText({ text: badges[state] || '' });
  chrome.action.setBadgeBackgroundColor({ color: colors[state] || '#000' });
  broadcastStatus();
}

function broadcastStatus() {
  chrome.runtime.sendMessage({ type: 'STATUS_PUSH' }).catch(() => {});
}

chrome.runtime.onMessage.addListener((msg, _, reply) => {
  if (msg.type === 'STATUS') {
    reply({
      connected: ws?.readyState === WebSocket.OPEN,
      agentConnected: ws?.readyState === WebSocket.OPEN,
      flowKeyPresent: !!flowKey,
      manualDisconnect,
      tokenAge: metrics.tokenCapturedAt ? Date.now() - metrics.tokenCapturedAt : null,
      metrics: {
        requestCount: metrics.requestCount,
        successCount: metrics.successCount,
        failedCount: metrics.failedCount,
        lastError: metrics.lastError,
      },
      state,
    });
  }

  if (msg.type === 'DISCONNECT') {
    manualDisconnect = true;
    if (ws) ws.close();
    reply({ ok: true });
    return true;
  }

  if (msg.type === 'RECONNECT') {
    manualDisconnect = false;
    connectToAgent();
    reply({ ok: true });
    return true;
  }

  if (msg.type === 'REQUEST_LOG') {
    reply({ log: requestLog });
    return true;
  }

  // [FLOW UI mới] Gõ prompt TRUSTED vào editor (editor Flow mới bỏ qua synthetic event) qua
  // chrome.debugger + CDP Input.insertText — như Puppeteer. content.js chuyển tiếp từ injected.js.
  if (msg.type === 'INSERT_TEXT') {
    const tabId = _ && _.tab && _.tab.id;
    (async () => {
      if (String(msg.text) === '__PING__') { reply({ ok: true, ping: true, hasDbg: !!chrome.debugger, tabId: tabId || null }); return; }
      if (!chrome.debugger) { reply({ ok: false, error: 'no chrome.debugger (thiếu quyền?)' }); return; }
      if (!tabId) { reply({ ok: false, error: 'no tabId' }); return; }
      const dbg = { tabId };
      const withTimeout = (p, ms, label) => Promise.race([p, new Promise((_r, rej) => setTimeout(() => rej(new Error('timeout ' + label)), ms))]);
      let step = 'attach';
      try {
        try { await withTimeout(chrome.debugger.attach(dbg, '1.3'), 6000, 'attach'); }
        catch (e) { if (!/already attached/i.test(String(e && e.message))) throw e; }  // đã attach → dùng tiếp
        step = 'focus';
        await withTimeout(chrome.debugger.sendCommand(dbg, 'Input.insertText', { text: String(msg.text || '') }), 8000, 'insertText');
        reply({ ok: true });
      } catch (e) {
        reply({ ok: false, error: step + ':' + ((e && e.message) || String(e)) });
      } finally {
        try { await chrome.debugger.detach(dbg); } catch (e) {}
      }
    })();
    return true;  // async reply
  }

  if (msg.type === 'OPEN_FLOW_TAB') {
    chrome.tabs.query({
      url: ['https://flow.google.com/project/*', 'https://flow.google.com/*',
            'https://labs.google/fx/tools/flow*', 'https://labs.google/fx/*/tools/flow*'],
    }).then((tabs) => {
      if (tabs.length) {
        chrome.tabs.update(tabs[0].id, { active: true });
        reply({ ok: true, tabId: tabs[0].id });
      } else {
        chrome.tabs.create({ url: 'https://flow.google.com/' })
          .then((tab) => reply({ ok: true, tabId: tab.id }))
          .catch((e) => reply({ error: e.message }));
      }
    }).catch((e) => reply({ error: e.message }));
    return true;
  }

  if (msg.type === 'REFRESH_TOKEN') {
    captureTokenFromFlowTab()
      .then(() => reply({ ok: true }))
      .catch((e) => reply({ error: e.message }));
    return true;
  }

  if (msg.type === 'TEST_CAPTCHA') {
    solveCaptcha(`test-${Date.now()}`, msg.pageAction || 'IMAGE_GENERATION')
      .then((r) => reply(r))
      .catch((e) => reply({ error: e.message }));
    return true;
  }

  if (msg.type === 'TRPC_MEDIA_URLS') {
    handleTrpcMediaUrls(msg.trpcUrl, msg.body);
    reply({ ok: true });
    return true;
  }

  if (msg.type === 'SNIFFED_AISANDBOX_REQUEST') {
    console.log('[Flow Agent] SNIFFED aisandbox request:', msg.url);
    fetch('http://127.0.0.1:8100/api/ext/callback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        type: 'sniffed_video_request',
        url: msg.url,
        method: msg.method,
        payload: msg.payload,
        timestamp: msg.timestamp,
      }),
    }).catch((e) => console.error('[Flow Agent] Failed to forward sniffed request:', e));
    reply({ ok: true });
    return true;
  }

  return true;
});

// ─── TRPC Media URL Extractor ──────────────────────────────

function handleTrpcMediaUrls(trpcUrl, bodyText) {
  try {
    // Extract all fresh GCS signed URLs
    // [VÁ RIÊNG 18/08] hai host: CDN cũ (storage.googleapis) và mới (flow-content.google)
    const urlRegex = /https:\/\/(?:storage\.googleapis\.com\/ai-sandbox-videofx|flow-content\.google)\/(?:image|video)\/[0-9a-f-]{36}\?[^"'\s\\]+/g;
    // [VÁ RIÊNG 11/09] batchexecute (Flow v2) escape "/"→"\/", "&"→"&", "="→"=".
    // PHẢI gỡ CẢ BA trước regex; thiếu = (=) thì URL /video/ bị cắt cụt ở "?Expires"
    // (regex dừng ở "\") → chữ ký thiếu → tải 403. [SỬA 15/09]
    // [SỬA 15/09 #2] batchexecute là JSON LỒNG → escape bị NHÂN ĐÔI ("\\u003d"); gỡ 1 gạch chéo
    // vẫn còn "\=" → regex URL dừng ở "?Expires". Dùng \\+ để gỡ MỌI độ sâu escape.
    bodyText = String(bodyText)
      .replace(/\\+\//g, '/')
      .replace(/\\+u0026/gi, '&')
      .replace(/\\+u003d/gi, '=');
    const matches = bodyText.match(urlRegex) || [];
    if (!matches.length) return;

    // Deduplicate and parse
    const urlMap = {};
    for (const rawUrl of matches) {
      // Unescape JSON-escaped URLs (phòng khi còn sót)
      const url = rawUrl.replace(/\\u0026/gi, '&').replace(/\\u003d/gi, '=').replace(/\\/g, '');
      const mediaMatch = url.match(/\/(image|video)\/([0-9a-f-]{36})\?/);
      if (mediaMatch) {
        const [, mediaType, mediaId] = mediaMatch;
        // Keep last occurrence (freshest)
        urlMap[mediaId] = { mediaType, url, mediaId };
      }
    }

    const entries = Object.values(urlMap);
    if (!entries.length) return;

    console.log(`[Flow Agent] Captured ${entries.length} fresh media URLs from TRPC`);
    // URL refresh is silent — don't show in request log

    // Forward to agent for DB update
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'media_urls_refresh',
        urls: entries,
      }));
    }
  } catch (e) {
    console.error('[Flow Agent] Failed to extract TRPC media URLs:', e);
  }
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// [FLOW V2 11/09] ArrayBuffer → base64 theo khối (tránh tràn stack với video vài MB)
function _abToBase64(buf) {
  const bytes = new Uint8Array(buf);
  let bin = '';
  const CH = 0x8000;
  for (let i = 0; i < bytes.length; i += CH) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + CH));
  return btoa(bin);
}

// [FLOW V2 11/09] Tải bytes video từ CDN cookie-gated. PHẢI chạy ở service worker: SW có
// host_permission flow-content.google → fetch chéo đọc được body + credentials:include gửi cookie
// (trang KHÔNG làm được: cookie-less 403, with-credentials bị CORS chặn). Trả base64 hoặc lỗi.
async function _downloadVideoBytes(url) {
  try {
    const resp = await fetch(url, { credentials: 'include' });
    if (!resp.ok) return { error: 'DOWNLOAD_HTTP_' + resp.status };
    const buf = await resp.arrayBuffer();
    if (!buf || buf.byteLength < 1000) return { error: 'DOWNLOAD_TOO_SMALL_' + (buf ? buf.byteLength : 0) };
    return { base64: _abToBase64(buf), bytes: buf.byteLength };
  } catch (e) {
    return { error: 'DOWNLOAD_FETCH_FAIL: ' + (e && e.message || e) };
  }
}

// ─── Human-like Telemetry ──────────────────────────────────
// Periodically send tracking events to Google's analytics endpoints
// to mimic normal browser behavior.

const _UA = navigator.userAgent;
let _telemetrySessionId = `;${Date.now()}`;

function _rand(min, max) { return Math.floor(Math.random() * (max - min + 1)) + min; }

function _buildBatchLogPayload() {
  const events = [];
  const types = ['FLOW_IMAGE_LATENCY', 'FLOW_VIDEO_LATENCY'];
  const count = _rand(1, 3);
  for (let i = 0; i < count; i++) {
    events.push({
      event: types[_rand(0, types.length - 1)],
      eventProperties: [
        { key: 'CURRENT_TIME_MS', doubleValue: Date.now() },
        { key: 'DURATION_MS', doubleValue: _rand(150, 800) },
        { key: 'USER_AGENT', stringValue: _UA },
        { key: 'IS_DESKTOP', booleanValue: true },
      ],
      eventMetadata: { sessionId: _telemetrySessionId },
      eventTime: new Date().toISOString(),
    });
  }
  return { appEvents: events };
}

function _buildFrontendEventsPayload() {
  const eventTypes = [
    'FLOW_IMAGE_LATENCY', 'FLOW_VIDEO_LATENCY', 'GRID_SCROLL_DEPTH',
    'FLOW_PROJECT_OPEN', 'FLOW_SCENE_VIEW',
  ];
  const count = _rand(1, 4);
  const events = [];
  for (let i = 0; i < count; i++) {
    const et = eventTypes[_rand(0, eventTypes.length - 1)];
    const params = {
      USER_AGENT: { '@type': 'type.googleapis.com/google.protobuf.StringValue', value: _UA },
      IS_DESKTOP: { '@type': 'type.googleapis.com/google.protobuf.StringValue', value: 'true' },
    };
    if (et.includes('LATENCY')) {
      params.CURRENT_TIME_MS = { '@type': 'type.googleapis.com/google.protobuf.StringValue', value: String(Date.now()) };
      params.DURATION_MS = { '@type': 'type.googleapis.com/google.protobuf.StringValue', value: String(_rand(100, 600)) };
    }
    if (et === 'GRID_SCROLL_DEPTH') {
      params.MEDIA_GENERATION_PAYGATE_TIER = { '@type': 'type.googleapis.com/google.protobuf.StringValue', value: 'PAYGATE_TIER_TWO' };
    }
    events.push({
      eventType: et,
      metadata: {
        sessionId: _telemetrySessionId,
        createTime: new Date().toISOString(),
        additionalParams: params,
      },
    });
  }
  return { events };
}

async function sendTelemetry() {
  if (!flowKey || state === 'off') return;

  const headers = {
    'Content-Type': 'text/plain;charset=UTF-8',
    'authorization': `Bearer ${flowKey}`,
  };

  // Telemetry is silent — don't show in request log
  try {
    if (Math.random() < 0.5) {
      await fetch(`https://aisandbox-pa.googleapis.com/v1:batchLog`, {
        method: 'POST', headers, credentials: 'include',
        body: JSON.stringify(_buildBatchLogPayload()),
      });
    } else {
      await fetch(`https://aisandbox-pa.googleapis.com/v1/flow:batchLogFrontendEvents`, {
        method: 'POST', headers, credentials: 'include',
        body: JSON.stringify(_buildFrontendEventsPayload()),
      });
    }
  } catch {}
}

// Send telemetry at random intervals (45-120s) to look organic
function scheduleTelemetry() {
  const delay = _rand(45, 120) * 1000;
  setTimeout(async () => {
    await sendTelemetry();
    scheduleTelemetry(); // reschedule with new random interval
  }, delay);
}

// Refresh session ID every ~30min like a real user
setInterval(() => { _telemetrySessionId = `;${Date.now()}`; }, _rand(25, 35) * 60 * 1000);

scheduleTelemetry();

console.log('[Flow Agent] Extension loaded');
