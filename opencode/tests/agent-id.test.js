/**
 * RED tests for SPEC-F005 — `X-Agent-ID` authorship (plugin side).
 *
 * Run: node --test opencode/tests/agent-id.test.js
 *
 * The plugin must send a stable identity on every REST call it makes (search,
 * store, delete, harvest, health), resolving it from
 * `OPENCODE_MEMORY_AGENT_ID` → `memoryService.agentId` → `opencode`, and
 * rejecting malformed values after trimming.
 *
 * These tests are RED on the current implementation: there is no
 * `resolveAgentId`, no `loadConfig` seam, and `buildHeaders()` sends no
 * `X-Agent-ID`. No HTTP boundary is mocked: the header capture uses a real
 * `http.createServer` on an ephemeral port.
 */

import { test } from "node:test"
import assert from "node:assert"
import http from "node:http"
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"

import { _internal } from "../memory-plugin.js"

const { buildHeaders, loadConfig, requestJson, resolveAgentId } = _internal
const PLUGIN_URL = new URL("../memory-plugin.js", import.meta.url).href

const DEFAULT_AGENT = "opencode"

// --- helpers -----------------------------------------------------------------

function configFor(agentId, endpoint = "http://127.0.0.1:1") {
  return {
    memoryService: {
      endpoint,
      apiKey: "",
      timeoutMs: 5000,
      loadTimeoutMs: 2500,
      maxMemoriesPerSession: 8,
      searchTags: [],
      includeProjectTag: false,
      allowSelfSignedCerts: false,
      projectQueries: [],
      agentId,
    },
  }
}

/** Run `body` with the given environment variables set (undefined deletes). */
async function withEnv(values, body) {
  const previous = new Map()
  for (const [name, value] of Object.entries(values)) {
    previous.set(name, process.env[name])
    if (value === undefined) delete process.env[name]
    else process.env[name] = value
  }
  try {
    return await body()
  } finally {
    for (const [name, value] of previous) {
      if (value === undefined) delete process.env[name]
      else process.env[name] = value
    }
  }
}

function captureWarnings(body) {
  const original = console.warn
  const warnings = []
  console.warn = (...args) => warnings.push(args.join(" "))
  try {
    body()
  } finally {
    console.warn = original
  }
  return warnings
}

function startServer() {
  const requests = []
  const server = http.createServer((request, response) => {
    let body = ""
    request.on("data", (chunk) => { body += chunk })
    request.on("end", () => {
      requests.push({ url: request.url, method: request.method, headers: request.headers })
      response.setHeader("Content-Type", "application/json")
      response.statusCode = 200
      response.end(JSON.stringify({ ok: true, content_hash: "hash-1", status: "healthy" }))
    })
  })

  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      resolve({ server, requests, endpoint: `http://127.0.0.1:${server.address().port}` })
    })
  })
}

async function stopServer(server) {
  await new Promise((resolve) => server.close(resolve))
}

// --- 1. resolveAgentId: config → env → default (R5, R7) ----------------------

test("a config without agentId resolves to opencode", async () => {
  await withEnv({ OPENCODE_MEMORY_AGENT_ID: undefined }, () => {
    assert.strictEqual(resolveAgentId(configFor(undefined)), DEFAULT_AGENT)
  })
})

test("memoryService.agentId is used when the environment says nothing", async () => {
  await withEnv({ OPENCODE_MEMORY_AGENT_ID: undefined }, () => {
    assert.strictEqual(resolveAgentId(configFor("file-box")), "file-box")
  })
})

test("OPENCODE_MEMORY_AGENT_ID wins over the config file", async () => {
  await withEnv({ OPENCODE_MEMORY_AGENT_ID: "env-box" }, () => {
    assert.strictEqual(resolveAgentId(configFor("file-box")), "env-box")
  })
})

test("the resolved identity is trimmed", async () => {
  await withEnv({ OPENCODE_MEMORY_AGENT_ID: undefined }, () => {
    assert.strictEqual(resolveAgentId(configFor("  research-box  ")), "research-box")
  })
})

// --- 2. resolveAgentId: invalid values (R8) ----------------------------------

for (const [label, value] of [
  ["empty", ""],
  ["65 characters", "a".repeat(65)],
  ["a control character", "research\nbox"],
]) {
  test(`${label} falls back to opencode`, async () => {
    await withEnv({ OPENCODE_MEMORY_AGENT_ID: undefined }, () => {
      assert.strictEqual(resolveAgentId(configFor(value)), DEFAULT_AGENT)
    })
  })
}

test("the same invalid identity warns exactly once", async () => {
  await withEnv({ OPENCODE_MEMORY_AGENT_ID: undefined }, () => {
    // Unique to this test: warning dedupe is per value, so reusing a value
    // another test already resolved would observe zero warnings.
    const config = configFor("warn-once\n" + "x".repeat(50))
    const warnings = captureWarnings(() => {
      resolveAgentId(config)
      resolveAgentId(config)
      resolveAgentId(config)
    })
    assert.strictEqual(warnings.length, 1, `expected a single warning, got ${JSON.stringify(warnings)}`)
    assert.match(warnings[0], /agent/i)
  })
})

// --- 3. buildHeaders (R4) ----------------------------------------------------

test("buildHeaders adds X-Agent-ID and keeps the API key and extra headers", () => {
  const config = configFor("file-box")
  config.memoryService.apiKey = "secret-key"

  const headers = buildHeaders(config, { "Content-Type": "application/json" })

  assert.strictEqual(headers["X-Agent-ID"], "file-box")
  assert.strictEqual(headers["X-API-Key"], "secret-key")
  assert.strictEqual(headers.Accept, "application/json")
  assert.strictEqual(headers["Content-Type"], "application/json")
})

test("buildHeaders sends no X-API-Key when none is configured", () => {
  const headers = buildHeaders(configFor("file-box"))

  assert.strictEqual(headers["X-Agent-ID"], "file-box")
  assert.strictEqual(headers["X-API-Key"], undefined)
})

// --- 4. every REST call carries the header (R4, AC4) -------------------------

test("requestJson sends X-Agent-ID on search, store, delete, harvest and health", async () => {
  const { server, requests, endpoint } = await startServer()
  try {
    const config = configFor("server-box", endpoint)
    const json = { "Content-Type": "application/json" }

    await requestJson(config, "/api/search", {
      method: "POST",
      headers: json,
      body: JSON.stringify({ query: "architecture", n_results: 3 }),
    })
    await requestJson(config, "/api/memories", {
      method: "POST",
      headers: json,
      body: JSON.stringify({ content: "a memory", tags: ["auto-capture"] }),
    })
    await requestJson(config, "/api/memories/hash-1", { method: "DELETE" })
    await requestJson(config, "/api/harvest", {
      method: "POST",
      headers: json,
      body: JSON.stringify({ sessions: 1, dry_run: true }),
    })
    await requestJson(config, "/api/health", { method: "GET" })

    assert.deepStrictEqual(
      requests.map((entry) => entry.url),
      ["/api/search", "/api/memories", "/api/memories/hash-1", "/api/harvest", "/api/health"],
    )
    for (const entry of requests) {
      assert.strictEqual(
        entry.headers["x-agent-id"],
        "server-box",
        `${entry.method} ${entry.url} was sent without X-Agent-ID: ${JSON.stringify(entry.headers)}`,
      )
    }
  } finally {
    await stopServer(server)
  }
})

// --- 5. loadConfig (R5, R7) --------------------------------------------------

test("loadConfig resolves the identity from file, then env, then default", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "opencode-agent-id-"))
  const home = path.join(root, "home")
  const configPath = path.join(root, "memory-plugin.json")
  await mkdir(home, { recursive: true })
  await writeFile(
    configPath,
    JSON.stringify({ memoryService: { endpoint: "http://127.0.0.1:1", agentId: "file-box" } }),
  )

  try {
    await withEnv({
      HOME: home,
      XDG_CONFIG_HOME: path.join(root, "config"),
      XDG_STATE_HOME: path.join(root, "state"),
      XDG_DATA_HOME: path.join(root, "data"),
      OPENCODE_MEMORY_PLUGIN_CONFIG: configPath,
      OPENCODE_MEMORY_AGENT_ID: undefined,
      OPENCODE_MEMORY_INBOX_AGENT_ID: undefined,
      OPENCODE_MEMORY_ENDPOINT: undefined,
      OPENCODE_MEMORY_URL: undefined,
      OPENCODE_MEMORY_API_KEY: undefined,
    }, async () => {
      // Fresh module instance so the XDG paths above are the ones it sees.
      const fresh = await import(`${PLUGIN_URL}?f005=${Date.now()}`)
      const freshLoadConfig = fresh._internal.loadConfig
      assert.strictEqual(typeof freshLoadConfig, "function", "loadConfig is not exposed under _internal")

      const fromFile = await freshLoadConfig(path.join(root, "project"))
      assert.strictEqual(fromFile.memoryService.agentId, "file-box")

      process.env.OPENCODE_MEMORY_AGENT_ID = "env-box"
      const fromEnv = await freshLoadConfig(path.join(root, "project"))
      assert.strictEqual(fromEnv.memoryService.agentId, "env-box")

      delete process.env.OPENCODE_MEMORY_AGENT_ID
      await rm(configPath, { force: true })
      const fromDefault = await freshLoadConfig(path.join(root, "project"))
      assert.strictEqual(fromDefault.memoryService.agentId, DEFAULT_AGENT)
    })
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test("loadConfig keeps the statically imported seam usable", async () => {
  assert.strictEqual(typeof loadConfig, "function", "loadConfig is not exposed under _internal")
})
