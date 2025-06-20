use std::cmp;
use std::collections::HashMap;
use std::io::{self, BufRead, BufReader};
use std::path::Path;
use std::process::Command;

use pyo3::{pyclass, pymethods};

use crate::LineLoc;

pub fn run_perf_script(data_path: &Path) -> io::Result<Vec<u8>> {
    let output = Command::new("perf")
        .args(&["script", "-Fip,srcline", "--full-source-path", "-i"])
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
    let mut lines = BufReader::new(r).lines().filter_map(Result::ok);
    let mut hit_count = HashMap::new();

    loop {
        match extract_srcline_from_perf_entry(&mut lines, is_srcline_good) {
            Err(ExtractError::Done) => break,
            Err(ExtractError::Invalid) => continue,
            Ok(loc) => *hit_count.entry(loc).or_default() += 1,
        }
    }

    let total_hits = hit_count.values().sum::<u64>();
    Ok(AttributedPerf {
        hit_count,
        total_hits,
    })
}

enum ExtractError {
    Invalid,
    Done,
}

/// Parses a `perf script` entry from the provided iterator,
/// and returns the first "good" line location from the stack trace,
/// based on the provided callback.
///
/// Meant to be run on output from `perf script -Fip,srcline --full-source-path`.
fn extract_srcline_from_perf_entry(
    mut lines: impl Iterator<Item = String>,
    is_srcline_good: impl Fn(&Path) -> Option<String>,
) -> Result<LineLoc, ExtractError> {
    loop {
        // ip/sym
        if lines.next().ok_or(ExtractError::Done)?.trim().is_empty() {
            return Err(ExtractError::Invalid);
        }
        // srcline
        let srcline_raw = lines.next().ok_or(ExtractError::Done)?;
        let srcline = srcline_raw.trim();
        if srcline.is_empty() {
            return Err(ExtractError::Invalid);
        }
        let (loc, _) = srcline.split_once(" ").unwrap_or((srcline, ""));
        if !loc.contains(':') {
            return Err(ExtractError::Invalid);
        }
        let (path, lineno_str) = loc.rsplit_once(":").ok_or(ExtractError::Invalid)?;
        let line = lineno_str.parse().map_err(|_| ExtractError::Invalid)?;
        if let Some(path) = is_srcline_good(Path::new(path)) {
            return Ok(LineLoc { path, line });
        }
    }
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
