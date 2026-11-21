"""Force the travel / world map screen (scene 0x1d) from a town state, for checking its graphics.

usage: python3 tools/emu/travel.py   then, within a few seconds, enter any building (e.g.
       tools/emu/hpress.sh /dev/null X on s5_town_map.sav, cursor on the Inn).
The main loop 0x800220b8 calls table 0x800c0d6c[scene byte 0x800e5618]; at the next dispatch the scene
is set to 0x1d (0x80023050). Without a destination the screen runs in its automatic mode and returns at
once, so the branch at 0x80022eac (bnez s0) is nopped in RAM: the cursor mode (choose a town) stays up.
Restart the emulator afterwards (the RAM patch stays)."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from gdbmem import G, wait_break
g = G()
wait_break(g, 0x800220bc, 60)
g.cmd('M800e5618,1:1d')
g.cmd('M80022eac,4:00000000')
g.resume()
