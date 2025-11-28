use std::cmp;
use std::collections::HashMap;
use std::io;
use std::path::Path;
use std::process::Command;

use perfparser::Parser;
use pyo3::{pyclass, pymethods};

use crate::LineLoc;

pub fn run_perf_script(data_path: &Path) -> io::Result<Vec<u8>> {
    let output = Command::new("perf")
        .args(&["script", "-F+srcline", "--full-source-path", "-i"])
        .arg(data_path)
        .output()?;
    if output.status.success() {
        Ok(output.stdout)
    } else {
        Err(io::Error::other(String::from_utf8_lossy(&output.stderr)))
    }
}

pub fn parse_and_attribute<R: io::Read>(r: R, project_root: &Path) -> io::Result<AttributedPerf> {
    let is_srcline_good = |path: &Path| {
        path.strip_prefix(project_root)
            .ok()
            .and_then(Path::to_str)
            .map(str::to_owned)
    };
    let parser = Parser::new(r);
    let mut hit_count = HashMap::new();

    for event in parser {
        let lineloc = event
            .stack
            .iter()
            .filter_map(|frame| frame.srcline.as_ref())
            .find_map(|srcline| {
                is_srcline_good(Path::new(&srcline.path)).map(|path| LineLoc {
                    path,
                    line: srcline.line as u64,
                })
            });
        if let Some(lineloc) = lineloc {
            *hit_count.entry(lineloc).or_insert(0) += event.period.unwrap_or(1) as u64;
        }
    }

    let total_hits = hit_count.values().sum::<u64>();
    Ok(AttributedPerf {
        hit_count,
        total_hits,
    })
}

#[pyclass]
#[derive(Debug)]
pub struct AttributedPerf {
    #[pyo3(get)]
    pub hit_count: HashMap<LineLoc, u64>,
    #[pyo3(get)]
    pub total_hits: u64,
}

#[pymethods]
impl AttributedPerf {
    pub fn tabulate(&self) -> Vec<(LineLoc, f64)> {
        let total_hits = self.total_hits as f64;
        let mut sorted: Vec<_> = self
            .hit_count
            .iter()
            .map(|(loc, hits)| (loc.clone(), *hits))
            .collect();
        sorted.sort_by_key(|&(_, hits)| cmp::Reverse(hits));
        sorted
            .into_iter()
            .map(|(loc, hits)| (loc, hits as f64 / total_hits))
            .collect()
    }
}
