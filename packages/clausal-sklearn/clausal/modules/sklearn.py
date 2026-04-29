"""clausal.modules.sklearn — scikit-learn predicates for Clausal.

Provides predicates for machine learning via scikit-learn::

    -import_from(sklearn, [Fit, Predict, Score, LoadDataset, Algorithm,
                           Est, Dataset, Fitted, Split])

Term constructors (tagged tuples for deep unification):
    Est(algorithm, params)     — unfitted estimator description
    Dataset(x, y)              — supervised/unsupervised dataset
    Fitted(est, handle)        — fitted estimator with opaque handle
    Split(train, test)         — train/test partition

Layers
------
1. **Term constructors & algorithm registry** — Est, Dataset, Fitted, Split,
   Algorithm/2, DefaultParams/2, ParamKey/3
2. **Data loading & splitting** — LoadDataset/2, MakeDataset/3, LoadCsv/3,
   SplitData/3,4, KFoldSplit/3, StratifiedSplit/3
3. **Fitting & prediction** — Fit/3,4, Predict/3, Transform/3,
   FitTransform/4, PredictProba/3, DecisionFunction/3
4. **Scoring & metrics** — Score/3,4, Metric/4, CrossValScore/4,5,
   CrossValidate/5, ConfusionMatrix/3, ClassificationReport/4
5. **Pipelines & search** — Pipeline/2, PipelineStep/3, GridSearch/5,6,
   RandomSearch/6, SearchResults/2, BestParams/2, BestScore/2
6. **Extras** — Learned/3, Param/3, MakeEst/3, EncodeLabels/3, Binarize/3,
   Normalize/3, PolynomialFeatures/3, SaveFitted/2, LoadFitted/2
"""

from __future__ import annotations

import threading as _threading
from typing import Any

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py import ModulePredicate, simple_to_trampoline
from clausal.terms import Compound, DictTerm


# ── Lazy sklearn import ───────────────────────────────────────────────────

_sk = None
_sk_lock = _threading.Lock()


_sk_datasets = None
_sk_model_selection = None
_sk_metrics = None
_sk_pipeline = None
_sk_preprocessing = None


def _ensure_sklearn():
    """Lazily import sklearn on first use.

    All submodule references are cached globally so individual functions
    never need bare ``from sklearn...`` imports.
    """
    global _sk, _sk_datasets, _sk_model_selection, _sk_metrics
    global _sk_pipeline, _sk_preprocessing
    if _sk is not None:
        return
    with _sk_lock:
        if _sk is not None:
            return
        import importlib

        sklearn = importlib.import_module("sklearn")
        importlib.import_module("sklearn.datasets")
        importlib.import_module("sklearn.decomposition")
        importlib.import_module("sklearn.ensemble")
        importlib.import_module("sklearn.linear_model")
        importlib.import_module("sklearn.metrics")
        importlib.import_module("sklearn.model_selection")
        importlib.import_module("sklearn.naive_bayes")
        importlib.import_module("sklearn.neighbors")
        importlib.import_module("sklearn.pipeline")
        importlib.import_module("sklearn.preprocessing")
        importlib.import_module("sklearn.svm")
        importlib.import_module("sklearn.tree")
        importlib.import_module("sklearn.cluster")
        importlib.import_module("sklearn.feature_extraction.text")

        _sk = sklearn
        _sk_datasets = sklearn.datasets
        _sk_model_selection = sklearn.model_selection
        _sk_metrics = sklearn.metrics
        _sk_pipeline = sklearn.pipeline
        _sk_preprocessing = sklearn.preprocessing


def _get_sklearn():
    _ensure_sklearn()
    return _sk


# ── Handle registry ───────────────────────────────────────────────────────

_MODELS: dict[int, Any] = {}
_NEXT_ID = 0
_MODEL_LOCK = _threading.Lock()


def _register_model(model) -> int:
    global _NEXT_ID
    with _MODEL_LOCK:
        handle = _NEXT_ID
        _NEXT_ID += 1
        _MODELS[handle] = model
    return handle


def _get_model(handle: int):
    m = _MODELS.get(handle)
    if m is None:
        raise ValueError(f"No sklearn model with handle {handle!r}")
    return m


# ── Term constructors (tagged tuples) ─────────────────────────────────────

def Est(algorithm, params=None):
    """Unfitted estimator term: ("Est", algorithm, params_dict)."""
    return ("Est", algorithm, params if params is not None else {})


def Dataset(x, y=None):
    """Dataset term: ("Dataset", x, y)."""
    return ("Dataset", x, y)


def Fitted(est, handle):
    """Fitted estimator term: ("Fitted", est, handle)."""
    return ("Fitted", est, handle)


def Split(train, test):
    """Train/test split term: ("Split", train, test)."""
    return ("Split", train, test)


# ── CV term constructors ──────────────────────────────────────────────────

class _CVFunc:
    """Callable that produces Compound("name", args) for CV strategies."""
    __slots__ = ("_name",)

    def __init__(self, name: str) -> None:
        self._name = name

    def __call__(self, *args):
        return Compound(self._name, args)

    def __repr__(self) -> str:
        return self._name


kfold = _CVFunc("kfold")
stratified_kfold = _CVFunc("stratified_kfold")
shuffle_split = _CVFunc("shuffle_split")
group_kfold = _CVFunc("group_kfold")
loo = Compound("loo", ())


# ── Algorithm registry ────────────────────────────────────────────────────

# Maps algorithm name -> (sklearn class import path, default role)
_ALGORITHM_REGISTRY: dict[str, tuple[str, str, str]] = {
    # (module_path, class_name, primary_role)
    # Classifiers
    "random_forest":             ("sklearn.ensemble", "RandomForestClassifier", "classifier"),
    "random_forest_regressor":   ("sklearn.ensemble", "RandomForestRegressor", "regressor"),
    "gradient_boosting":         ("sklearn.ensemble", "GradientBoostingClassifier", "classifier"),
    "gradient_boosting_regressor": ("sklearn.ensemble", "GradientBoostingRegressor", "regressor"),
    "adaboost":                  ("sklearn.ensemble", "AdaBoostClassifier", "classifier"),
    "extra_trees":               ("sklearn.ensemble", "ExtraTreesClassifier", "classifier"),
    "svc":                       ("sklearn.svm", "SVC", "classifier"),
    "svr":                       ("sklearn.svm", "SVR", "regressor"),
    "logistic_regression":       ("sklearn.linear_model", "LogisticRegression", "classifier"),
    "linear_regression":         ("sklearn.linear_model", "LinearRegression", "regressor"),
    "ridge":                     ("sklearn.linear_model", "Ridge", "regressor"),
    "lasso":                     ("sklearn.linear_model", "Lasso", "regressor"),
    "elastic_net":               ("sklearn.linear_model", "ElasticNet", "regressor"),
    "knn_classifier":            ("sklearn.neighbors", "KNeighborsClassifier", "classifier"),
    "knn_regressor":             ("sklearn.neighbors", "KNeighborsRegressor", "regressor"),
    "naive_bayes":               ("sklearn.naive_bayes", "GaussianNB", "classifier"),
    "decision_tree":             ("sklearn.tree", "DecisionTreeClassifier", "classifier"),
    "decision_tree_regressor":   ("sklearn.tree", "DecisionTreeRegressor", "regressor"),
    # Transformers
    "pca":                       ("sklearn.decomposition", "PCA", "transformer"),
    "standard_scaler":           ("sklearn.preprocessing", "StandardScaler", "transformer"),
    "min_max_scaler":            ("sklearn.preprocessing", "MinMaxScaler", "transformer"),
    "one_hot_encoder":           ("sklearn.preprocessing", "OneHotEncoder", "transformer"),
    "label_encoder":             ("sklearn.preprocessing", "LabelEncoder", "transformer"),
    "tfidf_vectorizer":          ("sklearn.feature_extraction.text", "TfidfVectorizer", "transformer"),
    "truncated_svd":             ("sklearn.decomposition", "TruncatedSVD", "transformer"),
    "nmf":                       ("sklearn.decomposition", "NMF", "transformer"),
    # Clusterers
    "kmeans":                    ("sklearn.cluster", "KMeans", "clusterer"),
    "dbscan":                    ("sklearn.cluster", "DBSCAN", "clusterer"),
    "agglomerative":             ("sklearn.cluster", "AgglomerativeClustering", "clusterer"),
}

# Backward compat aliases from spec
_ALGORITHM_ALIASES = {
    "svm": "svc",
    "knn": "knn_classifier",
}

# Algorithm/role fact table for nondeterministic enumeration
_ALGORITHM_FACTS = []
for _name, (_mod, _cls, _role) in _ALGORITHM_REGISTRY.items():
    _ALGORITHM_FACTS.append((_name, _role))
# Pipeline can be any role
_ALGORITHM_FACTS.append(("pipeline", "classifier"))
_ALGORITHM_FACTS.append(("pipeline", "regressor"))
_ALGORITHM_FACTS.append(("pipeline", "transformer"))


def _resolve_algorithm(name: str) -> str:
    """Resolve aliases and return canonical algorithm name."""
    name = str(name)
    return _ALGORITHM_ALIASES.get(name, name)


def _get_sklearn_class(algorithm: str):
    """Return the sklearn class for an algorithm name."""
    _ensure_sklearn()
    algorithm = _resolve_algorithm(algorithm)
    entry = _ALGORITHM_REGISTRY.get(algorithm)
    if entry is None:
        raise ValueError(f"Unknown sklearn algorithm: {algorithm!r}")
    mod_path, cls_name, _role = entry
    # Navigate from cached _sk root to the submodule
    parts = mod_path.split(".")
    mod = _sk
    for part in parts[1:]:  # skip "sklearn"
        mod = getattr(mod, part)
    return getattr(mod, cls_name)


def _instantiate_estimator(algorithm, params):
    """Create a sklearn estimator instance from algorithm name + params dict."""
    algorithm = str(algorithm)
    if algorithm == "pipeline":
        # Handled separately via Pipeline predicate
        raise ValueError("Use Pipeline/2 to construct pipeline estimators")
    cls = _get_sklearn_class(algorithm)
    if isinstance(params, dict):
        return cls(**params)
    return cls()


# ── Metric registry ──────────────────────────────────────────────────────

_METRIC_REGISTRY = {
    "accuracy":     ("sklearn.metrics", "accuracy_score", {}),
    "f1":           ("sklearn.metrics", "f1_score", {"average": "binary"}),
    "f1_weighted":  ("sklearn.metrics", "f1_score", {"average": "weighted"}),
    "f1_macro":     ("sklearn.metrics", "f1_score", {"average": "macro"}),
    "precision":    ("sklearn.metrics", "precision_score", {"average": "binary"}),
    "recall":       ("sklearn.metrics", "recall_score", {"average": "binary"}),
    "roc_auc":      ("sklearn.metrics", "roc_auc_score", {}),
    "log_loss":     ("sklearn.metrics", "log_loss", {}),
    "r2":           ("sklearn.metrics", "r2_score", {}),
    "mse":          ("sklearn.metrics", "mean_squared_error", {}),
    "mae":          ("sklearn.metrics", "mean_absolute_error", {}),
    "rmse":         ("sklearn.metrics", "root_mean_squared_error", {}),
}


def _get_metric_fn(name: str):
    """Return (callable, extra_kwargs) for a metric name."""
    _ensure_sklearn()
    entry = _METRIC_REGISTRY.get(str(name))
    if entry is None:
        raise ValueError(f"Unknown metric: {name!r}")
    _mod_path, fn_name, kwargs = entry
    return getattr(_sk_metrics, fn_name), kwargs


def _metric_to_scoring(name: str) -> str:
    """Convert our metric name to sklearn scoring string."""
    mapping = {
        "accuracy": "accuracy",
        "f1": "f1",
        "f1_weighted": "f1_weighted",
        "f1_macro": "f1_macro",
        "precision": "precision",
        "recall": "recall",
        "roc_auc": "roc_auc",
        "log_loss": "neg_log_loss",
        "r2": "r2",
        "mse": "neg_mean_squared_error",
        "mae": "neg_mean_absolute_error",
        "rmse": "neg_root_mean_squared_error",
    }
    s = mapping.get(str(name))
    if s is None:
        raise ValueError(f"Unknown metric for scoring: {name!r}")
    return s


# ── Dataset registry ─────────────────────────────────────────────────────

_DATASET_LOADERS = {
    "iris":               "load_iris",
    "digits":             "load_digits",
    "wine":               "load_wine",
    "breast_cancer":      "load_breast_cancer",
    "diabetes":           "load_diabetes",
    "california_housing": "fetch_california_housing",
}

_DATASET_GENERATORS = {
    "classification": "make_classification",
    "regression":     "make_regression",
    "blobs":          "make_blobs",
    "moons":          "make_moons",
    "circles":        "make_circles",
}


# ── CV strategy helper ───────────────────────────────────────────────────

def _make_cv(cv_term):
    """Convert a CV term to a sklearn cross-validation object or int."""
    _ensure_sklearn()
    ms = _sk_model_selection
    cv_term = deref(cv_term)
    if isinstance(cv_term, int):
        return cv_term
    if isinstance(cv_term, Compound):
        name = cv_term.functor
        args = cv_term.args
        if name == "kfold":
            return ms.KFold(n_splits=int(args[0]))
        elif name == "stratified_kfold":
            return ms.StratifiedKFold(n_splits=int(args[0]))
        elif name == "shuffle_split":
            return ms.ShuffleSplit(n_splits=int(args[0]), test_size=float(args[1]))
        elif name == "group_kfold":
            return ms.GroupKFold(n_splits=int(args[0]))
        elif name == "loo":
            return ms.LeaveOneOut()
    raise ValueError(f"Unknown CV strategy: {cv_term!r}")


# ── Helper: extract X, Y from dataset term ───────────────────────────────

def _unpack_dataset(d):
    """Extract (X, Y) from a Dataset tuple. Y may be None."""
    d = deref(d)
    if isinstance(d, tuple) and len(d) == 3 and d[0] == "Dataset":
        x = deref(d[1])
        y = deref(d[2])
        if y is None or (isinstance(y, str) and y == "nil"):
            y = None
        return x, y
    raise ValueError(f"Expected Dataset(X, Y), got {d!r}")


def _unpack_est(e):
    """Extract (algorithm, params) from an Est tuple."""
    e = deref(e)
    if isinstance(e, tuple) and len(e) == 3 and e[0] == "Est":
        return str(deref(e[1])), deref(e[2])
    raise ValueError(f"Expected Est(algorithm, params), got {e!r}")


def _unpack_fitted(f):
    """Extract (est_tuple, handle) from a Fitted tuple."""
    f = deref(f)
    if isinstance(f, tuple) and len(f) == 3 and f[0] == "Fitted":
        return deref(f[1]), int(deref(f[2]))
    raise ValueError(f"Expected Fitted(est, handle), got {f!r}")


def _unpack_split(s):
    """Extract (train_dataset, test_dataset) from a Split tuple."""
    s = deref(s)
    if isinstance(s, tuple) and len(s) == 3 and s[0] == "Split":
        return deref(s[1]), deref(s[2])
    raise ValueError(f"Expected Split(train, test), got {s!r}")


# ── Helper: build pipeline from steps ─────────────────────────────────────

def _build_pipeline(steps):
    """Build a sklearn Pipeline from a list of (name, Est(...)) tuples."""
    _ensure_sklearn()
    SkPipeline = _sk_pipeline.Pipeline
    sk_steps = []
    for step in steps:
        step = deref(step)
        if isinstance(step, tuple) and len(step) == 2:
            name, est = str(deref(step[0])), deref(step[1])
        else:
            raise ValueError(f"Pipeline step must be (name, Est(...)): {step!r}")
        algo, params = _unpack_est(est)
        sk_steps.append((name, _instantiate_estimator(algo, params)))
    return SkPipeline(sk_steps)


# ── Helper: convert param dict from clausal ───────────────────────────────

def _deref_params(params):
    """Deep-deref a params dict."""
    params = deref(params)
    if isinstance(params, dict):
        return {str(deref(k)): deref(v) for k, v in params.items()}
    return {}


# ═══════════════════════════════════════════════════════════════════════════
# Layer 1: Algorithm introspection (nondeterministic fact tables)
# ═══════════════════════════════════════════════════════════════════════════

def _algorithm_2(this_generator, _proceed, _fail, _catcher, algo_var, role_var, trail):
    """Algorithm/2: enumerate (algorithm, role) pairs."""
    algo_v = deref(algo_var)
    role_v = deref(role_var)
    for name, role in _ALGORITHM_FACTS:
        mark = trail.mark()
        if unify(algo_var, name, trail) and unify(role_var, role, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


def _default_params_2(algo, params_var, trail, k):
    """DefaultParams/2: get default params for an algorithm."""
    algo = str(deref(algo))
    algo = _resolve_algorithm(algo)
    if algo == "pipeline":
        if unify(params_var, {}, trail):
            yield None
        return
    cls = _get_sklearn_class(algo)
    instance = cls()
    defaults = instance.get_params()
    if unify(params_var, defaults, trail):
        yield None


def _param_key_3(this_generator, _proceed, _fail, _catcher, algo_var, key_var, domain_var, trail):
    """ParamKey/3: enumerate valid parameter keys for an algorithm."""
    algo = str(deref(algo_var))
    algo = _resolve_algorithm(algo)
    if algo == "pipeline":
        yield (_fail, DONE)
        return
    cls = _get_sklearn_class(algo)
    instance = cls()
    params = instance.get_params()
    for key in sorted(params.keys()):
        mark = trail.mark()
        if unify(key_var, key, trail) and unify(domain_var, "any", trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


# ═══════════════════════════════════════════════════════════════════════════
# Layer 2: Data loading and splitting
# ═══════════════════════════════════════════════════════════════════════════

def _load_dataset_2(name, dataset_var, trail, k):
    """LoadDataset/2: load a built-in sklearn dataset."""
    _ensure_sklearn()
    skd = _sk_datasets
    name = str(deref(name))
    loader_name = _DATASET_LOADERS.get(name)
    if loader_name is None:
        raise ValueError(f"Unknown built-in dataset: {name!r}")
    loader_fn = getattr(skd, loader_name)
    bunch = loader_fn()
    result = Dataset(bunch.data, bunch.target)
    if unify(dataset_var, result, trail):
        yield None


def _make_dataset_3(kind, options, dataset_var, trail, k):
    """MakeDataset/3: generate a synthetic dataset."""
    _ensure_sklearn()
    skd = _sk_datasets
    kind = str(deref(kind))
    options = _deref_params(options)
    gen_name = _DATASET_GENERATORS.get(kind)
    if gen_name is None:
        raise ValueError(f"Unknown dataset kind: {kind!r}")
    gen_fn = getattr(skd, gen_name)
    X, y = gen_fn(**options)
    result = Dataset(X, y)
    if unify(dataset_var, result, trail):
        yield None


def _load_csv_3(path, options, dataset_var, trail, k):
    """LoadCsv/3: load CSV into a Dataset term."""
    import pandas as pd
    path = str(deref(path))
    options = _deref_params(options)
    df = pd.read_csv(path)

    target_col = options.get("target")
    drop_cols = options.get("drop", [])
    na_action = options.get("na_action", "drop")
    fill_value = options.get("fill_value", 0)

    if drop_cols:
        if isinstance(drop_cols, (list, tuple)):
            df = df.drop(columns=[str(c) for c in drop_cols], errors="ignore")
        else:
            df = df.drop(columns=[str(drop_cols)], errors="ignore")

    if na_action == "drop":
        df = df.dropna()
    elif na_action == "fill":
        df = df.fillna(fill_value)

    if target_col:
        target_col = str(target_col)
        y = df[target_col].values
        X = df.drop(columns=[target_col]).values
    else:
        X = df.values
        y = None

    result = Dataset(X, y)
    if unify(dataset_var, result, trail):
        yield None


def _split_data_3(dataset, test_size, split_var, trail, k):
    """SplitData/3: single train/test split."""
    _ensure_sklearn()
    train_test_split = _sk_model_selection.train_test_split
    X, y = _unpack_dataset(dataset)
    test_size = float(deref(test_size))
    if y is not None:
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size)
    else:
        X_train, X_test = train_test_split(X, test_size=test_size)
        y_train = y_test = None
    result = Split(Dataset(X_train, y_train), Dataset(X_test, y_test))
    if unify(split_var, result, trail):
        yield None


def _split_data_4(dataset, test_size, seed, split_var, trail, k):
    """SplitData/4: train/test split with random seed."""
    _ensure_sklearn()
    train_test_split = _sk_model_selection.train_test_split
    X, y = _unpack_dataset(dataset)
    test_size = float(deref(test_size))
    seed = int(deref(seed))
    if y is not None:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=seed
        )
    else:
        X_train, X_test = train_test_split(X, test_size=test_size, random_state=seed)
        y_train = y_test = None
    result = Split(Dataset(X_train, y_train), Dataset(X_test, y_test))
    if unify(split_var, result, trail):
        yield None


def _kfold_split_3(this_generator, _proceed, _fail, _catcher, dataset, k_val, split_var, trail):
    """KFoldSplit/3: K-fold splits via backtracking."""
    _ensure_sklearn()
    KFold = _sk_model_selection.KFold
    X, y = _unpack_dataset(dataset)
    k_val = int(deref(k_val))
    kf = KFold(n_splits=k_val)
    splitter = kf.split(X, y) if y is not None else kf.split(X)
    for train_idx, test_idx in splitter:
        mark = trail.mark()
        X_train, X_test = X[train_idx], X[test_idx]
        y_train = y[train_idx] if y is not None else None
        y_test = y[test_idx] if y is not None else None
        result = Split(Dataset(X_train, y_train), Dataset(X_test, y_test))
        if unify(split_var, result, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


def _stratified_split_3(this_generator, _proceed, _fail, _catcher, dataset, k_val, split_var, trail):
    """StratifiedSplit/3: stratified K-fold via backtracking."""
    _ensure_sklearn()
    StratifiedKFold = _sk_model_selection.StratifiedKFold
    X, y = _unpack_dataset(dataset)
    k_val = int(deref(k_val))
    skf = StratifiedKFold(n_splits=k_val)
    for train_idx, test_idx in skf.split(X, y):
        mark = trail.mark()
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]
        result = Split(Dataset(X_train, y_train), Dataset(X_test, y_test))
        if unify(split_var, result, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


# ═══════════════════════════════════════════════════════════════════════════
# Layer 3: Fitting, prediction, transformation
# ═══════════════════════════════════════════════════════════════════════════

def _fit_3(est_term, dataset, fitted_var, trail, k):
    """Fit/3: fit an estimator on a Dataset term."""
    _ensure_sklearn()
    algo, params = _unpack_est(est_term)
    X, y = _unpack_dataset(dataset)
    params = _deref_params(params)

    if algo == "pipeline":
        steps = params.get("steps", [])
        model = _build_pipeline(steps)
    else:
        model = _instantiate_estimator(algo, params)

    model.fit(X, y)
    handle = _register_model(model)
    est_term_d = deref(est_term)
    result = Fitted(est_term_d, handle)
    if unify(fitted_var, result, trail):
        yield None


def _fit_4(est_term, x, y, fitted_var, trail, k):
    """Fit/4: fit with raw X and Y."""
    _ensure_sklearn()
    algo, params = _unpack_est(est_term)
    x = deref(x)
    y = deref(y)
    params = _deref_params(params)

    if algo == "pipeline":
        steps = params.get("steps", [])
        model = _build_pipeline(steps)
    else:
        model = _instantiate_estimator(algo, params)

    model.fit(x, y)
    handle = _register_model(model)
    est_term_d = deref(est_term)
    result = Fitted(est_term_d, handle)
    if unify(fitted_var, result, trail):
        yield None


def _predict_3(fitted, x, pred_var, trail, k):
    """Predict/3: predict using a fitted estimator."""
    _est, handle = _unpack_fitted(fitted)
    model = _get_model(handle)
    x = deref(x)
    predictions = model.predict(x)
    if unify(pred_var, predictions, trail):
        yield None


def _transform_3(fitted, x, result_var, trail, k):
    """Transform/3: transform data using a fitted transformer."""
    _est, handle = _unpack_fitted(fitted)
    model = _get_model(handle)
    x = deref(x)
    transformed = model.transform(x)
    if unify(result_var, transformed, trail):
        yield None


def _fit_transform_4(est_term, dataset, transformed_var, fitted_var, trail, k):
    """FitTransform/4: fit and transform in one step."""
    _ensure_sklearn()
    algo, params = _unpack_est(est_term)
    X, y = _unpack_dataset(dataset)
    params = _deref_params(params)

    if algo == "pipeline":
        steps = params.get("steps", [])
        model = _build_pipeline(steps)
    else:
        model = _instantiate_estimator(algo, params)

    transformed = model.fit_transform(X, y)
    handle = _register_model(model)
    est_term_d = deref(est_term)
    fitted_result = Fitted(est_term_d, handle)
    if unify(transformed_var, transformed, trail) and unify(fitted_var, fitted_result, trail):
        yield None


def _predict_proba_3(fitted, x, proba_var, trail, k):
    """PredictProba/3: predict class probabilities."""
    _est, handle = _unpack_fitted(fitted)
    model = _get_model(handle)
    x = deref(x)
    proba = model.predict_proba(x)
    if unify(proba_var, proba, trail):
        yield None


def _decision_function_3(fitted, x, scores_var, trail, k):
    """DecisionFunction/3: raw decision scores."""
    _est, handle = _unpack_fitted(fitted)
    model = _get_model(handle)
    x = deref(x)
    scores = model.decision_function(x)
    if unify(scores_var, scores, trail):
        yield None


# ═══════════════════════════════════════════════════════════════════════════
# Layer 4: Scoring, metrics, cross-validation
# ═══════════════════════════════════════════════════════════════════════════

def _score_3(fitted, dataset, score_var, trail, k):
    """Score/3: score with default metric."""
    _est, handle = _unpack_fitted(fitted)
    model = _get_model(handle)
    X, y = _unpack_dataset(dataset)
    score = model.score(X, y)
    if unify(score_var, score, trail):
        yield None


def _score_4(fitted, dataset, metric, score_var, trail, k):
    """Score/4: score with explicit metric."""
    _est, handle = _unpack_fitted(fitted)
    model = _get_model(handle)
    X, y = _unpack_dataset(dataset)
    metric_name = str(deref(metric))

    # For probability-based metrics, use predict_proba
    if metric_name in ("roc_auc", "log_loss"):
        y_pred = model.predict_proba(X)
        if metric_name == "roc_auc" and y_pred.shape[1] == 2:
            y_pred = y_pred[:, 1]
    else:
        y_pred = model.predict(X)

    fn, extra_kw = _get_metric_fn(metric_name)
    score = fn(y, y_pred, **extra_kw)
    if unify(score_var, score, trail):
        yield None


def _metric_4(metric_name, y_true, y_pred, score_var, trail, k):
    """Metric/4: compute a metric from ground truth and predictions."""
    _ensure_sklearn()
    metric_name = str(deref(metric_name))
    y_true = deref(y_true)
    y_pred = deref(y_pred)
    fn, extra_kw = _get_metric_fn(metric_name)
    score = fn(y_true, y_pred, **extra_kw)
    if unify(score_var, score, trail):
        yield None


def _cross_val_score_4(est_term, dataset, cv_term, scores_var, trail, k):
    """CrossValScore/4: cross-validation with default metric."""
    _ensure_sklearn()
    cross_val_score = _sk_model_selection.cross_val_score
    algo, params = _unpack_est(est_term)
    X, y = _unpack_dataset(dataset)
    params = _deref_params(params)
    cv = _make_cv(cv_term)

    if algo == "pipeline":
        steps = params.get("steps", [])
        model = _build_pipeline(steps)
    else:
        model = _instantiate_estimator(algo, params)

    scores = cross_val_score(model, X, y, cv=cv)
    if unify(scores_var, scores.tolist(), trail):
        yield None


def _cross_val_score_5(est_term, dataset, cv_term, metric, scores_var, trail, k):
    """CrossValScore/5: cross-validation with explicit metric."""
    _ensure_sklearn()
    cross_val_score = _sk_model_selection.cross_val_score
    algo, params = _unpack_est(est_term)
    X, y = _unpack_dataset(dataset)
    params = _deref_params(params)
    cv = _make_cv(cv_term)
    scoring = _metric_to_scoring(str(deref(metric)))

    if algo == "pipeline":
        steps = params.get("steps", [])
        model = _build_pipeline(steps)
    else:
        model = _instantiate_estimator(algo, params)

    scores = cross_val_score(model, X, y, cv=cv, scoring=scoring)
    # Negate back for neg_* scorers
    if scoring.startswith("neg_"):
        scores = -scores
    if unify(scores_var, scores.tolist(), trail):
        yield None


def _cross_validate_5(est_term, dataset, cv_term, metrics_list, results_var, trail, k):
    """CrossValidate/5: cross-validate with multiple metrics."""
    _ensure_sklearn()
    sk_cross_validate = _sk_model_selection.cross_validate
    algo, params = _unpack_est(est_term)
    X, y = _unpack_dataset(dataset)
    params = _deref_params(params)
    cv = _make_cv(cv_term)

    metrics_list = deref(metrics_list)
    scoring = {}
    neg_metrics = set()
    for m in metrics_list:
        m_str = str(deref(m))
        s = _metric_to_scoring(m_str)
        scoring[m_str] = s
        if s.startswith("neg_"):
            neg_metrics.add(m_str)

    if algo == "pipeline":
        steps = params.get("steps", [])
        model = _build_pipeline(steps)
    else:
        model = _instantiate_estimator(algo, params)

    cv_results = sk_cross_validate(model, X, y, cv=cv, scoring=scoring)
    results = {}
    for m_str, s in scoring.items():
        key = f"test_{m_str}"
        vals = cv_results[key]
        if m_str in neg_metrics:
            vals = -vals
        results[m_str] = vals.tolist()

    if unify(results_var, results, trail):
        yield None


def _confusion_matrix_3(y_true, y_pred, matrix_var, trail, k):
    """ConfusionMatrix/3: compute confusion matrix."""
    _ensure_sklearn()
    confusion_matrix = _sk_metrics.confusion_matrix
    y_true = deref(y_true)
    y_pred = deref(y_pred)
    matrix = confusion_matrix(y_true, y_pred)
    if unify(matrix_var, matrix, trail):
        yield None


def _classification_report_4(y_true, y_pred, classes, report_var, trail, k):
    """ClassificationReport/4: per-class precision/recall/F1/support."""
    _ensure_sklearn()
    precision_recall_fscore_support = _sk_metrics.precision_recall_fscore_support
    y_true = deref(y_true)
    y_pred = deref(y_pred)
    classes = deref(classes)
    p, r, f1, sup = precision_recall_fscore_support(y_true, y_pred, labels=classes)
    report = []
    for i, c in enumerate(classes):
        report.append((deref(c), (float(p[i]), float(r[i]), float(f1[i]), int(sup[i]))))
    if unify(report_var, report, trail):
        yield None


# ═══════════════════════════════════════════════════════════════════════════
# Layer 5: Pipelines and hyperparameter search
# ═══════════════════════════════════════════════════════════════════════════

def _pipeline_2(steps, est_var, trail, k):
    """Pipeline/2: construct a pipeline Est term."""
    steps = deref(steps)
    result = Est("pipeline", {"steps": steps})
    if unify(est_var, result, trail):
        yield None


def _pipeline_step_3(fitted_pipeline, name, step_fitted_var, trail, k):
    """PipelineStep/3: extract a named step from a fitted pipeline."""
    _est, handle = _unpack_fitted(fitted_pipeline)
    model = _get_model(handle)
    name = str(deref(name))
    step_model = model.named_steps[name]
    step_handle = _register_model(step_model)
    # Create a minimal Est for the step
    step_algo = type(step_model).__name__.lower()
    step_fitted = Fitted(Est(step_algo, {}), step_handle)
    if unify(step_fitted_var, step_fitted, trail):
        yield None


def _grid_search_5(est_term, param_grid, dataset, cv_term, best_fitted_var, trail, k):
    """GridSearch/5: exhaustive grid search."""
    _ensure_sklearn()
    GridSearchCV = _sk_model_selection.GridSearchCV
    algo, params = _unpack_est(est_term)
    X, y = _unpack_dataset(dataset)
    params = _deref_params(params)
    cv = _make_cv(cv_term)
    param_grid = _deref_params(param_grid)

    if algo == "pipeline":
        steps = params.get("steps", [])
        model = _build_pipeline(steps)
    else:
        model = _instantiate_estimator(algo, params)

    gs = GridSearchCV(model, param_grid, cv=cv, refit=True)
    gs.fit(X, y)
    handle = _register_model(gs)
    est_term_d = deref(est_term)
    result = Fitted(est_term_d, handle)
    if unify(best_fitted_var, result, trail):
        yield None


def _grid_search_6(est_term, param_grid, dataset, cv_term, metric, best_fitted_var, trail, k):
    """GridSearch/6: grid search with explicit metric."""
    _ensure_sklearn()
    GridSearchCV = _sk_model_selection.GridSearchCV
    algo, params = _unpack_est(est_term)
    X, y = _unpack_dataset(dataset)
    params = _deref_params(params)
    cv = _make_cv(cv_term)
    param_grid = _deref_params(param_grid)
    scoring = _metric_to_scoring(str(deref(metric)))

    if algo == "pipeline":
        steps = params.get("steps", [])
        model = _build_pipeline(steps)
    else:
        model = _instantiate_estimator(algo, params)

    gs = GridSearchCV(model, param_grid, cv=cv, scoring=scoring, refit=True)
    gs.fit(X, y)
    handle = _register_model(gs)
    est_term_d = deref(est_term)
    result = Fitted(est_term_d, handle)
    if unify(best_fitted_var, result, trail):
        yield None


def _random_search_6(est_term, param_dists, dataset, cv_term, n_iter, best_fitted_var, trail, k):
    """RandomSearch/6: random search over parameter distributions."""
    _ensure_sklearn()
    RandomizedSearchCV = _sk_model_selection.RandomizedSearchCV
    algo, params = _unpack_est(est_term)
    X, y = _unpack_dataset(dataset)
    params = _deref_params(params)
    cv = _make_cv(cv_term)
    param_dists = _deref_params(param_dists)
    n_iter = int(deref(n_iter))

    if algo == "pipeline":
        steps = params.get("steps", [])
        model = _build_pipeline(steps)
    else:
        model = _instantiate_estimator(algo, params)

    rs = RandomizedSearchCV(model, param_dists, n_iter=n_iter, cv=cv, refit=True)
    rs.fit(X, y)
    handle = _register_model(rs)
    est_term_d = deref(est_term)
    result = Fitted(est_term_d, handle)
    if unify(best_fitted_var, result, trail):
        yield None


def _search_results_2(fitted_search, results_var, trail, k):
    """SearchResults/2: full results from a grid/random search."""
    _est, handle = _unpack_fitted(fitted_search)
    model = _get_model(handle)
    cv_results = model.cv_results_
    results = []
    for i in range(len(cv_results["mean_test_score"])):
        params = cv_results["params"][i]
        mean = float(cv_results["mean_test_score"][i])
        std = float(cv_results["std_test_score"][i])
        results.append(("result", params, mean, std))
    if unify(results_var, results, trail):
        yield None


def _best_params_2(fitted_search, params_var, trail, k):
    """BestParams/2: best parameters from a search."""
    _est, handle = _unpack_fitted(fitted_search)
    model = _get_model(handle)
    best = dict(model.best_params_)
    if unify(params_var, best, trail):
        yield None


def _best_score_2(fitted_search, score_var, trail, k):
    """BestScore/2: best score from a search."""
    _est, handle = _unpack_fitted(fitted_search)
    model = _get_model(handle)
    score = float(model.best_score_)
    if unify(score_var, score, trail):
        yield None


# ═══════════════════════════════════════════════════════════════════════════
# Layer 6: State queries, preprocessing, serialization
# ═══════════════════════════════════════════════════════════════════════════

def _learned_3(fitted, attr, value_var, trail, k):
    """Learned/3: read a learned attribute from a fitted estimator."""
    _est, handle = _unpack_fitted(fitted)
    model = _get_model(handle)
    attr = str(deref(attr))
    # Append underscore (sklearn convention)
    sk_attr = attr + "_"
    if hasattr(model, sk_attr):
        value = getattr(model, sk_attr)
    elif hasattr(model, attr):
        value = getattr(model, attr)
    else:
        return  # fail
    if unify(value_var, value, trail):
        yield None


def _param_3(est_or_fitted, key, value_var, trail, k):
    """Param/3: read a hyperparameter from an Est or Fitted term."""
    term = deref(est_or_fitted)
    if isinstance(term, tuple) and len(term) == 3:
        tag = term[0]
        if tag == "Fitted":
            _est_inner, handle = deref(term[1]), int(deref(term[2]))
            model = _get_model(handle)
            key_str = str(deref(key))
            params = model.get_params()
            if key_str in params:
                if unify(value_var, params[key_str], trail):
                    yield None
            return
        elif tag == "Est":
            _algo, params = str(deref(term[1])), deref(term[2])
            key_str = str(deref(key))
            if isinstance(params, (dict, DictTerm)) and key_str in params:
                if unify(value_var, params[key_str], trail):
                    yield None
            return
    # fail silently


def _make_est_3(algo, params, est_var, trail, k):
    """MakeEst/3: construct an Est term, filling defaults."""
    _ensure_sklearn()
    algo = str(deref(algo))
    algo = _resolve_algorithm(algo)
    user_params = _deref_params(params)

    if algo == "pipeline":
        result = Est("pipeline", user_params)
    else:
        cls = _get_sklearn_class(algo)
        instance = cls()
        defaults = instance.get_params()
        defaults.update(user_params)
        result = Est(algo, defaults)

    if unify(est_var, result, trail):
        yield None


def _encode_labels_3(labels, encoded_var, mapping_var, trail, k):
    """EncodeLabels/3: encode symbolic labels to integers."""
    _ensure_sklearn()
    LabelEncoder = _sk_preprocessing.LabelEncoder
    labels = deref(labels)
    le = LabelEncoder()
    encoded = le.fit_transform(labels)
    mapping = {str(cls): int(i) for i, cls in enumerate(le.classes_)}
    if unify(encoded_var, encoded.tolist(), trail) and unify(mapping_var, mapping, trail):
        yield None


def _binarize_3(x, threshold, result_var, trail, k):
    """Binarize/3: threshold a matrix to 0/1."""
    _ensure_sklearn()
    binarize = _sk_preprocessing.binarize
    x = deref(x)
    threshold = float(deref(threshold))
    result = binarize(x, threshold=threshold)
    if unify(result_var, result, trail):
        yield None


def _normalize_3(x, norm, result_var, trail, k):
    """Normalize/3: row-wise normalization."""
    _ensure_sklearn()
    normalize = _sk_preprocessing.normalize
    x = deref(x)
    norm = str(deref(norm))
    result = normalize(x, norm=norm)
    if unify(result_var, result, trail):
        yield None


def _polynomial_features_3(x, degree, result_var, trail, k):
    """PolynomialFeatures/3: generate polynomial features."""
    _ensure_sklearn()
    SkPolyFeatures = _sk_preprocessing.PolynomialFeatures
    x = deref(x)
    degree = int(deref(degree))
    pf = SkPolyFeatures(degree=degree)
    result = pf.fit_transform(x)
    if unify(result_var, result, trail):
        yield None


def _save_fitted_2(fitted, path, trail, k):
    """SaveFitted/2: save a fitted estimator to disk."""
    import joblib
    _est, handle = _unpack_fitted(fitted)
    model = _get_model(handle)
    path = str(deref(path))
    joblib.dump(model, path)
    yield None


def _load_fitted_2(path, fitted_var, trail, k):
    """LoadFitted/2: load a fitted estimator from disk."""
    import joblib
    path = str(deref(path))
    model = joblib.load(path)
    handle = _register_model(model)
    # Create a minimal Est term from the loaded model
    algo = type(model).__name__.lower()
    params = model.get_params() if hasattr(model, "get_params") else {}
    result = Fitted(Est(algo, params), handle)
    if unify(fitted_var, result, trail):
        yield None


# ═══════════════════════════════════════════════════════════════════════════
# Build and export predicate objects
# ═══════════════════════════════════════════════════════════════════════════

Algorithm = ModulePredicate("Algorithm")
Algorithm._register(2, _algorithm_2)

DefaultParams = ModulePredicate("DefaultParams")
DefaultParams._register(2, simple_to_trampoline(_default_params_2))

ParamKey = ModulePredicate("ParamKey")
ParamKey._register(3, _param_key_3)

LoadDataset = ModulePredicate("LoadDataset")
LoadDataset._register(2, simple_to_trampoline(_load_dataset_2))

MakeDataset = ModulePredicate("MakeDataset")
MakeDataset._register(3, simple_to_trampoline(_make_dataset_3))

LoadCsv = ModulePredicate("LoadCsv")
LoadCsv._register(3, simple_to_trampoline(_load_csv_3))

SplitData = ModulePredicate("SplitData")
SplitData._register(3, simple_to_trampoline(_split_data_3))
SplitData._register(4, simple_to_trampoline(_split_data_4))

KFoldSplit = ModulePredicate("KFoldSplit")
KFoldSplit._register(3, _kfold_split_3)

StratifiedSplit = ModulePredicate("StratifiedSplit")
StratifiedSplit._register(3, _stratified_split_3)

Fit = ModulePredicate("Fit")
Fit._register(3, simple_to_trampoline(_fit_3))
Fit._register(4, simple_to_trampoline(_fit_4))

Predict = ModulePredicate("Predict")
Predict._register(3, simple_to_trampoline(_predict_3))

Transform = ModulePredicate("Transform")
Transform._register(3, simple_to_trampoline(_transform_3))

FitTransform = ModulePredicate("FitTransform")
FitTransform._register(4, simple_to_trampoline(_fit_transform_4))

PredictProba = ModulePredicate("PredictProba")
PredictProba._register(3, simple_to_trampoline(_predict_proba_3))

DecisionFunction = ModulePredicate("DecisionFunction")
DecisionFunction._register(3, simple_to_trampoline(_decision_function_3))

Score = ModulePredicate("Score")
Score._register(3, simple_to_trampoline(_score_3))
Score._register(4, simple_to_trampoline(_score_4))

Metric = ModulePredicate("Metric")
Metric._register(4, simple_to_trampoline(_metric_4))

CrossValScore = ModulePredicate("CrossValScore")
CrossValScore._register(4, simple_to_trampoline(_cross_val_score_4))
CrossValScore._register(5, simple_to_trampoline(_cross_val_score_5))

CrossValidate = ModulePredicate("CrossValidate")
CrossValidate._register(5, simple_to_trampoline(_cross_validate_5))

ConfusionMatrix = ModulePredicate("ConfusionMatrix")
ConfusionMatrix._register(3, simple_to_trampoline(_confusion_matrix_3))

ClassificationReport = ModulePredicate("ClassificationReport")
ClassificationReport._register(4, simple_to_trampoline(_classification_report_4))

Pipeline = ModulePredicate("Pipeline")
Pipeline._register(2, simple_to_trampoline(_pipeline_2))

PipelineStep = ModulePredicate("PipelineStep")
PipelineStep._register(3, simple_to_trampoline(_pipeline_step_3))

GridSearch = ModulePredicate("GridSearch")
GridSearch._register(5, simple_to_trampoline(_grid_search_5))
GridSearch._register(6, simple_to_trampoline(_grid_search_6))

RandomSearch = ModulePredicate("RandomSearch")
RandomSearch._register(6, simple_to_trampoline(_random_search_6))

SearchResults = ModulePredicate("SearchResults")
SearchResults._register(2, simple_to_trampoline(_search_results_2))

BestParams = ModulePredicate("BestParams")
BestParams._register(2, simple_to_trampoline(_best_params_2))

BestScore = ModulePredicate("BestScore")
BestScore._register(2, simple_to_trampoline(_best_score_2))

Learned = ModulePredicate("Learned")
Learned._register(3, simple_to_trampoline(_learned_3))

Param = ModulePredicate("Param")
Param._register(3, simple_to_trampoline(_param_3))

MakeEst = ModulePredicate("MakeEst")
MakeEst._register(3, simple_to_trampoline(_make_est_3))

EncodeLabels = ModulePredicate("EncodeLabels")
EncodeLabels._register(3, simple_to_trampoline(_encode_labels_3))

Binarize = ModulePredicate("Binarize")
Binarize._register(3, simple_to_trampoline(_binarize_3))

Normalize = ModulePredicate("Normalize")
Normalize._register(3, simple_to_trampoline(_normalize_3))

PolynomialFeatures = ModulePredicate("PolynomialFeatures")
PolynomialFeatures._register(3, simple_to_trampoline(_polynomial_features_3))

SaveFitted = ModulePredicate("SaveFitted")
SaveFitted._register(2, simple_to_trampoline(_save_fitted_2))

LoadFitted = ModulePredicate("LoadFitted")
LoadFitted._register(2, simple_to_trampoline(_load_fitted_2))
