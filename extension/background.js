/**
 * NeuroUI — Background Service Worker (MV3)
 * ==========================================
 * Routes messages between popup ↔ content script,
 * and handles fetch() calls to the backend API.
 *
 * MV3 service workers are ephemeral — all state is
 * persisted via chrome.storage.local.
 */

const API_BASE = 'http://localhost:8000';

// --- Message Handler ---
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'API_CALL') {
    handleAPICall(message)
      .then(sendResponse)
      .catch(error => sendResponse({ error: error.message }));
    return true; // Keep channel open for async response
  }

  if (message.action === 'HEALTH_CHECK') {
    fetch(`${API_BASE}/api/health`)
      .then(r => r.json())
      .then(data => sendResponse(data))
      .catch(error => sendResponse({ error: error.message }));
    return true;
  }
});


async function handleAPICall(message) {
  const { endpoint, method, body } = message;

  try {
    const response = await fetch(`${API_BASE}${endpoint}`, {
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

    return await response.json();

  } catch (error) {
    console.error('[NeuroUI Background] API call failed:', error);
    throw error;
  }
}


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
    });
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
