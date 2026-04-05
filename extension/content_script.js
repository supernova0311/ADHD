/**
 * NeuroUI — Content Script
 * ==========================
 * The core DOM transformation engine. Injected into every page.
 *
 * Responsibilities:
 * 1. Extract text content from visible DOM elements
 * 2. Build DOM metadata snapshot (node count, depth, distractors)
 * 3. Send data to backend via background.js bridge
 * 4. Apply transformations: text replacement, CSS injection, element hiding
 * 5. Show floating CLS improvement badge
 * 6. Reading ruler for dyslexia profile
 */

(() => {
  'use strict';

  // Guard against multiple injections
  if (window.__NEUROUI_INJECTED__) return;
  window.__NEUROUI_INJECTED__ = true;

  // --- State ---
  let isActive = false;
  let activeProfile = null;
  let heatmapActive = false;
  let injectedStylesheet = null;
  let clsBadge = null;
  let readingRuler = null;
  let originalTexts = new Map(); // Store originals for reset
  let hiddenElements = new Map(); // Track hidden elements for restore
  let pausedMedia = []; // Track paused media for restore
  let modifiedStyles = new Map(); // Track style changes for restore

  // Visual feature state
  let bionicActive = false;
  let spotlightActive = false;
  let spotlightScrollHandler = null;
  let minimapActive = false;
  let minimapScrollHandler = null;
  let readerActive = false;
  let progressBarActive = false;
  let progressScrollHandler = null;

  // --- Constants ---
  const TEXT_TAGS = ['P', 'LI', 'TD', 'TH', 'BLOCKQUOTE', 'FIGCAPTION', 'DD', 'DT'];
  const HEADING_TAGS = ['H1', 'H2', 'H3', 'H4', 'H5', 'H6'];
  const MAX_CHUNK_WORDS = 500;
  const MIN_TEXT_LENGTH = 30; // Minimum characters to process

  // --- Message Listener ---
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === 'ACTIVATE') {
      activate(message.profile, message.settings)
        .then(result => sendResponse(result))
        .catch(error => sendResponse({ success: false, error: error.message }));
      return true; // Keep channel open for async
    }

    if (message.action === 'DEACTIVATE') {
      deactivate();
      sendResponse({ success: true });
    }

    if (message.action === 'HEATMAP') {
      activateHeatmap()
        .then(result => sendResponse(result))
        .catch(error => sendResponse({ success: false, error: error.message }));
      return true;
    }

    if (message.action === 'HEATMAP_OFF') {
      removeHeatmap();
      sendResponse({ success: true });
    }

    if (message.action === 'VISUAL_FEATURE') {
      handleVisualFeature(message.feature)
        .then(result => sendResponse(result))
        .catch(error => sendResponse({ active: false, error: error.message }));
      return true;
    }

    if (message.action === 'GET_FEATURE_STATUS') {
      sendResponse({
        bionic: bionicActive,
        spotlight: spotlightActive,
        minimap: minimapActive,
        reader: readerActive,
        progress: progressBarActive,
      });
    }
  });


  // =============================================
  // ACTIVATION PIPELINE
  // =============================================

  async function activate(profile, settings) {
    try {
      isActive = true;
      activeProfile = profile;
      showProgressOverlay();

      // Step 1: Extract text content
      updateProgress('Extracting text content...', 15);
      const textElements = extractTextElements();
      const chunks = chunkTextElements(textElements);

      // Step 2: Build DOM snapshot
      updateProgress('Analyzing page structure...', 30);
      const domSnapshot = buildDOMSnapshot();

      // Step 3: Call backend API
      updateProgress('Running AI simplification...', 50);
      const apiResponse = await callBackendAPI(chunks, profile, domSnapshot, settings);

      if (!apiResponse || apiResponse.error) {
        throw new Error(apiResponse?.error || 'Backend unavailable');
      }

      // Step 4: Apply text transformations
      updateProgress('Simplifying text...', 65);
      applyTextTransformations(textElements, apiResponse.simplified_chunks);

      // Step 5: Inject visual CSS
      updateProgress('Applying visual adaptations...', 75);
      injectCSS(apiResponse.visual_css + '\n' + apiResponse.focus_css);

      // Step 6: Execute focus commands SAFELY (no eval)
      updateProgress('Removing distractions...', 85);
      if (apiResponse.focus_js_commands) {
        apiResponse.focus_js_commands.forEach(cmd => {
          executeFocusCommand(cmd);
        });
      }

      // Step 7: Hide distractor elements
      if (apiResponse.hide_selectors) {
        hideElements(apiResponse.hide_selectors);
      }

      // Step 8: Enable reading ruler for dyslexia
      if (profile === 'dyslexia') {
        enableReadingRuler();
      }

      // Step 9: Show CLS badge
      updateProgress('Done!', 100);
      const clsBefore = apiResponse.cls_before?.cls || 0;
      const clsAfter = apiResponse.cls_after?.cls || 0;

      // Brief delay to show 100% before closing
      await new Promise(r => setTimeout(r, 400));
      hideProgressOverlay();
      showCLSBadge(clsBefore, clsAfter);

      return {
        success: true,
        cls_before: clsBefore,
        cls_after: clsAfter,
        metrics: apiResponse.metrics,
      };

    } catch (error) {
      hideProgressOverlay();
      console.error('[NeuroUI] Activation failed:', error);
      return { success: false, error: error.message };
    }
  }


  function deactivate() {
    isActive = false;
    activeProfile = null;

    // 1. Restore original text content AND remove style indicators
    originalTexts.forEach((originalText, element) => {
      if (element && element.isConnected) {
        element.textContent = originalText;
      }
    });
    originalTexts.clear();

    // 2. Restore modified inline styles (border-left, padding-left indicators)
    modifiedStyles.forEach((originalStyles, element) => {
      if (element && element.isConnected) {
        for (const [prop, value] of Object.entries(originalStyles)) {
          if (value === null) {
            element.style.removeProperty(prop);
          } else {
            element.style.setProperty(prop, value);
          }
        }
      }
    });
    modifiedStyles.clear();

    // 3. Restore hidden elements
    hiddenElements.forEach((originalDisplay, element) => {
      if (element && element.isConnected) {
        if (originalDisplay) {
          element.style.display = originalDisplay;
        } else {
          element.style.removeProperty('display');
        }
      }
    });
    hiddenElements.clear();

    // 4. Resume paused media
    pausedMedia.forEach(el => {
      if (el && el.isConnected && el.play) {
        try { el.play(); } catch (e) { /* ignore */ }
      }
    });
    pausedMedia = [];

    // 5. Remove reading ruler
    if (readingRuler) {
      readingRuler.remove();
      readingRuler = null;
    }
    document.removeEventListener('mousemove', handleReadingRulerMove);

    // 6. Remove injected CSS
    if (injectedStylesheet) {
      injectedStylesheet.remove();
      injectedStylesheet = null;
    }

    // 7. Remove CLS badge
    if (clsBadge) {
      clsBadge.remove();
      clsBadge = null;
    }

    // 8. Clean up visual features
    if (bionicActive) disableBionicReading();
    if (spotlightActive) disableSpotlightMode();
    if (minimapActive) disableMinimap();
    if (readerActive) disableReaderMode();
    if (progressBarActive) disableProgressBar();

    // 9. Remove progress overlay
    hideProgressOverlay();

    // 10. Restore body overflow (in case cookie banner removal locked it)
    document.body.style.overflow = '';
    document.documentElement.style.overflow = '';
  }


  // =============================================
  // SAFE FOCUS COMMAND EXECUTOR (replaces eval)
  // =============================================

  function executeFocusCommand(cmd) {
    // Only allow known, safe operations — NO eval()

    // Pattern: pause media elements matching a selector
    const pauseMatch = cmd.match(/document\.querySelectorAll\("([^"]+)"\)/);
    if (pauseMatch && cmd.includes('pause')) {
      try {
        document.querySelectorAll(pauseMatch[1]).forEach(el => {
          if (el.pause) {
            el.pause();
            pausedMedia.push(el);
          }
        });
      } catch (e) { /* invalid selector */ }
      return;
    }

    // Pattern: restore body overflow (cookie banner removal)
    if (cmd.includes('overflow')) {
      document.body.style.overflow = 'auto';
      document.documentElement.style.overflow = 'auto';
      return;
    }

    console.warn('[NeuroUI] Skipped unknown focus command:', cmd.substring(0, 80));
  }


  // =============================================
  // DOM EXTRACTION
  // =============================================

  function extractTextElements() {
    const elements = [];
    const allTags = [...TEXT_TAGS, ...HEADING_TAGS];

    allTags.forEach(tag => {
      document.querySelectorAll(tag).forEach(el => {
        const text = el.textContent?.trim();
        if (text && text.length >= MIN_TEXT_LENGTH && isVisible(el)) {
          elements.push({
            element: el,
            text: text,
            tag: el.tagName,
            hasChildElements: el.children.length > 0,
          });
        }
      });
    });

    return elements;
  }


  function chunkTextElements(textElements) {
    const chunks = [];
    let currentChunk = [];
    let currentWordCount = 0;

    textElements.forEach(({ text }) => {
      const words = text.split(/\s+/).length;

      if (currentWordCount + words > MAX_CHUNK_WORDS && currentChunk.length > 0) {
        chunks.push(currentChunk.join('\n\n'));
        currentChunk = [];
        currentWordCount = 0;
      }

      currentChunk.push(text);
      currentWordCount += words;
    });

    if (currentChunk.length > 0) {
      chunks.push(currentChunk.join('\n\n'));
    }

    return chunks.length > 0 ? chunks : [''];
  }


  function buildDOMSnapshot() {
    const allElements = document.querySelectorAll('*');
    const elements = [];

    // Sample elements for distractor detection (limit for performance)
    const sampleSize = Math.min(allElements.length, 200);
    const step = Math.max(1, Math.floor(allElements.length / sampleSize));

    for (let i = 0; i < allElements.length; i += step) {
      const el = allElements[i];
      const computed = window.getComputedStyle(el);

      elements.push({
        tag: el.tagName.toLowerCase(),
        classes: Array.from(el.classList),
        id: el.id || '',
        attributes: {
          role: el.getAttribute('role') || '',
          'aria-label': el.getAttribute('aria-label') || '',
        },
        has_autoplay: el.hasAttribute('autoplay'),
        position: computed.position,
        z_index: parseInt(computed.zIndex) || 0,
      });
    }

    return {
      node_count: allElements.length,
      max_depth: getMaxDepth(document.body),
      elements: elements,
      url: window.location.href,
    };
  }


  function getMaxDepth(node, depth = 0) {
    if (!node || !node.children || node.children.length === 0) {
      return depth;
    }

    let maxChildDepth = depth;
    // Sample children for performance
    const children = Array.from(node.children).slice(0, 10);
    for (const child of children) {
      const childDepth = getMaxDepth(child, depth + 1);
      if (childDepth > maxChildDepth) {
        maxChildDepth = childDepth;
      }
    }

    return maxChildDepth;
  }


  // =============================================
  // API COMMUNICATION
  // =============================================

  async function callBackendAPI(chunks, profile, domSnapshot, settings) {
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage({
        action: 'API_CALL',
        endpoint: '/api/process',
        method: 'POST',
        body: {
          chunks: chunks,
          profile: profile,
          dom_snapshot: domSnapshot,
          custom_settings: settings || undefined,
        },
      }, (response) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
        } else {
          resolve(response);
        }
      });
    });
  }


  // =============================================
  // DOM TRANSFORMATIONS
  // =============================================

  function applyTextTransformations(textElements, simplifiedChunks) {
    if (!simplifiedChunks || simplifiedChunks.length === 0) return;

    // Flatten simplified chunks back to individual paragraphs
    const simplifiedTexts = simplifiedChunks.join('\n\n').split('\n\n').filter(t => t.trim());

    const elementsToUpdate = textElements.slice(0, simplifiedTexts.length);

    elementsToUpdate.forEach((item, index) => {
      const simplified = simplifiedTexts[index];
      if (simplified && simplified !== item.text) {
        // Save original for reset
        originalTexts.set(item.element, item.text);

        // Save original inline styles for full restore
        modifiedStyles.set(item.element, {
          'border-left': item.element.style.borderLeft || null,
          'padding-left': item.element.style.paddingLeft || null,
        });

        // Apply simplified text — preserve child elements if possible
        if (item.hasChildElements) {
          // Only replace direct text nodes, preserve <a>, <strong>, etc.
          replaceTextNodesOnly(item.element, simplified);
        } else {
          item.element.textContent = simplified;
        }

        // Add visual indicator that this text was simplified
        item.element.style.borderLeft = '2px solid rgba(99, 102, 241, 0.3)';
        item.element.style.paddingLeft = '8px';
      }
    });
  }


  function replaceTextNodesOnly(element, newText) {
    // Find the longest direct text node and replace it
    // This preserves <a>, <strong>, <em>, <code> etc.
    let longestTextNode = null;
    let longestLength = 0;

    for (const node of element.childNodes) {
      if (node.nodeType === Node.TEXT_NODE && node.textContent.trim().length > longestLength) {
        longestTextNode = node;
        longestLength = node.textContent.trim().length;
      }
    }

    if (longestTextNode && longestLength > 20) {
      longestTextNode.textContent = newText + ' ';
    } else {
      // Fallback: no significant text node found, replace all
      element.textContent = newText;
    }
  }


  function injectCSS(cssText) {
    if (!cssText) return;

    // Remove existing injection
    if (injectedStylesheet) {
      injectedStylesheet.remove();
    }

    injectedStylesheet = document.createElement('style');
    injectedStylesheet.id = 'neuroui-styles';
    injectedStylesheet.textContent = `
      /* NeuroUI Cognitive Accessibility Stylesheet */
      ${cssText}
    `;
    document.head.appendChild(injectedStylesheet);
  }


  function hideElements(selectors) {
    selectors.forEach(selector => {
      try {
        document.querySelectorAll(selector).forEach(el => {
          // Save original display value for restore
          hiddenElements.set(el, el.style.display || '');
          el.style.setProperty('display', 'none', 'important');
        });
      } catch (e) {
        // Invalid selector — skip silently
      }
    });
  }


  // =============================================
  // READING RULER (Dyslexia Aid)
  // =============================================

  function handleReadingRulerMove(e) {
    if (readingRuler) {
      readingRuler.style.top = (e.clientY - 22) + 'px';
    }
  }

  function enableReadingRuler() {
    if (readingRuler) return;

    readingRuler = document.createElement('div');
    readingRuler.id = 'neuroui-reading-ruler';
    readingRuler.style.cssText = `
      position: fixed;
      left: 0;
      right: 0;
      height: 44px;
      background: linear-gradient(
        to bottom,
        transparent 0%,
        rgba(255, 255, 180, 0.18) 15%,
        rgba(255, 255, 180, 0.25) 50%,
        rgba(255, 255, 180, 0.18) 85%,
        transparent 100%
      );
      border-top: 1.5px solid rgba(255, 210, 0, 0.35);
      border-bottom: 1.5px solid rgba(255, 210, 0, 0.35);
      pointer-events: none;
      z-index: 999998;
      transition: top 0.06s linear;
      top: 50%;
    `;
    document.body.appendChild(readingRuler);
    document.addEventListener('mousemove', handleReadingRulerMove);
  }


  // =============================================
  // UI INDICATORS
  // =============================================

  function showCLSBadge(before, after) {
    if (clsBadge) clsBadge.remove();

    clsBadge = document.createElement('div');
    clsBadge.id = 'neuroui-cls-badge';

    const improvement = Math.round(before - after);
    const improvementPct = before > 0 ? Math.round((improvement / before) * 100) : 0;

    clsBadge.innerHTML = `
      <div style="
        position: fixed; bottom: 20px; right: 20px; z-index: 999999;
        background: linear-gradient(135deg, #1a1a2e, #16213e);
        border: 1px solid rgba(99, 102, 241, 0.3);
        border-radius: 12px; padding: 12px 16px;
        font-family: 'Segoe UI', system-ui, sans-serif;
        color: #e4e4e7; font-size: 12px;
        box-shadow: 0 8px 32px rgba(0,0,0,0.4);
        display: flex; align-items: center; gap: 12px;
        cursor: pointer; user-select: none;
        animation: neuroui-badge-in 0.4s cubic-bezier(0.16, 1, 0.3, 1);
      " onclick="this.parentElement.style.display='none'">
        <div style="text-align:center;">
          <div style="font-size:10px;color:#9ca3af;text-transform:uppercase;letter-spacing:0.05em;">CLS Score</div>
          <div style="display:flex;align-items:center;gap:8px;margin-top:2px;">
            <span style="color:#ef4444;font-weight:700;font-size:18px;">${Math.round(before)}</span>
            <span style="color:#6366f1;">→</span>
            <span style="color:#22c55e;font-weight:700;font-size:18px;">${Math.round(after)}</span>
          </div>
        </div>
        <div style="
          background: rgba(34,197,94,0.15);
          color: #22c55e; font-weight: 700;
          padding: 4px 8px; border-radius: 6px;
          font-size: 11px;
        ">-${improvementPct}%</div>
      </div>
      <style>
        @keyframes neuroui-badge-in {
          0% { opacity: 0; transform: translateY(20px) scale(0.9); }
          100% { opacity: 1; transform: translateY(0) scale(1); }
        }
      </style>
    `;

    document.body.appendChild(clsBadge);
  }


  // --- Step-by-Step Progress Overlay ---

  function showProgressOverlay() {
    let overlay = document.getElementById('neuroui-progress');
    if (overlay) overlay.remove();

    overlay = document.createElement('div');
    overlay.id = 'neuroui-progress';
    overlay.innerHTML = `
      <div style="
        position: fixed; top: 0; left: 0; right: 0; z-index: 999999;
        background: linear-gradient(135deg, #1a1a2e, #0f0f1e);
        border-bottom: 1px solid rgba(99, 102, 241, 0.2);
        padding: 10px 20px;
        font-family: 'Segoe UI', system-ui, sans-serif;
        display: flex; align-items: center; gap: 14px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.5);
      ">
        <div style="
          width: 24px; height: 24px; border-radius: 50%;
          border: 2.5px solid rgba(99, 102, 241, 0.2);
          border-top-color: #6366f1;
          animation: neuroui-spin 0.8s linear infinite;
        "></div>
        <div>
          <div id="neuroui-progress-text" style="color: #e4e4e7; font-size: 13px; font-weight: 500;">Initializing...</div>
          <div style="margin-top: 4px; height: 3px; width: 200px; background: rgba(255,255,255,0.1); border-radius: 2px; overflow: hidden;">
            <div id="neuroui-progress-bar" style="
              height: 100%; width: 0%; border-radius: 2px;
              background: linear-gradient(90deg, #6366f1, #8b5cf6);
              transition: width 0.3s ease;
            "></div>
          </div>
        </div>
        <div id="neuroui-progress-pct" style="color: #6366f1; font-size: 12px; font-weight: 700; margin-left: auto;">0%</div>
      </div>
      <style>
        @keyframes neuroui-spin {
          to { transform: rotate(360deg); }
        }
      </style>
    `;
    document.body.appendChild(overlay);
  }

  function updateProgress(text, percent) {
    const textEl = document.getElementById('neuroui-progress-text');
    const barEl = document.getElementById('neuroui-progress-bar');
    const pctEl = document.getElementById('neuroui-progress-pct');
    if (textEl) textEl.textContent = text;
    if (barEl) barEl.style.width = percent + '%';
    if (pctEl) pctEl.textContent = Math.round(percent) + '%';
  }

  function hideProgressOverlay() {
    const overlay = document.getElementById('neuroui-progress');
    if (overlay) overlay.remove();
  }


  // =============================================
  // COGNITIVE LOAD HEATMAP
  // =============================================

  const HEATMAP_COLORS = {
    low:      { bg: 'rgba(34, 197, 94, 0.12)',  border: '#22c55e', label: 'Easy' },
    moderate: { bg: 'rgba(250, 204, 21, 0.12)', border: '#facc15', label: 'Moderate' },
    high:     { bg: 'rgba(249, 115, 22, 0.12)', border: '#f97316', label: 'Hard' },
    critical: { bg: 'rgba(239, 68, 68, 0.15)',  border: '#ef4444', label: 'Very Hard' },
  };

  async function activateHeatmap() {
    if (heatmapActive) {
      removeHeatmap();
      return { success: true, removed: true };
    }

    showProgressOverlay();
    updateProgress('Scanning page content...', 20);

    // 1. Extract all visible text elements
    const elements = [];
    const allTags = [...TEXT_TAGS, ...HEADING_TAGS];
    allTags.forEach(tag => {
      document.querySelectorAll(tag).forEach(el => {
        const text = el.textContent?.trim();
        if (text && text.length >= 20 && isVisible(el)) {
          elements.push({ element: el, text });
        }
      });
    });

    if (elements.length === 0) {
      hideProgressOverlay();
      return { success: false, error: 'No text content found' };
    }

    updateProgress(`Analyzing ${elements.length} paragraphs...`, 50);

    // 2. Send to backend for per-paragraph CLS
    const chunks = elements.map(e => e.text);
    let scores;
    try {
      const resp = await new Promise((resolve, reject) => {
        chrome.runtime.sendMessage({
          action: 'API_CALL',
          endpoint: '/api/heatmap',
          method: 'POST',
          body: { chunks },
        }, (response) => {
          if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
          else resolve(response);
        });
      });

      if (resp.error) throw new Error(resp.error);
      scores = resp.scores;
    } catch (err) {
      hideProgressOverlay();
      return { success: false, error: err.message };
    }

    updateProgress('Rendering heatmap...', 80);

    // 3. Apply color overlays
    elements.forEach((item, i) => {
      if (!scores[i]) return;
      const score = scores[i];
      const colors = HEATMAP_COLORS[score.level] || HEATMAP_COLORS.moderate;

      item.element.setAttribute('data-neuroui-heatmap', score.level);
      item.element.style.setProperty('background-color', colors.bg, 'important');
      item.element.style.setProperty('border-left', `4px solid ${colors.border}`, 'important');
      item.element.style.setProperty('padding-left', '10px', 'important');
      item.element.style.setProperty('position', 'relative');

      // Add CLS score badge on each paragraph
      const badge = document.createElement('span');
      badge.className = 'neuroui-heatmap-badge';
      badge.textContent = Math.round(score.cls);
      badge.title = `CLS: ${score.cls} | ${score.grade_level} | ${colors.label}`;
      badge.style.cssText = `
        position: absolute; top: -8px; right: -8px;
        background: ${colors.border}; color: #fff;
        font-size: 10px; font-weight: 700;
        width: 24px; height: 24px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-family: 'Segoe UI', system-ui, sans-serif;
        box-shadow: 0 2px 6px rgba(0,0,0,0.3);
        z-index: 999;
        pointer-events: none;
      `;
      item.element.appendChild(badge);
    });

    // 4. Show heatmap legend
    showHeatmapLegend(scores);

    heatmapActive = true;
    updateProgress('Done!', 100);
    await new Promise(r => setTimeout(r, 300));
    hideProgressOverlay();

    return {
      success: true,
      paragraphs_analyzed: elements.length,
      avg_cls: Math.round(scores.reduce((s, c) => s + c.cls, 0) / scores.length),
    };
  }

  function showHeatmapLegend(scores) {
    const existing = document.getElementById('neuroui-heatmap-legend');
    if (existing) existing.remove();

    const counts = { low: 0, moderate: 0, high: 0, critical: 0 };
    scores.forEach(s => counts[s.level]++);
    const total = scores.length;
    const avgCls = Math.round(scores.reduce((s, c) => s + c.cls, 0) / total);

    const legend = document.createElement('div');
    legend.id = 'neuroui-heatmap-legend';
    legend.innerHTML = `
      <div style="
        position: fixed; bottom: 20px; left: 20px; z-index: 999999;
        background: linear-gradient(135deg, #1a1a2e, #16213e);
        border: 1px solid rgba(99, 102, 241, 0.3);
        border-radius: 14px; padding: 16px 20px;
        font-family: 'Segoe UI', system-ui, sans-serif;
        color: #e4e4e7; min-width: 220px;
        box-shadow: 0 8px 32px rgba(0,0,0,0.5);
        animation: neuroui-badge-in 0.4s cubic-bezier(0.16, 1, 0.3, 1);
      ">
        <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: #9ca3af; margin-bottom: 10px;">Cognitive Load Heatmap</div>
        <div style="font-size: 24px; font-weight: 800; color: #6366f1; margin-bottom: 8px;">Avg CLS: ${avgCls}</div>
        <div style="display: flex; flex-direction: column; gap: 5px; font-size: 12px;">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="width: 12px; height: 12px; border-radius: 3px; background: #22c55e;"></span>
            <span>Easy (${counts.low})</span>
            <span style="margin-left: auto; color: #6b7280;">${Math.round(counts.low/total*100)}%</span>
          </div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="width: 12px; height: 12px; border-radius: 3px; background: #facc15;"></span>
            <span>Moderate (${counts.moderate})</span>
            <span style="margin-left: auto; color: #6b7280;">${Math.round(counts.moderate/total*100)}%</span>
          </div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="width: 12px; height: 12px; border-radius: 3px; background: #f97316;"></span>
            <span>Hard (${counts.high})</span>
            <span style="margin-left: auto; color: #6b7280;">${Math.round(counts.high/total*100)}%</span>
          </div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="width: 12px; height: 12px; border-radius: 3px; background: #ef4444;"></span>
            <span>Very Hard (${counts.critical})</span>
            <span style="margin-left: auto; color: #6b7280;">${Math.round(counts.critical/total*100)}%</span>
          </div>
        </div>
        <div style="margin-top: 10px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.08); font-size: 10px; color: #6b7280; text-align: center; cursor: pointer;"
             onclick="this.closest('[id]').remove()">
          ${total} paragraphs analyzed · Click to dismiss
        </div>
      </div>
    `;
    document.body.appendChild(legend);
  }

  function removeHeatmap() {
    heatmapActive = false;

    // Remove all heatmap overlays
    document.querySelectorAll('[data-neuroui-heatmap]').forEach(el => {
      el.removeAttribute('data-neuroui-heatmap');
      el.style.removeProperty('background-color');
      el.style.removeProperty('border-left');
      el.style.removeProperty('padding-left');
      el.style.removeProperty('position');
    });

    // Remove badges
    document.querySelectorAll('.neuroui-heatmap-badge').forEach(b => b.remove());

    // Remove legend
    const legend = document.getElementById('neuroui-heatmap-legend');
    if (legend) legend.remove();
  }


  // =============================================
  // VISUAL FEATURE DISPATCHER
  // =============================================

  async function handleVisualFeature(feature) {
    switch (feature) {
      case 'bionic':
        if (bionicActive) { disableBionicReading(); return { active: false }; }
        enableBionicReading(); return { active: true };
      case 'spotlight':
        if (spotlightActive) { disableSpotlightMode(); return { active: false }; }
        enableSpotlightMode(); return { active: true };
      case 'minimap':
        if (minimapActive) { disableMinimap(); return { active: false }; }
        await enableMinimap(); return { active: minimapActive };
      case 'reader':
        if (readerActive) { disableReaderMode(); return { active: false }; }
        enableReaderMode(); return { active: true };
      case 'progress':
        if (progressBarActive) { disableProgressBar(); return { active: false }; }
        enableProgressBar(); return { active: true };
      default:
        return { active: false, error: 'Unknown feature' };
    }
  }


  // =============================================
  // 1. BIONIC READING
  // =============================================

  function enableBionicReading() {
    if (bionicActive) return;
    bionicActive = true;

    const style = document.createElement('style');
    style.id = 'neuroui-bionic-css';
    style.textContent = `
      .neuroui-bionic {
        font-weight: 700 !important;
        color: inherit;
      }
    `;
    document.head.appendChild(style);

    const tags = [...TEXT_TAGS, ...HEADING_TAGS];
    tags.forEach(tag => {
      document.querySelectorAll(tag).forEach(el => {
        if (!isVisible(el) || el.closest('#neuroui-reader') || el.closest('#neuroui-cls-badge')) return;
        bionicifyElement(el);
      });
    });
  }

  function bionicifyElement(el) {
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    const textNodes = [];
    while (walker.nextNode()) textNodes.push(walker.currentNode);

    textNodes.forEach(node => {
      const text = node.textContent;
      if (text.trim().length < 3) return;

      const frag = document.createDocumentFragment();
      const parts = text.split(/(\s+)/);

      parts.forEach(part => {
        if (/^\s*$/.test(part) || part.length < 2) {
          frag.appendChild(document.createTextNode(part));
          return;
        }
        const boldLen = Math.ceil(part.length * 0.5);
        const b = document.createElement('b');
        b.className = 'neuroui-bionic';
        b.textContent = part.substring(0, boldLen);
        frag.appendChild(b);
        frag.appendChild(document.createTextNode(part.substring(boldLen)));
      });

      const wrapper = document.createElement('span');
      wrapper.className = 'neuroui-bionic-wrapper';
      wrapper.dataset.originalText = text;
      wrapper.appendChild(frag);
      node.parentNode.replaceChild(wrapper, node);
    });
  }

  function disableBionicReading() {
    bionicActive = false;
    document.querySelectorAll('.neuroui-bionic-wrapper').forEach(wrapper => {
      const textNode = document.createTextNode(wrapper.dataset.originalText);
      wrapper.parentNode.replaceChild(textNode, wrapper);
    });
    const style = document.getElementById('neuroui-bionic-css');
    if (style) style.remove();
  }


  // =============================================
  // 2. SPOTLIGHT FOCUS MODE
  // =============================================

  function enableSpotlightMode() {
    if (spotlightActive) return;
    spotlightActive = true;

    const style = document.createElement('style');
    style.id = 'neuroui-spotlight-css';
    style.textContent = `
      .neuroui-spotlight-focus {
        box-shadow: 0 0 0 100vmax rgba(0, 0, 0, 0.82) !important;
        position: relative !important;
        z-index: 99998 !important;
        border-radius: 8px !important;
        padding: 10px 14px !important;
        transition: box-shadow 0.3s ease !important;
      }
      @media (prefers-color-scheme: dark) {
        .neuroui-spotlight-focus {
          background-color: rgba(30, 30, 40, 0.98) !important;
        }
      }
    `;
    document.head.appendChild(style);

    spotlightScrollHandler = () => requestAnimationFrame(updateSpotlight);
    window.addEventListener('scroll', spotlightScrollHandler, { passive: true });
    updateSpotlight();
  }

  function updateSpotlight() {
    if (!spotlightActive) return;
    const selector = [...TEXT_TAGS, ...HEADING_TAGS].join(', ');
    const paragraphs = document.querySelectorAll(selector);
    const center = window.innerHeight / 2;
    let closest = null;
    let closestDist = Infinity;

    const prev = document.querySelector('.neuroui-spotlight-focus');
    if (prev) prev.classList.remove('neuroui-spotlight-focus');

    paragraphs.forEach(p => {
      if (p.closest('#neuroui-reader') || p.closest('#neuroui-cls-badge')) return;
      const rect = p.getBoundingClientRect();
      if (rect.height === 0 || rect.bottom < 0 || rect.top > window.innerHeight) return;
      const dist = Math.abs(rect.top + rect.height / 2 - center);
      if (dist < closestDist) { closestDist = dist; closest = p; }
    });

    if (closest) closest.classList.add('neuroui-spotlight-focus');
  }

  function disableSpotlightMode() {
    spotlightActive = false;
    if (spotlightScrollHandler) {
      window.removeEventListener('scroll', spotlightScrollHandler);
      spotlightScrollHandler = null;
    }
    const prev = document.querySelector('.neuroui-spotlight-focus');
    if (prev) prev.classList.remove('neuroui-spotlight-focus');
    const style = document.getElementById('neuroui-spotlight-css');
    if (style) style.remove();
  }


  // =============================================
  // 3. CLS SCROLL MINIMAP
  // =============================================

  async function enableMinimap() {
    if (minimapActive) return;
    minimapActive = true;

    const allTags = [...TEXT_TAGS, ...HEADING_TAGS];
    const elements = [];
    allTags.forEach(tag => {
      document.querySelectorAll(tag).forEach(el => {
        const text = el.textContent?.trim();
        if (text && text.length >= 20 && isVisible(el)) {
          elements.push({ element: el, text });
        }
      });
    });

    if (elements.length === 0) { minimapActive = false; return; }

    // Call heatmap API
    let scores;
    try {
      const resp = await new Promise((resolve, reject) => {
        chrome.runtime.sendMessage({
          action: 'API_CALL', endpoint: '/api/heatmap', method: 'POST',
          body: { chunks: elements.map(e => e.text) },
        }, r => chrome.runtime.lastError ? reject(new Error(chrome.runtime.lastError.message)) : resolve(r));
      });
      if (resp.error) throw new Error(resp.error);
      scores = resp.scores;
    } catch (err) { minimapActive = false; return; }

    const colors = { low: '#22c55e', moderate: '#facc15', high: '#f97316', critical: '#ef4444' };
    const docHeight = document.documentElement.scrollHeight;

    const minimap = document.createElement('div');
    minimap.id = 'neuroui-minimap';
    minimap.style.cssText = `
      position:fixed; top:0; right:0; width:14px; height:100vh;
      z-index:999997; background:rgba(15,15,26,0.92);
      border-left:1px solid rgba(99,102,241,0.2); cursor:pointer;
    `;

    elements.forEach((item, i) => {
      if (!scores[i]) return;
      const rect = item.element.getBoundingClientRect();
      const absTop = rect.top + window.scrollY;
      const band = document.createElement('div');
      band.style.cssText = `
        position:absolute; top:${(absTop/docHeight)*100}%;
        left:2px; right:2px; height:${Math.max(0.4,(rect.height/docHeight)*100)}%;
        min-height:2px; background:${colors[scores[i].level]||colors.moderate};
        border-radius:1px; opacity:0.8;
      `;
      band.title = `CLS: ${Math.round(scores[i].cls)} (${scores[i].level})`;
      minimap.appendChild(band);
    });

    // Viewport indicator
    const vp = document.createElement('div');
    vp.id = 'neuroui-minimap-vp';
    vp.style.cssText = `
      position:absolute; left:0; right:0;
      border:1.5px solid rgba(99,102,241,0.8); border-radius:2px;
      background:rgba(99,102,241,0.08); pointer-events:none;
      transition:top 0.1s linear,height 0.1s linear;
    `;
    minimap.appendChild(vp);
    document.body.appendChild(minimap);

    minimap.addEventListener('click', e => {
      const r = minimap.getBoundingClientRect();
      const pct = (e.clientY - r.top) / r.height;
      window.scrollTo({ top: pct * (docHeight - window.innerHeight), behavior: 'smooth' });
    });

    minimapScrollHandler = () => {
      const v = document.getElementById('neuroui-minimap-vp');
      if (!v) return;
      v.style.top = (window.scrollY / docHeight * 100) + '%';
      v.style.height = (window.innerHeight / docHeight * 100) + '%';
    };
    window.addEventListener('scroll', minimapScrollHandler, { passive: true });
    minimapScrollHandler();
  }

  function disableMinimap() {
    minimapActive = false;
    const m = document.getElementById('neuroui-minimap');
    if (m) m.remove();
    if (minimapScrollHandler) {
      window.removeEventListener('scroll', minimapScrollHandler);
      minimapScrollHandler = null;
    }
  }


  // =============================================
  // 4. READER MODE (ZEN LAYOUT)
  // =============================================

  function enableReaderMode() {
    if (readerActive) return;
    readerActive = true;

    const allTags = [...TEXT_TAGS, ...HEADING_TAGS];
    const content = [];
    allTags.forEach(tag => {
      document.querySelectorAll(tag).forEach(el => {
        const text = el.textContent?.trim();
        if (text && text.length >= 10 && isVisible(el)) {
          content.push({ tag: el.tagName.toLowerCase(), text });
        }
      });
    });

    const html = content.map(el => {
      const t = el.text.replace(/</g, '&lt;').replace(/>/g, '&gt;');
      return `<${el.tag}>${t}</${el.tag}>`;
    }).join('\n');

    const reader = document.createElement('div');
    reader.id = 'neuroui-reader';
    reader.innerHTML = `
      <style>
        #neuroui-reader {
          position:fixed;top:0;left:0;right:0;bottom:0;z-index:999999;
          overflow-y:auto;background:var(--nr-bg,#0f0f1a);color:var(--nr-text,#d4d4d8);
          animation:nrFadeIn .4s ease;
        }
        @keyframes nrFadeIn { from{opacity:0} to{opacity:1} }
        .nr-toolbar {
          position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:10px;
          padding:10px 24px;background:var(--nr-bar,rgba(15,15,26,.95));
          backdrop-filter:blur(12px);border-bottom:1px solid rgba(255,255,255,.06);
          font-family:'Inter','Segoe UI',system-ui,sans-serif;
        }
        .nr-title {
          font-size:14px;font-weight:700;margin-right:auto;
          background:linear-gradient(135deg,#6366f1,#a78bfa);
          -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
        }
        .nr-toolbar button {
          background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);
          color:#e4e4e7;border-radius:6px;padding:6px 12px;font-size:13px;
          cursor:pointer;font-family:inherit;transition:all .2s;
        }
        .nr-toolbar button:hover {
          background:rgba(99,102,241,.15);border-color:rgba(99,102,241,.3);
        }
        .nr-body {
          max-width:680px;margin:0 auto;padding:48px 24px 120px;
          font-size:var(--nr-fs,18px);line-height:1.85;
          font-family:'Georgia','Charter',serif;
        }
        .nr-body h1{font-size:2em;font-weight:800;margin:1.2em 0 .5em;font-family:'Inter','Segoe UI',system-ui,sans-serif;color:var(--nr-h,#f4f4f5);line-height:1.3}
        .nr-body h2{font-size:1.5em;font-weight:700;margin:1em 0 .4em;font-family:'Inter','Segoe UI',system-ui,sans-serif;color:var(--nr-h,#f4f4f5);border-bottom:1px solid rgba(255,255,255,.06);padding-bottom:.3em}
        .nr-body h3,.nr-body h4,.nr-body h5,.nr-body h6{font-size:1.2em;font-weight:600;margin:.8em 0 .3em;font-family:'Inter','Segoe UI',system-ui,sans-serif;color:var(--nr-h,#e4e4e7)}
        .nr-body p{margin-bottom:1.3em}
        .nr-body li{margin-bottom:.6em;margin-left:1.5em}
        .nr-body blockquote{border-left:3px solid #6366f1;padding-left:16px;margin:1em 0;color:#9ca3af;font-style:italic}
        #neuroui-reader.theme-sepia{--nr-bg:#f4ecd8;--nr-text:#433422;--nr-h:#2c2010;--nr-bar:rgba(244,236,216,.95)}
        #neuroui-reader.theme-light{--nr-bg:#ffffff;--nr-text:#1f2937;--nr-h:#111827;--nr-bar:rgba(255,255,255,.95)}
      </style>
      <div class="nr-toolbar">
        <span class="nr-title">📄 Reader Mode — NeuroUI</span>
        <button id="nr-font-down" title="Decrease font">A−</button>
        <button id="nr-font-up" title="Increase font">A+</button>
        <button id="nr-theme" title="Toggle theme">🎨</button>
        <button id="nr-close" title="Close">✕ Close</button>
      </div>
      <div class="nr-body">${html}</div>`;

    document.body.appendChild(reader);
    document.body.style.overflow = 'hidden';

    let fontSize = 18;
    const themes = ['', 'theme-sepia', 'theme-light'];
    let themeIdx = 0;

    document.getElementById('nr-font-down').onclick = () => {
      fontSize = Math.max(14, fontSize - 2);
      reader.style.setProperty('--nr-fs', fontSize + 'px');
    };
    document.getElementById('nr-font-up').onclick = () => {
      fontSize = Math.min(28, fontSize + 2);
      reader.style.setProperty('--nr-fs', fontSize + 'px');
    };
    document.getElementById('nr-theme').onclick = () => {
      reader.classList.remove(...themes.filter(t => t));
      themeIdx = (themeIdx + 1) % themes.length;
      if (themes[themeIdx]) reader.classList.add(themes[themeIdx]);
    };
    document.getElementById('nr-close').onclick = () => {
      disableReaderMode();
      chrome.runtime.sendMessage({ action: 'READER_CLOSED' }).catch(() => {});
    };
  }

  function disableReaderMode() {
    readerActive = false;
    const r = document.getElementById('neuroui-reader');
    if (r) r.remove();
    document.body.style.overflow = '';
  }


  // =============================================
  // 5. READING PROGRESS BAR
  // =============================================

  function enableProgressBar() {
    if (progressBarActive) return;
    progressBarActive = true;

    const bar = document.createElement('div');
    bar.id = 'neuroui-progress-reading';
    bar.style.cssText = `
      position:fixed;top:0;left:0;height:3px;
      background:linear-gradient(90deg,#6366f1,#8b5cf6,#a78bfa);
      z-index:999999;width:0%;transition:width .15s linear;
      box-shadow:0 0 8px rgba(99,102,241,.4);border-radius:0 2px 2px 0;
    `;
    document.body.appendChild(bar);

    progressScrollHandler = () => {
      const pct = document.documentElement.scrollHeight - window.innerHeight;
      bar.style.width = (pct > 0 ? Math.min(100, (window.scrollY / pct) * 100) : 0) + '%';
    };
    window.addEventListener('scroll', progressScrollHandler, { passive: true });
    progressScrollHandler();
  }

  function disableProgressBar() {
    progressBarActive = false;
    const bar = document.getElementById('neuroui-progress-reading');
    if (bar) bar.remove();
    if (progressScrollHandler) {
      window.removeEventListener('scroll', progressScrollHandler);
      progressScrollHandler = null;
    }
  }


  // =============================================
  // UTILITY
  // =============================================

  function isVisible(el) {
    const style = window.getComputedStyle(el);
    return (
      style.display !== 'none' &&
      style.visibility !== 'hidden' &&
      style.opacity !== '0' &&
      el.offsetHeight > 0
    );
  }

})();
