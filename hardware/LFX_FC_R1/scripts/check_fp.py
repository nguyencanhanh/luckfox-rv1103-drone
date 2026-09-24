#!/usr/bin/env python3
"""Verify that every footprint in the design exists and that its pad numbers
cover the symbol pins that carry a net.  Run with KiCad's own python:

  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/\
Versions/3.9/bin/python3.9 scripts/check_fp.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import pcbnew                                          # noqa: E402
import design                                          # noqa: E402

STOCK = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"
LOCAL = os.path.join(ROOT, "lib", "footprints")


def fp_dir(libname):
    for base in (LOCAL, STOCK):
        p = os.path.join(base, libname + ".pretty")
        if os.path.isdir(p):
            return p
    return None


def main():
    problems, seen = [], {}
    for c in design.COMPONENTS:
        fp = c["fp"]
        if not fp:
            continue
        lib, name = fp.split(":", 1)
        d = fp_dir(lib)
        if d is None:
            problems.append("%-6s library missing: %s" % (c["ref"], lib))
            continue
        key = (d, name)
        if key not in seen:
            try:
                seen[key] = pcbnew.FootprintLoad(d, name)
            except Exception as e:                      # noqa: BLE001
                seen[key] = None
                problems.append("%-6s load failed %s (%s)" % (c["ref"], fp, e))
                continue
        mod = seen[key]
        if mod is None:
            problems.append("%-6s footprint not found: %s" % (c["ref"], fp))
            continue
        pads = {p.GetNumber() for p in mod.Pads()}
        used = {n for n, net in c["pins"].items() if net}
        missing = used - pads
        if missing:
            problems.append("%-6s %s: pads %s missing (has %s)"
                            % (c["ref"], fp, sorted(missing), sorted(pads)))
    print("components checked:", len(design.COMPONENTS))
    print("unique footprints :", len(seen))
    for p in problems:
        print("  !!", p)
    print("OK" if not problems else "PROBLEMS: %d" % len(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
