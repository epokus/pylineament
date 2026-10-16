# PyLineament

**PyLineament** is a Python-based, open-source toolkit for **automatic and regional-scale lineament extraction** from Digital Elevation Models (DEMs) and remote sensing imagery.

It is designed for geological and geomorphological analysis — providing a **fully automated, reproducible**, and **scalable** workflow for extracting, reducing, and mapping lineaments across local to regional scales.

---

## Installation

```bash
pip install pylineament
```
Or from source:

```bash
git clone https://github.com/epokus/pylineament.git
cd pylineament
pip install -e .
```

## Quick Start (Command Line)

Once installed, simply open your terminal or command prompt and run:

```bash
pylineament
```

## Graphical interface

Run `pylineament` (or `python -m pylineament.gui`) to open the GUI:

1. **Open** a DEM (GeoTIFF; JPEG/PNG also work in pixel coordinates). The *Overview* tab shows the
   hillshade and the tile grid.
2. **Click a tile** to preview it. The *Tile preview* tab shows the hillshade the algorithm sees,
   the edge points, fitted lines and final lines. The preview recomputes when a parameter changes,
   and a banner reminds you when it is out of date.
3. **Run extraction** (Ctrl+R) to process all tiles in parallel and write a shapefile. Progress,
   ETA and Cancel are in the status bar. The parameters are saved next to the shapefile as
   `<name>_params.json`.
4. The *Results* tab shows counts, lengths, a rose diagram and a length histogram.

The *Style* tab sets colours and widths of every layer, and the *How to use* tab (F1) explains
each parameter. *Parameters > Copy as Python* gives the equivalent `dem_to_shp(...)` call; the GUI
and the Python API produce identical lineaments.

## Windows executable

A standalone executable (no Python needed) is built with PyInstaller:

```bash
pip install -e .[dev] pyinstaller
pyinstaller pylineament.spec          # -> dist/pylineament-<version>.exe
dist/pylineament-<version>.exe --self-test example/e_kal_crop2.tif selftest_out
```

The self-test runs a preview and a full extraction headless and writes `selftest_out/self_test.json`.

## Tests

```bash
pip install -e .[dev]
python -m pytest tests
```

## Key Features
- Interactive UI — Run `pylineament` (or `python -m pylineament.gui`) to open the GUI: tile grid overview, live per-tile preview of edge points and fitted lines, parallel full extraction with progress and cancel, rose diagram and length statistics, and parameter save/load.
- Automated Workflow — Full end-to-end lineament extraction.
- Customizable Parameters — Control edge detection thresholds, segment length, and merging distance.
- Multi-Resolution Support — Works with various DEM/image resolutions.
- Scalable — Efficient for large-area or regional-scale mapping.
- Reproducible — Transparent parameters and open-source implementation.

## Core Functions
| Function                     | Description                                                  |
| ---------------------------- | ------------------------------------------------------------ |
| `read_raster()`              | Reads and preprocesses a raster (DEM or image).              |
| `extract_lineament_points()` | Detects lineament-like edge points using gradient filters.   |
| `convert_points_to_line()`   | Converts clustered edge points into connected line segments. |
| `reduce_lines()`             | Simplifies and merges overlapping or redundant lineaments.   |
| `hillshade()`                | Generates a hillshade image for visualization.               |
| `dem_to_line()`              | Extracts lineaments directly from a DEM file.                |
| `dem_to_shp()`               | Full workflow: extract + merge + export to shapefile.        |


## Example Workflow
- Input your DEM or satellite image.
- Optionally apply hillshade() or downscale for efficiency.
- Extract edge points using extract_lineament_points().
- Convert points to lines and merge them with reduce_lines().
- Save as shapefile using dem_to_shp() or merge_lines_csv_to_shp().

## example how to use this Library with CLI or python

```python
from pylineament import dem_to_shp
dem_to_shp("data/srtm_sample.tif", shp_name= "lineamentsExtract")
```
shp file will be saved in "lineamentsExtract" folder.
see more examples in example folder
![PyLineament UI Preview](examples/lienament_extracted.png)


## Parameters Overview
| Parameter    | Description                           | Typical Range     |
| ------------ | ------------------------------------- | ----------------- |
| `eps`        | Edge detection sensitivity            | 0.8 – 2.0         |
| `thresh`     | Edge detection threshold              | 20 – 80           |
| `z_multip`   | Vertical exaggeration factor          | 0.5 – 2.0         |
| `min_dist`   | Minimum distance between merged lines | 5 – 20 pixels     |
| `seg_len`    | Minimum segment length                | 5 – 20 pixels     |
| `split_size` | DEM/image tile size for processing    | 250 – 1000 pixels |
| `line_fit`   | Line fitting: `'ols'` (v1.0.1) or `'pca'` (orientation-unbiased) | `'ols'`, `'pca'` |
| `azimuths`   | Hillshade azimuths (degrees). Default 0–150° step 30°: at altitude 0, azimuths 180° apart give identical edges, so 6 cover every direction and run ~2× faster than v1.0.1's 12. Use `ln.LEGACY_AZIMUTHS` (0–330°) to reproduce v1.0.1 results exactly | `ln.DEFAULT_AZIMUTHS` |



## Why PyLineament?
Typical “automatic” lineament extraction tools are limited by:
- Fixed image resolution and poor scalability,
- Heavy preprocessing requirements,
- Loss of geological meaning across scales,
- Slow performance in large regions.

## PyLineament addresses these by providing:
- Automated but parameter-controllable extraction,
- Multi-resolution and downscaling support,
- Robust reduction and merging algorithms,
- Compatibility with both small-area (detailed) and large-area datasets (regional mapping).

## Citation
If you use PyLineament in your research, please cite:
Prasetya Kusumah, E. (2025). PyLineament: A Python Toolkit for Regional-Scale Lineament Extraction. 
Version 1.1.0. https://github.com/epokus/pylineament

## License
This project is licensed under the MIT License — see the LICENSE
 file for details.

