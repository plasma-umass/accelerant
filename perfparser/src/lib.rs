mod perf;

use std::path::Path;

use pyo3::prelude::*;

#[pyclass]
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct LineLoc {
    #[pyo3(get)]
    pub path: String,
    #[pyo3(get)]
    pub line: u64,
}

/// Formats the sum of two numbers as string.
#[pyfunction]
fn get_perf_data(data_path_str: &str, project_root_str: &str) -> PyResult<Vec<(LineLoc, f64)>> {
    let path = Path::new(data_path_str);
    let project_root = Path::new(project_root_str);
    let script_output = perf::run_perf_script(path)?;
    let data = perf::parse_and_attribute(&script_output[..], project_root)?;
    let tabulated = data.tabulate();
    Ok(tabulated)
}

/// A Python module implemented in Rust.
#[pymodule]
fn perfparser(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<LineLoc>()?;
    m.add_function(wrap_pyfunction!(get_perf_data, m)?)?;
    Ok(())
}
