"""Sculpt a neutral standing human body out of blended rounded cones.

Saves body_highres.obj (smooth, dense) and body_lowpoly.obj (the same shape as
evenly sized triangles, which is what the wire frame is built from).

Runs outside Maya (needs numpy and scikit-image). Units are centimetres, Y is up,
the figure faces +Z and stands on the floor at Y = 0, about 180 cm tall.
Only the figure's left half (x >= 0) is described; the other half is its mirror image.
"""
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from skimage import measure

VOXEL = 1.0  # size of the sampling grid in cm; smaller is smoother and slower
CORNERS = 1100  # how many corner points the low-poly frame has

# Each part: (start point, end point, start radius, end radius, blend, squash)
# blend  = how softly the part melts into what is already there
# squash = (x, y, z) scale that flattens the round shape, e.g. a chest wider than it is deep
PARTS = [
    # torso
    ((0, 96, 0), (0, 112, 0), 15.4, 12.8, 0, (1, 1, 0.68)),      # pelvis up to waist
    ((0, 112, 0), (0, 128, 0), 12.8, 15.0, 4, (1, 1, 0.64)),     # waist up to ribs
    ((0, 128, 0), (0, 141, 0), 15.0, 14.0, 4, (1, 1, 0.64)),     # chest
    ((0, 146.5, -1), (16.5, 144.5, -1), 5.8, 5.2, 5, (1, 1, 1)),       # shoulder line
    ((6.5, 91, -4), (6.5, 94, -4), 8.0, 8.0, 5, (1, 1, 1)),      # seat
    # neck and head
    ((0, 148, -1), (0, 160, 0.5), 5.4, 4.9, 4, (1, 1, 1)),
    ((0, 170, 0), (0, 162.5, 2.0), 8.2, 6.2, 2.5, (0.93, 1, 1.08)),
    # arm, hanging a little away from the body
    ((19.5, 143, -1), (28, 115, -2), 5.3, 4.0, 2.5, (1, 1, 1)),      # upper arm
    ((28, 115, -2), (33, 90, 1), 4.2, 2.8, 2, (1, 1, 1)),      # forearm
    ((33.3, 87, 1.3), (35, 75, 3.2), 4.4, 3.1, 1.5, (0.5, 1, 1)),  # hand, flat like a mitten
    # leg
    ((9.6, 90, 0), (10.5, 50, 1), 9.3, 6.0, 4, (1, 1, 1)),       # thigh
    ((10.5, 50, 1), (11.5, 9, -1), 5.9, 3.6, 2, (1, 1, 1)),      # shin
    ((10.9, 42, -2.2), (11.3, 28, -1.8), 5.6, 4.0, 2, (1, 1, 1)),  # calf
    ((11.5, 4.2, -3), (12.6, 2.9, 14.5), 4.2, 2.9, 2, (1, 1, 1)),  # foot
]


def round_cone(p, a, b, r1, r2):
    """Distance from points p to a cone with rounded ends (after Inigo Quilez's sdRoundCone)."""
    ba = b - a
    l2 = ba @ ba
    rr = r1 - r2
    a2 = l2 - rr * rr
    il2 = 1.0 / l2
    pa = p - a
    y = pa @ ba
    z = y - l2
    x2 = ((pa * l2 - np.outer(y, ba)) ** 2).sum(axis=1)
    y2 = y * y * l2
    z2 = z * z * l2
    k = np.sign(rr) * rr * rr * x2
    far_end = np.sqrt(x2 + z2) * il2 - r2
    near_end = np.sqrt(x2 + y2) * il2 - r1
    side = (np.sqrt(x2 * a2 * il2) + y * rr) * il2 - r1
    return np.where(np.sign(z) * a2 * z2 > k, far_end, np.where(np.sign(y) * a2 * y2 < k, near_end, side))


def smooth_min(d1, d2, k):
    if k <= 0:
        return np.minimum(d1, d2)
    h = np.clip(0.5 + 0.5 * (d2 - d1) / k, 0, 1)
    return d2 * (1 - h) + d1 * h - k * h * (1 - h)


def body_distance(p):
    p = p.copy()
    p[:, 0] = np.abs(p[:, 0])  # mirror left to right
    d = None
    for a, b, r1, r2, blend, squash in PARTS:
        s = np.array(squash, dtype=float)
        part = round_cone(p / s, np.array(a, float) / s, np.array(b, float) / s, r1, r2) * s.min()
        d = part if d is None else smooth_min(d, part, blend)
    return np.maximum(d, -p[:, 1])  # flat soles on the floor


def even_triangles(verts, faces, count, rounds=2):
    """Rebuild a dense mesh as roughly `count` corners joined by evenly sized triangles.

    Picks well-spread corner points, gives every dense vertex to its nearest corner
    (measured along the surface, so the two sides of a thin hand stay separate),
    then joins corners whose patches meet.
    """
    # Start with corners spread as far from each other as possible
    seeds = [int(np.argmax(verts[:, 1]))]
    nearest = np.linalg.norm(verts - verts[seeds[0]], axis=1)
    for _ in range(count - 1):
        seeds.append(int(np.argmax(nearest)))
        nearest = np.minimum(nearest, np.linalg.norm(verts - verts[seeds[-1]], axis=1))
    seeds = np.array(seeds)

    # The surface as a graph, so distances can be measured along it
    pairs = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    lengths = np.linalg.norm(verts[pairs[:, 0]] - verts[pairs[:, 1]], axis=1)
    graph = coo_matrix((lengths, (pairs[:, 0], pairs[:, 1])), shape=(len(verts), len(verts))).tocsr()

    for step in range(rounds + 1):
        _, _, owner_vertex = dijkstra(graph, directed=False, indices=seeds, min_only=True, return_predecessors=True)
        patch = np.searchsorted(np.sort(seeds), owner_vertex)
        seeds = np.sort(seeds)
        if step == rounds:
            break
        # Nudge each corner to the middle of its patch, which evens out the spacing
        moved = []
        for i in range(len(seeds)):
            members = np.flatnonzero(patch == i)
            middle = verts[members].mean(axis=0)
            moved.append(members[np.argmin(np.linalg.norm(verts[members] - middle, axis=1))])
        seeds = np.array(moved)

    # A dense triangle touching three different patches becomes one low-poly triangle
    corners = patch[faces]
    meets = (corners[:, 0] != corners[:, 1]) & (corners[:, 1] != corners[:, 2]) & (corners[:, 0] != corners[:, 2])
    seen, triangles = set(), []
    for tri in corners[meets]:
        key = tuple(sorted(tri))
        if key not in seen:
            seen.add(key)
            triangles.append(tri)
    return verts[seeds], np.array(triangles)


def save_obj(path, verts, faces):
    with open(path, "w") as f:
        for v in verts:
            f.write(f"v {v[0]:.3f} {v[1]:.3f} {v[2]:.3f}\n")
        for t in faces + 1:
            f.write(f"f {t[0]} {t[1]} {t[2]}\n")


def main():
    xs = np.arange(-42, 42 + VOXEL, VOXEL)
    ys = np.arange(-3, 184 + VOXEL, VOXEL)
    zs = np.arange(-22, 24 + VOXEL, VOXEL)
    grid = np.stack(np.meshgrid(xs, ys, zs, indexing="ij"), axis=-1).reshape(-1, 3)
    field = body_distance(grid).reshape(len(xs), len(ys), len(zs))
    verts, faces, _, _ = measure.marching_cubes(field, level=0.0, spacing=(VOXEL, VOXEL, VOXEL))
    verts += np.array([xs[0], ys[0], zs[0]])

    save_obj("body_highres.obj", verts, faces)
    low_verts, low_faces = even_triangles(verts, faces, CORNERS)
    save_obj("body_lowpoly.obj", low_verts, low_faces)
    edge_count = len({tuple(sorted(e)) for t in low_faces for e in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0]))})
    print(f"low-poly: {len(low_verts)} corners, {len(low_faces)} triangles, {edge_count} edges "
          f"(closed surface would have {len(low_faces) * 3 // 2})")
    lo, hi = verts.min(axis=0), verts.max(axis=0)
    print(f"{len(verts)} verts, {len(faces)} triangles")
    print("size (cm): x %.1f..%.1f  y %.1f..%.1f  z %.1f..%.1f" % (lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]))


if __name__ == "__main__":
    main()
