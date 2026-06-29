#!/usr/bin/env python3
"""Pure-stdlib PNG pixel-variance probe — no PIL/numpy (so it runs in bare CI).

Decodes a PNG (zlib + the 5 PNG filter types) and reports:
  - non_blank_frac : fraction of pixels that differ from the page background by > THRESH
  - distinct_lumas : number of distinct luminance buckets seen (a blank/solid page -> ~1)

A page that rendered *something* (buildings, polygons, scatter, text, UI chrome) will have many
distinct lumas and a non-trivial non-blank fraction even with the basemap blank. A page that
crashed before drawing is a flat fill -> distinct_lumas ~1, non_blank_frac ~0.

Usage: pixvar.py <png>   -> prints JSON {w,h,distinct_lumas,non_blank_frac,bg}
Exit 0 always; the caller decides thresholds (keeps this a pure measurement).
"""
import sys, json, zlib, struct, collections


def read_png(path):
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos = 8
    width = height = bitd = colort = None
    idat = bytearray()
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        ctype = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        if ctype == b"IHDR":
            width, height, bitd, colort = struct.unpack(">IIBB", chunk[:10])
        elif ctype == b"IDAT":
            idat += chunk
        elif ctype == b"IEND":
            break
        pos += 12 + length
    if bitd != 8 or colort not in (2, 6):
        raise ValueError("unsupported PNG (need 8-bit RGB/RGBA): bitd=%s colort=%s" % (bitd, colort))
    chans = 4 if colort == 6 else 3
    raw = zlib.decompress(bytes(idat))
    stride = width * chans
    out = bytearray(width * height * chans)

    def paeth(a, b, c):
        p = a + b - c
        pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
        if pa <= pb and pa <= pc:
            return a
        return b if pb <= pc else c

    ri = 0
    for y in range(height):
        ft = raw[ri]; ri += 1
        for x in range(stride):
            v = raw[ri]; ri += 1
            a = out[y * stride + x - chans] if x >= chans else 0
            b = out[(y - 1) * stride + x] if y > 0 else 0
            c = out[(y - 1) * stride + x - chans] if (y > 0 and x >= chans) else 0
            if ft == 0:
                out[y * stride + x] = v
            elif ft == 1:
                out[y * stride + x] = (v + a) & 255
            elif ft == 2:
                out[y * stride + x] = (v + b) & 255
            elif ft == 3:
                out[y * stride + x] = (v + (a + b) // 2) & 255
            elif ft == 4:
                out[y * stride + x] = (v + paeth(a, b, c)) & 255
            else:
                raise ValueError("bad filter %d" % ft)
    return width, height, chans, out


def main():
    path = sys.argv[1]
    w, h, chans, px = read_png(path)
    # subsample for speed: step so we examine ~40k pixels max regardless of size
    total = w * h
    step = max(1, int((total / 40000) ** 0.5))
    lumas = collections.Counter()
    samp = []
    for y in range(0, h, step):
        for x in range(0, w, step):
            i = (y * w + x) * chans
            r, g, b = px[i], px[i + 1], px[i + 2]
            lum = (r * 299 + g * 587 + b * 114) // 1000
            lumas[lum // 8] += 1   # 8-wide luma buckets
            samp.append((r, g, b))
    # background = most common sampled colour
    bgc = collections.Counter(samp).most_common(1)[0][0]
    THRESH = 24
    nonblank = sum(1 for (r, g, b) in samp
                   if abs(r - bgc[0]) + abs(g - bgc[1]) + abs(b - bgc[2]) > THRESH)
    print(json.dumps({
        "w": w, "h": h,
        "samples": len(samp),
        "distinct_lumas": len(lumas),
        "non_blank_frac": round(nonblank / max(1, len(samp)), 4),
        "bg": list(bgc),
    }))


if __name__ == "__main__":
    main()
