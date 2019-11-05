#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function, division

"""
NE2001 for extragalactic work.
"""


from astropy.constants import kpc, c, au
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS
import astropy.units as u
import numpy as np
import os
import logging
from scipy.special import gamma

__author__ = ['Paul Hancock', 'Elliott Charlton']
__date__ = '2019-06-07'

SECONDS_PER_YEAR = 3600 * 24 * 365.25

class SM(object):
    """
    :param ha_file:
    :param err_file:
    :param nu: freq in Hz
    :param d: distance in kpc
    :param v: in m/s
    :param log:
    """
    def __init__(self, ha_file, err_file=None, nu=185e6, log=None, d=None, v=10e3):

        if log is None:
            logging.basicConfig(format="%(module)s:%(levelname)s %(message)s")
            self.log = logging.getLogger("SM2017")
            self.log.setLevel(logging.DEBUG)
        else:
            self.log=log

        # define some of the constants that we need
        # i'm saving these here to allow for different instances to have different values
        self.nu = nu  # Hz
        self.kpc = kpc.value  # in m
        self.t4 = 0.8  # t/1e4 K
        self.lo = 1e18/(self.kpc*1e-3)  # 1e18m expressed in pc (also armstrong_electron_1985 !)
        self.eps = 1
        self.D = d  # kpc - distance to the screen
        self.c = c.value
        self.beta = 11/3
        self.re = 2.817e-15  # m
        self.v = v  # relative velocity of source/observer in m/s
        self.file = ha_file
        self.err_file = err_file
        #self.tau_file = "/home/elliottcharlton/PycharmProjects/SM2017/data/tau_map_near.fits"
        self.tau_file = "/home/elliottcharlton/PycharmProjects/SM2017/data/tau_map.fits"
        self._load_file()



    def _load_file(self):
        self.hdu = fits.getheader(self.file, ignore_missing_end=True)
        self.wcs = WCS(self.hdu)
        self.data = fits.open(self.file, memmap=True, ignore_missing_end=True)[0].data
        self.thdu = fits.getheader(self.tau_file, ignore_missing_end=True)
        self.twcs=(WCS(self.thdu))
        self.tau = fits.open(self.tau_file, memmap=True, ignore_missing_end=True)[0].data
        if self.err_file:
            self.err_hdu = fits.getheader(self.err_file, ignore_missing_end=True)
            self.err_wcs = WCS(self.err_hdu)
            self.err_data = fits.open(self.err_file, memmap=True, ignore_missing_end=True)[0].data
        else:
            self.err_hud = self.err_wcs = self.err_data = None

        return

    def get_tau(self, position):
        """
        Return the Halpha for a given location on the sky.
        :param position: astropy.coordinates.SkyCoord
        :return:
        """
        # The coordinates we request need to be the same as that in the WCS header
        # for the files in this repo, this currently means galactic coordinates.
        x, y = zip(*self.twcs.all_world2pix(zip(position.galactic.l.degree, position.galactic.b.degree), 0))
        x = np.int64(np.floor(x))
        x = np.clip(x, 0, self.thdu['NAXIS1'])
        y = np.int64(np.floor(y))
        y = np.clip(y, 0, self.thdu['NAXIS2'])
        tau = self.tau[y, x]
        alpha = 4.
        #YMW16 assumes nu^-4 scaling for tau
        tau = (tau) * ((self.nu / 1e9) ** (-alpha))  # In seconds
        err_tau = 0.1 * tau
        return tau, err_tau

    def get_halpha(self, position):
        """
        Return the Halpha for a given location on the sky.
        :param position: astropy.coordinates.SkyCoord
        :return:
        """
        # The coordinates we request need to be the same as that in the WCS header
        # for the files in this repo, this currently means galactic coordinates.
        x, y = zip(*self.wcs.all_world2pix(list(zip(position.galactic.l.degree, position.galactic.b.degree)), 0))
        x = np.int64(np.floor(x))
        x = np.clip(x, 0, self.hdu['NAXIS1'])
        y = np.int64(np.floor(y))
        y = np.clip(y, 0, self.hdu['NAXIS2'])
        iha = self.data[y, x]
        err_iha = self.err_data[y, x]
        return iha, err_iha

    def get_sm(self, position):
        """
        Return the scintillation measure for a given location on the sky.
        Units are kpc m^{-20/3}
        :param position: astropy.coordinates.SkyCoord
        :return:
        """
        iha, err_iha = self.get_halpha(position)
        # Cordes2002
        sm2 = iha / 198 * self.t4 ** 0.9 * self.eps ** 2 / (1 + self.eps ** 2) * self.lo ** (-2 / 3)
        err_sm2 = (err_iha / iha) * sm2
        return sm2, err_sm2

    def get_rdiff(self, position):
        """
        Calculate the diffractive scale at the given sky coord
        :param position: astropy.coordinates.SkyCoord
        :return: parameter r_diff in m
        """
        sm2, err_sm2 = self.get_sm(position)
        # ^ units are kpc m^{-20/3}, but we want m^{-17/3} so we have to multiply by kpc below
        # r_diff as per Mcquart & Koay 2013, eq 7a.
        rdiff = (2 ** (2 - self.beta) * (
                    np.pi * self.re ** 2 * (self.c / self.nu) ** 2 * self.beta) * sm2 * self.kpc *
                 gamma(-self.beta / 2) / gamma(self.beta / 2)) ** (1 / (2 - self.beta))
        err_rdiff = abs((1 / (2 - self.beta)) * (err_sm2 / sm2) * rdiff)
        return rdiff, err_rdiff

    def get_rf(self, position):
        rdiff, err_rdiff = self.get_rdiff(position)
        tau, err_tau = self.get_tau(position)

        rf = rdiff * (4. * np.pi * self.nu * tau) ** (1. / 2.)

        err_rf = ((err_rdiff / rdiff) ** 2.0 + (1. / 2. * (err_tau / tau)) ** 2.0) * rf
        # rf = rdiff (m) x sqrt(tau(s) x nu(1/s))
        # rf = metres
        return rf, err_rf


    def get_xi(self, position):
        """
        calculate the parameter ξ for a given sky coord
        Parameter is dimensionless
        :param position: astropy.coordinates.SkyCoord
        :return: parameter ξ
        """
        rdiff, err_rdiff = self.get_rdiff(position)
        # Narayan 1992, uses r_F/r_diff = \xi without explicitly stating that this is being done
        # Compare Narayan 1992 eq 3.5 with Walker 1998 eq 6
        rf, err_rf = self.get_rf(position)
        xi = rf / rdiff
        err_xi = np.sqrt((err_rdiff / rdiff) ** 2.0 + (err_rf / rf) ** 2.0) * xi
        return np.array(xi),  np.array(err_xi)

    def get_theta(self, position):
        """
        calculate the size of the scattering disk for a given sky coord
        :param position: astropy.coordinates.SkyCoord
        :return: scattering disk in degrees
        """
        # See Narayan 1992 eq 4.10 and discussion immediately prior
        rdiff, err_rdiff = self.get_rdiff(position)
        theta = np.degrees((self.c/self.nu)/(2.* np.pi*rdiff))
        err_theta = np.degrees(err_rdiff / rdiff)*theta
        return  np.array(theta),  np.array(err_theta)

    def get_m(self, position, ssize=0):
        """
        calculate the modulation index using parameter ξ for a given sky coord
        :param position: astropy.coordinates.SkyCoord
        :param ssize: source size in deg
        :return:
        """
        ssize = np.zeros(len(position)) + ssize
        xi, err_xi = self.get_xi(position)
        m = xi ** (-1. / 3.)
        err_m = (1. / 3.) * (err_xi / xi) * m
        theta, err_theta = self.get_theta(position)
        mask = np.where(ssize > theta)
        if len(mask[0])>0:
            m[mask] = m[mask] * (theta[mask] / ssize[mask]) ** (7. / 6.)
            err_m[mask] = np.sqrt((err_m[mask]/m[mask]) ** (2.0) + ((7. / 6.) * (err_theta[mask] / theta[mask])) ** 2.) * m[mask]
        return m, err_m

    def get_timescale(self, position, ssize=0):
        """
        calculate the refractive timescale using parameter ξ for a given sky coord
        timescale is in years
        :param position: astropy.coordinates.SkyCoord
        :param ssize: source size in deg
        :return:
        """

        xi, err_xi = self.get_xi(position)
        ssize = np.zeros(len(position)) + ssize
        rf, err_rf = self.get_rf(position)
        tref = rf * xi / self.v / SECONDS_PER_YEAR
        err_tref = np.sqrt((err_xi / xi)**2.0 + (err_rf / rf)**2.0) * tref
        # timescale is longer for 'large' sources
        theta, err_theta = self.get_theta(position)
        large = np.where(ssize > theta)
        if len(large[0]) > 0:
            tref[large] = tref[large] * ssize[large] / theta[large]
            err_tref[large] = tref[large] * np.sqrt((err_tref[large]/tref[large])**2.  + (err_theta[large]/theta[large])**2.)
        return tref, err_tref

    def get_rms_var(self, position, ssize=0, nyears=1):
        """
        calculate the expected modulation index observed when measured on nyears timescales
        at a given sky coord
        :param position: astropy.coordinates.SkyCoord
        :param ssize: source size in deg
        :param nyears: timescale of interest
        :param ssize: source size in deg
        :return:
        """
        ssize = np.zeros(len(position)) + ssize
        tref, err_tref = self.get_timescale(position, ssize=ssize)
        m, err_m = self.get_m(position, ssize=ssize)
        short = np.where(nyears < tref)
        if len(short[0]) > 0:
            m[short] *= (nyears / tref[short])
            err_m[short] = np.sqrt((err_m[short]/m[short]) ** 2. + (err_tref[short] / tref[short]) ** 2.) * m[short]
        return m, err_m

    def get_vo(self, position):
        """
        Calculate the transition frequency at a given sky location
        :param position:
        :return: Transition frequency in GHz
        """
        #np.sqrt(self.c * self.get_distance(position) * self.kpc / (2 * np.pi * self.nu))
        sm2, _ = self.get_sm(position)
        pow = (1 / (2 - self.beta))
        A = (2 ** (2 - self.beta) * (np.pi * self.re ** 2 * self.beta) * sm2 * self.kpc *
             gamma(-self.beta / 2) / gamma(self.beta / 2)) ** pow
        rf, _=self.get_rf(position)
        vo = self.c * (rf*np.sqrt(self.c/self.nu) / A)**(1/(0.5 - 2*pow))
        return vo/1e9


def test_all_params():
    print("Testing with single positions")
    #original map
    #sm = SM(os.path.join('data', 'Halpha_map.fits'), os.path.join('data', 'Halpha_error.fits'), nu=1e8)
    #new map
    sm = SM(os.path.join('data', 'Ha_map_new.fits'), os.path.join('data', 'Ha_err_new.fits'), nu=1e8)
    pos = SkyCoord([0], [0], unit=(u.hour, u.degree))
    print("Hα = {0}".format(sm.get_halpha(pos)))
    print("ξ = {0}".format(sm.get_xi(pos)))
    print("m = {0}".format(sm.get_m(pos)))
    print("sm = {0} (m^-17/3)".format(sm.get_sm(pos)[0]*sm.kpc))
    print("t0 = {0} (sec)".format(sm.get_timescale(pos)))
    print("r_diff = {0} (m)".format(sm.get_rdiff(pos)))
    print("r_F = {0} (m)".format(sm.get_rf(pos)))
    print("rms = {0}".format(sm.get_rms_var(pos)))
    print("theta = {0} (rad)".format(np.radians(sm.get_theta(pos))))
    print("nu_0 = {0} (GHz)".format(sm.get_vo(pos)))

def test_multi_pos():
    print("Testing with list of positions")
    # original map
    # sm = SM(os.path.join('data', 'Halpha_map.fits'), os.path.join('data', 'Halpha_error.fits'), nu=1e8)
    # new map
    sm = SM(os.path.join('data', 'Ha_map_new.fits'), os.path.join('data', 'Ha_err_new.fits'), nu=1e8)
    pos = SkyCoord([0, 4, 8, 12, 16, 20]*u.hour, [-90, -45, 0, 45, 90, -26]*u.degree)
    print("Hα = {0}".format(sm.get_halpha(pos)))
    print("ξ = {0}".format(sm.get_xi(pos)))
    print("m = {0}".format(sm.get_m(pos)))
    print("sm = {0}".format(sm.get_sm(pos)))
    print("t0 = {0}".format(sm.get_timescale(pos)))
    print("rms = {0}".format(sm.get_rms_var(pos)))
    print("theta = {0}".format(sm.get_theta(pos)))

def write_multi_pos():
    from astropy.table import Table, Column
    RA=np.append(np.arange(0,360),np.arange(0,360))
    DEC=np.append(np.append(np.append(np.arange(-90,90),np.arange(-90,90)),np.arange(-90,90)),np.arange(-90,90))
    #Original map
    #sm = SM(os.path.join('data', 'Halpha_map.fits'), os.path.join('data', 'Halpha_error.fits'), nu=1e8)
    sm = SM(os.path.join('data', 'Ha_map_new.fits'), os.path.join('data', 'Ha_err_new.fits'), nu=1e8)



    pos = SkyCoord(RA * u.degree, DEC * u.degree)
    mvar=int(1)
    Ha,err_Ha=sm.get_halpha(pos)
    mod,err_m=sm.get_m(pos)
    t0,err_t0=sm.get_timescale(pos)
    theta,err_theta=sm.get_theta(pos)
    #tau,err_tau=sm.get_tau(pos)
    datatab1 = Table()
    datafile ='SM2017_test_m{0}.csv'.format(mvar)
    ### DATA FILE
    datatab1.add_column(Column(data=RA, name='RA'))
    datatab1.add_column(Column(data=DEC, name='DEC'))
    datatab1.add_column(Column(data=Ha, name='H_Alpha'))
    datatab1.add_column(Column(data=err_Ha, name='H_Alpha err'))
    #datatab1.add_column(Column(data=tau, name='Tau'))
    #datatab1.add_column(Column(data=err_tau, name='Tau err'))
    datatab1.add_column(Column(data=mod, name='Modulation'))
    datatab1.add_column(Column(data=err_m, name='Modulation err'))
    datatab1.add_column(Column(data=t0, name='Timescale'))
    datatab1.add_column(Column(data=err_t0, name='Timescale err'))
    datatab1.add_column(Column(data=theta, name='Theta'))
    datatab1.add_column(Column(data=err_theta, name='Theta err'))
    datatab1.write(datafile, overwrite=True)


def test_get_distance_empty_mask():
    print("Testing get_distance where the mask is empty")
    sm = SM(os.path.join('data', 'Halpha_map.fits'), os.path.join('data', 'Halpha_error.fits'))
    pos = SkyCoord([0, 0, 0, 12, 16, 20]*u.degree, [0.5, 1, 1.2, 90, 90, -90]*u.degree, frame='galactic')
    print("Hα = {0}".format(sm.get_halpha(pos)))
    print("ξ = {0}".format(sm.get_xi(pos)))
    print("m = {0}".format(sm.get_m(pos)))
    print("sm = {0}".format(sm.get_sm(pos)))
    print("t0 = {0}".format(sm.get_timescale(pos)))
    print("rms = {0}".format(sm.get_rms_var(pos)))
    print("theta = {0}".format(sm.get_theta(pos)))
    print("Distance = {0}".format(sm.get_distance(pos)))


if __name__ == "__main__":
    #test_all_params()
    test_multi_pos()
    #test_get_distance_empty_mask()
