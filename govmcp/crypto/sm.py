"""
govmcp 国密加密模块 — SM3哈希 + SM4对称加密

SM3: 中国国家密码管理局发布的密码杂凑算法 (GB/T 32905-2016)
     输出256位哈希值，强度等同于SHA-256

SM4: 中国国家密码管理局发布的对称加密算法 (GB/T 32907-2016)
     128位分组密码，密钥长度128位

生产环境应使用硬件加密模块（HSM）或国密专用芯片。
本模块提供纯软件参考实现，用于开发与测试。
"""

import os

# ====== SM3 哈希 ======
# SM3 初始值 IV
SM3_IV = [
    0x7380166F,
    0x4914B2B9,
    0x172442D7,
    0xDA8A0600,
    0xA96F30BC,
    0x163138AA,
    0xE38DEE4D,
    0xB0FB0E4E,
]


# SM3 常量 T
def _sm3_t(j: int) -> int:
    return 0x79CC4519 if 0 <= j <= 15 else 0x7A879D8A


def _sm3_rotate_left(x: int, n: int) -> int:
    return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF


def _sm3_ff0(x: int, y: int, z: int) -> int:
    return x ^ y ^ z


def _sm3_ff1(x: int, y: int, z: int) -> int:
    return (x & y) | (x & z) | (y & z)


def _sm3_gg0(x: int, y: int, z: int) -> int:
    return x ^ y ^ z


def _sm3_gg1(x: int, y: int, z: int) -> int:
    return (x & y) | ((~x) & z)


def _sm3_p0(x: int) -> int:
    return x ^ _sm3_rotate_left(x, 9) ^ _sm3_rotate_left(x, 17)


def _sm3_p1(x: int) -> int:
    return x ^ _sm3_rotate_left(x, 15) ^ _sm3_rotate_left(x, 23)


def sm3_hash(data: bytes) -> str:
    """
    SM3 国密哈希

    Args:
        data: 待哈希数据

    Returns:
        64字符十六进制哈希值

    Example:
        >>> sm3_hash(b"hello")
        'becbbfaae6548b8bf0cfcad5a27183cd1be6093b...'
    """
    # 填充
    msg_len = len(data) * 8
    data = data + b"\x80"
    while (len(data) * 8) % 512 != 448:
        data += b"\x00"
    data += msg_len.to_bytes(8, "big")

    # 分组处理
    V = list(SM3_IV)
    for i in range(0, len(data), 64):
        block = data[i : i + 64]
        W = []
        for j in range(16):
            W.append(int.from_bytes(block[j * 4 : (j + 1) * 4], "big"))
        for j in range(16, 68):
            W.append(_sm3_p1(W[j - 16] ^ W[j - 9] ^ _sm3_rotate_left(W[j - 3], 15)) ^ _sm3_rotate_left(W[j - 13], 7) ^ W[j - 6])

        W1 = [W[j] ^ W[j + 4] for j in range(64)]

        A, B, C, D, E, F, G, H = V
        for j in range(64):
            if j <= 15:
                SS1 = _sm3_rotate_left(
                    (_sm3_rotate_left(A, 12) + E + _sm3_rotate_left(_sm3_t(j), j % 32)) & 0xFFFFFFFF,
                    7,
                )
                SS2 = SS1 ^ _sm3_rotate_left(A, 12)
                TT1 = (_sm3_ff0(A, B, C) + D + SS2 + W1[j]) & 0xFFFFFFFF
                TT2 = (_sm3_gg0(E, F, G) + H + SS1 + W[j]) & 0xFFFFFFFF
            else:
                SS1 = _sm3_rotate_left(
                    (_sm3_rotate_left(A, 12) + E + _sm3_rotate_left(_sm3_t(j), j % 32)) & 0xFFFFFFFF,
                    7,
                )
                SS2 = SS1 ^ _sm3_rotate_left(A, 12)
                TT1 = (_sm3_ff1(A, B, C) + D + SS2 + W1[j]) & 0xFFFFFFFF
                TT2 = (_sm3_gg1(E, F, G) + H + SS1 + W[j]) & 0xFFFFFFFF

            D, C, B, A = C, _sm3_rotate_left(B, 9), A, TT1
            H, G, F, E = G, _sm3_rotate_left(F, 19), E, _sm3_p0(TT2)

        V = [(V[i] ^ x) & 0xFFFFFFFF for i, x in enumerate([A, B, C, D, E, F, G, H])]

    return "".join(f"{x:08x}" for x in V)


# ====== SM4 对称加密 ======
# SM4 S-Box
SM4_SBOX = [
    0xD6,
    0x90,
    0xE9,
    0xFE,
    0xCC,
    0xE1,
    0x3D,
    0xB7,
    0x16,
    0xB6,
    0x14,
    0xC2,
    0x28,
    0xFB,
    0x2C,
    0x05,
    0x2B,
    0x67,
    0x9A,
    0x76,
    0x2A,
    0xBE,
    0x04,
    0xC3,
    0xAA,
    0x44,
    0x13,
    0x26,
    0x49,
    0x86,
    0x06,
    0x99,
    0x9C,
    0x42,
    0x50,
    0xF4,
    0x91,
    0xEF,
    0x98,
    0x7A,
    0x33,
    0x54,
    0x0B,
    0x43,
    0xED,
    0xCF,
    0xAC,
    0x62,
    0xE4,
    0xB3,
    0x1C,
    0xA9,
    0xC9,
    0x08,
    0xE8,
    0x95,
    0x80,
    0xDF,
    0x94,
    0xFA,
    0x75,
    0x8F,
    0x3F,
    0xA6,
    0x47,
    0x07,
    0xA7,
    0xFC,
    0xF3,
    0x73,
    0x17,
    0xBA,
    0x83,
    0x59,
    0x3C,
    0x19,
    0xE6,
    0x85,
    0x4F,
    0xA8,
    0x68,
    0x6B,
    0x81,
    0xB2,
    0x71,
    0x64,
    0xDA,
    0x8B,
    0xF8,
    0xEB,
    0x0F,
    0x4B,
    0x70,
    0x56,
    0x9D,
    0x35,
    0x1E,
    0x24,
    0x0E,
    0x5E,
    0x63,
    0x58,
    0xD1,
    0xA2,
    0x25,
    0x22,
    0x7C,
    0x3B,
    0x01,
    0x21,
    0x78,
    0x87,
    0xD4,
    0x00,
    0x46,
    0x57,
    0x9F,
    0xD3,
    0x27,
    0x52,
    0x4C,
    0x36,
    0x02,
    0xE7,
    0xA0,
    0xC4,
    0xC8,
    0x9E,
    0xEA,
    0xBF,
    0x8A,
    0xD2,
    0x40,
    0xC7,
    0x38,
    0xB5,
    0xA3,
    0xF7,
    0xF2,
    0xCE,
    0xF9,
    0x61,
    0x15,
    0xA1,
    0xE0,
    0xAE,
    0x5D,
    0xA4,
    0x9B,
    0x34,
    0x1A,
    0x55,
    0xAD,
    0x93,
    0x32,
    0x30,
    0xF5,
    0x8C,
    0xB1,
    0xE3,
    0x1D,
    0xF6,
    0xE2,
    0x2E,
    0x82,
    0x66,
    0xCA,
    0x60,
    0xC0,
    0x29,
    0x23,
    0xAB,
    0x0D,
    0x53,
    0x4E,
    0x6F,
    0xD5,
    0xDB,
    0x37,
    0x45,
    0xDE,
    0xFD,
    0x8E,
    0x2F,
    0x03,
    0xFF,
    0x6A,
    0x72,
    0x6D,
    0x6C,
    0x5B,
    0x51,
    0x8D,
    0x1B,
    0xAF,
    0x92,
    0xBB,
    0xDD,
    0xBC,
    0x7F,
    0x11,
    0xD9,
    0x5C,
    0x41,
    0x1F,
    0x10,
    0x5A,
    0xD8,
    0x0A,
    0xC1,
    0x31,
    0x88,
    0xA5,
    0xCD,
    0x7B,
    0xBD,
    0x2D,
    0x74,
    0xD0,
    0x12,
    0xB8,
    0xE5,
    0xB4,
    0xB0,
    0x89,
    0x69,
    0x97,
    0x4A,
    0x0C,
    0x96,
    0x77,
    0x7E,
    0x65,
    0xB9,
    0xF1,
    0x09,
    0xC5,
    0x6E,
    0xC6,
    0x84,
    0x18,
    0xF0,
    0x7D,
    0xEC,
    0x3A,
    0xDC,
    0x4D,
    0x20,
    0x79,
    0xEE,
    0x5F,
    0x3E,
    0xD7,
    0xCB,
    0x39,
    0x48,
]

SM4_FK = [0xA3B1BAC6, 0x56AA3350, 0x677D9197, 0xB27022DC]
SM4_CK = [
    0x00070E15,
    0x1C232A31,
    0x383F464D,
    0x545B6269,
    0x70777E85,
    0x8C939AA1,
    0xA8AFB6BD,
    0xC4CBD2D9,
    0xE0E7EEF5,
    0xFC030A11,
    0x181F262D,
    0x343B4249,
    0x50575E65,
    0x6C737A81,
    0x888F969D,
    0xA4ABB2B9,
    0xC0C7CED5,
    0xDCE3EAF1,
    0xF8FF060D,
    0x141B2229,
    0x30373E45,
    0x4C535A61,
    0x686F767D,
    0x848B9299,
    0xA0A7AEB5,
    0xBCC3CAD1,
    0xD8DFE6ED,
    0xF4FB0209,
    0x10171E25,
    0x2C333A41,
    0x484F565D,
    0x646B7279,
]


def _sm4_tau(a: int) -> int:
    return (
        SM4_SBOX[(a >> 24) & 0xFF] << 24
        | SM4_SBOX[(a >> 16) & 0xFF] << 16
        | SM4_SBOX[(a >> 8) & 0xFF] << 8
        | SM4_SBOX[a & 0xFF]
    )


def _sm4_l(b: int) -> int:
    return b ^ _sm3_rotate_left(b, 2) ^ _sm3_rotate_left(b, 10) ^ _sm3_rotate_left(b, 18) ^ _sm3_rotate_left(b, 24)


def _sm4_l_prime(b: int) -> int:
    return b ^ _sm3_rotate_left(b, 13) ^ _sm3_rotate_left(b, 23)


def _sm4_t(x: int) -> int:
    return _sm4_l(_sm4_tau(x))


def _sm4_t_prime(x: int) -> int:
    return _sm4_l_prime(_sm4_tau(x))


def sm4_encrypt(plaintext: bytes, key: bytes, use_pkcs7: bool = True) -> bytes:
    """
    SM4 国密对称加密 (ECB模式)

    【PKCS7填充边界】
    - 输入: 任意长度的明文
    - 输出: 16字节倍数长度的密文
    - 填充责任: 本函数负责。如果 use_pkcs7=True 且明文长度不是16的倍数，
               本函数内部调用 pkcs7_pad() 进行填充。
               如果 use_pkcs7=False，则要求明文必须是16的倍数。

    Args:
        plaintext: 明文数据（任意长度）
        key: 128位密钥 (16字节)
        use_pkcs7: 是否使用PKCS7填充（默认True，自动填充）
                   - True: 自动填充，不要求输入是16的倍数
                   - False: 不填充，要求输入必须是16的倍数

    Returns:
        密文（长度是16的倍数）

    Raises:
        ValueError: 密钥长度不是16字节
        ValueError: use_pkcs7=False时，明文长度不是16的倍数

    Example:
        # 自动填充（推荐）
        ct = sm4_encrypt(b"Hello", key)  # 自动填充到16字节
        pt = sm4_decrypt(ct, key)       # 自动去填充

        # 手动填充
        padded = pkcs7_pad(b"Hello", 16)
        ct = sm4_encrypt(padded, key, use_pkcs7=False)
        pt = sm4_decrypt(ct, key, use_pkcs7=False)
        pt = pkcs7_unpad(pt, 16)
    """
    if len(key) != 16:
        raise ValueError(f"SM4密钥必须为16字节(128位)，当前: {len(key)}")

    if use_pkcs7:
        plaintext = pkcs7_pad(plaintext, 16)
    elif len(plaintext) % 16 != 0:
        raise ValueError(f"SM4明文长度必须为16的倍数，当前: {len(plaintext)}")

    # 密钥扩展
    MK = [int.from_bytes(key[i : i + 4], "big") for i in range(0, 16, 4)]
    K = [MK[i] ^ SM4_FK[i] for i in range(4)]
    rk = []
    for i in range(32):
        K.append(K[i] ^ _sm4_t_prime(K[i + 1] ^ K[i + 2] ^ K[i + 3] ^ SM4_CK[i]))
        rk.append(K[-1])

    # 加密
    result = b""
    for block_idx in range(0, len(plaintext), 16):
        X = [int.from_bytes(plaintext[block_idx + i : block_idx + i + 4], "big") for i in range(0, 16, 4)]
        for i in range(32):
            X.append(X[i] ^ _sm4_t(X[i + 1] ^ X[i + 2] ^ X[i + 3] ^ rk[i]))
        result += b"".join(x.to_bytes(4, "big") for x in reversed(X[-4:]))

    return result


def sm4_decrypt(ciphertext: bytes, key: bytes, use_pkcs7: bool = True) -> bytes:
    """
    SM4 国密对称解密 (ECB模式)

    【PKCS7填充边界】
    - 输入: 16字节倍数长度的密文
    - 输出: 明文
    - 去填充责任: 本函数负责。如果 use_pkcs7=True，
               本函数内部调用 pkcs7_unpad() 进行去填充。

    Args:
        ciphertext: 密文（必须是16的倍数）
        key: 128位密钥 (16字节)
        use_pkcs7: 是否使用PKCS7去填充（默认True）
                   - True: 自动去填充
                   - False: 不去填充，返回原始数据

    Returns:
        明文

    Raises:
        ValueError: 密钥长度不是16字节
        ValueError: 密文长度不是16的倍数

    Example:
        ct = sm4_encrypt(b"Hello", key)
        pt = sm4_decrypt(ct, key)  # 自动去填充
    """
    if len(key) != 16:
        raise ValueError(f"SM4密钥必须为16字节(128位)，当前: {len(key)}")
    if len(ciphertext) % 16 != 0:
        raise ValueError(f"SM4密文长度必须为16的倍数，当前: {len(ciphertext)}")

    # 密钥扩展（同加密）
    MK = [int.from_bytes(key[i : i + 4], "big") for i in range(0, 16, 4)]
    K = [MK[i] ^ SM4_FK[i] for i in range(4)]
    rk = []
    for i in range(32):
        K.append(K[i] ^ _sm4_t_prime(K[i + 1] ^ K[i + 2] ^ K[i + 3] ^ SM4_CK[i]))
        rk.append(K[-1])

    # 解密（轮密钥逆序）
    rk.reverse()
    result = b""
    for block_idx in range(0, len(ciphertext), 16):
        X = [int.from_bytes(ciphertext[block_idx + i : block_idx + i + 4], "big") for i in range(0, 16, 4)]
        for i in range(32):
            X.append(X[i] ^ _sm4_t(X[i + 1] ^ X[i + 2] ^ X[i + 3] ^ rk[i]))
        result += b"".join(x.to_bytes(4, "big") for x in reversed(X[-4:]))

    if use_pkcs7:
        result = pkcs7_unpad(result, 16)
    return result


def pkcs7_pad(data: bytes, block_size: int = 16) -> bytes:
    """
    PKCS7 填充

    【职责】纯填充函数，不涉及加密解密

    Args:
        data: 待填充数据（任意长度）
        block_size: 块大小，默认16字节

    Returns:
        填充后的数据（长度是block_size的倍数）

    Note:
        - 填充长度 = block_size - (len(data) % block_size)
        - 如果 data 正好是 block_size 的倍数，则添加一整个 block_size 的填充
          （这是PKCS7标准要求，与PKCS5不同）
        - 填充字节值 = 填充长度
    """
    pad_len = block_size - (len(data) % block_size)
    if pad_len == 0:
        pad_len = block_size
    return data + bytes([pad_len] * pad_len)


def pkcs7_unpad(data: bytes, block_size: int = 16) -> bytes:
    """
    PKCS7 去填充

    【职责】纯去填充函数，不涉及加密解密

    Args:
        data: 填充后的数据（必须是block_size的倍数）
        block_size: 块大小，默认16字节

    Returns:
        去填充后的数据

    Raises:
        ValueError: 数据长度为0
        ValueError: 数据长度不是block_size的倍数
        ValueError: 填充长度无效（为0或大于block_size）
        ValueError: 填充内容不匹配

    Note:
        - 读取最后一个字节作为填充长度
        - 验证填充长度和填充内容
        - 返回原始数据（不包含填充）
    """
    if len(data) == 0 or len(data) % block_size != 0:
        raise ValueError("数据长度无效")

    pad_len = data[-1]
    if pad_len == 0 or pad_len > block_size:
        raise ValueError("填充长度无效")

    if any(b != pad_len for b in data[-pad_len:]):
        raise ValueError("填充内容无效")

    return data[:-pad_len]


def generate_sm4_iv() -> bytes:
    """生成随机SM4 IV（初始化向量）"""
    return os.urandom(16)


def sm4_cbc_encrypt(plaintext: bytes, key: bytes, iv: bytes) -> bytes:
    """
    SM4-CBC 国密对称加密

    【PKCS7填充边界】
    - 输入: 任意长度的明文
    - 输出: 16字节倍数长度的密文
    - 填充责任: 本函数负责。内部调用 pkcs7_pad() 进行填充。
      调用 sm4_encrypt() 时使用 use_pkcs7=False，避免双重填充。

    Args:
        plaintext: 明文数据（任意长度）
        key: 128位密钥 (16字节)
        iv: 初始化向量 (16字节)

    Returns:
        密文（长度是16的倍数）

    Raises:
        ValueError: 密钥长度不是16字节
        ValueError: IV长度不是16字节

    Example:
        ct = sm4_cbc_encrypt(b"Hello", key, iv)
        pt = sm4_cbc_decrypt(ct, key, iv)
    """
    if len(key) != 16:
        raise ValueError(f"SM4密钥必须为16字节(128位)，当前: {len(key)}")
    if len(iv) != 16:
        raise ValueError(f"SM4 IV必须为16字节，当前: {len(iv)}")

    padded = pkcs7_pad(plaintext, 16)
    prev_block = iv

    result = b""
    for block_idx in range(0, len(padded), 16):
        block = bytearray(padded[block_idx : block_idx + 16])
        for i in range(16):
            block[i] ^= prev_block[i]

        encrypted = sm4_encrypt(bytes(block), key, use_pkcs7=False)
        result += encrypted
        prev_block = encrypted

    return result


def sm4_cbc_decrypt(ciphertext: bytes, key: bytes, iv: bytes) -> bytes:
    """
    SM4-CBC 国密对称解密

    【PKCS7填充边界】
    - 输入: 16字节倍数长度的密文
    - 输出: 明文
    - 去填充责任: 本函数负责。内部调用 sm4_decrypt(use_pkcs7=False)，
      解密后整体进行 pkcs7_unpad() 去填充。

    Args:
        ciphertext: 密文（必须是16的倍数）
        key: 128位密钥 (16字节)
        iv: 初始化向量 (16字节)

    Returns:
        明文

    Raises:
        ValueError: 密钥长度不是16字节
        ValueError: IV长度不是16字节
        ValueError: 密文长度不是16的倍数

    Example:
        ct = sm4_cbc_encrypt(b"Hello", key, iv)
        pt = sm4_cbc_decrypt(ct, key, iv)
    """
    if len(key) != 16:
        raise ValueError(f"SM4密钥必须为16字节(128位)，当前: {len(key)}")
    if len(iv) != 16:
        raise ValueError(f"SM4 IV必须为16字节，当前: {len(iv)}")
    if len(ciphertext) == 0 or len(ciphertext) % 16 != 0:
        raise ValueError(f"SM4密文长度必须为16的倍数，当前: {len(ciphertext)}")

    prev_block = iv
    result = b""

    for block_idx in range(0, len(ciphertext), 16):
        block = ciphertext[block_idx : block_idx + 16]
        decrypted = sm4_decrypt(block, key, use_pkcs7=False)

        plaintext_block = bytearray(decrypted)
        for i in range(16):
            plaintext_block[i] ^= prev_block[i]

        result += bytes(plaintext_block)
        prev_block = block

    return pkcs7_unpad(result, 16)


# ====== 便捷函数 ======
def generate_sm4_key() -> bytes:
    """生成随机SM4密钥"""
    return os.urandom(16)
