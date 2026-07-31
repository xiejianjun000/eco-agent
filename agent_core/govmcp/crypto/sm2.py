"""
govmcp 国密加密模块 — SM2非对称加密

SM2: 中国国家密码管理局发布的椭圆曲线公钥密码算法 (GB/T 32918-2016)
     基于256位椭圆曲线，强度等同于NIST P-256/prime256v1

功能:
- SM2 密钥对生成
- SM2 加密/解密 (ECIES风格)
- SM2 签名/验签 (ECDSA风格)
- SM2 密钥派生函数 (KDF)

生产环境应使用硬件加密模块（HSM）或国密专用芯片。
本模块提供纯软件参考实现，用于开发与测试。
"""

import hashlib
import os
from typing import Tuple

# ====== SM2 国密椭圆曲线参数 (GB/T 32918-2016) ======
# SM2 曲线方程: y^2 = x^3 + ax + b (mod p)
SM2_P = 0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFF
SM2_A = 0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFC
SM2_B = 0x28E9FA9E9D9F5E344D5A9E4BCF6509A7F39789F515AB8F92DDBCBD414D940E93
SM2_N = 0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123
SM2_G_X = 0x32C4AE2C1F1981195F9904466A39C9948FE30BBFF2660BE1715A4589334C74C7
SM2_G_Y = 0xBC3736A2F4F6779C59BDCEE36B692153D0A9877CC62A474002DF32E52139F0A0

# 哈希函数使用 SM3
SM2_DEFAULT_ID = b"1234567812345678"


def _mod_inverse(a: int, m: int) -> int:
    """扩展欧几里得算法求模逆元"""
    if a < 0:
        a = (a % m + m) % m
    g, x, _ = _extended_gcd(a, m)
    if g != 1:
        raise ValueError("模逆元不存在")
    return x % m


def _extended_gcd(a: int, b: int) -> tuple[int, int, int]:
    """扩展欧几里得算法"""
    if a == 0:
        return b, 0, 1
    gcd, x1, y1 = _extended_gcd(b % a, a)
    x = y1 - (b // a) * x1
    y = x1
    return gcd, x, y


def _point_add(p1: tuple[int, int], p2: tuple[int, int]) -> tuple[int, int]:
    """椭圆曲线点加运算"""
    if p1 is None:
        return p2
    if p2 is None:
        return p1

    x1, y1 = p1
    x2, y2 = p2

    if x1 == x2:
        if y1 == y2:
            return _point_double(p1)
        return None

    lam = ((y2 - y1) * _mod_inverse(x2 - x1, SM2_P)) % SM2_P
    x3 = (lam * lam - x1 - x2) % SM2_P
    y3 = (lam * (x1 - x3) - y1) % SM2_P

    return (x3, y3)


def _point_double(p: tuple[int, int]) -> tuple[int, int]:
    """椭圆曲线倍点运算"""
    x1, y1 = p

    lam = ((3 * x1 * x1 + SM2_A) * _mod_inverse(2 * y1, SM2_P)) % SM2_P
    x3 = (lam * lam - 2 * x1) % SM2_P
    y3 = (lam * (x1 - x3) - y1) % SM2_P

    return (x3, y3)


def _point_mul(k: int, p: tuple[int, int]) -> tuple[int, int]:
    """椭圆曲线标量乘法 (二进制展开法)"""
    if k == 0:
        return None
    if k < 0:
        result = _point_mul(-k, p)
        return (result[0], (-result[1]) % SM2_P) if result else None

    result = None
    addend = p

    while k:
        if k & 1:
            result = _point_add(result, addend)
        addend = _point_double(addend)
        k >>= 1

    return result


def _is_on_curve(p: tuple[int, int]) -> bool:
    """检查点是否在椭圆曲线上"""
    if p is None:
        return True
    x, y = p
    return (y * y - x * x * x - SM2_A * x - SM2_B) % SM2_P == 0


def _int_to_bytes(n: int, length: int) -> bytes:
    """整数转字节数组 (大端序)"""
    return n.to_bytes(length, "big")


def _bytes_to_int(b: bytes) -> int:
    """字节数组转整数 (大端序)"""
    return int.from_bytes(b, "big")


def _kdf(shared_secret: bytes, klen: int) -> bytes:
    """
    SM2 密钥派生函数 (KDF)
    基于SM3的KBKDF

    Args:
        shared_secret: 共享秘密 (32字节)
        klen: 期望输出长度 (字节)

    Returns:
        派生密钥
    """
    from govmcp.crypto.sm import sm3_hash

    ct = 1
    result = b""

    while len(result) < klen:
        k = _bytes_to_int(shared_secret)
        k = (k + ct) % (1 << 256)
        k_bytes = _int_to_bytes(k, 32)
        h = sm3_hash(k_bytes)
        h_bytes = bytes.fromhex(h)
        if h_bytes == b"\x00" * 32 and len(result) + 32 > klen:
            h_bytes = bytes(32)
        result += h_bytes
        ct += 1
        if ct > (1 << 32):
            raise ValueError("KDF 迭代次数超限")

    return result[:klen]


def _sm3_z(user_id: bytes, public_key: tuple[int, int]) -> bytes:
    """
    计算SM2签名使用的Z值
    Z = SM3(ENTL || ID || a || b || xG || yG || xA || yA)
    """
    from govmcp.crypto.sm import sm3_hash

    entl = (len(user_id) * 8).to_bytes(2, "big")

    a_bytes = _int_to_bytes(SM2_A, 32)
    b_bytes = _int_to_bytes(SM2_B, 32)
    gx_bytes = _int_to_bytes(SM2_G_X, 32)
    gy_bytes = _int_to_bytes(SM2_G_Y, 32)
    px_bytes = _int_to_bytes(public_key[0], 32)
    py_bytes = _int_to_bytes(public_key[1], 32)

    data = entl + user_id + a_bytes + b_bytes + gx_bytes + gy_bytes + px_bytes + py_bytes

    z = sm3_hash(data)
    return bytes.fromhex(z)


def _parse_public_key(public_key: bytes) -> tuple[int, int]:
    """解析公钥为坐标点"""
    if len(public_key) != 64:
        raise ValueError(f"SM2公钥必须为64字节，当前: {len(public_key)}")

    x = _bytes_to_int(public_key[:32])
    y = _bytes_to_int(public_key[32:])

    return (x, y)


def _parse_private_key(private_key: bytes) -> int:
    """解析私钥"""
    if len(private_key) != 32:
        raise ValueError(f"SM2私钥必须为32字节，当前: {len(private_key)}")

    return _bytes_to_int(private_key)


def _public_key_to_bytes(p: tuple[int, int]) -> bytes:
    """公钥点转字节数组"""
    if p is None:
        raise ValueError("无效的公钥点")
    return _int_to_bytes(p[0], 32) + _int_to_bytes(p[1], 32)


def _bytes_to_public_key(data: bytes) -> tuple[int, int]:
    """字节数组转公钥点"""
    if len(data) != 64:
        raise ValueError(f"公钥数据必须为64字节，当前: {len(data)}")
    return _parse_public_key(data)


def _generate_random_n() -> int:
    """生成随机数k (1 <= k < N)"""
    while True:
        k_bytes = os.urandom(32)
        k = _bytes_to_int(k_bytes)
        if 1 <= k < SM2_N:
            return k


def generate_sm2_keypair() -> tuple[bytes, bytes]:
    """
    生成SM2密钥对

    Returns:
        Tuple[private_key, public_key]:
        - private_key: 32字节私钥
        - public_key: 64字节公钥 (未压缩格式: x||y)

    Example:
        >>> private_key, public_key = generate_sm2_keypair()
        >>> len(private_key), len(public_key)
        (32, 64)
    """
    while True:
        d = _bytes_to_int(os.urandom(32))
        if 1 <= d < SM2_N:
            break

    g_point = (SM2_G_X, SM2_G_Y)
    public_key_point = _point_mul(d, g_point)

    if not _is_on_curve(public_key_point):
        return generate_sm2_keypair()

    private_key = _int_to_bytes(d, 32)
    public_key = _public_key_to_bytes(public_key_point)

    return private_key, public_key


def sm2_encrypt(plaintext: bytes, public_key: bytes) -> bytes:
    """
    SM2加密 (C1 || C3 || C2 格式)

    使用SM2椭圆曲线公钥加密算法:
    1. 使用随机数k生成C1点
    2. 计算S = k*P，并计算C3 = SM3(x2 || M || y2)
    3. 计算C2 = M XOR t

    Args:
        plaintext: 明文数据
        public_key: 64字节公钥

    Returns:
        密文: C1(64字节) || C3(32字节) || C2(与明文等长)

    Raises:
        ValueError: 公钥格式错误

    Example:
        >>> private_key, public_key = generate_sm2_keypair()
        >>> ciphertext = sm2_encrypt(b"hello", public_key)
        >>> len(ciphertext) > len(b"hello")
        True
    """
    from govmcp.crypto.sm import sm3_hash

    if len(public_key) != 64:
        raise ValueError(f"SM2公钥必须为64字节，当前: {len(public_key)}")

    p = _parse_public_key(public_key)

    if not _is_on_curve(p):
        raise ValueError("公钥不在有效曲线上")

    g_point = (SM2_G_X, SM2_G_Y)
    m_len = len(plaintext)

    while True:
        k = _generate_random_n()
        c1_point = _point_mul(k, g_point)

        if c1_point is None or not _is_on_curve(c1_point):
            continue

        s_point = _point_mul(k, p)

        if s_point is None or not _is_on_curve(s_point):
            continue

        x2, y2 = s_point
        t = _kdf(_int_to_bytes(x2, 32) + _int_to_bytes(y2, 32), m_len)

        if m_len > 0 and b"\x00" * m_len == t:
            continue

        c2 = bytes(m ^ k for m, k in zip(plaintext, t))

        c3_input = _int_to_bytes(x2, 32) + plaintext + _int_to_bytes(y2, 32)
        c3 = bytes.fromhex(sm3_hash(c3_input))

        c1 = _public_key_to_bytes(c1_point)

        return c1 + c3 + c2


def sm2_decrypt(ciphertext: bytes, private_key: bytes) -> bytes:
    """
    SM2解密

    使用SM2椭圆曲线私钥解密算法:
    1. 从C1解析点
    2. 计算S = d*C1
    3. 计算M' = C2 XOR t
    4. 验证C3 = SM3(x2 || M' || y2)

    Args:
        ciphertext: 密文 (C1||C3||C2格式)
        private_key: 32字节私钥

    Returns:
        明文

    Raises:
        ValueError: 密文或私钥格式错误

    Example:
        >>> private_key, public_key = generate_sm2_keypair()
        >>> ciphertext = sm2_encrypt(b"hello", public_key)
        >>> sm2_decrypt(ciphertext, private_key)
        b'hello'
    """
    from govmcp.crypto.sm import sm3_hash

    if len(private_key) != 32:
        raise ValueError(f"SM2私钥必须为32字节，当前: {len(private_key)}")

    min_len = 64 + 32
    if len(ciphertext) < min_len:
        raise ValueError(f"SM2密文太短，最小: {min_len}字节")

    c1 = ciphertext[:64]
    c3 = ciphertext[64:96]
    c2 = ciphertext[96:]

    c1_point = _bytes_to_public_key(c1)

    if not _is_on_curve(c1_point):
        raise ValueError("密文中C1不是有效曲线点")

    d = _parse_private_key(private_key)
    s_point = _point_mul(d, c1_point)

    if s_point is None or not _is_on_curve(s_point):
        raise ValueError("密钥派生点无效")

    x2, y2 = s_point
    m_len = len(c2)
    t = _kdf(_int_to_bytes(x2, 32) + _int_to_bytes(y2, 32), m_len)

    if m_len > 0 and b"\x00" * m_len == t:
        raise ValueError("密钥派生失败")

    m = bytes(c ^ k for c, k in zip(c2, t))

    check_input = _int_to_bytes(x2, 32) + m + _int_to_bytes(y2, 32)
    check_c3 = bytes.fromhex(sm3_hash(check_input))

    if c3 != check_c3:
        raise ValueError("SM2解密验证失败 - 数据可能被篡改")

    return m


def sm2_sign(data: bytes, private_key: bytes, user_id: bytes = None) -> bytes:
    """
    SM2签名 (GB/T 32918-2016)

    使用SM2椭圆曲线数字签名算法:
    1. 计算Z = SM3(ENTL || ID || a || b || G || P)
    2. 计算e = SM3(Z || M)
    3. 计算(r + e) mod N != 0
    4. 计算s = d^(-1) * (k - r) mod N

    Args:
        data: 待签名数据
        private_key: 32字节私钥
        user_id: 用户标识 (默认: b"1234567812345678")

    Returns:
        签名: r(32字节) || s(32字节)，共64字节

    Example:
        >>> private_key, public_key = generate_sm2_keypair()
        >>> signature = sm2_sign(b"test data", private_key)
        >>> len(signature)
        64
    """
    from govmcp.crypto.sm import sm3_hash

    if user_id is None:
        user_id = SM2_DEFAULT_ID

    if len(private_key) != 32:
        raise ValueError(f"SM2私钥必须为32字节，当前: {len(private_key)}")

    d = _parse_private_key(private_key)
    p = _point_mul(d, (SM2_G_X, SM2_G_Y))

    if p is None:
        raise ValueError("公钥派生失败")

    z = _sm3_z(user_id, p)

    e_hash = sm3_hash(z + data)
    e = _bytes_to_int(bytes.fromhex(e_hash))

    g_point = (SM2_G_X, SM2_G_Y)

    while True:
        k = _generate_random_n()
        point1 = _point_mul(k, g_point)

        if point1 is None:
            continue

        x1, y1 = point1
        r = (e + x1) % SM2_N

        if r == 0 or r + k == SM2_N:
            continue

        d_plus_1_inv = _mod_inverse((1 + d) % SM2_N, SM2_N)
        s = (d_plus_1_inv * ((k - r * d) % SM2_N)) % SM2_N

        if s == 0:
            continue

        return _int_to_bytes(r, 32) + _int_to_bytes(s, 32)


def sm2_verify(data: bytes, signature: bytes, public_key: bytes, user_id: bytes = None) -> bool:
    """
    SM2验签

    Args:
        data: 原始数据
        signature: 64字节签名 (r || s)
        public_key: 64字节公钥
        user_id: 用户标识 (默认: b"1234567812345678")

    Returns:
        验签结果: True 或 False

    Example:
        >>> private_key, public_key = generate_sm2_keypair()
        >>> signature = sm2_sign(b"test data", private_key)
        >>> sm2_verify(b"test data", signature, public_key)
        True
    """
    from govmcp.crypto.sm import sm3_hash

    if user_id is None:
        user_id = SM2_DEFAULT_ID

    if len(public_key) != 64:
        raise ValueError(f"SM2公钥必须为64字节，当前: {len(public_key)}")

    if len(signature) != 64:
        raise ValueError(f"SM2签名必须为64字节，当前: {len(signature)}")

    try:
        p = _parse_public_key(public_key)
    except ValueError:
        return False

    if not _is_on_curve(p):
        return False

    r = _bytes_to_int(signature[:32])
    s = _bytes_to_int(signature[32:])

    if r < 1 or r >= SM2_N or s < 1 or s >= SM2_N:
        return False

    z = _sm3_z(user_id, p)
    e_hash = sm3_hash(z + data)
    e = _bytes_to_int(bytes.fromhex(e_hash))

    t = (r + s) % SM2_N
    if t == 0:
        return False

    g_point = (SM2_G_X, SM2_G_Y)
    point1 = _point_mul(s, g_point)
    point2 = _point_mul(t, p)

    if point1 is None or point2 is None:
        return False

    x1, y1 = _point_add(point1, point2)

    if x1 is None:
        return False

    v = (e + x1) % SM2_N

    return v == r


def sm2_derive_key(shared_secret: bytes, key_length: int = 32) -> bytes:
    """
    SM2密钥派生函数 (KDF)

    基于SM3的密钥派生函数，用于从共享秘密派生出密钥材料。

    Args:
        shared_secret: 共享秘密 (建议32字节)
        key_length: 期望输出的密钥长度 (字节)

    Returns:
        派生的密钥

    Example:
        >>> key = sm2_derive_key(os.urandom(32), 32)
        >>> len(key)
        32
    """
    if len(shared_secret) < 16:
        raise ValueError("共享秘密长度至少16字节")

    if key_length < 1:
        raise ValueError("密钥长度必须大于0")

    return _kdf(shared_secret, key_length)


def sm2_calculate_shared_secret(private_key: bytes, peer_public_key: bytes) -> bytes:
    """
    SM2椭圆曲线Diffie-Hellman密钥交换 - 计算共享秘密

    计算 ECDH 共享点坐标，用于密钥派生。

    Args:
        private_key: 本端私钥 (32字节)
        peer_public_key: 对端公钥 (64字节)

    Returns:
        共享秘密 (x坐标的32字节)

    Example:
        >>> private_a, public_a = generate_sm2_keypair()
        >>> private_b, public_b = generate_sm2_keypair()
        >>> secret_a = sm2_calculate_shared_secret(private_a, public_b)
        >>> secret_b = sm2_calculate_shared_secret(private_b, public_a)
        >>> secret_a == secret_b
        True
    """
    if len(private_key) != 32:
        raise ValueError(f"SM2私钥必须为32字节，当前: {len(private_key)}")

    if len(peer_public_key) != 64:
        raise ValueError(f"SM端公钥必须为64字节，当前: {len(peer_public_key)}")

    d = _parse_private_key(private_key)
    p = _parse_public_key(peer_public_key)

    if not _is_on_curve(p):
        raise ValueError("对端公钥不在有效曲线上")

    shared_point = _point_mul(d, p)

    if shared_point is None or not _is_on_curve(shared_point):
        raise ValueError("共享点计算失败")

    x, _ = shared_point
    return _int_to_bytes(x, 32)
