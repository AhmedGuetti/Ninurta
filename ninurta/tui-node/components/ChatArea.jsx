// Scrollable chat log area — full width, streaming assistant line.
// Mirrors hermes StreamingAssistant: last turn streams inline.

import React from 'react'
import { Box, Text } from '@hermes/ink'
import { ACCENT_LIGHT, PINK, FUCHSIA, TEXT, MUTED, TAGLINE } from '../lib/palette.js'

export default function ChatArea({ messages, streaming, step, width }) {
  return (
    <Box flexDirection="column" width={width}>
      {messages.map((msg, i) => {
        if (msg.role === 'user') {
          return (
            <Text key={i} color={TEXT} wrap="wrap">
              <Text bold color={PINK}>
                you:{' '}
              </Text>
              {msg.text}
            </Text>
          )
        }
        if (msg.role === 'system') {
          return (
            <Text key={i} color={TAGLINE} wrap="wrap">
              <Text bold color={TAGLINE}>
                ⚠{' '}
              </Text>
              {msg.text}
            </Text>
          )
        }
        return (
          <Text key={i} color={TEXT} wrap="wrap">
            <Text bold color={FUCHSIA}>
              ninurta:{' '}
            </Text>
            {msg.text}
          </Text>
        )
      })}
      {streaming && (
        <Text color={TEXT} wrap="wrap">
          <Text bold color={FUCHSIA}>
            ninurta:{' '}
          </Text>
          {streaming}
        </Text>
      )}
      {step && !streaming && (
        <Text color={TAGLINE} italic>
          {step}
        </Text>
      )}
    </Box>
  )
}
