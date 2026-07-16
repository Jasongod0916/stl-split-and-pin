from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np


AXES = {"x": 0, "y": 1, "z": 2}
EPS = 1e-7
VENDOR_DIR = Path(__file__).with_name("vendor")


@dataclass
class SplitResult:
    negative: np.ndarray
    positive: np.ndarray
    axis: int
    position: float
    cap_segments: int


@dataclass
class MeshPart:
    triangles: np.ndarray
    name: str


def load_stl(path: Path) -> np.ndarray:
    data = path.read_bytes()
    if len(data) >= 84:
        count = struct.unpack("<I", data[80:84])[0]
        expected = 84 + count * 50
        if expected == len(data):
            return load_binary_stl(data, count)
    return load_ascii_stl(data.decode("utf-8", errors="ignore"))


def load_binary_stl(data: bytes, count: int) -> np.ndarray:
    triangles = np.empty((count, 3, 3), dtype=np.float64)
    offset = 84
    for i in range(count):
        # normal is bytes 0..11, vertices are bytes 12..47, attr is 48..49
        floats = struct.unpack("<12f", data[offset : offset + 48])
        triangles[i] = np.array(floats[3:12], dtype=np.float64).reshape(3, 3)
        offset += 50
    return triangles


def load_ascii_stl(text: str) -> np.ndarray:
    vertices: list[list[float]] = []
    triangles: list[list[list[float]]] = []
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) == 4 and parts[0].lower() == "vertex":
            vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
            if len(vertices) == 3:
                triangles.append(vertices)
                vertices = []
    if not triangles:
        raise ValueError("No triangles found. Is this a valid STL?")
    return np.array(triangles, dtype=np.float64)


def write_binary_stl(path: Path, triangles: np.ndarray, name: str) -> None:
    header = name.encode("ascii", errors="ignore")[:80].ljust(80, b" ")
    with path.open("wb") as fh:
        fh.write(header)
        fh.write(struct.pack("<I", len(triangles)))
        for tri in triangles:
            normal = triangle_normal(tri)
            fh.write(struct.pack("<3f", *normal))
            for vertex in tri:
                fh.write(struct.pack("<3f", *vertex))
            fh.write(struct.pack("<H", 0))


def try_enable_vendor_packages() -> None:
    if VENDOR_DIR.exists():
        vendor = str(VENDOR_DIR)
        if vendor not in sys.path:
            sys.path.insert(0, vendor)


def triangle_normal(tri: np.ndarray) -> np.ndarray:
    normal = np.cross(tri[1] - tri[0], tri[2] - tri[0])
    norm = np.linalg.norm(normal)
    if norm < EPS:
        return np.array([0.0, 0.0, 0.0])
    return normal / norm


def rotate_mesh_z(triangles: np.ndarray, degrees: float) -> np.ndarray:
    if abs(degrees) < EPS:
        return triangles
    radians = math.radians(degrees)
    c = math.cos(radians)
    s = math.sin(radians)
    rotation = np.array(
        [
            [c, -s, 0.0],
            [s, c, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    return triangles @ rotation.T


def clip_polygon(poly: list[np.ndarray], axis: int, position: float, keep_negative: bool) -> list[np.ndarray]:
    if not poly:
        return []

    def inside(point: np.ndarray) -> bool:
        d = point[axis] - position
        return d <= EPS if keep_negative else d >= -EPS

    def intersect(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        da = a[axis] - position
        db = b[axis] - position
        denom = da - db
        if abs(denom) < EPS:
            return a.copy()
        t = da / denom
        p = a + t * (b - a)
        p[axis] = position
        return p

    result: list[np.ndarray] = []
    prev = poly[-1]
    prev_inside = inside(prev)
    for curr in poly:
        curr_inside = inside(curr)
        if curr_inside:
            if not prev_inside:
                result.append(intersect(prev, curr))
            result.append(curr.copy())
        elif prev_inside:
            result.append(intersect(prev, curr))
        prev = curr
        prev_inside = curr_inside
    return remove_adjacent_duplicates(result)


def remove_adjacent_duplicates(points: list[np.ndarray]) -> list[np.ndarray]:
    clean: list[np.ndarray] = []
    for point in points:
        if not clean or np.linalg.norm(point - clean[-1]) > EPS:
            clean.append(point)
    if len(clean) > 1 and np.linalg.norm(clean[0] - clean[-1]) <= EPS:
        clean.pop()
    return clean


def polygon_to_triangles(poly: list[np.ndarray]) -> list[np.ndarray]:
    if len(poly) < 3:
        return []
    return [np.array([poly[0], poly[i], poly[i + 1]], dtype=np.float64) for i in range(1, len(poly) - 1)]


def split_mesh(triangles: np.ndarray, axis: int, position: float) -> SplitResult:
    negative: list[np.ndarray] = []
    positive: list[np.ndarray] = []
    segments: list[tuple[np.ndarray, np.ndarray]] = []

    for tri in triangles:
        poly = [tri[0], tri[1], tri[2]]
        neg_poly = clip_polygon(poly, axis, position, True)
        pos_poly = clip_polygon(poly, axis, position, False)
        negative.extend(polygon_to_triangles(neg_poly))
        positive.extend(polygon_to_triangles(pos_poly))

        crossing = intersection_segment(tri, axis, position)
        if crossing is not None:
            segments.append(crossing)

    cap_loops = build_loops(segments)
    negative.extend(cap_triangles(cap_loops, axis, outward_sign=1.0))
    positive.extend(cap_triangles(cap_loops, axis, outward_sign=-1.0))

    return SplitResult(
        negative=np.array(negative, dtype=np.float64),
        positive=np.array(positive, dtype=np.float64),
        axis=axis,
        position=position,
        cap_segments=len(segments),
    )


def split_mesh_auto_fit(
    triangles: np.ndarray,
    build_volume: tuple[float, float, float],
    max_parts: int = 16,
) -> list[MeshPart]:
    volume = np.array(build_volume, dtype=np.float64)
    pending = [MeshPart(triangles=triangles, name="part")]
    finished: list[MeshPart] = []

    while pending:
        part = pending.pop(0)
        mesh_min, mesh_max, mesh_size = bounds(part.triangles)
        oversized_axes = np.where(mesh_size > volume + EPS)[0]
        if len(oversized_axes) == 0:
            finished.append(part)
            continue

        if len(pending) + len(finished) + 2 > max_parts:
            finished.append(part)
            continue

        axis = int(oversized_axes[np.argmax(mesh_size[oversized_axes] / volume[oversized_axes])])
        position = float((mesh_min[axis] + mesh_max[axis]) / 2)
        result = split_mesh(part.triangles, axis, position)
        pending.append(MeshPart(result.negative, f"{part.name}_A"))
        pending.append(MeshPart(result.positive, f"{part.name}_B"))

    return finished


def intersection_segment(tri: np.ndarray, axis: int, position: float) -> tuple[np.ndarray, np.ndarray] | None:
    points: list[np.ndarray] = []
    for i in range(3):
        a = tri[i]
        b = tri[(i + 1) % 3]
        da = a[axis] - position
        db = b[axis] - position
        if abs(da) <= EPS and abs(db) <= EPS:
            points.extend([a.copy(), b.copy()])
        elif abs(da) <= EPS:
            points.append(a.copy())
        elif abs(db) <= EPS:
            points.append(b.copy())
        elif da * db < 0:
            t = da / (da - db)
            p = a + t * (b - a)
            p[axis] = position
            points.append(p)

    unique = unique_points(points)
    if len(unique) >= 2:
        return unique[0], unique[1]
    return None


def unique_points(points: list[np.ndarray]) -> list[np.ndarray]:
    unique: list[np.ndarray] = []
    for point in points:
        if all(np.linalg.norm(point - existing) > EPS for existing in unique):
            unique.append(point)
    return unique


def build_loops(segments: list[tuple[np.ndarray, np.ndarray]]) -> list[list[np.ndarray]]:
    if not segments:
        return []

    def key(point: np.ndarray) -> tuple[int, int, int]:
        return tuple(int(round(v * 1000000)) for v in point)

    points: dict[tuple[int, int, int], np.ndarray] = {}
    adjacency: dict[tuple[int, int, int], list[tuple[int, int, int]]] = {}
    edges: set[tuple[tuple[int, int, int], tuple[int, int, int]]] = set()

    for a, b in segments:
        ka = key(a)
        kb = key(b)
        if ka == kb:
            continue
        points[ka] = a
        points[kb] = b
        adjacency.setdefault(ka, []).append(kb)
        adjacency.setdefault(kb, []).append(ka)
        edges.add(tuple(sorted((ka, kb))))

    loops: list[list[np.ndarray]] = []
    while edges:
        start_edge = next(iter(edges))
        edges.remove(start_edge)
        start, curr = start_edge
        loop_keys = [start, curr]
        prev = start

        while curr != start:
            neighbors = adjacency.get(curr, [])
            candidates = [n for n in neighbors if n != prev and tuple(sorted((curr, n))) in edges]
            if not candidates:
                break
            nxt = candidates[0]
            edges.remove(tuple(sorted((curr, nxt))))
            prev, curr = curr, nxt
            loop_keys.append(curr)

        if loop_keys[-1] == start and len(loop_keys) >= 4:
            loops.append([points[k] for k in loop_keys[:-1]])

    return loops


def cap_triangles(loops: list[list[np.ndarray]], axis: int, outward_sign: float) -> list[np.ndarray]:
    capped: list[np.ndarray] = []
    target = np.zeros(3)
    target[axis] = outward_sign

    for loop in loops:
        if len(loop) < 3:
            continue
        center = np.mean(np.array(loop), axis=0)
        center[axis] = loop[0][axis]
        for i in range(len(loop)):
            tri = np.array([center, loop[i], loop[(i + 1) % len(loop)]], dtype=np.float64)
            normal = triangle_normal(tri)
            if np.dot(normal, target) < 0:
                tri = np.array([center, loop[(i + 1) % len(loop)], loop[i]], dtype=np.float64)
            capped.append(tri)
    return capped


def bounds(triangles: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    vertices = triangles.reshape(-1, 3)
    minimum = vertices.min(axis=0)
    maximum = vertices.max(axis=0)
    return minimum, maximum, maximum - minimum


def make_pin(radius: float, length: float, segments: int = 48) -> np.ndarray:
    tris: list[np.ndarray] = []
    z0 = -length / 2
    z1 = length / 2
    c0 = np.array([0.0, 0.0, z0])
    c1 = np.array([0.0, 0.0, z1])

    ring0 = []
    ring1 = []
    for i in range(segments):
        angle = 2 * math.pi * i / segments
        x = math.cos(angle) * radius
        y = math.sin(angle) * radius
        ring0.append(np.array([x, y, z0]))
        ring1.append(np.array([x, y, z1]))

    for i in range(segments):
        j = (i + 1) % segments
        tris.append(np.array([ring0[i], ring0[j], ring1[j]]))
        tris.append(np.array([ring0[i], ring1[j], ring1[i]]))
        tris.append(np.array([c0, ring0[j], ring0[i]]))
        tris.append(np.array([c1, ring1[i], ring1[j]]))
    return np.array(tris, dtype=np.float64)


def socket_centers_from_cut(part_triangles: np.ndarray, axis: int, position: float, count: int) -> list[np.ndarray]:
    vertices = part_triangles.reshape(-1, 3)
    cut_vertices = vertices[np.abs(vertices[:, axis] - position) < 1e-4]
    if len(cut_vertices) < 10:
        cut_vertices = vertices[np.abs(vertices[:, axis] - position) < 1e-2]
    if len(cut_vertices) < 10:
        _mn, _mx, size = bounds(part_triangles)
        raise ValueError(f"Could not find enough cut-plane vertices for socket placement. Part size: {size.tolist()}")

    other_axes = [i for i in range(3) if i != axis]
    a0, a1 = other_axes
    min0, max0 = np.percentile(cut_vertices[:, a0], [20, 80])
    min1, max1 = np.percentile(cut_vertices[:, a1], [35, 65])
    mid1 = float((min1 + max1) / 2)

    if count <= 1:
        coords0 = [float((min0 + max0) / 2)]
    else:
        coords0 = np.linspace(float(min0), float(max0), count).tolist()

    centers: list[np.ndarray] = []
    for coord0 in coords0:
        center = np.zeros(3, dtype=np.float64)
        center[axis] = position
        center[a0] = coord0
        center[a1] = mid1
        centers.append(center)
    return centers


def cylinder_transform(axis: int, center: np.ndarray) -> np.ndarray:
    transform = np.eye(4)
    if axis == 0:
        angle = math.pi / 2
        c, s = math.cos(angle), math.sin(angle)
        transform[:3, :3] = np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])
    elif axis == 1:
        angle = -math.pi / 2
        c, s = math.cos(angle), math.sin(angle)
        transform[:3, :3] = np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])
    transform[:3, 3] = center
    return transform


def add_socket_holes_to_parts(
    part_a_path: Path,
    part_b_path: Path,
    part_a_triangles: np.ndarray,
    axis: int,
    position: float,
    pin_count: int,
    pin_radius: float,
    pin_clearance: float,
    socket_depth: float,
    manual_centers: list[list[float]] | None = None,
    manual_radii: list[float] | None = None,
) -> list[list[float]]:
    if pin_count <= 0:
        return []

    try_enable_vendor_packages()
    import trimesh

    outside_overlap = 1.0
    height = socket_depth + outside_overlap
    centers_on_cut = (
        [np.array(center, dtype=np.float64) for center in manual_centers]
        if manual_centers
        else socket_centers_from_cut(part_a_triangles, axis, position, pin_count)
    )
    radii = manual_radii if manual_radii else [pin_radius for _ in centers_on_cut]
    cutters_a = []
    cutters_b = []

    for center, center_radius in zip(centers_on_cut, radii):
        radius = float(center_radius) + pin_clearance
        center_a = center.copy()
        center_b = center.copy()
        center_a[axis] = position + (outside_overlap - socket_depth) / 2
        center_b[axis] = position + (socket_depth - outside_overlap) / 2
        cutters_a.append(
            trimesh.creation.cylinder(
                radius=radius,
                height=height,
                sections=48,
                transform=cylinder_transform(axis, center_a),
            )
        )
        cutters_b.append(
            trimesh.creation.cylinder(
                radius=radius,
                height=height,
                sections=48,
                transform=cylinder_transform(axis, center_b),
            )
        )

    mesh_a = trimesh.load_mesh(part_a_path, force="mesh")
    mesh_b = trimesh.load_mesh(part_b_path, force="mesh")
    result_a = trimesh.boolean.difference([mesh_a, *cutters_a], engine="manifold")
    result_b = trimesh.boolean.difference([mesh_b, *cutters_b], engine="manifold")
    if result_a is None or result_b is None:
        raise ValueError("Boolean socket cut failed.")

    result_a.export(part_a_path)
    result_b.export(part_b_path)
    return [center.tolist() for center in centers_on_cut]


def split_file(
    input_path: Path,
    out_dir: Path,
    axis_name: str = "auto",
    position: float | None = None,
    build_volume: tuple[float, float, float] = (180.0, 180.0, 180.0),
    pins: int = 0,
    pin_radius: float = 3.0,
    pin_length: float = 12.0,
    pin_clearance: float = 0.2,
    rotate_z: float = 0.0,
    socket_holes: bool = False,
    socket_depth: float | None = None,
    socket_centers: list[list[float]] | None = None,
    socket_radii: list[float] | None = None,
) -> dict:
    triangles = load_stl(input_path)
    triangles = rotate_mesh_z(triangles, rotate_z)
    mesh_min, mesh_max, mesh_size = bounds(triangles)
    axis = int(np.argmax(mesh_size)) if axis_name == "auto" else AXES[axis_name]
    split_position = float((mesh_min[axis] + mesh_max[axis]) / 2) if position is None else position

    result = split_mesh(triangles, axis, split_position)
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = input_path.stem
    part_a = out_dir / f"{stem}_part_A.stl"
    part_b = out_dir / f"{stem}_part_B.stl"
    write_binary_stl(part_a, result.negative, f"{stem} part A")
    write_binary_stl(part_b, result.positive, f"{stem} part B")

    pin_files = []
    if pins > 0:
        for i in range(pins):
            radius = float(socket_radii[i]) if socket_radii and i < len(socket_radii) else pin_radius
            pin_mesh = make_pin(radius, pin_length)
            path = out_dir / f"{stem}_alignment_pin_{i + 1}.stl"
            write_binary_stl(path, pin_mesh, f"{stem} alignment pin {i + 1}")
            pin_files.append(str(path))

    socket_depth_value = float(socket_depth if socket_depth is not None else pin_length / 2 + pin_clearance)
    cut_socket_centers: list[list[float]] = []
    socket_status = "disabled"
    if socket_holes and pins > 0:
        try:
            cut_socket_centers = add_socket_holes_to_parts(
                part_a_path=part_a,
                part_b_path=part_b,
                part_a_triangles=result.negative,
                axis=axis,
                position=split_position,
                pin_count=pins,
                pin_radius=pin_radius,
                pin_clearance=pin_clearance,
                socket_depth=socket_depth_value,
                manual_centers=socket_centers,
                manual_radii=socket_radii,
            )
            socket_status = "cut"
        except Exception as exc:
            socket_status = f"failed: {exc}"

    volume = np.array(build_volume)
    _a_min, _a_max, a_size = bounds(result.negative)
    _b_min, _b_max, b_size = bounds(result.positive)
    report = {
        "input": str(input_path),
        "axis": "xyz"[axis],
        "position": split_position,
        "rotate_z_degrees": rotate_z,
        "original_size_mm": mesh_size.tolist(),
        "build_volume_mm": volume.tolist(),
        "parts": [
            {"file": str(part_a), "size_mm": a_size.tolist(), "fits": bool(np.all(a_size <= volume + EPS))},
            {"file": str(part_b), "size_mm": b_size.tolist(), "fits": bool(np.all(b_size <= volume + EPS))},
        ],
        "cap_segments": result.cap_segments,
        "pins": {
            "count": pins,
            "files": pin_files,
            "radius_mm": pin_radius,
            "radii_mm": socket_radii if socket_radii else [pin_radius for _ in range(pins)],
            "length_mm": pin_length,
            "suggested_socket_clearance_mm": pin_clearance,
        },
        "socket_holes": {
            "enabled": socket_holes,
            "status": socket_status,
            "depth_mm": socket_depth_value,
            "radius_mm": pin_radius + pin_clearance,
            "centers": cut_socket_centers,
        },
        "notes": [
            "MVP uses planar split and cap fill.",
            "Socket holes use boolean cutting when trimesh and manifold3d are available.",
        ],
    }
    (out_dir / f"{stem}_split_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def split_file_auto_fit(
    input_path: Path,
    out_dir: Path,
    build_volume: tuple[float, float, float] = (180.0, 180.0, 180.0),
    max_parts: int = 16,
    pins: int = 0,
    pin_radius: float = 3.0,
    pin_length: float = 12.0,
    pin_clearance: float = 0.2,
    rotate_z: float = 0.0,
) -> dict:
    triangles = load_stl(input_path)
    triangles = rotate_mesh_z(triangles, rotate_z)
    _mesh_min, _mesh_max, mesh_size = bounds(triangles)
    out_dir.mkdir(parents=True, exist_ok=True)

    parts = split_mesh_auto_fit(triangles, build_volume, max_parts=max_parts)
    stem = input_path.stem
    volume = np.array(build_volume)
    part_reports = []

    for index, part in enumerate(parts, start=1):
        path = out_dir / f"{stem}_part_{index:02d}.stl"
        write_binary_stl(path, part.triangles, f"{stem} part {index:02d}")
        _part_min, _part_max, part_size = bounds(part.triangles)
        part_reports.append(
            {
                "file": str(path),
                "size_mm": part_size.tolist(),
                "fits": bool(np.all(part_size <= volume + EPS)),
            }
        )

    pin_files = []
    if pins > 0:
        pin_mesh = make_pin(pin_radius, pin_length)
        for i in range(pins):
            path = out_dir / f"{stem}_alignment_pin_{i + 1}.stl"
            write_binary_stl(path, pin_mesh, f"{stem} alignment pin {i + 1}")
            pin_files.append(str(path))

    report = {
        "input": str(input_path),
        "mode": "auto_fit",
        "rotate_z_degrees": rotate_z,
        "original_size_mm": mesh_size.tolist(),
        "build_volume_mm": volume.tolist(),
        "part_count": len(parts),
        "all_parts_fit": all(part["fits"] for part in part_reports),
        "parts": part_reports,
        "pins": {
            "count": pins,
            "files": pin_files,
            "radius_mm": pin_radius,
            "length_mm": pin_length,
            "suggested_socket_clearance_mm": pin_clearance,
        },
        "notes": [
            "Auto-fit mode recursively splits oversized parts along their largest oversized axis.",
            "Pins are separate alignment dowels; this version does not boolean-cut matching sockets into the parts.",
        ],
    }
    (out_dir / f"{stem}_split_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Split an STL into two capped parts for small printers.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--out-dir", type=Path, default=Path("outputs/split"))
    parser.add_argument("--axis", choices=["auto", "x", "y", "z"], default="auto")
    parser.add_argument("--position", type=float)
    parser.add_argument("--build-volume", type=float, nargs=3, default=(180.0, 180.0, 180.0))
    parser.add_argument("--pins", type=int, default=0)
    parser.add_argument("--pin-radius", type=float, default=3.0)
    parser.add_argument("--pin-length", type=float, default=12.0)
    parser.add_argument("--pin-clearance", type=float, default=0.2)
    parser.add_argument("--auto-fit", action="store_true", help="Keep splitting until each part fits the build volume.")
    parser.add_argument("--max-parts", type=int, default=16)
    parser.add_argument("--rotate-z", type=float, default=0.0, help="Rotate the mesh around Z before splitting.")
    parser.add_argument("--socket-holes", action="store_true", help="Cut matching dowel sockets into both split parts.")
    parser.add_argument("--socket-depth", type=float, help="Socket depth in each part. Default is half pin length plus clearance.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.auto_fit:
        report = split_file_auto_fit(
            input_path=args.input,
            out_dir=args.out_dir,
            build_volume=tuple(args.build_volume),
            max_parts=args.max_parts,
            pins=args.pins,
            pin_radius=args.pin_radius,
            pin_length=args.pin_length,
            pin_clearance=args.pin_clearance,
            rotate_z=args.rotate_z,
            socket_holes=args.socket_holes,
            socket_depth=args.socket_depth,
        )
    else:
        report = split_file(
            input_path=args.input,
            out_dir=args.out_dir,
            axis_name=args.axis,
            position=args.position,
            build_volume=tuple(args.build_volume),
            pins=args.pins,
            pin_radius=args.pin_radius,
            pin_length=args.pin_length,
            pin_clearance=args.pin_clearance,
            rotate_z=args.rotate_z,
            socket_holes=args.socket_holes,
            socket_depth=args.socket_depth,
        )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
