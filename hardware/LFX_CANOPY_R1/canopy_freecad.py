# -*- coding: utf-8 -*-
"""
LFX_CANOPY_R1 - parametric canopy for the LFX_FC_R2 board, built in FreeCAD.

Run inside FreeCAD 1.x (Macro > Execute, or through the freecad-mcp addon's
RPC server).  It

  1. builds the canopy: a hollow shell with uniform 1.2 mm walls
     (makeThickness), rounded edges, four M3 posts that land on the board's
     39 x 39 mm holes, a camera window, USB-C access for flashing the
     Luckfox, side slots for every lead, vent slots over the Luckfox, and a
     0.8 mm pocket in the roof for a 25 x 25 mm GNSS patch with a cable hole
  2. builds what it covers: the board from its KiCad STEP export (step/,
     made by kicad-cli pcb export step) plus stand-ins for the parts with no
     3D model (Luckfox module and its sockets, camera, Lierda modem,
     standoffs)
  3. checks the canopy against all of it: any common volume is a collision
  4. exports canopy.stl (print) and canopy.step, and renders images

Coordinates follow the KiCad STEP export: X right, Y = -KiCad y (so the
camera / "FWD" edge is -Y), Z up.  The board centre (KiCad 25, 25) is moved
to the origin and Z = 0 is the top of the frame (LFX_FRAME_R1).
"""

import os

import FreeCAD as App
import Part
import Mesh
import MeshPart

try:
    HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:                     # exec'd through RPC: no __file__
    HERE = LFX_CANOPY_DIR             # noqa: F821 - set by the caller

STEP_DIR = os.path.join(HERE, "step")
V = App.Vector

# ---- the stack (mm) --------------------------------------------------------
FC_BOTTOM = 8.0               # 8 mm standoffs on the frame: the bottom
                              # carries the modem and a 5 mm buck inductor
PCB_T = 1.6
FC_TOP = FC_BOTTOM + PCB_T
SOCKET_H = 8.5                # female headers under the Luckfox
LF_PCB_T = 1.0
LF_BOTTOM = FC_TOP + SOCKET_H
USB_W, USB_H, USB_D = 9.0, 3.2, 7.4
LUCKFOX_TOP = LF_BOTTOM + LF_PCB_T + USB_H          # 22.3
HOLE = 19.5
BOARD_C = 25.0                # board centre in KiCad coordinates (50 x 50)

# ---- the shell -------------------------------------------------------------
WALL = 1.2
IN_X = 28.0                   # inner half width (3 mm past the board edge)
IN_REAR = 26.0                # inner face behind the board (+Y side)
IN_FRONT = 32.0               # inner face of the camera wall (-Y side)
SKIRT_Z = 1.6
HEADROOM = 1.5
R_VERT = 6.0                  # vertical edge radius
R_TOP = 3.0                   # roof edge radius

# ---- camera: Luckfox SC3336 (B), 25 x 24 x 18 mm ---------------------------
CAM_W, CAM_H, CAM_PCB = 25.0, 24.0, 1.6
CAM_Z0 = 2.0
LENS_D = 16.0
LENS_OD, LENS_L = 14.0, 13.0  # barrel stand-in for the fit check

POST_OD, POST_ID = 6.4, 3.4


def ky(y):
    """KiCad y (from the board's rear edge) -> model Y"""
    return BOARD_C - y


def box(x0, y0, z0, x1, y1, z1):
    """axis-aligned box between two corners, in any order"""
    return Part.makeBox(abs(x1 - x0), abs(y1 - y0), abs(z1 - z0),
                        V(min(x0, x1), min(y0, y1), min(z0, z1)))


def cyl(r, h, base, axis=V(0, 0, 1)):
    return Part.makeCylinder(r, h, base, axis)


def slot(x0, x1, y, z0, z1, depth_y):
    """rounded vent slot along Z through a wall normal to X"""
    w = x1 - x0
    s = box(x0, y - depth_y, z0, x1, y + depth_y, z1)
    try:
        s = s.makeFillet(w / 2 - 0.01, [e for e in s.Edges
                                         if abs(e.Vertexes[0].Point.y
                                                - e.Vertexes[-1].Point.y) > 1])
    except Exception:
        pass
    return s


def canopy(with_gnss=True):
    stack_top = LUCKFOX_TOP
    # the roof's inner edge rounding (R_TOP - WALL) must clear the top of
    # the camera board, which sits against the front wall
    roof_in = max(stack_top + HEADROOM,
                  CAM_Z0 + CAM_H + (R_TOP - WALL) + 0.5)
    roof_out = roof_in + WALL
    top_board = FC_TOP

    # solid outer body, rounded, then hollowed by removing its bottom face
    x0, x1 = -IN_X - WALL, IN_X + WALL
    yf, yr = -IN_FRONT - WALL, IN_REAR + WALL
    body = box(x0, yf, SKIRT_Z, x1, yr, roof_out)
    vert = [e for e in body.Edges
            if abs(e.Vertexes[0].Point.z - e.Vertexes[-1].Point.z) > 1]
    body = body.makeFillet(R_VERT, vert)
    top = [e for e in body.Edges
           if all(abs(v.Point.z - roof_out) < 1e-6 for v in e.Vertexes)]
    body = body.makeFillet(R_TOP, top)
    bottom = [f for f in body.Faces
              if abs(f.CenterOfMass.z - SKIRT_Z) < 1e-6]
    shell = body.makeThickness(bottom, -WALL, 1e-3)

    # posts from the roof onto the top board, M3 clearance through them
    for sx in (-1, 1):
        for sy in (-1, 1):
            shell = shell.fuse(cyl(POST_OD / 2, roof_in - top_board + 0.5,
                                   V(sx * HOLE, sy * HOLE, top_board)))
    for sx in (-1, 1):
        for sy in (-1, 1):
            shell = shell.cut(cyl(POST_ID / 2, roof_out - top_board + 4,
                                  V(sx * HOLE, sy * HOLE, top_board - 1)))

    # camera: chamfered lens window and a locating rim inside the front wall
    cz = CAM_Z0 + CAM_H / 2
    lens = cyl(LENS_D / 2, WALL + 4, V(0, yf - 1, cz), V(0, 1, 0))
    shell = shell.cut(lens)
    rim = box(-CAM_W / 2 - 1.6, -IN_FRONT, CAM_Z0 - 1.6,
              CAM_W / 2 + 1.6, -IN_FRONT + 1.5, CAM_Z0 + CAM_H + 1.6)
    rim = rim.cut(box(-CAM_W / 2 - 0.2, -IN_FRONT - 1, CAM_Z0 - 0.2,
                      CAM_W / 2 + 0.2, -IN_FRONT + 2, CAM_Z0 + CAM_H + 0.2))
    shell = shell.fuse(rim)
    try:
        ring = [e for e in shell.Edges
                if hasattr(e.Curve, "Radius")
                and abs(e.Curve.Radius - LENS_D / 2) < 1e-3
                and abs(e.Vertexes[0].Point.y - yf) < 1e-3]
        if ring:
            shell = shell.makeChamfer(0.8, ring)
    except Exception:
        pass

    # rear: USB-C, so the Luckfox can be flashed with the canopy on
    usb_z = LF_BOTTOM + LF_PCB_T + USB_H / 2
    plug = box(-7.0, IN_REAR - 1, usb_z - 4.5, 7.0, yr + 1, usb_z + 4.5)
    shell = shell.cut(plug)

    # behind the camera hood the walls stop 1 mm under the FC: below it the
    # stack is open anyway (ESC leads, arms), and a skirt cut up by every
    # lead would print as thin, fragile strips
    shell = shell.cut(box(x0 - 1, ky(2 * BOARD_C), 0.0, x1 + 1, yr + 1,
                          FC_BOTTOM - 1.0))
    # both sides, behind the hood: open up to 4.5 mm over the FC, one clean
    # slot for the RC receiver (J4), buzzer (J6) and ESC leads (corner pads)
    # - separate notches left 0.5 mm fingers of wall between them
    for sx in (-1, 1):
        shell = shell.cut(box(sx * IN_X - 3, ky(2 * BOARD_C) - 4.0, 0,
                              sx * IN_X + 3, yr + 1, FC_TOP + 4.5))
    # rear corners: ESC leads to the rear motor pads (KiCad y 2.2)
    for sx in (-1, 1):
        shell = shell.cut(box(sx * IN_X - 7, ky(2.2) - 7, 0,
                              sx * IN_X + 7, yr + 1, FC_TOP + 4.5))
    # vent slots both sides, over the Luckfox (it runs warm)
    for sx in (-1, 1):
        for i in range(3):
            y = ky(4.0) - i * 4.5
            shell = shell.cut(slot(sx * IN_X - 3 if sx > 0 else -IN_X - 3,
                                   sx * IN_X + 3 if sx > 0 else -IN_X + 3,
                                   y, LF_BOTTOM - 1.0, LUCKFOX_TOP - 1.0,
                                   1.1))

    if with_gnss:
        # GNSS patch pocket: the roof is thickened 1 mm on the inside there
        # and a 0.8 mm recess cut from the outside - the outer roof stays
        # flat, so the canopy still prints roof-down without supports
        shell = shell.fuse(box(-14.0, -14.0, roof_in - 1.0, 14.0, 14.0,
                               roof_in + 0.01))
        shell = shell.cut(box(-12.8, -12.8, roof_out - 0.8, 12.8, 12.8,
                              roof_out + 1.0))
        shell = shell.cut(cyl(2.0, WALL + 4, V(0, 0, roof_in - 2)))

    return shell.removeSplitter()


def stack():
    """The board and stand-ins, as (name, shape, colour)."""
    out = []
    p = os.path.join(STEP_DIR, "LFX_FC_R2.step")
    if os.path.exists(p):
        s = Part.read(p)
        s.translate(V(-BOARD_C, BOARD_C, FC_BOTTOM))
        out.append(("LFX_FC_R2", s, (0.10, 0.45, 0.20)))
    # Luckfox Pico Mini B on two 1x11 sockets (MOD1 at KiCad 25, 14.093)
    for sx in (-1, 1):
        out.append(("socket", box(sx * 8.89 - 1.27, ky(14.093 - 14.0), FC_TOP,
                                  sx * 8.89 + 1.27, ky(14.093 + 14.0),
                                  LF_BOTTOM), (0.1, 0.1, 0.1)))
    lf = box(-10.5, ky(0.0), LF_BOTTOM, 10.5, ky(28.16), LF_BOTTOM + LF_PCB_T)
    usb = box(-USB_W / 2, ky(-0.6), LF_BOTTOM + LF_PCB_T,
              USB_W / 2, ky(-0.6 + USB_D), LUCKFOX_TOP)
    out.append(("luckfox", lf.fuse(usb), (0.05, 0.25, 0.6)))
    # Lierda NT26-KCN E under the front half (U8 at KiCad 25, 39.2)
    out.append(("lierda", box(-7.9, ky(39.2 - 8.85), FC_BOTTOM - 2.4,
                              7.9, ky(39.2 + 8.85), FC_BOTTOM),
                (0.75, 0.75, 0.78)))
    # camera on the inside of the front wall
    cam = box(-CAM_W / 2, -IN_FRONT, CAM_Z0, CAM_W / 2, -IN_FRONT + CAM_PCB,
              CAM_Z0 + CAM_H)
    cam = cam.fuse(cyl(LENS_OD / 2, LENS_L,
                       V(0, -IN_FRONT, CAM_Z0 + CAM_H / 2), V(0, -1, 0)))
    out.append(("camera", cam, (0.15, 0.15, 0.15)))
    for sx in (-1, 1):
        for sy in (-1, 1):
            out.append(("standoff", cyl(2.5, FC_BOTTOM,
                                        V(sx * HOLE, sy * HOLE, 0.0)),
                        (0.8, 0.8, 0.8)))
    return out


def collisions(shell, parts):
    hits = []
    for name, s, _c in parts:
        try:
            v = shell.common(s).Volume
        except Exception:
            v = -1
        if v > 0.01:
            hits.append((name, round(v, 2)))
    return hits


def build(render=True):
    tag = "r2"
    doc_name = "LFX_Canopy_" + tag
    if doc_name in App.listDocuments():
        App.closeDocument(doc_name)
    doc = App.newDocument(doc_name)
    shell = canopy()
    parts = stack()

    obj = doc.addObject("Part::Feature", "Canopy")
    obj.Shape = shell
    for i, (name, s, colour) in enumerate(parts):
        o = doc.addObject("Part::Feature", "%s_%d" % (name, i))
        o.Shape = s
        if App.GuiUp:
            o.ViewObject.ShapeColor = colour
    doc.recompute()

    stl = os.path.join(HERE, "canopy.stl")
    mesh = MeshPart.meshFromShape(Shape=shell, LinearDeflection=0.03,
                                  AngularDeflection=0.25, Relative=False)
    mesh.write(stl)
    Part.export([obj], os.path.join(HERE, "canopy.step"))

    hits = collisions(shell, parts)
    bb = shell.BoundBox
    print("%s: %.1f x %.1f x %.1f mm, %.2f cm3 (PETG %.1f g solid), "
          "%d facets, collisions: %s"
          % (tag, bb.XLength, bb.YLength, bb.ZLength, shell.Volume / 1000,
             shell.Volume / 1000 * 1.27, mesh.CountFacets, hits or "none"))

    if render and App.GuiUp:
        import FreeCADGui as Gui
        vo = obj.ViewObject
        vo.ShapeColor = (0.95, 0.55, 0.10)
        view = Gui.getDocument(doc_name).activeView()
        for name, transp in (("closed", 0), ("fit", 70)):
            vo.Transparency = transp
            view.viewIsometric()
            view.fitAll()
            view.saveImage(os.path.join(HERE, "img", "canopy_%s_%s.png"
                                        % (tag, name)), 1600, 1200, "White")
        # and from the rear-left: the USB-C window, the side slots
        vo.Transparency = 0
        view.viewIsometric()
        view.setCameraOrientation(App.Rotation(V(0, 0, 1), 180).multiply(
            view.getCameraOrientation()))
        view.fitAll()
        view.saveImage(os.path.join(HERE, "img", "canopy_%s_rear.png" % tag),
                       1600, 1200, "White")
        vo.Visibility = True
    return hits


os.makedirs(os.path.join(HERE, "img"), exist_ok=True)
RESULT = build()
