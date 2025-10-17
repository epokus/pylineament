import sys
import numpy as np
import pyqtgraph as pg
from PyQt5.QtWidgets import (QApplication, 
                             QMainWindow, 
                             QWidget, 
                             QVBoxLayout, 
                             QPushButton, 
                             QFileDialog, 
                             QTabWidget,  
                             QHBoxLayout, 
                             QSlider, 
                             QLabel, 
                             QComboBox,
                             QCheckBox, 
                             QSplitter )

from PyQt5.QtCore import QThreadPool, QRunnable


from skimage.transform import rescale

from PyQt5.QtCore import Qt

import numpy as np
import pandas as pd
from pylineament import (dem_to_line, 
                         read_raster,
                         extract_lineament_points,
                         convert_points_to_line,
                         reduce_lines,
                         merge_lines_csv_to_shp, 
                         hillshade)
import os 


class ImageSplitterParallel(QRunnable):
    def __init__(self, i, crs, im, transform ,temp_folder):
        super().__init__()
        
        self.i = i

        self.n_ = i
        self.crs = crs 
        self.im = im
        self.transform = transform
        self.temp_folder = temp_folder


    def run(self):
        import rasterio
        import os 

        n_ = str(self.n_ ).zfill(5) +'.tiff'

        Z = self.im

        new_dataset = rasterio.open(
            os.path.normpath(rf'{self.temp_folder}\{n_}'),
            'w',
            driver='GTiff',
            height=Z.shape[0],
            width=Z.shape[1],
            count=1,
            dtype=Z.dtype,
            crs=self.crs,
            transform=self.transform,
            )
            
        new_dataset.write(Z, 1)
        new_dataset.close()


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.threadpool = QThreadPool.globalInstance()
        self.setWindowTitle("Lineamentor - Lineament Extractor form large DEM")
        # self.setGeometry(100, 100, 800, 600)


        self.mainWidget = QWidget()
        self.mainLayout = QHBoxLayout(self.mainWidget)

        self.dem = None

        self.setCentralWidget(self.mainWidget)

        self.initLayout()

        self.addFunctions()


    def addFunctions(self):
        self.openImageButton.clicked.connect(self.openFileAction)
        self.subsetSideSlider.valueChanged.connect(self.gridUpdateAction)
        self.resetButton.clicked.connect(self.resetAction)
        self.previewRegen.clicked.connect(self.previewRegenActionAndSmallCalc)
        self.extractButon.clicked.connect(self.extractLineamentAction)

        self.previewImageOverlaySelector.currentIndexChanged.connect(self.previewRegenAction)
        self.previewRegionSelector.currentIndexChanged.connect(self.previewRegenAction)
        self.hillshadeAngleSelector.currentIndexChanged.connect(self.previewRegenAction)

        self.previewRegionPointCheckbox.stateChanged.connect(self.previewRegenAction)
        self.previewRegionLineDenseCheckbox.stateChanged.connect(self.previewRegenAction)
        self.previewRegionLineCleanCheckbox.stateChanged.connect(self.previewRegenAction)



    def initLayout(self):

        middleSplitter = QSplitter()

        self.mainLayout.addWidget(middleSplitter)


        leftWidget = QWidget()
        rightWidget = QWidget()
        previewBigWidget = QWidget()
        previewSmallWidget = QWidget()

        leftLayout = QVBoxLayout(leftWidget)
        rightLayout = QVBoxLayout(rightWidget)
        righTab = QTabWidget()

        previewBigLayout = QVBoxLayout(previewBigWidget)
        previewSmallLayout = QVBoxLayout(previewSmallWidget)

        middleSplitter.addWidget(leftWidget)
        middleSplitter.addWidget(rightWidget)

        rightLayout.addWidget(righTab)


        righTab.addTab(previewBigWidget, 'overview', )
        righTab.addTab(previewSmallWidget, 'extraction preview', )

        # rightLayout.addLayout()

        self.openImageButton = QPushButton('open image')
        self.keepIntermediateCheckbox = QCheckBox()
        keepIntermediatelayout = QHBoxLayout()
        keepIntermediatelayout.addWidget(self.keepIntermediateCheckbox)
        keepIntermediatelayout.addWidget(QLabel('keep intermediate file'))


        self.resetButton = QPushButton('Reset to Default')
        self.previewRegen = QPushButton('Regenerate Preview')
        self.extractButon = QPushButton('Extract Lineament')

        self.subsetSideSlider, subsetSideLabel, subsetSideLayout = self.add_slider("Image Subset size", 500, 100, 2000, 50)
        self.downsampleSlider, downsampleLabel, downsampleLayout = self.add_slider("Downsample Factor", 1, 1, 20, 0.1)
        self.hillshadeZSlider, hillshadeZLabel, hillshadeZLayout  = self.add_slider("Hillshade Z", 0, -5, 5, 1,log=True)
        self.epsSlider, epsLabel, epsLayout  = self.add_slider("Eps", 1.2, 0.2, 4, 0.1)
        self.threshSlider, threshLabel, threshLayout  = self.add_slider("Thresh", 40, 10, 200, 1)
        self.minDistSlider, minDistLabel, minDistLayout  = self.add_slider("Min Dist", 10, 2, 100, 1)
        self.segLenSlider, segLenLabel, segLenLayout = self.add_slider("Seg Len", 10, 2, 100, 1)

        self.sliders = [self.subsetSideSlider, self.downsampleSlider, 
                        self.hillshadeZSlider, self.epsSlider, self.threshSlider, 
                        self.minDistSlider, self.segLenSlider, ]

        

        self.previewImageOverlaySelector = QComboBox()
        self.previewImageOverlaySelector.addItems(['orginial image', 
                                             'Downscaled image', 
                                             'Prewitt Filters',
                                             'Prewitt Filters Cutoff',
                                             'Hillshade',
                                             ])
        
        self.previewRegionSelector = QComboBox()
        self.previewRegionSelector.addItems(['0'])
        
        self.hillshadeAngleSelector = QComboBox()

        n = 16
        d = 360/n
        for i in range(0, n):
            deg1 = i*d
            deg2 = deg1 + d
            self.hillshadeAngleSelector.addItem(f'{deg1} - {deg2}')



        previewSmallMenuWidget = QWidget()
        previewSmallMenuWidget.setFixedHeight(120)
        previewSmallMenuLayout = QHBoxLayout(previewSmallMenuWidget)

        previewSmallLayout.addWidget(previewSmallMenuWidget)
        

        col1previewSmallMenuLayout = QVBoxLayout()
        col2previewSmallMenuLayout = QVBoxLayout()
        col3previewSmallMenuLayout = QVBoxLayout()

        previewSmallMenuLayout.addLayout(col1previewSmallMenuLayout)
        previewSmallMenuLayout.addLayout(col2previewSmallMenuLayout)
        previewSmallMenuLayout.addLayout(col3previewSmallMenuLayout)

        previewSmallMenuLayout.addStretch()

        def createLabelCheckbox(labelText:str):
            label = QLabel(f'{labelText}')
            checkbox = QCheckBox()
            layout = QHBoxLayout()
            layout.addWidget(checkbox)
            layout.addWidget(label)

            return checkbox, layout
        
        self.previewRegionPointCheckbox, previewRegionPointLayout = createLabelCheckbox('Show/hide Extracted Point Features')
        self.previewRegionLineDenseCheckbox, previewRegionLineDenseLayout = createLabelCheckbox('Show/hide Generate Lines Features')
        self.previewRegionLineCleanCheckbox, previewRegionLineCleanLayout = createLabelCheckbox('Show/hide Aggregated Lines Features')

        self.previewRegionPointCheckbox.setChecked(False)
        self.previewRegionLineDenseCheckbox.setChecked(False)
        self.previewRegionLineCleanCheckbox.setChecked(True)


        # col1previewSmallMenuLayout.addWidget()

        col1previewSmallMenuLayout.addWidget(QLabel('Preview Region Selector:'))
        col1previewSmallMenuLayout.addWidget(self.previewRegionSelector)

        col1previewSmallMenuLayout.addWidget(QLabel('Hillshade Angle Selector:'))
        col1previewSmallMenuLayout.addWidget(self.hillshadeAngleSelector)


        col2previewSmallMenuLayout.addStretch()
        col2previewSmallMenuLayout.addWidget(QLabel('Preview Image overlay:'))
        col2previewSmallMenuLayout.addWidget(self.previewImageOverlaySelector)
        col2previewSmallMenuLayout.addLayout(previewRegionPointLayout)
        col2previewSmallMenuLayout.addLayout(previewRegionLineDenseLayout)
        col2previewSmallMenuLayout.addLayout(previewRegionLineCleanLayout)

        col3previewSmallMenuLayout.addStretch()
        col3previewSmallMenuLayout.addWidget(self.previewRegen)


        leftLayout.addWidget(self.openImageButton)
        leftLayout.addLayout(keepIntermediatelayout)

        leftLayout.addLayout(subsetSideLayout)
        leftLayout.addLayout(downsampleLayout)
        leftLayout.addLayout(hillshadeZLayout)
        leftLayout.addLayout(epsLayout)
        leftLayout.addLayout(threshLayout)
        leftLayout.addLayout(minDistLayout)
        leftLayout.addLayout(segLenLayout)

        leftLayout.addWidget(self.resetButton)
        # leftLayout.addWidget(self.previewRegen)
        leftLayout.addStretch()
        leftLayout.addWidget(self.extractButon)


        
        self.previewBigImg = pg.plot()
        self.previewBigImg.setAspectLocked(True)
        previewBigLayout.addWidget(self.previewBigImg)

        self.previewSmallImg = pg.plot()
        self.previewSmallImg.setAspectLocked(True)
        previewSmallLayout.addWidget(self.previewSmallImg)


    def loadImageAndPreview(self):
        sz     = self.subsetSideSlider.value() * self.subsetSideSlider.step


        self.regions, self.dem, self.extent, self.crs_espg = read_raster(self.file_name, split_size=sz)

        imgFormat = self.file_name.split('.')[-1]
        if (imgFormat == 'jpg') or (imgFormat == 'jpeg'):
            from PIL import Image
            i = Image.open( r"C:\Users\user\Downloads\WhatsApp Image 2025-09-23 at 16.34.01.jpeg" )
            self.orgImg = np.transpose(np.array(i),( 1,0,2))[:,::-1]

        else:

            self.orgImg = self.dem[::-1].T

        L,R,B,T = self.extent

        if (L == 0) & (T==0):
            L,R,T,B = self.extent


        W, H    = abs(L-R), abs(B-T)
        # img = pg.ImageItem(self.dem[::-1].T)
        img = pg.ImageItem(self.orgImg)

        img.setRect(L,B,W,H)

        self.previewBigImg.clear()
        self.previewBigImg.addItem(img)

        xarr = []
        yarr = []

        for l,b,r,t in self.regions.values[:,-4:]:
            xarr = xarr + [l, r, r, l, l] 
            yarr = yarr + [t, t, b, b, t] 

        xarr = np.array(xarr)
        yarr = np.array(yarr)
        conn = np.ones_like(xarr,dtype=bool)

        conn[4::5] = 0

        girdArr = pg.arrayToQPath(xarr, yarr, connect=conn)
        
        self.girditem = pg.QtWidgets.QGraphicsPathItem(girdArr)
        self.girditem.setPen(pg.mkPen('y', width=1))
        self.previewBigImg.addItem(self.girditem)

        self.tx_plot_collection = []

        for num, (l,b,r,t) in enumerate(self.regions.values[:,-4:]):
            tx = pg.TextItem(str(num).zfill(5), color='yellow',anchor=(0.5,0.5))
            tx.setPos((l+r)/2, (t+b)/2)
            self.tx_plot_collection.append(tx)

            self.previewBigImg.addItem(tx)

        self.previewBigImg.enableAutoRange()


        self.previewRegionSelector.clear()
        self.previewRegionSelector.addItems([str(n).zfill(5) for n in range(len(self.regions))])

        self.previewRegenAction()

    
    def gridUpdateAction(self):
   
        sz     = self.subsetSideSlider.value() * self.subsetSideSlider.step

        shape = self.dem.shape
        left, bottom, right, top = self.extent[0], self.extent[2], self.extent[1], self.extent[3]
        resX = (right-left)/self.dem.shape[1]
        resY = (top-bottom)/self.dem.shape[0]


        v_split = np.c_[np.arange(0, shape[0]-sz, sz), np.arange(0, shape[0]-sz, sz)+sz]
        v_split = np.vstack([v_split, [v_split[-1,-1],shape[0]]])


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

        self.regions = pd.DataFrame(zip(ns, lefts, tops, resXs, resYs, szs), columns=['ns', 'lefts', 'tops', 'resXs', 'resYs', 'szs'])
        
        self.regions[['L', 'R', 'B', 'T']] = grids

        self.regions['left_bound']    = self.regions['lefts'] + self.regions['L']*self.regions['resXs']
        self.regions['bottom_bound']    = self.regions['tops'] - self.regions['T']*self.regions['resYs']
        self.regions['right_bound']    = self.regions['left_bound'] + abs(self.regions['L'] - self.regions['R'])*self.regions['resXs']
        self.regions['top_bound']    = self.regions['bottom_bound'] + abs(self.regions['T'] - self.regions['B'])*self.regions['resYs']
        
        xarr = []
        yarr = []


        for tx in self.tx_plot_collection:
            tx.setText('')

        for num, (l,b,r,t) in enumerate(self.regions.values[:,-4:]):
            xarr = xarr + [l, r, r, l, l] 
            yarr = yarr + [t, t, b, b, t]

            if num<len(self.tx_plot_collection):
                tx = self.tx_plot_collection[num]
                tx.setText(str(num).zfill(5))
                tx.setPos((l+r)/2, (t+b)/2)

            else:
                tx = pg.TextItem(str(num).zfill(5), color='yellow',anchor=(0.5,0.5))
                tx.setPos((l+r)/2, (t+b)/2)
                self.previewBigImg.addItem(tx)
                self.tx_plot_collection.append(tx)

            # tx = pg.TextItem(str(num).zfill(5), color='yellow',anchor=(0.5,0.5))
            # tx.setPos((l+r)/2, (t+b)/2)
            # tx.setAnchor
        xarr = np.array(xarr)
        yarr = np.array(yarr)
        conn = np.ones_like(xarr,dtype=bool)

        conn[4::5] = 0

        p = pg.arrayToQPath(xarr, yarr, connect=conn)

        self.girditem.setPath(p)

        self.previewRegionSelector.clear()
        self.previewRegionSelector.addItems([str(n).zfill(5) for n in range(len(self.regions))])


    def openFileAction(self):
        options = QFileDialog.Options()
        self.file_name, _ = QFileDialog.getOpenFileName(self, "Open File", "", "Georeferenced image (*.tif);;Georeferenced image (*.tiff);;Non Georef image (*.jpeg);;Non Georef image (*.jpg)", options=options)
        if self.file_name:
            self.loadImageAndPreview()


    def resetAction(self):

        self.keepIntermediateCheckbox.setChecked(False)
        for it in self.sliders:
            it.setValue(int(it.default / it.step))


    def previewRegenActionAndSmallCalc(self):
        self.smallCalc()
        self.previewRegenAction()


    def previewRegenAction(self):
        self.previewSmallImg.clear()
        self.getImageSubset()


        overlay = self.previewImageOverlaySelector.currentText()
        hs = self.hillshadeAngleSelector.currentText()
        hs = hs.replace(' ', '').split('-')
        avgAng = (float(hs[0]) + float(hs[1])) /2


        if overlay == 'original image':
            img = self.demSubset

        elif overlay == 'Prewitt Filters':
            img = self.im_prewitt

        elif overlay == 'Prewitt Filters Cutoff':
            img = self.im_prewitt_clip

        elif overlay == 'Hillshade':
            z_multip = round(10**(self.hillshadeZSlider.value() * self.hillshadeZSlider.step),5)
            img = hillshade(self.demSubset, azimuth=avgAng, z_multip=z_multip)

        else:
            img = self.demSubset
        
        subImg       = pg.ImageItem(img.T[:,::-1])
        self.previewSmallImg.addItem(subImg)

        showPoints = self.previewRegionPointCheckbox.checkState() > 0
        showLine = self.previewRegionLineDenseCheckbox.checkState() > 0
        showcleanLine = self.previewRegionLineCleanCheckbox.checkState() > 0

        c = [(202, 174, 209),
                (203, 51, 10),
                (62, 145, 52),
                (187, 97, 69),
                (148, 46, 4),
                (63, 117, 56),
                (68, 204, 91),
                (5, 55, 99),
                (16, 21, 21),
                (39, 107, 151), 
                (202, 174, 209),
                (203, 51, 10),
                (62, 145, 52),
                (187, 97, 69),
                (148, 46, 4),
                (63, 117, 56),
                (68, 204, 91),
                (5, 55, 99),
                (16, 21, 21),
                (39, 107, 151)]
        

        if showPoints:
            for num, df in enumerate(self.container):
                p = pg.ScatterPlotItem(df['X'], img.shape[0]-df['Y'], 
                                    pen = None, 
                                    brush=c[num],
                                    symbol ='o', 
                                    size = 5, 
                                    name =f'quadrant: {num}')
                p.setBrush(c[num])
                p.setPen(None)

                self.previewSmallImg.addItem(p)

        if showLine:
            self.line_all = pg.QtWidgets.QGraphicsPathItem()
            self.line_all.setPen(pg.mkPen('r', width=3))

            lines_ = self.lines[['min_x', 'max_x', 'min_y', 'max_y']].values
            xarr_line = np.ones(len(lines_)*2)
            yarr_line = np.ones(len(lines_)*2)
            conn_line = np.ones(len(lines_)*2)
            xarr_line[::2] = lines_[:,0]
            xarr_line[1::2] = lines_[:,1]
            yarr_line[::2] = lines_[:,2]
            yarr_line[1::2] = lines_[:,3]
            conn_line[1::2] = 0
            line_plot = pg.arrayToQPath(xarr_line, img.shape[0]-yarr_line, connect=conn_line)
            self.line_all.setPath(line_plot)
            self.previewSmallImg.addItem(self.line_all)

        if showcleanLine:

            self.line_all_sieve = pg.QtWidgets.QGraphicsPathItem()
            self.line_all_sieve.setPen(pg.mkPen('b', width=3))

            lines_ = self.broken_lines[['min_x', 'max_x', 'min_y', 'max_y']].values
            xarr_line = np.ones(len(lines_)*2)
            yarr_line = np.ones(len(lines_)*2)
            conn_line = np.ones(len(lines_)*2)
            xarr_line[::2] = lines_[:,0]
            xarr_line[1::2] = lines_[:,1]
            yarr_line[::2] = lines_[:,2]
            yarr_line[1::2] = lines_[:,3]
            conn_line[1::2] = 0
            line_plot = pg.arrayToQPath(xarr_line, img.shape[0]-yarr_line, connect=conn_line)
            self.line_all_sieve.setPath(line_plot)
            self.previewSmallImg.addItem(self.line_all_sieve)
        
        self.previewSmallImg.enableAutoRange()


    def getImageSubset(self):

        sz = self.subsetSideSlider.value() * self.subsetSideSlider.step
        z_multip = round(10**(self.hillshadeZSlider.value() * self.hillshadeZSlider.step),5)
        eps = self.epsSlider.value() * self.epsSlider.step
        thresh = self.threshSlider.value() * self.threshSlider.step
        min_dist = self.minDistSlider.value() * self.minDistSlider.step
        seg_len = self.segLenSlider.value() * self.segLenSlider.step
        downsacale = self.downsampleSlider.value() * self.downsampleSlider.step
        
        selected_region = int(self.previewRegionSelector.currentText())
        curr = self.regions[self.regions['ns'] == selected_region]

        curr           = self.regions.iloc[selected_region]

        L, R, B, T = int(curr['L']), int(curr['R']), int(curr['B']), int(curr['T'])

        dem = self.dem[B:T, L:R]
        self.demSubsetOrig = dem.copy()
        dem_min, dem_max = dem.min(), dem.max()
        dem = rescale(dem, 1/downsacale, anti_aliasing=False)
        dem2_min, dem2_max = dem.min(), dem.max()
        dem = (dem - dem2_min)/(dem2_max - dem2_min)
        dem = dem_min + dem*(dem_max-dem_min)
        self.demSubset = dem.copy()


    def smallCalc(self):
        
        sz = self.subsetSideSlider.value() * self.subsetSideSlider.step
        z_multip = round(10**(self.hillshadeZSlider.value() * self.hillshadeZSlider.step),5)
        eps = self.epsSlider.value() * self.epsSlider.step
        thresh = self.threshSlider.value() * self.threshSlider.step
        min_dist = self.minDistSlider.value() * self.minDistSlider.step
        seg_len = self.segLenSlider.value() * self.segLenSlider.step
        downsacale = self.downsampleSlider.value() * self.downsampleSlider.step
        
        selected_region = int(self.previewRegionSelector.currentText())
        curr = self.regions[self.regions['ns'] == selected_region]

        curr           = self.regions.iloc[selected_region]

        L, R, B, T = int(curr['L']), int(curr['R']), int(curr['B']), int(curr['T'])

        # dem = self.dem[B:T, L:R]
        self.getImageSubset()


        extent = [0, self.demSubset.shape[1], self.demSubset.shape[0],0]

        self.container, self.im_prewitt, self.im_prewitt_clip =extract_lineament_points(self.demSubset, 
                                                                        eps=eps, 
                                                                        thresh=thresh,
                                                                        z_multip=z_multip)
        self.lines = convert_points_to_line(self.container)

        _,_, self.broken_lines = reduce_lines(self.lines, extent, 
                                            self.demSubset.shape,
                                            min_dist=min_dist,
                                            seg_len=seg_len)


    def add_slider(self, name, default, min_val, max_val, step, log=False):

        if log:
            label = QLabel(f"{name}: {10**default}")
        else:
            label = QLabel(f"{name}: {default}")

        slider = QSlider(Qt.Horizontal)
        slider.setMinimum(int(min_val / step))
        slider.setMaximum(int(max_val / step))
        slider.setValue(int(default / step))
        slider.setTickInterval(1)
        slider.setSingleStep(1)
        slider.step = step
        slider.min_val = min_val
        slider.max_val = max_val
        slider.name = name
        slider.default = default


        if log:
            slider.valueChanged.connect(lambda value: label.setText(f"{name}: {10**(value * step)}"))

        else:
            if type(step) == int:
                slider.valueChanged.connect(lambda value: label.setText(f"{name}: {value * step} "))
            else:
                slider.valueChanged.connect(lambda value: label.setText(f"{name}: {round((value * step), 3)} "))

        layout = QVBoxLayout()
        layout.addWidget(label)
        layout.addWidget(slider)

        return slider, label, layout
    

    def extractLineamentAction(self):
        import glob 
        import rasterio

        options = QFileDialog.Options()
        shp_path, _ = QFileDialog.getSaveFileName(self, "Shapefile Name", "", "Shapefile (*.shp);", options=options)
        shp_name  = os.path.split(shp_path)[-1]
        n = shp_name.split('.')[0]
        temp_folder = os.path.normpath(shp_path.replace(shp_name,'')+ f'\\{n}')
        
        im_path = os.path.normpath(self.file_name)

        sz = self.subsetSideSlider.value() * self.subsetSideSlider.step
        z_multip = round(10**(self.hillshadeZSlider.value() * self.hillshadeZSlider.step),5)
        eps = self.epsSlider.value() * self.epsSlider.step
        thresh = self.threshSlider.value() * self.threshSlider.step
        min_dist = self.minDistSlider.value() * self.minDistSlider.step
        seg_len = self.segLenSlider.value() * self.segLenSlider.step
        downscale = self.downsampleSlider.value() * self.downsampleSlider.step

        keep_intermediate_file = self.keepIntermediateCheckbox.checkState() > 0


        if os.path.isdir(temp_folder):
            'delete content' 
            files = glob.glob(f'{temp_folder}/*')
            for f in files:
                os.remove(f)
        else:
            'create new folder'
            os.mkdir(temp_folder)


        ''' IMAGE SPLITTING SEQUENCES - START'''
        #==================================================================================================
        dataset = rasterio.open(im_path)
        im  = dataset.read(1)
        shape = im.shape
        left, bottom, right, top = list(dataset.bounds)
        resX = (right-left)/im.shape[1]
        resY = (top-bottom)/im.shape[0]

        if shape[0]<sz:
            v_split = np.array([[0, shape[0]]])
        else:
            v_split = np.c_[np.arange(0, shape[0]-sz, sz), np.arange(0, shape[0]-sz, sz)+sz]
            v_split = np.vstack([v_split, [v_split[-1,-1],shape[0]]])

        if shape[1]<sz:
            h_split = np.array([[0, shape[1]]])
        else:
            h_split = np.c_[np.arange(0, shape[1]-sz, sz), np.arange(0, shape[1]-sz, sz)+sz]
            h_split = np.vstack([h_split, [h_split[-1,-1],shape[1]]])


        xx, yy = np.meshgrid(np.arange(len(v_split)), np.arange(len(h_split)))
        xx, yy = xx.flatten(), yy.flatten()

        grids  =  np.c_[ h_split[yy], v_split[xx],]
        #==================================================================================================
        
        '''grid format: [[L, R, B, T]] '''


        ns = np.arange(len(grids))
        target_folders = [temp_folder]*len(grids)
        lefts = [left]*len(grids)
        tops  = [top]*len(grids)
        resXs = [resX]*len(grids)
        resYs = [resY]*len(grids)
        szs   = [sz]*len(grids)

        df = pd.DataFrame(zip(ns, target_folders, lefts, tops, resXs, resYs, szs), columns=['ns', 'target_folders', 'lefts', 'tops', 'resXs', 'resYs', 'szs'])
        
        df[['L', 'R', 'B', 'T']] = grids

        transforms = []
        ims        = []

        for n, tempfolder, left, top, resX, resY, sz, L, R, B, T in df.values:
            l = left + L*resX
            # b = top - T*resY - sz*resY
            b = top + T*resY

            transform = rasterio.Affine.translation(l - resX / 2, b + resY / 2) * rasterio.Affine.scale(resX, resY)
            Z  = im[B:T, L:R].astype('float')

            transforms.append(transform)
            ims.append(Z)

        crs = dataset.crs
        self.df = df



        cases = zip(np.arange(len(df)),
                              [crs]*len(df), 
                              ims, 
                              transforms,
                              [temp_folder]*len(df))
        for n_, crs, im, transform, temp_folder in cases:
            worker = ImageSplitterParallel(n_, crs, im, transform, temp_folder)
            self.threadpool.start(worker)

        print(''' IMAGE SPLITTING SEQUENCES - END'''   )
        
        self.threadpool.waitForDone()       


        flist = glob.glob(f'{temp_folder}/*.tiff')
        cases = pd.DataFrame(zip(flist, 
                                [temp_folder]*len(flist), 
                                [eps]*len(flist), 
                                [thresh]*len(flist), 
                                [min_dist]*len(flist), 
                                [seg_len]*len(flist), 
                                [z_multip]*len(flist),
                                [downscale]*len(flist))).values

        from joblib import Parallel, delayed
        Parallel(n_jobs=-1)(delayed(dem_to_line)(*c) for c in cases)

        df = merge_lines_csv_to_shp(tempfolder=temp_folder, 
                                    shppath=shp_path, 
                                    save_to_file=True)
        

        if keep_intermediate_file == False:
            
            if os.path.isdir(tempfolder):
                'delete content' 
                files = glob.glob(f'{tempfolder}/*')
                for f in files:
                    os.remove(f)
                os.removedirs(tempfolder)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()


