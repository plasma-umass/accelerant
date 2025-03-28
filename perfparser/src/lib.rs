mod perf;

use std::{
    hash::{DefaultHasher, Hash as _, Hasher as _},
    path::Path,
};

use perf::AttributedPerf;
use pyo3::prelude::*;

#[pyclass]
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct LineLoc {
    #[pyo3(get)]
    pub path: String,
    #[pyo3(get)]
    pub line: u64,
}

#[pymethods]
impl LineLoc {
    #[new]
    fn new(path: String, line: u64) -> Self {
        Self { path, line }
    }

    fn __repr__(&self) -> String {
        format!("LineLoc({}, {})", &self.path, self.line)
    }

    fn __eq__(&self, other: &Self) -> bool {
        self == other
    }

    fn __hash__(&self) -> u64 {
        let mut hasher = DefaultHasher::new();
        self.hash(&mut hasher);
        hasher.finish()
    }
}

/// Formats the sum of two numbers as string.
#[pyfunction]
fn get_perf_data(data_path_str: &str, project_root_str: &str) -> PyResult<AttributedPerf> {
    let path = Path::new(data_path_str);
    let project_root = Path::new(project_root_str);
    let script_output = perf::run_perf_script(path)?;
    let data = perf::parse_and_attribute(&script_output[..], project_root)?;
    Ok(data)
}

/// A Python module implemented in Rust.
#[pymodule]
fn perfparser(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<LineLoc>()?;
    m.add_class::<AttributedPerf>()?;
    m.add_function(wrap_pyfunction!(get_perf_data, m)?)?;
    Ok(())
}
