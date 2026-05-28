#!/bin/bash
set -e
DEST="$HOME/Downloads/G99_SatelliteMap_179KGA.png"
TMPDIR_MAP="$HOME/Downloads/_g99_tiles"
mkdir -p "$TMPDIR_MAP"

echo "Fetching 9 ESRI satellite tiles..."

# Tile coords: z=18, centre tile x=130019, y=87852 (50.9203478,-1.4458938 = 179 King Georges Ave)
# 3x3 grid: x 130018-130020, y 87851-87853
for y in 87851 87852 87853; do
  for x in 130018 130019 130020; do
    FPATH="$TMPDIR_MAP/tile_${y}_${x}.jpg"
    if [ ! -f "$FPATH" ]; then
      curl -sf -A "Mozilla/5.0" \
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/18/${y}/${x}" \
        -o "$FPATH"
      echo "  tile $y/$x fetched ($(wc -c < "$FPATH") bytes)"
    else
      echo "  tile $y/$x cached ($(wc -c < "$FPATH") bytes)"
    fi
  done
done

echo "Compositing tiles with Python..."

# Find arm64-native python3
if [ -x /opt/homebrew/bin/python3 ]; then
  PY=/opt/homebrew/bin/python3
elif [ -x /usr/bin/python3 ]; then
  PY=/usr/bin/python3
else
  PY=python3
fi
echo "Using Python: $PY ($($PY --version 2>&1))"

$PY << 'PYEOF'
import struct, zlib, subprocess, os, math, sys

TILES_DIR = os.path.expanduser("~/Downloads/_g99_tiles")
DEST      = os.path.expanduser("~/Downloads/G99_SatelliteMap_179KGA.png")
TILE      = 256
GRID      = 3
SIZE      = TILE * GRID   # 768

def sips_to_raw(jpg_path):
    """Convert JPEG tile to raw RGB bytes using sips -> PNG -> parse."""
    png_path = jpg_path.replace('.jpg', '_tmp.png')
    result = subprocess.run(
        ['sips', '-s', 'format', 'png', jpg_path, '--out', png_path],
        capture_output=True
    )
    if result.returncode != 0:
        print(f"    sips stderr: {result.stderr.decode()}", file=sys.stderr)
        raise RuntimeError(f"sips failed for {jpg_path}")

    with open(png_path, 'rb') as f:
        data = f.read()
    os.remove(png_path)

    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError(f"Not a valid PNG for {jpg_path}")

    pos = 8
    width = height = 0
    bpp = 3
    idat_chunks = []

    while pos + 8 <= len(data):
        length = struct.unpack('>I', data[pos:pos+4])[0]
        chunk_type = data[pos+4:pos+8]
        chunk_data = data[pos+8:pos+8+length]

        if chunk_type == b'IHDR':
            width, height = struct.unpack('>II', chunk_data[:8])
            color_type = chunk_data[9]
            # color_type: 0=Grey, 2=RGB, 3=Indexed, 4=GreyA, 6=RGBA
            bpp = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type, 3)
            print(f"    PNG {width}x{height} color_type={color_type} bpp={bpp}")
        elif chunk_type == b'IDAT':
            idat_chunks.append(chunk_data)
        elif chunk_type == b'IEND':
            break
        pos += 12 + length

    if not idat_chunks:
        raise ValueError(f"No IDAT data in PNG for {jpg_path}")

    raw = zlib.decompress(b''.join(idat_chunks))
    stride = width * bpp
    rows_rgb = []
    prev = bytearray(stride)
    idx = 0

    for row_y in range(height):
        f_byte = raw[idx]; idx += 1
        row_raw = bytearray(raw[idx:idx+stride]); idx += stride

        if f_byte == 0:
            row = bytearray(row_raw)
        elif f_byte == 1:  # Sub
            row = bytearray(row_raw)
            for i in range(bpp, stride):
                row[i] = (row[i] + row[i-bpp]) & 0xff
        elif f_byte == 2:  # Up
            row = bytearray((row_raw[i] + prev[i]) & 0xff for i in range(stride))
        elif f_byte == 3:  # Average
            row = bytearray(row_raw)
            for i in range(stride):
                a = row[i-bpp] if i >= bpp else 0
                b_val = prev[i]
                row[i] = (row[i] + (a + b_val) // 2) & 0xff
        elif f_byte == 4:  # Paeth
            row = bytearray(row_raw)
            for i in range(stride):
                a = row[i-bpp] if i >= bpp else 0
                b_val = prev[i]
                c = prev[i-bpp] if i >= bpp else 0
                pa = abs(b_val - c)
                pb = abs(a - c)
                pc = abs(a + b_val - 2*c)
                pr = a if pa <= pb and pa <= pc else (b_val if pb <= pc else c)
                row[i] = (row[i] + pr) & 0xff
        else:
            raise ValueError(f"Unknown PNG filter byte {f_byte} at row {row_y}")

        prev = bytearray(row)

        # Emit exactly RGB regardless of source format
        if bpp == 3:
            rows_rgb.append(bytes(row))
        elif bpp == 4:   # RGBA -> RGB
            rgb = bytearray(width * 3)
            for x in range(width):
                rgb[x*3:x*3+3] = row[x*4:x*4+3]
            rows_rgb.append(bytes(rgb))
        elif bpp == 1:   # Grey -> RGB
            rgb = bytearray(width * 3)
            for x in range(width):
                v = row[x]
                rgb[x*3] = rgb[x*3+1] = rgb[x*3+2] = v
            rows_rgb.append(bytes(rgb))
        else:            # GreyA -> RGB
            rgb = bytearray(width * 3)
            for x in range(width):
                v = row[x*2]
                rgb[x*3] = rgb[x*3+1] = rgb[x*3+2] = v
            rows_rgb.append(bytes(rgb))

    return rows_rgb, width, height

# Build 768x768 pixel buffer
print("Decoding tiles...")
canvas = [bytearray(SIZE * 3) for _ in range(SIZE)]
tile_ys = [87851, 87852, 87853]
tile_xs = [130018, 130019, 130020]

for di, ty in enumerate(tile_ys):
    for dj, tx in enumerate(tile_xs):
        jpg = os.path.join(TILES_DIR, f"tile_{ty}_{tx}.jpg")
        try:
            rows, w, h = sips_to_raw(jpg)
        except Exception as e:
            print(f"  ERROR decoding tile {ty}/{tx}: {e}", file=sys.stderr)
            raise
        for row_i, row in enumerate(rows):
            cy = di * TILE + row_i
            if cy >= SIZE: break
            cx_start = dj * TILE
            dst_start = cx_start * 3
            n_px = min(w, TILE)
            canvas[cy][dst_start:dst_start + n_px*3] = row[:n_px*3]
        print(f"  tile {ty}/{tx} OK ({w}x{h})")

# Property coords — 179 King Georges Avenue (confirmed via OSM Nominatim)
LAT, LNG = 50.9203478, -1.4458938
Z = 18

def ll_to_tile_exact(lat, lng, z):
    n = 2**z
    x = (lng + 180) / 360 * n
    lat_r = math.radians(lat)
    y = (1 - math.log(math.tan(lat_r) + 1/math.cos(lat_r)) / math.pi) / 2 * n
    return x, y

xe, ye = ll_to_tile_exact(LAT, LNG, Z)
cx_tile, cy_tile = int(xe), int(ye)
xf = xe - cx_tile   # fractional pixel within centre tile
yf = ye - cy_tile

print(f"  Property tile z={Z} x={cx_tile} y={cy_tile}  frac=({xf:.4f},{yf:.4f})")

# Centre tile is grid[1,1] → offset = 1*TILE from top-left
propX = TILE + xf * TILE
propY = TILE + yf * TILE
print(f"  Property canvas pixel ({propX:.1f}, {propY:.1f})")

cos_lat = math.cos(math.radians(LAT))
mpp     = 156543.0 * cos_lat / (2**Z)
lat_pp  = mpp / 111320
lng_pp  = mpp / (111320 * cos_lat)

def ll2px(la, ln):
    x = propX + (ln - LNG) / lng_pp
    y = propY - (la - LAT) / lat_pp
    return int(round(x)), int(round(y))

# Boundary corners: NW, NE, SE, SW
# OSM building bbox: N=50.9203941 S=50.9202855 W=-1.4460114 E=-1.4457968
# Plot = building + 3m front, 20m rear garden, 2m W side, 3m E driveway
corners = [
    (50.9204210, -1.4460399),   # NW: 3m N of bldg face, 2m W of W wall
    (50.9204210, -1.4457541),   # NE: 3m N of bldg face, 3m E (driveway east)
    (50.9201058, -1.4457541),   # SE: 20m S of bldg rear, east side
    (50.9201058, -1.4460399),   # SW: 20m S of bldg rear, west side
]
pts = [ll2px(c[0], c[1]) for c in corners]
print(f"  Boundary pixels: {pts}")

# Meter: east wall (driveway side), at mid-height of building
meterLat = (50.9203941 + 50.9202855) / 2   # midpoint of building N/S
mx, my = ll2px(meterLat, -1.4457968)
print(f"  Meter pixel: ({mx}, {my})")

def set_pixel(canvas, x, y, r, g, b, a=255):
    if 0 <= x < SIZE and 0 <= y < SIZE:
        i = x * 3
        if a < 255:
            o = canvas[y]
            canvas[y][i]   = (o[i]  *(255-a) + r*a) // 255
            canvas[y][i+1] = (o[i+1]*(255-a) + g*a) // 255
            canvas[y][i+2] = (o[i+2]*(255-a) + b*a) // 255
        else:
            canvas[y][i] = r; canvas[y][i+1] = g; canvas[y][i+2] = b

def draw_line(canvas, x0, y0, x1, y1, r, g, b, width=3):
    dx, dy = x1-x0, y1-y0
    steps = max(abs(dx), abs(dy), 1)
    hw = width // 2
    for i in range(steps+1):
        fx = x0 + dx*i/steps
        fy = y0 + dy*i/steps
        for wx in range(-hw, hw+1):
            for wy in range(-hw, hw+1):
                set_pixel(canvas, int(fx)+wx, int(fy)+wy, r, g, b)

def draw_rect_fill(canvas, x0, y0, x1, y1, r, g, b, a=60):
    for y in range(min(y0,y1), max(y0,y1)+1):
        for x in range(min(x0,x1), max(x0,x1)+1):
            set_pixel(canvas, x, y, r, g, b, a)

def draw_circle(canvas, cx, cy, radius, r, g, b):
    for y in range(cy-radius-2, cy+radius+3):
        for x in range(cx-radius-2, cx+radius+3):
            if math.sqrt((x-cx)**2+(y-cy)**2) <= radius:
                set_pixel(canvas, x, y, r, g, b)

print("Drawing annotations...")

# Boundary semi-transparent fill
x_min = min(p[0] for p in pts); x_max = max(p[0] for p in pts)
y_min = min(p[1] for p in pts); y_max = max(p[1] for p in pts)
draw_rect_fill(canvas, x_min, y_min, x_max, y_max, 255, 100, 50, 50)

# Boundary outline (4px red)
for i in range(len(pts)):
    x0, y0 = pts[i]; x1, y1 = pts[(i+1) % len(pts)]
    draw_line(canvas, x0, y0, x1, y1, 230, 59, 18, 4)

# Meter marker: white disc + blue disc
draw_circle(canvas, mx, my, 13, 255, 255, 255)
draw_circle(canvas, mx, my, 11, 26, 115, 232)

# Legend box (bottom-left)
lbx1, lby1, lbx2, lby2 = 8, SIZE-72, 440, SIZE-8
draw_rect_fill(canvas, lbx1, lby1, lbx2, lby2, 255, 255, 255, 230)
for px in range(lbx1, lbx2+1):
    set_pixel(canvas, px, lby1, 160, 160, 160)
    set_pixel(canvas, px, lby2, 160, 160, 160)
for py in range(lby1, lby2+1):
    set_pixel(canvas, lbx1, py, 160, 160, 160)
    set_pixel(canvas, lbx2, py, 160, 160, 160)

print("Encoding PNG...")

def write_png(canvas, size, dest):
    def chunk(name, data):
        crc = zlib.crc32(name + data) & 0xffffffff
        return struct.pack('>I', len(data)) + name + data + struct.pack('>I', crc)
    sig  = b'\x89PNG\r\n\x1a\n'
    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0))
    raw  = bytearray()
    for row in canvas:
        raw.append(0)        # filter type: None
        raw.extend(row)
    idat = chunk(b'IDAT', zlib.compress(bytes(raw), 6))
    iend = chunk(b'IEND', b'')
    with open(dest, 'wb') as f:
        f.write(sig + ihdr + idat + iend)

write_png(canvas, SIZE, DEST)
sz = os.path.getsize(DEST)
print(f"\nSaved: {DEST}")
print(f"Size:  {sz:,} bytes ({sz//1024} KB)")

# Also copy to /tmp for upload tool
import shutil
shutil.copy2(DEST, "/tmp/G99_SatelliteMap_179KGA.png")
print(f"Also at: /tmp/G99_SatelliteMap_179KGA.png")
PYEOF

echo ""
echo "PNG saved to ~/Downloads/G99_SatelliteMap_179KGA.png"
echo "         and /tmp/G99_SatelliteMap_179KGA.png"
echo "Press any key to close."
read -n1
