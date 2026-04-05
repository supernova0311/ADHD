/**
 * NeuroUI Extension — Popup Controller
 * ======================================
 * Handles profile selection, custom settings, and communication
 * with the content script and background service worker.
 *
 * KEY FIX: Custom settings are now ALWAYS sent to the backend
 * regardless of profile selection, so quiz-determined profiles
 * can still be fine-tuned.
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
const finetuneToggle = document.getElementById('finetune-toggle');

document.addEventListener('DOMContentLoaded', async () => {
  // Load saved state
  const saved = await chrome.storage.local.get([
    'profile', 'isActive', 'cls_before', 'cls_after',
    'adBlockEnabled', 'totalAdsBlocked', 'customSettings',
  ]);

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

  // Restore saved custom settings to the UI controls
  if (saved.customSettings) {
    restoreSettings(saved.customSettings);
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

  // Query visual feature status from content script
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab) {
      chrome.tabs.sendMessage(tab.id, { action: 'GET_FEATURE_STATUS' }, (status) => {
        if (chrome.runtime.lastError || !status) return;
        const features = ['bionic', 'minimap', 'reader', 'progress'];
        features.forEach(f => {
          const btn = document.getElementById(`btn-${f}`);
          if (btn && status[f]) btn.classList.add('active');
        });
      });
    }
  } catch (e) { /* ignore */ }
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

  // Fine-tune toggle (expand/collapse settings for ANY profile)
  if (finetuneToggle) {
    finetuneToggle.addEventListener('click', () => {
      const isOpen = customSettings.style.display !== 'none';
      customSettings.style.display = isOpen ? 'none' : 'flex';
      finetuneToggle.classList.toggle('open', !isOpen);
    });
  }

  // Custom settings sliders — save on every change
  const simplificationSlider = document.getElementById('simplification-level');
  const spacingSlider = document.getElementById('spacing-multiplier');
  const fontSizeSlider = document.getElementById('font-size');

  if (simplificationSlider) {
    simplificationSlider.addEventListener('input', (e) => {
      document.getElementById('simplification-value').textContent = e.target.value;
      persistSettings();
    });
  }

  if (spacingSlider) {
    spacingSlider.addEventListener('input', (e) => {
      document.getElementById('spacing-value').textContent = `${e.target.value}×`;
      persistSettings();
    });
  }

  if (fontSizeSlider) {
    fontSizeSlider.addEventListener('input', (e) => {
      document.getElementById('font-size-value').textContent = `${e.target.value}px`;
      persistSettings();
    });
  }

  // Selects
  const distractionSelect = document.getElementById('distraction-level');
  const colorSelect = document.getElementById('color-mode');

  if (distractionSelect) {
    distractionSelect.addEventListener('change', () => persistSettings());
  }
  if (colorSelect) {
    colorSelect.addEventListener('change', () => persistSettings());
  }

  // Visual feature toggles
  const features = ['bionic', 'minimap', 'reader', 'progress'];
  features.forEach(feature => {
    const btn = document.getElementById(`btn-${feature}`);
    if (btn) {
      btn.addEventListener('click', () => toggleVisualFeature(feature, btn));
    }
  });
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
    const isSelected = btn.dataset.profile === profile;
    btn.classList.toggle('selected', isSelected);
    btn.setAttribute('aria-checked', isSelected ? 'true' : 'false');
  });

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
    // ALWAYS collect custom settings, regardless of profile
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


/**
 * ALWAYS collect custom settings regardless of profile.
 * This is the key fix — previously returned {} for non-custom profiles.
 */
function getCustomSettings() {
  return {
    simplification_level: parseInt(document.getElementById('simplification-level').value),
    distraction_level: document.getElementById('distraction-level').value,
    spacing_multiplier: parseFloat(document.getElementById('spacing-multiplier').value),
    color_mode: document.getElementById('color-mode').value,
    font_size: parseInt(document.getElementById('font-size').value),
  };
}


/**
 * Persist current settings to chrome.storage so they survive popup close.
 */
async function persistSettings() {
  const settings = getCustomSettings();
  await chrome.storage.local.set({ customSettings: settings });
}


/**
 * Restore saved settings into the UI controls.
 */
function restoreSettings(settings) {
  if (!settings) return;

  const simplificationSlider = document.getElementById('simplification-level');
  const spacingSlider = document.getElementById('spacing-multiplier');
  const fontSizeSlider = document.getElementById('font-size');
  const distractionSelect = document.getElementById('distraction-level');
  const colorSelect = document.getElementById('color-mode');

  if (settings.simplification_level && simplificationSlider) {
    simplificationSlider.value = settings.simplification_level;
    document.getElementById('simplification-value').textContent = settings.simplification_level;
  }
  if (settings.distraction_level && distractionSelect) {
    distractionSelect.value = settings.distraction_level;
  }
  if (settings.spacing_multiplier && spacingSlider) {
    spacingSlider.value = settings.spacing_multiplier;
    document.getElementById('spacing-value').textContent = `${settings.spacing_multiplier}×`;
  }
  if (settings.font_size && fontSizeSlider) {
    fontSizeSlider.value = settings.font_size;
    document.getElementById('font-size-value').textContent = `${settings.font_size}px`;
  }
  if (settings.color_mode && colorSelect) {
    colorSelect.value = settings.color_mode;
  }
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


async function toggleVisualFeature(feature, btn) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) return;

  try {
    const response = await chrome.tabs.sendMessage(tab.id, {
      action: 'VISUAL_FEATURE',
      feature: feature,
    });

    if (response && response.active) {
      btn.classList.add('active');
      btn.setAttribute('aria-pressed', 'true');
    } else {
      btn.classList.remove('active');
      btn.setAttribute('aria-pressed', 'false');
    }
  } catch (err) {
    console.error('Visual feature error:', err);
  }
}


// Listen for READER_CLOSED from content script
chrome.runtime.onMessage.addListener((message) => {
  if (message.action === 'READER_CLOSED') {
    const btn = document.getElementById('btn-reader');
    if (btn) btn.classList.remove('active');
  }
});
