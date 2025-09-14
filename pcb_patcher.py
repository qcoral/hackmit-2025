#!/usr/bin/env python3
"""Utilities to convert grid trails back to PCB coordinates and append tracks to a .kicad_pcb file.

Assumptions:
- GRID_W, GRID_H, MAP_PADDING, and padding must match the values used by `snake_game.py`.
- This script uses `sexpdata` to parse and write the PCB S-expression.
"""
import json
import shutil
from sexpdata import loads, Symbol
import math
import re

# These must match snake_game.py settings unless you pass custom values
GRID_W = 60
GRID_H = 24
MAP_PADDING = 4
PADDING = 2


def compute_bounds_from_footprints(footprint_path):
    with open(footprint_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    xs = []
    ys = []
    for ref, fp in data.items():
        for pn, pinfo in fp.get('pads', {}).items():
            at = pinfo.get('at')
            if at:
                xs.append(float(at[0]))
                ys.append(float(at[1]))
    if not xs:
        raise ValueError('No pad coordinates found in footprint data')
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    # avoid zero-range
    if abs(maxx-minx) < 1e-6:
        maxx = minx + 1.0
    if abs(maxy-miny) < 1e-6:
        maxy = miny + 1.0
    gw = max(1, GRID_W - PADDING*2 - MAP_PADDING)
    gh = max(1, GRID_H - PADDING*2 - MAP_PADDING)
    return { 'minx': minx, 'maxx': maxx, 'miny': miny, 'maxy': maxy, 'gw': gw, 'gh': gh }


def grid_to_pcb(gx, gy, bounds):
    # inverse of map_to_grid in snake_game
    minx, maxx = bounds['minx'], bounds['maxx']
    miny, maxy = bounds['miny'], bounds['maxy']
    gw, gh = bounds['gw'], bounds['gh']
    # compute normalized fractions
    fx = (gx - PADDING - MAP_PADDING//2) / float(max(1, gw-1))
    fy = (gy - PADDING - MAP_PADDING//2) / float(max(1, gh-1))
    # clamp
    fx = max(0.0, min(1.0, fx))
    fy = max(0.0, min(1.0, fy))
    x = minx + fx * (maxx - minx)
    y = miny + fy * (maxy - miny)
    return (round(x, 4), round(y, 4))


def find_net_name(tree, net_idx):
    for node in tree:
        if isinstance(node, list) and node:
            if node[0] == Symbol('net') and len(node) >= 3:
                try:
                    if int(node[1]) == int(net_idx):
                        return node[2]
                except Exception:
                    pass
    return ''


def append_tracks(kicad_pcb_path, footprint_data_path, net_idx, ordered_grid_points, width_mm=0.5, layer='F.Cu'):
    """Append track segments for the provided ordered grid points (list of (gx,gy)).

    This will create consecutive segments between adjacent points in the list.
    """
    # backup original (keep existing .bak if present)
    shutil.copy(kicad_pcb_path, kicad_pcb_path + '.bak')

    bounds = compute_bounds_from_footprints(footprint_data_path)
    seg_width = float(width_mm)

    # read original file text
    with open(kicad_pcb_path, 'r', encoding='utf-8') as f:
        orig = f.read()

    # try to discover net name by regex in the file: (net <idx> "NAME")
    net_name = ''
    try:
        pat = re.compile(r"\(net\s+%d\s+\"([^\"]*)\"\)" % int(net_idx))
        m = pat.search(orig)
        if m:
            net_name = m.group(1)
    except Exception:
        net_name = ''

    # build textual segment S-expr lines
    seg_lines = []
    for a, b in zip(ordered_grid_points[:-1], ordered_grid_points[1:]):
        ax, ay = grid_to_pcb(a[0], a[1], bounds)
        bx, by = grid_to_pcb(b[0], b[1], bounds)
        line = '\t(segment (start %s %s) (end %s %s) (width %s) (layer "%s") (net %s))' % (
            format(ax, '.4f'), format(ay, '.4f'), format(bx, '.4f'), format(by, '.4f'),
            format(seg_width, '.4f'), layer, int(net_idx))
        seg_lines.append(line)

    if not seg_lines:
        return 0

    # insert before final closing paren of file: remove trailing whitespace, drop one trailing ')' and re-close
    s = orig.rstrip()
    if not s.endswith(')'):
        raise ValueError('Unexpected PCB file format: does not end with )')
    s_no_end = s[:-1].rstrip()
    new_text = s_no_end + '\n' + '\n'.join(seg_lines) + '\n)\n'

    with open(kicad_pcb_path, 'w', encoding='utf-8') as f:
        f.write(new_text)

    # quick parse check
    try:
        loads(new_text)
    except Exception:
        # if parse fails, restore backup and raise
        shutil.copy(kicad_pcb_path + '.bak', kicad_pcb_path)
        raise

    return len(seg_lines)


if __name__ == '__main__':
    print('Utility module; import and call append_tracks(...)')
