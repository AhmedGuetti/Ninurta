// Force 24-bit truecolor before chalk/@hermes-ink initialize (hermes pattern:
// ui-tui/src/lib/forceTruecolor.ts). Ninurta targets modern RGB terminals
// (Windows Terminal / WSL); NO_COLOR still respected.
if (!('NO_COLOR' in process.env)) {
  if (!process.env.COLORTERM) {
    process.env.COLORTERM = 'truecolor'
  }
  process.env.FORCE_COLOR = '3'
}

export {}
