
import logging
import numpy as np
import os

from astropy.io import fits as pyfits
from numpy import ma

from .coords import WCS, WaveCoord

# __all__ = ['iter_spe', 'iter_ima', 'Cube', 'CubeDisk']


def is_valid_fits_file(filename):
    return os.path.isfile(filename) and filename.endswith(("fits", "fits.gz"))


def read_slice_from_fits(filename, item=None, ext='DATA', mask_ext=None,
                         dtype=None):
    hdulist = pyfits.open(filename)
    if item is None:
        data = np.asarray(hdulist[ext].data, dtype=dtype)
    else:
        data = np.asarray(hdulist[ext].data[item], dtype=dtype)

    # mask extension
    if mask_ext is not None and mask_ext in hdulist:
        mask = ma.make_mask(hdulist[mask_ext].data[item])
        data = ma.MaskedArray(data, mask=mask)

    hdulist.close()
    return data


class DataArray(object):

    """Base class to handle arrays.

    Parameters
    ----------
    filename : string
                Possible FITS file name. None by default.
    ext      : integer or (integer,integer) or string or (string,string)
                Number/name of the data extension
                or numbers/names of the data and variance extensions.
    notnoise : boolean
                True if the noise Variance cube is not read (if it exists).
                Use notnoise=True to create cube without variance extension.
    shape    : integer or (integer,integer,integer)
                Lengths of data in Z, Y and X. Python notation is used
                (nz,ny,nx). If data is not None, its shape is used instead.
    wcs      : :class:`mpdaf.obj.WCS`
                World coordinates.
    wave     : :class:`mpdaf.obj.WaveCoord`
                Wavelength coordinates.
    unit     : string
                Possible data unit type. None by default.
    data     : float array
                Array containing the pixel values of the cube. None by
                default.
    var      : float array
                Array containing the variance. None by default.

    Attributes
    ----------
    filename       : string
                     Possible FITS filename.
    unit           : string
                     Possible data unit type
    primary_header : pyfits.Header
                     FITS primary header instance.
    data_header    : pyfits.Header
                     FITS data header instance.
    data           : masked array numpy.ma
                     Array containing the cube pixel values.
    shape          : array of 3 integers
                     Lengths of data in Z and Y and X
                     (python notation (nz,ny,nx)).
    var            : float array
                     Array containing the variance.
    wcs            : :class:`mpdaf.obj.WCS`
                     World coordinates.
    wave           : :class:`mpdaf.obj.WaveCoord`
                     Wavelength coordinates
    """

    _ndim = None

    def __init__(self, filename=None, ext=None, notnoise=False,
                 wcs=None, wave=None, unit=None, data=None, var=None,
                 copy=True, dtype=float):
        d = {'class': self.__class__.__name__, 'method': '__init__'}
        self.logger = logging.getLogger('mpdaf corelib')
        self.filename = filename
        self._data = None
        self._data_ext = None
        self._var = None
        self._var_ext = None
        self._shape = None
        self.wcs = None
        self.wave = None
        self.dtype = dtype
        self.unit = unit
        self.data_header = pyfits.Header()
        self.primary_header = pyfits.Header()

        if filename is not None:
            if not is_valid_fits_file(filename):
                raise IOError('Invalid file: %s' % filename)

            hdulist = pyfits.open(filename)
            # primary header
            self.primary_header = hdulist[0].header

            if len(hdulist) == 1:
                # if the number of extension is 1,
                # we just read the data from the primary header
                self._data_ext = 0
            elif ext is None:
                if 'DATA' in hdulist:
                    self._data_ext = 'DATA'
                elif 'SCI' in hdulist:
                    self._data_ext = 'SCI'
                else:
                    raise IOError('no DATA or SCI extension')

                if 'STAT' in hdulist:
                    self._var_ext = 'STAT'
            elif isinstance(ext, (list, tuple, np.ndarray)):
                self._data_ext = ext[0]
                self._var_ext = ext[1]

            if notnoise:
                self._var_ext = None

            self.data_header = hdr = hdulist[self._data_ext].header
            self.unit = hdr.get('BUNIT', None)
            self._shape = hdulist[self._data_ext].data.shape

            if self._ndim is not None and hdr['NAXIS'] != self._ndim:
                raise IOError('Wrong dimension number, should be %s'
                              % self._ndim)

            try:
                self.wcs = WCS(hdr)  # WCS object from data header
            except pyfits.VerifyError as e:
                # Workaround for
                # https://github.com/astropy/astropy/issues/887
                self.logger.warning(e, extra=d)
                self.wcs = WCS(hdr)

            # Wavelength coordinates
            if 'CRPIX3' in hdr and 'CRVAL3' in hdr:
                if 'CDELT3' in hdr:
                    cdelt = hdr.get('CDELT3')
                elif 'CD3_3' in hdr:
                    cdelt = hdr.get('CD3_3')
                else:
                    cdelt = 1.0
                cunit = hdr.get('CUNIT3', '')
                ctype = hdr.get('CTYPE3', 'LINEAR')
                self.wave = WaveCoord(hdr['CRPIX3'], cdelt, hdr['CRVAL3'],
                                      cunit, ctype, self._shape[0])

            hdulist.close()
        else:
            if data is not None:
                self._data = ma.MaskedArray(data, dtype=dtype, copy=copy)
                self._shape = self._data.shape

            if not notnoise and var is not None:
                self._var = np.array(var, dtype=dtype, copy=copy)

        if wcs is not None:
            try:
                self.wcs = wcs.copy()
                if wcs.naxis1 != 0 and wcs.naxis2 != 0 and \
                    (wcs.naxis1 != self._shape[2] or
                        wcs.naxis2 != self._shape[1]):
                    self.logger.warning(
                        'world coordinates and data have not the same '
                        'dimensions: shape of WCS object is modified', extra=d)
                self.wcs.naxis1 = self._shape[2]
                self.wcs.naxis2 = self._shape[1]
            except:
                self.logger.warning('world coordinates not copied',
                                    exc_info=True, extra=d)

        if wave is not None:
            try:
                self.wave = wave.copy()
                if wave.shape is not None and wave.shape != self._shape[0]:
                    self.logger.warning(
                        'wavelength coordinates and data have not the same '
                        'dimensions: shape of WaveCoord object is modified',
                        extra=d)
                self.wave.shape = self._shape[0]
            except:
                self.logger.warning('wavelength solution not copied',
                                    exc_info=True, extra=d)

    @property
    def shape(self):
        if self._shape is not None:
            return self._shape
        else:
            return self.data.shape

    @property
    def data(self):
        if self._data is None and self.filename is not None:
            self._data = read_slice_from_fits(
                self.filename, ext=self._data_ext, mask_ext='DQ',
                dtype=self.dtype)

            # Mask an array where invalid values occur (NaNs or infs).
            if ma.is_masked(self._data):
                self._data.mask |= ~(np.isfinite(self._data.data))
            else:
                self._data = ma.masked_invalid(self._data)
            self._shape = self._data.shape

        return self._data

    @data.setter
    def data(self, value):
        self._data = ma.MaskedArray(value)
        self._shape = self._data.shape

    @property
    def var(self):
        if self._var is None and self._var_ext is not None and \
                self.filename is not None:
            var = read_slice_from_fits(
                self.filename, ext=self._var_ext, dtype=self.dtype)
            if var.ndim != self.data.ndim:
                raise IOError('Wrong dimension number in STAT extension')
            if not np.array_equal(var.shape, self.data.shape):
                raise IOError('Number of points in STAT not equal to DATA')
            self._var = var

        return self._var
