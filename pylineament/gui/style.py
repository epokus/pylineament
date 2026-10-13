"""Display styles for lines and points (plain dicts, so they serialise to JSON / QSettings)."""

import copy

# key -> (label, view it appears in, colour, width, line style)
LINE_LAYERS = {
    'final':            ('Final lines', 'Tile preview', '#ff1744', 2.0, 'solid'),
    'fitted':           ('Fitted lines', 'Tile preview', '#ff9f1a', 1.0, 'solid'),
    'preview_overview': ('Preview lines', 'Overview', '#00e676', 1.5, 'solid'),
    'result':           ('Extracted lineaments', 'Overview', '#ff1744', 1.2, 'solid'),
    'grid':             ('Tile grid', 'Overview', '#ffd400', 1.0, 'solid'),
    'selected':         ('Selected tile', 'Overview', '#00e5ff', 2.5, 'solid'),
}
LINE_STYLES = ['solid', 'dash', 'dot', 'dash-dot']
POINT_SYMBOLS = {'o': 'Circle', 's': 'Square', 't': 'Triangle', 'd': 'Diamond', '+': 'Plus',
                 'x': 'Cross'}
POINT_MODES = {'azimuth': 'By azimuth', 'single': 'Single colour'}

# one colour per hillshade azimuth used by extract_lineament_points (0, 30, ..., 330 degrees)
AZ_COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b',
             '#e377c2', '#17becf', '#bcbd22', '#7f7f7f', '#aec7e8', '#ffbb78']


def default_style():
    s = {k: {'color': c, 'width': w, 'style': st} for k, (_, _, c, w, st) in LINE_LAYERS.items()}
    s['points'] = {'symbol': 'o', 'size': 3.0, 'opacity': 1.0, 'mode': 'azimuth',
                   'color': '#ffffff'}
    return s


def merge_style(d):
    """Defaults overlaid with the valid entries of d (unknown or bad values are ignored)."""
    s = default_style()
    if not isinstance(d, dict):
        return s
    for key, spec in s.items():
        src = d.get(key)
        if not isinstance(src, dict):
            continue
        for k, v in src.items():
            if k in spec and type(v) in (type(spec[k]), int):
                spec[k] = type(spec[k])(v)
        if key == 'points':
            if spec['symbol'] not in POINT_SYMBOLS:
                spec['symbol'] = 'o'
            if spec['mode'] not in POINT_MODES:
                spec['mode'] = 'azimuth'
            spec['opacity'] = min(1.0, max(0.0, spec['opacity']))
        elif spec['style'] not in LINE_STYLES:
            spec['style'] = 'solid'
    return copy.deepcopy(s)


def point_colors(points_style):
    """Colour per azimuth index for the edge points."""
    if points_style['mode'] == 'single':
        return [points_style['color']] * len(AZ_COLORS)
    return list(AZ_COLORS)
