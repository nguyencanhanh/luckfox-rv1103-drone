#!/usr/bin/env python3
"""Dump pin numbers/names/types of symbols from the KiCad stock libraries.

Usage:  python3 scripts/dump_sym.py Lib:Symbol [Lib:Symbol ...]
"""
import re
import sys
import os

SS = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"
LOCAL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "lib", "symbols")


def tokenize(text):
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif c in "()":
            out.append(c)
            i += 1
        elif c == '"':
            j = i + 1
            buf = []
            while j < n:
                if text[j] == "\\":
                    buf.append(text[j + 1])
                    j += 2
                elif text[j] == '"':
                    break
                else:
                    buf.append(text[j])
                    j += 1
            out.append(("STR", "".join(buf)))
            i = j + 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in "()":
                j += 1
            out.append(("SYM", text[i:j]))
            i = j
    return out


def parse(tokens):
    def build(idx):
        assert tokens[idx] == "("
        node, idx = [], idx + 1
        while tokens[idx] != ")":
            if tokens[idx] == "(":
                child, idx = build(idx)
                node.append(child)
            else:
                node.append(tokens[idx][1])
                idx += 1
        return node, idx + 1
    node, _ = build(0)
    return node


def load(libname):
    for base in (LOCAL, SS):
        p = os.path.join(base, libname + ".kicad_sym")
        if os.path.exists(p):
            return parse(tokenize(open(p).read()))
    raise SystemExit("library not found: " + libname)


def walk(node, tag):
    if isinstance(node, list):
        if node and node[0] == tag:
            yield node
        for c in node:
            yield from walk(c, tag)


def field(node, tag, default=None):
    for c in node:
        if isinstance(c, list) and c and c[0] == tag:
            return c[1]
    return default


def dump(libsym):
    lib, name = libsym.split(":", 1)
    root = load(lib)
    target = None
    for s in root[1:]:
        if isinstance(s, list) and s and s[0] == "symbol" and s[1] == name:
            target = s
            break
    if target is None:
        raise SystemExit("symbol not found: " + libsym)
    print("=" * 62)
    print(libsym)
    base = field(target, "extends")
    if base:
        print("   (extends %s)" % base)
        for s in root[1:]:
            if isinstance(s, list) and s and s[0] == "symbol" and s[1] == base:
                target = target + [c for c in s if isinstance(c, list)
                                   and c and c[0] == "symbol"]
                break
    for p in target:
        if isinstance(p, list) and p and p[0] == "property" and p[1] in (
                "Value", "Footprint", "ki_fp_filters", "Description"):
            print("   %-14s %s" % (p[1], p[2]))
    rows = []
    for pin in walk(target, "pin"):
        etype = pin[1]
        num = field(pin, "number")
        nm = field(pin, "name")
        rows.append((num, nm, etype))
    def key(r):
        try:
            return (0, int(r[0]))
        except ValueError:
            return (1, r[0])
    for num, nm, et in sorted(rows, key=key):
        print("   %-4s %-18s %s" % (num, nm, et))
    print("   pin count:", len(rows))


if __name__ == "__main__":
    for a in sys.argv[1:]:
        dump(a)
