#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Print the number of connections the board is still missing.

Exits 0 when the board is fully routed, 1 when it is not, so a build script
can decide whether another autoroute attempt is worth making.
"""

import os
import sys

import pcbnew

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PCB = os.path.join(ROOT, "LFX_FC_R1.kicad_pcb")


def main():
    board = pcbnew.LoadBoard(PCB)
    board.BuildConnectivity()
    n = board.GetConnectivity().GetUnconnectedCount(False)
    print(n)
    return 0 if n == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
