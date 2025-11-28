// TODO: make this more generic rather than specific to accelerant's use case

use std::io::{self, BufRead, BufReader};
use std::mem;

#[derive(Debug, Clone, Default)]
pub struct Event {
    pub period: Option<usize>,
    pub kind: String,
    pub stack: Vec<StackFrame>,
}

#[derive(Debug, Clone, Default)]
pub struct StackFrame {
    pub funcname: String,
    pub srcline: Option<SourceLine>,
}

#[derive(Debug, Clone)]
pub struct SourceLine {
    pub path: String,
    pub line: usize,
}

const SPECIAL_UNKNOWN: &str = "[unknown]";

pub struct Parser<R> {
    src: BufReader<R>,
    state: ParserState,
    cur_event: Event,
}

impl<R: io::Read> Parser<R> {
    pub fn new(reader: R) -> Self {
        Self {
            src: BufReader::new(reader),
            state: ParserState::Start,
            cur_event: Event::default(),
        }
    }

    fn parse_event_line(&mut self, line: &str) -> Result<(), ()> {
        let mut chunks = line.trim().split(':').filter(|s| !s.is_empty());
        let _ = chunks.next();
        let Some(period_and_kind) = chunks.next() else {
            return Err(());
        };
        let Some((period_str, kind)) = period_and_kind.trim().split_once(' ') else {
            return Err(());
        };
        self.cur_event.period = period_str.parse().ok();
        self.cur_event.kind = kind.to_owned();

        if let Some(single_stack_line) = chunks.next() {
            // Combined event/stack line
            if self.parse_stack_line(single_stack_line).is_err() {
                self.state = ParserState::AfterEventLine;
                return Err(());
            }
            self.state = ParserState::AfterCombinedLine;
        } else {
            self.state = ParserState::AfterEventLine;
        }
        Ok(())
    }

    fn parse_stack_line(&mut self, line: &str) -> Result<(), ()> {
        let Some((_addr, rest)) = line.trim().split_once(' ') else {
            return Err(());
        };
        let (funcname, module) = rest
            .rsplit_once(" (")
            .and_then(|(f, m)| m.strip_suffix(')').map(|m| (f, m)))
            .unwrap_or((rest, ""));
        let (funcname, _offset) = funcname.rsplit_once('+').unwrap_or((funcname, ""));

        self.cur_event.stack.push(StackFrame {
            funcname: funcname.to_owned(),
            srcline: None,
        });
        if funcname != SPECIAL_UNKNOWN || module != SPECIAL_UNKNOWN {
            self.state = ParserState::AfterStackLine;
        }
        Ok(())
    }

    fn parse_src_line(&mut self, line: &str) -> Result<(), ()> {
        let line = line.trim();
        let (srcinfo, _module) = line.rsplit_once(' ').unwrap_or((line, ""));
        let Some((path, lineno_str)) = srcinfo.rsplit_once(':') else {
            self.state = ParserState::AfterSrcLine;
            return Ok(());
        };
        let Ok(lineno) = lineno_str.parse::<usize>() else {
            return Err(());
        };
        if let Some(last_frame) = self.cur_event.stack.last_mut() {
            last_frame.srcline = Some(SourceLine {
                path: path.to_owned(),
                line: lineno,
            });
        }
        self.state = ParserState::AfterSrcLine;
        Ok(())
    }
}

impl<R: io::Read> Iterator for Parser<R> {
    type Item = Event;

    fn next(&mut self) -> Option<Self::Item> {
        let mut line = String::new();
        loop {
            line.clear();
            let bytes_read = self.src.read_line(&mut line).ok()?;
            if bytes_read == 0 {
                // EOF
                if self.state != ParserState::Start {
                    let event = mem::take(&mut self.cur_event);
                    self.state = ParserState::Start;
                    return Some(event);
                } else {
                    return None;
                }
            }

            let line = line.trim();
            if line.is_empty() {
                self.state = ParserState::Start;
                return Some(mem::take(&mut self.cur_event));
            }

            let result = match self.state {
                ParserState::Start => self.parse_event_line(line),
                ParserState::AfterEventLine => self.parse_stack_line(line),
                ParserState::AfterCombinedLine => {
                    maybe_handle_weird_line(line, self.parse_src_line(line));
                    self.state = ParserState::Start;
                    return Some(mem::take(&mut self.cur_event));
                }
                ParserState::AfterStackLine => self.parse_src_line(line),
                ParserState::AfterSrcLine => self.parse_stack_line(line),
            };
            maybe_handle_weird_line(line, result);
        }
    }
}

fn maybe_handle_weird_line(line: &str, result: Result<(), ()>) {
    if result.is_err() {
        // FIXME: use logging infrastructure instead
        eprintln!("Weird line: {}", line);
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ParserState {
    /// Ready to parse a new event.
    Start,
    /// After parsing the first line of the event.
    AfterEventLine,
    /// After parsing a combined event/stack line.
    AfterCombinedLine,
    /// After parsing a stack line.
    AfterStackLine,
    /// After parsing a stack srcline line.
    AfterSrcLine,
}
