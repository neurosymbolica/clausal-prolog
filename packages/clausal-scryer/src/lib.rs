//! PyO3 extension embedding Scryer Prolog for the Clausal project.
//!
//! Exposes `RawScryerMachine` (wraps `Machine`) and `QueryIterator`
//! (lazy iterator over query solutions) to Python.
//!
//! The ownership-transfer pattern follows Scryer's own WASM binding
//! (`src/wasm.rs`): when a query starts, the Machine is moved into a
//! self-referencing struct (via `ouroboros`) that owns it and borrows
//! it for `QueryState<'this>`.  When the iterator is dropped, the
//! Machine is returned.

use std::cell::RefCell;
use std::rc::Rc;

use ouroboros::self_referencing;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};

use scryer_prolog::Machine;
use scryer_prolog::MachineBuilder;
use scryer_prolog::{LeafAnswer, QueryState, Term as ScryerTerm};

// ── Custom exception ─────────────────────────────────────────────

pyo3::create_exception!(_scryer_ext, ScryerError, pyo3::exceptions::PyException);

// ── Machine slot ─────────────────────────────────────────────────
//
// The Machine lives in Rc<RefCell<Option<Machine>>>.  Both
// RawScryerMachine and any active QueryIterator hold an Rc clone.
// When a query starts the Machine is taken out; when it finishes
// (exhausted / dropped / close()) it is put back.

type MachineSlot = Rc<RefCell<Option<Machine>>>;

// ── RawScryerMachine ─────────────────────────────────────────────

#[pyclass(unsendable)]
struct RawScryerMachine {
    slot: MachineSlot,
}

impl RawScryerMachine {
    /// Borrow the machine mutably, returning a clear error if a query
    /// iterator currently holds it.
    fn with_machine<R>(
        &self,
        f: impl FnOnce(&mut Machine) -> R,
    ) -> PyResult<R> {
        let mut guard = self.slot.borrow_mut();
        match guard.as_mut() {
            Some(m) => Ok(f(m)),
            None => Err(ScryerError::new_err(
                "Machine is busy — a query iterator is still active. \
                 Exhaust, drop, or close() the iterator first.",
            )),
        }
    }
}

#[pymethods]
impl RawScryerMachine {
    #[new]
    fn new() -> PyResult<Self> {
        let mut machine = MachineBuilder::default().build();
        // Set double_quotes to atom so "hello" is an atom, not a char list.
        machine.consult_module_string(
            "user",
            ":- set_prolog_flag(double_quotes, atom).",
        );
        Ok(RawScryerMachine {
            slot: Rc::new(RefCell::new(Some(machine))),
        })
    }

    /// Load via consult_stream (full module system; replaces earlier clauses).
    fn consult_module_string(
        &self,
        module_name: &str,
        program: &str,
    ) -> PyResult<()> {
        self.with_machine(|m| {
            m.consult_module_string(module_name, program);
        })
    }

    /// Load via file_load (no module processing; accumulates clauses).
    fn load_module_string(
        &self,
        module_name: &str,
        program: &str,
    ) -> PyResult<()> {
        self.with_machine(|m| {
            m.load_module_string(module_name, program);
        })
    }

    /// Start a lazy query.  Returns a QueryIterator (Python iterator).
    /// While the iterator is alive the machine cannot be used for
    /// anything else.
    fn query(&self, query: String) -> PyResult<QueryIterator> {
        // Take the machine out of the slot.
        let machine = {
            let mut guard = self.slot.borrow_mut();
            guard.take().ok_or_else(|| {
                ScryerError::new_err(
                    "Machine is busy — a query iterator is still active.",
                )
            })?
        };

        // Build the self-referencing struct: owns Machine, borrows it
        // for QueryState<'this>.
        let inner = QueryIteratorInnerBuilder {
            machine,
            query_state_builder: |m: &mut Machine| m.run_query(query),
        }
        .build();

        Ok(QueryIterator {
            inner: Some(inner),
            slot: Rc::clone(&self.slot),
        })
    }
}

// ── Self-referencing query state ─────────────────────────────────

#[self_referencing]
struct QueryIteratorInner {
    machine: Machine,
    #[covariant]
    #[borrows(mut machine)]
    query_state: QueryState<'this>,
}

// ── QueryIterator — Python iterator ──────────────────────────────

#[pyclass(unsendable)]
struct QueryIterator {
    inner: Option<QueryIteratorInner>,
    slot: MachineSlot,
}

impl QueryIterator {
    /// Return the Machine to the RawScryerMachine.
    fn return_machine(&mut self) {
        if let Some(inner) = self.inner.take() {
            let heads = inner.into_heads();
            *self.slot.borrow_mut() = Some(heads.machine);
        }
    }
}

impl Drop for QueryIterator {
    fn drop(&mut self) {
        self.return_machine();
    }
}

#[pymethods]
impl QueryIterator {
    fn __iter__(slf: PyRef<'_, Self>) -> PyRef<'_, Self> {
        slf
    }

    fn __next__(&mut self, py: Python<'_>) -> PyResult<Option<PyObject>> {
        let inner = match &mut self.inner {
            Some(inner) => inner,
            None => return Ok(None), // already exhausted/closed
        };

        let mut py_result: Option<PyResult<Option<PyObject>>> = None;

        inner.with_query_state_mut(|qs| {
            py_result = Some(match qs.next() {
                Some(Ok(LeafAnswer::True)) => {
                    // Succeeded with no variable bindings → empty dict.
                    Ok(Some(PyDict::new(py).into()))
                }
                Some(Ok(LeafAnswer::False)) => {
                    // No more solutions.
                    Ok(None)
                }
                Some(Ok(LeafAnswer::LeafAnswer { bindings, .. })) => {
                    let dict = PyDict::new(py);
                    for (name, term) in &bindings {
                        match scryer_term_to_py(py, term) {
                            Ok(val) => {
                                if let Err(e) = dict.set_item(name, val) {
                                    py_result = Some(Err(e));
                                    return;
                                }
                            }
                            Err(e) => {
                                py_result = Some(Err(e));
                                return;
                            }
                        }
                    }
                    Ok(Some(dict.into()))
                }
                Some(Ok(LeafAnswer::Exception(term))) => Err(
                    ScryerError::new_err(format!("Prolog exception: {:?}", term)),
                ),
                Some(Err(term)) => Err(ScryerError::new_err(format!(
                    "Prolog error: {:?}",
                    term
                ))),
                None => {
                    // Iterator exhausted.
                    Ok(None)
                }
            });
        });

        let result = py_result.unwrap();

        // If done (None or error), return the machine immediately.
        match &result {
            Ok(None) | Err(_) => self.return_machine(),
            _ => {}
        }

        result
    }

    /// Explicitly close the iterator and return the machine.
    fn close(&mut self) {
        self.return_machine();
    }
}

// ── Term conversion ──────────────────────────────────────────────

fn scryer_term_to_py(py: Python<'_>, term: &ScryerTerm) -> PyResult<PyObject> {
    match term {
        ScryerTerm::Integer(i) => {
            // Small integers: convert directly.
            // Big integers: go via string → Python int().
            let s = i.to_string();
            if let Ok(n) = s.parse::<i64>() {
                Ok(n.into_pyobject(py)?.into_any().unbind())
            } else {
                let builtins = py.import("builtins")?;
                Ok(builtins.call_method1("int", (&s,))?.unbind())
            }
        }
        ScryerTerm::Rational(r) => {
            let frac_cls = py.import("fractions")?.getattr("Fraction")?;
            let numer = r.numerator().to_string();
            let denom = r.denominator().to_string();
            Ok(frac_cls.call1((&numer, &denom))?.unbind())
        }
        ScryerTerm::Float(f) => Ok(f.into_pyobject(py)?.into_any().unbind()),
        ScryerTerm::Atom(s) => Ok(s.into_pyobject(py)?.into_any().unbind()),
        ScryerTerm::String(s) => Ok(s.into_pyobject(py)?.into_any().unbind()),
        ScryerTerm::List(elems) => {
            let items: Vec<PyObject> = elems
                .iter()
                .map(|t| scryer_term_to_py(py, t))
                .collect::<PyResult<_>>()?;
            Ok(PyList::new(py, &items)?.into_any().unbind())
        }
        ScryerTerm::Compound(functor, args) => {
            // A compound term is the cell (functor, arg1, ..., argN).
            let mut items: Vec<PyObject> = Vec::with_capacity(args.len() + 1);
            items.push(functor.into_pyobject(py)?.into_any().unbind());
            for t in args.iter() {
                items.push(scryer_term_to_py(py, t)?);
            }
            Ok(PyTuple::new(py, &items)?.into_any().unbind())
        }
        ScryerTerm::Var(name) => {
            // Unbound / aliased variable — return the name as a string.
            Ok(name.into_pyobject(py)?.into_any().unbind())
        }
        // Non-exhaustive enum — handle future variants gracefully.
        _ => Err(ScryerError::new_err(format!(
            "Unsupported Scryer term variant: {:?}",
            term
        ))),
    }
}

// ── Module definition ────────────────────────────────────────────

#[pymodule]
fn _scryer_ext(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<RawScryerMachine>()?;
    m.add_class::<QueryIterator>()?;
    m.add("ScryerError", m.py().get_type::<ScryerError>())?;
    Ok(())
}
