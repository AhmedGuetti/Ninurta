// Ninurta App — Hermes-style full-width INLINE layout (no alternate screen:
// the host terminal's native scrollback and transparency must keep working).
import React, { useCallback, useEffect, useState } from 'react'
import { Box, Text, useInput, useStdout } from '@hermes/ink'
import { useStore } from '@nanostores/react'

import Banner from '../../components/Banner.jsx'
import InfoBox from '../../components/InfoBox.jsx'
import ChatArea from '../../components/ChatArea.jsx'
import StatusBar from '../../components/StatusBar.jsx'
import InputPrompt from '../../components/InputPrompt.jsx'
import Selector from '../../components/Selector.jsx'
import CompletionOverlay from '../../components/CompletionOverlay.jsx'
import { useMainApp } from './useMainApp.js'
import { $turnState, $modelId, $selector, $completion, clearSelector } from './turnStore.js'
import { ACCENT, MUTED, TEXT } from '../../lib/palette.js'

type FocusZone = 'input' | 'pipelines' | 'commands'

export function App({ cwd, version }: { cwd: string; version: string }) {
  const { stdout } = useStdout()
  const cols: number = stdout?.columns ?? 80
  // Tab: cycle focus  input → pipelines → commands → input
  // Enter: toggle focused section (returns focus to input)
  // Esc:   back to input
  // Ctrl+C: cancel running pipeline · Ctrl+D: exit · Ctrl+G: gateway log
  const { ready, error, stderrLog, sendMessage, runSlash, cancel } = useMainApp()
  const turn = useStore($turnState)
  const modelId = useStore($modelId)  // reactive — updated by /model
  const sel = useStore($selector)
  const selectorActive = sel.active
  const completion = useStore($completion)
  const completionActive = completion.active
  const [showGatewayLog, setShowGatewayLog] = useState(false)
  const [focus, setFocus] = useState<FocusZone>('input')
  const [pipesOpen, setPipesOpen] = useState(true)
  const [cmdsOpen, setCmdsOpen] = useState(true)

  // Key bindings: Tab cycle focus, Enter toggle section, Esc back to input,
  // Ctrl+C: selector open → dismiss · pipeline busy → cancel · else → exit
  // Ctrl+D exit, Ctrl+G gateway log
  useInput((input: string, key: { ctrl?: boolean; tab?: boolean; return?: boolean; escape?: boolean }) => {
    if (key.ctrl && input === 'c') {
      if (selectorActive) {
        clearSelector()
        return
      }
      if (turn.busy) {
        cancel()
        return
      }
      process.exit(0)
    }
    if (key.ctrl && input === 'd') process.exit(0)
    if (key.ctrl && input === 'g') setShowGatewayLog((v) => !v)
    if (key.tab) {
      // Slash-completion dropdown is up → Tab completes the command
      // (InputPrompt handles it); don't steal focus.
      if (completionActive) return
      setFocus((f) => (f === 'input' ? 'pipelines' : f === 'pipelines' ? 'commands' : 'input'))
      return
    }
    if (key.escape) {
      setFocus('input')
      return
    }
    if (key.return && focus !== 'input') {
      if (focus === 'pipelines') setPipesOpen((v) => !v)
      else setCmdsOpen((v) => !v)
      setFocus('input')
    }
  })

  const handleSubmit = useCallback(
    (text: string) => {
      const low = text.trim().toLowerCase()
      if (['quit', 'exit', 'q', '/exit', '/quit'].includes(low)) {
        process.exit(0)
        return
      }
      if (text.startsWith('/')) {
        const [cmd, ...args] = text.slice(1).split(' ')
        void runSlash(cmd, args)
      } else {
        void sendMessage(text)
      }
    },
    [runSlash, sendMessage]
  )

  // Update terminal tab / window title based on pipeline state
  useEffect(() => {
    const title = turn.busy ? '⏳ Ninurta — working...' : '⚡ Ninurta'
    process.stdout.write(`\x1b]0;${title}\x07`)
  }, [turn.busy])

  // Hermes INLINE_MODE layout — the skill-documented anti-scroll pattern:
  // `height` (NOT minHeight) clamps the frame to the terminal; rows - 1 keeps
  // the bottom row untouched so writing there never triggers a scroll. Ink
  // re-renders on SIGWINCH, so Ctrl+'+' / font-zoom resizes flow through.
  const rows = Math.max(4, (stdout?.rows ?? 24) - 1)

  return (
    <Box flexDirection="column" width={cols} height={rows} position="relative">
        <Banner width={cols} />
        <InfoBox
          modelId={modelId}
          cwd={cwd}
          version={version}
          width={cols}
          focus={focus}
          pipesOpen={pipesOpen}
          cmdsOpen={cmdsOpen}
        />
        {/* Scrollable chat log — the transcript grows unboundedly, so ChatArea
            caps itself to the most recent MAX_LINES. This wrapper fills the
            remaining space (flexGrow) and CLIPS any overflow (a plain Box,
            not ScrollBox: the scroll machinery re-measures on growth and can
            misplace rows in the inline renderer). */}
        <Box flexGrow={1} flexShrink={1} minHeight={2} overflow="hidden" width={cols}>
          <ChatArea messages={turn.messages} streaming={turn.streaming} step={turn.step} width={cols} />
        </Box>

        {!ready && !error && (
          <Text color={MUTED} dim>
            connecting to gateway…
          </Text>
        )}
        {error && (
          <Text color="#fb7185">
            gateway error: {error} — Ctrl+G to inspect stderr
          </Text>
        )}

        <StatusBar
          modelId={modelId}
          cwd={cwd}
          width={cols}
          ready={ready}
          busy={turn.busy}
          step={turn.step}
          stepMsg={turn.stepMsg}
        />

        {showGatewayLog && (
          <Box flexDirection="column" borderStyle="round" borderColor={MUTED} width={cols}>
            <Text color={ACCENT} bold>
              gateway stderr (last 200)
            </Text>
            {stderrLog.map((l, i) => (
              <Text key={i} color={MUTED} dim>
                {l}
              </Text>
            ))}
          </Box>
        )}

        <Selector width={cols} />
        <Box width={cols}>
          <InputPrompt
            onSubmit={handleSubmit}
            width={cols}
            active={focus === 'input' && !selectorActive}
            busy={turn.busy}
            step={turn.step}
            stepMsg={turn.stepMsg}
            modelId={modelId}
            selectorActive={selectorActive}
          />
        </Box>

        {/* Slash-completion dropdown — absolute overlay floating above the
            input prompt, OUTSIDE the height-clamped flex flow (see
            CompletionOverlay.jsx for why in-flow corrupts the layout). */}
        <CompletionOverlay width={cols} />
    </Box>
  )
}
