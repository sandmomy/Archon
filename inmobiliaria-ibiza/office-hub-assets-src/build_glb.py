"""
Builds the sculpted GLB assets used by office-hub-pages/index.html.

Everything is modelled as signed-distance fields (smooth unions of spheres,
ellipsoids, capsules and rounded boxes) and polygonised with marching cubes,
so the result is organic, blended geometry instead of stacked primitives.
Materials are named so the viewer can tint them per module
(BotShell / BotCan / BotGlow / BotEyes / BotDark / Fabric / FabricDark / ...).

    python3 build_glb.py            # writes ../office-hub-pages/assets/*.glb
"""
import os
import sys
import numpy as np
import trimesh
from skimage import measure
import fast_simplification

OUT = os.path.join(os.path.dirname(__file__), "..", "office-hub-pages", "assets")
os.makedirs(OUT, exist_ok=True)

# ---------------------------------------------------------------- SDF toolkit
def grid(lo, hi, voxel):
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    n = np.ceil((hi - lo) / voxel).astype(int) + 1
    xs = [lo[i] + np.arange(n[i]) * voxel for i in range(3)]
    X, Y, Z = np.meshgrid(*xs, indexing="ij")
    P = np.stack([X, Y, Z], -1).astype(np.float32)
    return P, lo, voxel

def length(v): return np.sqrt((v * v).sum(-1))

def sphere(p, c, r): return length(p - np.asarray(c, np.float32)) - r

def ellipsoid(p, c, r):
    q = (p - np.asarray(c, np.float32)) / np.asarray(r, np.float32)
    k0 = length(q); k1 = length(q / np.asarray(r, np.float32))
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-6)

def capsule(p, a, b, r):
    a, b = np.asarray(a, np.float32), np.asarray(b, np.float32)
    pa, ba = p - a, b - a
    h = np.clip((pa @ ba) / (ba @ ba), 0, 1)
    return length(pa - ba[None, None, None, :] * h[..., None]) - r

def rbox(p, c, b, r, rot_x=0.0):
    q = p - np.asarray(c, np.float32)
    if rot_x:
        cs, sn = np.cos(rot_x), np.sin(rot_x)
        y, z = q[..., 1].copy(), q[..., 2].copy()
        q = q.copy(); q[..., 1] = cs * y - sn * z; q[..., 2] = sn * y + cs * z
    q = np.abs(q) - np.asarray(b, np.float32)
    return length(np.maximum(q, 0)) + np.minimum(np.max(q, -1), 0) - r

def torus_x(p, c, R, r):
    """torus whose axis is the local X axis (ring sits in the YZ plane)"""
    q = p - np.asarray(c, np.float32)
    t = np.stack([length(q[..., [1, 2]]) - R, q[..., 0]], -1)
    return length(t) - r

def torus_z(p, c, R, r):
    q = p - np.asarray(c, np.float32)
    t = np.stack([length(q[..., [0, 1]]) - R, q[..., 2]], -1)
    return length(t) - r

def smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b * (1 - h) + a * h - k * h * (1 - h)

def union(*ds): return np.minimum.reduce(list(ds))
def smax(a, b, k): return -smin(-a, -b, k)

def polygonise(field, lo, voxel, target=None, smooth=10, name=""):
    verts, faces, _, _ = measure.marching_cubes(field, level=0.0, spacing=(voxel,) * 3, gradient_direction="ascent")
    verts = verts + lo
    m = trimesh.Trimesh(verts, faces, process=True)
    if smooth:
        trimesh.smoothing.filter_taubin(m, lamb=0.5, nu=-0.53, iterations=smooth)
    if target and len(m.faces) > target:
        v, f = fast_simplification.simplify(m.vertices.astype(np.float64), m.faces.astype(np.int64), target_count=target)
        m = trimesh.Trimesh(v, f, process=True)
        trimesh.smoothing.filter_taubin(m, lamb=0.5, nu=-0.53, iterations=3)
    # sanity: outward orientation (SDF is negative inside)
    out = ((m.triangles_center - m.centroid) * m.face_normals).sum(1).mean()
    if out < 0:
        m.invert()
    print(f"  {name:14s} {len(m.faces):6d} tris  orient={out:+.3f}")
    return m

def material(name, rgb, rough=0.5, metal=0.0, emissive=None):
    mat = trimesh.visual.material.PBRMaterial(
        name=name, baseColorFactor=[*rgb, 255], roughnessFactor=rough, metallicFactor=metal)
    if emissive is not None:
        mat.emissiveFactor = emissive
    return mat

def paint(mesh, mat):
    mesh.visual = trimesh.visual.TextureVisuals(material=mat)
    return mesh

def add(scene, mesh, name, pivot=(0, 0, 0), parent=None):
    """add a mesh as its own node with the pivot at `pivot` (world) so it can be animated"""
    pivot = np.asarray(pivot, float)
    mesh = mesh.copy(); mesh.apply_translation(-pivot)
    T = np.eye(4)
    if parent is None:      # children inherit the parent's pivot translation
        T[:3, 3] = pivot
    scene.add_geometry(mesh, node_name=name, geom_name=name, transform=T, parent_node_name=parent)

# ---------------------------------------------------------------- the bot
def build_bot():
    print("bot")
    vox = 0.009
    P, lo, v = grid((-0.75, -0.05, -0.65), (0.75, 1.95, 0.75), vox)

    HEAD_C = (0, 1.34, 0)
    def head_sdf(p):
        h = ellipsoid(p, HEAD_C, (0.49, 0.44, 0.46))
        jaw = ellipsoid(p, (0, 1.24, 0.06), (0.42, 0.30, 0.40))   # fuller lower face
        return smin(h, jaw, 0.10)
    head = head_sdf(P)

    body = ellipsoid(P, (0, 0.64, 0.0), (0.35, 0.37, 0.31))
    belly = ellipsoid(P, (0, 0.56, 0.05), (0.32, 0.28, 0.29))
    body = smin(body, belly, 0.06)
    neck = capsule(P, (0, 0.85, 0), (0, 1.02, 0), 0.14)
    body = smin(body, neck, 0.06)
    # stubby seated legs
    for s in (-1, 1):
        leg = capsule(P, (s * 0.15, 0.32, 0.12), (s * 0.17, 0.22, 0.34), 0.12)
        foot = ellipsoid(P, (s * 0.17, 0.17, 0.38), (0.13, 0.09, 0.14))
        body = smin(body, smin(leg, foot, 0.05), 0.06)

    arms = {}
    for s, nm in ((-1, "ArmL"), (1, "ArmR")):
        upper = capsule(P, (s * 0.33, 0.74, 0.06), (s * 0.38, 0.62, 0.26), 0.105)
        hand = sphere(P, (s * 0.37, 0.60, 0.33), 0.115)
        arms[nm] = smin(upper, hand, 0.06)

    cans = None
    for s in (-1, 1):
        can = ellipsoid(P, (s * 0.50, 1.32, 0.02), (0.12, 0.22, 0.22))
        cup = ellipsoid(P, (s * 0.44, 1.32, 0.02), (0.08, 0.17, 0.17))
        can = smin(can, cup, 0.04)
        cans = can if cans is None else union(cans, can)
    # headband arches over the crown from can to can (ring in the XY plane)
    band = torus_z(P, (0, 1.36, 0.02), 0.52, 0.045)
    band = smax(band, 1.36 - P[..., 1], 0.02)
    pad = torus_z(P, (0, 1.36, 0.02), 0.52, 0.068)
    pad = smax(pad, 1.74 - P[..., 1], 0.03)
    cans = smin(union(cans, band), pad, 0.03)

    def surface_z(x, y):
        """z of the head surface along +z at (x, y)"""
        zs = np.linspace(0.0, 0.7, 700, dtype=np.float32)
        pts = np.stack([np.full_like(zs, x), np.full_like(zs, y), zs], -1)[None, None]
        d = head_sdf(pts)[0, 0]
        inside = np.where(d < 0)[0]
        return float(zs[inside[-1]]) if len(inside) else 0.45

    sc = trimesh.Scene()
    shell = material("BotShell", (120, 70, 230), rough=0.32)
    canM = material("BotCan", (90, 50, 190), rough=0.35)
    eyes = material("BotEyes", (255, 255, 255), rough=0.2, emissive=[1.0, 1.0, 1.0])
    glow = material("BotGlow", (190, 150, 255), rough=0.2, emissive=[0.7, 0.5, 1.0])
    dark = material("BotDark", (25, 14, 50), rough=0.4)

    add(sc, paint(polygonise(body, lo, v, 9000, name="body"), shell), "Body")
    for nm, d in arms.items():
        pv = (-0.33 if nm == "ArmL" else 0.33, 0.74, 0.08)
        add(sc, paint(polygonise(d, lo, v, 2500, name=nm), shell), nm, pivot=pv)

    add(sc, paint(polygonise(head, lo, v, 9000, name="head"), shell), "Head", pivot=HEAD_C)
    add(sc, paint(polygonise(cans, lo, v, 6000, name="headset"), canM), "Headset", pivot=HEAD_C, parent="Head")

    # eyes: big soft white ovals sitting on the face, slightly tilted outwards
    EYE_X, EYE_Y = 0.155, 1.37
    for s in (-1, 1):
        e = trimesh.creation.icosphere(subdivisions=3, radius=1.0)
        e.apply_scale((0.105, 0.135, 0.05))
        e.apply_transform(trimesh.transformations.rotation_matrix(-s * 0.10, (0, 0, 1)))
        # follow the curvature of the face so the oval sits flush
        zc = surface_z(s * EYE_X, EYE_Y)
        yaw = np.arctan2(s * EYE_X, zc) * 0.9
        e.apply_transform(trimesh.transformations.rotation_matrix(yaw, (0, 1, 0)))
        e.apply_translation((s * EYE_X, EYE_Y, zc - 0.015))
        add(sc, paint(e, eyes), f"Eye{'L' if s < 0 else 'R'}", pivot=HEAD_C, parent="Head")
    # tiny dark 'o' mouth
    mz = surface_z(0, 1.19)
    mo = trimesh.creation.icosphere(subdivisions=2, radius=1.0); mo.apply_scale((0.042, 0.032, 0.025))
    mo.apply_translation((0, 1.19, mz - 0.005))
    add(sc, paint(mo, dark), "Mouth", pivot=HEAD_C, parent="Head")
    # glowing discs + rings on the outer face of each can
    for s in (-1, 1):
        d = trimesh.creation.cylinder(radius=0.125, height=0.03, sections=40)
        d.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, (0, 1, 0)))
        d.apply_translation((s * 0.605, 1.32, 0.02))
        add(sc, paint(d, glow), f"CanGlow{'L' if s < 0 else 'R'}", pivot=HEAD_C, parent="Head")
        ring = trimesh.creation.torus(0.145, 0.014, major_sections=48, minor_sections=10)
        ring.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, (0, 1, 0)))
        ring.apply_translation((s * 0.61, 1.32, 0.02))
        add(sc, paint(ring, glow), f"CanRing{'L' if s < 0 else 'R'}", pivot=HEAD_C, parent="Head")

    path = os.path.join(OUT, "bot.glb"); sc.export(path, include_normals=True)
    print("  ->", path, os.path.getsize(path) // 1024, "KB")

# ---------------------------------------------------------------- office chair
def build_chair():
    print("chair")
    vox = 0.01
    P, lo, v = grid((-0.5, 0.0, -0.75), (0.5, 1.75, 0.5), vox)
    seat = rbox(P, (0, 0.50, 0), (0.30, 0.045, 0.27), 0.07)
    seatPuff = ellipsoid(P, (0, 0.54, 0.02), (0.26, 0.05, 0.24))
    seat = smin(seat, seatPuff, 0.04)
    back = rbox(P, (0, 0.98, -0.33), (0.30, 0.34, 0.035), 0.07, rot_x=-0.12)
    lumbar = ellipsoid(P, (0, 0.74, -0.30), (0.22, 0.12, 0.05))
    back = smin(back, lumbar, 0.08)
    head = rbox(P, (0, 1.47, -0.40), (0.17, 0.075, 0.03), 0.05, rot_x=-0.15)
    stem = capsule(P, (0, 1.30, -0.37), (0, 1.42, -0.40), 0.03)
    chair = smin(smin(seat, back, 0.08), smin(head, stem, 0.04), 0.03)
    for s in (-1, 1):
        arm = rbox(P, (s * 0.36, 0.72, -0.02), (0.035, 0.02, 0.18), 0.03)
        post = capsule(P, (s * 0.36, 0.52, -0.08), (s * 0.36, 0.70, -0.08), 0.03)
        chair = smin(chair, smin(arm, post, 0.03), 0.04)

    sc = trimesh.Scene()
    fabric = material("ChairFabric", (24, 28, 39), rough=0.55)
    metal = material("ChairMetal", (40, 44, 56), rough=0.3, metal=0.8)
    add(sc, paint(polygonise(chair, lo, v, 9000, name="chair"), fabric), "Chair")
    post = trimesh.creation.cylinder(radius=0.04, height=0.42, sections=20)
    post.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, (1, 0, 0))); post.apply_translation((0, 0.25, 0))
    add(sc, paint(post, metal), "Post")
    for i in range(5):
        a = i / 5 * np.pi * 2
        leg = trimesh.creation.capsule(radius=0.03, height=0.32, count=[8, 8])
        leg.apply_translation((0, 0.06, 0.17))
        leg.apply_transform(trimesh.transformations.rotation_matrix(a, (0, 1, 0)))
        add(sc, paint(leg, metal), f"Leg{i}")
        wheel = trimesh.creation.icosphere(subdivisions=2, radius=0.045)
        wheel.apply_translation((np.sin(a) * 0.33, 0.045, np.cos(a) * 0.33))
        add(sc, paint(wheel, metal), f"Wheel{i}")
    path = os.path.join(OUT, "chair.glb"); sc.export(path, include_normals=True)
    print("  ->", path, os.path.getsize(path) // 1024, "KB")

# ---------------------------------------------------------------- sofas
def build_sofa(name, half_len, cushions):
    print(name)
    vox = 0.012
    P, lo, v = grid((-half_len - 0.3, 0.0, -0.75), (half_len + 0.3, 1.2, 0.7), vox)
    base = rbox(P, (0, 0.30, 0.02), (half_len, 0.20, 0.50), 0.10)
    back = rbox(P, (0, 0.70, -0.40), (half_len, 0.32, 0.12), 0.10, rot_x=-0.08)
    sofa = smin(base, back, 0.06)
    for s in (-1, 1):
        arm = rbox(P, (s * (half_len + 0.02), 0.52, 0.0), (0.14, 0.18, 0.50), 0.12)
        sofa = smin(sofa, arm, 0.06)
    cw = (2 * half_len - 0.2) / cushions
    cush = None
    for i in range(cushions):
        x = -half_len + 0.1 + (i + 0.5) * cw
        c = rbox(P, (x, 0.56, 0.06), (cw / 2 - 0.03, 0.08, 0.40), 0.07)
        puff = ellipsoid(P, (x, 0.60, 0.06), (cw / 2 - 0.08, 0.07, 0.34))
        c = smin(c, puff, 0.05)
        bc = rbox(P, (x, 0.84, -0.26), (cw / 2 - 0.03, 0.22, 0.09), 0.07, rot_x=-0.08)
        bpuff = ellipsoid(P, (x, 0.84, -0.20), (cw / 2 - 0.08, 0.18, 0.07))
        bc = smin(bc, bpuff, 0.05)
        c = union(c, bc)
        cush = c if cush is None else union(cush, c)
    sc = trimesh.Scene()
    fabric = material("Fabric", (205, 185, 149), rough=0.9)
    fabricDark = material("FabricDark", (184, 162, 126), rough=0.9)
    wood = material("Wood", (70, 50, 36), rough=0.6)
    add(sc, paint(polygonise(sofa, lo, v, 7000, name="frame"), fabricDark), "Frame")
    add(sc, paint(polygonise(cush, lo, v, 7000, name="cushions"), fabric), "Cushions")
    for s in (-1, 1):
        for z in (-0.3, 0.3):
            leg = trimesh.creation.cylinder(radius=0.035, height=0.12, sections=12)
            leg.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, (1, 0, 0)))
            leg.apply_translation((s * (half_len - 0.1), 0.06, z))
            add(sc, paint(leg, wood), f"Leg{s}{z}")
    path = os.path.join(OUT, f"{name}.glb"); sc.export(path, include_normals=True)
    print("  ->", path, os.path.getsize(path) // 1024, "KB")

if __name__ == "__main__":
    which = sys.argv[1:] or ["bot", "chair", "sofa", "armchair"]
    if "bot" in which: build_bot()
    if "chair" in which: build_chair()
    if "sofa" in which: build_sofa("sofa", 1.2, 2)
    if "armchair" in which: build_sofa("armchair", 0.55, 1)
