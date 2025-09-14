import sys, json, math
from sexpdata import loads, Symbol

def parse_file(path):
    with open(path, encoding="utf-8") as f:
        return loads(f.read())

def rotate(x, y, angle):
    theta = math.radians(angle)
    return (x*math.cos(theta) - y*math.sin(theta),
            x*math.sin(theta) + y*math.cos(theta))

def parse_symbols(tree):
    lib_pins = {}
    placed = {}
    pin_positions = {}

    # lib_symbols definitions
    # collect pin positions from library symbol definitions (pins can be nested)
    def walk_for_pins(node):
        # yield pin nodes found anywhere under node
        if not isinstance(node, list):
            return
        if node and node[0] == Symbol("pin"):
            yield node
        else:
            for child in node:
                if isinstance(child, list):
                    for p in walk_for_pins(child):
                        yield p

    for node in tree:
        if isinstance(node, list) and node and node[0] == Symbol("lib_symbols"):
            for sym in node[1:]:
                if isinstance(sym, list) and sym and sym[0] == Symbol("symbol"):
                    lib_id = sym[1] if len(sym) > 1 else None
                    if lib_id is None:
                        continue
                    lib_id = str(lib_id)
                    lib_pins.setdefault(lib_id, {})
                    # find all pin nodes anywhere inside this lib symbol
                    for pin_node in walk_for_pins(sym):
                        num, at = None, None
                        for attr in pin_node:
                            if isinstance(attr, list):
                                if attr and attr[0] == Symbol("number") and len(attr) > 1:
                                    num = str(attr[1])
                                elif attr and attr[0] == Symbol("at") and len(attr) > 2:
                                    try:
                                        at = (float(attr[1]), float(attr[2]))
                                    except Exception:
                                        at = None
                        if num and at:
                            lib_pins[lib_id][num] = at
    # done parsing library symbols

    # placed symbols
    for node in tree:
        if isinstance(node, list) and node and node[0] == Symbol("symbol"):
            ref, lib_id, at, value = None, None, (0,0,0), None
            for sub in node:
                if isinstance(sub, list):
                    if sub[0] == Symbol("lib_id"):
                        lib_id = sub[1]
                    elif sub[0] == Symbol("at"):
                        at = (float(sub[1]), float(sub[2]), float(sub[3]) if len(sub)>3 else 0)
                    elif sub[0] == Symbol("property"):
                        if sub[1]=="Reference": ref=sub[2]
                        if sub[1]=="Value": value=sub[2]
            if ref and lib_id in lib_pins:
                cx, cy, rot = at
                pins = {}
                for num,(dx,dy) in lib_pins[lib_id].items():
                    rx, ry = rotate(dx, dy, rot)
                    px, py = round(cx+rx,2), round(cy+ry,2)
                    pins[num]=(px,py)
                    pin_positions[(px,py)] = f"{ref}:{num}"
                placed[ref]={"lib_id":lib_id,"value":value,"pins":pins}
    return placed, pin_positions

def parse_wires_and_labels(tree):
    segments=[]
    labels={}
    for node in tree:
        if isinstance(node, list):
            if node[0]==Symbol("wire"):
                for sub in node:
                    if isinstance(sub,list) and sub[0]==Symbol("pts"):
                        pts=[(round(float(p[1]),2), round(float(p[2]),2)) for p in sub[1:]]
                        for a,b in zip(pts,pts[1:]): segments.append((a,b))
            if node[0] in (Symbol("label"), Symbol("global_label")):
                x=float(node[1]); y=float(node[2])
                labels[(round(x,2),round(y,2))]=node[3]
    return segments, labels

def unionfind(nodes, edges):
    parent={n:n for n in nodes}
    def find(x):
        if parent[x]!=x: parent[x]=find(parent[x])
        return parent[x]
    def union(a,b):
        ra,rb=find(a),find(b)
        if ra!=rb: parent[rb]=ra
    for a,b in edges: union(a,b)
    groups={}
    for n in nodes:
        root=find(n); groups.setdefault(root,[]).append(n)
    return groups

def parse_kicad(path):
    tree=parse_file(path)
    symbols, pin_pos=parse_symbols(tree)
    segs, labels=parse_wires_and_labels(tree)

    # continue without debug prints

    # graph nodes = wire endpoints + pin endpoints + labels
    nodes=set()
    for a,b in segs: nodes|={a,b}
    nodes|=set(pin_pos.keys())
    nodes|=set(labels.keys())

    groups=unionfind(nodes,segs)
    nets={}
    idx=1
    for coords in groups.values():
        pins=[pin_pos[c] for c in coords if c in pin_pos]
        if len(pins)>=2:
            # name
            name=None
            for c in coords:
                if c in labels: name=labels[c]
            if not name: name=f"N${idx}"; idx+=1
            nets[name]=pins
    return {"symbols":{r:{"lib_id":s["lib_id"],"value":s["value"]} for r,s in symbols.items()},
            "nets":nets}

if __name__=="__main__":
    if len(sys.argv)<2:
        print("Usage: python parse_kicad.py <file.kicad_sch>")
        sys.exit(1)
    out=parse_kicad(sys.argv[1])
    with open('schematic_data.json','w',encoding='utf-8') as f:
        json.dump(out,f,indent=2)
    print('Wrote schematic_data.json')
