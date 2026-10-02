# Clausal — scikit-learn (`sklearn` module)

## Overview

The `sklearn` module provides predicates for machine learning via [scikit-learn](https://scikit-learn.org/). Data flows through tagged tuples — `Est`, `Dataset`, `Fitted`, `Split` — that unify naturally with Clausal's logic variables.

```clausal
-import_from(sklearn, [Est, Dataset, Fitted, load_dataset, fit, predict, score])

train_and_predict(ALGO, DATASET, PREDS) <- (
    load_dataset(DATASET, D),
    fit(Est(ALGO, {}), D, F),
    D is ("Dataset", X, Y),
    predict(F, X, PREDS)
)
```

Or via [module import](import.md):

```clausal
-import_module(sklearn)

main <- (
    sklearn.load_dataset("iris", D),
    sklearn.fit(sklearn.Est("random_forest", {"n_estimators": 10}), D, F),
    sklearn.score(F, D, S),
    ++print(f"Accuracy: {S}")
)
```

---

## Import

```clausal
-import_from(sklearn, [
    Est, Dataset, Fitted, Split,
    algorithm, default_params, param_key, make_est, param,
    load_dataset, make_dataset, split_data, k_fold_split, stratified_split,
    fit, predict, transform, fit_transform, predict_proba, decision_function,
    score, metric, cross_val_score, cross_validate,
    confusion_matrix, classification_report,
    pipeline, pipeline_step,
    grid_search, random_search, best_params, best_score, search_results,
    learned, encode_labels, binarize, normalize, polynomial_features,
    save_fitted, load_fitted,
    kfold
])
```

---

## Term constructors

The module uses tagged tuples as its term language. These are plain Python tuples that [unify](predicates.md) with `is`:

| Constructor | Shape | Description |
|-------------|-------|-------------|
| `Est(algo, params)` | `("Est", algo, params_dict)` | Unfitted estimator description |
| `Dataset(X, Y)` | `("Dataset", X, Y)` | Feature matrix + optional target |
| `Fitted(est, handle)` | `("Fitted", est, handle)` | Fitted estimator (opaque handle) |
| `Split(train, test)` | `("Split", train_dataset, test_dataset)` | Train/test partition |

```clausal
--8<-- "tests/fixtures/docs/sklearn_sigs.txt:term_constructors"
```

---

## Algorithms

The module ships with a registry of named algorithms. Use `algorithm/2` to enumerate or check role membership.

| Predicate | Mode | Description |
|-----------|------|-------------|
| `algorithm(Algo, Role)` | `?Algo, ?Role` | Enumerate or check algorithm/role pairs |
| `default_params(Algo, Params)` | `+Algo, -Params` | Default hyperparameters for an algorithm |
| `param_key(Algo, Key, Domain)` | `+Algo, -Key, -Domain` | Enumerate valid parameter keys |
| `make_est(Algo, Params, Est)` | `+Algo, +Params, -Est` | Construct `Est` term, filling defaults |
| `param(EstOrFitted, Key, Value)` | `+EstOrFitted, +Key, -Value` | Read a hyperparameter value |

??? example "Supported algorithms"

    **Classifiers**: `random_forest`, `logistic_regression`, `svc`, `knn_classifier`, `naive_bayes`, `decision_tree`, `gradient_boosting`, `adaboost`, `extra_trees`

    **Regressors**: `random_forest_regressor`, `linear_regression`, `ridge`, `lasso`, `elastic_net`, `svr`, `knn_regressor`, `decision_tree_regressor`, `gradient_boosting_regressor`

    **Transformers**: `pca`, `standard_scaler`, `min_max_scaler`, `one_hot_encoder`, `label_encoder`, `tfidf_vectorizer`, `truncated_svd`, `nmf`

    **Clusterers**: `kmeans`, `dbscan`, `agglomerative`

```clausal
--8<-- "tests/fixtures/docs/sklearn_sigs.txt:algorithm_examples"
```

---

## Data loading and splitting

| Predicate | Mode | Description |
|-----------|------|-------------|
| `load_dataset(Name, Dataset)` | `+Name, -Dataset` | Load a built-in dataset (`"iris"`, `"diabetes"`, `"wine"`, `"breast_cancer"`, `"digits"`, `"linnerud"`) |
| `make_dataset(Kind, Opts, Dataset)` | `+Kind, +Opts, -Dataset` | Generate synthetic data (`"classification"`, `"regression"`, `"blobs"`, `"moons"`, `"circles"`) |
| `split_data(Dataset, TestSize, Split)` | `+Dataset, +TestSize, -Split` | Train/test split |
| `split_data(Dataset, TestSize, Seed, Split)` | `+Dataset, +TestSize, +Seed, -Split` | Reproducible split |
| `k_fold_split(Dataset, K, Split)` | `+Dataset, +K, -Split` | K-fold splits via backtracking |
| `stratified_split(Dataset, K, Split)` | `+Dataset, +K, -Split` | Stratified K-fold via backtracking |

```clausal
--8<-- "tests/fixtures/docs/sklearn_sigs.txt:data_loading_examples"
```

---

## Fitting and prediction

| Predicate | Mode | Description |
|-----------|------|-------------|
| `fit(Est, Dataset, Fitted)` | `+Est, +Dataset, -Fitted` | fit estimator on a dataset |
| `fit(Est, X, Y, Fitted)` | `+Est, +X, +Y, -Fitted` | fit on raw feature matrix + target |
| `predict(Fitted, X, Preds)` | `+Fitted, +X, -Preds` | predict from fitted model |
| `transform(Fitted, X, Transformed)` | `+Fitted, +X, -Transformed` | transform features |
| `fit_transform(Est, Dataset, Transformed, Fitted)` | `+Est, +Dataset, -Transformed, -Fitted` | fit + transform in one step |
| `predict_proba(Fitted, X, Proba)` | `+Fitted, +X, -Proba` | Class probability matrix |
| `decision_function(Fitted, X, Scores)` | `+Fitted, +X, -Scores` | Decision function scores |

```clausal
--8<-- "tests/fixtures/docs/sklearn_sigs.txt:fit_predict_examples"
```

---

## Scoring and metrics

| Predicate | Mode | Description |
|-----------|------|-------------|
| `score(Fitted, Dataset, S)` | `+Fitted, +Dataset, -S` | Default metric score |
| `score(Fitted, Dataset, metric, S)` | `+Fitted, +Dataset, +metric, -S` | score with explicit metric |
| `metric(Name, YTrue, YPred, S)` | `+Name, +YTrue, +YPred, -S` | Compute a named metric |
| `cross_val_score(Est, Dataset, CV, Scores)` | `+Est, +Dataset, +CV, -Scores` | Cross-validation scores |
| `cross_val_score(Est, Dataset, CV, metric, Scores)` | `+Est, +Dataset, +CV, +metric, -Scores` | CV with explicit metric |
| `cross_validate(Est, Dataset, CV, Metrics, Results)` | `+Est, +Dataset, +CV, +Metrics, -Results` | Multi-metric cross-validation |
| `confusion_matrix(YTrue, YPred, Matrix)` | `+YTrue, +YPred, -Matrix` | Confusion matrix |
| `classification_report(YTrue, YPred, Classes, Report)` | `+YTrue, +YPred, +Classes, -Report` | Per-class precision/recall/F1 |

Available metric names: `"accuracy"`, `"f1"`, `"f1_weighted"`, `"f1_macro"`, `"precision"`, `"recall"`, `"roc_auc"`, `"r2"`, `"mse"`, `"mae"`, `"rmse"`.

```clausal
--8<-- "tests/fixtures/docs/sklearn_sigs.txt:scoring_examples"
```

**Cross-validation strategies**: pass an integer for stratified K-fold (recommended for classification), or use `kfold(K)` for plain K-fold.

---

## Pipelines

| Predicate | Mode | Description |
|-----------|------|-------------|
| `pipeline(Steps, PipeEst)` | `+Steps, -PipeEst` | Build a pipeline `Est` from named steps |
| `pipeline_step(Fitted, StepName, StepFitted)` | `+Fitted, +StepName, -StepFitted` | Extract a fitted step from a fitted pipeline |

Steps are a list of `(name, Est(...))` tuples:

```clausal
--8<-- "tests/fixtures/docs/sklearn_sigs.txt:pipeline_example"
```

---

## Hyperparameter search

| Predicate | Mode | Description |
|-----------|------|-------------|
| `grid_search(Est, ParamGrid, Dataset, CV, BestFitted)` | `+Est, +Grid, +Data, +CV, -Best` | Exhaustive grid search |
| `grid_search(Est, ParamGrid, Dataset, CV, metric, BestFitted)` | `+Est, +Grid, +Data, +CV, +metric, -Best` | Grid search with explicit metric |
| `random_search(Est, ParamDists, Dataset, CV, NIter, BestFitted)` | `+Est, +Dists, +Data, +CV, +N, -Best` | Randomized search |
| `best_params(BestFitted, Params)` | `+BestFitted, -Params` | Best parameters from search |
| `best_score(BestFitted, score)` | `+BestFitted, -score` | Best CV score from search |
| `search_results(BestFitted, Results)` | `+BestFitted, -Results` | Full CV results dict |

```clausal
--8<-- "tests/fixtures/docs/sklearn_sigs.txt:grid_search_example"
```

---

## learned attributes

| Predicate | Mode | Description |
|-----------|------|-------------|
| `learned(Fitted, Attr, Value)` | `+Fitted, +Attr, -Value` | Read a learned attribute (e.g. `"feature_importances"`, `"coef"`, `"n_features_in"`, `"mean"`) |

```clausal
--8<-- "tests/fixtures/docs/sklearn_sigs.txt:learned_example"
```

---

## Preprocessing

| Predicate | Mode | Description |
|-----------|------|-------------|
| `encode_labels(Labels, Encoded, Mapping)` | `+Labels, -Encoded, -Mapping` | label encoding |
| `binarize(X, Threshold, Result)` | `+X, +Threshold, -Result` | Threshold to 0/1 |
| `normalize(X, Norm, Result)` | `+X, +Norm, -Result` | Row-wise normalization (`"l1"`, `"l2"`, `"max"`) |
| `polynomial_features(X, Degree, Result)` | `+X, +Degree, -Result` | Generate polynomial features |

---

## Serialization

| Predicate | Mode | Description |
|-----------|------|-------------|
| `save_fitted(Fitted, Path)` | `+Fitted, +Path` | Persist a fitted model to disk (joblib) |
| `load_fitted(Path, Fitted)` | `+Path, -Fitted` | Load a persisted model |

---

??? example "Complete workflow example"

    ```clausal
    --8<-- "tests/fixtures/docs/sklearn_sigs.txt:complete_workflow"
    ```

??? example "pipeline with grid search"

    ```clausal
    --8<-- "tests/fixtures/docs/sklearn_sigs.txt:pipeline_grid_search"
    ```

---

*See also: [Python Interop](python_integration.md) — `++()` escape for direct scikit-learn access · [Higher-Order](higher_order.md) — `maplist` and `include` for data preprocessing.*
