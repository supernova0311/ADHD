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

    // 8. Remove progress overlay
    hideProgressOverlay();

    // 9. Restore body overflow (in case cookie banner removal locked it)
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
