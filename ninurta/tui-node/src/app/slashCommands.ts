// Ninurta slash command registry — single source of truth for the TUI.
// Both the InputPrompt completion dropdown and the InfoBox Commands help
// render from this list, so a new command surfaces everywhere automatically.

export interface SlashCommand {
  /** Full invocation shown in the dropdown and help, e.g. '/db resume <id>'. */
  usage: string
  /** One-line description shown next to the command. */
  description: string
}

export interface SlashCompletion {
  /** Text to insert on accept (leading slash + command, trailing space). */
  text: string
  /** Label shown in the dropdown (the usage string). */
  display: string
  /** Description shown in muted text. */
  meta: string
}

export const SLASH_COMMANDS: SlashCommand[] = [
  { usage: '/model', description: 'interactive picker → choose provider + model' },
  { usage: '/db', description: 'db summary (tables + counts)' },
  { usage: '/db resumes', description: 'list all resumes by id' },
  { usage: '/db jobs', description: 'list all jobs (latest first)' },
  { usage: '/db reports', description: 'list all match reports (score history)' },
  { usage: '/db resume <id>', description: 'show resume detail' },
  { usage: '/db job <id>', description: 'show job detail' },
  { usage: '/db report <id>', description: 'show structured report (job × resume × score)' },
  { usage: '/clear', description: 'reset transcript' },
  { usage: '/exit', description: 'quit the TUI' },
  { usage: '/quit', description: 'quit the TUI' },
]

/**
 * Commands whose usage starts with the typed input (prefix match,
 * case-insensitive). '/' alone lists every command; '/db ' narrows to the
 * db sub-commands — the dropdown stays live as the user types.
 */
export function completeSlash(input: string): SlashCompletion[] {
  if (!input.startsWith('/')) return []
  const lower = input.toLowerCase()

  return SLASH_COMMANDS.filter((c) => c.usage.toLowerCase().startsWith(lower)).map((c) => ({
    // Strip <placeholders> from the inserted text so completing '/db resume <id>'
    // yields '/db resume ' — the user just types the id. Trailing space keeps the
    // dropdown open for arg-bearing commands ('/db ' → subcommand options).
    text: c.usage.replace(/<[^>]*>/g, '').trimEnd() + ' ',
    display: c.usage,
    meta: c.description,
  }))
}

/**
 * Replace from `compReplace` with the completion row, mirroring editor
 * replace semantics. The row text's leading slash is dropped when the input
 * already has one immediately before the replace point (the user typed '/',
 * so only the command name part is swapped in).
 */
export function applyCompletion(value: string, rowText: string, compReplace: number): string {
  const text = value[compReplace - 1] === '/' && rowText.startsWith('/') ? rowText.slice(1) : rowText

  return value.slice(0, compReplace) + text
}
