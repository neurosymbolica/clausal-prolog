# Predicate renames (2026-10-02)

Breaking: these predicate names were TitleCase (Python class-style),
which the engine's TitleCase lint rejects in functor position --
Clausal code could not call them by name. They are renamed to
lower_snake_case, matching clausal-jax / clausal-torch convention.
Acronyms collapse to one lowercase word (e.g. `FFT` -> `fft`,
`KMeans` -> `k_means`).

| Old (TitleCase) | New (lower_snake_case) |
|---|---|
| `Algorithm` | `algorithm` |
| `BestParams` | `best_params` |
| `BestScore` | `best_score` |
| `Binarize` | `binarize` |
| `ClassificationReport` | `classification_report` |
| `ConfusionMatrix` | `confusion_matrix` |
| `CrossValScore` | `cross_val_score` |
| `CrossValidate` | `cross_validate` |
| `DecisionFunction` | `decision_function` |
| `DefaultParams` | `default_params` |
| `EncodeLabels` | `encode_labels` |
| `Fit` | `fit` |
| `FitTransform` | `fit_transform` |
| `GridSearch` | `grid_search` |
| `KFoldSplit` | `k_fold_split` |
| `Learned` | `learned` |
| `LoadCsv` | `load_csv` |
| `LoadDataset` | `load_dataset` |
| `LoadFitted` | `load_fitted` |
| `MakeDataset` | `make_dataset` |
| `MakeEst` | `make_est` |
| `Metric` | `metric` |
| `Normalize` | `normalize` |
| `Param` | `param` |
| `ParamKey` | `param_key` |
| `Pipeline` | `pipeline` |
| `PipelineStep` | `pipeline_step` |
| `PolynomialFeatures` | `polynomial_features` |
| `Predict` | `predict` |
| `PredictProba` | `predict_proba` |
| `RandomSearch` | `random_search` |
| `SaveFitted` | `save_fitted` |
| `Score` | `score` |
| `SearchResults` | `search_results` |
| `SplitData` | `split_data` |
| `StratifiedSplit` | `stratified_split` |
| `Transform` | `transform` |

# Term constructor renames (2026-10-04)

Breaking: the term constructors were TitleCase too. They are plain Python
helpers (not predicates) that build tagged tuples, and both the helper
names and the TAGS are now lower_snake_case, with no aliases -- so the
term `est(svc, {})` written in a clause is the very term the adapter
builds and reads.

| Old | New | Term |
|---|---|---|
| `Est(Algo, Params)` | `est(Algo, Params)` | `('Est', ...)` -> `('est', ...)` |
| `Dataset(X, Y)` | `dataset(X, Y)` | `('Dataset', ...)` -> `('dataset', ...)` |
| `Fitted(Est, Handle)` | `fitted(Est, Handle)` | `('Fitted', ...)` -> `('fitted', ...)` |
| `Split(Train, Test)` | `split(Train, Test)` | `('Split', ...)` -> `('split', ...)` |
