# -*- coding: utf-8 -*-
"""
LFX_FRAME_R1 - 3D-printable X frame for the LFX_FC_R2 board, 3" props,
1103 / 1104 motors, four separate ESCs.  Built in FreeCAD 1.x (run as a
macro or through the freecad-mcp addon's RPC server).

  * centre plate 3 mm, the board on 8 mm M3 standoffs straight onto its
    39 x 39 mm holes, battery strap slots, lightening holes, two holes at
    the rear for antenna tubes / zip ties
  * four 4 mm arms, true X; the motor spacing is not guessed: the arms are
    lengthened until a 3" prop disc (plus 2 mm) clears the LFX_CANOPY_R1
    canopy - the canopy is ~30 mm tall, right in the prop plane
  * motor mounts slotted from r 3.3 to 4.5 mm for M2: both the 1104
    (4 x M2 on 9 mm) and the smaller 1103 patterns fit
  * ESCs zip-tied on the arms, outside the canopy

Writes frame.stl / frame.step and assembly renders into img/.  Coordinates
as LFX_CANOPY_R1: board centre at the origin, front ("FWD", camera) is -Y,
Z = 0 the top face of the frame.
"""

import math
import os

import FreeCAD as App
import Part
import MeshPart

try:
    HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:                     # exec'd through RPC: no __file__
    HERE = LFX_FRAME_DIR              # noqa: F821 - set by the caller
CANOPY_DIR = os.path.join(os.path.dirname(HERE), "LFX_CANOPY_R1")
V = App.Vector

PLATE_T, ARM_T = 3.0, 4.0
PLATE_X = 29.6                        # canopy outer half width 29.2 + 0.4
PLATE_FRONT, PLATE_REAR = -33.6, 27.6 # canopy outer -33.2 .. +27.2
HOLE = 19.5                           # stack standoffs, 39 x 39 mm
ARM_W = 11.0
MOUNT_D = 17.0                        # motor pad
MOTOR_SLOT = (3.3, 4.5, 2.2)          # r0, r1, width (M2)
SHAFT_D = 6.0
PROP_D = 76.2                         # 3"
PROP_MARGIN = 2.0
MOTOR_D, MOTOR_H = 14.0, 11.5         # 1104 stand-in (bell + stator)
PROP_Z0 = MOTOR_H + 1.0               # prop disc band over the arm top
PROP_Z1 = PROP_Z0 + 6.0
ESC_L, ESC_W, ESC_H = 24.0, 12.0, 4.0 # 12 A BLHeli_S class


def box(x0, y0, z0, x1, y1, z1):
    return Part.makeBox(abs(x1 - x0), abs(y1 - y0), abs(z1 - z0),
                        V(min(x0, x1), min(y0, y1), min(z0, z1)))


def cyl(r, h, base, axis=V(0, 0, 1)):
    return Part.makeCylinder(r, h, base, axis)


def canopy_shapes():
    out = []
    for name in ("canopy",):
        p = os.path.join(CANOPY_DIR, name + ".step")
        if os.path.exists(p):
            out.append((name, Part.read(p)))
    return out


def prop_disc(a, sx, sy):
    return cyl(PROP_D / 2 + PROP_MARGIN, PROP_Z1 - PROP_Z0,
               V(sx * a, sy * a, PROP_Z0))


def motor_spacing(canopies):
    """Smallest motor offset a (motors at +-a, +-a) whose prop discs clear
    every canopy variant and each other."""
    a = 40.0
    while a < 90.0:
        ok = (2 * a - (PROP_D + 2 * PROP_MARGIN)) > 0          # neighbours
        for _n, c in canopies:
            if not ok:
                break
            for sx in (-1, 1):
                for sy in (-1, 1):
                    if c.common(prop_disc(a, sx, sy)).Volume > 1e-3:
                        ok = False
        if ok:
            return a
        a += 0.5
    raise RuntimeError("no clear motor spacing below 90 mm")


def arm(a, sx, sy):
    """Arm from the plate centre to the motor at (sx*a, sy*a), plus its pad."""
    L = a * math.sqrt(2)
    b = box(0, -ARM_W / 2, -ARM_T, L, ARM_W / 2, 0)
    b.rotate(V(0, 0, 0), V(0, 0, 1), math.degrees(math.atan2(sy, sx)))
    pad = cyl(MOUNT_D / 2, ARM_T, V(sx * a, sy * a, -ARM_T))
    return b.fuse(pad)


def motor_cuts(a, sx, sy):
    c = cyl(SHAFT_D / 2, ARM_T + 2, V(sx * a, sy * a, -ARM_T - 1))
    r0, r1, w = MOTOR_SLOT
    for k in range(4):
        t = math.radians(45 + 90 * k)
        s = box(r0, -w / 2, -ARM_T - 1, r1, w / 2, 1)
        s = s.fuse(cyl(w / 2, ARM_T + 2, V(r0, 0, -ARM_T - 1)))
        s = s.fuse(cyl(w / 2, ARM_T + 2, V(r1, 0, -ARM_T - 1)))
        s.rotate(V(0, 0, 0), V(0, 0, 1), math.degrees(t))
        s.translate(V(sx * a, sy * a, 0))
        c = c.fuse(s)
    return c


def frame(a):
    plate = box(-PLATE_X, PLATE_FRONT, -PLATE_T, PLATE_X, PLATE_REAR, 0)
    vert = [e for e in plate.Edges
            if abs(e.Vertexes[0].Point.z - e.Vertexes[-1].Point.z) > 1]
    plate = plate.makeFillet(5.0, vert)
    f = plate
    for sx in (-1, 1):
        for sy in (-1, 1):
            f = f.fuse(arm(a, sx, sy))
    # stack standoffs
    for sx in (-1, 1):
        for sy in (-1, 1):
            f = f.cut(cyl(1.6, ARM_T + 2, V(sx * HOLE, sy * HOLE, -ARM_T - 1)))
    # battery strap: two 16 x 2.5 mm slots for a 15 mm strap, under the FC
    for sx in (-1, 1):
        s = box(sx * 10.0 - 1.25, -8.0, -ARM_T - 1, sx * 10.0 + 1.25, 8.0, 1)
        f = f.cut(s)
    # lightening, clear of the standoffs, strap slots and camera seat
    for y in (-15.0, 15.0):
        f = f.cut(cyl(4.5, ARM_T + 2, V(0, y, -ARM_T - 1)))
    for sx in (-1, 1):
        f = f.cut(cyl(3.0, ARM_T + 2, V(sx * 20.5, 0.0, -ARM_T - 1)))
    # rear: antenna tubes / zip ties
    for sx in (-1, 1):
        f = f.cut(cyl(1.6, ARM_T + 2, V(sx * 6.0, 24.5, -ARM_T - 1)))
    for sx in (-1, 1):
        for sy in (-1, 1):
            f = f.cut(motor_cuts(a, sx, sy))
    return f.removeSplitter()


def build():
    canopies = canopy_shapes()
    a = math.ceil(motor_spacing(canopies))
    fr = frame(a)

    doc_name = "LFX_Frame"
    if doc_name in App.listDocuments():
        App.closeDocument(doc_name)
    doc = App.newDocument(doc_name)
    fo = doc.addObject("Part::Feature", "Frame")
    fo.Shape = fr

    MeshPart.meshFromShape(Shape=fr, LinearDeflection=0.03,
                           AngularDeflection=0.25,
                           Relative=False).write(os.path.join(HERE,
                                                              "frame.stl"))
    Part.export([fo], os.path.join(HERE, "frame.step"))

    # assembly stand-ins: motors, ESCs, props, the LTE canopy
    parts = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(("motor", cyl(MOTOR_D / 2, MOTOR_H,
                                       V(sx * a, sy * a, 0)),
                          (0.15, 0.15, 0.18), 0))
            parts.append(("prop", cyl(PROP_D / 2, 1.2,
                                      V(sx * a, sy * a, PROP_Z0 + 2)),
                          (0.2, 0.5, 0.9), 75))
            ang = math.atan2(sy, sx)
            r = a * math.sqrt(2) * 0.55
            e = box(-ESC_L / 2, -ESC_W / 2, 0, ESC_L / 2, ESC_W / 2, ESC_H)
            e.rotate(V(0, 0, 0), V(0, 0, 1), math.degrees(ang))
            e.translate(V(r * math.cos(ang), r * math.sin(ang), 0))
            parts.append(("esc", e, (0.1, 0.35, 0.75), 0))
    for name, c in canopies[:1]:
        parts.append((name, c, (0.95, 0.55, 0.10), 0))
    # battery under the frame, 2S 450 mAh class 58 x 30 x 13 mm
    parts.append(("battery", box(-15, -29, -ARM_T - 13.5, 15, 29,
                                 -PLATE_T - 0.5), (0.85, 0.85, 0.2), 0))

    esc_hits = [round(fr.common(s).Volume, 2) for n, s, _c, _t in parts
                if n == "esc"]
    for i, (name, s, colour, transp) in enumerate(parts):
        o = doc.addObject("Part::Feature", "%s_%d" % (name, i))
        o.Shape = s
        if App.GuiUp:
            o.ViewObject.ShapeColor = colour
            o.ViewObject.Transparency = transp
    doc.recompute()

    bb = fr.BoundBox
    vol = fr.Volume / 1000.0
    print("motor offset a = %d mm (wheelbase %.0f mm), frame %.0f x %.0f x "
          "%.0f mm, %.1f cm3: PETG %.1f g, PLA %.1f g (solid); ESC overlap "
          "with frame %s"
          % (a, 2 * a * math.sqrt(2), bb.XLength, bb.YLength, bb.ZLength,
             vol, vol * 1.27, vol * 1.24, esc_hits))

    if App.GuiUp:
        import FreeCADGui as Gui
        fo.ViewObject.ShapeColor = (0.25, 0.25, 0.28)
        view = Gui.getDocument(doc_name).activeView()
        view.viewIsometric()
        view.fitAll()
        view.saveImage(os.path.join(HERE, "img", "frame_assembly.png"),
                       1600, 1200, "White")
        view.viewTop()
        view.fitAll()
        view.saveImage(os.path.join(HERE, "img", "frame_assembly_top.png"),
                       1600, 1200, "White")
        for o in doc.Objects:
            if o.Name != "Frame":
                o.ViewObject.Visibility = False
        view.viewIsometric()
        view.fitAll()
        view.saveImage(os.path.join(HERE, "img", "frame.png"), 1600, 1200,
                       "White")
        for o in doc.Objects:
            o.ViewObject.Visibility = True
    return a


RESULT = build()
