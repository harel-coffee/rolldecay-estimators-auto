import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.utils.validation import check_is_fitted
import rolldecayestimators.filters

class CutTransformer(BaseEstimator, TransformerMixin):
    """ Rolldecay transformer that cut time series from roll decay test for estimator.

    Parameters
    ----------
    phi_max : float, default=np.deg2rad(90)
        Start cutting value is below this value [rad]

    phi_min : float, default=0
        Stop cutting value is when below this value [rad]

    Attributes
    ----------
    n_features_ : int
        The number of features of the data passed to :meth:`fit`.
    """
    def __init__(self, phi_max=np.deg2rad(90), phi_min=0):
        self.phi_max = phi_max  # Maximum Roll angle [rad]
        self.phi_min = phi_min  # Minimum Roll angle [rad]
        self.phi_key = 'phi'  # Roll angle [rad]

    def fit(self, X, y=None):
        """Do the cut

        Parameters
        ----------
        X : {array-like, sparse matrix}, shape (n_samples, n_features)
            The training input samples.
        y : None
            There is no need of a target in a transformer, yet the pipeline API
            requires this parameter.

        Returns
        -------
        self : object
            Returns self.
        """
        #X = check_array(X, accept_sparse=True)

        self.n_features_ = X.shape[1]

        phi = X[self.phi_key]
        if (self.phi_max < phi.abs().min()):
            raise ValueError('"phi_max" is too small')

        if (self.phi_min > phi.abs().max()):
            raise ValueError('"phi_min" is too large')

        # Return the transformer
        return self

    def transform(self, X):
        """ A reference implementation of a transform function.

        Parameters
        ----------
        X : {array-like, sparse-matrix}, shape (n_samples, n_features)
            The input samples.

        Returns
        -------
        X_transformed : array, shape (n_samples, n_features)
            The array containing the element-wise square roots of the values
            in ``X``.
        """
        # Check is fit had been called
        check_is_fitted(self, 'n_features_')

        # Input validation
        #X = check_array(X, accept_sparse=True)

        # Check that the input is of the same shape as the one passed
        # during fit.
        #if X.shape[1] != self.n_features_:
        #    raise ValueError('Shape of input is different from what was seen'
        #                     'in `fit`')

        #Remove initial part (by removing first to maximums):
        phi = X[self.phi_key]
        index = phi.abs().idxmax()
        X_cut = X.loc[index:].copy()

        phi = X_cut[self.phi_key]
        phi_max_sign = np.sign(phi.loc[index])
        if phi_max_sign == 1:
            index2 = phi.idxmin()
        else:
            index2 = phi.idxmax()

        X_cut = X_cut.loc[index2:].copy()

        # Remove some large angles at start
        abs_phi = X_cut['phi'].abs()
        mask = abs_phi >= self.phi_max
        df_large = abs_phi.loc[mask]
        if len(df_large) > 0:
            start_index = df_large.index[-1]
            X_cut = X_cut.loc[start_index:]

        # Remove some small angles at end
        abs_phi = X_cut['phi'].abs()
        mask = abs_phi >= self.phi_min
        df_small = abs_phi.loc[mask]
        if len(df_small) > 0:
            stop_index = df_small.index[-1]
            X_cut = X_cut.loc[:stop_index]


        return X_cut

class LowpassFilterDerivatorTransformer(BaseEstimator, TransformerMixin):
    """ Rolldecay transformer that lowpass filters the roll signal for estimator.

    Parameters
    ----------
    phi_max : float, default=np.deg2rad(90)
        Start cutting value is below this value [rad]

    phi_min : float, default=0
        Stop cutting value is when below this value [rad]

    Attributes
    ----------
    n_features_ : int
        The number of features of the data passed to :meth:`fit`.
    """
    def __init__(self, cutoff=0.5, order=5):
        self.cutoff = cutoff
        self.order = order
        self.phi_key = 'phi'  # Roll angle [rad]
        self.phi_filtered_key = 'phi_filtered'  # Filtered roll angle [rad]
        self.phi1d_key = 'phi1d'  # Roll velocity [rad/s]
        self.phi2d_key = 'phi2d'  # Roll acceleration [rad/s2]

    def fit(self, X, y=None):
        """Do the cut

        Parameters
        ----------
        X : {array-like, sparse matrix}, shape (n_samples, n_features)
            The training input samples.
        y : None
            There is no need of a target in a transformer, yet the pipeline API
            requires this parameter.

        Returns
        -------
        self : object
            Returns self.
        """
        #X = check_array(X, accept_sparse=True)

        self.n_features_ = X.shape[1]

        # Return the transformer
        return self

    def transform(self, X):
        """ A reference implementation of a transform function.

        Parameters
        ----------
        X : {array-like, sparse-matrix}, shape (n_samples, n_features)
            The input samples.

        Returns
        -------
        X_transformed : array, shape (n_samples, n_features)
            The array containing the element-wise square roots of the values
            in ``X``.
        """
        # Check is fit had been called
        check_is_fitted(self, 'n_features_')

        # Input validation
        #X = check_array(X, accept_sparse=True)

        # Check that the input is of the same shape as the one passed
        # during fit.
        #if X.shape[1] != self.n_features_:
        #    raise ValueError('Shape of input is different from what was seen'
        #                     'in `fit`')

        # Lowpass filter the signal:
        X_filter = X.copy()

        phi = X[self.phi_key]

        ts = np.mean(np.diff(X_filter.index))
        fs = 1 / ts
        X_filter[self.phi_filtered_key] = rolldecayestimators.filters.lowpass_filter(data=X_filter['phi'],
                                                                                     cutoff=self.cutoff, fs=fs,
                                                                                     order=self.order)

        X_filter = self.add_derivatives(X=X_filter)

        return X_filter

    def add_derivatives(self, X):
        # Add accelerations:
        assert self.phi_key in X
        X = X.copy()
        X[self.phi1d_key] = np.gradient(X[self.phi_filtered_key].values, X.index.values)
        X[self.phi2d_key] = np.gradient(X[self.phi1d_key].values, X.index.values)
        return X

    def score(self, X, y=None, sample_weight=None):
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
        X_filter = self.transform(X)
        y_true = X_filter[self.phi_key]
        y_pred = X_filter[self.phi_filtered_key]

        u = ((y_true - y_pred) ** 2).sum()
        v = ((y_true - y_true.mean()) ** 2).sum()
        return (1 - u/v)

class ScaleFactorTransformer(BaseEstimator, TransformerMixin):
    """ Rolldecay to full scale using scale factor

    Parameters
    ----------
    phi_max : float, default=np.deg2rad(90)
        Start cutting value is below this value [rad]

    phi_min : float, default=0
        Stop cutting value is when below this value [rad]

    Attributes
    ----------
    n_features_ : int
        The number of features of the data passed to :meth:`fit`.
    """
    def __init__(self, scale_factor):
        self.scale_factor = scale_factor
        self.phi1d_key = 'phi1d'  # Roll velocity [rad/s]
        self.phi2d_key = 'phi2d'  # Roll acceleration [rad/s2]

    def fit(self, X, y=None):
        """Do the cut

        Parameters
        ----------
        X : {array-like, sparse matrix}, shape (n_samples, n_features)
            The training input samples.
        y : None
            There is no need of a target in a transformer, yet the pipeline API
            requires this parameter.

        Returns
        -------
        self : object
            Returns self.
        """
        #X = check_array(X, accept_sparse=True)

        self.n_features_ = X.shape[1]

        # Return the transformer
        return self

    def transform(self, X):
        """ A reference implementation of a transform function.

        Parameters
        ----------
        X : {array-like, sparse-matrix}, shape (n_samples, n_features)
            The input samples.

        Returns
        -------
        X_transformed : array, shape (n_samples, n_features)
            The array containing the element-wise square roots of the values
            in ``X``.
        """
        # Check is fit had been called
        check_is_fitted(self, 'n_features_')

        # Input validation
        #X = check_array(X, accept_sparse=True)

        # Check that the input is of the same shape as the one passed
        # during fit.
        #if X.shape[1] != self.n_features_:
        #    raise ValueError('Shape of input is different from what was seen'
        #                     'in `fit`')


        X_scaled = X.copy()
        X_scaled.index*=np.sqrt(self.scale_factor)  # To full scale
        if self.phi1d_key in X:
            X_scaled[self.phi1d_key]/=np.sqrt(self.scale_factor)

        if self.phi2d_key in X:
            X_scaled[self.phi2d_key]/=self.scale_factor


        return X_scaled