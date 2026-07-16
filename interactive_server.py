from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import sys
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from split_stl import bounds, intersection_segment, load_stl, split_file


ROOT = Path(__file__).resolve().parent
DEFAULT_STL = ROOT / "test.stl"
PYTHON_EXE = Path(sys.executable)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def _send(self, status: int, body: bytes, content_type: str = "application/octet-stream") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data: dict, status: int = 200) -> None:
        self._send(status, json.dumps(data, indent=2).encode("utf-8"), "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            return self._serve_file(ROOT / "web_app.html", "text/html; charset=utf-8")
        if parsed.path == "/api/info":
            path = Path(parse_qs(parsed.query).get("path", [str(DEFAULT_STL)])[0])
            return self._info(path)
        if parsed.path == "/api/open-stl":
            return self._open_stl()
        if parsed.path == "/api/section":
            qs = parse_qs(parsed.query)
            path = Path(qs.get("path", [str(DEFAULT_STL)])[0])
            axis_name = qs.get("axis", ["y"])[0]
            position = float(qs.get("position", ["0"])[0])
            return self._section(path, axis_name, position)
        if parsed.path == "/api/stl":
            path = Path(parse_qs(parsed.query).get("path", [str(DEFAULT_STL)])[0])
            return self._serve_stl(path)
        if parsed.path.startswith("/outputs/"):
            return self._serve_file(ROOT / parsed.path.lstrip("/"), mimetypes.guess_type(parsed.path)[0] or "application/octet-stream")
        self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/split":
            try:
                payload = self._read_json()
                report = self._split(payload)
                return self._json({"ok": True, "report": report})
            except Exception as exc:
                return self._json({"ok": False, "error": str(exc)}, 500)
        self._json({"error": "not found"}, 404)

    def _serve_file(self, path: Path, content_type: str) -> None:
        if not path.exists() or not path.resolve().is_relative_to(ROOT):
            return self._json({"error": "file not found"}, 404)
        self._send(200, path.read_bytes(), content_type)

    def _serve_stl(self, path: Path) -> None:
        if not path.exists() or path.suffix.lower() != ".stl":
            return self._json({"error": "STL not found"}, 404)
        self._send(200, path.read_bytes(), "model/stl")

    def _info(self, path: Path) -> None:
        if not path.exists() or path.suffix.lower() != ".stl":
            return self._json({"error": "STL not found"}, 404)
        triangles = load_stl(path)
        mn, mx, size = bounds(triangles)
        self._json(
            {
                "path": str(path),
                "triangles": int(len(triangles)),
                "min": mn.tolist(),
                "max": mx.tolist(),
                "size": size.tolist(),
                "defaultAxis": "xyz"[int(size.argmax())],
                "defaultPosition": float((mn[int(size.argmax())] + mx[int(size.argmax())]) / 2),
            }
        )

    def _open_stl(self) -> None:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        filename = filedialog.askopenfilename(
            title="Open STL file",
            filetypes=(("STL files", "*.stl"), ("All files", "*.*")),
        )
        root.destroy()
        self._json({"path": filename})

    def _section(self, path: Path, axis_name: str, position: float) -> None:
        if not path.exists() or path.suffix.lower() != ".stl":
            return self._json({"error": "STL not found"}, 404)
        axis = {"x": 0, "y": 1, "z": 2}[axis_name]
        triangles = load_stl(path)
        segments = []
        for tri in triangles:
            seg = intersection_segment(tri, axis, position)
            if seg is not None:
                segments.append([[float(v) for v in seg[0]], [float(v) for v in seg[1]]])
        self._json({"axis": axis_name, "position": position, "segments": segments})

    def _split(self, payload: dict) -> dict:
        path = Path(payload["path"])
        axis = payload["axis"]
        position = float(payload["position"])
        rotate_z = float(payload.get("rotateZ", 0))
        pin_radius = float(payload.get("pinRadius", 3.0))
        pin_clearance = float(payload.get("pinClearance", 0.2))
        socket_depth = float(payload.get("socketDepth", 6.2))
        pin_length = float(payload.get("pinLength", max(1.0, socket_depth * 2 - 0.4)))
        centers = payload.get("socketCenters") or []
        radii = payload.get("socketRadii") or []
        socket_holes = bool(payload.get("socketHoles")) and len(centers) > 0
        pins = len(centers) if socket_holes else 0
        out_dir = ROOT / "outputs" / f"{path.stem}_interactive"
        report = split_file(
            input_path=path,
            out_dir=out_dir,
            axis_name=axis,
            position=position,
            build_volume=(180.0, 180.0, 180.0),
            pins=pins,
            pin_radius=pin_radius,
            pin_length=pin_length,
            pin_clearance=pin_clearance,
            rotate_z=rotate_z,
            socket_holes=socket_holes,
            socket_depth=socket_depth,
            socket_centers=centers,
            socket_radii=radii,
        )
        zip_path = self._make_zip(out_dir, path.stem, report)
        report["zip_file"] = str(zip_path)
        report["zip_url"] = "/" + zip_path.relative_to(ROOT).as_posix()
        try:
            os.startfile(out_dir)  # type: ignore[attr-defined]
        except Exception:
            pass
        return report

    def _make_zip(self, out_dir: Path, stem: str, report: dict) -> Path:
        zip_path = out_dir / f"{stem}_split_package.zip"
        include = set(Path(part["file"]).name for part in report.get("parts", []))
        include.update(Path(pin).name for pin in report.get("pins", {}).get("files", []))
        include.add(f"{stem}_split_report.json")
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file in sorted(out_dir.iterdir()):
                if file.name not in include or not file.is_file():
                    continue
                zf.write(file, arcname=file.name)
        return zip_path


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    url = "http://127.0.0.1:8765/"
    print(f"Interactive STL splitter running at {url}")
    webbrowser.open(url)
    server.serve_forever()


if __name__ == "__main__":
    main()
