/*
tools.h
-------

different C methods used by several functions
*/

// Compute the arithmetic mean
void mpdaf_mean(double* data, int n, double x[3], int* indx);
// Compute sum
double mpdaf_sum(double* data, int n, int* indx);
// Compute the median
double mpdaf_median(double* data, int n, int* indx);
int indexx(int n, double *arr, int *indx);
// Iterative sigma-clipping of array elements
void mpdaf_mean_sigma_clip(double* data, int n, double x[3], int nmax, double nclip_low, double nclip_up, int nstop, int* indx);
void mpdaf_median_sigma_clip(double* data, int n, double x[3], int nmax, double nclip_low, double nclip_up, int nstop, int* indx);
// Linear interpolation
int mpdaf_locate(double* data, int n, double x);
double mpdaf_linear_interpolation(double* xx, double* yy, int n, double x);
