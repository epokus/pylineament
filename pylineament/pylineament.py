import pandas as pd 
import numpy as np
import glob
import fiona
import os
import pandas as pd 
import numpy as np
import rasterio


def read_raster(im_path, split_size=500):
    """
    Read and process a raster image (e.g., DEM).

    Parameters
    ----------
    im_path : str
        Path to the input raster file.
    split_size : int, optional
        Block size for splitting large rasters during processing (default is 500).

    Returns
    -------
    imageSplitting : pandas.DataFrame
        image subset coordinate and array slicing.
    dem : numpy.ndarray
        Digital Elevation Model array.
    extent : tuple
        Spatial extent of the raster (left, bottom, right, yop).
    crs_espg : int
        EPSG code of the raster’s coordinate reference system.
    """
    img_format = os.path.split(im_path)[-1].split('.')[-1]

    im_path = os.path.abspath(im_path)
    dataset = rasterio.open(im_path)
    try:
        crs_espg = dataset.crs.to_epsg()
        
    except:
        crs_espg = None

    e    = list(dataset.bounds), 
    extent = [e[0][0], e[0][2], e[0][1], e[0][3]]

    if dataset.count > 1:
        im = dataset.read().mean(axis=0)
    else:
        im  = dataset.read(1)

    shape = im.shape
    left, bottom, right, top = list(dataset.bounds)
    resX = (right-left)/im.shape[1]
    resY = (top-bottom)/im.shape[0]

    sz = split_size

    # print(shape, sz)

    if shape[0]<=sz:
        v_split = np.array([[0, shape[0]]])
    else:
        v_split = np.c_[np.arange(0, shape[0]-sz, sz), np.arange(0, shape[0]-sz, sz)+sz]
        v_split = np.vstack([v_split, [v_split[-1,-1],shape[0]] ])


    if shape[1]<=sz:
        h_split = np.array([[0, shape[1]]])
    else:
        h_split = np.c_[np.arange(0, shape[1]-sz, sz), np.arange(0, shape[1]-sz, sz)+sz]
        h_split = np.vstack([h_split, [h_split[-1,-1],shape[1]]])


    xx, yy = np.meshgrid(np.arange(len(v_split)), np.arange(len(h_split)))
    xx, yy = xx.flatten(), yy.flatten()

    grids  =  np.c_[ h_split[yy], v_split[xx],]
    '''grid format: [[L, R, B, T]] '''

    ns = np.arange(len(grids))
    lefts = [left]*len(grids)
    tops  = [top]*len(grids)
    resXs = [resX]*len(grids)
    resYs = [resY]*len(grids)
    szs   = [sz]*len(grids)

    imageSplitting = pd.DataFrame(zip(ns, lefts, tops, resXs, resYs, szs), columns=['ns', 'lefts', 'tops', 'resXs', 'resYs', 'szs'])
    
    imageSplitting[['L', 'R', 'B', 'T']] = grids

    imageSplitting['left_bound']    = imageSplitting['lefts'] + imageSplitting['L']*imageSplitting['resXs']
    imageSplitting['bottom_bound']    = imageSplitting['tops'] - imageSplitting['T']*imageSplitting['resYs']
    imageSplitting['right_bound']    = imageSplitting['left_bound'] + abs(imageSplitting['L'] - imageSplitting['R'])*imageSplitting['resXs']
    imageSplitting['top_bound']    = imageSplitting['bottom_bound'] + abs(imageSplitting['T'] - imageSplitting['B'])*imageSplitting['resYs']

    dem = im 

    return imageSplitting, dem, extent,crs_espg


def reduce_lines(lines, extent, dem_shape, min_dist=10, seg_len=10):

    """
    Simplify and merge extracted line segments to reduce redundancy.
    Parameters
    ----------
    lines : dataframes
        Extracted line segments.
    extent : tuple
        Raster extent used for spatial reference L B R T.
    dem_shape : tuple
        Shape of the DEM (rows, columns).
    min_dist : float, optional
        Minimum allowed distance between lines before merging (default is 10).
    seg_len : float, optional
        Minimum segment length to retain (default is 10).

    Returns
    -------
    initial_lines : list
        Original extracted lines.
    broken_lines_ : list
        Split or fragmented lines before reduction.
    reduced_lines : list
        Final reduced set of merged lineaments.
    """


    # frag lines

    d  = np.sqrt((lines['max_x'] - lines['min_x'])**2 + (lines['max_y'] - lines['min_y'])**2)
    dx =  lines['max_x'] - lines['min_x']
    dy =  lines['max_y'] - lines['min_y']
    m  = dy / dx
    c  = lines['max_y'] - m * lines['max_x']

    dr_dx = dx/d*seg_len

    # lines['d'] = d
    # lines['dx'] = dx
    # lines['dr_dx'] = d/dx

    lines['dr_dx'] = (dx/d)*seg_len
    lines['coef'] = m 
    lines['intercept'] = c 
    
    container = []

    for i in range(len(lines)):
        azi, clust, deg, xmin, xmax, ymin, ymax, dr_dx, coef, intercept = lines.iloc[i].values

        if (xmax != xmin) & (ymin != ymax):
            xs = np.arange(xmin, xmax+dr_dx, dr_dx)
            ys = coef*xs + intercept

            xs_a, xs_b = xs[:-1], xs[1:]
            ys_a, ys_b = ys[:-1], ys[1:]
            df_ = pd.DataFrame(np.c_[xs_a, xs_b, ys_a, ys_b], columns=['xs_a', 'xs_b', 'ys_a', 'ys_b'])
            df_[['quad', 'group', 'min_x', 'max_x', 'min_y', 'max_y', 'dr_dx', 'coef', 'intercept']] = azi, clust, xmin, xmax, ymin, ymax, dr_dx, coef, intercept
            container.append(df_)
            
    initial_lines = pd.concat(container)

    if len(initial_lines)>10:

        from sklearn.neighbors import KDTree
        
        tree= KDTree(initial_lines[['xs_a', 'xs_b', 'ys_a', 'ys_b']])
        dist, idxs = tree.query(initial_lines[['xs_a', 'xs_b', 'ys_a', 'ys_b']], k=10, return_distance=True)
        idxs = np.where(dist>min_dist,dist.shape[0]+1,idxs)

        keepit = np.unique(np.sort(idxs, axis=1)[:,0])
        broken_lines_ = initial_lines.iloc[keepit]
        # broken_lines_ = broken_lines.iloc[keepit].drop_duplicates(['azi', 'clust'])
    else:
        broken_lines_ = initial_lines

    
    container = []
    for quad in broken_lines_.quad.unique():
        temp = broken_lines_[broken_lines_.quad == quad]
        for group in temp.group.unique():

            temp = broken_lines_[(broken_lines_.quad == quad) & (broken_lines_.group == group)].sort_values('xs_a').reset_index(drop=True)

            min_x_ = temp.iloc[0]['xs_a']
            max_x_ = temp.iloc[-1]['xs_b']
            min_y_ = temp.iloc[0]['ys_a']
            max_y_ = temp.iloc[-1]['ys_b']

            L      = np.sqrt((max_x_ - min_x_)**2 + (max_y_ - min_y_)**2)
            deg    = -np.degrees(np.arctan((max_y_ - min_y_) / (max_x_ - min_x_)))+90
            container.append([quad, group, min_x_, max_x_, min_y_, max_y_, L, deg])
            
    reduced_lines = pd.DataFrame(container, columns=['quad', 'group', 'min_x', 'max_x', 'min_y', 'max_y', 'L', 'deg'])

    left, right, top, bot = extent
    
    reduced_lines['min_x_'] = reduced_lines['min_x']
    reduced_lines['max_x_'] = reduced_lines['max_x']

    reduced_lines['min_y_'] = reduced_lines['min_y']
    reduced_lines['max_y_'] = reduced_lines['max_y']


    reduced_lines['min_x'] = (reduced_lines['min_x']/dem_shape[1])*(right - left) + left
    reduced_lines['max_x'] = (reduced_lines['max_x']/dem_shape[1])*(right - left) + left

    reduced_lines['min_y'] = -(reduced_lines['min_y']/dem_shape[0])*(bot - top) + bot
    reduced_lines['max_y'] = -(reduced_lines['max_y']/dem_shape[0])*(bot - top) + bot
    reduced_lines['length'] = np.sqrt((reduced_lines['max_x'] - reduced_lines['min_x'])**2 + (reduced_lines['max_y'] - reduced_lines['min_y'])**2)

    return initial_lines, broken_lines_, reduced_lines


def extract_lineament_points(dem, eps=1.2, thresh=40,z_multip=1):
    """
    Detect edge points representing potential lineaments from a DEM.

    Parameters
    ----------
    dem : numpy.ndarray
        Input Digital Elevation Model.
    eps : float, optional
        Edge detection sensitivity parameter (default is 1.2).
    thresh : float, optional
        Threshold for edge classification (default is 40).
    z_multip : float, optional
        Vertical exaggeration factor for slope computation (default is 1).

    Returns
    -------
    container : list
        Container of extracted lineament points.
    im_prewitt : numpy.ndarray
        Image after applying Prewitt edge filter.
    im_prewitt_clip : numpy.ndarray
        Thresholded edge image highlighting lineament points.
    """

    from sklearn.cluster import DBSCAN
    # import rasterio
    from skimage.filters import prewitt
    import pandas as pd 
    import numpy as np

    container = []

    im_prewitt = None 
    im_prewitt_clip = None


    for num, deg in enumerate(range(0, 360, 30)):

        im = prewitt(hillshade(dem, deg, 0,z_multip))

        if num ==0:
            im_prewitt = im 

        im_ = np.where(im>100,1,0)
        im = np.where(im>100)
        im = np.c_[im[1], im[0]]

        if num ==0:
            im_prewitt_clip = im_

        try:
            db = DBSCAN(eps=eps, min_samples=3,leaf_size=50)
            pred = db.fit_predict(im)
        except:
            break

        flag = np.where(pred != -1)[0]

        im_ = im[flag]
        pred  = pred[flag]

        elev = dem[im_[:,1], im_[:,0]]
        flag = np.where(elev>10)[0]
        im_ = im_[flag]
        pred  = pred[flag].astype('int')
        elev = elev[flag]

        df = pd.DataFrame(np.c_[im_, pred, elev], columns=['X', 'Y', 'GROUP','elev'])
        
        temp        = df.groupby('GROUP').count().reset_index()
        good_points = temp[temp['X']>thresh]['GROUP'].values

        idx = df[['GROUP']].isin(good_points)
        idx = list(idx[idx['GROUP'] == True].index)

        df = df.iloc[idx]
        df['quad'] = num

        container.append(df)

    return container, im_prewitt, im_prewitt_clip


def convert_points_to_line(container):

    """
    Convert sets of edge points into connected line segments.

    Parameters
    ----------
    container : list
        Extracted lineament points grouped by proximity.

    Returns
    -------
    lines : dataFrame
        Line geometries derived from point clusters.
    """

    from sklearn.linear_model import LinearRegression

    if len(container)>0:
        linea = pd.concat(container)

        linea['GROUP'] = linea['GROUP'].astype('int')
        linea['quad'] = linea['quad'].astype('int')

        ugroup, uquad = linea['GROUP'].unique(), linea['quad'].unique()
        container  = []
        for g in ugroup:
            for q in uquad:
                temp = linea[(linea['GROUP'] == g) & (linea['quad'] == q)]

                if len(temp) == 0:
                    continue
                mla = LinearRegression()
                mla.fit(temp[['X']],temp['Y'])

                m            = mla.coef_[0]
                c            = mla.intercept_
                deg          = np.degrees(np.arctan(m))



                min_x1, max_x1 = np.nanpercentile(temp['X'],5), np.nanpercentile(temp['X'],95)
                min_y1, max_y1 = m*min_x1 + c, m*max_x1 + c

                container.append([q, g, deg, min_x1, max_x1, min_y1, max_y1])
                
    lines = pd.DataFrame(container, columns=['quad', 'group', 'deg', 
                                        'min_x', 'max_x', 'min_y', 'max_y',])
    
    return lines


def hillshade(array, azimuth=315, angle_altitude=45, z_multip=1):
    """
    Generate a hillshade image from a DEM for enhanced visualization.

    Parameters
    ----------
    array : numpy.ndarray
        DEM array.
    azimuth : float, optional
        Illumination azimuth in degrees (default is 315).
    angle_altitude : float, optional
        Illumination altitude angle in degrees (default is 45).
    z_multip : float, optional
        Vertical exaggeration multiplier (default is 1).

    Returns
    -------
    hs : numpy.ndarray
        Hillshaded representation of the DEM.
    """

    array = array*z_multip
    azimuth = 360.0 - azimuth  # Convert azimuth to geographic convention
    x, y = np.gradient(array)
    slope = np.pi / 2. - np.arctan(np.sqrt(x * x + y * y))
    aspect = np.arctan2(-x, y)
    azm_rad = azimuth * np.pi / 180.  # Convert azimuth to radians
    alt_rad = angle_altitude * np.pi / 180.  # Convert altitude to radians

    shaded = np.sin(alt_rad) * np.sin(slope) + np.cos(alt_rad) * np.cos(slope) * np.cos((azm_rad - np.pi / 2.) - aspect)
    hs = 255 * (shaded + 1) / 2  # Scale to 0-255


    
    return hs


def image_splitting(im_path='srtm/srtm_java.tif', split_size=500, tempfolder='temp'):
    
    """
    Split a large image or DEM into smaller tiles for efficient processing.

    Parameters
    ----------
    im_path : str, optional
        Path to the input raster file (default is 'srtm/srtm_java.tif').
    split_size : int, optional
        Tile size in pixels (default is 500).
    tempfolder : str, optional
        Temporary folder for saving image tiles (default is 'temp').

    Returns
    -------
    imageBoundaries : dataFrame
        List of boundaries or filenames for generated image tiles.
    """
    
    import pandas as pd 
    import numpy as np
    import rasterio


    dataset = rasterio.open(im_path)
    im  = dataset.read(1)
    shape = im.shape
    
    left, bottom, right, top = list(dataset.bounds)

    if (left == 0.0) and (top == 0.0):
        bottom = -bottom

    resX = (right-left)/im.shape[1]
    resY = (top-bottom)/im.shape[0]

    sz = split_size

    if shape[0]<=sz:
        v_split = np.array([[0, shape[0]]])
        # print('small', v_split)
    else:
        v_split = np.c_[np.arange(0, shape[0]-sz, sz), np.arange(0, shape[0]-sz, sz)+sz]
        # print('v_split \n', v_split)
        v_split = np.vstack([v_split, [v_split[-1,-1],shape[0]]])
        # print('v_split \n', v_split)


    if shape[1]<=sz:
        h_split = np.array([[0, shape[1]]])
        # print('small', h_split)

    else:
        h_split = np.c_[np.arange(0, shape[1]-sz, sz), np.arange(0, shape[1]-sz, sz)+sz]
        # print('h_split \n', h_split)
        h_split = np.vstack([h_split, [h_split[-1,-1],shape[1]]])
        # print('h_split \n', h_split)


    xx, yy = np.meshgrid(np.arange(len(v_split)), np.arange(len(h_split)))
    xx, yy = xx.flatten(), yy.flatten()

    grids  =  np.c_[ h_split[yy], v_split[xx],]
    '''grid format: [[L, R, B, T]] '''

    ns = np.arange(len(grids))
    target_folders = [tempfolder]*len(grids)
    lefts = [left]*len(grids)
    tops  = [top]*len(grids)
    resXs = [resX]*len(grids)
    resYs = [resY]*len(grids)
    szs   = [sz]*len(grids)

    imageBoundaries = pd.DataFrame(zip(ns, target_folders, lefts, tops, resXs, resYs, szs), columns=['ns', 'target_folders', 'lefts', 'tops', 'resXs', 'resYs', 'szs'])
    
    imageBoundaries[['L', 'R', 'B', 'T']] = grids

    for n, tempfolder, left, top, resX, resY, sz, L, R, B, T in imageBoundaries.values:
        l = left + L*resX
        # b = top - T*resY - sz*resY
        b = top - T*resY

        transform = rasterio.Affine.translation(l - resX / 2, b - resY / 2) * rasterio.Affine.scale(resX, resY)

        Z  = im[B:T, L:R].astype('float')
        Z  = Z[::-1]
        n_ = str(n).zfill(4)
        new_dataset = rasterio.open(
            f'{tempfolder}/{n_}.tiff',
            'w',
            driver='GTiff',
            height=Z.shape[0],
            width=Z.shape[1],
            count=1,
            dtype=Z.dtype,
            crs=dataset.crs,
            transform=transform,
        )
        new_dataset.write(Z, 1)
        new_dataset.close()

    imageBoundaries['left_bound']    = imageBoundaries['lefts'] + imageBoundaries['L']*imageBoundaries['resXs']
    imageBoundaries['bottom_bound']    = imageBoundaries['tops'] - imageBoundaries['T']*imageBoundaries['resYs']
    imageBoundaries['right_bound']    = imageBoundaries['left_bound'] + abs(imageBoundaries['L'] - imageBoundaries['R'])*imageBoundaries['resXs']
    imageBoundaries['top_bound']    = imageBoundaries['bottom_bound'] + abs(imageBoundaries['T'] - imageBoundaries['B'])*imageBoundaries['resYs']

    return imageBoundaries


def merge_lines_csv_to_shp(tempfolder, shppath, save_to_file):
    """
    Merge multiple lineament CSV outputs into a single shapefile.

    Parameters
    ----------
    tempfolder : str
        Directory containing intermediate CSV line data.
    shppath : str
        Path to the base shapefile used for spatial reference.
    save_to_file : str
        Output shapefile path.

    Returns
    -------
    lines : Dataframe
        Combined lineament data as a Dataframe.
    """

    flist = glob.glob(f'{tempfolder}/*.csv')

    all_lines = [pd.read_csv(f) for f in flist]

    lines = pd.concat(all_lines).reset_index(drop=True)
    lines = lines[['quad', 'group', 'min_x', 'max_x', 'min_y', 'max_y', 'L', 'deg', 'length', 'crs']]

    if save_to_file==True:
            
        crs_espg = lines['crs'].values[0]

        if type(crs_espg) != int:
            crs_espg = 4326

        crs_espg = f"EPSG:{crs_espg}"


        # if crs_espg != None:
        #     crs_espg = f"EPSG:{crs_espg}"
        # else:
        #     crs_espg = f"EPSG:{4326}"


        # crs_espg = f"EPSG:{crs_espg}"

        schema = {
            'geometry':'LineString',
            'properties':[('quad', 'int'),
                        ('group', 'int'),
                        ('deg', 'float'),
                        ('min_x', 'float'),
                        ('max_x', 'float'),
                        ('min_y', 'float'),
                        ('max_y', 'float'),
                        ('length', 'float')]
        }

        lineShp = fiona.open(shppath, mode='w', driver='ESRI Shapefile',
                schema = schema, crs = crs_espg)

        for quad, group,min_x, max_x, min_y, max_y, L_px,  deg, L_crs, crs in lines.values:
            g = ([(min_x, min_y), (max_x, max_y)])
            rowDict = {
            'geometry' : {'type':'LineString',
                        'coordinates': g},
            'properties': {'quad' : quad,
                            'group' : group,
                            'min_x' : min_x,
                            'max_x' : max_x,
                            'min_y' : min_y,
                            'max_y' : max_y,
                            'length' : L_crs,
                            'deg' : deg,}}
            lineShp.write(rowDict)

        lineShp.close()

    return lines


def merge_single_csv_to_shp(fname, shppath, save_to_file):
    """
    Merge a single CSV lineament file into a shapefile.

    Parameters
    ----------
    fname : str
        Path to the CSV file containing lineament data.
    shppath : str
        Path to reference shapefile for coordinate system.
    save_to_file : str
        Output shapefile path.

    Returns
    -------
    lines : dataFrame
        Converted lineament data as shapefile.
    """


    lines = pd.read_csv(fname)

    lines = lines[['quad', 'group', 'min_x', 'max_x', 'min_y', 'max_y', 'L', 'deg', 'length', 'crs']]

    crs_espg = lines['crs'].values[0]

    if save_to_file == True:
        
        schema = {
            'geometry':'LineString',
            'properties':[('quad', 'int'),
                        ('group', 'int'),
                        ('min_x', 'float'),
                        ('max_x', 'float'),
                        ('min_y', 'float'),
                        ('max_y', 'float'),
                        ('length', 'float'),
                        ('deg', 'float'),]
        }

        lineShp = fiona.open(shppath, mode='w', driver='ESRI Shapefile',
                schema = schema, crs = f"EPSG:{crs_espg}")

        for quad, group,min_x, max_x, min_y, max_y, L_px,  deg, L_crs, crs in lines.values:
            g = ([(min_x, min_y), (max_x, max_y)])
            rowDict = {
            'geometry' : {'type':'LineString',
                        'coordinates': g},
            'properties': {'quad' : quad,
                            'group' : group,
                            'min_x' : min_x,
                            'max_x' : max_x,
                            'min_y' : min_y,
                            'max_y' : max_y,
                            'length' : L_crs,
                            'deg' : deg,}}
            
            lineShp.write(rowDict)

        lineShp.close()

    return lines


def raster_resize (dem, factor=1):
    """
    Resize or downscale a DEM array.

    Parameters
    ----------
    dem : numpy.ndarray
        Input DEM array.
    factor : float, optional
        Rescaling factor (e.g., 0.5 reduces size by half, default is 1).

    Returns
    -------
    dem : numpy.ndarray
        Rescaled DEM array.
    """

    from skimage.transform import rescale 

    dem = dem

    dem_min, dem_max = dem.min(), dem.max()

    dem_ = rescale(dem, factor, anti_aliasing=True)

    dem2_min, dem2_max = dem_.min(), dem_.max()

    if (dem_min != dem2_min) & (dem_max != dem2_max) :
        dem_ = (dem_ - dem2_min)/(dem2_max - dem2_min)
        dem_ = dem_min + dem_*(dem_max-dem_min)

        return dem_
    
    else:
        return dem


def dem_to_line(path, 
                tempfolder='temp', 
                eps=1.2, 
                thresh=40, 
                min_dist=10, 
                seg_len=10,
                z_multip=1.0,
                downscale = 1.0,
                save_csv = False):
    """
    Extract lineaments directly from a DEM and return line features.

    Parameters
    ----------
    path : str
        Path to input DEM file.
    tempfolder : str, optional
        Folder for temporary outputs (default is 'temp').
    eps : float, optional
        Edge detection sensitivity (default is 1.2).
    thresh : float, optional
        Edge threshold for filtering (default is 40).
    min_dist : float, optional
        Minimum distance between line segments for merging (default is 10).
    seg_len : float, optional
        Minimum segment length (default is 10).
    z_multip : float, optional
        Vertical exaggeration multiplier (default is 1.0).
    downscale : float, optional
        DEM downscaling factor (default is 1.0).
    save_csv : bool, optional
        Save intermediate line data to CSV (default is False).

    Returns
    -------
    dem : numpy.ndarray
        Processed DEM array.
    extent : tuple
        Raster extent (Left, Bottom, Right, Top).
    lines : dataFrame
        Extracted lineament features.
    im_prewitt : numpy.ndarray
        Prewitt-filtered edge image.
    im_prewitt_clip : numpy.ndarray
        Thresholded edge map.
    container : list
        Intermediate lineament point container.
    """


    path = os.path.normpath(path)
    
    regions, dem, extent,crs_espg  = read_raster(path)

    dem = raster_resize(dem, factor=downscale)

    container, im_prewitt, im_prewitt_clip = extract_lineament_points(dem, 
                                                                      eps=eps, 
                                                                      thresh=thresh,
                                                                      z_multip=z_multip)

    lines     = convert_points_to_line(container)

    if len(lines) > 0:
        _,_,lines = reduce_lines(lines, extent=extent, dem_shape=dem.shape, min_dist=min_dist, seg_len=seg_len)
        fname  = path.split('\\')[-1].split('.')[0]
        # fname  = path.replace('.tiff', '.csv')
        lines['crs'] = crs_espg
        if save_csv:
            lines.to_csv(f'{tempfolder}\\{fname}.csv', index=False)
        return dem, extent, lines, im_prewitt, im_prewitt_clip, container
    
    else:
        lines['crs'] = crs_espg
        return dem, extent, lines, im_prewitt, im_prewitt_clip, container


def dem_to_shp(im_path, 
                tempfolder='temp', 
                eps=1.2, 
                thresh=40, 
                min_dist=10, 
                seg_len=10, 
                split_size=500, 
                z_multip=1,
                downscale = 1,
                shp_name = None,
                save_to_file=True,

                keep_intermediate_file = False):
    """
    Extract lineaments from a (large) DEM and export results as a shapefile. 
    This will involve image splitting, and the use of parallel computing to achieve calculation efficiency.

    Parameters
    ----------
    im_path : str
        Path to input DEM.
    tempfolder : str, optional
        Folder for temporary files (default is 'temp').
    eps : float, optional
        Edge detection sensitivity (default is 1.2).
    thresh : float, optional
        Edge threshold value (default is 40).
    min_dist : float, optional
        Minimum distance between lines (default is 10).
    seg_len : float, optional
        Minimum line segment length (default is 10).
    split_size : int, optional
        DEM tile size for splitting (default is 500).
    z_multip : float, optional
        Vertical exaggeration factor (default is 1).
    downscale : float, optional
        Downscaling factor for DEM (default is 1).
    shp_name : str, optional
        Output shapefile name.
    save_to_file : bool, optional
        Whether to save shapefile to disk (default is True).
    keep_intermediate_file : bool, optional
        Retain temporary files (default is False).

    Returns
    -------
    lines : dataFrame
        Extracted lineament shapefile.
    """
    
    im_path = os.path.normpath(im_path)

    if os.path.isdir(tempfolder):
        'delete content' 
        files = glob.glob(f'{tempfolder}/*')
        for f in files:
            os.remove(f)
    else:
        'create new folder'
        os.mkdir(tempfolder)


    image_splitting(im_path=im_path, split_size=split_size, tempfolder=tempfolder)

    flist = glob.glob(f'{tempfolder}/*.tiff')
    cases = pd.DataFrame(zip(flist, 
                             [tempfolder]*len(flist), 
                             [eps]*len(flist), 
                             [thresh]*len(flist), 
                             [min_dist]*len(flist), 
                             [seg_len]*len(flist), 
                             [z_multip]*len(flist),
                             [downscale]*len(flist),
                             [True]*len(flist))).values

    from joblib import Parallel, delayed
    Parallel(n_jobs=-1)(delayed(dem_to_line)(*c) for c in cases)

    fname = im_path.split('\\')[-1].split('.')[0]
    csv_name  = f'{tempfolder}\\{fname}.csv'
    
    if shp_name == None:
        shp_name  = f'{fname}'

    df = merge_lines_csv_to_shp(tempfolder=tempfolder, 
                                shppath=shp_name, 
                                save_to_file=save_to_file)
    

    if keep_intermediate_file == False:

        if os.path.isdir(tempfolder):
            'delete content' 
            files = glob.glob(f'{tempfolder}/*')
            for f in files:
                os.remove(f)
            os.removedirs(tempfolder)

    return df


def dem_to_shp_small(im_path, 
                     tempfolder='temp', 
                     eps=1.2, 
                     thresh=40, 
                     min_dist=10, 
                     seg_len=10, 
                     z_multip=1,
                     downscale=1,
                     shp_name=None, 
                     save_to_file=True):
    
    """
    Extract lineaments from a (small) DEM and export results as a shapefile. 
    The image will not splited, and be run as single chunk. This process only use single core, 
    therefore calculation for large dataset will took very long time.

    Parameters
    ----------
    im_path : str
        Path to the input DEM file.
    tempfolder : str, optional
        Folder for temporary outputs (default is 'temp').
    eps : float, optional
        Edge detection sensitivity (default is 1.2).
    thresh : float, optional
        Edge threshold value (default is 40).
    min_dist : float, optional
        Minimum distance between line segments (default is 10).
    seg_len : float, optional
        Minimum segment length (default is 10).
    z_multip : float, optional
        Vertical exaggeration multiplier (default is 1).
    downscale : float, optional
        DEM downscaling factor (default is 1).
    shp_name : str, optional
        Output shapefile name.
    save_to_file : bool, optional
        Whether to save shapefile to disk (default is True).

    Returns
    -------
    lines : dataFrame
        Extracted lineament features.
    """

    im_path = os.path.normpath(im_path)
    if os.path.isdir(tempfolder):
        'delete content' 
        files = glob.glob(f'{tempfolder}/*')
        for f in files:
            os.remove(f)
    else:
        'create new folder'
        os.mkdir(tempfolder)
    print(im_path)
    dem, extent, lines, im_prewitt, im_prewitt_clip, container  = dem_to_line(im_path, 
                                                                              tempfolder=tempfolder, 
                                                                              eps=eps, 
                                                                              thresh=thresh, 
                                                                              min_dist=min_dist, 
                                                                              seg_len=seg_len,
                                                                              z_multip=z_multip,
                                                                              downscale=downscale,
                                                                              save_csv=True)
    
    fname = im_path.split('\\')[-1].split('.')[0]
    csv_name  = f'{tempfolder}\\{fname}.csv'
    
    if shp_name == None:
        shp_name  = f'{fname}'


    merge_single_csv_to_shp(csv_name, shp_name, save_to_file)

    if os.path.isdir(tempfolder):
        'delete content' 
        files = glob.glob(f'{tempfolder}/*')
        for f in files:
            os.remove(f)
        os.removedirs(tempfolder)


    return lines

