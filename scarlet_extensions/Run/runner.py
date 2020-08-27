import numpy as np
import scarlet.display
from scarlet.display import AsinhMapping
from scarlet import Starlet
from scarlet.wavelet import mad_wavelet
from scarlet.observation import LowResObservation
import scipy.stats as scs
from scarlet.initialization import build_initialization_coadd
from functools import partial
from ..initialization.detection import makeCatalog


class Runner:
    """ Class that lets scarlet run on a set of `Data` objects

        parameters
        ----------
        datas: list of Data objects
            the list of Data objects to run scarlet on
        model_psf: 'numpy.ndarray' or `scarlet.PSF`
            the target psf of the model
        ra_dec: `array`
            ra and dec positions of detected sources
    """

    def __init__(self, datas, model_psf, ra_dec = None):

        self._data = datas
        self.run_detection(lvl = 3, wavelet = True)

        if len(self._data) == 1:
            weight = np.ones_like(self._data[0].images) / (self.bg_rms ** 2)[:, None, None]
            observations = [scarlet.Observation(self._data[0].images,
                                                    wcs=self._data[0].wcss,
                                                    psfs=self._data[0].psfs,
                                                    channels=self._data[0].channels,
                                                    weights=weight)]
        else:
            observations = []
            for i,bg in enumerate(self.bg_rms):
                weight = np.ones_like(self._data[i].images) / (bg**2)[:,None,None]
                observations.append(scarlet.Observation(self._data[i].images,
                                                    wcs=self._data[i].wcss,
                                                    psfs=self._data[i].psfs,
                                                    channels=self._data[i].channels,
                                                    weights=weight))
        self.observations = observations
        self.frame = scarlet.Frame.from_observations(self.observations, model_psf, coverage = 'intersection')
        # Convert the HST coordinates to the HSC WCS
        loc = [type(o) is not scarlet.LowResObservation for o in self.observations]
        if ra_dec is None:
            self.ra_dec = self.observations[np.where(loc)[0][0]].frame.get_sky_coord(self.pixels)
        else:
            self.ra_dec = ra_dec

    def run(self, it = 200, e_rel = 1.e-6):
        """ Run scarlet on the Runner object

        parameters
        ----------
        it: `int`
            Maximum number of iterations used to fit the model
        e_rel: `float`
            limit on the convergence: stop condition
        """
        self.blend = scarlet.Blend(self.sources, self.observations)
        self.blend.fit(it, e_rel=e_rel)
        print("scarlet ran for {0} iterations to logL = {1}".format(len(self.blend.loss), -self.blend.loss[-1]))


    def initialize_sources(self):
        '''
        Initialize all sources as Extended sources
        '''
        if len(self.observations) > 1:
            # Building a detection coadd
            coadd, bg_cutoff = build_initialization_coadd(self.observations, filtered_coadd=True)
        else:
            coadd = None
            bg_cutoff = None

        # Source initialisation
        self.sources = [
            scarlet.ExtendedSource(self.frame, sky, self.observations, coadd=coadd, coadd_rms=bg_cutoff)
            for sky in self.ra_dec
        ]


    def run_detection(self, lvl = 3, wavelet = True):
        ''' Runs the detection algorithms on data

        Parameters
        ----------
        lvl: float
            Detection level in units of background noise
        wavelet: Bool
            if set to true, runs sep on a wavelet filtered image

        Returns
        -------
        catalog: dict
            detection catalog that contains at least the position of the detected sources
        bg_rms: float
            background root mean square of the image
        '''
        self.lvl = lvl
        self.wavelet = wavelet
        catalog, self.bg_rms = makeCatalog(self._data, lvl, wavelet)
        # Get the source coordinates from the HST catalog
        self.pixels = np.stack((catalog['y'], catalog['x']), axis=1)

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, data):
        self._data = data
        self.run_detection(self.lvl, self.wavelet)
        for i,obs in enumerate(self.observations):
            obs.images = self._data[i].images
        loc = [type(o) is not scarlet.LowResObservation for o in self.observations]
        self.ra_dec = self.observations[np.where(loc)[0][0]].frame.get_sky_coord(self.pixels)
