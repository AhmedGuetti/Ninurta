// Ninurta color palette — vibrant magenta/fuchsia theme, transparent backgrounds.
// Mirror of the user's preferred palette (no opaque backgrounds, ever).

export const ACCENT = '#d946ef'        // fuchsia-500 — primary / borders
export const ACCENT_DEEP = '#a21caf'   // fuchsia-700 — deep
export const ACCENT_LIGHT = '#f472b6'  // pink-400 — lighter accents
export const TAGLINE = '#f0abfc'       // fuchsia-300 — title / tagline
export const TEXT = '#fdf4ff'          // fuchsia-50 — body / input
export const MUTED = '#a78bfa'         // violet-400 — dim / hints
export const PINK = '#f472b6'          // alias for accent-light
export const FUCHSIA = '#d946ef'       // alias for accent

// Fuchsia gradient for the banner (lightest → deepest)
export const VIOLET_GRADIENT = [
  '#fdf4ff', // fuchsia-50
  '#f0abfc', // fuchsia-300
  '#f472b6', // pink-400
  '#d946ef', // fuchsia-500
  '#a21caf', // fuchsia-700
  '#701a75', // fuchsia-900
]

// Status colors
export const STATUS_READY = '#00ff7f'
export const STATUS_BUSY = '#f472b6'
export const ERROR = '#fb7185'
