"""Code for SAX-VSM."""

import numpy as np
from sklearn.utils.validation import check_X_y, check_is_fitted
from sklearn.utils.multiclass import check_classification_targets
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import LabelEncoder
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from ..bag_of_words import BagOfWords
from ..approximation import SymbolicAggregateApproximation


class SAXVSM(BaseEstimator, ClassifierMixin):
    """Classifier based on SAX-VSM representation and tf-idf statistics.

    Time series are first transformed into bag of words using Symbolic
    Aggregate approXimation (SAX) algorithm followed by a bag-of-words
    model. Then the classes are transformed into a Vector Space Model
    (VSM) using term frequencies (tf) and inverse document frequencies
    (idf).

    Parameters
    ----------
    n_bins : int (default = 4)
        The number of bins to produce. The intervals for the bins are
        determined by the minimum and maximum of the input data. It must
        be between 2 and 26.

    strategy : 'uniform', 'quantile' or 'normal' (default = 'quantile')
        Strategy used to define the widths of the bins:

        - 'uniform': All bins in each sample have identical widths
        - 'quantile': All bins in each sample have the same number of points
        - 'normal': Bin edges are quantiles from a standard normal distribution

    alphabet : None or array-like, shape = (n_bins,)
        Alphabet to use. If None, the first `n_bins` letters of the Latin
        alphabet are used.

    window_size : int or float (default = 4)
        Size of the sliding window (i.e. the size of each word). If float, it
        represents the percentage of the size of each time series and must be
        between 0 and 1. The window size will be computed as
        ``ceil(window_size * n_timestamps)``.

    window_step : int or float (default = 1)
        Step of the sliding window. If float, it represents the percentage of
        the size of each time series and must be between 0 and 1. The window
        step will be computed as ``ceil(window_step * n_timestamps)``.

    numerosity_reduction : bool (default = True)
        If True, delete sample-wise all but one occurence of back to back
        identical occurences of the same words.

    use_idf : bool (default = True)
        Enable inverse-document-frequency reweighting.

    smooth_idf : bool (default = False)
        Smooth idf weights by adding one to document frequencies, as if an
        extra document was seen containing every term in the collection
        exactly once. Prevents zero divisions.

    sublinear_tf : bool (default = True)
        Apply sublinear tf scaling, i.e. replace tf with 1 + log(tf).

    Attributes
    ----------
    vocabulary_ : dict
        A mapping of feature indices to terms.

    tfidf_ : array, shape = (n_classes, n_words)
        Term-document matrix.

    idf_ : array, shape = (n_features,) , or None
        The learned idf vector (global term weights) when ``use_idf=True``,
        None otherwise.

    References
    ----------
    .. [1] P. Senin, and S. Malinchik, "SAX-VSM: Interpretable Time Series
           Classification Using SAX and Vector Space Model". International
           Conference on Data Mining, 13, 1175-1180 (2013).

    """

    def __init__(self, n_bins=4, strategy='quantile', alphabet=None,
                 window_size=4, window_step=1, numerosity_reduction=True,
                 use_idf=True, smooth_idf=False, sublinear_tf=True):
        self.n_bins = n_bins
        self.strategy = strategy
        self.alphabet = alphabet
        self.window_size = window_size
        self.window_step = window_step
        self.numerosity_reduction = numerosity_reduction
        self.use_idf = use_idf
        self.smooth_idf = smooth_idf
        self.sublinear_tf = sublinear_tf

    def fit(self, X, y):
        """Fit the model according to the given training data.

        Parameters
        ----------
        X : array-like, shape = (n_samples, n_timestamps)
            Training vector.

        y : array-like, shape = (n_samples,)
            Class labels for each data sample.

        Returns
        -------
        self : object

        """
        X, y = check_X_y(X, y)
        self._check_params()
        check_classification_targets(y)
        le = LabelEncoder()
        y_ind = le.fit_transform(y)
        self.classes_ = le.classes_
        n_classes = self.classes_.size

        sax = SymbolicAggregateApproximation(
            self.n_bins, self.strategy, self.alphabet)
        X_sax = sax.fit_transform(X)
        bow = BagOfWords(self.window_size, self.window_step,
                         self.numerosity_reduction)
        X_bow = bow.fit_transform(X_sax)

        X_class = [' '.join(X_bow[y_ind == classe])
                   for classe in range(n_classes)]

        tfidf = TfidfVectorizer(
            norm=None, use_idf=self.use_idf, smooth_idf=self.smooth_idf,
            sublinear_tf=self.sublinear_tf
        )
        self.tfidf_ = tfidf.fit_transform(X_class).toarray()
        self.vocabulary_ = {value: key for key, value in
                            tfidf.vocabulary_.items()}
        if self.use_idf:
            self.idf_ = tfidf.idf_
        else:
            self.idf_ = None
        self._tfidf = tfidf
        self._sax = sax
        self._bow = bow
        return self

    def decision_function(self, X):
        """Evaluate the cosine similarity between document-term matrix and X.

        Parameters
        ----------
        X : array-like, shape (n_samples, n_timestamps)
            Test samples.

        Returns
        -------
        X : array-like, shape (n_samples, n_classes)
            osine similarity between the document-term matrix and X.

        """
        check_is_fitted(self, ['vocabulary_', 'tfidf_', 'idf_',
                               '_tfidf', 'classes_'])
        X_sax = self._sax.transform(X)
        X_bow = self._bow.transform(X_sax)
        vectorizer = CountVectorizer(vocabulary=self._tfidf.vocabulary_)
        X_transformed = vectorizer.transform(X_bow).toarray()
        return cosine_similarity(X_transformed, self.tfidf_)

    def predict(self, X):
        """Predict the class labels for the provided data.

        Parameters
        ----------
        X : array-like, shape = (n_samples, n_timestamps)
            Test samples.

        Returns
        -------
        y_pred : array-like, shape = (n_samples,)
            Class labels for each data sample.

        """
        return self.classes_[self.decision_function(X).argmax(axis=1)]

    def _check_params(self):
        if not isinstance(self.n_bins, (int, np.integer)):
            raise TypeError("'n_bins' must be an integer.")
        if not 2 <= self.n_bins <= 26:
            raise ValueError("'n_bins' must be between 2 and 26.")
