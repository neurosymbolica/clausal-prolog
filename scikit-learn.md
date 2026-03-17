# scikit-learn Prolog API Specification

## Overview

This document defines a Prolog-style API for scikit-learn, the Python machine learning
library. The goal is a **small, orthogonal set of predicates** that cover the full
scikit-learn surface area — roughly 40 predicates mapping to a library of ~300 classes
and ~1,300 functions.

The API is designed around a single central insight: **scikit-learn has one design
pattern used everywhere**. Every algorithm — whether a classifier, regressor,
clusterer, or data transformer — is an *Estimator*: an object constructed with
hyperparameters, fitted to data, and then used to make predictions or
transformations. This uniformity means we can build a small relational vocabulary
that works the same way for every algorithm in the library.

### Naming Conventions

- Predicate names are **TitleCase**: `Fit`, `Predict`, `MakeEst`
- Variables are **ALLCAPS**: `X`, `Y`, `FITTED`, `PARAMS`
- Keyword arguments use Python-style `keyword=value` syntax in argument position
- The arity suffix is omitted in prose; context determines which variant is meant

---

## The Term Language

Before any predicates, we establish the **term language** — the data structures
that flow between predicates. Understanding these terms is the key to understanding
the whole API.

### `Est(ALGORITHM, PARAMS)`

An **unfitted estimator**. Represents a machine learning algorithm with its
hyperparameter configuration, but no learned state. `ALGORITHM` is an atom
naming the algorithm (e.g. `random_forest`, `svm`, `pca`). `PARAMS` is a list
of `key=value` pairs.

In scikit-learn terms this corresponds to constructing an estimator object:
```python
# Python equivalent
RandomForestClassifier(n_estimators=100, max_depth=5)
```

The `Est` term carries **no learned state** — it is a pure description of what
you want to train.

**Examples:**
```
Est(random_forest, [n_estimators=100, max_depth=5])
Est(svm, [kernel=rbf, C=1.0])
Est(standard_scaler, [])
Est(pca, [n_components=10])
```

---

### `Fitted(EST, HANDLE)`

A **fitted estimator**. Wraps an `Est` term together with an opaque `HANDLE`
that refers to a live Python-side scikit-learn object holding all learned
parameters (coefficients, cluster centres, scaling factors, etc.).

`HANDLE` is opaque — you never inspect or construct it directly. All access to
learned state goes through the `Learned` predicate. From Prolog's perspective,
`Fitted` is an **immutable term**: fitting produces a new `Fitted` term rather
than mutating anything visible at the Prolog level.

In scikit-learn terms, `HANDLE` points to the Python object *after* `.fit()` has
been called on it.

**Example:**
```
Fitted(Est(random_forest, [n_estimators=100]), <handle:42>)
```

---

### `Dataset(X, Y)`

A supervised dataset. `X` is the feature matrix (rows = samples, columns =
features) and `Y` is the target vector or matrix. For unsupervised problems,
pass `Y=nil`.

In scikit-learn, `X` is always a 2D array of shape `(n_samples, n_features)` and
`Y` is a 1D array of shape `(n_samples,)` for single-output problems.

**Examples:**
```
Dataset(X, Y)          % supervised
Dataset(X, nil)        % unsupervised (clustering, PCA, etc.)
```

---

### `Split(TRAIN, TEST)`

A train/test partition of a dataset. Both `TRAIN` and `TEST` are `Dataset` terms.

```
Split(Dataset(Xtrain, Ytrain), Dataset(Xtest, Ytest))
```

---

### `CV` terms

Cross-validation strategies, used as arguments to `CrossValScore` and
`GridSearch`:

```
kfold(K)                    % standard K-fold
stratified_kfold(K)         % preserves class proportions per fold
shuffle_split(N, TEST_SIZE) % N random train/test splits
loo                         % leave-one-out
group_kfold(K)              % K-fold with group labels
```

---

## Section 1: Estimator Construction & Introspection

These predicates describe the *space* of available algorithms and their
hyperparameters. They are **pure facts and relations** — no scikit-learn calls
are made. They exist so that other predicates (search, validation) can reason
over the space of possible models.

---

### `Algorithm(ALGORITHM, ROLE)`

**scikit-learn reference:** The full set of estimator classes across
`sklearn.linear_model`, `sklearn.ensemble`, `sklearn.svm`,
`sklearn.preprocessing`, `sklearn.decomposition`, etc.

Enumerates all known algorithms. `ROLE` is one of `classifier`, `regressor`,
`transformer`, or `clusterer`. Use backtracking to enumerate all algorithms of
a given role.

```
Algorithm(random_forest,        classifier).
Algorithm(gradient_boosting,    classifier).
Algorithm(svm,                  classifier).
Algorithm(svm,                  regressor).
Algorithm(logistic_regression,  classifier).
Algorithm(linear_regression,    regressor).
Algorithm(ridge,                regressor).
Algorithm(lasso,                regressor).
Algorithm(elastic_net,          regressor).
Algorithm(knn,                  classifier).
Algorithm(knn,                  regressor).
Algorithm(naive_bayes,          classifier).
Algorithm(decision_tree,        classifier).
Algorithm(decision_tree,        regressor).
Algorithm(adaboost,             classifier).
Algorithm(extra_trees,          classifier).
Algorithm(pca,                  transformer).
Algorithm(standard_scaler,      transformer).
Algorithm(min_max_scaler,       transformer).
Algorithm(one_hot_encoder,      transformer).
Algorithm(label_encoder,        transformer).
Algorithm(tfidf_vectorizer,     transformer).
Algorithm(truncated_svd,        transformer).
Algorithm(nmf,                  transformer).
Algorithm(kmeans,               clusterer).
Algorithm(dbscan,               clusterer).
Algorithm(agglomerative,        clusterer).
Algorithm(pipeline,             classifier).  % role depends on final step
Algorithm(pipeline,             regressor).
Algorithm(pipeline,             transformer).
```

**Query patterns:**
```
% All classifiers
Algorithm(ALG, classifier)

% Everything that can be a transformer
Algorithm(ALG, transformer)
```

---

### `DefaultParams(ALGORITHM, PARAMS)`

**scikit-learn reference:** The default argument values defined in each
estimator class's `__init__` signature.

Returns the default hyperparameter list for an algorithm. `PARAMS` is a list
of `key=value` pairs. Useful for constructing estimators without specifying
every parameter.

```
DefaultParams(random_forest, [n_estimators=100, max_depth=nil,
                               min_samples_split=2, max_features=sqrt])

DefaultParams(svm, [C=1.0, kernel=rbf, degree=3, gamma=scale])

DefaultParams(pca, [n_components=nil, whiten=false, svd_solver=auto])
```

---

### `ParamKey(ALGORITHM, KEY, DOMAIN)`

**scikit-learn reference:** The type annotations and valid value sets in each
estimator's docstring and parameter validation.

Describes a single valid hyperparameter. `DOMAIN` constrains what values are
legal:

```
Domain = positive_integer
Domain = positive_float
Domain = boolean
Domain = [atom1, atom2, ...]    % enumeration of valid atoms
Domain = range(LOW, HIGH)       % numeric range
Domain = any                    % unconstrained
```

**Examples:**
```
ParamKey(random_forest, n_estimators,   positive_integer).
ParamKey(random_forest, max_depth,      positive_integer).
ParamKey(svm,           kernel,         [linear, rbf, poly, sigmoid]).
ParamKey(svm,           C,              positive_float).
ParamKey(pca,           svd_solver,     [auto, full, arpack, randomized]).
```

Used by `GridSearch` to validate parameter grids and by `RandomSearch` to
sample from parameter distributions.

---

### `MakeEst(ALGORITHM, PARAMS, EST)`

**scikit-learn reference:** Calling `ClassName(**params)` — the constructor
of any estimator class.

The main estimator constructor. Unifies `EST` with a fully-specified `Est` term,
filling any parameters absent from `PARAMS` with their defaults from
`DefaultParams`. If `PARAMS=[]`, the result is a fully default estimator.

This is the primary entry point for creating estimators. The partial-specification
pattern means you only write the parameters you care about.

```
MakeEst(random_forest, [n_estimators=200], EST)
% EST = Est(random_forest, [n_estimators=200, max_depth=nil,
%                           min_samples_split=2, max_features=sqrt])

MakeEst(svm, [], EST)
% EST = Est(svm, [C=1.0, kernel=rbf, degree=3, gamma=scale])
```

---

### `Param(ESTIMATOR, KEY, VALUE)`

**scikit-learn reference:** `estimator.get_params()` — retrieves the
hyperparameter dict of any estimator, fitted or not.

Reads a single hyperparameter from either an unfitted `Est` or a `Fitted` term.
Works on pipelines too, using double-underscore-style step addressing.

```
Param(Est(svm, [C=2.0, kernel=rbf]), kernel, VALUE)
% VALUE = rbf

Param(Fitted(Est(random_forest,[n_estimators=100]),_), n_estimators, VALUE)
% VALUE = 100
```

Because this is a relation, you can also use it to enumerate all parameters
of an estimator by leaving `KEY` and `VALUE` unbound and backtracking.

---

## Section 2: Fitting

Fitting is the **single stateful transition** in the API. An unfitted `Est` term
plus a `Dataset` produces a `Fitted` term. From Prolog's perspective this is
a pure function — no mutation is visible.

---

### `Fit(EST, DATASET, FITTED)`

**scikit-learn reference:** `estimator.fit(X, y)` — trains the model on data.

The core fitting predicate. `EST` is an `Est` term (or a bare `Est(ALG, PARAMS)`
structure). `DATASET` is a `Dataset(X, Y)` term. `FITTED` is unified with a
`Fitted(EST, HANDLE)` term where `HANDLE` is the opaque reference to the trained
Python object.

For unsupervised algorithms (transformers, clusterers), pass `Dataset(X, nil)`.

```
Fit(Est(random_forest, [n_estimators=100]),
    Dataset(X, Y),
    FITTED)
% FITTED = Fitted(Est(random_forest,[n_estimators=100]), <handle>)

Fit(Est(standard_scaler, []),
    Dataset(X, nil),
    FITTED)
```

**Important:** For pipelines, `Fit` calls `.fit()` on the whole pipeline,
which internally fits each step in sequence. No special handling is needed —
a pipeline `Est` term is just an estimator.

---

### `Fit(EST, X, Y, FITTED)`

Convenience variant accepting raw `X` and `Y` directly, without wrapping in a
`Dataset` term. Equivalent to `Fit(EST, Dataset(X,Y), FITTED)`.

---

## Section 3: Prediction and Transformation

Once you have a `Fitted` term, these predicates apply the learned model to
new data. They all take a `Fitted` term as their first argument.

---

### `Predict(FITTED, X, PREDICTIONS)`

**scikit-learn reference:** `estimator.predict(X)` — applies a fitted predictor
to new samples.

Used for classifiers and regressors. `X` is a feature matrix of new samples.
`PREDICTIONS` is unified with the predicted labels (classifiers) or values
(regressors).

```
Predict(FITTED, Xnew, PREDICTIONS)
```

For classifiers, `PREDICTIONS` is a vector of class labels. For regressors,
a vector of continuous values.

---

### `Transform(FITTED, X, TRANSFORMED)`

**scikit-learn reference:** `estimator.transform(X)` — applies a fitted
transformer to new data.

Used for transformers (scalers, encoders, dimensionality reduction). Returns
the transformed feature matrix. The number of samples is preserved; the number
of features may change (e.g. PCA reduces dimensions, OneHotEncoder expands them).

```
Transform(Fitted(Est(standard_scaler,[]),_), Xnew, XSCALED)

Transform(Fitted(Est(pca,[n_components=10]),_), Xnew, XREDUCED)
```

---

### `FitTransform(EST, DATASET, TRANSFORMED, FITTED)`

**scikit-learn reference:** `estimator.fit_transform(X, y)` — fits and
transforms in a single call, which is often more efficient than calling
`fit` then `transform` separately (particularly for decomposition methods).

Returns both the transformed data and the fitted estimator. Most useful
when building preprocessing pipelines step by step, or when you want the
transformed training data alongside a fitted transformer for later use on
test data.

```
FitTransform(Est(pca, [n_components=50]),
             Dataset(Xtrain, nil),
             XTRAIN_REDUCED,
             FITTED_PCA)
% Then later:
Transform(FITTED_PCA, Xtest, XTEST_REDUCED)
```

---

### `PredictProba(FITTED, X, PROBABILITIES)`

**scikit-learn reference:** `estimator.predict_proba(X)` — returns class
membership probabilities rather than hard predictions.

Available on probabilistic classifiers (logistic regression, random forest,
gradient boosting, naive Bayes, etc. — but not plain SVM). `PROBABILITIES`
is a matrix of shape `(n_samples, n_classes)` where each row sums to 1.

```
PredictProba(FITTED, Xnew, PROBA)
% PROBA[i][j] = P(sample i belongs to class j)
```

Required input for metrics like `roc_auc` and `log_loss`.

---

### `DecisionFunction(FITTED, X, SCORES)`

**scikit-learn reference:** `estimator.decision_function(X)` — returns raw
decision scores rather than probabilities or labels.

Available on SVMs and linear classifiers. For binary classification, returns
a 1D vector of signed distances to the decision boundary. For multiclass,
returns a matrix. Useful for ranking rather than hard classification.

```
DecisionFunction(FITTED, Xnew, SCORES)
```

---

## Section 4: Querying Fitted State

A fitted scikit-learn estimator stores all its learned parameters as attributes
on the Python object (by convention, attributes whose names end in `_`). This
section provides access to that learned state.

---

### `Learned(FITTED, ATTRIBUTE, VALUE)`

**scikit-learn reference:** Attribute access on fitted estimators, e.g.
`est.coef_`, `est.feature_importances_`, `est.cluster_centers_`,
`est.explained_variance_ratio_`, `est.n_features_in_`, `est.classes_`.

The **single gateway to all learned state**. `ATTRIBUTE` is an atom naming
the attribute (without the trailing underscore used in Python).
`VALUE` is unified with the attribute's value.

This single predicate replaces what would otherwise be dozens of
attribute-specific accessors. The set of valid attributes depends on the
algorithm:

| Algorithm family | Common attributes |
|---|---|
| Linear models | `coef`, `intercept`, `n_iter` |
| Tree ensembles | `feature_importances`, `n_estimators`, `estimators` |
| SVM | `support_vectors`, `dual_coef`, `intercept` |
| PCA | `components`, `explained_variance_ratio`, `singular_values` |
| KMeans | `cluster_centers`, `labels`, `inertia` |
| All | `n_features_in`, `classes` (classifiers only) |

```
Learned(FITTED, coef,                 COEF)
Learned(FITTED, feature_importances,  FI)
Learned(FITTED, cluster_centers,      CENTERS)
Learned(FITTED, explained_variance_ratio, EVR)
Learned(FITTED, n_features_in,        N)
Learned(FITTED, classes,              CLASSES)
```

Use backtracking to enumerate all available learned attributes of a fitted
estimator by leaving `ATTRIBUTE` unbound.

---

## Section 5: Scoring and Evaluation

---

### `Score(FITTED, DATASET, SCORE)`

**scikit-learn reference:** `estimator.score(X, y)` — evaluates the fitted
estimator on a labelled dataset using its default metric.

The default metric is algorithm-dependent: classifiers use accuracy, regressors
use R², clusterers use silhouette score. Returns a single scalar `SCORE`.

```
Score(FITTED, Dataset(Xtest, Ytest), SCORE)
```

---

### `Score(FITTED, DATASET, METRIC, SCORE)`

As above but with an explicit `METRIC` atom. Use this when you want a specific
metric rather than the estimator's default. `METRIC` is the same atom vocabulary
as used in `Metric/4` (see Section 10).

```
Score(FITTED, Dataset(Xtest, Ytest), f1_weighted, SCORE)
```

---

### `CrossValScore(EST, DATASET, CV, SCORES)`

**scikit-learn reference:** `sklearn.model_selection.cross_val_score(estimator, X, y, cv=k)`

Performs cross-validation using strategy `CV` and returns `SCORES` as a list
of per-fold scores using the estimator's default metric. The estimator is
re-fitted from scratch on each fold's training data — the input `EST` is
never mutated.

```
CrossValScore(Est(random_forest, [n_estimators=100]),
              Dataset(X, Y),
              kfold(5),
              SCORES)
% SCORES = [0.91, 0.89, 0.93, 0.90, 0.92]
```

---

### `CrossValScore(EST, DATASET, CV, METRIC, SCORES)`

As above with an explicit `METRIC`.

```
CrossValScore(Est(svm,[kernel=rbf]),
              Dataset(X, Y),
              stratified_kfold(10),
              roc_auc,
              SCORES)
```

---

### `CrossValidate(EST, DATASET, CV, METRICS, RESULTS)`

**scikit-learn reference:** `sklearn.model_selection.cross_validate(...)` —
like `cross_val_score` but computes multiple metrics simultaneously and also
returns fit/score times.

`METRICS` is a list of metric atoms. `RESULTS` is a list of
`metric=scores_list` pairs, one entry per metric.

```
CrossValidate(Est(gradient_boosting,[]),
              Dataset(X, Y),
              kfold(5),
              [accuracy, f1_weighted, roc_auc],
              RESULTS)
% RESULTS = [accuracy=[0.91,...], f1_weighted=[0.90,...], roc_auc=[0.95,...]]
```

More efficient than calling `CrossValScore` multiple times because all metrics
are computed in a single pass over the folds.

---

## Section 6: Data Splitting

These predicates partition datasets for training and evaluation. The key Prolog
idiom here is **backtracking**: multi-fold splitters generate one split per
solution rather than returning a list. Use `FindAll` if you need all splits at once.

---

### `SplitData(DATASET, TEST_SIZE, SPLIT)`

**scikit-learn reference:** `sklearn.model_selection.train_test_split(X, y, test_size=...)`

Splits a dataset into a single train/test `Split` term. `TEST_SIZE` is a float
between 0 and 1 representing the fraction of samples held out for testing.

```
SplitData(Dataset(X, Y), 0.2, SPLIT)
% SPLIT = Split(Dataset(Xtrain, Ytrain), Dataset(Xtest, Ytest))
```

---

### `SplitData(DATASET, TEST_SIZE, SEED, SPLIT)`

As above with a random `SEED` integer for reproducibility.

```
SplitData(Dataset(X, Y), 0.2, seed=42, SPLIT)
```

---

### `KFoldSplit(DATASET, K, SPLIT)`

**scikit-learn reference:** `sklearn.model_selection.KFold(n_splits=K).split(X, y)`

Generates train/test splits by backtracking. Each solution unifies `SPLIT` with
one fold's `Split(Train, Test)` term. There are exactly `K` solutions.

```
KFoldSplit(Dataset(X, Y), 5, SPLIT)
% On first call:  SPLIT = Split(Dataset(Xtrain1,Ytrain1), Dataset(Xtest1,Ytest1))
% On backtrack:   SPLIT = Split(Dataset(Xtrain2,Ytrain2), Dataset(Xtest2,Ytest2))
% ... 5 solutions total

% Get all splits at once:
FindAll(SPLIT, KFoldSplit(Dataset(X,Y), 5, SPLIT), SPLITS)
```

---

### `StratifiedSplit(DATASET, K, SPLIT)`

**scikit-learn reference:** `sklearn.model_selection.StratifiedKFold(n_splits=K).split(X, y)`

Like `KFoldSplit` but preserves the proportion of each class in both train and
test folds. Essential for imbalanced classification problems. Generates `K`
solutions by backtracking.

```
StratifiedSplit(Dataset(X, Y), 5, SPLIT)
```

---

## Section 7: Pipelines and Composition

A **pipeline** chains transformers and a final estimator into a single object
that behaves exactly like any other estimator. This is the primary composition
mechanism in scikit-learn.

The key design point: **a pipeline is just an `Est` term with `algorithm=pipeline`**.
It therefore works with `Fit`, `Predict`, `Transform`, `CrossValScore`, `GridSearch`,
and every other predicate in this API without any special cases. You get
composition entirely for free.

---

### `Pipeline(STEPS, EST)`

**scikit-learn reference:** `sklearn.pipeline.Pipeline(steps=[...])`

Constructs a pipeline `Est` term from a list of `name-estimator` pairs. The
final step may be a predictor or transformer; all preceding steps must be
transformers. `EST` is unified with `Est(pipeline, [steps=STEPS])`.

```
Pipeline([scaler-Est(standard_scaler,[]),
          reducer-Est(pca,[n_components=50]),
          clf-Est(svm,[C=1.0,kernel=rbf])],
         EST)

% EST can then be used like any estimator:
Fit(EST, Dataset(Xtrain, Ytrain), FITTED_PIPELINE)
Predict(FITTED_PIPELINE, Xtest, PREDICTIONS)
```

During `Fit`, scikit-learn calls `.fit_transform()` on each intermediate step
and `.fit()` on the final step. During `Predict`, it calls `.transform()` on
each intermediate step and `.predict()` on the final step. This is all handled
transparently.

---

### `PipelineStep(FITTED_PIPELINE, NAME, STEP_FITTED)`

**scikit-learn reference:** `pipeline.named_steps['name']` — access a
specific fitted component of a pipeline by its step name.

Returns the `Fitted` term for a named step within a fitted pipeline.
Useful for inspecting learned state of individual pipeline components, e.g.
to see the PCA components or the scaler's learned mean and variance.

```
PipelineStep(FITTED_PIPELINE, pca, FITTED_PCA)
Learned(FITTED_PCA, explained_variance_ratio, EVR)

PipelineStep(FITTED_PIPELINE, scaler, FITTED_SCALER)
Learned(FITTED_SCALER, mean, MEANS)
```

---

## Section 8: Hyperparameter Search

Search predicates treat an estimator as a **template** and search over
variations of its hyperparameters, evaluating each variant by cross-validation.
The output is itself a `Fitted` term (the best model found), so all downstream
predicates work on it unchanged.

---

### `GridSearch(EST, PARAM_GRID, DATASET, CV, BEST_FITTED)`

**scikit-learn reference:** `sklearn.model_selection.GridSearchCV(estimator, param_grid, cv=...)`

Exhaustive search over a hyperparameter grid. `PARAM_GRID` is a list of
`key=[v1,v2,v3]` pairs specifying the values to try for each parameter.
All combinations are evaluated. `CV` is a cross-validation strategy term.
`BEST_FITTED` is the estimator re-fitted on the full dataset with the best
parameter combination found.

```
GridSearch(Est(svm, []),
           [C=[0.1, 1.0, 10.0], kernel=[rbf, linear]],
           Dataset(X, Y),
           kfold(5),
           BEST_FITTED)
% Tries 6 combinations, each evaluated with 5-fold CV
```

Works on pipelines too — prefix parameter names with `stepname__` to address
parameters inside pipeline steps:

```
GridSearch(Est(pipeline, [steps=[scaler-Est(standard_scaler,[]),
                                  clf-Est(svm,[])]]),
           [clf__C=[0.1,1.0,10.0], clf__kernel=[rbf,linear]],
           Dataset(X, Y),
           kfold(5),
           BEST_FITTED)
```

---

### `GridSearch(EST, PARAM_GRID, DATASET, CV, METRIC, BEST_FITTED)`

As above with an explicit scoring `METRIC`.

---

### `RandomSearch(EST, PARAM_DISTS, DATASET, CV, N_ITER, BEST_FITTED)`

**scikit-learn reference:** `sklearn.model_selection.RandomSearchCV(estimator, param_distributions, n_iter=..., cv=...)`

Samples `N_ITER` random parameter combinations from `PARAM_DISTS` rather than
trying all combinations. Much more efficient than `GridSearch` when the parameter
space is large. `PARAM_DISTS` uses the same `key=[v1,v2,...]` format as
`PARAM_GRID` (discrete lists) or `key=dist(DIST_TERM)` for continuous
distributions.

```
RandomSearch(Est(random_forest, []),
             [n_estimators=[50,100,200,500],
              max_depth=[3,5,10,nil],
              max_features=[sqrt, log2, 0.5]],
             Dataset(X, Y),
             kfold(5),
             50,
             BEST_FITTED)
```

---

### `SearchResults(FITTED_SEARCH, RESULTS)`

**scikit-learn reference:** `grid_search.cv_results_` — the full results table
from a search.

Returns all evaluated configurations and their scores. `RESULTS` is a list of
terms of the form `result(PARAMS, MEAN_SCORE, STD_SCORE)`.

```
SearchResults(FITTED_SEARCH, RESULTS)
% RESULTS = [result([C=0.1,kernel=rbf], 0.87, 0.02),
%            result([C=1.0,kernel=rbf], 0.91, 0.01), ...]
```

---

### `BestParams(FITTED_SEARCH, PARAMS)`

**scikit-learn reference:** `grid_search.best_params_`

Returns the hyperparameter combination that achieved the best cross-validation
score during the search.

```
BestParams(FITTED_SEARCH, PARAMS)
% PARAMS = [C=1.0, kernel=rbf]
```

---

### `BestScore(FITTED_SEARCH, SCORE)`

**scikit-learn reference:** `grid_search.best_score_`

Returns the mean cross-validation score of the best parameter combination.

```
BestScore(FITTED_SEARCH, SCORE)
% SCORE = 0.912
```

---

## Section 9: Pure Preprocessing Functions

These transforms do **not** require fitting — they are stateless functions that
transform data directly. They do not produce `Fitted` terms. Algorithms that
*do* require fitting (scalers, encoders, etc.) are ordinary `Est` terms handled
by the standard `Fit`/`Transform` predicates above.

---

### `EncodeLabels(LABELS, ENCODED, MAPPING)`

**scikit-learn reference:** `sklearn.preprocessing.LabelEncoder` used as a
pure function, or `numpy`-level label encoding for categorical targets.

Converts a list of symbolic class labels to integer indices. `MAPPING` is a
list of `label=index` pairs. Invertible by passing the `MAPPING` back.

```
EncodeLabels([cat, dog, cat, bird, dog], ENCODED, MAPPING)
% ENCODED = [1, 2, 1, 0, 2]
% MAPPING = [bird=0, cat=1, dog=2]
```

---

### `Binarize(X, THRESHOLD, BINARIZED)`

**scikit-learn reference:** `sklearn.preprocessing.binarize(X, threshold=...)`

Thresholds a numeric matrix to 0/1 values. Values above `THRESHOLD` become 1,
at or below become 0.

```
Binarize(X, 0.5, BINARIZED)
```

---

### `Normalize(X, NORM, NORMALIZED)`

**scikit-learn reference:** `sklearn.preprocessing.normalize(X, norm=...)`

Scales each *sample* (row) independently so that its norm equals 1. `NORM`
is one of `l1`, `l2`, `max`. Note this is row-wise normalisation of samples,
not column-wise standardisation of features (that is `standard_scaler`).

```
Normalize(X, l2, NORMALIZED)
```

---

### `PolynomialFeatures(X, DEGREE, EXPANDED)`

**scikit-learn reference:** `sklearn.preprocessing.PolynomialFeatures(degree=D).fit_transform(X)` —
used here as a pure function since there are no data-dependent parameters.

Generates polynomial and interaction features up to `DEGREE`. For degree 2 with
features [a, b], produces [1, a, b, a², ab, b²].

```
PolynomialFeatures(X, 2, EXPANDED)
```

---

## Section 10: Metrics

Metrics are **pure functions** — they take ground-truth labels and predictions,
return a score. No estimator involved. These are all implemented via a single
polymorphic predicate discriminating on the metric name.

---

### `Metric(METRIC_NAME, Y_TRUE, Y_PRED, SCORE)`

**scikit-learn reference:** The functions in `sklearn.metrics`:
`accuracy_score`, `f1_score`, `precision_score`, `recall_score`,
`roc_auc_score`, `r2_score`, `mean_squared_error`, `mean_absolute_error`,
`log_loss`.

All point metrics go through this single predicate. `METRIC_NAME` is an atom.

| `METRIC_NAME` | scikit-learn function | Notes |
|---|---|---|
| `accuracy` | `accuracy_score` | classifiers |
| `f1` | `f1_score(average='binary')` | binary classifiers |
| `f1_weighted` | `f1_score(average='weighted')` | multiclass |
| `f1_macro` | `f1_score(average='macro')` | multiclass |
| `precision` | `precision_score` | |
| `recall` | `recall_score` | |
| `roc_auc` | `roc_auc_score` | needs `PredictProba` output |
| `log_loss` | `log_loss` | needs `PredictProba` output |
| `r2` | `r2_score` | regressors |
| `mse` | `mean_squared_error` | regressors |
| `mae` | `mean_absolute_error` | regressors |
| `rmse` | `mean_squared_error(squared=False)` | regressors |

```
Metric(accuracy,     Ytrue, Ypred,  SCORE)
Metric(f1_weighted,  Ytrue, Ypred,  SCORE)
Metric(roc_auc,      Ytrue, Yproba, SCORE)   % Y_PRED must be probabilities
Metric(r2,           Ytrue, Ypred,  SCORE)
Metric(mse,          Ytrue, Ypred,  SCORE)
```

---

### `ConfusionMatrix(Y_TRUE, Y_PRED, MATRIX)`

**scikit-learn reference:** `sklearn.metrics.confusion_matrix(y_true, y_pred)`

Returns the confusion matrix as a 2D structure. Entry `MATRIX[i][j]` is the
number of samples of true class `i` predicted as class `j`. The diagonal
contains correct predictions.

```
ConfusionMatrix(Ytrue, Ypred, MATRIX)
```

---

### `ClassificationReport(Y_TRUE, Y_PRED, CLASSES, REPORT)`

**scikit-learn reference:** `sklearn.metrics.classification_report(y_true, y_pred)`

Returns per-class precision, recall, F1, and support. `REPORT` is a list of
`class=metrics(PRECISION, RECALL, F1, SUPPORT)` terms, one per class in
`CLASSES`.

```
ClassificationReport(Ytrue, Ypred, [cat, dog, bird], REPORT)
% REPORT = [cat=metrics(0.91, 0.88, 0.89, 120),
%           dog=metrics(0.87, 0.92, 0.89, 95),
%           bird=metrics(0.95, 0.90, 0.92, 80)]
```

---

## Section 11: Datasets

---

### `LoadDataset(NAME, DATASET)`

**scikit-learn reference:** `sklearn.datasets.load_*()` — the built-in toy
datasets bundled with scikit-learn for experimentation.

Loads a built-in dataset. `NAME` is one of:

| Atom | Description | Task |
|---|---|---|
| `iris` | 150 samples, 4 features, 3 flower species | classification |
| `digits` | 1797 handwritten digit images (8×8) | classification |
| `wine` | 178 wine samples, 13 chemical features | classification |
| `breast_cancer` | 569 tumour samples, 30 features | classification |
| `diabetes` | 442 samples, 10 features | regression |
| `california_housing` | 20640 census blocks | regression |

```
LoadDataset(iris, DATASET)
% DATASET = Dataset(X, Y)  where X is (150,4) and Y is (150,)
```

---

### `MakeDataset(KIND, OPTIONS, DATASET)`

**scikit-learn reference:** `sklearn.datasets.make_classification`,
`make_regression`, `make_blobs`, `make_moons`, `make_circles` — synthetic
dataset generators.

Generates a synthetic dataset for testing and prototyping. `KIND` is one of
`classification`, `regression`, `blobs`, `moons`, `circles`. `OPTIONS` is a
list of `key=value` pairs controlling the generation.

```
MakeDataset(classification,
            [n_samples=1000, n_features=20, n_classes=3,
             n_informative=10, random_state=42],
            DATASET)

MakeDataset(blobs,
            [n_samples=500, n_centers=4, cluster_std=1.0],
            DATASET)

MakeDataset(moons,
            [n_samples=200, noise=0.1],
            DATASET)
```

---

### `LoadCsv(PATH, OPTIONS, DATASET)`

**scikit-learn reference:** `pandas.read_csv` + scikit-learn conventions for
structuring a DataFrame into `X` and `Y`.

Loads a CSV file into a `Dataset` term. `OPTIONS` controls parsing behaviour
and column selection:

```
LoadCsv('/data/titanic.csv',
        [target=survived, drop=[name, ticket], na_action=drop],
        DATASET)
```

Common options: `target=COLUMN` (which column becomes `Y`), `drop=[COL,...]`
(columns to exclude), `na_action=drop|fill`, `fill_value=VALUE`.

---

## Section 12: Serialization

---

### `SaveFitted(FITTED, PATH)`

**scikit-learn reference:** `joblib.dump(estimator, path)` — serializes a
fitted estimator to disk using joblib's efficient binary format.

Persists a `Fitted` term to a file at `PATH`. The file captures all learned
state so the model can be restored in a future session without retraining.
Works on pipelines as well as individual estimators.

```
SaveFitted(FITTED_PIPELINE, '/models/classifier_v1.joblib')
```

---

### `LoadFitted(PATH, FITTED)`

**scikit-learn reference:** `joblib.load(path)` — restores a fitted estimator
from disk.

Restores a `Fitted` term from a previously saved file. The restored `FITTED`
can be used with `Predict`, `Transform`, `Score`, `Learned`, and all other
predicates that accept a fitted estimator.

```
LoadFitted('/models/classifier_v1.joblib', FITTED)
Predict(FITTED, Xnew, PREDICTIONS)
```

---

## Predicate Summary

### Core Term Constructors

| Predicate | Arity | Description |
|---|---|---|
| `MakeEst` | 3 | Construct an estimator term with defaults filled |
| `Pipeline` | 2 | Construct a pipeline estimator from a step list |

### Fitting

| Predicate | Arity | Description |
|---|---|---|
| `Fit` | 3 | Fit an estimator to a Dataset term |
| `Fit` | 4 | Fit with raw X and Y |

### Prediction and Transformation

| Predicate | Arity | Description |
|---|---|---|
| `Predict` | 3 | Predict labels or values |
| `Transform` | 3 | Transform features |
| `FitTransform` | 4 | Fit and transform in one call |
| `PredictProba` | 3 | Predict class probabilities |
| `DecisionFunction` | 3 | Raw decision scores |

### State Query

| Predicate | Arity | Description |
|---|---|---|
| `Learned` | 3 | Read any learned attribute from a fitted estimator |
| `Param` | 3 | Read any hyperparameter from fitted or unfitted estimator |

### Evaluation

| Predicate | Arity | Description |
|---|---|---|
| `Score` | 3 | Score with default metric |
| `Score` | 4 | Score with explicit metric |
| `CrossValScore` | 4 | Cross-validated scores, default metric |
| `CrossValScore` | 5 | Cross-validated scores, explicit metric |
| `CrossValidate` | 5 | Cross-validate multiple metrics simultaneously |

### Data Splitting

| Predicate | Arity | Description |
|---|---|---|
| `SplitData` | 3 | Single train/test split |
| `SplitData` | 4 | Single train/test split with seed |
| `KFoldSplit` | 3 | K-fold splits via backtracking |
| `StratifiedSplit` | 3 | Stratified K-fold via backtracking |

### Pipelines

| Predicate | Arity | Description |
|---|---|---|
| `Pipeline` | 2 | Construct a pipeline |
| `PipelineStep` | 3 | Extract a named step from a fitted pipeline |

### Hyperparameter Search

| Predicate | Arity | Description |
|---|---|---|
| `GridSearch` | 5 | Exhaustive grid search |
| `GridSearch` | 6 | Grid search with explicit metric |
| `RandomSearch` | 6 | Random search |
| `SearchResults` | 2 | Full results table from a search |
| `BestParams` | 2 | Best parameters found |
| `BestScore` | 2 | Best score found |

### Introspection (Fact Tables)

| Predicate | Arity | Description |
|---|---|---|
| `Algorithm` | 2 | Enumerate algorithms by role |
| `DefaultParams` | 2 | Default hyperparameters for an algorithm |
| `ParamKey` | 3 | Valid keys and domains for an algorithm |

### Pure Preprocessing

| Predicate | Arity | Description |
|---|---|---|
| `EncodeLabels` | 3 | Encode symbolic labels to integers |
| `Binarize` | 3 | Threshold a matrix to 0/1 |
| `Normalize` | 3 | Row-wise normalisation |
| `PolynomialFeatures` | 3 | Generate polynomial/interaction features |

### Metrics

| Predicate | Arity | Description |
|---|---|---|
| `Metric` | 4 | All point-wise metrics via name dispatch |
| `ConfusionMatrix` | 3 | Confusion matrix |
| `ClassificationReport` | 4 | Per-class precision/recall/F1 |

### Datasets

| Predicate | Arity | Description |
|---|---|---|
| `LoadDataset` | 2 | Load a built-in toy dataset |
| `MakeDataset` | 3 | Generate a synthetic dataset |
| `LoadCsv` | 3 | Load a CSV file |

### Serialization

| Predicate | Arity | Description |
|---|---|---|
| `SaveFitted` | 2 | Save a fitted estimator to disk |
| `LoadFitted` | 2 | Load a fitted estimator from disk |

---

## Design Notes

### Why `Learned/3` instead of per-attribute predicates

A naive design would expose each scikit-learn attribute as its own predicate:
`Coef(FITTED, COEF)`, `FeatureImportances(FITTED, FI)`, etc. This would
balloon the API to hundreds of predicates — one per algorithm per attribute.
Instead, `Learned/3` treats the attribute name as a first-class argument.
This mirrors how scikit-learn itself works (`getattr(est, 'coef_')`) and
keeps the predicate count flat regardless of how many algorithms are added.

### Why splitting uses backtracking

`KFoldSplit` and `StratifiedSplit` generate one split per solution rather
than returning a list of splits. This is the natural Prolog idiom and composes
cleanly: use them directly in a goal that processes one split at a time, or
wrap in `FindAll` to materialise all splits as a list. It also means the
interface to a 2-fold and a 100-fold splitter is identical.

### Why pipelines are just `Est` terms

A pipeline could have been a separate term type with its own predicates.
Instead, `Pipeline/2` simply produces an `Est(pipeline, [steps=...])` term.
This means every predicate that works on estimators — `Fit`, `Predict`,
`CrossValScore`, `GridSearch`, `SaveFitted` — automatically works on pipelines
too. Composition is free.

### The `Fitted` term is immutable from Prolog's perspective

scikit-learn's Python objects are mutable — calling `.fit()` modifies the
object in place. At the Prolog level this is hidden: `Fit` takes an `Est` and
returns a new `Fitted`. You can hold references to multiple `Fitted` terms
simultaneously (e.g. models trained on different data splits) without any
aliasing concerns. The Python side manages the actual objects; Prolog sees
only ground terms.
