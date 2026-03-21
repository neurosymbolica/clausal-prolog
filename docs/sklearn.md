# Clausal — scikit-learn (`sklearn` module)

## Overview

The `sklearn` module provides predicates for machine learning via [scikit-learn](https://scikit-learn.org/). Data flows through tagged tuples — `Est`, `Dataset`, `Fitted`, `Split` — that unify naturally with Clausal's logic variables.

```clausal
-import_from(sklearn, [Est, Dataset, Fitted, LoadDataset, Fit, Predict, Score])

TrainAndPredict(ALGO, DATASET, PREDS) <- (
    LoadDataset(DATASET, D),
    Fit(Est(ALGO, {}), D, F),
    D is ("Dataset", X, Y),
    Predict(F, X, PREDS)
)
```

Or via module import:

```clausal
-import_module(sklearn)

Main <- (
    sklearn.LoadDataset("iris", D),
    sklearn.Fit(sklearn.Est("random_forest", {"n_estimators": 10}), D, F),
    sklearn.Score(F, D, S),
    ++print(f"Accuracy: {S}")
)
```

---

## Import

```clausal
-import_from(sklearn, [
    Est, Dataset, Fitted, Split,
    Algorithm, DefaultParams, ParamKey, MakeEst, Param,
    LoadDataset, MakeDataset, SplitData, KFoldSplit, StratifiedSplit,
    Fit, Predict, Transform, FitTransform, PredictProba, DecisionFunction,
    Score, Metric, CrossValScore, CrossValidate,
    ConfusionMatrix, ClassificationReport,
    Pipeline, PipelineStep,
    GridSearch, RandomSearch, BestParams, BestScore, SearchResults,
    Learned, EncodeLabels, Binarize, Normalize, PolynomialFeatures,
    SaveFitted, LoadFitted,
    kfold
])
```

---

## Term constructors

The module uses tagged tuples as its term language. These are plain Python tuples that unify with `is`:

| Constructor | Shape | Description |
|-------------|-------|-------------|
| `Est(algo, params)` | `("Est", algo, params_dict)` | Unfitted estimator description |
| `Dataset(X, Y)` | `("Dataset", X, Y)` | Feature matrix + optional target |
| `Fitted(est, handle)` | `("Fitted", est, handle)` | Fitted estimator (opaque handle) |
| `Split(train, test)` | `("Split", train_dataset, test_dataset)` | Train/test partition |

```clausal
% Destructure a dataset
LoadDataset("iris", D), D is ("Dataset", X, Y)

% Destructure a fitted model
Fit(Est("svc", {}), D, F), F is ("Fitted", E, H)
```

---

## Algorithms

The module ships with a registry of named algorithms. Use `Algorithm/2` to enumerate or check role membership.

| Predicate | Mode | Description |
|-----------|------|-------------|
| `Algorithm(Algo, Role)` | `?Algo, ?Role` | Enumerate or check algorithm/role pairs |
| `DefaultParams(Algo, Params)` | `+Algo, -Params` | Default hyperparameters for an algorithm |
| `ParamKey(Algo, Key, Domain)` | `+Algo, -Key, -Domain` | Enumerate valid parameter keys |
| `MakeEst(Algo, Params, Est)` | `+Algo, +Params, -Est` | Construct `Est` term, filling defaults |
| `Param(EstOrFitted, Key, Value)` | `+EstOrFitted, +Key, -Value` | Read a hyperparameter value |

??? example "Supported algorithms"

    **Classifiers**: `random_forest`, `logistic_regression`, `svc`, `knn_classifier`, `naive_bayes`, `decision_tree`, `gradient_boosting`, `adaboost`, `extra_trees`

    **Regressors**: `random_forest_regressor`, `linear_regression`, `ridge`, `lasso`, `elastic_net`, `svr`, `knn_regressor`, `decision_tree_regressor`, `gradient_boosting_regressor`

    **Transformers**: `pca`, `standard_scaler`, `min_max_scaler`, `one_hot_encoder`, `label_encoder`, `tfidf_vectorizer`, `truncated_svd`, `nmf`

    **Clusterers**: `kmeans`, `dbscan`, `agglomerative`

```clausal
% Check that random_forest is a classifier
Algorithm("random_forest", "classifier")

% Enumerate all regressors
Algorithm(ALGO, "regressor")
```

---

## Data loading and splitting

| Predicate | Mode | Description |
|-----------|------|-------------|
| `LoadDataset(Name, Dataset)` | `+Name, -Dataset` | Load a built-in dataset (`"iris"`, `"diabetes"`, `"wine"`, `"breast_cancer"`, `"digits"`, `"linnerud"`) |
| `MakeDataset(Kind, Opts, Dataset)` | `+Kind, +Opts, -Dataset` | Generate synthetic data (`"classification"`, `"regression"`, `"blobs"`, `"moons"`, `"circles"`) |
| `SplitData(Dataset, TestSize, Split)` | `+Dataset, +TestSize, -Split` | Train/test split |
| `SplitData(Dataset, TestSize, Seed, Split)` | `+Dataset, +TestSize, +Seed, -Split` | Reproducible split |
| `KFoldSplit(Dataset, K, Split)` | `+Dataset, +K, -Split` | K-fold splits via backtracking |
| `StratifiedSplit(Dataset, K, Split)` | `+Dataset, +K, -Split` | Stratified K-fold via backtracking |

```clausal
% Load and split iris
LoadDataset("iris", D),
SplitData(D, 0.2, 42, S),
S is ("Split", TRAIN, TEST)

% Synthetic classification data
MakeDataset("classification",
            {"n_samples": 200, "n_features": 5, "random_state": 42},
            D)
```

---

## Fitting and prediction

| Predicate | Mode | Description |
|-----------|------|-------------|
| `Fit(Est, Dataset, Fitted)` | `+Est, +Dataset, -Fitted` | Fit estimator on a dataset |
| `Fit(Est, X, Y, Fitted)` | `+Est, +X, +Y, -Fitted` | Fit on raw feature matrix + target |
| `Predict(Fitted, X, Preds)` | `+Fitted, +X, -Preds` | Predict from fitted model |
| `Transform(Fitted, X, Transformed)` | `+Fitted, +X, -Transformed` | Transform features |
| `FitTransform(Est, Dataset, Transformed, Fitted)` | `+Est, +Dataset, -Transformed, -Fitted` | Fit + transform in one step |
| `PredictProba(Fitted, X, Proba)` | `+Fitted, +X, -Proba` | Class probability matrix |
| `DecisionFunction(Fitted, X, Scores)` | `+Fitted, +X, -Scores` | Decision function scores |

```clausal
% Classification workflow
LoadDataset("iris", D),
Fit(Est("random_forest", {"n_estimators": 100}), D, F),
D is ("Dataset", X, Y),
Predict(F, X, PREDS)

% PCA transform
LoadDataset("iris", D),
D is ("Dataset", X, Y),
Fit(Est("pca", {"n_components": 2}), ("Dataset", X, None), F),
Transform(F, X, REDUCED)
```

---

## Scoring and metrics

| Predicate | Mode | Description |
|-----------|------|-------------|
| `Score(Fitted, Dataset, S)` | `+Fitted, +Dataset, -S` | Default metric score |
| `Score(Fitted, Dataset, Metric, S)` | `+Fitted, +Dataset, +Metric, -S` | Score with explicit metric |
| `Metric(Name, YTrue, YPred, S)` | `+Name, +YTrue, +YPred, -S` | Compute a named metric |
| `CrossValScore(Est, Dataset, CV, Scores)` | `+Est, +Dataset, +CV, -Scores` | Cross-validation scores |
| `CrossValScore(Est, Dataset, CV, Metric, Scores)` | `+Est, +Dataset, +CV, +Metric, -Scores` | CV with explicit metric |
| `CrossValidate(Est, Dataset, CV, Metrics, Results)` | `+Est, +Dataset, +CV, +Metrics, -Results` | Multi-metric cross-validation |
| `ConfusionMatrix(YTrue, YPred, Matrix)` | `+YTrue, +YPred, -Matrix` | Confusion matrix |
| `ClassificationReport(YTrue, YPred, Classes, Report)` | `+YTrue, +YPred, +Classes, -Report` | Per-class precision/recall/F1 |

Available metric names: `"accuracy"`, `"f1"`, `"f1_weighted"`, `"f1_macro"`, `"precision"`, `"recall"`, `"roc_auc"`, `"r2"`, `"mse"`, `"mae"`, `"rmse"`.

```clausal
% Score a classifier
Score(F, D, S), S > 0.9

% 3-fold cross-validation
CrossValScore(Est("logistic_regression", {"max_iter": 200}),
              D, 3, SCORES)

% Multi-metric CV
CrossValidate(Est("logistic_regression", {"max_iter": 200}),
              D, 3, ["accuracy", "f1_weighted"], R)
```

**Cross-validation strategies**: pass an integer for stratified K-fold (recommended for classification), or use `kfold(K)` for plain K-fold.

---

## Pipelines

| Predicate | Mode | Description |
|-----------|------|-------------|
| `Pipeline(Steps, PipeEst)` | `+Steps, -PipeEst` | Build a pipeline `Est` from named steps |
| `PipelineStep(Fitted, StepName, StepFitted)` | `+Fitted, +StepName, -StepFitted` | Extract a fitted step from a fitted pipeline |

Steps are a list of `(name, Est(...))` tuples:

```clausal
Pipeline([("scaler", Est("standard_scaler", {})),
          ("clf", Est("logistic_regression", {"max_iter": 200}))],
         PIPE),
LoadDataset("iris", D),
Fit(PIPE, D, F),
Score(F, D, S)
```

---

## Hyperparameter search

| Predicate | Mode | Description |
|-----------|------|-------------|
| `GridSearch(Est, ParamGrid, Dataset, CV, BestFitted)` | `+Est, +Grid, +Data, +CV, -Best` | Exhaustive grid search |
| `GridSearch(Est, ParamGrid, Dataset, CV, Metric, BestFitted)` | `+Est, +Grid, +Data, +CV, +Metric, -Best` | Grid search with explicit metric |
| `RandomSearch(Est, ParamDists, Dataset, CV, NIter, BestFitted)` | `+Est, +Dists, +Data, +CV, +N, -Best` | Randomized search |
| `BestParams(BestFitted, Params)` | `+BestFitted, -Params` | Best parameters from search |
| `BestScore(BestFitted, Score)` | `+BestFitted, -Score` | Best CV score from search |
| `SearchResults(BestFitted, Results)` | `+BestFitted, -Results` | Full CV results dict |

```clausal
LoadDataset("iris", D),
GridSearch(Est("svc", {}),
           {"C": [0.1, 1.0, 10.0], "kernel": ["rbf", "linear"]},
           D, 3, BEST),
BestParams(BEST, PARAMS),
BestScore(BEST, SCORE)
```

---

## Learned attributes

| Predicate | Mode | Description |
|-----------|------|-------------|
| `Learned(Fitted, Attr, Value)` | `+Fitted, +Attr, -Value` | Read a learned attribute (e.g. `"feature_importances"`, `"coef"`, `"n_features_in"`, `"mean"`) |

```clausal
Fit(Est("random_forest", {"n_estimators": 10}), D, F),
Learned(F, "feature_importances", FI)
```

---

## Preprocessing

| Predicate | Mode | Description |
|-----------|------|-------------|
| `EncodeLabels(Labels, Encoded, Mapping)` | `+Labels, -Encoded, -Mapping` | Label encoding |
| `Binarize(X, Threshold, Result)` | `+X, +Threshold, -Result` | Threshold to 0/1 |
| `Normalize(X, Norm, Result)` | `+X, +Norm, -Result` | Row-wise normalization (`"l1"`, `"l2"`, `"max"`) |
| `PolynomialFeatures(X, Degree, Result)` | `+X, +Degree, -Result` | Generate polynomial features |

---

## Serialization

| Predicate | Mode | Description |
|-----------|------|-------------|
| `SaveFitted(Fitted, Path)` | `+Fitted, +Path` | Persist a fitted model to disk (joblib) |
| `LoadFitted(Path, Fitted)` | `+Path, -Fitted` | Load a persisted model |

---

??? example "Complete workflow example"

    ```clausal
    -import_from(sklearn, [Est, Dataset, Fitted, Split,
                           LoadDataset, SplitData, Fit, Predict, Score,
                           ConfusionMatrix, Learned])

    % Load, split, train, evaluate
    IrisWorkflow(SCORE, IMPORTANCES) <- (
        LoadDataset("iris", D),
        SplitData(D, 0.2, 42, S),
        S is ("Split", TRAIN, TEST),
        Fit(Est("random_forest", {"n_estimators": 100, "random_state": 42}),
            TRAIN, F),
        Score(F, TEST, SCORE),
        Learned(F, "feature_importances", IMPORTANCES)
    )
    ```

??? example "Pipeline with grid search"

    ```clausal
    -import_from(sklearn, [Est, LoadDataset, Pipeline, Fit, Score,
                           GridSearch, BestParams, BestScore])

    SearchBestPipeline(PARAMS, SCORE) <- (
        LoadDataset("iris", D),
        Pipeline([("scaler", Est("standard_scaler", {})),
                  ("clf", Est("svc", {}))],
                 PIPE),
        GridSearch(PIPE,
                   {"clf__C": [0.1, 1.0, 10.0],
                    "clf__kernel": ["rbf", "linear"]},
                   D, 5, "accuracy", BEST),
        BestParams(BEST, PARAMS),
        BestScore(BEST, SCORE)
    )
    ```
