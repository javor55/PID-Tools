"""
Ikona aplikace PID Tools: modrý čtverec se zaoblenými rohy, žádaná hodnota (oranžová přerušovaná) a odezva smyčky
s překmitem (bílá). Vytvoří pidtools/assets/icon.png (256 px, okno desktopu a web) a pidtools/assets/icon.ico
(Windows: exe, instalátor, zástupci) a pidtools/assets/logo.svg (logo v hlavičce webu, ostré v každé velikosti).
Spuštění: python tools/make_icon.py
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "pidtools" / "assets"


def draw(size=1024):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = int(size * 0.2)
    # pozadí: svislý přechod modré
    grad = Image.new("RGBA", (size, size))
    gd = ImageDraw.Draw(grad)
    for y in range(size):
        f = y / size
        gd.line([(0, y), (size, y)], fill=(int(30 + 10 * f), int(98 - 30 * f), int(178 - 50 * f), 255))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=255)
    img.paste(grad, (0, 0), mask)
    m = size * 0.16
    x0, x1, y_lo, y_hi = m, size - m, size * 0.74, size * 0.34
    w = max(2, int(size * 0.045))
    # žádaná hodnota: skok (oranžová, přerušovaná)
    xs = x0 + 0.18 * (x1 - x0)
    d.line([(xs, y_lo), (xs, y_hi)], fill=(251, 146, 60, 255), width=w)
    n_dash = 7
    for k in range(n_dash):
        a = xs + (x1 - xs) * k / n_dash
        b = a + (x1 - xs) / n_dash * 0.55
        d.line([(a, y_hi), (b, y_hi)], fill=(251, 146, 60, 255), width=w)
    # odezva: zpoždění, překmit, ustálení (bílá)
    t = np.linspace(0, 1, 400)
    tt = np.clip((t - 0.24) / 0.76, 0, None)
    zeta, wn = 0.42, 13.0
    wd = wn * np.sqrt(1 - zeta ** 2)
    y = 1 - np.exp(-zeta * wn * tt) * (np.cos(wd * tt) + zeta / np.sqrt(1 - zeta ** 2) * np.sin(wd * tt))
    y[t < 0.24] = 0
    pts = [(x0 + ti * (x1 - x0), y_lo + yi * (y_hi - y_lo)) for ti, yi in zip(t, y)]
    rad = w * 0.65                       # tlustá hladká čára: kruhy podél křivky (bez zubů na spojích)
    for (xa, ya), (xb, yb) in zip(pts[:-1], pts[1:]):
        for f in np.linspace(0, 1, 6):
            cx, cy = xa + f * (xb - xa), ya + f * (yb - ya)
            d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=(255, 255, 255, 255))
    return img


def _curve(size):
    """Body odezvy (zpoždění, překmit, ustálení) a geometrie skoku – společné pro PNG i SVG."""
    m = size * 0.16
    x0, x1, y_lo, y_hi = m, size - m, size * 0.74, size * 0.34
    t = np.linspace(0, 1, 160)
    tt = np.clip((t - 0.24) / 0.76, 0, None)
    zeta, wn = 0.42, 13.0
    wd = wn * np.sqrt(1 - zeta ** 2)
    y = 1 - np.exp(-zeta * wn * tt) * (np.cos(wd * tt) + zeta / np.sqrt(1 - zeta ** 2) * np.sin(wd * tt))
    y[t < 0.24] = 0
    return x0, x1, y_lo, y_hi, [(x0 + ti * (x1 - x0), y_lo + yi * (y_hi - y_lo)) for ti, yi in zip(t, y)]


def svg(size=256):
    """Stejná kresba jako ikona ve vektoru (SVG)."""
    x0, x1, y_lo, y_hi, pts = _curve(size)
    w = size * 0.045
    xs = x0 + 0.18 * (x1 - x0)
    dash = (x1 - xs) / 7
    path = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" role="img" aria-label="PID Tools">
  <defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1e62b2"/>
    <stop offset="1" stop-color="#28447e"/></linearGradient></defs>
  <rect width="{size}" height="{size}" rx="{size * 0.2:.1f}" fill="url(#g)"/>
  <path d="M{xs:.1f} {y_lo:.1f} V{y_hi:.1f}" stroke="#fb923c" stroke-width="{w:.1f}"/>
  <path d="M{xs:.1f} {y_hi:.1f} H{x1:.1f}" stroke="#fb923c" stroke-width="{w:.1f}"
        stroke-dasharray="{dash * 0.55:.1f} {dash * 0.45:.1f}"/>
  <path d="{path}" fill="none" stroke="#ffffff" stroke-width="{w * 1.3:.1f}" stroke-linecap="round"
        stroke-linejoin="round"/>
</svg>
"""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    big = draw(1024)
    big.resize((256, 256), Image.LANCZOS).save(OUT / "icon.png")
    big.resize((256, 256), Image.LANCZOS).save(OUT / "icon.ico",
                                               sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128),
                                                      (256, 256)])
    (OUT / "logo.svg").write_text(svg(), encoding="utf-8")
    print("icon:", OUT / "icon.png", OUT / "icon.ico", OUT / "logo.svg")


if __name__ == "__main__":
    main()
