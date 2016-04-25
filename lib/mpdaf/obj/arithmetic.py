# -*- coding: utf-8 -*-

import numpy as np
from numpy import ma

from .data import DataArray
from .objs import UnitMaskedArray, UnitArray


def _check_compatible_coordinates(a, b):
    if a.wave is not None and b.wave is not None and \
            not a.wave.isEqual(b.wave):
        raise ValueError('Operation forbidden for cubes with different world '
                         'coordinates in spectral direction')

    if a.wcs is not None and b.wcs is not None and \
            not a.wcs.isEqual(b.wcs):
        raise ValueError('Operation forbidden for cubes with different world '
                         'coordinates in spatial directions')


def _check_compatible_shapes(a, b, dims=slice(None)):
    if not np.array_equal(a.shape[dims], b.shape[dims]):
        raise ValueError('Operation forbidden for arrays with different '
                         'shapes')


def _arithmetic_data(operation, a, b, newshape=None):
    if a.unit != b.unit:
        data = UnitMaskedArray(b.data, b.unit, a.unit)
    else:
        data = b.data
    if newshape is not None:
        data = data.reshape(newshape)
    return operation(a.data, data)


def _arithmetic_var(operation, a, b, newshape=None):
    if a._var is None and b._var is None:
        return None

    if b._var is not None:
        if a.unit != b.unit:
            var = UnitArray(b._var, b.unit**2, a.unit**2)
        else:
            var = b._var

        if newshape is not None:
            var = var.reshape(newshape)

    if operation in (ma.add, ma.subtract):
        if b.var is None:
            return a.var
        elif a.var is None:
            return np.broadcast_to(var, a.shape)
        else:
            return a.var + var
    elif operation in (ma.multiply, ma.divide):
        b_data = b._data.reshape(newshape)
        if a._var is None:
            var = var * a._data * a._data
        elif b._var is None:
            var = a._var * b_data * b_data
        else:
            var = var * a._data * a._data + a._var * b_data * b_data

        if operation is ma.divide:
            var /= (b_data ** 4)
        return var


def _arithmetic(operation, a, b):
    if a.ndim < b.ndim:
        if operation == ma.subtract:
            return -1 * _arithmetic(operation, b, a)
        elif operation == ma.divide:
            return 1 / _arithmetic(operation, b, a)
        else:
            return _arithmetic(operation, b, a)

    _check_compatible_coordinates(a, b)

    if a.ndim == 3 and b.ndim == 1:  # cube + spectrum
        _check_compatible_shapes(a, b, dims=0)
        newshape = (-1, 1, 1)
    elif a.ndim == 3 and b.ndim == 2:  # cube + image
        _check_compatible_shapes(a, b, dims=slice(-1, -3, -1))
        newshape = (1, ) + b.shape
    elif a.ndim == 2 and b.ndim == 1:  # image + spectrum
        raise NotImplementedError
    else:
        _check_compatible_shapes(a, b)
        newshape = None

    res = a.clone()
    res.data = _arithmetic_data(operation, a, b, newshape=newshape)
    res.var = _arithmetic_var(operation, a, b, newshape=newshape)
    return res


class ArithmeticMixin(object):

    def __add__(self, other):
        if not isinstance(other, DataArray):
            return self.__class__.new_from_obj(
                self, data=self._data + other, copy=True)
        else:
            return _arithmetic(ma.add, self, other)

    def __sub__(self, other):
        if not isinstance(other, DataArray):
            return self.__class__.new_from_obj(
                self, data=self._data - other, copy=True)
        else:
            return _arithmetic(ma.subtract, self, other)

    def __rsub__(self, other):
        if not isinstance(other, DataArray):
            return self.__class__.new_from_obj(
                self, data=other - self._data, copy=True)
        # else:
        #     return other.__sub__(self)

    def __mul__(self, other):
        if not isinstance(other, DataArray):
            res = self.__class__.new_from_obj(
                self, data=self._data * other, copy=True)
            if self._var is not None:
                res._var *= other ** 2
            return res
        else:
            return _arithmetic(ma.multiply, self, other)

    def __div__(self, other):
        if not isinstance(other, DataArray):
            res = self.__class__.new_from_obj(
                self, data=self._data / other, copy=True)
            if self._var is not None:
                res._var /= other ** 2
            return res
        else:
            return _arithmetic(ma.divide, self, other)

    def __rdiv__(self, other):
        # FIXME: check var
        if not isinstance(other, DataArray):
            res = self.__class__.new_from_obj(
                self, data=other / self._data, copy=True)
            # if self._var is not None:
            #     res._var = other ** 2 / res._var
            if self._var is not None:
                res._var = (self._var * other**2 +
                            other * self._data * self._data) / self._data**4
            return res
        # else:
        #     return other.__div__(self)

    __radd__ = __add__
    __rmul__ = __mul__
    __truediv__ = __div__
    __rtruediv__ = __rdiv__
