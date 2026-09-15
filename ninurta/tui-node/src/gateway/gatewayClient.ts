// Ninurta GatewayClient — mirrors hermes-agent ui-tui/src/gatewayClient.ts
// stdio JSON-RPC bridge to the Python gateway (ninurta.gateway.entry).
import { type ChildProcess, spawn } from 'node:child_process'
import { EventEmitter } from 'node:events'
import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { createInterface } from 'node:readline'

const MAX_STDERR_LINES = 200
const STARTUP_TIMEOUT_MS = 15_000

/** Gateway push events (method field with no id) — Ninurta's own event set. */
export type NinurtaGatewayEvent =
  | { method: 'turn.delta'; params: { text?: string } }
  | { method: 'turn.end'; params: { text?: string; error?: string } }
  | { method: 'pipeline.progress'; params: { step: string; message?: string } }

interface PendingRequest {
  resolve: (value: unknown) => void
  reject: (reason: Error) => void
  timer: ReturnType<typeof setTimeout>
}

export class GatewayClient extends EventEmitter {
  private child: ChildProcess | null = null
  private pending = new Map<number, PendingRequest>()
  private nextId = 1
  private readyResolve: (() => void) | null = null
  private ready = new Promise<void>((res) => {
    this.readyResolve = res
  })

  /** Rolling 200-line stderr ring buffer (hermes: MAX_GATEWAY_LOG_LINES). */
  readonly stderrLog: string[] = []

  start(): void {
    const root = resolve(typeof import.meta.dirname === 'string' ? import.meta.dirname : '.', '../../../..')
    const python = this.resolvePython(root)

    this.child = spawn(python, ['-m', 'ninurta.gateway.entry'], {
      stdio: ['pipe', 'pipe', 'pipe'],
      cwd: root,
      env: {
        ...process.env,
        PYTHONPATH: [root, process.env.PYTHONPATH ?? ''].filter(Boolean).join(':'),
        PYTHONUNBUFFERED: '1'
      }
    })

    // Stderr ring buffer — never pollutes the terminal.
    this.child.stderr?.on('data', (chunk: Buffer) => {
      for (const line of chunk.toString().split('\n')) {
        const trimmed = line.trim()
        if (!trimmed) continue
        this.stderrLog.push(trimmed)
        if (this.stderrLog.length > MAX_STDERR_LINES) this.stderrLog.shift()
        this.emit('log', trimmed)
      }
    })

    // stdout — JSON-RPC frames: responses (id) and push events (method).
    if (this.child.stdout) {
      const rl = createInterface({ input: this.child.stdout })
      rl.on('line', (line) => this.onFrame(line))
    }

    this.child.on('close', (code) => {
      this.stderrLog.push(`gateway exited code=${code}`)
      this.emit('close', code)
    })
  }

  /** Wait for the gateway to boot (first frame received). */
  async waitReady(): Promise<void> {
    const timeout = new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error('gateway startup timeout')), STARTUP_TIMEOUT_MS)
    )
    await Promise.race([this.ready, timeout])
  }

  request<T = unknown>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      const id = this.nextId++
      const timer = setTimeout(() => {
        this.pending.delete(id)
        reject(new Error(`request timed out: ${method}`))
      }, 120_000)
      this.pending.set(id, { resolve: resolve as (v: unknown) => void, reject, timer })
      this.child?.stdin?.write(JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n')
    })
  }

  private onFrame(line: string): void {
    if (this.readyResolve) {
      this.readyResolve()
      this.readyResolve = null
    }
    let msg: { id?: number; method?: string; params?: unknown; result?: unknown; error?: unknown }
    try {
      msg = JSON.parse(line)
    } catch {
      this.stderrLog.push(`non-JSON frame: ${line.slice(0, 120)}`)
      return
    }
    if (msg.id !== undefined) {
      const pending = this.pending.get(msg.id)
      if (!pending) return
      this.pending.delete(msg.id)
      clearTimeout(pending.timer)
      if (msg.error) pending.reject(new Error(String(msg.error)))
      else pending.resolve(msg.result)
    } else if (msg.method) {
      this.emit(msg.method, msg.params ?? {})
    }
  }

  private resolvePython(root: string): string {
    const venv = process.env.VIRTUAL_ENV
    const candidates = [
      venv && resolve(venv, 'bin/python'),
      resolve(root, '.venv/bin/python'),
      resolve(root, '.venv/bin/python3'),
      resolve(root, 'venv/bin/python'),
      resolve(root, 'venv/bin/python3')
    ].filter((p): p is string => !!p && existsSync(p))
    return candidates[0] ?? (process.platform === 'win32' ? 'python' : 'python3')
  }
}
