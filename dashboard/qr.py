#!/usr/bin/env python3
"""qr.py - a tiny, dependency-free QR encoder (byte mode, EC level L, versions 1-10).

Just enough QR to turn a LAN dashboard URL into something you can point a phone at:

    from qr import qr_matrix, qr_ascii, qr_svg
    m = qr_matrix("http://192.168.1.20:8770")

`qr_matrix` returns a list of rows of 0/1 ints (1 = dark, no quiet zone included);
`qr_ascii` renders it for a terminal and `qr_svg` for a browser page.

No third-party deps, matching the rest of this repo.
"""

# ---- GF(256), primitive polynomial 0x11D ----
_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _mul(a, b):
    return 0 if a == 0 or b == 0 else _EXP[_LOG[a] + _LOG[b]]


def _generator(n):
    """Generator polynomial for n EC codewords, highest degree first."""
    g = [1]
    for i in range(n):
        ng = [0] * (len(g) + 1)
        for j, c in enumerate(g):
            ng[j] ^= c
            ng[j + 1] ^= _mul(c, _EXP[i])
        g = ng
    return g


def _ecc(data, n):
    g = _generator(n)
    rem = list(data) + [0] * n
    for i in range(len(data)):
        f = rem[i]
        if f:
            for j, c in enumerate(g):
                rem[i + j] ^= _mul(c, f)
    return rem[len(data):]


# ---- version tables, EC level L: version -> (total codewords, ec per block, [(blocks, data cw)]) ----
_VERSIONS = {
    1:  (26,   7, [(1, 19)]),
    2:  (44,  10, [(1, 34)]),
    3:  (70,  15, [(1, 55)]),
    4:  (100, 20, [(1, 80)]),
    5:  (134, 26, [(1, 108)]),
    6:  (172, 18, [(2, 68)]),
    7:  (196, 20, [(2, 78)]),
    8:  (242, 24, [(2, 97)]),
    9:  (292, 30, [(2, 116)]),
    10: (346, 18, [(2, 68), (2, 69)]),
}
_ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30],
          6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50]}
_REMAINDER = {1: 0, 2: 7, 3: 7, 4: 7, 5: 7, 6: 7, 7: 0, 8: 0, 9: 0, 10: 0}


def _pick_version(nbytes):
    for v in range(1, 11):
        data_cw = sum(c * d for c, d in _VERSIONS[v][2])
        count_bits = 8 if v < 10 else 16
        if 4 + count_bits + 8 * nbytes <= data_cw * 8:
            return v
    raise ValueError(f"{nbytes} bytes is too long for this encoder (max ~271)")


def _bitstream(data, version):
    data_cw = sum(c * d for c, d in _VERSIONS[version][2])
    bits = []

    def put(value, n):
        for i in range(n - 1, -1, -1):
            bits.append((value >> i) & 1)

    put(0b0100, 4)                              # byte mode
    put(len(data), 8 if version < 10 else 16)   # character count
    for b in data:
        put(b, 8)
    put(0, min(4, data_cw * 8 - len(bits)))     # terminator
    while len(bits) % 8:
        bits.append(0)
    cw = [int("".join(str(b) for b in bits[i:i + 8]), 2) for i in range(0, len(bits), 8)]
    for pad in (0xEC, 0x11) * data_cw:          # pad codewords
        if len(cw) >= data_cw:
            break
        cw.append(pad)
    return cw


def _interleave(cw, version):
    _, ec_n, groups = _VERSIONS[version]
    blocks, pos = [], 0
    for count, size in groups:
        for _ in range(count):
            blocks.append(cw[pos:pos + size])
            pos += size
    ec_blocks = [_ecc(b, ec_n) for b in blocks]
    out = []
    for i in range(max(len(b) for b in blocks)):
        out += [b[i] for b in blocks if i < len(b)]
    for i in range(ec_n):
        out += [b[i] for b in ec_blocks]
    return out


def _bch(value, generator, gen_bits):
    rem = value
    while rem.bit_length() >= gen_bits:
        rem ^= generator << (rem.bit_length() - gen_bits)
    return rem


def _format_bits(mask):
    v = (0b01 << 3) | mask                        # EC level L = 01
    full = (v << 10) | _bch(v << 10, 0b10100110111, 11)
    return full ^ 0b101010000010010


def _version_bits(version):
    return (version << 12) | _bch(version << 12, 0b1111100100101, 13)


def _skeleton(version):
    size = 4 * version + 17
    m = [[0] * size for _ in range(size)]
    fixed = [[False] * size for _ in range(size)]

    def rect(r0, c0, h, w, val):
        for r in range(r0, r0 + h):
            for c in range(c0, c0 + w):
                if 0 <= r < size and 0 <= c < size:
                    m[r][c] = val
                    fixed[r][c] = True

    for r0, c0 in ((0, 0), (0, size - 7), (size - 7, 0)):     # finders + separators
        rect(r0 - 1, c0 - 1, 9, 9, 0)
        rect(r0, c0, 7, 7, 1)
        rect(r0 + 1, c0 + 1, 5, 5, 0)
        rect(r0 + 2, c0 + 2, 3, 3, 1)

    centers = _ALIGN[version]                                  # alignment patterns
    for r in centers:
        for c in centers:
            if fixed[r][c]:
                continue
            rect(r - 2, c - 2, 5, 5, 1)
            rect(r - 1, c - 1, 3, 3, 0)
            rect(r, c, 1, 1, 1)

    for i in range(size):                                      # timing patterns
        for r, c in ((6, i), (i, 6)):
            if not fixed[r][c]:
                m[r][c] = 1 - (i % 2)
                fixed[r][c] = True

    rect(4 * version + 9, 8, 1, 1, 1)                          # dark module

    for i in range(9):                                         # reserve format info
        for r, c in ((8, i), (i, 8)):
            fixed[r][c] = True
    for i in range(8):
        fixed[8][size - 1 - i] = True
        fixed[size - 1 - i][8] = True

    if version >= 7:                                           # version info
        bits = _version_bits(version)
        for i in range(18):
            b = (bits >> i) & 1
            r, c = i // 3, size - 11 + i % 3
            m[r][c] = m[c][r] = b
            fixed[r][c] = fixed[c][r] = True
    return m, fixed, size


def _place_data(m, fixed, size, codewords, version):
    bits = [(b >> i) & 1 for b in codewords for i in range(7, -1, -1)]
    bits += [0] * _REMAINDER[version]
    idx, col, up = 0, size - 1, True
    while col > 0:
        if col == 6:
            col -= 1
        for i in range(size):
            row = size - 1 - i if up else i
            for c in (col, col - 1):
                if not fixed[row][c]:
                    m[row][c] = bits[idx] if idx < len(bits) else 0
                    idx += 1
        up = not up
        col -= 2


_MASKS = (
    lambda r, c: (r + c) % 2 == 0,
    lambda r, c: r % 2 == 0,
    lambda r, c: c % 3 == 0,
    lambda r, c: (r + c) % 3 == 0,
    lambda r, c: (r // 2 + c // 3) % 2 == 0,
    lambda r, c: (r * c) % 2 + (r * c) % 3 == 0,
    lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0,
    lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0,
)


def _penalty(m, size):
    score = 0
    for line in [m[r] for r in range(size)] + [[m[r][c] for r in range(size)] for c in range(size)]:
        run, prev = 1, line[0]
        for v in line[1:]:
            if v == prev:
                run += 1
            else:
                if run >= 5:
                    score += 3 + run - 5
                run, prev = 1, v
        if run >= 5:
            score += 3 + run - 5
        for i in range(size - 10):                 # 1:1:3:1:1 finder-like patterns
            seq = line[i:i + 11]
            if seq[:7] == [1, 0, 1, 1, 1, 0, 1] and seq[7:] == [0, 0, 0, 0]:
                score += 40
            if seq[4:] == [1, 0, 1, 1, 1, 0, 1] and seq[:4] == [0, 0, 0, 0]:
                score += 40
    for r in range(size - 1):                      # 2x2 blocks of one colour
        for c in range(size - 1):
            if m[r][c] == m[r][c + 1] == m[r + 1][c] == m[r + 1][c + 1]:
                score += 3
    dark = sum(sum(row) for row in m)
    score += 10 * (abs(dark * 100 // (size * size) - 50) // 5)
    return score


def _apply_format(m, size, mask):
    """Write both copies of the 15-bit format info (bit 0 = most significant)."""
    bits = _format_bits(mask)
    for i in range(15):
        b = (bits >> (14 - i)) & 1
        if i < 6:                       # copy 1: around the top-left finder
            m[8][i] = b
        elif i == 6:
            m[8][7] = b
        elif i == 7:
            m[8][8] = b
        elif i == 8:
            m[7][8] = b
        else:
            m[14 - i][8] = b
        if i < 7:                       # copy 2: bottom-left column, then top-right row
            m[size - 1 - i][8] = b
        else:
            m[8][size - 15 + i] = b


def qr_matrix(text):
    """Encode `text` as a QR code; returns rows of 0/1 ints (1 = dark)."""
    data = text.encode("utf-8")
    version = _pick_version(len(data))
    codewords = _interleave(_bitstream(data, version), version)
    base, fixed, size = _skeleton(version)
    _place_data(base, fixed, size, codewords, version)

    best, best_score = None, None
    for mask, fn in enumerate(_MASKS):
        m = [row[:] for row in base]
        for r in range(size):
            for c in range(size):
                if not fixed[r][c] and fn(r, c):
                    m[r][c] ^= 1
        _apply_format(m, size, mask)
        s = _penalty(m, size)
        if best_score is None or s < best_score:
            best, best_score = m, s
    return best


def qr_ascii(matrix, quiet=2):
    """Render a matrix for a terminal, two rows per line of half-blocks."""
    size = len(matrix)
    pad = [[0] * (size + 2 * quiet) for _ in range(quiet)]
    rows = pad + [[0] * quiet + row + [0] * quiet for row in matrix] + pad
    if len(rows) % 2:
        rows.append([0] * len(rows[0]))
    out = []
    for i in range(0, len(rows), 2):
        top, bot = rows[i], rows[i + 1]
        # inverted like `qrcode.print_ascii`: blocks are light modules, so this scans
        # off a dark-background terminal (the /phone page is the light-terminal fallback)
        out.append("".join(
            {(0, 0): "█", (1, 1): " ", (0, 1): "▀", (1, 0): "▄"}[(t, b)]
            for t, b in zip(top, bot)))
    return "\n".join(out)


def qr_svg(matrix, px=8, quiet=2):
    """Render a matrix as a self-contained SVG string."""
    size = len(matrix)
    dim = (size + 2 * quiet) * px
    cells = "".join(
        f'<rect x="{(c + quiet) * px}" y="{(r + quiet) * px}" width="{px}" height="{px}"/>'
        for r, row in enumerate(matrix) for c, v in enumerate(row) if v)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{dim}" height="{dim}" '
            f'viewBox="0 0 {dim} {dim}" role="img" aria-label="QR code">'
            f'<rect width="{dim}" height="{dim}" fill="#fff"/><g fill="#000">{cells}</g></svg>')


if __name__ == "__main__":
    import sys
    text = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8770"
    print(qr_ascii(qr_matrix(text)))
    print(text)
