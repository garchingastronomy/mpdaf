"""Copyright 2010-2016 CNRS/CRAL

This file is part of MPDAF.

MPDAF is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 3 of the License, or
(at your option) any later version

MPDAF is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with MPDAF.  If not, see <http://www.gnu.org/licenses/>.


rawobj.py Manages raw FITS file.
"""

from __future__ import absolute_import, print_function, division

import datetime
import logging
import matplotlib.pyplot as plt
import multiprocessing
import numpy as np
import os.path
import sys
import warnings

from astropy.io import fits
from scipy import integrate
from six.moves import range

from ..obj import Image, WCS

NB_SUBSLICERS = 4  # number of sub-slicers
NB_SPEC_PER_SLICE = 75  # number of pixels per slice
NB_SLICES = 12  # number of slices per sub-slicer
INTERSPEC = 7  # inter-spectrum distance in pixel
OVERSCAN = 32  # overscan width in pixel
slit_position = np.array([9, 8, 1, 10, 7, 2, 11, 6, 3, 12, 5, 4])


class Channel(object):

    """Channel object corresponds to an extension of a raw FITS file.

    Parameters
    ----------
    extname : str
        The extension name.
    filename : str
        The raw FITS file name.

    Attributes
    ----------
    extname : str
        The extension name
    header : `astropy.io.fits.Header`
        The extension header
    data : array
        Array containing the pixel values of the image extension
    nx : int
        Lengths of data in X
    ny : int
        Lengths of data in Y
    mask : array of booleans
        Arrays that contents TRUE for overscanned pixels, FALSE for the others.

    """

    def __init__(self, extname=None, filename=None, data=None):
        self._logger = logging.getLogger(__name__)
        self.extname = extname
        if filename is not None:
            hdulist = fits.open(filename)
            self.header = hdulist[extname].header
            self.nx = hdulist[extname].header["NAXIS1"]
            self.ny = hdulist[extname].header["NAXIS2"]
            try:
                data = hdulist[extname].data
                self.data = np.ndarray(np.shape(data))
                self.data[:] = data[:]
            except:
                self._logger.warning("extension %s not loaded" % extname)
                self.data = None
            hdulist.close()
        elif data is not None:
            self.header = fits.Header()
            shape = np.shape(data)
            self.data = np.ndarray(shape)
            self.data[:] = data[:]
            self.nx = shape[1]
            self.ny = shape[0]
        else:
            self.header = fits.Header()
            self.nx = 0
            self.ny = 0
            self.data = None
        self.mask = self._init_mask()

    def _init_mask(self):
        """Create mask that invalidates over scanned pixels."""
        m = np.ones((self.ny, self.nx), dtype=int)
        try:
            nx_data = self.header["NAXIS1"]  # length of data in X
            ny_data = self.header["NAXIS2"]  # length of data in Y
            # Physical active pixels in X
            nx_data2 = self.header["ESO DET CHIP NX"]
            # Physical active pixels in Y
            ny_data2 = self.header["ESO DET CHIP NY"]
            m = np.ones((self.ny, self.nx), dtype=int)

            for i in range(4):
                try:
                    n = i + 1
                    key = "ESO DET OUT%i" % n
                    # Output data pixels in X
                    nx = self.header["%s NX" % key]
                    # Output data pixels in Y
                    ny = self.header["%s NY" % key]
                    try:
                        # Output prescan pixels in X
                        prscx = self.header["%s PRSCX" % key]
                    except:
                        prscx = OVERSCAN
                    try:
                        # Output prescan pixels in Y
                        prscy = self.header["%s PRSCY" % key]
                    except:
                        prscy = OVERSCAN
                    # X location of output
                    x = self.header["%s X" % key]
                    # Y location of output
                    y = self.header["%s Y" % key]
                    if x < nx_data2 // 2:
                        i1 = x - 1 + prscx
                        i2 = i1 + nx
                    else:
                        i2 = nx_data - prscx
                        i1 = i2 - nx
                    if y < ny_data2 // 2:
                        j1 = y - 1 + prscy
                        j2 = j1 + ny
                    else:
                        j2 = ny_data - prscy
                        j1 = j2 - ny
                    m[j1:j2, i1:i2] *= 0
                except:
                    break
        except:
            pass
        return np.ma.make_mask(m)

    def copy(self):
        """Return a copy of the Channel object."""
        result = Channel(self.extname)
        result.header = self.header.copy()
        try:
            result.data = self.data.__copy__()
        except:
            result.data = None
        result.nx = self.nx
        result.ny = self.ny
        result.mask = self.mask.__copy__()
        return result

    def _decorator(function):
        # decorator used to define arithmetic functions
        def _wrapper(self, other):
            if isinstance(other, Channel):
                if self.extname != other.extname:
                    raise IOError('operations on channel extensions '
                                  'with different names')
                result = Channel(self.extname)
                result.header = self.header
                result.nx = self.nx
                result.ny = self.ny
                result.mask = self.mask
                result.data = function(self.data, other.data)
                if isinstance(result.data, np.ma.core.MaskedArray):
                    result.data = result.data.data
                return result
            else:
                result = Channel(self.extname)
                result.header = self.header
                result.nx = self.nx
                result.ny = self.ny
                result.mask = self.mask
                result.data = function(self.data, other)
                if isinstance(result.data, np.ma.core.MaskedArray):
                    result.data = result.data.data
                return result
        return _wrapper

    def _idecorator(function):
        # decorator used to define in-place arithmetic functions
        def _wrapper(self, other):
            if isinstance(other, Channel):
                if self.extname != other.extname:
                    raise IOError('operations on channel extensions '
                                  'with different names')
                result = Channel(self.extname)
                result.header = self.header
                result.nx = self.nx
                result.ny = self.ny
                result.mask = self.mask
                result.data = function(self.data, other.data)
                return result
            else:
                result = Channel(self.extname)
                result.header = self.header
                result.nx = self.nx
                result.ny = self.ny
                result.mask = self.mask
                result.data = function(self.data, other)
                return result
        return _wrapper

    @_decorator
    def __mul__(self, other):
        """Multiplies either a number or a Channel object."""
        if isinstance(self, np.ma.core.MaskedArray):
            return np.ma.MaskedArray.__mul__(self, other)
        else:
            return np.ndarray.__mul__(self, other)

    @_idecorator
    def __imul__(self, other):
        if isinstance(self, np.ma.core.MaskedArray):
            return np.ma.MaskedArray.__mul__(self, other)
        else:
            return np.ndarray.__mul__(self, other)

    @_decorator
    def __div__(self, other):
        """Divides either a number or a Channel object."""
        if isinstance(self, np.ma.core.MaskedArray):
            return np.ma.MaskedArray.__div__(self, other)
        else:
            return np.ndarray.__div__(self, other)

    @_idecorator
    def __idiv__(self, other):
        if isinstance(self, np.ma.core.MaskedArray):
            return np.ma.MaskedArray.__div__(self, other)
        else:
            return np.ndarray.__div__(self, other)

    __truediv__ = __div__
    __itruediv__ = __idiv__

    @_decorator
    def __sub__(self, other):
        """Subtracts either a number or a Channel object."""
        if isinstance(self, np.ma.core.MaskedArray):
            return np.ma.MaskedArray.__sub__(self, other)
        else:
            return np.ndarray.__sub__(self, other)

    @_idecorator
    def __isub__(self, other):
        if isinstance(self, np.ma.core.MaskedArray):
            return np.ma.MaskedArray.__sub__(self, other)
        else:
            return np.ndarray.__sub__(self, other)

    @_decorator
    def __add__(self, other):
        """Add either a number or a Channel object."""
        if isinstance(self, np.ma.core.MaskedArray):
            return np.ma.MaskedArray.__add__(self, other)
        else:
            return np.ndarray.__add__(self, other)

    @_idecorator
    def __iadd__(self, other):
        if isinstance(self, np.ma.core.MaskedArray):
            return np.ma.MaskedArray.__add__(self, other)
        else:
            return np.ndarray.__add__(self, other)

    @_decorator
    def __pow__(self, other):
        """Compute the power exponent."""
        if isinstance(self, np.ma.core.MaskedArray):
            return np.ma.MaskedArray.__pow__(self, other)
        else:
            return np.ndarray.__pow__(self, other)

    @_idecorator
    def __ipow__(self, other):
        if isinstance(self, np.ma.core.MaskedArray):
            return np.ma.MaskedArray.__pow__(self, other)
        else:
            return np.ndarray.__pow__(self, other)

    def sqrt(self):
        """Compute the positive square-root."""
        result = Channel(self.extname)
        result.header = self.header
        result.nx = self.nx
        result.ny = self.ny
        result.mask = self.mask
        result.data = np.sqrt(self.data)
        if isinstance(result.data, np.ma.core.MaskedArray):
            result.data = result.data.data
        return result

    def trimmed(self):
        """Return a Channel object containing only reference to the valid
        pixels.

        Returns
        -------
        out : `mpdaf.drs.Channel`
        """
        result = Channel(self.extname)
        result.header = self.header
        result.nx = self.nx
        result.ny = self.ny
        result.mask = self.mask
        result.data = np.ma.MaskedArray(self.data, mask=self.mask, copy=True)
        return result

    def overscan(self):
        """Return a Channel object containing only reference to the overscanned
        pixels.

        Returns
        -------
        out : `mpdaf.drs.Channel`
        """
        result = Channel(self.extname)
        result.header = self.header
        result.nx = self.nx
        result.ny = self.ny
        result.mask = self.mask
        result.data = np.ma.MaskedArray(self.data,
                                        mask=np.logical_not(self.mask),
                                        copy=True)
        return result

    def get_image(self, det_out=None, bias=False):
        """Return an Image object.

        Parameters
        ----------
        det_out : int in [1,4]
            Number of output detector. If None, all image is returned.
        bias    : boolean
            If True, median value of the overscanned pixels is subtracted.

        Returns
        -------
        out : `~mpdaf.obj.Image`
        """
        wcs = WCS(self.header)
        ima = Image(wcs=wcs, data=self.data.__copy__())

        if det_out is not None:
            # length of data in X
            nx_data = self.header["NAXIS1"]
            # length of data in Y
            ny_data = self.header["NAXIS2"]
            # Physical active pixels in X
            nx_data2 = self.header["ESO DET CHIP NX"]
            # Physical active pixels in Y
            ny_data2 = self.header["ESO DET CHIP NY"]
            key = "ESO DET OUT%i" % det_out
            # Output data pixels in X
            nx = self.header["%s NX" % key]
            # Output data pixels in Y
            ny = self.header["%s NY" % key]
            # Output prescan pixels in X
            prscx = self.header["%s PRSCX" % key]
            # Output prescan pixels in Y
            prscy = self.header["%s PRSCY" % key]
            # X location of output
            x = self.header["%s X" % key]
            # Y location of output
            y = self.header["%s Y" % key]
            if x < nx_data2 // 2:
                i1 = x - 1
                i2 = i1 + nx + 2 * prscx
            else:
                i2 = nx_data
                i1 = i2 - nx - 2 * prscx
            if y < ny_data2 // 2:
                j1 = y - 1
                j2 = j1 + ny + 2 * prscy
            else:
                j2 = ny_data
                j1 = j2 - ny - 2 * prscy
            ima = ima[j1:j2, i1:i2]
            if bias:
                ima -= self. get_bias_level(det_out)

        if det_out is None and bias:
            # length of data in X
            nx_data = self.header["NAXIS1"]
            # length of data in Y
            ny_data = self.header["NAXIS2"]
            # Physical active pixels in X
            nx_data2 = self.header["ESO DET CHIP NX"]
            # Physical active pixels in Y
            ny_data2 = self.header["ESO DET CHIP NY"]
            for det in range(1, 5):
                key = "ESO DET OUT%i" % det
                # Output data pixels in X
                nx = self.header["%s NX" % key]
                # Output data pixels in Y
                ny = self.header["%s NY" % key]
                # Output prescan pixels in X
                prscx = self.header["%s PRSCX" % key]
                # Output prescan pixels in Y
                prscy = self.header["%s PRSCY" % key]
                # X location of output
                x = self.header["%s X" % key]
                # Y location of output
                y = self.header["%s Y" % key]
                if x < nx_data2 // 2:
                    i1 = x - 1
                    i2 = i1 + nx + 2 * prscx
                else:
                    i2 = nx_data
                    i1 = i2 - nx - 2 * prscx
                if y < ny_data2 // 2:
                    j1 = y - 1
                    j2 = j1 + ny + 2 * prscy
                else:
                    j2 = ny_data
                    j1 = j2 - ny - 2 * prscy
                ima[j1:j2, i1:i2] -= self. get_bias_level(det)

        return ima

    def get_bias_level(self, det_out):
        """computes median value of the overscanned pixels.

        Parameters
        ----------
        det_out : int in [1,4]
            Number of detector taken into account.

        Returns
        -------
        out : float
        """
        ima = self.get_image_just_overscan(det_out)
        ksel = np.where(ima.data.mask == False)
        return np.median(ima.data.data[ksel])

    def get_trimmed_image(self, det_out=None, bias_substract=False,
                          bias=False):
        """Return an Image object without over scanned pixels.

        Parameters
        ----------
        det_out : int in [1,4]
            Number of output detector. If None, all image is returned.
        bias_substract : boolean
            If True, median value of the overscanned pixels is substracted.
        bias : boolean
            If True, median value of the overscanned pixels is subtracted.

        Returns
        -------
        out : `~mpdaf.obj.Image`
        """
        # Physical active pixels in X
        nx_data2 = self.header["ESO DET CHIP NX"]
        # Physical active pixels in Y
        ny_data2 = self.header["ESO DET CHIP NY"]
        if isinstance(self.data, np.ma.core.MaskedArray):
            work = np.ma.MaskedArray(self.data.data.__copy__(),
                                     mask=self.mask)
        else:
            work = np.ma.MaskedArray(self.data.__copy__(), mask=self.mask)

        if bias_substract:
            warnings.warn("get_trimmed_image: bias_substract parameter "
                          "will be replaced by bias parameter",
                          DeprecationWarning)
            bias = True

        if bias:
            ksel = np.where(self.mask == True)
            # length of data in X
            nx_data = self.header["NAXIS1"]
            # length of data in Y
            ny_data = self.header["NAXIS2"]

            if det_out is None:
                for det in range(1, 5):
                    key = "ESO DET OUT%i" % det
                    # Output data pixels in X
                    nx = self.header["%s NX" % key]
                    # Output data pixels in Y
                    ny = self.header["%s NY" % key]
                    # Output prescan pixels in X
                    prscx = self.header["%s PRSCX" % key]
                    # Output prescan pixels in Y
                    prscy = self.header["%s PRSCY" % key]
                    # X location of output
                    x = self.header["%s X" % key]
                    # Y location of output
                    y = self.header["%s Y" % key]
                    if x < nx_data2 // 2:
                        i1 = x - 1
                        i2 = i1 + nx + 2 * prscx
                    else:
                        i2 = nx_data
                        i1 = i2 - nx - 2 * prscx
                    if y < ny_data2 // 2:
                        j1 = y - 1
                        j2 = j1 + ny + 2 * prscy
                    else:
                        j2 = ny_data
                        j1 = j2 - ny - 2 * prscy

                    ksel = np.where(self.mask[j1:j2, i1:i2] == True)
                    bias_level = np.median((work.data[j1:j2, i1:i2])[ksel])
                    work[j1:j2, i1:i2] -= bias_level
            else:
                key = "ESO DET OUT%i" % det_out
                # Output data pixels in X
                nx = self.header["%s NX" % key]
                # Output data pixels in Y
                ny = self.header["%s NY" % key]
                # Output prescan pixels in X
                prscx = self.header["%s PRSCX" % key]
                # Output prescan pixels in Y
                prscy = self.header["%s PRSCY" % key]
                # X location of output
                x = self.header["%s X" % key]
                # Y location of output
                y = self.header["%s Y" % key]
                if x < nx_data2 // 2:
                    i1 = x - 1
                    i2 = i1 + nx + 2 * prscx
                else:
                    i2 = nx_data
                    i1 = i2 - nx - 2 * prscx
                if y < ny_data2 // 2:
                    j1 = y - 1
                    j2 = j1 + ny + 2 * prscy
                else:
                    j2 = ny_data
                    j1 = j2 - ny - 2 * prscy

                ksel = np.where(self.mask[j1:j2, i1:i2] == True)
                bias_level = np.median(work.data[j1:j2, i1:i2][ksel])
                work[j1:j2, i1:i2] -= bias_level

        data = np.ma.compressed(work)
        data = np.reshape(data, (ny_data2, nx_data2))
        wcs = WCS(crpix=(1.0, 1.0), shape=(ny_data2, nx_data2))
        ima = Image(wcs=wcs, data=data)

        if det_out is not None:
            # length of data in X
            nx_data = self.header["NAXIS1"]
            # length of data in Y
            ny_data = self.header["NAXIS2"]
            key = "ESO DET OUT%i" % det_out
            # Output data pixels in X
            nx = self.header["%s NX" % key]
            # Output data pixels in Y
            ny = self.header["%s NY" % key]
            # Output prescan pixels in X
            prscx = self.header["%s PRSCX" % key]
            # Output prescan pixels in Y
            prscy = self.header["%s PRSCY" % key]
            # X location of output
            x = self.header["%s X" % key]
            # Y location of output
            y = self.header["%s Y" % key]
            if x < nx_data2 // 2:
                i1 = x - 1 + prscx
                i2 = i1 + nx
            else:
                i2 = nx_data - prscx
                i1 = i2 - nx
            if y < ny_data2 // 2:
                j1 = y - 1 + prscy
                j2 = j1 + ny
            else:
                j2 = ny_data - prscy
                j1 = j2 - ny
            ima = ima[j1:j2, i1:i2]

        return ima

    def get_image_mask_overscan(self, det_out=None):
        """Return an Image object in which overscanned pixels are masked.

        Parameters
        ----------
        det_out : int in [1,4]
                  Number of output detector.
                  If None, all image is returned.

        Returns
        -------
        out : `~mpdaf.obj.Image`
        """
        wcs = WCS(fits.Header(self.header))
        ima = Image(wcs=wcs, data=self.data)
        ima.data = np.ma.MaskedArray(self.data.__copy__(),
                                     mask=self.mask, copy=True)

        if det_out is not None:
            # length of data in X
            nx_data = self.header["NAXIS1"]
            # length of data in Y
            ny_data = self.header["NAXIS2"]
            # Physical active pixels in X
            nx_data2 = self.header["ESO DET CHIP NX"]
            # Physical active pixels in Y
            ny_data2 = self.header["ESO DET CHIP NY"]
            key = "ESO DET OUT%i" % det_out
            # Output data pixels in X
            nx = self.header["%s NX" % key]
            # Output data pixels in Y
            ny = self.header["%s NY" % key]
            # Output prescan pixels in X
            prscx = self.header["%s PRSCX" % key]
            # Output prescan pixels in Y
            prscy = self.header["%s PRSCY" % key]
            # X location of output
            x = self.header["%s X" % key]
            # Y location of output
            y = self.header["%s Y" % key]
            if x < nx_data2 // 2:
                i1 = x - 1
                i2 = i1 + nx + 2 * prscx
            else:
                i2 = nx_data
                i1 = i2 - nx - 2 * prscx
            if y < ny_data2 // 2:
                j1 = y - 1
                j2 = j1 + ny + 2 * prscy
            else:
                j2 = ny_data
                j1 = j2 - ny - 2 * prscy
            ima = ima[j1:j2, i1:i2]

        return ima

    def get_image_just_overscan(self, det_out=None):
        """Return an Image object in which only overscanned pixels are not
        masked.

        Parameters
        ----------
        det_out : int in [1,4]
            Number of output detector. If None, all image is returned.

        Returns
        -------
        out : `~mpdaf.obj.Image`
        """
        wcs = WCS(fits.Header(self.header))
        ima = Image(wcs=wcs, data=self.data)
        ima.data = np.ma.MaskedArray(self.data.__copy__(),
                                     mask=np.logical_not(self.mask),
                                     copy=True)

        if det_out is not None:
            # length of data in X
            nx_data = self.header["NAXIS1"]
            # length of data in Y
            ny_data = self.header["NAXIS2"]
            # Physical active pixels in X
            nx_data2 = self.header["ESO DET CHIP NX"]
            # Physical active pixels in Y
            ny_data2 = self.header["ESO DET CHIP NY"]
            key = "ESO DET OUT%i" % det_out
            # Output data pixels in X
            nx = self.header["%s NX" % key]
            # Output data pixels in Y
            ny = self.header["%s NY" % key]
            # Output prescan pixels in X
            prscx = self.header["%s PRSCX" % key]
            # Output prescan pixels in Y
            prscy = self.header["%s PRSCY" % key]
            # X location of output
            x = self.header["%s X" % key]
            # Y location of output
            y = self.header["%s Y" % key]
            if x < nx_data2 // 2:
                i1 = x - 1
                i2 = i1 + nx + 2 * prscx
            else:
                i2 = nx_data
                i1 = i2 - nx - 2 * prscx
            if y < ny_data2 // 2:
                j1 = y - 1
                j2 = j1 + ny + 2 * prscy
            else:
                j2 = ny_data
                j1 = j2 - ny - 2 * prscy
            ima = ima[j1:j2, i1:i2]

        return ima


STR_FUNCTIONS = {'Channel.__mul__': Channel.__mul__,
                 'Channel.__imul__': Channel.__imul__,
                 'Channel.__div__': Channel.__div__,
                 'Channel.__idiv__': Channel.__idiv__,
                 'Channel.__sub__': Channel.__sub__,
                 'Channel.__isub__': Channel.__isub__,
                 'Channel.__add__': Channel.__add__,
                 'Channel.__iadd__': Channel.__iadd__,
                 'Channel.__pow__': Channel.__pow__,
                 'Channel.__ipow__': Channel.__ipow__,
                 'Channel.sqrt': Channel.sqrt,
                 'Channel.trimmed': Channel.trimmed,
                 'Channel.overscan': Channel.overscan,
                 }


def Channel_median(channels):
    result = Channel(channels[0].extname)
    result.header = channels[0].header
    result.nx = channels[0].nx
    result.ny = channels[0].ny
    result.mask = channels[0].mask
    result.data = np.empty_like(channels[0].data)
    arrays = []
    for chan in channels:
        arrays.append(chan.data)
        result.mask += chan.mask
    arrays = np.array(arrays, dtype=np.int16)
    result.data = np.median(arrays, axis=0)
    if isinstance(result.data, np.ma.core.MaskedArray):
        result.data = result.data.data
    return result


class RawFile(object):

    """RawFile class manages input/output for raw FITS file.

    Parameters
    ----------
    filename : str
        The raw FITS file name. ``filename=None`` creates an empty object. The
        FITS file is opened with memory mapping. Just the primary header and
        the list of extension name are loaded. Method get_channel(extname)
        returns the corresponding channel Operator [extnumber] loads and
        returns the corresponding channel.

    Attributes
    ----------
    filename : str
        The raw FITS file name. None if any.
    channels : dict
        List of extension (extname,Channel)
    primary_header : `astropy.io.fits.Header`
        The primary header
    nx : int
        Lengths of data in X
    ny : int
        Lengths of data in Y
    next : int
        Number of extensions
    progress : boolean
        If True, progress of multiprocessing tasks are displayed. True by
        default.

    """

    def __init__(self, filename=None):
        self._logger = logging.getLogger(__name__)
        self.filename = filename
        self.primary_header = fits.Header()
        self.progress = True
        self.channels = dict()
        self.nx = 0
        self.ny = 0
        self.next = 0

        if filename is not None:
            hdulist = fits.open(self.filename)
            self.primary_header = hdulist[0].header
            for hdu in hdulist[1:]:
                extname = hdu.header["EXTNAME"]
                exttype = hdu.header["XTENSION"]
                if exttype == 'IMAGE' and hdu.header["NAXIS"] != 0:
                    nx = hdu.header["NAXIS1"]
                    ny = hdu.header["NAXIS2"]
                    if self.nx == 0:
                        self.nx = nx
                        self.ny = ny
                    if nx != self.nx and ny != self.ny:
                        self._logger.warning(
                            'image extensions %s not considered '
                            '(different sizes)', extname)
                    else:
                        self.channels[extname] = None
            self.next = len(self.channels)
            hdulist.close()

    def copy(self):
        """Return a copy of the RawFile object."""
        result = RawFile(self.filename)
        if result.filename is None:
            result.primary_header = fits.Header(self.primary_header)
            result.nx = self.nx
            result.ny = self.ny
            result.next = self.next
            for name, chan in self.channels.items():
                if chan is not None:
                    result.channels[name] = chan.copy()
                else:
                    result.channels[name] = None
        return result

    def info(self):
        """Print information."""
        if self.filename is not None:
            msg = self.filename
        else:
            msg = 'NoName'
        self._logger.info(msg)
        self._logger.info('Nb extensions:\t%i (loaded:%i %s)', self.next,
                          len(self.channels), list(self.channels.keys()))
        msg = 'format:\t(%i,%i)' % (self.nx, self.ny)
        self._logger.info(msg)

    def get_keywords(self, key):
        """Return the keyword value."""
        return self.primary_header[key]

    def get_channels_extname_list(self):
        """Return the list of existing channels names."""
        return list(self.channels.keys())

    def get_channel(self, extname):
        """Return a Channel object.

        Parameters
        ----------
        extname : str
            The extension name.

        Returns
        -------
        out : `mpdaf.drs.Channel`
        """
        if self.channels[extname] is not None:
            return self.channels[extname]
        else:
            return Channel(extname, self.filename)

    def __len__(self):
        """Return the number of extensions."""
        return self.next

    def __getitem__(self, key):
        """Load the Channel object if relevant and returns it.

        Parameters
        ----------
        key : int
            The extension number.

        Returns
        -------
        out : `mpdaf.drs.Channel`
        """
        extname = "CHAN%02d" % key
        if self.channels[extname] is None:
            self.channels[extname] = Channel(extname, self.filename)
        return self.channels[extname]

    def __setitem__(self, key, value):
        """Set the corresponding channel.

        Parameters
        ----------
        key : int
            The extension number.
        value : `mpdaf.drs.Channel` or array
            Channel object or image

        """
        extname = "CHAN%02d" % key
        if isinstance(value, Channel):
            if value.nx == self.nx and value.ny == self.ny:
                self.channels[extname] = value
            else:
                raise IOError('set an image extension with different sizes')
        elif isinstance(value, np.ndarray):
            if np.shape(value) == (self.ny, self.nx):
                chan = Channel(extname)
                chan.data = value
                chan.nx = self.nx
                chan.ny = self.ny
                self.channels[extname] = chan
            else:
                raise IOError('set an image extension with bad dimensions')
        else:
            raise IOError('format %s incompatible '
                          'with an image extension' % type(value))

    def __mul__(self, other):
        """Multiplies either a number or a RawFits object."""
        return self._mp_operator(other, 'Channel.__mul__')

    def __imul__(self, other):
        return self._mp_operator(other, 'Channel.__imul__')

    def __div__(self, other):
        """Divides either a number or a RawFits object."""
        return self._mp_operator(other, 'Channel.__div__')

    def __idiv__(self, other):
        return self._mp_operator(other, 'Channel.__idiv__')

    __truediv__ = __div__
    __itruediv__ = __idiv__

    def __sub__(self, other):
        """Subtracts either a number or a RawFits object."""
        return self._mp_operator(other, 'Channel.__sub__')

    def __isub__(self, other):
        return self._mp_operator(other, 'Channel.__isub__')

    def __add__(self, other):
        """Add either a number or a RawFits object."""
        return self._mp_operator(other, 'Channel.__add__')

    def __iadd__(self, other):
        return self._mp_operator(other, 'Channel.__iadd__')

    def __pow__(self, other):
        """Compute the power exponent of each channel."""
        return self._mp_operator(other, 'Channel.__pow__')

    def __ipow__(self, other):
        return self._mp_operator(other, 'Channel.__ipow__')

    def _mp_operator(self, other, funcname):
        # multiprocessing function
        cpu_count = multiprocessing.cpu_count()
        result = RawFile()
        result.primary_header = self.primary_header
        result.nx = self.nx
        result.ny = self.ny
        result.next = self.next
        pool = multiprocessing.Pool(processes=cpu_count)
        processlist = list()
        if self.channels is not None:
            for k in self.channels.keys():
                processlist.append([funcname, k, self, other, self.progress])
            if isinstance(other, RawFile):
                processresult = pool.map(_process_operator, processlist)
            else:
                processresult = pool.map(_process_operator2, processlist)
            for k, out in processresult:
                result.channels[k] = out
            if self.progress:
                sys.stdout.write('\r                        \n')
        return result

    def sqrt(self):
        """Compute the square root of each channel."""
        cpu_count = multiprocessing.cpu_count()
        result = RawFile()
        result.primary_header = self.primary_header
        result.nx = self.nx
        result.ny = self.ny
        result.next = self.next
        pool = multiprocessing.Pool(processes=cpu_count)
        processlist = list()
        if self.channels is not None:
            for k in self.channels.keys():
                processlist.append(['Channel.sqrt', k, self, self.progress])
            processresult = pool.map(_process_operator3, processlist)
            for k, out in processresult:
                result.channels[k] = out
            if self.progress:
                sys.stdout.write('\r                        \n')
        return result

    def trimmed(self):
        """Return a RawFile object containing only valid pixels.

        Returns
        -------
        `mpdaf.drs.RawFile`
        """
        cpu_count = multiprocessing.cpu_count()
        result = RawFile()
        result.primary_header = self.primary_header
        result.nx = self.nx
        result.ny = self.ny
        result.next = self.next
        pool = multiprocessing.Pool(processes=cpu_count)
        processlist = list()
        if self.channels is not None:
            for k in self.channels.keys():
                processlist.append(['Channel.trimmed', k,
                                    self, self.progress])
            processresult = pool.map(_process_operator3, processlist)
            for k, out in processresult:
                result.channels[k] = out
            if self.progress:
                sys.stdout.write('\r                        \n')
        return result

    def overscan(self):
        """Return a RawFile object containing only overscanned pixels.

        Returns
        -------
        `mpdaf.drs.RawFile`
        """
        cpu_count = multiprocessing.cpu_count()
        result = RawFile()
        result.primary_header = self.primary_header
        result.nx = self.nx
        result.ny = self.ny
        result.next = self.next
        pool = multiprocessing.Pool(processes=cpu_count)
        processlist = list()
        if self.channels is not None:
            for k in self.channels.keys():
                processlist.append(['Channel.overscan', k,
                                    self, self.progress])
            processresult = pool.map(_process_operator3, processlist)
            for k, out in processresult:
                result.channels[k] = out
            if self.progress:
                sys.stdout.write('\r                        \n')
        return result

    def write(self, filename):
        """Save the object in a FITS file.

        Parameters
        ----------
        filename : str
            The FITS filename.

        """
        # create primary header
        prihdu = fits.PrimaryHDU()
        if self.primary_header is not None:
            for card in self.primary_header.cards:
                try:
                    prihdu.header[card.keyword] = (card.value, card.comment)
                except ValueError:
                    if isinstance(card.value, str):
                        n = 80 - len(card.keyword) - 14
                        s = card.value[0:n]
                        prihdu.header['hierarch %s' % card.keyword] = \
                            (s, card.comment)
                    else:
                        prihdu.header['hierarch %s' % card.keyword] = \
                            (card.value, card.comment)
                except:
                    pass
        prihdu.header['date'] = \
            (str(datetime.datetime.now()), 'creation date')
        prihdu.header['author'] = ('MPDAF', 'origin of the file')
        hdulist = [prihdu]
        if self.channels is not None:
            for name in self.channels.keys():
                chan = self.get_channel(name)
                try:
                    if isinstance(chan.data, np.ma.core.MaskedArray):
                        dhdu = fits.ImageHDU(name=name, data=chan.data.data)
                    else:
                        dhdu = fits.ImageHDU(name=name, data=chan.data)
                    if chan.header is not None:
                        for card in chan.header.cards:
                            try:
                                if card.keyword != "EXTNAME":
                                    dhdu.header[card.keyword] = \
                                        (card.value, card.comment)
                            except ValueError:
                                dhdu.header['hierarch %s' % card.keyword] = \
                                    (card.value, card.comment)
                            except:
                                pass
                    hdulist.append(dhdu)
                except:
                    pass
        # save to disk
        hdu = fits.HDUList(hdulist)
        hdu.writeto(filename, clobber=True, output_verify='fix')
        # update attributes
        self.filename = filename
        for name, chan in self.channels.items():
            del chan
            self.channels[name] = None

    def plot(self, title=None, channels="all", area=None, scale='linear',
             vmin=None, vmax=None, zscale=False, colorbar=None, **kargs):
        """Plot the raw images.

        Parameters
        ----------
        title : str
            Figure title (None by default).
        channels : list or 'all'
            list of channel names. All by default.
        area : list
            list of pixels ``[pmin,pmax,qmin,qmax]`` to zoom.
        scale : str
            'linear' | 'log' | 'sqrt' | 'arcsinh' | 'power'
            The stretch function to use for the scaling
            (default is 'linear').
        vmin : float
            Minimum pixel value to use for the scaling. If None, vmin
            is set to min of data.
        vmax : float
            Maximum pixel value to use for the scaling. If None, vmax
            is set to max of data.
        zscale : bool
            If true, vmin and vmax are computed
            using the IRAF zscale algorithm.
        colorbar : str
            If 'h'/'v', a horizontal/vertical colorbar is added.
        kargs : dict
            kargs can be used to set additional Artist properties.

        """
        fig = plt.figure()
        fig.subplots_adjust(wspace=0.02, hspace=0.01)
        if title is not None:
            plt.title(title)
        if channels == "all":
            for name in self.channels.keys():
                chan = self.get_channel(name)
                ima = chan.get_trimmed_image(det_out=None,
                                             bias_substract=False,
                                             bias=False)
                if area is not None:
                    ima = ima[area[0]:area[1], area[2]:area[3]]
                ima = ima.rebin_mean(6)
                ichan = int(name[-2:])
                fig.add_subplot(4, 6, ichan)
                ima.plot(None, scale, vmin, vmax, zscale, colorbar, **kargs)
                plt.axis('off')
                plt.text(ima.shape[0] - 30, ima.shape[1] - 30, '%i' % ichan,
                         style='italic',
                         bbox={'facecolor': 'red', 'alpha': 0.2, 'pad': 10})
        else:
            nchan = len(channels)
            nrows = int(np.sqrt(nchan))
            if nchan % nrows == 0:
                ncols = nchan // nrows
            else:
                ncols = int(nchan // nrows) + 1
            for i, name in enumerate(channels):
                chan = self.get_channel(name)
                ima = chan.get_trimmed_image(det_out=None,
                                             bias_substract=False, bias=False)
                if area is not None:
                    ima = ima[area[0]:area[1], area[2]:area[3]]
                ima = ima.rebin_mean(6)
                ichan = int(name[-2:])
                fig.add_subplot(nrows, ncols, i + 1)
                ima.plot(None, scale, vmin, vmax, zscale, colorbar, **kargs)
                plt.axis('off')
                plt.text(ima.shape[0] - 30, ima.shape[1] - 30, '%i' % ichan,
                         style='italic',
                         bbox={'facecolor': 'red', 'alpha': 0.2, 'pad': 10})

    def reconstruct_white_image(self, mask=None, verbose=True):
        """Reconstructs the white image of the FOV using a mask file.

        Parameters
        ----------
        mask : str
            mumdatMask_1x1.fits filename used for this reconstruction
            (if None, the last file stored in mpdaf is used).
        verbose : bool
            if True, progression is printed.

        Returns
        -------
        `~mpdaf.obj.Image`

        """
        if mask is None:
            path = os.path.dirname(__file__)
            mask = path + '/mumdatMask_1x1/PAE_July2013.fits.gz'
        raw_mask = RawFile(mask)

        white_ima = np.zeros((12 * 24, 300))

        cpu_count = multiprocessing.cpu_count()
        pool = multiprocessing.Pool(processes=cpu_count)
        processlist = list()
        for chan in self.get_channels_extname_list():
            processlist.append([chan, raw_mask, self])

        processresult = pool.imap_unordered(_process_white_image, processlist)
        pool.close()

        num_tasks = len(processlist)
        if self.progress:
            msg = 'reconstruct white image ...'
            self._logger.info(msg)
            import time
            while (True):
                time.sleep(1)
                completed = processresult._index
                if completed == num_tasks:
                    output = ""
                    sys.stdout.write("\r\x1b[K" + output.__str__())
                    break
                output = "\r (%i%% done)" % (float(completed) /
                                             float(num_tasks) * 100.0)
                sys.stdout.write("\r\x1b[K" + output.__str__())
                sys.stdout.flush()

        for ifu, data in processresult:
            # For each subslicer 1-4
            for k in range(1, NB_SUBSLICERS + 1):
                # For each slice 1-12*/
                for l in range(1, NB_SLICES + 1):
                    noslice = (k - 1) * NB_SLICES + l
                    wr_row = NB_SLICES - slit_position[l - 1] \
                        + 12 * (24 - ifu)
                    wr_col = k * NB_SPEC_PER_SLICE
                    white_ima[wr_row, wr_col - NB_SPEC_PER_SLICE:wr_col] = \
                        data[noslice - 1, :]

        return Image(data=white_ima, wcs=WCS())

    def _plot_ifu_slice_on_white_image(self, ifu, sli):
        # plot channel
        ymin = NB_SLICES * (24 - ifu) - 0.5
        ymax = ymin + NB_SLICES
        plt.plot(np.arange(-0.5, 299.5), np.ones(300) * ymin, 'b-')
        plt.plot(np.arange(-0.5, 299.5), np.ones(300) * ymax, 'b-')
        plt.annotate('%02d' % ifu, xy=(0, (ymin + ymax) / 2.0),
                     xycoords='data', textcoords='data', color='b')
        # plot slice
        k = np.floor((sli - 1) // NB_SLICES)
        l = np.mod(sli - 1, NB_SLICES) + 1
        wr_row = NB_SLICES - slit_position[l - 1] + 12 * (24 - ifu) - 0.5
        wr_col = k * NB_SPEC_PER_SLICE - 0.5
        plt.plot(np.arange(wr_col, wr_col + 76), np.ones(76) * wr_row, 'r-')
        plt.plot(np.arange(wr_col, wr_col + 76),
                 np.ones(76) * (wr_row + 1), 'r-')
        plt.plot(np.ones(2) * wr_col, np.arange(wr_row, wr_row + 2), 'r-')
        plt.plot(np.ones(2) * (wr_col + 75),
                 np.arange(wr_row, wr_row + 2), 'r-')
        self.whiteima.plot(cmap='copper')

    def _plot_slice_on_raw_image(self, ifu, sli, same_raw=False):
        mask_raw = RawFile(self.mask_file)
        chan = 'CHAN%02d' % ifu
        mask_chan = mask_raw.get_channel(chan)

        self.x1 = mask_chan.header['HIERARCH ESO DET SLICE1 XSTART'] \
            - OVERSCAN
        self.x2 = mask_chan.header['HIERARCH ESO DET SLICE48 XEND'] \
            - 2 * OVERSCAN

        xstart = mask_chan.header['HIERARCH ESO DET '
                                  'SLICE%d XSTART' % sli] - OVERSCAN
        xend = mask_chan.header['HIERARCH ESO DET '
                                'SLICE%d XEND' % sli] - OVERSCAN
        if xstart > (mask_chan.header["ESO DET CHIP NX"] / 2.0):
            xstart -= 2 * OVERSCAN
        if xend > (mask_chan.header["ESO DET CHIP NX"] / 2.0):
            xend -= 2 * OVERSCAN
        ystart = mask_chan.header['HIERARCH ESO DET '
                                  'SLICE%d YSTART' % sli] - OVERSCAN
        yend = mask_chan.header['HIERARCH ESO DET '
                                'SLICE%d YEND' % sli] - OVERSCAN
        if ystart > (mask_chan.header["ESO DET CHIP NY"] / 2.0):
            ystart -= 2 * OVERSCAN
        if yend > (mask_chan.header["ESO DET CHIP NY"] / 2.0):
            yend -= 2 * OVERSCAN

        plt.plot(np.arange(xstart, xend + 1),
                 np.ones(xend + 1 - xstart) * ystart, 'r-')
        plt.plot(np.arange(xstart, xend + 1),
                 np.ones(xend + 1 - xstart) * yend, 'r-')
        plt.plot(np.ones(yend + 1 - ystart) * xstart,
                 np.arange(ystart, yend + 1), 'r-')
        plt.plot(np.ones(yend + 1 - ystart) * xend,
                 np.arange(ystart, yend + 1), 'r-')
        plt.annotate('%02d' % sli, xy=(xstart, yend + 1),
                     xycoords='data', textcoords='data', color='r')
        if same_raw is False:
            self.rawima = self.get_channel(chan).get_trimmed_image()
        self.rawima.plot(title='CHAN%02d' % ifu, cmap='copper')
        self.plotted_chan = ifu

    def _onclick(self, event):
        if event.button != 1:
            if event.inaxes is not None:
                if (event.x < self.fig.canvas.get_width_height()[0] // 2):
                    p = event.ydata
                    q = event.xdata
                    ifu = 24 - int(p + 0.5) // NB_SLICES
                    k = int(q + 0.5) // NB_SPEC_PER_SLICE
                    pos = NB_SLICES + 12 * (24 - ifu) - int(p + 0.5)
                    l = np.where(slit_position == pos)[0][0] + 1
                    sli = k * NB_SLICES + l
                    ax = plt.subplot(1, 2, 1)
                    ax.clear()
                    self._plot_ifu_slice_on_white_image(ifu, sli)
                    ax = plt.subplot(1, 2, 2)
                    ax.clear()
                    if ifu == self.plotted_chan:
                        self._plot_slice_on_raw_image(ifu, sli,
                                                      same_raw=True)
                    else:
                        self._plot_slice_on_raw_image(ifu, sli)
                else:
                    p = event.ydata
                    q = event.xdata
                    nq = (self.x2 - self.x1) // 48
                    sli = int((q + 0.5 - self.x1) / nq) + 1
                    ax = plt.subplot(1, 2, 2)
                    ax.clear()
                    self._plot_slice_on_raw_image(self.plotted_chan,
                                                  sli, same_raw=True)
                    ax = plt.subplot(1, 2, 1)
                    ax.clear()
                    self._plot_ifu_slice_on_white_image(self.plotted_chan,
                                                        sli)

    def plot_white_image(self, mask=None):
        """Reconstructs the white image of the FOV using a mask file and plots
        this image.

        Parameters
        ----------
        mask : str
            mumdatMask_1x1.fits filename used for this reconstruction
            (if None, the last file stored in mpdaf is used).

        """
        if mask is None:
            path = os.path.dirname(__file__)
            self.mask_file = path + '/mumdatMask_1x1/PAE_July2013.fits'
        # create image
        self.whiteima = self.reconstruct_white_image(self.mask_file)
        # highlighted ifu
        selected_ifu = 12
        # plot white image
        self.fig = plt.figure()
        plt.subplot(1, 2, 1)
        self._plot_ifu_slice_on_white_image(selected_ifu, 1)
        # plot raw image
        plt.subplot(1, 2, 2)
        self._plot_slice_on_raw_image(selected_ifu, 1)
        self.fig.canvas.mpl_connect('button_press_event', self._onclick)
        print('To select on other channel/slice, '\
              'click on the images with the right mouse button.')


def _process_operator(arglist):
    # d ecorator used to define arithmetic functions with a RawFits object
    function = STR_FUNCTIONS[arglist[0]]
    k = arglist[1]
    obj = arglist[2]
    other = arglist[3]
    progress = arglist[4]
    v = obj.get_channel(k)
    try:
        v2 = other.get_channel(k)
    except:
        raise IOError('operations on raw files with different extensions')
    out = function(v, v2)
    if progress:
        sys.stdout.write(".")
        sys.stdout.flush()
    return (k, out)


def _process_operator2(arglist):
    # decorator used to define arithmetic functions with a number
    function = STR_FUNCTIONS[arglist[0]]
    k = arglist[1]
    obj = arglist[2]
    other = arglist[3]
    progress = arglist[4]
    v = obj.get_channel(k)
    out = function(v, other)
    if progress:
        sys.stdout.write(".")
        sys.stdout.flush()
    return (k, out)


def _process_operator3(arglist):
    # decorator used to define sqrt/trimmed
    function = STR_FUNCTIONS[arglist[0]]
    k = arglist[1]
    obj = arglist[2]
    progress = arglist[3]
    v = obj.get_channel(k)
    out = function(v)
    if progress:
        sys.stdout.write(".")
        sys.stdout.flush()
    return (k, out)


def _process_median(arglist):
    k = arglist[0]
    list_chan = arglist[1]
    out = Channel_median(list_chan)
    return (k, out)


def _process_white_image(arglist):
    chan = arglist[0]
    raw_mask = arglist[1]
    raw_ima = arglist[2]
    ifu = int(chan[-2:])
    mask_chan = raw_mask.get_channel(chan)
    ima = raw_ima.get_channel(chan).get_trimmed_image(bias=True).data.data
    mask = mask_chan.get_trimmed_image(bias=False).data.data
    ima *= mask
    spe = ima.sum(axis=0)
    data = np.empty((48, NB_SPEC_PER_SLICE))
    for sli in range(1, 49):
        xstart = mask_chan.header['HIERARCH ESO DET '
                                  'SLICE%d XSTART' % sli] - OVERSCAN
        xend = mask_chan.header['HIERARCH ESO DET '
                                'SLICE%d XEND' % sli] - OVERSCAN
        if xstart > (mask_chan.header["ESO DET CHIP NX"] / 2.0):
            xstart -= 2 * OVERSCAN
        if xend > (mask_chan.header["ESO DET CHIP NX"] / 2.0):
            xend -= 2 * OVERSCAN

        spe_slice = spe[xstart:xend + 1]
        n = spe_slice.shape[0]

        if n < NB_SPEC_PER_SLICE:
            spe_slice_75pix = np.zeros(NB_SPEC_PER_SLICE)
            spe_slice_75pix[:n] = spe_slice
        elif n == NB_SPEC_PER_SLICE:
            spe_slice_75pix = spe_slice
        else:
            spe_slice_75pix = np.empty(NB_SPEC_PER_SLICE, dtype=np.float)

        f = lambda x: spe_slice[int(x) + 0.5]
        pix = np.arange(NB_SPEC_PER_SLICE + 1, dtype=np.float)
        new_step = float(n) / NB_SPEC_PER_SLICE
        x = pix * new_step - 0.5 * new_step

        for i in range(NB_SPEC_PER_SLICE):
            spe_slice_75pix[i] = integrate.quad(f, x[i], x[i + 1],
                                                full_output=1)[0] / new_step

        data[sli - 1, :] = spe_slice_75pix
    return (ifu, data)


def RawFile_median(RawList):
    cpu_count = multiprocessing.cpu_count()
    result = RawFile()
    result.primary_header = RawList[0].primary_header
    result.nx = RawList[0].nx
    result.ny = RawList[0].ny
    result.next = RawList[0].next
    pool = multiprocessing.Pool(processes=cpu_count)
    processlist = list()
    if RawList[0].channels is not None:
        for k in RawList[0].channels.keys():
            ChanList = []
            for raw in RawList:
                ChanList.append(raw.get_channel(k))
            processlist.append([k, ChanList])
        processresult = pool.map(_process_median, processlist)
        for k, out in processresult:
            result.channels[k] = out
    return result
