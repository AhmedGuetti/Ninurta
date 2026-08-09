// Load ASCII art assets — banner + bow art.
// Assets live at ninurta/assets/, two levels up from tui-node/.

import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ASSETS = join(__dirname, "..", "..", "assets");

const BANNER_PATH = join(ASSETS, "ninurta_banner.txt");
const BOW_PATH = join(ASSETS, "bow_art.txt");

export function loadBanner() {
  try {
    return readFileSync(BANNER_PATH, "utf-8");
  } catch {
    return "NINURTA";
  }
}

export function loadBowArt() {
  try {
    return readFileSync(BOW_PATH, "utf-8");
  } catch {
    return "";
  }
}
