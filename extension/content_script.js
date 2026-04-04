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
 */

(() => {
  'use strict';

  // Guard against multiple injections
  if (window.__NEUROUI_INJECTED__) return;
  window.__NEUROUI_INJECTED__ = true;

  // --- State ---
  let isActive = false;
  let injectedStylesheet = null;
  let clsBadge = null;
  let originalTexts = new Map(); // Store originals for reset

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
  });


  // =============================================
  // ACTIVATION PIPELINE
  // =============================================

  async function activate(profile, settings) {
    try {
      isActive = true;
      showProcessingIndicator();

      // Step 1: Extract text content
      const textElements = extractTextElements();
      const chunks = chunkTextElements(textElements);

      // Step 2: Build DOM snapshot
      const domSnapshot = buildDOMSnapshot();

      // Step 3: Call backend API
      const apiResponse = await callBackendAPI(chunks, profile, domSnapshot, settings);

      if (!apiResponse || apiResponse.error) {
        throw new Error(apiResponse?.error || 'Backend unavailable');
      }

      // Step 4: Apply text transformations
      applyTextTransformations(textElements, apiResponse.simplified_chunks);

      // Step 5: Inject visual CSS
      injectCSS(apiResponse.visual_css + '\n' + apiResponse.focus_css);

      // Step 6: Execute focus JS commands
      if (apiResponse.focus_js_commands) {
        apiResponse.focus_js_commands.forEach(cmd => {
          try { eval(cmd); } catch (e) { /* Silently handle */ }
        });
      }

      // Step 7: Hide distractor elements
      if (apiResponse.hide_selectors) {
        hideElements(apiResponse.hide_selectors);
      }

      // Step 8: Show CLS badge
      const clsBefore = apiResponse.cls_before?.cls || 0;
      const clsAfter = apiResponse.cls_after?.cls || 0;
      showCLSBadge(clsBefore, clsAfter);

      hideProcessingIndicator();

      return {
        success: true,
        cls_before: clsBefore,
        cls_after: clsAfter,
        metrics: apiResponse.metrics,
      };

    } catch (error) {
      hideProcessingIndicator();
      console.error('[NeuroUI] Activation failed:', error);
      return { success: false, error: error.message };
    }
  }


  function deactivate() {
    isActive = false;

    // Restore original text content
    originalTexts.forEach((originalText, element) => {
      if (element && element.isConnected) {
        element.textContent = originalText;
      }
    });
    originalTexts.clear();

    // Remove injected CSS
    if (injectedStylesheet) {
      injectedStylesheet.remove();
      injectedStylesheet = null;
    }

    // Remove CLS badge
    if (clsBadge) {
      clsBadge.remove();
      clsBadge = null;
    }

    // Remove processing indicator
    hideProcessingIndicator();

    // Reload page to fully reset (simplest reliable approach)
    // Only if significant changes were made
    // location.reload();
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

        // Apply simplified text
        item.element.textContent = simplified;

        // Add visual indicator that this text was simplified
        item.element.style.borderLeft = '2px solid rgba(99, 102, 241, 0.3)';
        item.element.style.paddingLeft = '8px';
      }
    });
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
          el.style.setProperty('display', 'none', 'important');
        });
      } catch (e) {
        // Invalid selector — skip silently
      }
    });
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
        transition: opacity 0.3s, transform 0.3s;
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
    `;

    document.body.appendChild(clsBadge);
  }


  function showProcessingIndicator() {
    let indicator = document.getElementById('neuroui-processing');
    if (indicator) return;

    indicator = document.createElement('div');
    indicator.id = 'neuroui-processing';
    indicator.innerHTML = `
      <div style="
        position: fixed; top: 0; left: 0; right: 0; z-index: 999999;
        height: 3px; background: linear-gradient(90deg, #6366f1, #8b5cf6, #a78bfa, #6366f1);
        background-size: 200% 100%;
        animation: neuroui-loading 1.5s ease infinite;
      "></div>
      <style>
        @keyframes neuroui-loading {
          0% { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
      </style>
    `;
    document.body.appendChild(indicator);
  }


  function hideProcessingIndicator() {
    const indicator = document.getElementById('neuroui-processing');
    if (indicator) indicator.remove();
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
