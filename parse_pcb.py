import sys, json, math
from sexpdata import loads, Symbol

def parse_file(path):
    with open(path, encoding='utf-8') as f:
        return loads(f.read())

def parse_pcb(tree):
    footprints = {}

    for node in tree:
        if not isinstance(node, list):
            continue
        if node and node[0] == Symbol('footprint'):
            ref = None
            at = (0.0, 0.0, 0.0)
            lib = None
            pads = {}
            # walk children
            for child in node[1:]:
                if not isinstance(child, list):
                    continue
                head = child[0]
                if head == Symbol('property') and len(child) >= 3 and child[1] == 'Reference':
                    ref = child[2]
                elif head == Symbol('at') and len(child) >= 3:
                    # footprint origin: (at x y [rot])
                    try:
                        x = float(child[1]); y = float(child[2])
                        rot = float(child[3]) if len(child) > 3 else 0.0
                        at = (x,y,rot)
                    except Exception:
                        pass
                elif head == Symbol('path') and len(child) >= 2:
                    lib = child[1]
                elif head == Symbol('pad'):
                    # pad can be (pad "1" ... (at x y rot) (net N ...))
                    name = None
                    pad_at = None
                    shape = None
                    net = None
                    for p in child[1:]:
                        if not isinstance(p, list):
                            continue
                        if p[0] == Symbol('at') and len(p) >= 3:
                            try:
                                px = float(p[1]); py = float(p[2]);
                                # ignore pad-level rotation for now
                                pad_at = (px,py)
                            except Exception:
                                pass
                        elif p[0] == Symbol('net') and len(p) >= 2:
                            net = p[1]
                        elif p[0] == Symbol('size') and len(p) >= 3:
                            shape = ('size', float(p[1]), float(p[2]))
                        elif isinstance(p[0], str) or isinstance(p[0], Symbol):
                            # other unknown
                            pass
                    # pad name is the first token after 'pad'
                    if len(child) >= 2:
                        raw = child[1]
                        if isinstance(raw, str):
                            name = raw
                        else:
                            try:
                                name = str(raw)
                            except Exception:
                                name = None
                    if name and pad_at:
                        # absolute pad coords = footprint at + pad offset
                        fx,fy,fr = at
                        ax = round(fx + pad_at[0], 4)
                        ay = round(fy + pad_at[1], 4)
                        pads[name] = { 'at': [ax, ay], 'net': net, 'shape': shape }
            if ref:
                footprints[ref] = { 'lib': lib, 'at': list(at), 'pads': pads }
    return footprints

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python parse_pcb.py <file.kicad_pcb>')
        sys.exit(1)
    tree = parse_file(sys.argv[1])
    out = parse_pcb(tree)
    with open('footprint_data.json','w',encoding='utf-8') as f:
        json.dump(out,f,indent=2)
    print('Wrote footprint_data.json')
