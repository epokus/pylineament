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

## Key Features
- Interactive UI — Run `pylineament` in the terminal to open the GUI.
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
Version 1.0. https://github.com/epokus/pylineament

## License
This project is licensed under the MIT License — see the LICENSE
 file for details.

