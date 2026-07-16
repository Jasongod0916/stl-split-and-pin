# STL Splitter

STL Splitter is a browser-based tool for splitting oversized STL models into two printable parts. It lets you choose the cut position, place alignment pin holes on the cut face, and download a ZIP package directly from the browser.

## Features

- Open local binary or ASCII STL files in the browser.
- Inspect the model with a 3D orbit view and orthographic views.
- Choose the cut axis and cut position manually.
- Use 1/2, 1/3, and 1/4 guide points for faster cut placement.
- Draw, move, select, copy, and delete alignment holes on the cut face.
- Show safety hints for risky hole positions.
- Cut matching socket holes on the split face.
- Export split STL parts, alignment pin STL files, and a JSON report as one ZIP.

## Web App

Open the hosted app:

```text
https://jasongod0916.github.io/stl-split-and-pin/
```

Or open `web_app.html` locally in a browser.

Basic workflow:

1. Click `Open STL` and choose a local STL file.
2. Set the cut axis and cut position.
3. Use `Draw` to place alignment holes on the Cut Face.
4. Adjust hole radius, depth, and tolerance.
5. Click `Split and download ZIP`.
6. Check the exported STL files in your slicer before printing.

## ZIP Output

The downloaded ZIP includes:

- `*_part_A.stl`
- `*_part_B.stl`
- `*_alignment_pin_*.stl`
- `*_split_report.json`

## Notes

- Socket cutting is designed for split-face alignment pins, not general CAD boolean operations.
- Hole placement should avoid thin walls, outer edges, and functional surfaces.
- STL units are treated as millimeters.
- Always inspect the generated parts in Bambu Studio or another slicer before printing.

## Local Python Tools

The repository also includes older local Python tools:

```text
run_interactive.bat
run_gui.bat
```

The browser app is the recommended interface for normal use.
