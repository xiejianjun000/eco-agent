/**
 * sm3.ts — SM3 cryptographic hash (GB/T 32905-2016 / GM/T 0004-2012)
 *
 * Pure TypeScript implementation with zero runtime dependencies.
 * Ported to back the eco-agent trace-audit chain (originally govmcp.crypto.sm).
 * Used to build the tamper-evident SM3 hash chain in eco-audit-chain.
 */

const IV = new Uint32Array([
  0x7380166f, 0x4914b2b9, 0x172442d7, 0xda8a0600,
  0xa96f30bc, 0x163138aa, 0xe38dee4d, 0xb0fb0e4e,
])

const T = new Uint32Array(64)
for (let j = 0; j < 16; j++) T[j] = 0x79cc4519
for (let j = 16; j < 64; j++) T[j] = 0x7a879d8a

function rotl(x: number, n: number): number {
  return ((x << n) | (x >>> (32 - n))) >>> 0
}

function p0(x: number): number {
  return (x ^ rotl(x, 9) ^ rotl(x, 17)) >>> 0
}

function p1(x: number): number {
  return (x ^ rotl(x, 15) ^ rotl(x, 23)) >>> 0
}

function ff(x: number, y: number, z: number, j: number): number {
  return j < 16 ? (x ^ y ^ z) : ((x & y) | (x & z) | (y & z)) >>> 0
}

function gg(x: number, y: number, z: number, j: number): number {
  return j < 16 ? (x ^ y ^ z) : ((x & y) | (~x & z)) >>> 0
}

/** Compress one 64-byte block into V (8 x 32-bit words). */
function cf(v: Uint32Array, block: Uint8Array, offset: number): Uint32Array {
  const w = new Uint32Array(68)
  const w1 = new Uint32Array(64)
  for (let i = 0; i < 16; i++) {
    const o = offset + i * 4
    w[i] = ((block[o] << 24) | (block[o + 1] << 16) | (block[o + 2] << 8) | block[o + 3]) >>> 0
  }
  for (let j = 16; j < 68; j++) {
    w[j] = (p1(w[j - 16] ^ w[j - 9] ^ rotl(w[j - 3], 15)) ^ rotl(w[j - 13], 7) ^ w[j - 6]) >>> 0
  }
  for (let j = 0; j < 64; j++) {
    w1[j] = (w[j] ^ w[j + 4]) >>> 0
  }

  let a = v[0], b = v[1], c = v[2], d = v[3]
  let e = v[4], f = v[5], g = v[6], h = v[7]

  for (let j = 0; j < 64; j++) {
    const ss1 = (rotl((rotl(a, 12) + e + rotl(T[j], j)) >>> 0, 7)) >>> 0
    const ss2 = (ss1 ^ rotl(a, 12)) >>> 0
    const tt1 = (ff(a, b, c, j) + d + ss2 + w1[j]) >>> 0
    const tt2 = (gg(e, f, g, j) + h + ss1 + w[j]) >>> 0
    d = c
    c = rotl(b, 9)
    b = a
    a = tt1
    h = g
    g = rotl(f, 19)
    f = e
    e = p0(tt2)
  }

  v[0] = (v[0] ^ a) >>> 0
  v[1] = (v[1] ^ b) >>> 0
  v[2] = (v[2] ^ c) >>> 0
  v[3] = (v[3] ^ d) >>> 0
  v[4] = (v[4] ^ e) >>> 0
  v[5] = (v[5] ^ f) >>> 0
  v[6] = (v[6] ^ g) >>> 0
  v[7] = (v[7] ^ h) >>> 0
  return v
}

/** Compute the SM3 digest of a byte array. */
export function sm3(message: Uint8Array): Uint8Array {
  const n = message.length
  // Padding: append 0x80, zeros, then 64-bit big-endian bit length.
  const withOne = n + 1
  const paddedLen = (((withOne + 8 + 63) >> 6) << 6) // multiple of 64
  const padded = new Uint8Array(paddedLen)
  padded.set(message)
  padded[n] = 0x80
  const bitLen = BigInt(n) * 8n
  // 64-bit length in big-endian at the end
  let pos = paddedLen - 8
  for (let i = 7; i >= 0; i--) {
    padded[pos + i] = Number((bitLen >> BigInt((7 - i) * 8)) & 0xffn)
  }

  const v = new Uint32Array(IV)
  for (let off = 0; off < paddedLen; off += 64) {
    cf(v, padded, off)
  }

  const out = new Uint8Array(32)
  for (let i = 0; i < 8; i++) {
    out[i * 4] = (v[i] >>> 24) & 0xff
    out[i * 4 + 1] = (v[i] >>> 16) & 0xff
    out[i * 4 + 2] = (v[i] >>> 8) & 0xff
    out[i * 4 + 3] = v[i] & 0xff
  }
  return out
}

/** Compute the hex SM3 digest of a string (UTF-8) or byte array. */
export function sm3Hex(data: Uint8Array | string): string {
  const bytes = typeof data === 'string' ? new TextEncoder().encode(data) : data
  const digest = sm3(bytes)
  return Array.from(digest, (b) => b.toString(16).padStart(2, '0')).join('')
}
