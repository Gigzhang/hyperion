import os
import hashlib
import warnings

import atpy
import numpy as np

import hyperion

from hyperion.util.constants import c
from hyperion.util.functions import FreezableClass
from hyperion.util.interpolate import interp1d_fast_loglog

from hyperion.dust.optical_properties import OpticalProperties
from hyperion.dust.emissivities import Emissivities
from hyperion.dust.mean_opacities import MeanOpacities

import matplotlib.pyplot as mpl

mpl.rc('axes', titlesize='x-small')
mpl.rc('axes', labelsize='x-small')
mpl.rc('xtick', labelsize='xx-small')
mpl.rc('ytick', labelsize='xx-small')
mpl.rc('axes', linewidth=0.5)
mpl.rc('patch', linewidth=0.5)


def henyey_greenstein(mu, g, p_lin_max):
    P1 = (1. - g * g) / (1. + g * g - 2. * g * mu) ** 1.5
    P2 = - p_lin_max * P1 * (1. - mu * mu) / (1. + mu * mu)
    P3 = P1 * 2. * mu / (1. + mu * mu)
    P4 = 0.
    return P1, P2, P3, P4


class SphericalDust(FreezableClass):

    def __init__(self, *args):

        self.filename = None
        self.md5 = None

        self.optical_properties = OpticalProperties()
        self.emissivities = Emissivities()
        self.mean_opacities = MeanOpacities()

        self.set_sublimation_specific_energy('no', 0.)

        self._freeze()

        if len(args) == 0:
            pass
        elif len(args) == 1:
            self.read(args[0])
        else:
            raise Exception("SphericalDust cannot take more than one argument")

    def plot(self, filename):

        # Check that emissivities are set (before computing mean opacities)
        if not self.emissivities.set:
            warnings.warn("Computing emissivities assuming LTE")
            self.emissivities.set_lte(self.optical_properties)

        # Compute mean opacities if not already existent
        if not self.mean_opacities.set:
            self.mean_opacities.compute(self.emissivities, self.optical_properties)

        # Initialize figure
        fig = mpl.figure(figsize=(8, 8))

        # Plot optical properties
        fig = self.optical_properties.plot(fig, [421, 423, 424, 425, 426])

        # Plot emissivities
        fig = self.emissivities.plot(fig, 427)

        # Plot mean opacities
        fig = self.mean_opacities.plot(fig, 422)

        # Save figure
        fig.savefig(filename)

    def set_sublimation_temperature(self, mode, temperature=0.):
        '''
        Set the dust sublimation mode and temperature.

        Parameters
        ----------
        mode : str
            The dust sublimation mode, which can be:
                * 'no'   - no sublimation
                * 'fast' - remove all dust in cells exceeding the
                           sublimation temperature
                * 'slow' - reduce the dust in cells exceeding the
                           sublimation temperature
                * 'cap'  - any temperature exceeding the sublimation
                           temperature is reset to the sublimation
                           temperature.

        temperature : float, optional
            The dust sublimation temperature, in K
        '''

        if mode not in ['no', 'fast', 'slow', 'cap']:
            raise Exception("mode should be one of no/fast/slow/cap")

        if mode != 'no' and temperature is None:
            raise Exception("Need to specify a sublimation temperature")

        self.sublimation_mode = mode
        self.sublimation_energy = self.optical_properties._temperature2specific_energy(temperature)

    def set_sublimation_specific_energy(self, mode, specific_energy=0.):
        '''
        Set the dust sublimation mode and specific energy.

        Parameters
        ----------
        mode : str
            The dust sublimation mode, which can be:
                * 'no'   - no sublimation
                * 'fast' - remove all dust in cells exceeding the
                           sublimation specific energy
                * 'slow' - reduce the dust in cells exceeding the
                           sublimation specific energy
                * 'cap'  - any specific energy exceeding the sublimation
                           specific energy is reset to the sublimation
                           specific energy.

        specific_energy : float, optional
            The dust sublimation specific energy, in cgs
        '''

        if mode not in ['no', 'fast', 'slow', 'cap']:
            raise Exception("mode should be one of no/fast/slow/cap")

        if mode != 'no' and specific_energy is None:
            raise Exception("Need to specify a sublimation specific_energy")

        self.sublimation_mode = mode
        self.sublimation_energy = specific_energy

    def _write_dust_sublimation(self, table_set):
        table_set.add_keyword('sublimation_mode', self.sublimation_mode)
        if self.sublimation_mode in ['slow', 'fast', 'cap']:
            table_set.add_keyword('sublimation_specific_energy', self.sublimation_energy)

    def write(self, filename, compression=True):
        '''
        Write out to a standard dust file, including calculations of the mean
        opacities and optionally thermal emissivities.
        '''

        # Check that emissivities are set (before computing mean opacities)
        if not self.emissivities.set:
            warnings.warn("Computing emissivities assuming LTE")
            self.emissivities.set_lte(self.optical_properties)

        # Compute mean opacities if not already existent
        if not self.mean_opacities.set:
            self.mean_opacities.compute(self.emissivities, self.optical_properties)

        # Create dust table set
        ts = atpy.TableSet()

        # Add standard keywords to header
        ts.add_keyword('version', 1)
        ts.add_keyword('type', 1)
        ts.add_keyword('python_version', hyperion.__version__)
        if self.md5:
            ts.add_keyword('asciimd5', self.md5)

        # Add optical properties and scattering angle tables
        self.optical_properties.to_table_set(ts)

        # Add mean opacities table
        self.mean_opacities.to_table_set(ts)

        # Add emissivities and emissivity variable tables
        self.emissivities.to_table_set(ts)

        # Dust sublimation parameters
        self._write_dust_sublimation(ts)

        # Output dust file
        ts.write(filename, overwrite=True, compression=compression, type='hdf5')

        self.filename = filename

    def read(self, filename):
        '''
        Read in from a standard dust file
        '''

        if type(filename) is str:

            # Check file exists
            if not os.path.exists(filename):
                raise Exception("File not found: %s" % filename)

            self.filename = filename

        # Read in dust table set
        ts = atpy.TableSet(filename, verbose=False, type='hdf5')

        # Check version and type
        if ts.keywords['version'] != 1:
            raise Exception("Version should be 1")
        if ts.keywords['type'] != 1:
            raise Exception("Type should be 1")
        if 'asciimd5' in ts.keywords:
            self.md5 = ts.keywords['asciimd5']
        else:
            self.md5 = None

        # Read in the optical properties
        self.optical_properties.from_table_set(ts)

        # Read in the planck and rosseland mean opacities
        self.mean_opacities.from_table_set(ts)

        # Read in emissivities
        self.emissivities.from_table_set(ts)


class IsotropicSphericalDust(SphericalDust):

    def __init__(self, wav, chi, albedo):

        SphericalDust.__init__(self)

        # Set cos(theta) grid for computing the scattering matrix elements
        self.optical_properties.mu = np.linspace(-1., 1., 2)

        # Set optical properties
        self.optical_properties.nu = c / wav * 1.e4
        self.optical_properties.albedo = albedo
        self.optical_properties.chi = chi

        # Compute scattering matrix elements
        self.optical_properties.initialize_scattering_matrix()

        # Set scattering matrix to isotropic values
        self.optical_properties.P1[:, :] = 1.
        self.optical_properties.P2[:, :] = 0.
        self.optical_properties.P3[:, :] = 1.
        self.optical_properties.P4[:, :] = 0.


class SimpleSphericalDust(SphericalDust):

    def __init__(self, filename):

        SphericalDust.__init__(self)

        # Set cos(theta) grid for computing the scattering matrix elements
        n_mu = 100
        self.optical_properties.mu = np.linspace(-1., 1., n_mu)

        # Read in dust file
        dustfile = np.loadtxt(filename, dtype=[('wav', float), ('c_ext', float), \
                              ('c_sca', float), ('chi', float), ('g', float), \
                              ('p_lin_max', float)], usecols=[0, 1, 2, 3, 4, 5])

        self.optical_properties.nu = c / dustfile['wav'] * 1.e4
        self.optical_properties.albedo = dustfile['c_sca'] / dustfile['c_ext']
        self.optical_properties.chi = dustfile['chi']

        self.md5 = hashlib.md5(open(filename, 'rb').read()).hexdigest()

        # Compute scattering matrix elements
        self.optical_properties.initialize_scattering_matrix()

        for i in range(n_mu):
            self.optical_properties.P1[:, i], \
            self.optical_properties.P2[:, i], \
            self.optical_properties.P3[:, i], \
            self.optical_properties.P4[:, i] = henyey_greenstein(self.optical_properties.mu[i], dustfile['g'], dustfile['p_lin_max'])


class CoatsphSingle(SphericalDust):

    def __init__(self, directory, size, density):
        '''
        Initialize single-component dust.

        Required Arguments:

            *directory*: [ string ]
                Directory containing all the files describing the dust

            *size*: [ float ]
                Grain size, in cm

            *density*: [ float ]
                Dust grain density, in g/cm^3
        '''

        SphericalDust.__init__(self)

        f = open('%s/coatsph_forw.dat' % directory, 'rb')
        version = f.readline()
        n_components = int(f.readline().strip().split()[5])

        # Read in main dust file

        dustfile = np.loadtxt(f, skiprows=3,
                    dtype=[('x', float), ('radius', float), ('wav', float),
                    ('q_ext', float), ('q_sca', float), ('q_back', float),
                    ('g', float)])

        n_wav = len(dustfile)

        self.optical_properties.nu = c / dustfile['wav'] * 1.e4
        self.optical_properties.albedo = dustfile['q_sca'] / dustfile['q_ext']
        self.optical_properties.chi = 0.75 * dustfile['q_ext'] / size / density

        # Read in scattering matrix elements

        for i in range(n_wav):

            filename = '%s/coatsph_scat_%04i_0001.dat' % (directory, i + 1)

            phasefile = np.loadtxt(filename, skiprows=9,
                        dtype=[('theta', float), ('s11', float), ('polariz',
                        float), ('s12', float), ('s33', float), ('s34',
                        float)])

            if i == 0:
                self.optical_properties.mu = np.cos(np.radians(phasefile['theta']))
                self.optical_properties.initialize_scattering_matrix()

            self.optical_properties.P1[i, :] = phasefile['s11']
            self.optical_properties.P2[i, :] = phasefile['s12']
            self.optical_properties.P3[i, :] = phasefile['s33']
            self.optical_properties.P4[i, :] = phasefile['s34']


class CoatsphMultiple(SphericalDust):

    def __init__(self, directory):
        '''
        Initialize multi-component dust.

        Required Arguments:

            *directory*: [ string ]
                Directory containing all the files describing the dust
        '''

        SphericalDust.__init__(self)

        f = open('%s/coatsph_forw.dat' % directory, 'rb')
        version = f.readline()
        n_components = int(f.readline().strip().split()[5])

        # Read in main dust file

        dustfile = np.loadtxt(f, skiprows=7,
                    dtype=[('wav', float), ('c_ext', float), ('c_sca', float),
                    ('chi', float), ('g', float), ('pmax', float),
                    ('thetmax', float)])

        n_wav = len(dustfile)
        self.optical_properties.nu = c / dustfile['wav'] * 1.e4
        self.optical_properties.albedo = dustfile['c_sca'] / dustfile['c_ext']
        self.optical_properties.chi = dustfile['chi']

        # Read in scattering matrix elements

        for i in range(n_wav):

            filename = '%s/coatsph_scat.%04i.dat' % (directory, i + 1)

            phasefile = np.loadtxt(filename, skiprows=7,
                        dtype=[('theta', float), ('s11', float), ('polariz',
                        float), ('s12', float), ('s33', float), ('s34',
                        float)])

            if i == 0:
                self.optical_properties.mu = np.cos(np.radians(phasefile['theta']))
                self.optical_properties.initialize_scattering_matrix()

            self.optical_properties.P1[i, :] = phasefile['s11']
            self.optical_properties.P2[i, :] = phasefile['s12']
            self.optical_properties.P3[i, :] = phasefile['s33']
            self.optical_properties.P4[i, :] = phasefile['s34']


class MieXDust(SphericalDust):

    def __init__(self, model):

        SphericalDust.__init__(self)

        wav = np.loadtxt('%s.alb' % model, usecols=[0])
        self.optical_properties.albedo = np.loadtxt('%s.alb' % model, usecols=[1])
        kappa = np.loadtxt('%s.k_abs' % model, usecols=[1])
        self.optical_properties.chi = kappa / (1 - self.optical_properties.albedo)

        # Check for NaN values
        for quantity in ['chi', 'albedo']:

            values = self.optical_properties.__dict__[quantity]

            if np.any(np.isnan(values)):
                warnings.warn("NaN values found inside MieX %s file - interpolating" % quantity)
                invalid = np.isnan(values)
                values[invalid] = interp1d_fast_loglog(wav[~invalid], values[~invalid], wav[invalid])
                if np.any(np.isnan(values)):
                    raise Exception("Did not manage to fix NaN values in MieX %s" % quantity)

        self.optical_properties.nu = c / wav * 1.e4

        n_wav = len(wav)
        n_mu = (len(open('%s.f11' % model).readlines()) / n_wav) - 1

        self.optical_properties.mu = np.zeros(n_mu)
        self.optical_properties.initialize_scattering_matrix()

        # Read mu
        f11 = open('%s.f11' % model)
        f11.readline()
        f11.readline()
        for i in range(n_mu):
            self.optical_properties.mu[i] = np.cos(np.radians(float(f11.readline().split()[0])))
        f11.close()

        # Read in matrix elements
        f11 = open('%s.f11' % model)
        f12 = open('%s.f12' % model)
        f33 = open('%s.f33' % model)
        f34 = open('%s.f34' % model)

        f11.readline()
        f12.readline()
        f33.readline()
        f34.readline()

        for j in range(n_wav):

            if float(f11.readline()) != wav[j]:
                raise Exception("Incorrect wavelength in f11")
            if float(f12.readline()) != wav[j]:
                raise Exception("Incorrect wavelength in f12")
            if float(f33.readline()) != wav[j]:
                raise Exception("Incorrect wavelength in f33")
            if float(f34.readline()) != wav[j]:
                raise Exception("Incorrect wavelength in f34")

            for i in range(n_mu):

                self.optical_properties.P1[j, i] = float(f11.readline().split()[1])
                self.optical_properties.P2[j, i] = float(f12.readline().split()[1])
                self.optical_properties.P3[j, i] = float(f33.readline().split()[1])
                self.optical_properties.P4[j, i] = float(f34.readline().split()[1])

        for i in range(n_mu):

            for quantity in ['P1', 'P2', 'P3', 'P4']:

                values = self.optical_properties.__dict__[quantity]

                if np.any(np.isnan(values[:, i])):
                    warnings.warn("NaN values found inside MieX %s file - interpolating" % quantity)
                    invalid = np.isnan(values[:, i])
                    values[:, i][invalid] = interp1d_fast_loglog(wav[~invalid], values[:, i][~invalid], wav[invalid])
                    if np.any(np.isnan(values[:, i])):
                        raise Exception("Did not manage to fix NaN values in MieX %s" % quantity)


class BHDust(SphericalDust):

    def __init__(self, model):

        SphericalDust.__init__(self)

        self.optical_properties.nu = c / np.loadtxt('%s.wav' % model) * 1.e4
        self.optical_properties.mu = np.loadtxt('%s.mu' % model)
        self.optical_properties.albedo = np.loadtxt('%s.alb' % model)
        self.optical_properties.chi = np.loadtxt('%s.chi' % model)

        self.optical_properties.initialize_scattering_matrix()

        self.optical_properties.P1 = np.loadtxt('%s.f11' % model)
        self.optical_properties.P2 = np.loadtxt('%s.f12' % model)
        self.optical_properties.P3 = np.loadtxt('%s.f33' % model)
        self.optical_properties.P4 = np.loadtxt('%s.f34' % model)
