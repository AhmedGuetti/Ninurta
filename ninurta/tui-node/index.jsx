#!/usr/bin/env -S npx tsx
// Ninurta TUI — Ink-based transparent inline chat interface.
// Built following the Hermes Agent TUI patterns (ui-tui/src/entry.tsx).

import React, { useState } from "react";
import { render, Box, Text, useInput, useApp } from "ink";

import Banner from "./components/Banner.jsx";
import InfoBox from "./components/InfoBox.jsx";
import ChatArea from "./components/ChatArea.jsx";
import StatusBar from "./components/StatusBar.jsx";
import InputPrompt from "./components/InputPrompt.jsx";

// ── Startup ──────────────────────────────────────────────────────────────────
if (!process.stdin.isTTY) {
  console.log("ninurta-tui: no TTY (stdin is not a terminal)");
  process.exit(0);
}

// Let the terminal handle display naturally — no clear screen.

// ── Graceful exit ────────────────────────────────────────────────────────────
const cleanup = () => {
  // Reset terminal — nothing to reset yet, but placeholder for future mouse/raw mode cleanup
  process.stdout.write("\x1b[?25h"); // show cursor
};

process.on("exit", cleanup);

// ── Parse CLI args ───────────────────────────────────────────────────────────
const args = process.argv.slice(2);
const modelId = args[0] || "gemini-2.5-flash";
const cwd = args[1] || process.cwd();
const version = "0.1.0";

// ── App ──────────────────────────────────────────────────────────────────────
function App() {
  const { exit } = useApp();
  const [messages, setMessages] = useState([]);

  useInput((input, key) => {
    if (key.ctrl && (input === "c" || input === "d")) {
      exit();
    }
  });

  const handleSubmit = (text) => {
    const low = text.toLowerCase();
    if (["quit", "exit", "q", "/exit", "/quit"].includes(low)) {
      exit();
      return;
    }
    setMessages((prev) => [
      ...prev,
      { role: "you", text },
      { role: "ninurta", text: `You said \u2014 ${text}` },
    ]);
  };

  // JSX via tsx
  return (
    <Box flexDirection="column">
      <Banner />
      <InfoBox modelId={modelId} cwd={cwd} version={version} />
      <ChatArea messages={messages} />
      <StatusBar modelId={modelId} cwd={cwd} />
      <InputPrompt onSubmit={handleSubmit} />
    </Box>
  );
}

// ── Render (synchronous — event loop kept alive by stdin in raw mode) ───────
render(<App />, {
  exitOnCtrlC: false,
});
