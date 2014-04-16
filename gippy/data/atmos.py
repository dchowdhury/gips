#!/usr/bin/env python
################################################################################
#    GIPPY: Geospatial Image Processing library for Python
#
#    Copyright (C) 2014 Matthew A Hanson
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program. If not, see <http://www.gnu.org/licenses/>
################################################################################

import os
import datetime
import gdal
import ftplib
import numpy

import gippy
from gippy.data.inventory import DataInventory
from gippy.data.core import Repository, Asset, Data
from gippy.utils import File2List, List2File, VerboseOut
import gippy.settings as settings

import traceback
from pdb import set_trace


class AtmosRepository(Repository):
    _rootpath = '/titan/data/atmos'
    _datedir = '%Y%j'

    @classmethod
    def path(cls, tile='', date=''):
        path = os.path.join(cls._rootpath, cls._tilesdir)
        if date != '':
            path = os.path.join(path, str(date.strftime('%Y')), str(date.strftime('%j')))
        return path

    @classmethod
    def find_tiles(cls):
        return ['']

    @classmethod
    def find_dates(cls, tile=''):
        """ Get list of dates available in repository for a tile """
        #tdir = cls.path()
        #if os.path.exists(tdir):
        dates = []
        for year in os.listdir(cls.path()):
            days = os.listdir(os.path.join(cls.path(), year))
            for day in days:
                dates.append(datetime.datetime.strptime(year+day, '%Y%j').date())
        return dates


class AtmosAsset(Asset):
    Repository = AtmosRepository

    # ???? Not specific to MODIS
    _sensors = {
        'MOD': {'description': 'MODIS Terra'},
        'MYD': {'description': 'MODIS Aqua'},
    }
    _assets = {
        'MOD08': {
            'pattern': 'MOD08_D3*hdf',
            'url': 'ladsweb.nascom.nasa.gov/allData/51/MOD08_D3'
        },
        'MYD08': {
            'pattern': 'MYD08_D3*hdf',
            'url': 'ladsweb.nascom.nasa.gov/allData/51/MYD08_D3'
        }
    }

    def __init__(self, filename):
        """ Inspect a single file and get some metadata """
        super(AtmosAsset, self).__init__(filename)

        bname = os.path.basename(filename)
        self.asset = bname[0:5]
        self.tile = ''
        year = bname[10:14]
        doy = bname[14:17]
        self.date = datetime.datetime.strptime(year+doy, "%Y%j").date()
        self.sensor = bname[:3]
        #datafiles = self.datafiles()
        prefix = 'HDF4_EOS:EOS_GRID:"'
        self.products = {'aero': prefix + filename + '":mod08:Optical_Depth_Land_And_Ocean_Mean'}

    def datafiles(self):
        indexfile = self.filename + '.index'

        if os.path.exists(indexfile):
            datafiles = File2List(indexfile)
        else:
            gdalfile = gdal.Open(self.filename)
            subdatasets = gdalfile.GetSubDatasets()
            datafiles = [s[0] for s in subdatasets]
            List2File(datafiles, indexfile)
        return datafiles

    @classmethod
    def archive(cls, path='.', recursive=False, keep=False):
        assets = super(AtmosAsset, cls).archive(path, recursive, keep)
        dates = [a.date for a in assets]
        for date in set(dates):
            AtmosData.process_aerolta_daily(date.strftime('%j'))


class AtmosData(Data):
    name = 'Globally Gridded Atmospheric Data'
    Asset = AtmosAsset

    _products = {
        'aero': {
            'description': 'Aerosols',
            # the list of asset types associated with this product
            'assets': ['MOD08'],  # , 'MYD08'],
        },
        'aerolta': {
            'description': 'Aerosols, average daily',
            # the list of asset types associated with this product
            'assets': ['MOD08'],  # , 'MYD08'],
        },
    }

    def process(self, products):
        start = datetime.datetime.now()
        #bname = os.path.basename(self.assets[''].filename)
        for product in products:
            print product
            #if product == 'aerolta':
            #    self.process_aerolta()
            VerboseOut(' -> %s: processed %s in %s' % (fout, product, datetime.datetime.now()-start))

    @classmethod
    def process_mean(cls, filenames, fout):
        """ Calculates mean of all filenames, and per pixel variances """
        start = datetime.datetime.now()
        if len(filenames) > 0:
            img = gippy.GeoImage(filenames)
            imgout = gippy.GeoImage(fout, img, gippy.GDT_Float32, 2)
            imgout.SetNoData(-32768)
            img.Mean(imgout[0])
            meanimg = imgout[0].Read()
            for band in range(0, img.NumBands()):
                data = img[band].Read()
                mask = img[band].DataMask()
                var = numpy.multiply(numpy.power(data-meanimg, 2), mask)
                if band == 0:
                    totalvar = var
                    counts = mask
                else:
                    totalvar = totalvar + var
                    counts = counts + mask
            inds = numpy.where(counts == 0)
            totalvar[inds] = -32768
            inds = numpy.where(counts != 0)
            totalvar[inds] = numpy.divide(totalvar[inds], counts[inds])
            imgout[1].Write(totalvar)
            t = datetime.datetime.now()-start
            VerboseOut('%s: mean/variances for %s files processed in %s' % (os.path.basename(fout), len(filenames), t))
        return imgout

    @classmethod
    def process_aerolta_daily(cls, day):
        """ Calculate AOT long-term multi-year averages (lta) for given day """
        inv = cls.inventory(products=['aero'], days="%s,%s" % (day, day))
        fnames = [inv[d].tiles[''].products['aero'] for d in inv.dates]
        fout = os.path.join(cls.Asset.Repository.cpath('aerolta'), 'aerolta_%s.tif' % str(day).zfill(3))
        imgout = cls.process_mean(fnames, fout)
        return imgout.Filename()

    @classmethod
    def process_aerolta(cls):
        filenames = glob.glob(os.path.join(cls.Asset.Repository.cpath('aerolta'), 'aerolta_*.tif'))
        fout = os.path.join(cls.Asset.Repository.cpath('aerolta'), 'aerolta.tif')
        cls.process_mean(filenames, fout)

    @classmethod
    def process_aerolta_all(cls):
        """ Process all daily long-term average and final lta average file """
        filenames = []
        for day in range(1, 366):
            filenames.append(cls.process_aerolta_daily(day))
        # spatial average
        #img[band].Smooth(imgout[1])
        #mean = numpy.multiply(imgout[1].Read(), mask)

    def get_point(self, lat, lon, product=''):
        pixx = int(numpy.round(float(lon) + 179.5))
        pixy = int(numpy.round(89.5 - float(lat)))
        roi = gippy.iRect(pixx-1, pixy-1, 3, 3)
        img = self.open(product=product)
        nodata = img[0].NoDataValue()
        vals = img[0].Read(roi).squeeze()
        # TODO - do this automagically in swig wrapper
        vals[numpy.where(vals == nodata)] = numpy.nan

        val = vals[1, 1]
        if val is numpy.nan:
            val = numpy.nanmean(vals)

        cpath = self.Repository.cpath('aerolta')
        day = self.date.strftime('%j')

        if val is numpy.nan:
            img = gippy.GeoImage(os.path.join(cpath, 'aerolta_%s.tif' % str(day).zfill(3)))
            vals = img[0].Read(roi).squeeze()
            if vals == numpy.nan:
                val = numpy.nanmean(vals)
            else:
                val = vals[1, 1]

        if val is numpy.nan:
            img = gippy.GeoImage(os.path.join(cpath, 'aerolta.tif'))
            vals = img[0].Read(roi).squeeze()
            if vals == numpy.nan:
                val = numpy.nanmean(vals)
            else:
                val = vals[1, 1]

        set_trace()

        #total = 0
        #count = 0
        #for x, y in numpy.ndindex(vals.shape):
        #    if vals[x,y] != nodata:
        #        total = total + vals[x,y]
        #        count = count+1
        #set_trace()

        day = self.date.strftime('%j')
        print 'val', val
        if val == img[0].NoData():
            fname = os.path.join(self.Repository.cpath('aerolta'), 'aerolta_%s' % day)
            img = gippy.GeoImage(fname)
            val = img[0].Read(roi).squeeze()
            print 'val', val
        if val == img[0].NoData():
            print 'still nodata aerosols'
            val = 0.17
        return val


def main():
    DataInventory.main(AtmosData)