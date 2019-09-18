from __future__ import print_function, division
import os
import logging
import cPickle
import argparse
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.table import Table, Column
import astropy.units as u
from lib.tau import SM
from astropy.utils.exceptions import AstropyWarning
import warnings
warnings.filterwarnings("ignore")
import matplotlib.pyplot as plt
#warnings.filterwarnings("always")
#warnings.simplefilter('ignore', category=AstropyWarning)

datadir = os.path.join(os.path.dirname(__file__), 'data')
SFG=0
AGN=1
stypes=[SFG, AGN]
#sprobs=[0.84839, 1-0.84839] #0.15161
sprobs=[1-0.84839,0.84839]
parser = argparse.ArgumentParser()

parser.add_argument('-FUL', action='store', dest='FUL', default=1.,
                    help='Store upper flux limit (Jy)')
parser.add_argument('-FLL', action='store', dest='FLL', default=0.01,
                    help='Store lower flux limit (Jy)')
parser.add_argument('-mc', action='store', dest='mc', default=0.05,
                    help='Store modulation cut off value')
parser.add_argument('-t', action='store', dest='obs_time', default=365.,
                    help='observation time in days')
parser.add_argument('-a', action='store', dest='a', default=3300.,
                    help='Scaling Constant for source counts')
parser.add_argument('-scount', action='store', dest='scount', default=False,
                    help='Number of sources')
parser.add_argument('-f', action='store', dest='nu', default=185.,
                    help='Frequency in MHz')
parser.add_argument('-i', action='store', dest='loops', default=20,
                    help='Number of iterations to run program through (30+ recommended)')
parser.add_argument('-reg', action='store', dest='region_name',
                    help='read in region file')
parser.add_argument('-map', action='store', dest='map', default=0,
                    help='Select old (0) or new (1) Ha maps')
parser.add_argument('--out', dest='outfile', default=False, type=str,
                        help="Output file name for results including file type (.csv)")
parser.add_argument('--fig', dest='figure', default=False,
                        help="Save Figure?")

parser.add_argument('--version', action='version', version='%(prog)s 1.0')

results = parser.parse_args()
outfile=results.outfile
class SIM(object):
    def __init__(self, log=None):


        if log is None:
            logging.basicConfig(format="%(module)s:%(levelname)s %(message)s")
            self.log = logging.getLogger("SIM_new")
            self.log.setLevel(logging.DEBUG)
        else:
            self.log=log
        #Variables
        self.figure=results.figure
        self.nu = np.float(results.nu) * 1e6 #Hz, Default 185 MHz
        self.arcsec = np.pi / (180. * 3600.)
        self.mod_cutoff = np.float(results.mc) #Default 0.05
        self.low_Flim = np.float(results.FLL)  # Jy, Default 0.01 Jy
        self.upp_Flim = np.float(results.FUL) # Jy, Default 1 Jy
        self.region_name = results.region_name
        region=cPickle.load(open(self.region_name, 'rb'))
        self.area = region.get_area(degrees=True)
        self.obs_time = np.float(results.obs_time) * 24. * 60. * 60. # seconds, Default 183 days
        self.loops=np.int(results.loops) #Default 20
        self.num_scale=40
        self.a=np.float(results.a) #Default 3300
        self.map=float(results.map)
        if self.map==1:
            self.ha_file = 'Ha_map_new.fits'
            self.err_file = 'Ha_err_new.fits'
        elif self.map==0:
            self.ha_file = 'Halpha_map.fits'
            self.err_file = 'Halpha_error.fits'

        self.scount=float(results.scount)

    def flux_gen(self):
        """
        Function to distribute flux across all points
        Input:  Flux Density limit, RA/DEC positions, source distribution function
        Output: Flux for each RA/DEC point
        """
        low=self.low_Flim
        upp=self.upp_Flim
        #Function that finds dN = (alpha * [Flux] ** (1-b))/ 1-b
        def dn_func(val, a, b):
            output = (a * val ** (1.0 - b)) / (1.0 - b)
            return output
        #Takes input of lower flux, upper flux, a and b values to create differentail flux counts in that range.
        #Main outputs: Bins, Ni.
        def diff_counts(a, b, low, upp):
            low=np.log10(low)
            upp=np.log10(upp)
            bins = np.logspace(low, upp, num=100)
            Ni = []
            mpoint = []
            dS = []
            for i in range(0, len(bins) - 1):
                Ni.append(dn_func(bins[i + 1], a, b) - dn_func(bins[i], a, b))
                mpoint.append(np.sqrt(bins[i + 1] * bins[i]))
                dS.append(bins[i + 1] - bins[i])
            Ni = np.array(Ni)
            mpoint = np.array(mpoint)
            dS = np.array(dS)
            dNdS= Ni / dS
            return bins, dNdS, mpoint, Ni, dS
        a = self.a
        bins, dnds, mid, Ni, width = diff_counts(a, 1.6, low, upp)
        Area = self.area * (np.pi ** 2.) / (180. ** 2.)
        #print('bins',sum(bins))
        #print(sum(Ni))
        scount=self.scount
        #print(scount)
        plim=0.01
        num_s = 0
        for i in range(0, len(bins) - 1):
            num_s = num_s + int(Ni[i] * Area)
        if scount!=False:
            while ((num_s  >= scount + plim * scount) or (num_s  <= scount - plim * scount)):
                num_s = 0
                for i in range(0, len(bins) - 1):
                    num_s = num_s + int(Ni[i] * Area)
                    #print('num_s', num_s)
                if num_s >= scount + plim * scount:
                    a = a-plim*a
                    bins, dnds, mid, Ni, width = diff_counts(a, 1.6, low, upp)
                if num_s  <= scount - plim * scount:
                    a = a + 0.01 * a
                    bins, dnds, mid, Ni, width = diff_counts(a, 1.6, low, upp)
                #print('a', a)
            #if (Ni>scount+0.05*scount or Ni<scount-0.05*scount):
        FLUX = []
        self.a=a

        for i in range(0, len(bins) - 1):
            rang = np.logspace(np.log10(bins[i]), np.log10(bins[i]+width[i]), dtype=float)
            FLUX.extend(np.random.choice(rang, size=int(Ni[i]*Area)))
        flux_arr = np.random.permutation(np.array(FLUX))
        #print(len(flux_arr))
        #print(np.sum(Ni)*Area)

        return flux_arr, len(flux_arr)

    def pos_gen(self):
        """
        A function to generate a number of random points in RA/DEC
        Input:  Number of points to generate from flux_gen function
        Output: List of RA/DEC (2,1) array in (2D) Cartesian coordiantes.
        """
        num=self.flux_gen()[1]
        num=num*self.num_scale
        lim = int(num * 2.5)
        x = []
        y = []
        z = []
        r = []
        i = 0
        #Generating cube
        x1 = np.array(np.random.uniform(-1.0, 1.0, lim))
        y1 = np.array(np.random.uniform(-1.0, 1.0, lim))
        z1 = np.array(np.random.uniform(-1.0, 1.0, lim))
        rad = (x1 ** 2.0 + y1 ** 2.0 + z1 ** 2.0) ** (0.5)
        #Getting points inside sphere of radius 1
        for i in range(0, len(rad)):
            if rad[i] <= 1.:
                x.append(x1[i])
                y.append(y1[i])
                z.append(z1[i])
                r.append(rad[i])
        x, y, z = np.array(x) / np.array(r), np.array(y) / np.array(r), np.array(z) / np.array(r)
        r0 = (x ** 2.0 + y ** 2.0 + z ** 2.0) ** 0.5
        #converting back to cartesian cooridantes
        theta = np.arccos(z / r0) * 180 / np.pi
        theta = theta - 90.
        theta = theta[:num]
        phi = np.arctan2(y, x) * 180. / (np.pi)
        phi = phi + 180.
        phi = phi[:num]
        return phi, theta

    def region_gen(self, reg_file):
        """
        Takes in a list of positions and removes points outside the MIMAS region
        Input:  RA/DEC positions and MIMAS region file.
        Output: List of RA/DEC inside the correct region.
        """

        reg_ind = []
        reg_ra = []
        reg_dec = []
        region = cPickle.load(open(reg_file, 'rb'))
        num=self.flux_gen()[1]
        #print(num)
        while len(reg_ind) < num:
            RA, DEC = self.pos_gen()
            #print(len(RA))
            reg_arr = region.sky_within(RA, DEC, degin=True)
            for i in range(0, len(reg_arr)):
                if len(reg_ra) < num:
                    reg_ind.append(i)
                    reg_ra.append(RA[i])
                    reg_dec.append(DEC[i])
                    #print(len(reg_ind), len(reg_dec))
        return np.array(reg_ra), np.array(reg_dec)

    def stype_gen(self,arr):
        """
        Function to determine if a source is of type compact or extended
        Input:  RA/DEC list (source_size?)
        Output: compact (1?) or extended (0?)
        """
        stype_arr = []
        for i in range(0, len(arr)):
            stype_arr.append(np.random.choice(stypes, p=sprobs))
        return stype_arr

    def ssize_gen(self, stype):
        """
        Generates source size based stype given.
        Input: Flux and source type
        Output: Source size
        """
        """
        tt = theta
        tm = np.nanmean(tt)
        #tmed = np.nanmedian(tt)
        cn = tt[np.where(tt <= tm)]
        en = tt[np.where(tt > tm)]

        # en=np.ran
        # print cn
        ssize = []
        # 0 = extended
        # 1 = compact
        for i in range(0, len(tt)):
            if stype[i] == 0:
                ssize.append(np.random.choice(en))
            if stype[i] == 1:
                ssize.append(np.random.choice(cn))
        """
        ssize_arr=[]
        for i in range(0, len(stype)):

            if stype[i] == AGN:
                # 2 milli arc secs
                ssize_arr.append((0.5*1e-3)/3600.) #(0.0979/(3600.)) actual values
            elif stype[i] == SFG:
                # 30 milli arc secs
                ssize_arr.append((10*1e-3)/3600.) #(0.2063/(3600.)) actual values

        return np.array(ssize_arr)


    def output_gen(self, ra, dec, ssize):
        """
        Function to use SM2017 to get Modulation, Timescale, Halpha, Theta and other values.
        Input: RA, DEC, Source Size
        Output: Modulation, Timescale, Halpha, Theta
        """
        nu = np.float(self.nu)
        frame = 'fk5'
        tab = Table()

        # create the sky coordinate
        pos = SkyCoord(ra * u.degree, dec * u.degree, frame=frame)
        # make the SM object

        sm = SM(ha_file=os.path.join(datadir, self.ha_file),
                err_file=os.path.join(datadir, self.err_file),
                nu=nu, d=0)
        # Halpha
        Ha, err_Ha = sm.get_halpha(pos)
        # xi
        #xi, err_xi = sm.get_xi(pos)
        # theta
        theta, err_theta = sm.get_theta(pos)
        # sm
        #sm, err_sm = sm.get_sm(pos)
        # mod
        m, err_m = sm.get_m(pos, ssize)
        # t0
        t0, err_t0 = sm.get_timescale(pos)
        # rms
        #val6, err6 = sm.get_rms_var(pos, stype, ssize)

        #tau
        tau, err_tau=sm.get_tau(pos)
        return m, err_m, t0, err_t0, Ha, err_Ha , theta, err_theta, tau, err_tau

    def areal_gen(self):
        """
        Function to generate the areal sky density (ASD) values
        Uses: Flux, Region, Stype, Ssize, Output (Ha, mod, t0, theta), Obs_Yrs
        Output: ASD, modulation, timescale, Ha, Theta
        """
        flux, num = self.flux_gen()
        RA, DEC = self.region_gen(self.region_name)
        #print('RA')
        stype = self.stype_gen(RA)
        ssize = self.ssize_gen(stype)
        #print('SS')
        mod, err_m, t0, err_t0, Ha, err_Ha, theta, err_theta, tau, err_tau= self.output_gen(RA, DEC, ssize)
        obs_yrs = self.obs_time / (3600. * 24. * 365.25)
        for i in range(0, len(t0) - 1):
            if obs_yrs <= t0[i]:
                mod[i] = mod[i] * (np.float(obs_yrs / t0[i]))
                err_m[i] = err_m[i] * (np.float(obs_yrs / t0[i]))
        mp = np.random.normal(loc=mod, scale=err_m)
        vcount=0
        mcount=0
        v_arr=np.zeros(len(flux))
        m_arr=np.zeros(len(flux))
        for i in range(0,len(mp)):
            if mp[i]*flux[i]>=self.low_Flim/5.:
                vcount=vcount+1
                v_arr[i]=1
            if mp[i]>=self.mod_cutoff:
                mcount=mcount+1
                m_arr[i]=1
        #print(vcount,mcount)
        #print(np.nanmean(theta*3600))
        mareal = float(mcount) / self.area
        vareal = float(vcount) / self.area
        """
        mcert = 0
        muncert=0
        nonvar=0
        var = [] #Definitely Var
        mvar = [] #Maybe Var
        nvar = [] #Non Var
        mnvar = []  # Maybe Non Var
        #print(mod[np.where(mod=='nan')])
        for i in range(0, len(t0) - 1):
            if obs_yrs <= t0[i]:
                mod[i] = mod[i] * (np.float(obs_yrs/t0[i]))
                err_m[i]= err_m[i] * (np.float(obs_yrs/t0[i]))
        for i in range(0, len(mod)):
            if mod[i] >= self.mod_cutoff and mod[i] - err_m[i]>= self.mod_cutoff:
                #mcert = mcert + 1
                var.append(mod[i])
            elif mod[i] >= self.mod_cutoff and mod[i] - err_m[i] <= self.mod_cutoff:
                #muncert = muncert + 1
                mvar.append(mod[i])
            elif mod[i] <= self.mod_cutoff and mod[i] + err_m[i] >= self.mod_cutoff:
                #var = nvar + 1
                mnvar.append(mod[i])
            elif mod[i] <= self.mod_cutoff and mod[i] + err_m[i] <= self.mod_cutoff:
                #mnvar=nonvar+1
                nvar.append(mod[i])
        areal = float(len(var)+len(mvar)) / self.area
        print(len(var), len(mvar), len(mnvar), len(nvar), (len(var)+len(mvar)+len(mnvar)+len(nvar)),len(mod))
        #print(np.nanmean(err_m)*100./np.nanmean(mod))
        """
        datatab1 = Table()
        mvar=int(self.map)
        datafile = self.region_name[8:-4] + '_tau' +'_m{0}_data.csv'.format(mvar)
        #print('mod_mean',np.mean(mod))
        ### DATA FILE
        datatab1.add_column(Column(data=RA, name='RA'))
        datatab1.add_column(Column(data=DEC, name='DEC'))
        datatab1.add_column(Column(data=Ha, name='H_Alpha'))
        datatab1.add_column(Column(data=err_Ha, name='H_Alpha err'))
        datatab1.add_column(Column(data=mod, name='Modulation'))
        datatab1.add_column(Column(data=err_m, name='Modulation err'))
        datatab1.add_column(Column(data=t0, name='Timescale'))
        datatab1.add_column(Column(data=err_t0, name='Timescale err'))
        datatab1.add_column(Column(data=theta, name='Theta'))
        datatab1.add_column(Column(data=err_theta, name='Theta err'))
        datatab1.add_column(Column(data=tau, name='Tau'))
        datatab1.add_column(Column(data=err_tau, name='Tau err'))
        datatab1.write(datafile, overwrite=True)
        return mareal, mp, t0, Ha, theta, flux, vareal

    def repeat(self):
        """
        Function to repeate the ASD calculation
        Input: Number of iterations set at beginning
        Output: Arrays of Modulation, Timescale, Halpha, Theta as well as other statistics.
        """
        areal_arr = []
        mod_arr = np.empty((self.loops,2))
        t0_arr = np.empty((self.loops,2))
        Ha_arr = np.empty((self.loops,2))
        theta_arr = np.empty((self.loops,2))
        NSources = []
        count = 0

        for i in range(0, self.loops):
            INPUT = self.areal_gen()
            areal_arr.append(INPUT[0])
            mod_arr[i,:]=[np.mean(INPUT[1]), np.std(INPUT[1])]
            t0_arr[i,:]=[np.mean(INPUT[2]), np.std(INPUT[2])]
            Ha_arr[i,:]=[np.mean(INPUT[3]), np.std(INPUT[3])]
            theta_arr[i,:]=[np.mean(INPUT[4]), np.std(INPUT[4])]
            count=count+1
            NSources.append(len(INPUT[1]))
        areal_arr = np.array(areal_arr)
        NSources = np.array(NSources)

        return areal_arr, mod_arr,t0_arr, Ha_arr, theta_arr, count, NSources, self.area, self.low_Flim, self.upp_Flim, self.obs_time, self.nu, self.mod_cutoff, self.a


def test():
    """
    This section collects runs the previous functions and outputs them to two different files.
    Data file: Includes raw data from each iteration.
    Results file: Returns averaged results.
    """

    sim=SIM()
    areal_arr, mod_arr, t0_arr, Ha_arr, theta_arr, count, NSources, area, low_Flim, upp_Flim, obs_time, nu, mod_cutoff, a=sim.repeat()
    datatab=Table()
    resultstab=Table()
    if outfile != False:
        datafile=outfile[:-4]+'_data'+outfile[-4:]
        ### DATA FILE
        datatab.add_column(Column(data=np.arange(1,len(areal_arr)+1,1), name='Interations'))
        datatab.add_column(Column(data=Ha_arr[:,0], name='H_Alpha Mean'))
        datatab.add_column(Column(data=Ha_arr[:,1], name='H_Alpha STD'))
        datatab.add_column(Column(data=mod_arr[:,0], name='Modulation Mean'))
        datatab.add_column(Column(data=mod_arr[:,1], name='Modulation STD'))
        datatab.add_column(Column(data=t0_arr[:,0], name='Timescale Mean'))
        datatab.add_column(Column(data=t0_arr[:,1], name='Timescale STD'))
        datatab.add_column(Column(data=theta_arr[:,0], name='Theta Mean'))
        datatab.add_column(Column(data=theta_arr[:,1], name='Theta STD'))
        datatab.add_column(Column(data=areal_arr, name='Areal Sky Density'))
        datatab.write(datafile, overwrite=True)

        ##RESUTLS FILE
        resultsfile = outfile[:-4] + '_results' + outfile[-4:]
        Stats = ['H_Alpha Mean','H_Alpha STD', 'Modulation Mean', 'Modulation STD', 'Timescale Mean (yrs)', 'Timescale STD (yrs)',
               'Theta Mean (deg)', 'Theta STD (deg)', 'Areal Sky Desnity Mean',  'Areal Sky Desnity STD']
        Stats_vals = [np.mean(Ha_arr[:,0]),np.std(Ha_arr[:,0]),np.mean(mod_arr[:,0]),np.std(mod_arr[:,0]),
                    np.mean(t0_arr[:,0]),np.std(t0_arr[:,0]), np.mean(theta_arr[:,0]),np.std(theta_arr[:,0]),
                    np.mean(areal_arr), np.std(areal_arr)]
        Params = ['Avg # Sources', 'Avg Variables','Area (deg^2)', 'Lower Flux Limit (Jy)', 'Upper Flux Limit (Jy)', 'Observation time (days)', 'Frequency (MHz)', 'Modulation Cutoff']
        Params.extend(["",""])
        Param_vals =[ np.mean(NSources),area*np.mean(areal_arr), area, low_Flim, upp_Flim, obs_time/(24.*3600.), nu/(1E6), mod_cutoff]
        Param_vals.extend(["", ""])

        resultstab.add_column(Column(data=Stats, name='Statistics'))
        resultstab.add_column(Column(data=Stats_vals, name='Results'))
        resultstab.add_column(Column(data=Params, name='Parameters'))
        resultstab.add_column(Column(data=Param_vals, name='Values'))
        resultstab.write(resultsfile, overwrite=True)
    if outfile == False:
        print("Array: {0}".format(areal_arr))
        print("Avg Areal: {0}".format(np.mean(areal_arr)))
        print("Iterations: {0}".format(len(areal_arr)))
        print("Num Sources: {0}".format(np.mean(NSources)))
        print("Area: {0}".format(area))
        print("Num Variable: {0}".format(np.mean(areal_arr)*area))
        print("a: {0}".format(a))


test()