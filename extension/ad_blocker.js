/**
 * NeuroUI — Cosmetic Ad Filter
 * ==============================
 * CSS-based element hiding for ad containers that slip through
 * network-level blocking. Injected as a content script.
 *
 * This is the second layer of ad blocking:
 * Layer 1: declarativeNetRequest blocks network requests (ad_block_rules.json)
 * Layer 2: This CSS hides any leftover DOM elements (cosmetic filtering)
 * Layer 3: Focus Agent hides profile-specific distractors (backend)
 */

(() => {
  'use strict';

  // Guard against double injection
  if (window.__NEUROUI_ADBLOCKER__) return;
  window.__NEUROUI_ADBLOCKER__ = true;

  // --- Configuration ---
  let adBlockEnabled = true;

  // Check if ad blocking is enabled in storage
  chrome.storage.local.get(['adBlockEnabled'], (result) => {
    adBlockEnabled = result.adBlockEnabled !== false; // Default: ON
    if (adBlockEnabled) {
      injectCosmeticFilters();
      observeNewAds();
    }
  });

  // Listen for toggle messages from popup
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.action === 'TOGGLE_ADBLOCK') {
      adBlockEnabled = msg.enabled;
      chrome.storage.local.set({ adBlockEnabled: msg.enabled });
      if (adBlockEnabled) {
        injectCosmeticFilters();
        observeNewAds();
      } else {
        removeCosmeticFilters();
      }
    }
  });

  // =============================================
  // COSMETIC FILTER — CSS ELEMENT HIDING
  // =============================================

  const COSMETIC_CSS = `
    /* NeuroUI Cosmetic Ad Filter */

    /* === Google Ads === */
    ins.adsbygoogle,
    .adsbygoogle,
    [id^="google_ads_"],
    [id^="div-gpt-ad"],
    [data-google-query-id],
    .google-auto-placed,
    .ap_container,
    iframe[src*="doubleclick.net"],
    iframe[src*="googlesyndication"],
    iframe[id^="google_ads_"],
    div[id^="google_ads_"] {
      display: none !important;
      height: 0 !important;
      min-height: 0 !important;
      max-height: 0 !important;
      overflow: hidden !important;
    }

    /* === Generic Ad Containers === */
    [class*="ad-wrapper"],
    [class*="ad_wrapper"],
    [class*="ad-container"],
    [class*="ad_container"],
    [class*="ad-banner"],
    [class*="ad_banner"],
    [class*="ad-slot"],
    [class*="ad_slot"],
    [class*="ad-unit"],
    [class*="ad_unit"],
    [class*="ad-block"],
    [class*="ad_block"],
    [class*="ad-placement"],
    [class*="ad_placement"],
    [class*="advert-"],
    [class*="advert_"],
    [class*="advertisement"],
    [id*="ad-wrapper"],
    [id*="ad_wrapper"],
    [id*="ad-container"],
    [id*="ad_container"],
    [id*="ad-banner"],
    [id*="ad_banner"],
    [id*="ad-slot"],
    [id*="ad-unit"],
    [id*="advertisement"],
    div[aria-label="advertisement"],
    div[aria-label="Ads"],
    aside[aria-label="advertisement"],
    section[aria-label="Sponsored"] {
      display: none !important;
      height: 0 !important;
      min-height: 0 !important;
    }

    /* === Sponsored Content / Native Ads === */
    [class*="sponsored"],
    [class*="Sponsored"],
    [class*="promoted-"],
    [class*="native-ad"],
    [data-ad-slot],
    [data-ad-client],
    [data-adunit],
    [data-ad],
    [data-ad-wrapper] {
      display: none !important;
    }

    /* === Taboola / Outbrain / Content Recommendation === */
    .taboola-wrapper,
    [id^="taboola-"],
    [class*="taboola"],
    .OUTBRAIN,
    [data-widget-id*="outbrain"],
    [class*="outbrain"],
    .revcontent,
    [id*="revcontent"],
    .zergnet,
    [id*="zergnet"],
    [class*="mgid"],
    [id*="mgid"] {
      display: none !important;
    }

    /* === Cookie Consent / GDPR Banners === */
    [class*="cookie-banner"],
    [class*="cookie-consent"],
    [class*="cookie-notice"],
    [class*="cookie-popup"],
    [class*="cookie_banner"],
    [class*="cookie_consent"],
    [id*="cookie-banner"],
    [id*="cookie-consent"],
    [id*="cookie-notice"],
    [id*="cookieConsent"],
    [id*="CookieConsent"],
    [class*="gdpr"],
    [id*="gdpr"],
    [class*="consent-banner"],
    [class*="privacy-banner"],
    [id*="consent-banner"],
    [aria-label*="cookie"],
    [aria-label*="Cookie"],
    [aria-label*="consent"] {
      display: none !important;
    }

    /* === Newsletter / Subscription Popups === */
    [class*="newsletter-popup"],
    [class*="newsletter-modal"],
    [class*="subscribe-popup"],
    [class*="subscribe-modal"],
    [class*="email-signup"],
    [class*="signup-modal"],
    [id*="newsletter-popup"],
    [id*="newsletter-modal"],
    [id*="subscribe-popup"] {
      display: none !important;
    }

    /* === Social Share Floating Bars === */
    [class*="social-share-bar"][style*="fixed"],
    [class*="share-widget"][style*="fixed"],
    [class*="floating-social"] {
      display: none !important;
    }

    /* === Chat Widgets === */
    [class*="intercom-"],
    [id*="intercom-"],
    [class*="drift-"],
    [id*="drift-widget"],
    [class*="crisp-"],
    [id*="crisp-chatbox"],
    [class*="tawk-"],
    [id*="tawk-"],
    [class*="zendesk-"],
    [id*="launcher"][data-testid*="chat"],
    iframe[title*="chat widget"],
    iframe[title*="intercom"],
    iframe[title*="Zendesk"] {
      display: none !important;
    }

    /* === Notification Bars / Promo Banners === */
    [class*="notification-bar"][style*="fixed"],
    [class*="promo-bar"][style*="fixed"],
    [class*="announcement-bar"],
    [class*="top-bar-dismiss"],
    [class*="site-banner"][style*="fixed"] {
      display: none !important;
    }

    /* === Prevent body scroll lock from hidden modals === */
    body.modal-open,
    body.no-scroll,
    body[style*="overflow: hidden"],
    html[style*="overflow: hidden"] {
      overflow: auto !important;
      position: static !important;
    }
  `;

  // --- Counters ---
  let blockedElementCount = 0;

  function injectCosmeticFilters() {
    if (document.getElementById('neuroui-adblock-css')) return;

    const style = document.createElement('style');
    style.id = 'neuroui-adblock-css';
    style.textContent = COSMETIC_CSS;
    (document.head || document.documentElement).appendChild(style);

    // Count how many elements are being hidden
    countBlockedElements();

    // Report stats
    chrome.storage.local.get(['totalAdsBlocked'], (result) => {
      const total = (result.totalAdsBlocked || 0) + blockedElementCount;
      chrome.storage.local.set({ totalAdsBlocked: total, sessionAdsBlocked: blockedElementCount });
    });
  }

  function removeCosmeticFilters() {
    const style = document.getElementById('neuroui-adblock-css');
    if (style) style.remove();
  }

  function countBlockedElements() {
    // Sample some common ad selectors
    const selectors = [
      '.adsbygoogle', '[id^="google_ads_"]', '[id^="div-gpt-ad"]',
      '[class*="ad-wrapper"]', '[class*="ad-container"]', '[class*="ad-banner"]',
      '[class*="taboola"]', '.OUTBRAIN', '[class*="cookie-banner"]',
      '[class*="cookie-consent"]', '[class*="newsletter-popup"]',
    ];

    blockedElementCount = 0;
    selectors.forEach(sel => {
      try {
        blockedElementCount += document.querySelectorAll(sel).length;
      } catch (e) { /* invalid selector */ }
    });
  }

  // =============================================
  // MUTATION OBSERVER — Catch dynamically injected ads
  // =============================================

  let observer = null;

  function observeNewAds() {
    if (observer) return;

    observer = new MutationObserver((mutations) => {
      if (!adBlockEnabled) return;

      let newAdsFound = false;

      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          if (node.nodeType !== Node.ELEMENT_NODE) continue;

          // Check if the added element is an ad
          const el = node;
          const classStr = (el.className || '').toString().toLowerCase();
          const idStr = (el.id || '').toLowerCase();

          if (
            classStr.includes('adsbygoogle') ||
            classStr.includes('ad-wrapper') ||
            classStr.includes('ad-container') ||
            classStr.includes('ad-banner') ||
            classStr.includes('taboola') ||
            classStr.includes('outbrain') ||
            classStr.includes('cookie-consent') ||
            classStr.includes('cookie-banner') ||
            idStr.includes('google_ads') ||
            idStr.includes('div-gpt-ad') ||
            el.hasAttribute('data-ad-slot') ||
            el.hasAttribute('data-google-query-id')
          ) {
            el.style.setProperty('display', 'none', 'important');
            newAdsFound = true;
          }

          // Also check iframes (common ad delivery mechanism)
          if (el.tagName === 'IFRAME') {
            const src = (el.src || '').toLowerCase();
            if (
              src.includes('doubleclick') ||
              src.includes('googlesyndication') ||
              src.includes('adservice') ||
              src.includes('taboola') ||
              src.includes('outbrain')
            ) {
              el.style.setProperty('display', 'none', 'important');
              newAdsFound = true;
            }
          }
        }
      }

      if (newAdsFound) {
        blockedElementCount++;
        chrome.storage.local.get(['totalAdsBlocked'], (result) => {
          chrome.storage.local.set({ totalAdsBlocked: (result.totalAdsBlocked || 0) + 1 });
        });
      }
    });

    observer.observe(document.documentElement, {
      childList: true,
      subtree: true,
    });
  }

})();
