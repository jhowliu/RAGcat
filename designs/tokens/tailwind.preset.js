// RAGcat Tailwind preset. Import tokens.css once globally, then:
//   // tailwind.config.js
//   module.exports = { presets: [require('./design/tokens/tailwind.preset.js')], content: [...] }
// Utilities: bg-rc-bg, text-rc-ink, border-rc-border, rounded-md (8px), shadow-overlay, font-serif, max-w-app ...
// Note: screens are RAGcat's (lg = 960px, xl = 1024px), not Tailwind's defaults.
module.exports = {
  "theme": {
    "screens": {
      "sm": "640px",
      "md": "768px",
      "lg": "960px",
      "xl": "1024px"
    },
    "extend": {
      "colors": {
        "rc": {
          "bg": "var(--rc-bg)",
          "surface": "var(--rc-surface)",
          "surface-subtle": "var(--rc-surface-subtle)",
          "surface-sunken": "var(--rc-surface-sunken)",
          "surface-hover": "var(--rc-surface-hover)",
          "ink": "var(--rc-ink)",
          "ink-hover": "var(--rc-ink-hover)",
          "on-ink": "var(--rc-on-ink)",
          "text-secondary": "var(--rc-text-secondary)",
          "text-muted": "var(--rc-text-muted)",
          "text-control": "var(--rc-text-control)",
          "text-subtle": "var(--rc-text-subtle)",
          "text-disabled": "var(--rc-text-disabled)",
          "border": "var(--rc-border)",
          "border-subtle": "var(--rc-border-subtle)",
          "border-strong": "var(--rc-border-strong)",
          "border-input": "var(--rc-border-input)",
          "accent-eyebrow": "var(--rc-accent-eyebrow)",
          "citation": "var(--rc-citation)",
          "selection": "var(--rc-selection)",
          "selection-fill": "var(--rc-selection-fill)",
          "success": "var(--rc-success)",
          "success-bg": "var(--rc-success-bg)",
          "success-text": "var(--rc-success-text)",
          "warning": "var(--rc-warning)",
          "warning-bg": "var(--rc-warning-bg)",
          "warning-text": "var(--rc-warning-text)",
          "callout-bg": "var(--rc-callout-bg)",
          "callout-border": "var(--rc-callout-border)",
          "callout-icon": "var(--rc-callout-icon)",
          "info-bg": "var(--rc-info-bg)",
          "info-text": "var(--rc-info-text)",
          "neutral-bg": "var(--rc-neutral-bg)",
          "neutral-text": "var(--rc-neutral-text)",
          "dot-idle": "var(--rc-dot-idle)",
          "danger": "var(--rc-danger)",
          "header-bg": "var(--rc-header-bg)",
          "bg-hover": "var(--rc-bg-hover)",
          "on-ink-muted": "var(--rc-on-ink-muted)",
          "on-ink-hover": "var(--rc-on-ink-hover)",
          "avatar-bg": "var(--rc-avatar-bg)",
          "pdf-line": "var(--rc-pdf-line)",
          "pdf-rule": "var(--rc-pdf-rule)",
          "selection-tint": "var(--rc-selection-tint)",
          "selection-card": "var(--rc-selection-card)"
        }
      },
      "fontFamily": {
        "serif": [
          "var(--rc-font-serif)"
        ],
        "sans": [
          "var(--rc-font-sans)"
        ],
        "mono": [
          "var(--rc-font-mono)"
        ]
      },
      "borderRadius": {
        "xs": "var(--rc-radius-xs)",
        "sm": "var(--rc-radius-sm)",
        "seg-option": "var(--rc-radius-seg-option)",
        "callout": "var(--rc-radius-callout)",
        "seg": "var(--rc-radius-seg)",
        "md": "var(--rc-radius-md)",
        "lg": "var(--rc-radius-lg)",
        "xl": "var(--rc-radius-xl)",
        "full": "var(--rc-radius-full)",
        "bar": "var(--rc-radius-bar)",
        "bubble": "var(--rc-radius-bubble)",
        "switch": "var(--rc-radius-switch)"
      },
      "boxShadow": {
        "raised": "var(--rc-shadow-raised)",
        "raised-lg": "var(--rc-shadow-raised-lg)",
        "overlay": "var(--rc-shadow-overlay)"
      },
      "maxWidth": {
        "landing": "var(--rc-container-landing)",
        "app": "var(--rc-container-app)",
        "review": "var(--rc-container-review)"
      },
      "transitionDuration": {
        "rc": "var(--rc-duration)"
      }
    }
  }
};
