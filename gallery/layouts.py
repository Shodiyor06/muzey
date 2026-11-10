"""Muzey xaritalari.

Xarita — satrlar roʻyxati. ``#`` devor, ``.`` pol, ``S`` boshlanish nuqtasi,
``L`` — xat lavhasi turadigan katak, ``V`` — video turadigan katak (ikkalasi ham pol hisoblanadi).
4 ta tayyor shakl bor, lekin muzey rasmlar soniga qarab oʻzi uzayadi.
Qoʻlda chizilgan xarita (SiteSettings.map_data) boʻlsa, oʻsha ishlatiladi.
"""
from collections import deque

CELL = 4  # bir katak = 4 metr (front-end bilan bir xil)

MAPS = {
    "winding": ["#########", "#S......#", "#######.#", "#.......#", "#.#######", "#.......#", "#######.#", "#.......#", "#########"],
    "cross": ["#########", "####.####", "####.####", "####.####", "#...S...#", "####.####", "####.####", "####.####", "#########"],
    "ring": ["#########", "#.......#", "#.#####.#", "#.#####.#", "#.#####.#", "#S......#", "#########"],
    "rooms": ["###########", "#...#.....#", "#.S.#.....#", "#.........#", "#...#.....#", "###.#######", "#...#.....#", "#...#.....#", "###########"],
}
PALETTE_HEX = {"rose": "#7a3f56", "night": "#27325c", "gold": "#9c8160", "green": "#2f5a4c"}
D = ((0, -1), (1, 0), (0, 1), (-1, 0))


def parse(text):
    """Qoʻlda chizilgan xaritani tekshiradi. Notoʻgʻri boʻlsa ``None`` qaytaradi."""
    rows = [r.rstrip() for r in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    rows = [r for r in rows if r.strip()]
    if len(rows) < 3:
        return None
    width = max(len(r) for r in rows)
    if width < 3:
        return None
    rows = [r.ljust(width, "#") for r in rows]
    bad = set("".join(rows)) - set("#.SLV")
    if bad or not any("S" in r for r in rows):
        return None
    if not reachable(rows):
        return None
    return rows


def start(m):
    for z, row in enumerate(m):
        x = row.find("S")
        if x >= 0:
            return x, z
    return 1, 1


def is_floor(m, x, z):
    return 0 <= z < len(m) and 0 <= x < len(m[z]) and m[z][x] != "#"


def reachable(m):
    st, seen, q = start(m), {start(m)}, deque([start(m)])
    while q:
        x, z = q.popleft()
        for dx, dz in D:
            n = (x + dx, z + dz)
            if is_floor(m, *n) and n not in seen:
                seen.add(n)
                q.append(n)
    return len(seen) > 1


def slots(m):
    """Devorlarga osiladigan ramkalar, boshidan uzoqligi boʻyicha tartiblangan.

    Har bir element: ``{"x","z","dx","dz","d"}`` — devor tomon yoʻnalish va masofa.
    """
    st = start(m)
    depth = {st: 0}
    q = deque([st])
    out = []
    while q:
        x, z = q.popleft()
        for dx, dz in D:
            nx, nz = x + dx, z + dz
            if is_floor(m, nx, nz):
                if (nx, nz) not in depth:
                    depth[(nx, nz)] = depth[(x, z)] + 1
                    q.append((nx, nz))
            else:
                out.append({"x": x, "z": z, "dx": dx, "dz": dz, "d": depth[(x, z)]})
    out.sort(key=lambda s: s["d"])
    return out


def capacity(m):
    return len(slots(m))


def _blank(w, h):
    return [["#"] * w for _ in range(h)]


def _rows(grid):
    return ["".join(r) for r in grid]


def _fit(maker, need):
    """Kerakli ramkalar soniga yetadigan xaritani yasaydi."""
    return maker(max(3, need))


def _winding(need):
    """Iloniziq yoʻlak: rasmlar soniga mos eng ixcham uzunlik tanlanadi."""
    need = max(1, need)
    best = None
    for w in (5, 7, 9, 11):
        per_run = 2 * (w - 2) + 2
        first = max(1, -(-need // per_run))
        for runs in range(first, first + 3):
            h = 2 * runs + 1
            g = _blank(w, h)
            for k in range(runs):
                for x in range(1, w - 1):
                    g[2 * k + 1][x] = "."
            for k in range(runs - 1):
                g[2 * k + 2][w - 2 if k % 2 == 0 else 1] = "."
            g[1][1] = "S"
            m = _rows(g)
            got = len(slots(m))
            if got >= need:
                score = max(w, h) + min(w, h) * 0.5 + (got - need) * 0.3
                if best is None or score < best[0]:
                    best = (score, m)
                break
    return best[1]


def _cross(need):
    """Xoch zal: markazdan toʻrt tomonga choʻzilgan yoʻlaklar."""
    size = 5
    while size < 61:
        mid = size // 2
        g = _blank(size, size)
        for x in range(1, size - 1):
            g[mid][x] = "."
        for z in range(1, size - 1):
            g[z][mid] = "."
        g[mid][1] = "S"
        m = _rows(g)
        if len(slots(m)) >= need:
            return m
        size += 2
    return _rows(g)


def _ring(need):
    """Aylanma zal: halqa yoʻlak, rasmlar koʻpaygan sari choʻziladi."""
    h = 5
    for w in range(7, 61, 2):
        g = _blank(w, h)
        for z in (1, 3):
            for x in range(1, w - 1):
                g[z][x] = "."
        g[2][1] = g[2][w - 2] = "."
        g[1][1] = "S"
        m = _rows(g)
        if len(slots(m)) >= need:
            return m
    return _rows(g)


def _rooms(need):
    """Xonalar: bir-biriga eshik bilan ulangan 12x12 metrli zallar."""
    for count in range(1, 41):
        w = 4 * count + 1
        g = _blank(w, 5)
        for i in range(count):
            for x in range(4 * i + 1, 4 * i + 4):
                for z in (1, 2, 3):
                    g[z][x] = "."
            if i < count - 1:
                g[2][4 * i + 4] = "."
        g[1][1] = "S"
        m = _rows(g)
        if len(slots(m)) >= need:
            return m
    return _rows(g)


GENERATORS = {"winding": _winding, "cross": _cross, "ring": _ring, "rooms": _rooms}


def auto_map(layout, need):
    """Rasmlar soniga mos uzunlikdagi xarita."""
    maker = GENERATORS.get(layout or "winding", _winding)
    return _fit(maker, need)


def museum_map(settings, photos, has_video=False):
    """Joriy sozlamalar uchun ishlatiladigan xarita.

    Qoʻlda chizilgan xarita toʻgʻri boʻlsa — oʻsha, aks holda avtomatik xarita.
    Oxirgi devor (xat) va video uchun joy hisobga olinadi.
    """
    custom = parse(getattr(settings, "map_data", "") or "")
    if custom:
        return custom
    if photos == 0:
        need = 7 + (1 if has_video else 0)  # namuna ramkalar uchun
    else:
        need = photos + 1 + (1 if has_video else 0)
    return auto_map(getattr(settings, "layout", "winding"), need)


def map_meters(m):
    """Xaritaning eng katta tomoni, metrlarda."""
    return max(len(m[0]), len(m)) * CELL
