# Reference data

`graciella2026_manual_lineaments.shp`: manual lineament interpretation from the undergraduate thesis of
Jemima Graciella (2026), *Geologi daerah Sukamakmur dan sekitarnya, Kabupaten Bogor, Jawa Barat*,
Universitas Pertamina. 140 lineaments (114 ridge, 26 valley) west of Bandung, West Java
(107.00°–107.14° E, 6.57°–6.72° S). Used as reference for the accuracy assessment in the Pylineament paper.

- Coordinate system: WGS 84 / UTM zone 48S (EPSG:32748)
- Fields: `class` (`ridge` or `valley`), `sudut` (azimuth as given by the interpreter), `src_fid` (feature id in
  the original file), `length_m` (line length in metres)
