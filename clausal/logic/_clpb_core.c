/*
 * _clpb_core.c — C-accelerated CLP(B) BDD operations.
 *
 * Provides a C extension type for BDD nodes and accelerated versions
 * of apply, restrict, count_paths, and collect_bdd_var_ids.
 *
 * BDD terminals are Python int 0 (FALSE) and 1 (TRUE).
 * Internal nodes are BDDNode objects with var_id, high, low fields.
 * Hash-consing uses per-variable unique tables (Python dicts passed
 * from the Python layer).
 *
 * The apply memo uses a C-level open-addressing hash table keyed by
 * (op, f_ptr, g_ptr) to avoid Python tuple/dict overhead on the
 * hot recursive path.
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <structmember.h>
#include <limits.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

/* ── BDD terminal singletons (cached on module init) ────────────── */

static PyObject *BDD_TRUE_OBJ;   /* Python int 1 */
static PyObject *BDD_FALSE_OBJ;  /* Python int 0 */

/* Macro for terminal checks — pointer comparison is safe because
   CPython caches small ints (-5..256) as singletons, and this is a
   CPython C extension.  BDD_TRUE/FALSE are those cached 1/0 singletons,
   so is_bdd_true/false compare by pointer only (no value fallback). */
static inline int is_bdd_true(PyObject *obj) {
    return obj == BDD_TRUE_OBJ;
}
static inline int is_bdd_false(PyObject *obj) {
    return obj == BDD_FALSE_OBJ;
}

/* ── BDDNode C extension type ───────────────────────────────────── */

typedef struct {
    PyObject_HEAD
    int       var_id;
    PyObject *high;          /* BDDNode or terminal (int 0/1) */
    PyObject *low;           /* BDDNode or terminal (int 0/1) */
    Py_hash_t cached_hash;
} BDDNodeObject;

static PyTypeObject BDDNodeType;

static inline int
is_bdd_node(PyObject *obj)
{
    return Py_TYPE(obj) == &BDDNodeType;
}

static inline int
var_id_of(PyObject *bdd)
{
    if (is_bdd_node(bdd))
        return ((BDDNodeObject *)bdd)->var_id;
    return INT_MAX;
}

/* ── BDDNode type methods ───────────────────────────────────────── */

static PyObject *
BDDNode_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    static char *kwlist[] = {"var_id", "high", "low", NULL};
    int var_id;
    PyObject *high, *low;

    if (!PyArg_ParseTupleAndKeywords(args, kwds, "iOO", kwlist,
                                      &var_id, &high, &low))
        return NULL;

    BDDNodeObject *self = (BDDNodeObject *)type->tp_alloc(type, 0);
    if (!self) return NULL;

    self->var_id = var_id;
    Py_INCREF(high);
    self->high = high;
    Py_INCREF(low);
    self->low = low;

    /* Hash: match Python's hash((var_id, id(high), id(low))) */
    PyObject *tup = Py_BuildValue("(inn)", var_id,
                                  (Py_ssize_t)high, (Py_ssize_t)low);
    if (tup) {
        self->cached_hash = PyObject_Hash(tup);
        Py_DECREF(tup);
    } else {
        self->cached_hash = (Py_hash_t)var_id * 1000003
                          ^ (Py_hash_t)((uintptr_t)high)
                          ^ (Py_hash_t)((uintptr_t)low) * 1000003;
        if (self->cached_hash == -1) self->cached_hash = -2;
        PyErr_Clear();
    }

    return (PyObject *)self;
}

static void
BDDNode_dealloc(BDDNodeObject *self)
{
    Py_XDECREF(self->high);
    Py_XDECREF(self->low);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static Py_hash_t
BDDNode_hash(BDDNodeObject *self)
{
    return self->cached_hash;
}

static PyObject *
BDDNode_richcompare(PyObject *self, PyObject *other, int op)
{
    /* Identity comparison only, matching Python BDDNode.__eq__ */
    if (op == Py_EQ)
        return PyBool_FromLong(self == other);
    if (op == Py_NE)
        return PyBool_FromLong(self != other);
    Py_RETURN_NOTIMPLEMENTED;
}

static PyObject *
BDDNode_repr(BDDNodeObject *self)
{
    return PyUnicode_FromFormat("BDDNode(%d, %R, %R)",
                                self->var_id, self->high, self->low);
}

static PyMemberDef BDDNode_members[] = {
    {"var_id", T_INT,       offsetof(BDDNodeObject, var_id), READONLY, NULL},
    {"high",   T_OBJECT_EX, offsetof(BDDNodeObject, high),   READONLY, NULL},
    {"low",    T_OBJECT_EX, offsetof(BDDNodeObject, low),    READONLY, NULL},
    {NULL}
};

/* Expose _hash for backward compat with Python BDDNode */
static PyObject *
BDDNode_get_hash(BDDNodeObject *self, void *closure)
{
    (void)closure;
    return PyLong_FromSsize_t(self->cached_hash);
}

static PyGetSetDef BDDNode_getset[] = {
    {"_hash", (getter)BDDNode_get_hash, NULL, "cached hash value", NULL},
    {NULL}
};

static PyTypeObject BDDNodeType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name        = "clausal.logic._clpb_core.BDDNode",
    .tp_basicsize   = sizeof(BDDNodeObject),
    .tp_flags       = Py_TPFLAGS_DEFAULT,
    .tp_new         = BDDNode_new,
    .tp_dealloc     = (destructor)BDDNode_dealloc,
    .tp_hash        = (hashfunc)BDDNode_hash,
    .tp_richcompare = BDDNode_richcompare,
    .tp_repr        = (reprfunc)BDDNode_repr,
    .tp_members     = BDDNode_members,
    .tp_getset      = BDDNode_getset,
    .tp_doc         = "C-accelerated BDD node: if var_id then high else low.",
};

/* ── Op enum ────────────────────────────────────────────────────── */

enum BDDOp { OP_AND, OP_OR, OP_XOR, OP_EQUIV, OP_IMPL, OP_NAND };

static int
parse_op(const char *s)
{
    if (!s) return -1;
    switch (s[0]) {
    case 'a': if (s[1] == 'n' && s[2] == 'd' && s[3] == '\0') return OP_AND; break;
    case 'o': if (s[1] == 'r' && s[2] == '\0') return OP_OR; break;
    case 'x': if (s[1] == 'o' && s[2] == 'r' && s[3] == '\0') return OP_XOR; break;
    case 'e': if (strcmp(s, "equiv") == 0) return OP_EQUIV; break;
    case 'i': if (strcmp(s, "impl") == 0) return OP_IMPL; break;
    case 'n': if (strcmp(s, "nand") == 0) return OP_NAND; break;
    }
    return -1;
}

/* ══════════════════════════════════════════════════════════════════
 * C-level memo hash table for apply
 *
 * Open-addressing with linear probing.  Keys are (op, f_ptr, g_ptr).
 * Values are strong references (INCREF on insert, DECREF on free).
 * No deletions — the table lives for a single apply() call.
 * ══════════════════════════════════════════════════════════════════ */

#define MEMO_INIT_CAP  1024    /* must be power of 2 */
#define MEMO_LOAD_NUM  7       /* grow when count * 10 > capacity * 7 */
#define MEMO_LOAD_DEN  10

typedef struct {
    PyObject *f;
    PyObject *g;
    PyObject *value;           /* NULL → empty slot */
    int       op;
} MemoSlot;

typedef struct {
    MemoSlot *slots;
    size_t    capacity;
    size_t    mask;            /* capacity - 1 */
    size_t    count;
} MemoTable;

static inline size_t
memo_hash(int op, PyObject *f, PyObject *g)
{
    /* Mix pointer bits + op into a size_t.
       Shift away low bits (alignment) for better distribution. */
    size_t h = (size_t)op;
    h = h * 0x9e3779b97f4a7c15ULL ^ ((uintptr_t)f >> 4);
    h = h * 0x517cc1b727220a95ULL ^ ((uintptr_t)g >> 4);
    return h;
}

static int
memo_init(MemoTable *t)
{
    t->capacity = MEMO_INIT_CAP;
    t->mask     = MEMO_INIT_CAP - 1;
    t->count    = 0;
    t->slots    = (MemoSlot *)calloc(MEMO_INIT_CAP, sizeof(MemoSlot));
    return t->slots ? 0 : -1;
}

static void
memo_free(MemoTable *t)
{
    if (!t->slots) return;
    for (size_t i = 0; i < t->capacity; i++)
        Py_XDECREF(t->slots[i].value);
    free(t->slots);
    t->slots = NULL;
}

static PyObject *
memo_get(MemoTable *t, int op, PyObject *f, PyObject *g)
{
    size_t idx = memo_hash(op, f, g) & t->mask;
    for (;;) {
        MemoSlot *s = &t->slots[idx];
        if (!s->value) return NULL;            /* empty → miss  */
        if (s->op == op && s->f == f && s->g == g)
            return s->value;                   /* hit (borrowed) */
        idx = (idx + 1) & t->mask;
    }
}

static int memo_grow(MemoTable *t);

static int
memo_set(MemoTable *t, int op, PyObject *f, PyObject *g, PyObject *value)
{
    if (t->count * MEMO_LOAD_DEN > t->capacity * MEMO_LOAD_NUM) {
        if (memo_grow(t) < 0) return -1;
    }
    size_t idx = memo_hash(op, f, g) & t->mask;
    for (;;) {
        MemoSlot *s = &t->slots[idx];
        if (!s->value) {
            s->op = op;
            s->f  = f;
            s->g  = g;
            Py_INCREF(value);
            s->value = value;
            t->count++;
            return 0;
        }
        /* Duplicate key — shouldn't happen in BDD apply, but handle it */
        if (s->op == op && s->f == f && s->g == g) {
            Py_DECREF(s->value);
            Py_INCREF(value);
            s->value = value;
            return 0;
        }
        idx = (idx + 1) & t->mask;
    }
}

static int
memo_grow(MemoTable *t)
{
    size_t new_cap  = t->capacity * 2;
    size_t new_mask = new_cap - 1;
    MemoSlot *new_slots = (MemoSlot *)calloc(new_cap, sizeof(MemoSlot));
    if (!new_slots) return -1;

    for (size_t i = 0; i < t->capacity; i++) {
        MemoSlot *old = &t->slots[i];
        if (!old->value) continue;
        size_t idx = memo_hash(old->op, old->f, old->g) & new_mask;
        while (new_slots[idx].value)
            idx = (idx + 1) & new_mask;
        new_slots[idx] = *old;                 /* move (transfers ref) */
    }
    free(t->slots);
    t->slots    = new_slots;
    t->capacity = new_cap;
    t->mask     = new_mask;
    return 0;
}

/* ── Internal: hash-consed make_node ────────────────────────────── */

/*
 * Create or retrieve a BDD node from the per-variable unique table.
 *
 * unique_tables : dict { id(Var) -> dict { (id(hi), id(lo)) -> node } }
 * id_to_var     : dict { var_id  -> Var }
 *
 * Returns new reference.  NULL on error.
 */
static PyObject *
c_make_node(int var_id, PyObject *high, PyObject *low,
            PyObject *unique_tables, PyObject *id_to_var)
{
    /* Reduction rule: if children identical, skip this level */
    if (high == low) {
        Py_INCREF(low);
        return low;
    }

    /* Look up the Var object for this var_id.
     *
     * OWNED, not borrowed, and that is a correctness requirement rather
     * than tidiness (2026-09-11).  Everything below allocates -- and an
     * allocation can run the collector, which can run a weakref finalizer,
     * and `clpb._cleanup_trail_allocs` is exactly such a finalizer: it pops
     * `_id_to_var[idx]` and `_unique_tables[id(var)]` when a Trail dies.
     * Held borrowed, `var` could be freed underneath this call and `tbl`
     * could be freed before it is next read -- a dangling dict, then a
     * segfault inside PyDict_GetItem.  Owning both for the duration also
     * pins the Var's ADDRESS, which is what the unique table is keyed on,
     * so no other variable can alias this table mid-call.
     */
    PyObject *vid_key = PyLong_FromLong(var_id);
    if (!vid_key) return NULL;

    PyObject *var = PyDict_GetItem(id_to_var, vid_key);   /* borrowed */
    Py_XINCREF(var);                                      /* now owned */
    Py_DECREF(vid_key);

    if (!var) {
        /* No var found — create node without unique-table entry */
        PyObject *args = Py_BuildValue("(iOO)", var_id, high, low);
        if (!args) return NULL;
        PyObject *node = BDDNode_new(&BDDNodeType, args, NULL);
        Py_DECREF(args);
        return node;
    }

    /* ── Get or create the per-variable unique table ─────────── */
    PyObject *tbl = NULL, *ukey = NULL, *args = NULL, *result = NULL;

    PyObject *tbl_key = PyLong_FromSsize_t((Py_ssize_t)var);
    if (!tbl_key) goto done;

    tbl = PyDict_GetItem(unique_tables, tbl_key);         /* borrowed */
    Py_XINCREF(tbl);                                      /* now owned */
    if (!tbl) {
        tbl = PyDict_New();
        if (!tbl) { Py_DECREF(tbl_key); goto done; }
        if (PyDict_SetItem(unique_tables, tbl_key, tbl) < 0) {
            Py_CLEAR(tbl);
            Py_DECREF(tbl_key);
            goto done;
        }
        /* keep our own reference; the dict has its own */
    }
    Py_DECREF(tbl_key);

    /* ── Unique-table lookup: (id(high), id(low)) ───────────── */
    ukey = Py_BuildValue("(nn)", (Py_ssize_t)high, (Py_ssize_t)low);
    if (!ukey) goto done;

    PyObject *existing = PyDict_GetItem(tbl, ukey);   /* borrowed */
    if (existing) {
        Py_INCREF(existing);
        result = existing;
        goto done;
    }

    /* ── Create new node and insert ─────────────────────────── */
    args = Py_BuildValue("(iOO)", var_id, high, low);
    if (!args) goto done;
    result = BDDNode_new(&BDDNodeType, args, NULL);
    Py_CLEAR(args);
    if (!result) goto done;

    if (PyDict_SetItem(tbl, ukey, result) < 0)
        Py_CLEAR(result);

done:
    Py_XDECREF(args);
    Py_XDECREF(ukey);
    Py_XDECREF(tbl);
    Py_DECREF(var);
    return result;        /* new reference, or NULL with an exception set */
}

/* ── Terminal cases for apply ───────────────────────────────────── */

/*
 * Returns new reference to result if terminal, or NULL if non-terminal
 * (not an error — caller must recurse).  Actual errors set PyErr.
 */
static PyObject *
apply_terminal(int op, PyObject *f, PyObject *g)
{
    int f_term = !is_bdd_node(f);
    int g_term = !is_bdd_node(g);

    switch (op) {
    case OP_AND:
        if (is_bdd_false(f) || is_bdd_false(g))
            { Py_INCREF(BDD_FALSE_OBJ); return BDD_FALSE_OBJ; }
        if (is_bdd_true(f))  { Py_INCREF(g); return g; }
        if (is_bdd_true(g))  { Py_INCREF(f); return f; }
        break;

    case OP_OR:
        if (is_bdd_true(f) || is_bdd_true(g))
            { Py_INCREF(BDD_TRUE_OBJ); return BDD_TRUE_OBJ; }
        if (is_bdd_false(f)) { Py_INCREF(g); return g; }
        if (is_bdd_false(g)) { Py_INCREF(f); return f; }
        break;

    case OP_XOR:
        if (f_term && g_term) {
            PyObject *r = (f != g) ? BDD_TRUE_OBJ : BDD_FALSE_OBJ;
            Py_INCREF(r); return r;
        }
        if (is_bdd_false(f)) { Py_INCREF(g); return g; }
        if (is_bdd_false(g)) { Py_INCREF(f); return f; }
        break;

    case OP_EQUIV:
        if (f_term && g_term) {
            PyObject *r = (f == g) ? BDD_TRUE_OBJ : BDD_FALSE_OBJ;
            Py_INCREF(r); return r;
        }
        if (is_bdd_true(f))  { Py_INCREF(g); return g; }
        if (is_bdd_true(g))  { Py_INCREF(f); return f; }
        break;

    case OP_IMPL:
        if (is_bdd_false(f) || is_bdd_true(g))
            { Py_INCREF(BDD_TRUE_OBJ); return BDD_TRUE_OBJ; }
        if (is_bdd_true(f))  { Py_INCREF(g); return g; }
        if (is_bdd_false(g) && f_term) {
            PyObject *r = is_bdd_false(f) ? BDD_TRUE_OBJ : BDD_FALSE_OBJ;
            Py_INCREF(r); return r;
        }
        break;

    case OP_NAND:
        if (is_bdd_false(f) || is_bdd_false(g))
            { Py_INCREF(BDD_TRUE_OBJ); return BDD_TRUE_OBJ; }
        if (f_term && g_term)
            { Py_INCREF(BDD_FALSE_OBJ); return BDD_FALSE_OBJ; }
        break;
    }
    return NULL;           /* not terminal — caller recurses */
}

/* ── Iterative apply (uses C memo table) ────────────────────────────
 *
 * An explicit heap work-stack replaces C-stack recursion so a deep BDD (e.g.
 * a 100k-level chain) completes like the Python fallback instead of
 * overflowing the C stack and segfaulting (A07-F007).  Standard memoised
 * post-order DFS: a (f, g) node reduces only once both cofactor results are in
 * the memo; otherwise the missing cofactors are pushed above it.  All (f, g)
 * pairs are sub-nodes of the roots, hence borrowed refs kept alive by the
 * caller — the stack stores no owned references. */

typedef struct { PyObject *f; PyObject *g; } ApplyPair;

static PyObject *
c_apply_rec(int op, PyObject *root_f, PyObject *root_g,
            MemoTable *memo, PyObject *unique_tables, PyObject *id_to_var)
{
    PyObject *cached = memo_get(memo, op, root_f, root_g);
    if (cached) { Py_INCREF(cached); return cached; }

    Py_ssize_t cap = 4096, top = 0;
    ApplyPair *stack = (ApplyPair *)PyMem_Malloc((size_t)cap * sizeof(ApplyPair));
    if (!stack) { PyErr_NoMemory(); return NULL; }
    stack[top].f = root_f; stack[top].g = root_g; top++;

    while (top > 0) {
        PyObject *f = stack[top - 1].f;
        PyObject *g = stack[top - 1].g;

        /* Already computed (shared node reached via two parents)? */
        if (memo_get(memo, op, f, g)) { top--; continue; }

        /* Terminal? */
        PyObject *term = apply_terminal(op, f, g);
        if (term) {
            int rc = memo_set(memo, op, f, g, term);
            Py_DECREF(term);
            if (rc < 0) { PyMem_Free(stack); return NULL; }
            top--;
            continue;
        }

        /* Shannon expansion on the lowest var_id. */
        int fid = var_id_of(f);
        int gid = var_id_of(g);
        int min_id = (fid < gid) ? fid : gid;

        PyObject *fh, *fl, *gh, *gl;
        if (is_bdd_node(f) && ((BDDNodeObject *)f)->var_id == min_id) {
            fh = ((BDDNodeObject *)f)->high; fl = ((BDDNodeObject *)f)->low;
        } else { fh = f; fl = f; }
        if (is_bdd_node(g) && ((BDDNodeObject *)g)->var_id == min_id) {
            gh = ((BDDNodeObject *)g)->high; gl = ((BDDNodeObject *)g)->low;
        } else { gh = g; gl = g; }

        PyObject *ch = memo_get(memo, op, fh, gh);  /* borrowed */
        PyObject *cl = memo_get(memo, op, fl, gl);  /* borrowed */
        if (ch && cl) {
            PyObject *result = c_make_node(min_id, ch, cl,
                                           unique_tables, id_to_var);
            if (!result) { PyMem_Free(stack); return NULL; }
            int rc = memo_set(memo, op, f, g, result);
            Py_DECREF(result);
            if (rc < 0) { PyMem_Free(stack); return NULL; }
            top--;
        } else {
            if (top + 2 > cap) {
                Py_ssize_t ncap = cap * 2;
                ApplyPair *ns = (ApplyPair *)PyMem_Realloc(
                    stack, (size_t)ncap * sizeof(ApplyPair));
                if (!ns) { PyMem_Free(stack); PyErr_NoMemory(); return NULL; }
                stack = ns; cap = ncap;
            }
            /* Leave (f, g) in place; push the missing cofactors above it. */
            if (!cl) { stack[top].f = fl; stack[top].g = gl; top++; }
            if (!ch) { stack[top].f = fh; stack[top].g = gh; top++; }
        }
    }

    PyMem_Free(stack);
    PyObject *out = memo_get(memo, op, root_f, root_g);
    if (!out) {
        PyErr_SetString(PyExc_RuntimeError, "c_apply: root not computed");
        return NULL;
    }
    Py_INCREF(out);
    return out;
}

/* ── Recursive restrict ─────────────────────────────────────────── */

static PyObject *
c_restrict_rec(PyObject *bdd, int var_id, int value,
               PyObject *unique_tables, PyObject *id_to_var, PyObject *memo)
{
    if (!is_bdd_node(bdd)) {
        Py_INCREF(bdd);
        return bdd;
    }

    BDDNodeObject *node = (BDDNodeObject *)bdd;

    if (node->var_id == var_id) {
        PyObject *r = value ? node->high : node->low;
        Py_INCREF(r);
        return r;
    }
    if (node->var_id > var_id) {
        Py_INCREF(bdd);
        return bdd;
    }

    /* Memoize by node identity so a hash-consed DAG is restricted in
       O(nodes), not O(paths).  Without it, _propagate_forced's per-variable
       restrict sweep is O(vars x 2^vars) — the dominant cost of the
       exponential-sat blowup (A07-F001).  var_id/value are fixed per call, so
       the node pointer alone keys the result. */
    PyObject *memo_key = PyLong_FromVoidPtr(bdd);
    if (!memo_key) return NULL;
    PyObject *cached = PyDict_GetItemWithError(memo, memo_key);
    if (cached) { Py_INCREF(cached); Py_DECREF(memo_key); return cached; }
    if (PyErr_Occurred()) { Py_DECREF(memo_key); return NULL; }

    /* Guard the C-stack recursion (A07-F007). */
    if (Py_EnterRecursiveCall(" in CLP(B) restrict")) {
        Py_DECREF(memo_key);
        return NULL;
    }

    PyObject *high = c_restrict_rec(node->high, var_id, value,
                                    unique_tables, id_to_var, memo);
    if (!high) { Py_LeaveRecursiveCall(); Py_DECREF(memo_key); return NULL; }

    PyObject *low = c_restrict_rec(node->low, var_id, value,
                                   unique_tables, id_to_var, memo);
    if (!low) { Py_LeaveRecursiveCall(); Py_DECREF(high); Py_DECREF(memo_key); return NULL; }

    /* Reduction + hash-consing via make_node */
    PyObject *result = c_make_node(node->var_id, high, low,
                                   unique_tables, id_to_var);
    Py_DECREF(high);
    Py_DECREF(low);
    Py_LeaveRecursiveCall();
    if (result && PyDict_SetItem(memo, memo_key, result) < 0) {
        Py_DECREF(result);
        Py_DECREF(memo_key);
        return NULL;
    }
    Py_DECREF(memo_key);
    return result;         /* may be NULL on error */
}

/* ══════════════════════════════════════════════════════════════════
 * count_paths — two implementations:
 *   Fast path (n_vars < 63): uses C long long arithmetic
 *   Big path  (n_vars >= 63): uses Python arbitrary-precision ints
 * ══════════════════════════════════════════════════════════════════ */

/* ── Fast path: long long ────────────────────────────────────────── */

static long long
c_count_paths_fast(PyObject *bdd, PyObject *level_map, int n_vars,
                   PyObject *memo, int current_level)
{
    if (is_bdd_true(bdd)) {
        int remaining = n_vars - current_level;
        return (remaining > 0) ? (1LL << remaining) : 1;
    }
    if (is_bdd_false(bdd))
        return 0;
    if (!is_bdd_node(bdd))
        return 0;

    PyObject *memo_key = Py_BuildValue("(ni)", (Py_ssize_t)bdd, current_level);
    if (!memo_key) return -1;

    PyObject *cached = PyDict_GetItem(memo, memo_key);
    if (cached) {
        long long val = PyLong_AsLongLong(cached);
        Py_DECREF(memo_key);
        return val;
    }

    BDDNodeObject *node = (BDDNodeObject *)bdd;

    PyObject *vid_key = PyLong_FromLong(node->var_id);
    if (!vid_key) { Py_DECREF(memo_key); return -1; }

    PyObject *level_obj = PyDict_GetItem(level_map, vid_key);
    Py_DECREF(vid_key);
    int node_level = level_obj ? (int)PyLong_AsLong(level_obj) : current_level;

    int skipped = node_level - current_level;
    long long multiplier = (skipped > 0) ? (1LL << skipped) : 1;

    long long hi_cnt = c_count_paths_fast(node->high, level_map, n_vars,
                                          memo, node_level + 1);
    if (hi_cnt < 0 && PyErr_Occurred()) { Py_DECREF(memo_key); return -1; }

    long long lo_cnt = c_count_paths_fast(node->low, level_map, n_vars,
                                          memo, node_level + 1);
    if (lo_cnt < 0 && PyErr_Occurred()) { Py_DECREF(memo_key); return -1; }

    long long result = multiplier * (hi_cnt + lo_cnt);

    PyObject *result_obj = PyLong_FromLongLong(result);
    if (result_obj) {
        PyDict_SetItem(memo, memo_key, result_obj);
        Py_DECREF(result_obj);
    }
    Py_DECREF(memo_key);
    return result;
}

/* ── Big path: arbitrary-precision PyLong ─────────────────────────── */

/* Helper: compute 1 << shift as a PyLong (new ref) */
static PyObject *
pylong_1_lshift(int shift)
{
    if (shift <= 0) return PyLong_FromLong(1);
    PyObject *one = PyLong_FromLong(1);
    if (!one) return NULL;
    PyObject *sh = PyLong_FromLong(shift);
    if (!sh) { Py_DECREF(one); return NULL; }
    PyObject *result = PyNumber_Lshift(one, sh);
    Py_DECREF(one);
    Py_DECREF(sh);
    return result;
}

static PyObject *
c_count_paths_big(PyObject *bdd, PyObject *level_map, int n_vars,
                  PyObject *memo, int current_level)
{
    if (is_bdd_true(bdd)) {
        int remaining = n_vars - current_level;
        return pylong_1_lshift(remaining);
    }
    if (is_bdd_false(bdd))
        return PyLong_FromLong(0);
    if (!is_bdd_node(bdd))
        return PyLong_FromLong(0);

    /* Memo lookup */
    PyObject *memo_key = Py_BuildValue("(ni)", (Py_ssize_t)bdd, current_level);
    if (!memo_key) return NULL;

    PyObject *cached = PyDict_GetItem(memo, memo_key);
    if (cached) {
        Py_DECREF(memo_key);
        Py_INCREF(cached);
        return cached;
    }

    BDDNodeObject *node = (BDDNodeObject *)bdd;

    PyObject *vid_key = PyLong_FromLong(node->var_id);
    if (!vid_key) { Py_DECREF(memo_key); return NULL; }

    PyObject *level_obj = PyDict_GetItem(level_map, vid_key);
    Py_DECREF(vid_key);
    int node_level = level_obj ? (int)PyLong_AsLong(level_obj) : current_level;

    int skipped = node_level - current_level;

    PyObject *hi_cnt = c_count_paths_big(node->high, level_map, n_vars,
                                         memo, node_level + 1);
    if (!hi_cnt) { Py_DECREF(memo_key); return NULL; }

    PyObject *lo_cnt = c_count_paths_big(node->low, level_map, n_vars,
                                         memo, node_level + 1);
    if (!lo_cnt) { Py_DECREF(memo_key); Py_DECREF(hi_cnt); return NULL; }

    /* sum = hi_cnt + lo_cnt */
    PyObject *sum = PyNumber_Add(hi_cnt, lo_cnt);
    Py_DECREF(hi_cnt);
    Py_DECREF(lo_cnt);
    if (!sum) { Py_DECREF(memo_key); return NULL; }

    /* result = (1 << skipped) * sum */
    PyObject *result;
    if (skipped > 0) {
        PyObject *mult = pylong_1_lshift(skipped);
        if (!mult) { Py_DECREF(sum); Py_DECREF(memo_key); return NULL; }
        result = PyNumber_Multiply(mult, sum);
        Py_DECREF(mult);
        Py_DECREF(sum);
        if (!result) { Py_DECREF(memo_key); return NULL; }
    } else {
        result = sum;
    }

    PyDict_SetItem(memo, memo_key, result);
    Py_DECREF(memo_key);
    return result;
}

/* ── Recursive collect_bdd_var_ids ──────────────────────────────── */

static int
c_collect_ids_rec(PyObject *bdd, PyObject *result_set, PyObject *seen)
{
    if (!is_bdd_node(bdd))
        return 0;

    /* A BDD is a hash-consed DAG: shared sub-nodes are the same object, so a
       visited-set keyed by node pointer keeps this O(nodes) rather than
       O(paths) — without it an n-var XOR chain (2n-1 nodes, 2^n paths) makes
       sat/sat_count exponential (A07-F001). */
    PyObject *nid = PyLong_FromVoidPtr(bdd);
    if (!nid) return -1;
    int contains = PySet_Contains(seen, nid);
    if (contains < 0) { Py_DECREF(nid); return -1; }
    if (contains) { Py_DECREF(nid); return 0; }
    if (PySet_Add(seen, nid) < 0) { Py_DECREF(nid); return -1; }
    Py_DECREF(nid);

    BDDNodeObject *node = (BDDNodeObject *)bdd;
    PyObject *vid = PyLong_FromLong(node->var_id);
    if (!vid) return -1;

    if (PySet_Add(result_set, vid) < 0) { Py_DECREF(vid); return -1; }
    Py_DECREF(vid);

    /* Guard the C-stack recursion: the visited set caps total work but not the
       descent depth, so a deep chain BDD would still overflow (A07-F007). */
    if (Py_EnterRecursiveCall(" in CLP(B) collect_var_ids"))
        return -1;
    if (c_collect_ids_rec(node->high, result_set, seen) < 0) {
        Py_LeaveRecursiveCall();
        return -1;
    }
    if (c_collect_ids_rec(node->low, result_set, seen) < 0) {
        Py_LeaveRecursiveCall();
        return -1;
    }
    Py_LeaveRecursiveCall();
    return 0;
}

/* ================================================================
 * Python-facing wrapper functions
 * ================================================================ */

/*
 * c_apply(op_str, f, g, unique_tables, id_to_var) -> BDD
 */
static PyObject *
py_apply(PyObject *self, PyObject *args)
{
    (void)self;
    const char *op_str;
    PyObject *f, *g, *unique_tables, *id_to_var;

    if (!PyArg_ParseTuple(args, "sOOO!O!",
                          &op_str, &f, &g,
                          &PyDict_Type, &unique_tables,
                          &PyDict_Type, &id_to_var))
        return NULL;

    int op = parse_op(op_str);
    if (op < 0) {
        PyErr_Format(PyExc_ValueError,
                     "unknown BDD operation: '%s'", op_str);
        return NULL;
    }

    MemoTable memo;
    if (memo_init(&memo) < 0) {
        PyErr_NoMemory();
        return NULL;
    }

    PyObject *result = c_apply_rec(op, f, g, &memo, unique_tables, id_to_var);
    memo_free(&memo);
    return result;
}

/*
 * c_restrict(bdd, var_id, value, unique_tables, id_to_var) -> BDD
 */
static PyObject *
py_restrict(PyObject *self, PyObject *args)
{
    (void)self;
    PyObject *bdd, *unique_tables, *id_to_var;
    int var_id, value;

    if (!PyArg_ParseTuple(args, "OiiO!O!",
                          &bdd, &var_id, &value,
                          &PyDict_Type, &unique_tables,
                          &PyDict_Type, &id_to_var))
        return NULL;

    PyObject *memo = PyDict_New();
    if (!memo) return NULL;
    PyObject *result = c_restrict_rec(bdd, var_id, value,
                                      unique_tables, id_to_var, memo);
    Py_DECREF(memo);
    return result;
}

/*
 * c_count_paths(bdd, level_map, n_vars) -> int
 *
 * Dispatches to fast (long long) path for n_vars < 63, or
 * big (PyLong) path for n_vars >= 63 to avoid overflow.
 */
static PyObject *
py_count_paths(PyObject *self, PyObject *args)
{
    (void)self;
    PyObject *bdd, *level_map;
    int n_vars;

    if (!PyArg_ParseTuple(args, "OO!i",
                          &bdd, &PyDict_Type, &level_map, &n_vars))
        return NULL;

    PyObject *memo = PyDict_New();
    if (!memo) return NULL;

    if (n_vars < 63) {
        long long result = c_count_paths_fast(bdd, level_map, n_vars, memo, 0);
        Py_DECREF(memo);
        if (result < 0 && PyErr_Occurred())
            return NULL;
        return PyLong_FromLongLong(result);
    } else {
        PyObject *result = c_count_paths_big(bdd, level_map, n_vars, memo, 0);
        Py_DECREF(memo);
        return result;
    }
}

/*
 * c_collect_bdd_var_ids(bdd, result_set) -> None
 *
 * Adds all variable IDs found in the BDD to result_set.
 */
static PyObject *
py_collect_bdd_var_ids(PyObject *self, PyObject *args)
{
    (void)self;
    PyObject *bdd, *result_set;

    if (!PyArg_ParseTuple(args, "OO!", &bdd, &PySet_Type, &result_set))
        return NULL;

    PyObject *seen = PySet_New(NULL);
    if (!seen) return NULL;
    int rc = c_collect_ids_rec(bdd, result_set, seen);
    Py_DECREF(seen);
    if (rc < 0)
        return NULL;

    Py_RETURN_NONE;
}

/* ── Module definition ──────────────────────────────────────────── */

static PyMethodDef module_methods[] = {
    {"c_apply",              py_apply,              METH_VARARGS,
     "apply(op, f, g, unique_tables, id_to_var) -> BDD"},
    {"c_restrict",           py_restrict,           METH_VARARGS,
     "restrict(bdd, var_id, value, unique_tables, id_to_var) -> BDD"},
    {"c_count_paths",        py_count_paths,        METH_VARARGS,
     "count_paths(bdd, level_map, n_vars) -> int"},
    {"c_collect_bdd_var_ids", py_collect_bdd_var_ids, METH_VARARGS,
     "collect_bdd_var_ids(bdd, result_set) -> None"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef clpb_core_module = {
    PyModuleDef_HEAD_INIT,
    "_clpb_core",
    "C-accelerated CLP(B) BDD operations.\n",
    -1,
    module_methods
};

PyMODINIT_FUNC
PyInit__clpb_core(void)
{
    if (PyType_Ready(&BDDNodeType) < 0)
        return NULL;

    PyObject *m = PyModule_Create(&clpb_core_module);
    if (!m) return NULL;

    Py_INCREF(&BDDNodeType);
    if (PyModule_AddObject(m, "BDDNode", (PyObject *)&BDDNodeType) < 0) {
        Py_DECREF(&BDDNodeType);
        Py_DECREF(m);
        return NULL;
    }

    /* Cache the singleton ints 0 and 1 for fast pointer comparison.
       CPython guarantees small ints (-5..256) are cached singletons. */
    BDD_TRUE_OBJ  = PyLong_FromLong(1);
    BDD_FALSE_OBJ = PyLong_FromLong(0);

    return m;
}
