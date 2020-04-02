import inspect
from scipy.optimize import least_squares
from scipy.integrate import odeint
from scipy.integrate import solve_ivp
from sklearn.base import BaseEstimator
from sklearn.utils.validation import check_is_fitted
from sklearn.metrics import r2_score

import numpy as np
import pandas as pd

from rolldecayestimators.substitute_dynamic_symbols import lambdify
from rolldecayestimators.symbols import *


class RollDecay(BaseEstimator):

    # Defining the diff equation for this estimator:
    rhs = -phi_dot_dot/(omega0**2) - 2*zeta/omega0*phi_dot
    roll_diff_equation = sp.Eq(lhs=phi, rhs=rhs)
    acceleration = sp.Eq(lhs=phi, rhs=sp.solve(roll_diff_equation, phi.diff().diff())[0])
    functions = (lambdify(acceleration.rhs),)

    def __init__(self, maxfev = 4000, bounds={}, ftol=10**-20, p0={}, fit_method='derivation', omega_regression=True):
        self.is_fitted_ = False

        self.phi_key = 'phi'  # Roll angle [rad]
        self.phi1d_key = 'phi1d'  # Roll velocity [rad/s]
        self.phi2d_key = 'phi2d'  # Roll acceleration [rad/s2]
        self.y_key = self.phi2d_key
        self.boundaries = bounds
        self.p0 = p0
        self.maxfev=maxfev
        self.ftol=ftol
        self.set_fit_method(fit_method=fit_method)
        self.omega_regression = omega_regression
        self.assert_success = True

    def set_fit_method(self,fit_method):
        self.fit_method = fit_method

        if self.fit_method == 'derivation':
            self.y_key=self.phi2d_key
        elif self.fit_method == 'integration':
            self.y_key=self.phi_key
        else:
            raise ValueError('Unknown fit_mehod:%s' % self.fit_method)

    def __repr__(self):
        if self.is_fitted_:
            parameters = ''.join('%s:%0.3f, '%(key,value) for key,value in self.parameters.items())[0:-1]
            return '%s(%s)' % (self.__class__.__name__,parameters)
        else:
            return '%s' % (self.__class__.__name__)

    @property
    def calculate_acceleration(self):
        return self.functions[0]

    @property
    def parameter_names(self):
        signature = inspect.signature(self.calculate_acceleration)

        remove = [self.phi_key, self.phi1d_key]
        if not self.omega_regression:
            remove.append('omega0')

        return list(set(signature.parameters.keys()) - set(remove))

    @staticmethod
    def error(x, self, xs, ys):
        #return np.sum((ys - self.estimator(x, xs))**2)
        return ys-self.estimator(x, xs)


    def estimator(self, x, xs):
        parameters = {key: x for key, x in zip(self.parameter_names, x)}

        if not self.omega_regression:
            parameters['omega0'] = self.omega0

        if self.fit_method=='derivation':
            parameters['phi'] = xs[self.phi_key]
            parameters['phi1d'] = xs[self.phi1d_key]
            return self.estimator_acceleration(parameters=parameters)
        elif self.fit_method=='integration':
            t = xs.index
            phi0=xs.iloc[0][self.phi_key]
            #phi1d0=xs.iloc[0][self.phi1d_key]
            phi1d0 = 0.0

            return self.estimator_integration(t=t, phi0=phi0, phi1d0=phi1d0, parameters=parameters)
        else:
            raise ValueError('Unknown fit_mehod:%s' % self.fit_method)

    def estimator_acceleration(self,parameters):
        acceleration = self.calculate_acceleration(**parameters)
        return acceleration

    def estimator_integration(self, t, phi0, phi1d0, parameters):
        parameters=dict(parameters)

        try:
            df = self._simulate(t=t,phi0=phi0, phi1d0=phi1d0,parameters=parameters )
        except:
            df = pd.DataFrame(index=t)
            df['phi']=np.inf
            df['phi1d']=np.inf

        return df[self.y_key]

    def fit(self, X, y=None, **kwargs):
        self.X = X

        kwargs = {'self': self,
                  'xs': X,
                  'ys': X[self.y_key]}

        self.result = least_squares(fun=self.error, x0=self.initial_guess, kwargs=kwargs, bounds=self.bounds,
                                    ftol=self.ftol, max_nfev=self.maxfev, loss='soft_l1', f_scale=0.1,)
        if self.assert_success:
            assert self.result['success']

        self.parameters = {key: x for key, x in zip(self.parameter_names, self.result.x)}

        if not self.omega_regression:
            self.parameters['omega0'] = self.omega0

        self.is_fitted_ = True

    def simulate(self, t :np.ndarray, phi0 :float, phi1d0 :float,omega0:float, zeta:float)->pd.DataFrame:
        """
        Simulate a roll decay test using the quadratic method.
        :param t: time vector to be simulated [s]
        :param phi0: initial roll angle [rad]
        :param phi1d0: initial roll speed [rad/s]
        :param omega0: roll natural frequency[rad/s]
        :param zeta:linear roll damping [-]
        :return: pandas data frame with time series of 'phi' and 'phi1d'
        """
        parameters={
            'omega0':omega0,
            'zeta':zeta,
        }
        return self._simulate(t=t, phi0=phi0, phi1d0=phi1d0, parameters=parameters)

    def _simulate(self,t,phi0, phi1d0, parameters:dict)->pd.DataFrame:

        states0 = [phi0, phi1d0]

        #states = odeint(self.roll_decay_time_step, y0=states0, t=t, args=(self,parameters))
        #df[self.phi_key] = states[:, 0]
        #df[self.phi1d_key] = states[:, 1]

        t_ = t-t[0]
        t_span = [t_[0], t_[-1]]
        self.simulation_result = solve_ivp(fun=self.roll_decay_time_step, t_span=t_span, y0=states0, t_eval=t_,
                                           args=(parameters,))
        if not self.simulation_result['success']:
            raise ValueError('Simulation failed')

        df = pd.DataFrame(index=t)
        df[self.phi_key] = self.simulation_result.y[0, :]
        df[self.phi1d_key] = self.simulation_result.y[1, :]

        return df

    def roll_decay_time_step(self,t,states,parameters):
        # states:
        # [phi,phi1d]

        phi_old = states[0]
        p_old = states[1]

        phi1d = p_old
        calculate_acceleration = self.calculate_acceleration
        phi2d = calculate_acceleration(phi1d=p_old, phi=phi_old, **parameters)

        d_states_dt = np.array([phi1d, phi2d])

        return d_states_dt

    def predict(self, X)->pd.DataFrame:

        check_is_fitted(self, 'is_fitted_')

        phi0 = X[self.phi_key].iloc[0]
        phi1d0 = X[self.phi1d_key].iloc[0]
        t = np.array(X.index)
        return self._simulate(t=t, phi0=phi0, phi1d0=phi1d0, parameters=self.parameters)


    def score(self, X=None, y=None, sample_weight=None):
        """
        Return the coefficient of determination R^2 of the prediction.

        The coefficient R^2 is defined as (1 - u/v), where u is the residual sum of squares
        ((y_true - y_pred) ** 2).sum() and v is the total sum of squares ((y_true - y_true.mean()) ** 2).sum().
        The best possible score is 1.0 and it can be negative (because the model can be arbitrarily worse).
        A constant model that always predicts the expected value of y, disregarding the input features,
        would get a R^2 score of 0.0.

        Parameters
        ----------
        X : array-like of shape (n_samples, n_features)
            Test samples. For some estimators this may be a precomputed kernel matrix or a list of generic
            objects instead, shape = (n_samples, n_samples_fitted), where n_samples_fitted is the number of samples
            used in the fitting for the estimator.

        y : Dummy not used

        sample_weight : Dummy

        Returns
        -------
        score : float
            R^2 of self.predict(X) wrt. y.

        """

        y_true, y_pred = self.true_and_prediction(X=X)

        return r2_score(y_true=y_true, y_pred=y_pred)

    def true_and_prediction(self, X=None):

        if X is None:
            X=self.X

        y_true = X[self.phi_key]
        df_sim = self.predict(X)
        y_pred = df_sim[self.phi_key]
        return y_true, y_pred

    @property
    def bounds(self):

        minimums = []
        maximums = []

        for key in self.parameter_names:

            boundaries = self.boundaries.get(key,(-np.inf, np.inf))
            assert len(boundaries) == 2
            minimums.append(boundaries[0])
            maximums.append(boundaries[1])

        return [tuple(minimums), tuple(maximums)]

    @property
    def initial_guess(self):
        p0 = []
        for key in self.parameter_names:
            p0.append(self.p0.get(key,0.5))

        return p0

    @property
    def omega0(self):
        """
        Mean natural frequency
        Returns
        -------

        """

        frequencies, dft = self.fft(self.X['phi'])
        omega0 = self.fft_omega0(frequencies=frequencies, dft=dft)
        return omega0

    @staticmethod
    def fft_omega0(frequencies, dft):

        index = np.argmax(dft)
        natural_frequency = frequencies[index]
        omega0 = 2 * np.pi * natural_frequency
        return omega0

    @staticmethod
    def fft(series):
        """
        FFT of a series
        Parameters
        ----------
        series

        Returns
        -------

        """

        signal = series.values
        time = series.index

        number_of_samples = len(signal)  # Compute number of samples
        nondimensional_frequencies = np.fft.rfftfreq(number_of_samples)

        dt = np.mean(np.diff(time))  # Time step size in [s]
        fs = 1 / dt  # Sampling frequency in [Hz]

        frequencies = nondimensional_frequencies * fs
        dft = np.abs(np.fft.rfft(signal))

        return frequencies, dft