#!/usr/bin/env python3
"""纯 Python SM3 国密哈希实现（GM/T 0004-2012）。

零第三方依赖，供 govmcp.crypto.audit 审计链与等保场景使用。
公开标准测试向量：
    sm3(b"abc")   == 66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0
    sm3(b"abcd" * 16) == debe9ff92275b8a138604889c18e5a4d6fdb70e5387e5765293dcba39c0c5732
"""

from __future__ import annotations

import struct

_IV = bytes.fromhex("7380166f4914b2b9172442d7da8a0600a96f30bc163138aae38dee4db0fb0e4e")


def _rotl(x: int, n: int) -> int:
    n %= 32
    return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF


def _ff(x: int, y: int, z: int, j: int) -> int:
    return (x ^ y ^ z) if j < 16 else ((x & y) | (x & z) | (y & z))


def _gg(x: int, y: int, z: int, j: int) -> int:
    return (x ^ y ^ z) if j < 16 else ((x & y) | (~x & z))


def _t(j: int) -> int:
    return 0x79CC4519 if j < 16 else 0x7A879D8A


def _p0(x: int) -> int:
    return x ^ _rotl(x, 9) ^ _rotl(x, 17)


def _p1(x: int) -> int:
    return x ^ _rotl(x, 15) ^ _rotl(x, 23)


def sm3(data: bytes) -> bytes:
    """计算 SM3 摘要，返回 32 字节。"""
    msg = bytearray(data)
    bit_len = len(msg) * 8
    msg.append(0x80)
    while len(msg) % 64 != 56:
        msg.append(0x00)
    msg += struct.pack(">Q", bit_len & 0xFFFFFFFFFFFFFFFF)

    v = list(struct.unpack(">8I", _IV))
    for off in range(0, len(msg), 64):
        block = msg[off : off + 64]
        w = list(struct.unpack(">16I", block)) + [0] * 52
        for j in range(16, 68):
            w[j] = _p1(w[j - 16] ^ w[j - 9] ^ _rotl(w[j - 3], 15)) ^ _rotl(w[j - 13], 7) ^ w[j - 6]
        w1 = [0] * 64
        for j in range(64):
            w1[j] = w[j] ^ w[j + 4]
        a, b, c, d, e, f, g, h = v
        for j in range(64):
            ss1 = _rotl((_rotl(a, 12) + e + _rotl(_t(j), j)) & 0xFFFFFFFF, 7)
            ss2 = ss1 ^ _rotl(a, 12)
            tt1 = (_ff(a, b, c, j) + d + ss2 + w1[j]) & 0xFFFFFFFF
            tt2 = (_gg(e, f, g, j) + h + ss1 + w[j]) & 0xFFFFFFFF
            d = c
            c = _rotl(b, 9)
            b = a
            a = tt1
            h = g
            g = _rotl(f, 19)
            f = e
            e = _p0(tt2)
        v = [(x ^ y) & 0xFFFFFFFF for x, y in zip(v, (a, b, c, d, e, f, g, h))]
    return struct.pack(">8I", *v)


def sm3_hex(data: bytes) -> str:
    return sm3(data).hex()
