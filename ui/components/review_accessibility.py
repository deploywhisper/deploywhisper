"""Shared keyboard-accessibility helpers for report review surfaces."""

from __future__ import annotations

import re

from nicegui import ui

_REVIEW_ACCESSIBILITY_HEAD = """
<style>
.dw-review-region:focus-visible,
.dw-finding-row:focus-visible {
  outline: 2px solid var(--dw-accent);
  outline-offset: 4px;
}
</style>
<script>
(() => {
  if (window.dwReviewAccessibilityInstalled) {
    return;
  }
  window.dwReviewAccessibilityInstalled = true;

  const isVisible = (element) =>
    Boolean(element && (element.offsetWidth || element.offsetHeight || element.getClientRects().length));
  const isInteractive = (element) =>
    Boolean(
      element &&
      element.closest(
        'a, button, input, select, textarea, [role="button"], [contenteditable="true"]',
      ) &&
      !element.matches('[data-dw-finding-row="1"]'),
    );
  const activeElementMovedAway = (initialActiveElement) => {
    const activeElement = document.activeElement;
    return Boolean(
      activeElement &&
      activeElement !== document.body &&
      initialActiveElement &&
      activeElement !== initialActiveElement
    );
  };
  window.dwRestoreFocusWhenReady = ({
    focusRequestId,
    initialActiveElement,
    selector,
    timeoutMs = 3000,
  }) => {
    const startedAt = Date.now();
    let timeoutId = null;
    let observer = null;
    let done = false;
    const finish = (status) => {
      if (done) {
        return;
      }
      done = true;
      if (timeoutId) {
        window.clearTimeout(timeoutId);
      }
      if (observer) {
        observer.disconnect();
      }
      window.dwFocusRestoreLastStatus = { requestId: focusRequestId, status };
    };
    const tryFocus = () => {
      if (done) {
        return;
      }
      if (window.dwEvidenceFocusRequestId !== focusRequestId) {
        finish('cancelled');
        return;
      }
      if (activeElementMovedAway(initialActiveElement)) {
        finish('aborted');
        return;
      }
      const target = document.querySelector(selector);
      if (target) {
        target.focus();
        finish('focused');
        return;
      }
      if (Date.now() - startedAt >= timeoutMs) {
        finish('timeout');
        return;
      }
      timeoutId = window.setTimeout(tryFocus, 50);
    };
    observer = new MutationObserver(tryFocus);
    observer.observe(document.body, {
      attributes: true,
      attributeFilter: ['aria-expanded', 'aria-controls', 'id'],
      childList: true,
      subtree: true,
    });
    tryFocus();
  };
  const focusEvidenceToggle = (
    panelId,
    expectedExpanded,
    focusRequestId = (window.dwEvidenceFocusRequestId || 0) + 1,
    initialActiveElement = document.activeElement,
  ) => {
    window.dwEvidenceFocusRequestId = focusRequestId;
    window.dwRestoreFocusWhenReady({
      focusRequestId,
      initialActiveElement,
      selector: `[data-dw-evidence-toggle="1"][aria-controls="${panelId}"][aria-expanded="${expectedExpanded}"]`,
    });
  };

  document.addEventListener(
    'click',
    (event) => {
      const target = event.target instanceof Element ? event.target : null;
      const button = target && target.closest('[data-dw-evidence-toggle="1"]');
      if (!button) {
        return;
      }
      const panelId = button.getAttribute('aria-controls');
      const expectedExpanded = button.getAttribute('aria-expanded') === 'true' ? 'false' : 'true';
      const initialActiveElement = document.activeElement;
      if (panelId) {
        setTimeout(
          () => focusEvidenceToggle(
            panelId,
            expectedExpanded,
            (window.dwEvidenceFocusRequestId || 0) + 1,
            initialActiveElement,
          ),
          0,
        );
      }
    },
    true,
  );

  document.addEventListener(
    'keydown',
    (event) => {
      if (event.key === 'Escape') {
        const dialogs = Array.from(document.querySelectorAll('[data-dw-modal-root="1"]')).filter(isVisible);
        const topmostDialog = dialogs.at(-1);
        const closeButton = topmostDialog && topmostDialog.querySelector('[data-dw-modal-close="1"]');
        if (closeButton) {
          event.preventDefault();
          closeButton.click();
          return;
        }
      }

      const target = event.target instanceof Element ? event.target : null;
      const row = target && target.closest('[data-dw-finding-row="1"]');
      if (!row || target !== row || isInteractive(target)) {
        return;
      }

      const table = row.closest('[data-dw-findings-table="1"]');
      if (!table) {
        return;
      }
      const rows = Array.from(table.querySelectorAll('[data-dw-finding-row="1"]')).filter(isVisible);
      const currentIndex = rows.indexOf(row);
      if (currentIndex === -1) {
        return;
      }

      if (event.key === 'ArrowDown') {
        event.preventDefault();
        rows[Math.min(currentIndex + 1, rows.length - 1)].focus();
        return;
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault();
        rows[Math.max(currentIndex - 1, 0)].focus();
        return;
      }
      if (event.key === 'Home') {
        event.preventDefault();
        rows[0].focus();
        return;
      }
      if (event.key === 'End') {
        event.preventDefault();
        rows[rows.length - 1].focus();
        return;
      }
      if (event.key === 'Enter' || event.key === ' ' || event.key === 'Spacebar') {
        event.preventDefault();
        row.dispatchEvent(new CustomEvent('dw-key-toggle', { bubbles: true }));
      }
    },
    true,
  );
})();
</script>
"""


def register_review_accessibility() -> None:
    """Inject the shared keyboard-accessibility script and focus styles."""
    ui.add_head_html(_REVIEW_ACCESSIBILITY_HEAD)


def decorate_review_section(element, *, section: str, label: str) -> None:
    """Mark a review section as a focusable landmark in natural DOM order."""
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(label))
    safe_label = re.sub(r" {2,}", " ", text).strip()
    safe_label = safe_label.replace("\\", "\\\\").replace('"', '\\"')
    element.props(
        f'tabindex=0 role=region data-dw-review-section="{section}" aria-label="{safe_label}"'
    )
    element.classes("dw-review-region")


def decorate_modal_card(element, *, label: str) -> None:
    """Mark a dialog card so Escape can close the active modal consistently."""
    register_review_accessibility()
    element.props(
        f'data-dw-modal-root="1" role=dialog aria-modal=true aria-label="{label}"'
    )


def decorate_modal_close(control) -> None:
    """Mark a control as the Escape-close target for the active modal."""
    control.props('data-dw-modal-close="1"')
