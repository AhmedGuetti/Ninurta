// Violet-gradient NINURTA banner.
// Each line of the ASCII art gets a colour from the gradient.

import React from "react";
import { Box, Text } from "ink";
import { VIOLET_GRADIENT, TAGLINE } from "../lib/palette.js";
import { loadBanner } from "../lib/art.js";

const BANNER_LINES = loadBanner().split("\n");

export default function Banner() {
  return (
    <Box flexDirection="column">
      {BANNER_LINES.map((line, i) => {
        const step = Math.min(
          Math.floor((i / Math.max(BANNER_LINES.length, 1)) * VIOLET_GRADIENT.length),
          VIOLET_GRADIENT.length - 1,
        );
        return (
          <Text key={i} bold color={VIOLET_GRADIENT[step]}>
            {line}
          </Text>
        );
      })}
      <Text bold color={TAGLINE}>
        § Ninurta · God of War and the Hunt — Lord of the Bow
      </Text>
      <Text> </Text>
    </Box>
  );
}
