// Bordered info box with bow art (left) + system info (right).
// Mirror of _build_box_text() in the Python prompt_toolkit version.

import React from "react";
import { Box, Text } from "ink";
import { ACCENT, ACCENT_LIGHT, MUTED, TEXT } from "../lib/palette.js";
import { loadBowArt } from "../lib/art.js";

export default function InfoBox({ modelId, cwd, version }) {
  const bow = loadBowArt();
  const leftLines = [];
  if (bow) {
    leftLines.push(...bow.split("\n"));
  }
  leftLines.push("");
  leftLines.push(`${modelId} · Nous Research`);
  leftLines.push(cwd);
  leftLines.push(`Session: ${version}`);

  const rightLines = [];
  rightLines.push(`Ninurta v${version}`);
  rightLines.push("");
  rightLines.push("▼ Pipelines");
  rightLines.push("  extract → extractor");
  rightLines.push("  resume  → reader · validator · reviewer · saver");
  rightLines.push("");
  rightLines.push("▼ Commands");
  rightLines.push("  ninurta tui      interactive chat interface");
  rightLines.push("  ninurta extract  parse a job description");
  rightLines.push("  ninurta resume   parse + validate + save resume");
  rightLines.push("  ninurta models   list available models");

  const leftW = Math.max(...leftLines.map((l) => l.length), 0);
  const rightW = Math.max(...rightLines.map((l) => l.length), 0);
  const gap = 4;
  const innerW = leftW + gap + rightW;
  const boxW = innerW + 4;

  const maxRows = Math.max(leftLines.length, rightLines.length);
  while (leftLines.length < maxRows) leftLines.push("");
  while (rightLines.length < maxRows) rightLines.push("");

  const title = ` NINURTA v${version} `;
  const topPad = Math.max(0, boxW - 2 - title.length);

  const bowLineCount = bow ? bow.split("\n").length : 0;

  return (
    <Box flexDirection="column">
      <Text color={ACCENT}>
        ╭{title}{"─".repeat(topPad)}╮
      </Text>
      {leftLines.map((_, i) => {
        const lPadded = leftLines[i].padEnd(leftW);
        const rPadded = rightLines[i].padEnd(rightW);
        const row = `${lPadded}${" ".repeat(gap)}${rPadded}`.padEnd(innerW);
        return (
          <Text key={i} color={i < bowLineCount ? ACCENT_LIGHT : TEXT}>
            │ {row} │
          </Text>
        );
      })}
      <Text color={ACCENT}>
        ╰{"─".repeat(boxW - 2)}╯
      </Text>
      <Text> </Text>
      <Text color={MUTED}>
        Type below and press Enter — it echoes back.  quit / Ctrl+C to exit.
      </Text>
      <Text> </Text>
    </Box>
  );
}
