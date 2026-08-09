// Minimal ambient types for the Ninurta TUI (npm couldn't install @types/node
// in this environment — see session notes). Only what the UI code touches.
declare const process: {
  env: Record<string, string | undefined>
  exit(code?: number): never
  on(event: string, cb: (...args: unknown[]) => void): unknown
  cwd(): string
  platform: string
  stdin: { isTTY?: boolean }
  stdout: { write(s: string): void; isTTY?: boolean }
  stderr: { write(s: string): void }
  argv: string[]
}

interface Buffer extends Uint8Array {
  toString(encoding?: string): string
}
declare const Buffer: {
  from(s: string): Buffer
}

interface ImportMeta {
  dirname?: string
}

declare module 'node:child_process' {
  interface ReadableStream {
    on(event: 'data', cb: (chunk: Buffer) => void): this
    on(event: 'line', cb: (line: string) => void): this
  }
  interface WritableStream {
    write(s: string): boolean
  }
  export interface ChildProcess {
    stdin?: WritableStream
    stdout?: ReadableStream
    stderr?: ReadableStream
    on(event: string, cb: (...args: any[]) => void): this
    killed: boolean
    pid?: number
    exitCode: number | null
    signalCode: string | null
  }
  export function spawn(cmd: string, args: string[], opts: unknown): ChildProcess
}
declare module 'node:events' {
  export class EventEmitter {
    on(event: string, cb: (...args: any[]) => void): this
    emit(event: string, ...args: unknown[]): boolean
    removeAllListeners(event?: string): this
  }
}
declare module 'node:readline' {
  export interface Interface {
    on(event: 'line', cb: (line: string) => void): this
  }
  export function createInterface(opts: { input: unknown }): Interface
}
declare module 'node:fs' {
  export function existsSync(p: string): boolean
}
declare module 'node:path' {
  export function resolve(...parts: string[]): string
}
