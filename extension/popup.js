/**
 * NeuroUI Extension — Popup Controller
 * ======================================
 * Handles profile selection, custom settings, and communication
 * with the content script and background service worker.
 */

// --- State ---
let currentProfile = null;
let isActive = false;

// --- DOM Elements ---
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const clsDisplay = document.getElementById('cls-display');
const clsBeforeValue = document.getElementById('cls-before-value');
const clsAfterValue = document.getElementById('cls-after-value');
const btnActivate = document.getElementById('btn-activate');
const btnReset = document.getElementById('btn-reset');
const customSettings = document.getElementById('custom-settings');
const profileButtons = document.querySelectorAll('.profile-btn');

document.addEventListener('DOMContentLoaded', async () => {
  // Load saved state
  const saved = await chrome.storage.local.get(['profile', 'isActive', 'cls_before', 'cls_after', 'adBlockEnabled', 'totalAdsBlocked']);

  if (saved.profile) {
    currentProfile = saved.profile;
    selectProfile(saved.profile);
  }

  if (saved.isActive) {
    isActive = true;
    setActiveState();
  }

  if (saved.cls_before && saved.cls_after) {
    showCLSScores(saved.cls_before, saved.cls_after);
  }

  // Ad blocker state
  const adBlockToggle = document.getElementById('adblock-toggle');
  const adBlockStats = document.getElementById('adblock-stats');
  
  if (adBlockToggle) {
    adBlockToggle.checked = saved.adBlockEnabled !== false; // Default: ON
    adBlockToggle.addEventListener('change', async (e) => {
      const enabled = e.target.checked;
      await chrome.storage.local.set({ adBlockEnabled: enabled });
      
      // Notify all tabs
      const tabs = await chrome.tabs.query({});
      tabs.forEach(tab => {
        chrome.tabs.sendMessage(tab.id, {
          action: 'TOGGLE_ADBLOCK',
          enabled: enabled,
        }).catch(() => {}); // Ignore tabs without content script
      });

      // Update the ad blocker card style
      const card = document.querySelector('.adblock-card');
      if (card) {
        card.style.borderColor = enabled ? 'rgba(34, 197, 94, 0.15)' : 'rgba(255, 255, 255, 0.06)';
        card.style.background = enabled ? 'rgba(34, 197, 94, 0.06)' : 'rgba(255, 255, 255, 0.03)';
      }
      if (adBlockStats) {
        adBlockStats.style.color = enabled ? '#22C55E' : '#6B7280';
      }
    });
  }

  // Update blocked count
  if (adBlockStats) {
    const total = saved.totalAdsBlocked || 0;
    adBlockStats.textContent = `${total.toLocaleString()} ads blocked`;
  }

  // Setup event listeners
  setupEventListeners();
});


function setupEventListeners() {
  // Profile buttons
  profileButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const profile = btn.dataset.profile;
      selectProfile(profile);
    });
  });

  // Activate button
  btnActivate.addEventListener('click', handleActivate);

  // Reset button
  btnReset.addEventListener('click', handleReset);

  // Heatmap button
  const btnHeatmap = document.getElementById('btn-heatmap');
  if (btnHeatmap) {
    btnHeatmap.addEventListener('click', handleHeatmap);
  }

  // Quiz link
  const quizLink = document.getElementById('quiz-link');
  if (quizLink) {
    quizLink.addEventListener('click', (e) => {
      e.preventDefault();
      chrome.tabs.create({ url: chrome.runtime.getURL('onboarding.html') });
    });
  }

  // Custom settings sliders
  const simplificationSlider = document.getElementById('simplification-level');
  const spacingSlider = document.getElementById('spacing-multiplier');

  if (simplificationSlider) {
    simplificationSlider.addEventListener('input', (e) => {
      document.getElementById('simplification-value').textContent = e.target.value;
    });
  }

  if (spacingSlider) {
    spacingSlider.addEventListener('input', (e) => {
      document.getElementById('spacing-value').textContent = `${e.target.value}×`;
    });
  }
}


async function handleHeatmap() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) return;

  const btn = document.getElementById('btn-heatmap');
  btn.innerHTML = '<span class="btn-icon">⏳</span> Analyzing...';
  btn.disabled = true;

  try {
    const response = await chrome.tabs.sendMessage(tab.id, { action: 'HEATMAP' });
    if (response && response.success) {
      if (response.removed) {
        btn.innerHTML = '<span class="btn-icon">🔥</span> Cognitive Heatmap';
      } else {
        btn.innerHTML = '<span class="btn-icon">✅</span> Heatmap Active';
      }
    } else {
      btn.innerHTML = '<span class="btn-icon">❌</span> ' + (response?.error || 'Failed');
    }
  } catch (err) {
    btn.innerHTML = '<span class="btn-icon">❌</span> Error';
  }
  btn.disabled = false;
}


function selectProfile(profile) {
  currentProfile = profile;

  // Update button states
  profileButtons.forEach(btn => {
    btn.classList.toggle('selected', btn.dataset.profile === profile);
  });

  // Show/hide custom settings
  customSettings.style.display = profile === 'custom' ? 'flex' : 'none';

  // Save selection
  chrome.storage.local.set({ profile });

  // Update activate button
  btnActivate.disabled = false;
}


async function handleActivate() {
  if (!currentProfile) return;

  if (isActive) {
    // Deactivate
    handleReset();
    return;
  }

  // Set processing state
  setProcessingState();

  try {
    // Get custom settings if applicable
    const settings = getCustomSettings();

    // Save state
    await chrome.storage.local.set({
      profile: currentProfile,
      isActive: true,
      customSettings: settings,
    });

    // Send ACTIVATE message to content script via background
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    if (tab) {
      const response = await chrome.tabs.sendMessage(tab.id, {
        action: 'ACTIVATE',
        profile: currentProfile,
        settings: settings,
      });

      if (response && response.success) {
        isActive = true;
        setActiveState();

        if (response.cls_before && response.cls_after) {
          showCLSScores(response.cls_before, response.cls_after);
          await chrome.storage.local.set({
            cls_before: response.cls_before,
            cls_after: response.cls_after,
          });
        }
      } else {
        setErrorState(response?.error || 'Unknown error');
      }
    }
  } catch (error) {
    console.error('Activation error:', error);
    setErrorState(error.message);
  }
}


async function handleReset() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    if (tab) {
      await chrome.tabs.sendMessage(tab.id, { action: 'DEACTIVATE' });
    }

    isActive = false;
    await chrome.storage.local.set({ isActive: false, cls_before: null, cls_after: null });

    setInactiveState();
  } catch (error) {
    console.error('Reset error:', error);
  }
}


function getCustomSettings() {
  if (currentProfile !== 'custom') return {};

  return {
    simplification_level: parseInt(document.getElementById('simplification-level').value),
    distraction_level: document.getElementById('distraction-level').value,
    spacing_multiplier: parseFloat(document.getElementById('spacing-multiplier').value),
    color_mode: document.getElementById('color-mode').value,
  };
}


// --- UI State Updates ---

function setProcessingState() {
  statusDot.className = 'status-dot processing';
  statusText.textContent = 'Processing...';
  btnActivate.disabled = true;
  btnActivate.innerHTML = '<span class="btn-icon">⏳</span> Processing...';
}

function setActiveState() {
  statusDot.className = 'status-dot active';
  statusText.textContent = `Active — ${currentProfile?.toUpperCase()} mode`;
  btnActivate.className = 'btn-primary active';
  btnActivate.innerHTML = '<span class="btn-icon">✅</span> Active — Click to Deactivate';
  btnActivate.disabled = false;
  btnReset.style.display = 'flex';
}

function setInactiveState() {
  statusDot.className = 'status-dot';
  statusText.textContent = 'Inactive';
  btnActivate.className = 'btn-primary';
  btnActivate.innerHTML = '<span class="btn-icon">🧠</span> Activate NeuroUI';
  btnActivate.disabled = false;
  btnReset.style.display = 'none';
  clsDisplay.style.display = 'none';
}

function setErrorState(message) {
  statusDot.className = 'status-dot';
  statusText.textContent = `Error: ${message}`;
  btnActivate.className = 'btn-primary';
  btnActivate.innerHTML = '<span class="btn-icon">🧠</span> Retry Activation';
  btnActivate.disabled = false;
}

function showCLSScores(before, after) {
  clsDisplay.style.display = 'flex';
  clsBeforeValue.textContent = Math.round(before);
  clsAfterValue.textContent = Math.round(after);
}
