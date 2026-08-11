#!/usr/bin/env -S npx tsx
// Ninurta TUI — Hermes Agent TUI architecture.
// Node/Ink frontend (ui-tui/src/entry.tsx pattern) + Python JSON-RPC gateway.

import './lib/forceTruecolor.js' // MUST be first import — nudges chalk before it loads

import React from 'react'
import { render } from '@hermes/ink'

import { App } from './src/app/App.js'
import { $modelId } from './src/app/turnStore.js'

if (!process.stdin.isTTY) {
  console.log('ninurta-tui: no TTY (stdin is not a terminal)')
  process.exit(0)
}

// Clean startup slate (hermes entry.tsx): clear screen + scrollback so the TUI
// fills the terminal from the top with no leftover output above it.
process.stdout.write('\x1b[2J\x1b[H\x1b[3J')

// Set terminal tab / window title
process.stdout.write('\x1b]0;⚡ Ninurta\x07')

// ── Parse CLI args ───────────────────────────────────────────────────────────
const args = process.argv.slice(2)
const modelId = args[0] || 'gemini-3.6-flash'
$modelId.set(modelId)  // seed the reactive store from CLI arg
const cwd = args[1] || process.cwd()
const version = '0.2.0'

// ── Graceful exit: leave the terminal pristine (hermes setupGracefulExit) ────
const cleanup = () => {
  process.stdout.write('\x1b[?25h') // show cursor
}
process.on('exit', cleanup)

// ── Render ───────────────────────────────────────────────────────────────────
render(<App cwd={cwd} version={version} />, {
  exitOnCtrlC: false
})
