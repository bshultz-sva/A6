"""Build the wire body in the open Maya scene.

Brings in body_lowpoly.obj (made by make_body_shape.py), then turns every edge into a thin glowing rod and every corner into
a small bead. Running it again replaces the previous wire body.

The body is also given five adjustable shapes (trunk, each arm, each leg) so that
body_profile_ui.py can make each part thicker or thinner from saved measurements.
"""
import math
import os
import tempfile

import maya.api.OpenMaya as om
import maya.cmds as cmds

HERE = os.path.dirname(os.path.abspath(__file__))
LOWPOLY_OBJ = os.path.join(HERE, "body_lowpoly.obj")

GROUP = "wireBody_grp"
WIRE_RADIUS = 0.11   # thickness of each rod, in cm
BEAD_RADIUS = 0.32   # size of the bead at each corner
WIRE_COLOR = (0.42, 0.80, 1.0)
SKIN_COLOR = (0.02, 0.10, 0.24)
SKIN_SEE_THROUGH = 0.82  # 0 = solid, 1 = invisible

# --- Body parts in the rest pose (cm) ---
# The figure faces +Z, so its right side is at negative X.
# The centre line of an arm and of a leg at a few heights: (height, x, z, radius).
ARM_LINE = [(150, 19.5, -1.0, 5.3), (143, 19.5, -1.0, 5.3), (115, 28.0, -2.0, 4.1), (90, 33.0, 1.0, 2.8),
            (72, 35.3, 3.4, 2.4)]
LEG_LINE = [(90, 9.6, 0.0, 9.3), (50, 10.5, 1.0, 6.0), (9, 11.5, -1.0, 3.6), (0, 11.5, -1.0, 3.6)]
ARM_FOLLOW = 15.0  # how far the arms move sideways as the trunk widens, per unit of trunk scale
PARTS = ["trunk", "right_arm", "left_arm", "right_leg", "left_leg"]
SHAPE_NODES = {"wireBody_skin": "wireBody_skin_shapes", "wireBody_wires": "wireBody_wires_shapes"}


def import_obj(path, name):
    """Import an OBJ file and return its mesh, renamed."""
    if not cmds.pluginInfo("objExport", query=True, loaded=True):
        cmds.loadPlugin("objExport")
    new_nodes = cmds.file(path, i=True, type="OBJ", ignoreVersion=True, namespace="wireBodyImport",
                          options="mo=0", returnNewNodes=True)
    shape = cmds.ls(new_nodes, type="mesh", long=True)[0]
    transform = cmds.listRelatives(shape, parent=True, fullPath=True)[0]
    transform = cmds.rename(transform, name)
    cmds.namespace(removeNamespace="wireBodyImport", mergeNamespaceWithRoot=True)
    return transform


def perpendiculars(d):
    """Two unit vectors at right angles to direction d and to each other."""
    helper = (0.0, 1.0, 0.0) if abs(d[1]) < 0.9 else (1.0, 0.0, 0.0)
    u = (d[1] * helper[2] - d[2] * helper[1], d[2] * helper[0] - d[0] * helper[2], d[0] * helper[1] - d[1] * helper[0])
    length = math.sqrt(u[0] ** 2 + u[1] ** 2 + u[2] ** 2)
    u = (u[0] / length, u[1] / length, u[2] / length)
    v = (d[1] * u[2] - d[2] * u[1], d[2] * u[0] - d[0] * u[2], d[0] * u[1] - d[1] * u[0])
    return u, v


def write_wire_obj(points, edges, path):
    """Write an OBJ with a three-sided rod along every edge and a bead on every point."""
    verts, faces = [], []

    for a, b in edges:
        pa, pb = points[a], points[b]
        d = (pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2])
        length = math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2)
        if length < 1e-6:
            continue
        u, v = perpendiculars((d[0] / length, d[1] / length, d[2] / length))
        base = len(verts)
        for end in (pa, pb):
            for i in range(3):
                angle = i * 2 * math.pi / 3
                c, s = math.cos(angle) * WIRE_RADIUS, math.sin(angle) * WIRE_RADIUS
                verts.append((end[0] + u[0] * c + v[0] * s, end[1] + u[1] * c + v[1] * s, end[2] + u[2] * c + v[2] * s))
        for i in range(3):
            j = (i + 1) % 3
            faces.append((base + i, base + j, base + 3 + j, base + 3 + i))

    r = BEAD_RADIUS
    for p in points:
        base = len(verts)
        for offset in ((r, 0, 0), (-r, 0, 0), (0, r, 0), (0, -r, 0), (0, 0, r), (0, 0, -r)):
            verts.append((p[0] + offset[0], p[1] + offset[1], p[2] + offset[2]))
        for x in (0, 1):
            for y in (2, 3):
                for z in (4, 5):
                    tri = (x, y, z) if (x + y + z) % 2 == 0 else (x, z, y)
                    faces.append(tuple(base + i for i in tri))

    with open(path, "w") as f:
        for v in verts:
            f.write("v %.4f %.4f %.4f\n" % v)
        for face in faces:
            f.write("f " + " ".join(str(i + 1) for i in face) + "\n")


def smoothstep(start, end, value):
    """0 at start, 1 at end, easing in between. Works with start above end too."""
    t = max(0.0, min(1.0, (value - start) / (end - start)))
    return t * t * (3 - 2 * t)


def along_line(line, height):
    """The (x, z, radius) of an arm or leg centre line at a given height."""
    if height >= line[0][0]:
        return line[0][1:]
    for (y1, *upper), (y2, *lower) in zip(line, line[1:]):
        if height >= y2:
            t = (y1 - height) / (y1 - y2)
            return tuple(a + (b - a) * t for a, b in zip(upper, lower))
    return line[-1][1:]


def part_offsets(point):
    """For one point, how far it moves when each body part is scaled up by 100%.

    Every part grows sideways and front-to-back only, never up or down, so the
    figure's height and the floor contact stay put.
    """
    x, y, z = point
    side = 1.0 if x >= 0 else -1.0
    arm_x, arm_z, arm_r = along_line(ARM_LINE, y)
    leg_x, leg_z, leg_r = along_line(LEG_LINE, y)

    # How much this point belongs to an arm, a leg or the trunk (the three add up to 1 below the neck)
    arm = smoothstep(arm_x - arm_r - 3.0, arm_x - arm_r, abs(x)) * smoothstep(153, 147, y) * smoothstep(66, 70, y)
    below_hips = smoothstep(97, 80, y)
    leg = (1 - arm) * below_hips
    trunk = (1 - arm) * (1 - below_hips) * smoothstep(158, 149, y)  # the neck and head never change

    # Arms: scale about the arm's centre line
    arm_move = (arm * (x - side * arm_x), 0.0, arm * (z - arm_z))
    # Legs: scale away from the inner edge so the thighs don't push through each other; feet stay as they are
    leg *= smoothstep(3, 14, y)
    inner_edge = max(0.0, leg_x - leg_r)
    leg_move = (leg * (x - side * inner_edge), 0.0, leg * (z - leg_z))
    # Trunk: scale about the spine, carry the arms outward with the shoulders,
    # and take the tops of the thighs along so the hips don't end in a ledge
    thigh_top = smoothstep(55, 92, y)
    offsets = {"trunk": (trunk * x + arm * side * ARM_FOLLOW + thigh_top * leg_move[0], 0.0,
                         trunk * z + thigh_top * leg_move[2])}

    nothing = (0.0, 0.0, 0.0)
    offsets["left_arm"], offsets["right_arm"] = (arm_move, nothing) if side > 0 else (nothing, arm_move)
    offsets["left_leg"], offsets["right_leg"] = (leg_move, nothing) if side > 0 else (nothing, leg_move)
    return offsets


def mesh_function(name):
    selection = om.MSelectionList()
    selection.add(name)
    return om.MFnMesh(selection.getDagPath(0))


def add_part_shapes(mesh):
    """Give a mesh one adjustable shape per body part. A shape's value is how much thicker that part is:
    0 leaves it alone, 0.1 is 10% thicker, -0.1 is 10% thinner."""
    rest = [(p.x, p.y, p.z) for p in mesh_function(mesh).getPoints(om.MSpace.kObject)]
    offsets = [part_offsets(p) for p in rest]
    targets = []
    for part in PARTS:
        target = cmds.duplicate(mesh, name=part)[0]
        moved = om.MPointArray([om.MPoint(p[0] + o[part][0], p[1] + o[part][1], p[2] + o[part][2])
                                for p, o in zip(rest, offsets)])
        mesh_function(target).setPoints(moved, om.MSpace.kObject)
        targets.append(target)
    cmds.blendShape(targets, mesh, name=SHAPE_NODES[mesh])
    cmds.delete(targets)


def make_material(name, shader_type, **attrs):
    shader = cmds.shadingNode(shader_type, asShader=True, name=name)
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    for attr, value in attrs.items():
        cmds.setAttr(shader + "." + attr, *value, type="double3")
    return group


def build():
    if cmds.objExists(GROUP):
        cmds.delete(GROUP)
    for leftover in ("wireBody_wire_mat", "wireBody_wire_matSG", "wireBody_skin_mat", "wireBody_skin_matSG"):
        if cmds.objExists(leftover):
            cmds.delete(leftover)

    # Low-poly triangle body
    skin = import_obj(LOWPOLY_OBJ, "wireBody_skin")
    cmds.polySoftEdge(skin, angle=0, constructionHistory=False)  # faceted, so the triangles read clearly

    flat = cmds.xform(skin + ".vtx[*]", query=True, translation=True, worldSpace=True)
    points = [tuple(flat[i:i + 3]) for i in range(0, len(flat), 3)]
    edges = []
    for i in range(cmds.polyEvaluate(skin, edge=True)):
        info = cmds.polyInfo("%s.e[%d]" % (skin, i), edgeToVertex=True)[0].split()
        edges.append((int(info[2]), int(info[3])))

    # Rods and beads
    wire_obj = os.path.join(tempfile.mkdtemp(prefix="wireBody-"), "wires.obj")
    write_wire_obj(points, edges, wire_obj)
    wires = import_obj(wire_obj, "wireBody_wires")

    cmds.sets(wires, edit=True, forceElement=make_material("wireBody_wire_mat", "surfaceShader", outColor=WIRE_COLOR))
    see_through = (SKIN_SEE_THROUGH,) * 3
    cmds.sets(skin, edit=True, forceElement=make_material("wireBody_skin_mat", "lambert", color=SKIN_COLOR,
                                                           transparency=see_through))

    for mesh in (skin, wires):
        add_part_shapes(mesh)

    cmds.group(skin, wires, name=GROUP)
    cmds.select(clear=True)
    height = cmds.exactWorldBoundingBox(GROUP)[4]
    print("Built %s: %d triangles, %d wires, %d corners, %.0f cm tall" % (
        GROUP, cmds.polyEvaluate(skin, triangle=True), len(edges), len(points), height))


if __name__ == "__main__":
    build()
