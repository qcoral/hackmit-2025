
#!/usr/bin/env python3
"""
Terminal PCB router-snake using `footprint_data.json` and `schematic_data.json`.

Behavior:
- For each net in the schematic, start a snake at one pad of that net.
- The snake must visit all pads in the net sequentially. Its trail becomes a permanent trace.
- If a snake runs into a previously routed trace, the game ends and reports invalid routing.
- Between each net, the program waits for a keypress to continue.
"""

import curses
import json
import time
import os
from collections import deque

DATA_FILE = 'footprint_data.json'
SCHEM_FILE = 'schematic_data.json'
GRID_W = 80
GRID_H = 40
MAP_PADDING = 4  # extra padding around components when mapping
TICK = 0.08

KEY_MAP = {
    curses.KEY_UP: (0,-1),
    curses.KEY_DOWN: (0,1),
    curses.KEY_LEFT: (-1,0),
    curses.KEY_RIGHT: (1,0),
    ord('w'):(0,-1), ord('s'):(0,1), ord('a'):(-1,0), ord('d'):(1,0)
}


def load_pads(path):
    with open(path,'r',encoding='utf-8') as f:
        data = json.load(f)
    pads = []
    for ref,fp in data.items():
        pads_dict = fp.get('pads',{})
        def pad_key(k):
            try: return int(k)
            except Exception: return k
        for p_name in sorted(pads_dict.keys(), key=pad_key):
            at = pads_dict[p_name].get('at', [0,0])
            pads.append((ref,p_name, float(at[0]), float(at[1])))
    return pads


def map_to_grid(pads, width, height, padding=2):
    if not pads:
        return []
    xs = [p[2] for p in pads]
    ys = [p[3] for p in pads]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    if maxx - minx < 1e-6:
        maxx = minx + 1.0
    if maxy - miny < 1e-6:
        maxy = miny + 1.0
    gw = max(1, width - padding*2 - MAP_PADDING)
    gh = max(1, height - padding*2 - MAP_PADDING)
    mapped = []
    for ref,pn,x,y in pads:
        gx = padding + MAP_PADDING//2 + int(round((x - minx) / (maxx - minx) * (gw-1)))
        gy = padding + MAP_PADDING//2 + int(round((y - miny) / (maxy - miny) * (gh-1)))
        mapped.append((ref,pn,gx,gy))
    return mapped


def run(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.keypad(True)

    def countdown(msg_y, msg_x, msg, seconds=5):
        """Show a message and countdown for `seconds` seconds, then return."""
        try:
            for s in range(seconds, 0, -1):
                try:
                    stdscr.addstr(msg_y, msg_x, f"{msg} Continuing in {s}s... ")
                except curses.error:
                    pass
                stdscr.refresh()
                time.sleep(1)
        except Exception:
            # if curses or sleep fails, just return
            pass

    def pause_forever(msg_y, msg_x, msg):
        """Display a message and pause indefinitely (until user kills the program)."""
        try:
            try:
                stdscr.addstr(msg_y, msg_x, msg)
            except curses.error:
                pass
            stdscr.refresh()
            # sleep forever in a loop so terminal stays responsive to signals
            while True:
                time.sleep(1)
        except Exception:
            # if interrupted, just block
            while True:
                time.sleep(1)

    def wait_for_key(msg_y, msg_x, msg):
        """Display `msg` and block until the user presses a key."""
        # flush any pending input first
        stdscr.nodelay(True)
        try:
            while True:
                k = stdscr.getch()
                if k == -1:
                    break
        except Exception:
            pass

        try:
            stdscr.addstr(msg_y, msg_x, msg)
        except curses.error:
            pass
        stdscr.refresh()
        # block for a key
        stdscr.nodelay(False)
        try:
            stdscr.getch()
        except Exception:
            # if getch fails, just return
            pass
        finally:
            stdscr.nodelay(True)

    # check data files
    # regenerate footprint and schematic JSONs by calling the parsers if available
    try:
        # prefer to run local scripts directly
        import subprocess
        subprocess.run(['python3','parse_pcb.py','hackmit_2025.kicad_pcb'], check=False)
        subprocess.run(['python3','parse_sch.py','hackmit_2025.kicad_sch'], check=False)
    except Exception:
        # ignore failures here; we'll check files below
        pass

    if not os.path.exists(DATA_FILE) or not os.path.exists(SCHEM_FILE):
        # no interactive key prompts: show message briefly then exit
        countdown(0, 0, f"Required data files not found: {DATA_FILE} and/or {SCHEM_FILE}", seconds=5)
        return

    pads = load_pads(DATA_FILE)
    mapped = map_to_grid(pads, GRID_W, GRID_H)
    pad_map = {}
    for ref,pn,x,y in mapped:
        pad_map[f"{ref}:{pn}"] = (x,y)
    # reverse mapping: (x,y) -> pad_key
    coord_to_pad = { (x,y): f"{ref}:{pn}" for ref,pn,x,y in mapped }

    with open(SCHEM_FILE,'r',encoding='utf-8') as f:
        schem = json.load(f)
    nets = schem.get('nets', {})

    occupied = {}  # (x,y) -> char
    net_chars = list('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz')
    net_names = list(nets.keys())

    total_nets = len(net_names)
    net_index = 0

    while net_index < total_nets:
        net_name = net_names[net_index]
        pins = nets[net_name]
        coords = []
        for p in pins:
            if p in pad_map:
                coords.append((p, pad_map[p]))
        if not coords:
            net_index += 1
            continue

        ch = net_chars[net_index % len(net_chars)]
        apples = [p for p,_ in coords]

        start_pin = apples[0]
        start_x, start_y = pad_map[start_pin]

        if (start_x,start_y) in occupied:
            # invalid routing: pause indefinitely so user can inspect/kill program
            pause_forever(0, 0, f"Invalid routing detected: start pin for net {net_name} on existing trace. Program paused.")

        # helper to (re)initialize snake state for this net
        def init_snake():
            s = deque()
            for i in range(3):
                x0 = (start_x - i) % GRID_W
                y0 = start_y % GRID_H
                s.append((x0,y0))
            return s, (1,0), set(s), 1, 1

        snake, direction, trail, apple_idx, score = init_snake()

        last_time = time.time()

        while True:
            now = time.time()
            if now - last_time < TICK:
                time.sleep(max(0, TICK - (now-last_time)))
            last_time = time.time()

            try:
                k = stdscr.getch()
            except Exception:
                k = -1
            if k in KEY_MAP:
                nd = KEY_MAP[k]
                if (nd[0] != -direction[0] or nd[1] != -direction[1]):
                    direction = nd
            elif k == ord('q'):
                return

            hx,hy = snake[0]
            nx,ny = hx + direction[0], hy + direction[1]
            nx = (nx + GRID_W) % GRID_W
            ny = (ny + GRID_H) % GRID_H

            # collision with existing routed trace
            if (nx,ny) in occupied:
                # offer restart instead of pausing forever
                try:
                    stdscr.addstr(GRID_H+1, 0, f"Collision: net {net_name} hit existing trace. Press any key to restart this snake, or 'q' to quit.")
                except curses.error:
                    pass
                stdscr.nodelay(False)
                k = stdscr.getch()
                stdscr.nodelay(True)
                if k == ord('q'):
                    return
                # restart snake
                snake, direction, trail, apple_idx, score = init_snake()
                last_time = time.time()
                continue

            # collision with a pad that's not part of the current net
            hit_pad = coord_to_pad.get((nx, ny))
            if hit_pad is not None and hit_pad not in apples:
                try:
                    stdscr.addstr(GRID_H+1, 0, f"Collision: net {net_name} hit pad {hit_pad} not in this net. Press any key to restart this snake, or 'q' to quit.")
                except curses.error:
                    pass
                stdscr.nodelay(False)
                k = stdscr.getch()
                stdscr.nodelay(True)
                if k == ord('q'):
                    return
                snake, direction, trail, apple_idx, score = init_snake()
                last_time = time.time()
                continue

            snake.appendleft((nx,ny))
            trail.add((nx,ny))

            if apple_idx < len(apples):
                target_pin = apples[apple_idx]
                ax,ay = pad_map[target_pin]
            else:
                break

            if (nx,ny) == (ax,ay):
                score += 1
                apple_idx += 1

            # draw
            stdscr.erase()
            for x in range(GRID_W):
                try:
                    stdscr.addch(0, x, '#')
                    stdscr.addch(GRID_H-1, x, '#')
                except curses.error:
                    pass
            for y in range(GRID_H):
                try:
                    stdscr.addch(y, 0, '#')
                    stdscr.addch(y, GRID_W-1, '#')
                except curses.error:
                    pass

            for key,(px,py) in pad_map.items():
                try:
                    stdscr.addch(py, px, '.')
                except curses.error:
                    pass

            for (ox,oy), oc in occupied.items():
                try:
                    stdscr.addch(oy, ox, oc)
                except curses.error:
                    pass

            for (tx,ty) in trail:
                try:
                    stdscr.addch(ty, tx, ch)
                except curses.error:
                    pass

            if apple_idx < len(apples):
                try:
                    stdscr.addch(ay, ax, 'A')
                except curses.error:
                    pass

            try:
                stdscr.addstr(GRID_H, 0, f"Routing net {net_name} ({net_index+1}/{total_nets})  Collected: {score}/{len(apples)}  q=quit")
            except curses.error:
                pass
            stdscr.refresh()

        # mark occupied cells for this net
        for coord in trail:
            occupied[coord] = ch

        # attempt to write traces back to PCB once for this net
        try:
            from pcb_patcher import append_tracks
            # convert trail (set) to an ordered list following snake body order
            ordered = list(snake)  # snake deque head-to-tail covers recent path
            # ensure we include entire trail set in order by extending with any leftover trail points
            trail_set = set(trail)
            for p in reversed(ordered):
                if p in trail_set:
                    trail_set.remove(p)
            remaining = list(trail_set)
            ordered_grid_points = [(p[0], p[1]) for p in ordered] + remaining
            # call patcher (net idx comes from pad net mapping; find from pad_map and schem nets)
            # pick net index by reading first pad's net from footprint JSON
            fp = json.load(open(DATA_FILE,'r',encoding='utf-8'))
            first_pin = apples[0]
            # first_pin format 'REF:PIN'
            ref, pin = first_pin.split(':')
            net_idx = fp.get(ref,{}).get('pads',{}).get(pin,{}).get('net')
            if net_idx is not None:
                appended = append_tracks(os.path.join(os.getcwd(), 'hackmit_2025.kicad_pcb'),
                                         os.path.join(os.getcwd(), DATA_FILE),
                                         net_idx,
                                         ordered_grid_points,
                                         width_mm=0.5,
                                         layer='F.Cu')
                wait_for_key(GRID_H+1, 0, f"Net {net_name} routed and {appended} segments written to PCB. Press any key to continue.")
        except Exception:
            wait_for_key(GRID_H+1, 0, f"Net {net_name} routed. (PCB patching skipped or failed). Press any key to continue.")

        net_index += 1

    stdscr.nodelay(False)
    wait_for_key(GRID_H+1, 0, f"All nets routed successfully. Press any key to exit.")


if __name__ == '__main__':
    curses.wrapper(run)
