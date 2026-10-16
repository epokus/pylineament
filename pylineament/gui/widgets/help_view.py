from PyQt5.QtWidgets import QTextBrowser

from ..params import AZIMUTH_SETS, LINE_FITS, SPECS, Params

_CSS = """
<style>
 body { font-size: 10pt; }
 h2 { margin-top: 18px; color: #1f4e79; }
 h3 { margin-top: 12px; }
 td, th { padding: 3px 8px; vertical-align: top; }
 th { background: #e8eef5; text-align: left; }
 .key { background: #f1f1f1; border: 1px solid #ccc; padding: 0 4px; font-family: Consolas; }
 .tip { background: #fff8e1; border-left: 4px solid #f2b400; padding: 6px; }
</style>
"""


def _param_table():
    d = Params()
    rows = []
    for name, (label, lo, hi, _step, _dec, tip) in SPECS.items():
        rows.append(f'<tr><td><b>{label}</b><br><code>{name}</code></td>'
                    f'<td>{getattr(d, name)}</td><td>{lo} – {hi}</td><td>{tip}</td></tr>')
    fits = '; '.join(f'<code>{k}</code>: {v}' for k, v in LINE_FITS.items())
    rows.append(f'<tr><td><b>Line fit</b><br><code>line_fit</code></td><td>{d.line_fit}</td>'
                f'<td>ols, tls</td><td>{fits}</td></tr>')
    sets = '; '.join(f'<b>{n}</b>: {label}' for n, (_, label) in AZIMUTH_SETS.items())
    rows.append(f'<tr><td><b>Azimuths</b><br><code>azimuths</code></td><td>{d.azimuths}</td>'
                f'<td>6, 12</td><td>Hillshade illumination directions ({sets}). With the light at '
                'the horizon, az and az + 180° give identical edges, so 6 directions cover every '
                'orientation. 12 reproduces v1.0.1; the results differ by about 0.1 % of the '
                'lines.</td></tr>')
    return ('<table cellspacing="0" border="1" style="border-collapse:collapse">'
            '<tr><th>Parameter</th><th>Default</th><th>Range</th><th>Meaning</th></tr>'
            + ''.join(rows) + '</table>')


def help_html():
    return _CSS + f"""
<h1>How to use Pylineament</h1>
<p>Pylineament extracts geological lineaments from a DEM. It builds hillshades lit from the horizon
from 6 azimuths (0–150°; azimuths 180° apart give the same edges, so these cover every direction),
detects edges with a Prewitt filter, clusters the edge pixels with DBSCAN, fits a straight line to
each cluster and finally merges nearby segments.</p>

<h2>Quick start</h2>
<ol>
 <li><b>Open a DEM</b>: <span class="key">Ctrl+O</span>, <i>File &gt; Open DEM</i>, or drag a
     GeoTIFF onto the window. JPEG/PNG images also work (coordinates are then in pixels).</li>
 <li><b>Check the tile grid</b> on the <i>Overview</i> tab. The DEM is processed in square tiles
     (<i>Tile size</i>). Click a tile to preview it.</li>
 <li><b>Preview and tune</b> on the <i>Tile preview</i> tab. Nothing is extracted when a DEM is
     opened: press <i>Preview</i> (<span class="key">F5</span>) to extract the lineaments of the
     selected tile. A yellow banner reminds you when the preview is missing or out of date.
     Tick <i>Auto preview</i> (off by default) to recompute automatically half a second after
     each parameter change.</li>
 <li><b>Run the extraction</b>: <span class="key">Ctrl+R</span> or <i>Run extraction…</i>.
     Choose the output shapefile. All tiles are processed in parallel; you can cancel at any time
     with <span class="key">Esc</span>.</li>
 <li><b>Inspect the results</b> on the <i>Results</i> tab (rose diagram, lengths) and on the
     <i>Overview</i>. The parameters are saved next to the shapefile as
     <code>&lt;name&gt;_params.json</code>.</li>
</ol>

<h2>The tabs</h2>
<h3>Overview</h3>
<p>The whole DEM as a hillshade, an elevation map, or an elevation map shaded by the hillshade
(<i>Elevation + hillshade</i>, the default), the tile grid (the selected tile is outlined),
the <b>preview lines</b> of the last previewed tile and the <b>extracted lineaments</b> of the
last full run. Each layer has a checkbox above the map. The status bar shows the coordinates,
elevation and tile under the cursor.</p>
<h3>Tile preview</h3>
<p>Shows each processing step for one tile:</p>
<ul>
 <li><b>Background</b>: the tile DEM (optionally shaded), the hillshade the algorithm sees
     (altitude 0°) for the chosen
     <b>Azimuth</b>, its Prewitt edge magnitude, or the Prewitt cut-off (&gt; 100) that defines
     edge pixels.</li>
 <li><b>Edge points</b>: edge pixels that survived clustering, coloured by the azimuth that found
     them. <i>this azimuth only</i> shows one azimuth at a time.</li>
 <li><b>Fitted lines</b>: one straight line per cluster.</li>
 <li><b>Final lines</b>: after merging and simplification. These are what the full run writes.</li>
</ul>
<p>The line under the map gives the number of points, clusters and lines, and the compute time.
The preview of a tile is identical to what the full extraction produces for that tile.</p>
<h3>Results</h3>
<p>Number of lineaments, total, mean and median length (km for geographic or metric CRSs), a rose
diagram of azimuths (10° bins, both directions) and a length histogram.
<i>Export CSV…</i> saves the attribute table.</p>

<h2>Parameters</h2>
{_param_table()}
<p><i>Worker processes</i> and <i>Keep intermediate files</i> only affect the full run, not the
preview. <i>Parameters &gt; Copy as Python</i> copies the equivalent
<code>pylineament.dem_to_shp(...)</code> call, which gives the same result in a notebook.</p>

<h2>Tuning tips</h2>
<ul>
 <li><b>Too many short, noisy lines</b>: raise <i>Min cluster size</i>, or lower the
     <i>Resample factor</i> (for example 0.5) to smooth small-scale relief.</li>
 <li><b>Too few lines</b>: lower <i>Min cluster size</i>, raise <i>Z multiplier</i> in flat
     terrain, or raise <i>DBSCAN eps</i> to join gaps between edge pixels.</li>
 <li><b>Lines broken into pieces</b>: raise <i>Merge distance</i> and <i>Segment length</i>.</li>
 <li><b>Orientation statistics</b>: use <i>Line fit = TLS</i> (total least squares: perpendicular instead of vertical
     distances). OLS (the v1.0.1 default) biases
     azimuths towards E–W.</li>
 <li><b>Slow preview</b>: a smaller <i>Tile size</i> or a lower <i>Resample factor</i> previews much
     faster. The window stays usable while a preview is computing.</li>
</ul>

<h2>Troubleshooting</h2>
<div class="tip"><b>"No line extracted"</b> under the preview means no cluster was large enough
or no edge pixel passed the Prewitt cut-off. Look at the <i>Prewitt cut-off</i> background: if it
is almost empty, raise the <i>Z multiplier</i>; if it is full but there are no points, lower
<i>Min cluster size</i>. Flat areas and areas at or below 10 m elevation (the library ignores them)
never give lines.</div>
<ul>
 <li>Every message, warning and error is written to the <b>Log</b> panel
     (<i>View &gt; Log</i>).</li>
 <li>If one tile fails during a run, the other tiles still finish and the failure is listed in the
     log and the Results summary.</li>
 <li>Lines are cut at tile edges because tiles do not overlap. Use a larger tile size if long
     lineaments matter.</li>
</ul>

<h2>Styles</h2>
<p><b>Topography</b>: choose the elevation <i>palette</i> (Terrain, Hypsometric, Grey, Viridis,
…, optionally reversed) and the <i>minimum</i> and <i>maximum</i> elevation it spans. The range is
set to the 2–98 % percentiles of the DEM when a file is opened; <i>Auto</i> and <i>Full range</i>
reset it. <i>Hillshade overlay</i> sets how strongly the hillshade shades the colours in the
<i>Elevation + hillshade</i> backgrounds (0 = colour only, 1 = fully shaded). These settings only
change the display, never the extraction.</p>
<p>The <i>Style</i> tab on the left also sets the colour (including transparency), width and dash style
of every line layer, and the symbol, size, opacity and colouring of the edge points. Styles are
remembered between sessions.</p>
"""


class HelpView(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenExternalLinks(True)
        self.setHtml(help_html())
