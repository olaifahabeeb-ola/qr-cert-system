import math
from PIL import Image, ImageDraw

GF_EXP = [0] * 512
GF_LOG  = [0] * 256

def _init_gf():
    x = 1
    for i in range(255):
        GF_EXP[i] = x
        GF_LOG[x]  = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    for i in range(255, 512):
        GF_EXP[i] = GF_EXP[i - 255]

_init_gf()

def gf_mul(a, b):
    if a == 0 or b == 0:
        return 0
    return GF_EXP[(GF_LOG[a] + GF_LOG[b]) % 255]

def gf_poly_mul(p, q):
    r = [0] * (len(p) + len(q) - 1)
    for j, qj in enumerate(q):
        for i, pi in enumerate(p):
            r[i + j] ^= gf_mul(pi, qj)
    return r

def gf_poly_div(dividend, divisor):
    msg = list(dividend)
    for i in range(len(dividend) - len(divisor) + 1):
        coef = msg[i]
        if coef:
            for j in range(1, len(divisor)):
                if divisor[j]:
                    msg[i + j] ^= gf_mul(divisor[j], coef)
    sep = len(divisor) - 1
    return msg[:-sep], msg[-sep:]

def rs_generator_poly(n):
    g = [1]
    for i in range(n):
        g = gf_poly_mul(g, [1, GF_EXP[i]])
    return g

def rs_encode(data, n_ec):
    gen    = rs_generator_poly(n_ec)
    padded = data + [0] * n_ec
    _, rem = gf_poly_div(padded, gen)
    return data + rem

QR_VERSIONS = [
    (1,  26,  16,  10, 21),
    (2,  44,  28,  16, 25),
    (3,  70,  44,  26, 29),
    (4,  100, 64,  36, 33),
    (5,  134, 86,  48, 37),
    (6,  172, 108, 64, 41),
    (7,  196, 124, 72, 45),
    (8,  242, 154, 88, 49),
    (9,  292, 182, 110, 53),
    (10, 346, 216, 130, 57),
]

def pick_version(data_len):
    for ver, total, data, ec, size in QR_VERSIONS:
        if data_len <= data:
            return ver, total, data, ec, size
    raise ValueError(f"Data too long ({data_len} bytes) for supported QR versions")

ALIGN_POS = {
    1: [], 2: [6,18], 3: [6,22], 4: [6,26], 5: [6,30],
    6: [6,34], 7: [6,22,38], 8: [6,24,42], 9: [6,26,46], 10: [6,28,50],
}

FORMAT_STRINGS = {
    0: 0b101010000010010,
    1: 0b101000100100101,
    2: 0b101111001111100,
    3: 0b101101101001011,
    4: 0b100010111111001,
    5: 0b100000011001110,
    6: 0b100111110010111,
    7: 0b100101010100000,
}


class QRCode:
    def __init__(self, data: str):
        raw = data.encode('utf-8')
        ver, total, data_cap, ec_count, self.size = pick_version(len(raw))
        self.version = ver

        bits = []
        bits += [0, 1, 0, 0]
        n = len(raw)
        for i in range(7, -1, -1):
            bits.append((n >> i) & 1)
        for byte in raw:
            for i in range(7, -1, -1):
                bits.append((byte >> i) & 1)
        bits += [0, 0, 0, 0]
        while len(bits) % 8:
            bits.append(0)
        pad_bytes = [0xEC, 0x11]
        i = 0
        while len(bits) < data_cap * 8:
            bits += [(pad_bytes[i % 2] >> k) & 1 for k in range(7, -1, -1)]
            i += 1
        bits = bits[:data_cap * 8]

        data_cw = [
            sum(bits[i*8+j] << (7-j) for j in range(8))
            for i in range(data_cap)
        ]
        full_cw = rs_encode(data_cw, ec_count)

        self.modules = [[None] * self.size for _ in range(self.size)]
        self._place_patterns()
        self._place_data(full_cw)
        self._apply_mask()

    def _set(self, r, c, v):
        if 0 <= r < self.size and 0 <= c < self.size:
            self.modules[r][c] = v

    def _place_finder(self, tr, tc):
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                r, c = tr + dr, tc + dc
                if not (0 <= r < self.size and 0 <= c < self.size):
                    continue
                if dr in (-1, 7) or dc in (-1, 7):
                    self._set(r, c, False)
                elif dr in (0, 6) or dc in (0, 6):
                    self._set(r, c, True)
                elif 2 <= dr <= 4 and 2 <= dc <= 4:
                    self._set(r, c, True)
                else:
                    self._set(r, c, False)

    def _place_alignment(self, cr, cc):
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                r, c = cr + dr, cc + dc
                if self.modules[r][c] is not None:
                    continue
                if dr in (-2, 2) or dc in (-2, 2):
                    self._set(r, c, True)
                elif dr == 0 and dc == 0:
                    self._set(r, c, True)
                else:
                    self._set(r, c, False)

    def _place_patterns(self):
        s = self.size
        self._place_finder(0, 0)
        self._place_finder(0, s - 7)
        self._place_finder(s - 7, 0)
        for i in range(8, s - 8):
            self._set(6, i, i % 2 == 0)
            self._set(i, 6, i % 2 == 0)
        self._set(4 * self.version + 9, 8, True)
        pos = ALIGN_POS.get(self.version, [])
        for cr in pos:
            for cc in pos:
                if self.modules[cr][cc] is None:
                    self._place_alignment(cr, cc)
        fmt_pos = (
            [(8, i) for i in range(6)] +
            [(8, 7), (8, 8), (7, 8)] +
            [(i, 8) for i in range(6, -1, -1)] +
            [(s - 1 - i, 8) for i in range(7)] +
            [(8, s - 1 - i) for i in range(8)]
        )
        for r, c in fmt_pos:
            if self.modules[r][c] is None:
                self._set(r, c, False)

    def _place_data(self, codewords):
        bits = []
        for cw in codewords:
            for i in range(7, -1, -1):
                bits.append((cw >> i) & 1)
        s       = self.size
        bit_idx = 0
        col     = s - 1
        going_up = True
        while col >= 0:
            if col == 6:
                col -= 1
                continue
            rows = range(s - 1, -1, -1) if going_up else range(s)
            for row in rows:
                for dc in (0, -1):
                    c = col + dc
                    if self.modules[row][c] is None:
                        if bit_idx < len(bits):
                            self.modules[row][c] = bits[bit_idx]
                            bit_idx += 1
                        else:
                            self.modules[row][c] = False
            col -= 2
            going_up = not going_up

    def _score(self, grid):
        s     = self.size
        score = 0
        for row in grid:
            run = 1
            for i in range(1, s):
                if row[i] == row[i-1]:
                    run += 1
                else:
                    if run >= 5:
                        score += run - 2
                    run = 1
            if run >= 5:
                score += run - 2
        for c in range(s):
            run = 1
            for r in range(1, s):
                if grid[r][c] == grid[r-1][c]:
                    run += 1
                else:
                    if run >= 5:
                        score += run - 2
                    run = 1
            if run >= 5:
                score += run - 2
        dark  = sum(grid[r][c] for r in range(s) for c in range(s))
        total = s * s
        pct   = dark / total * 100
        score += abs(int(pct / 5) * 5 - 50) // 5 * 10
        return score

    def _apply_mask(self):
        s = self.size
        best_score = None
        best_grid  = None

        mask_fns = [
            lambda r, c: (r + c) % 2 == 0,
            lambda r, c: r % 2 == 0,
            lambda r, c: c % 3 == 0,
            lambda r, c: (r + c) % 3 == 0,
            lambda r, c: (r // 2 + c // 3) % 2 == 0,
            lambda r, c: (r * c) % 2 + (r * c) % 3 == 0,
            lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0,
            lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0,
        ]

        for mask_id, fn in enumerate(mask_fns):
            grid = [
                [bool(self.modules[r][c]) for c in range(s)]
                for r in range(s)
            ]
            for r in range(s):
                for c in range(s):
                    if self.modules[r][c] is not None and fn(r, c):
                        grid[r][c] = not grid[r][c]
            fmt      = FORMAT_STRINGS[mask_id]
            fmt_bits = [(fmt >> (14 - i)) & 1 for i in range(15)]
            positions = (
                [(8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5),
                 (8, 7), (8, 8), (7, 8), (5, 8), (4, 8), (3, 8),
                 (2, 8), (1, 8), (0, 8)]
            )
            for i, (r, c) in enumerate(positions):
                grid[r][c] = bool(fmt_bits[i])
            score = self._score(grid)
            if best_score is None or score < best_score:
                best_score = score
                best_grid  = grid

        self.grid = best_grid

    def to_image(self, box_size=10, border=4):
        s        = self.size
        img_size = (s + 2 * border) * box_size
        img      = Image.new('RGB', (img_size, img_size), 'white')
        draw     = ImageDraw.Draw(img)
        for r in range(s):
            for c in range(s):
                if self.grid[r][c]:
                    x = (border + c) * box_size
                    y = (border + r) * box_size
                    draw.rectangle(
                        [x, y, x + box_size - 1, y + box_size - 1],
                        fill='black'
                    )
        return img


def make_qr(data: str, box_size=8, border=3) -> Image.Image:
    return QRCode(data).to_image(box_size=box_size, border=border)