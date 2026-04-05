/**
 * NeuroUI — Background Service Worker (MV3)
 * ==========================================
 * Routes messages between popup ↔ content script,
 * and handles fetch() calls to the backend API.
 *
 * MV3 service workers are ephemeral — all state is
 * persisted via chrome.storage.local.
 */

const DEFAULT_API_BASE = 'http://localhost:8000';

// --- Dynamic API URL ---
async function getAPIBase() {
  try {
    const { apiUrl } = await chrome.storage.local.get('apiUrl');
    return apiUrl || DEFAULT_API_BASE;
  } catch {
    return DEFAULT_API_BASE;
  }
}

// --- Message Handler ---
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'API_CALL') {
    handleAPICall(message)
      .then(sendResponse)
      .catch(error => sendResponse({ error: error.message }));
    return true; // Keep channel open for async response
  }

  if (message.action === 'HEALTH_CHECK') {
    getAPIBase().then(apiBase => {
      fetch(`${apiBase}/api/health`)
        .then(r => r.json())
        .then(data => sendResponse(data))
        .catch(error => sendResponse({ error: error.message }));
    });
    return true;
  }
});


// --- Response Cache ---
const API_CACHE = new Map();
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes
const MAX_CACHE_SIZE = 50;

function hashKey(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) {
    h = ((h << 5) - h) + str.charCodeAt(i);
    h |= 0;
  }
  return h.toString(36);
}


async function handleAPICall(message) {
  const { endpoint, method, body } = message;
  const apiBase = await getAPIBase();

  // Check cache
  const cacheKey = hashKey(endpoint + JSON.stringify(body || {}));
  const cached = API_CACHE.get(cacheKey);
  if (cached && Date.now() - cached.time < CACHE_TTL) {
    console.log(`[NeuroUI] Cache HIT for ${endpoint} (${API_CACHE.size} entries)`);
    return { ...cached.data, _cached: true };
  }

  try {
    const response = await fetch(`${apiBase}${endpoint}`, {
      method: method || 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: body ? JSON.stringify(body) : undefined,
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`API error ${response.status}: ${errorText}`);
    }

    const data = await response.json();

    // Store in cache
    API_CACHE.set(cacheKey, { data, time: Date.now() });

    // Evict oldest if over limit
    if (API_CACHE.size > MAX_CACHE_SIZE) {
      const oldest = API_CACHE.keys().next().value;
      API_CACHE.delete(oldest);
    }

    console.log(`[NeuroUI] Cache MISS for ${endpoint} — stored (${API_CACHE.size} entries)`);
    return data;

  } catch (error) {
    console.error('[NeuroUI Background] API call failed:', error);
    throw error;
  }
}


// --- Keyboard Shortcut Handler ---
chrome.commands.onCommand.addListener(async (command) => {
  if (command === 'toggle-neuroui') {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab) return;

    const { isActive, profile } = await chrome.storage.local.get(['isActive', 'profile']);

    if (isActive) {
      // Deactivate
      chrome.tabs.sendMessage(tab.id, { action: 'DEACTIVATE' }).catch(() => {});
      await chrome.storage.local.set({ isActive: false, cls_before: null, cls_after: null });
      console.log('[NeuroUI] Deactivated via keyboard shortcut');
    } else if (profile) {
      // Load saved custom settings
      const { customSettings } = await chrome.storage.local.get('customSettings');

      chrome.tabs.sendMessage(tab.id, {
        action: 'ACTIVATE',
        profile: profile,
        settings: customSettings || {},
      }).catch(() => {});
      await chrome.storage.local.set({ isActive: true });
      console.log(`[NeuroUI] Activated via keyboard shortcut (${profile})`);
    }
  }
});


// --- Extension Install/Update Handler ---
chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === 'install') {
    console.log('[NeuroUI] Extension installed successfully.');
    // Set default state
    chrome.storage.local.set({
      profile: null,
      isActive: false,
      cls_before: null,
      cls_after: null,
      adBlockEnabled: true,
      totalAdsBlocked: 0,
      sessionAdsBlocked: 0,
      apiUrl: DEFAULT_API_BASE,
      quizCompleted: false,
    });

    // Open onboarding quiz on first install
    chrome.tabs.create({ url: chrome.runtime.getURL('onboarding.html') });
  }
});

// --- Ad Blocker: Track blocked requests ---
// Listen for changes to ad block toggle
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === 'local' && changes.adBlockEnabled) {
    const enabled = changes.adBlockEnabled.newValue;
    // Enable/disable the declarativeNetRequest ruleset
    chrome.declarativeNetRequest.updateEnabledRulesets({
      enableRulesetIds: enabled ? ['neuroui_adblock'] : [],
      disableRulesetIds: enabled ? [] : ['neuroui_adblock'],
    }).catch(err => console.warn('[NeuroUI] Rule toggle error:', err));

    console.log(`[NeuroUI] Ad blocker ${enabled ? 'enabled' : 'disabled'}`);
  }
});
