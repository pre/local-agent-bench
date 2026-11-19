//! The trace format. docs/TRACE.md describes it.

use std::fmt;

use crate::backoff::RetryPolicy;
use crate::job::Outcome;

/// One command of a trace.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Command {
    Submit { name: String, delay_ms: u64, max_attempts: u32, script: Vec<Outcome> },
    Cancel { name: String },
    Reschedule { name: String, delay_ms: u64 },
    Advance,
}

/// A command and its time.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Step {
    pub line: usize,
    pub at: u64,
    pub command: Command,
}

/// A parsed trace.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Trace {
    pub policy: RetryPolicy,
    pub steps: Vec<Step>,
}

/// An error in a trace, with its line number.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ParseError {
    pub line: usize,
    pub message: String,
}

impl fmt::Display for ParseError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "line {}: {}", self.line, self.message)
    }
}

impl std::error::Error for ParseError {}

/// The largest repeat count in a script, for example `retry*500`.
pub const MAX_REPEAT: u32 = 10_000;

pub fn parse(text: &str) -> Result<Trace, ParseError> {
    let mut trace = Trace { policy: RetryPolicy::default(), steps: Vec::new() };
    let mut last_time = 0;
    for (i, raw) in text.lines().enumerate() {
        let line = i + 1;
        let err = |message: String| ParseError { line, message };
        let content = raw.split('#').next().unwrap_or("").trim();
        if content.is_empty() {
            continue;
        }
        let mut words = content.split_whitespace();
        let first = words.next().unwrap_or_default();
        if first == "policy" {
            if !trace.steps.is_empty() {
                return Err(err("policy must come before the first command".into()));
            }
            for w in words {
                let (k, v) = split_option(w).map_err(err)?;
                match k {
                    "base" => trace.policy.base_ms = parse_u64(k, v).map_err(err)?,
                    "max" => trace.policy.max_ms = parse_u64(k, v).map_err(err)?,
                    _ => return Err(err(format!("unknown policy option {k:?}"))),
                }
            }
            continue;
        }
        let at = parse_u64("time", first).map_err(err)?;
        if at < last_time {
            return Err(err(format!("time {at} is before the time of the line before ({last_time})")));
        }
        last_time = at;
        let verb = words.next().ok_or_else(|| err("missing command".into()))?;
        let args: Vec<&str> = words.collect();
        let command = match verb {
            "submit" => parse_submit(&args).map_err(err)?,
            "cancel" => Command::Cancel { name: one_name(&args).map_err(err)? },
            "reschedule" => {
                let (name, rest) = args.split_first().ok_or_else(|| err("missing name".into()))?;
                check_name(name).map_err(err)?;
                let mut delay_ms = None;
                for w in rest {
                    let (k, v) = split_option(w).map_err(err)?;
                    match k {
                        "delay" => delay_ms = Some(parse_u64(k, v).map_err(err)?),
                        _ => return Err(err(format!("unknown option {k:?}"))),
                    }
                }
                let delay_ms = delay_ms.ok_or_else(|| err("missing delay=".into()))?;
                Command::Reschedule { name: name.to_string(), delay_ms }
            }
            "advance" => {
                if !args.is_empty() {
                    return Err(err("advance has no arguments".into()));
                }
                Command::Advance
            }
            _ => return Err(err(format!("unknown command {verb:?}"))),
        };
        trace.steps.push(Step { line, at, command });
    }
    Ok(trace)
}

fn parse_submit(args: &[&str]) -> Result<Command, String> {
    let (name, rest) = args.split_first().ok_or("missing name")?;
    check_name(name)?;
    let mut delay_ms = 0;
    let mut max_attempts = 3;
    let mut script = Vec::new();
    for w in rest {
        let (k, v) = split_option(w)?;
        match k {
            "delay" => delay_ms = parse_u64(k, v)?,
            "attempts" => {
                max_attempts = u32::try_from(parse_u64(k, v)?).map_err(|_| "attempts is too large".to_string())?;
                if max_attempts == 0 {
                    return Err("attempts must be at least 1".into());
                }
            }
            "script" => script = parse_script(v)?,
            _ => return Err(format!("unknown option {k:?}")),
        }
    }
    Ok(Command::Submit { name: name.to_string(), delay_ms, max_attempts, script })
}

/// Reads a script such as `retry*3,fatal`.
pub fn parse_script(v: &str) -> Result<Vec<Outcome>, String> {
    let mut out = Vec::new();
    for item in v.split(',') {
        let (word, count) = match item.split_once('*') {
            Some((w, n)) => {
                let n: u32 = n.parse().map_err(|_| format!("bad repeat count {n:?}"))?;
                if n == 0 || n > MAX_REPEAT {
                    return Err(format!("repeat count must be 1 to {MAX_REPEAT}"));
                }
                (w, n)
            }
            None => (item, 1),
        };
        let outcome = match word {
            "done" => Outcome::Done,
            "retry" => Outcome::Retry,
            "fatal" => Outcome::Fatal,
            _ => return Err(format!("unknown outcome {word:?}")),
        };
        out.extend(std::iter::repeat(outcome).take(count as usize));
    }
    Ok(out)
}

fn one_name(args: &[&str]) -> Result<String, String> {
    match args {
        [name] => {
            check_name(name)?;
            Ok(name.to_string())
        }
        _ => Err("expected one name".into()),
    }
}

fn check_name(name: &str) -> Result<(), String> {
    let ok = !name.is_empty()
        && !name.contains('=')
        && name.chars().all(|c| c.is_ascii_alphanumeric() || "-_./".contains(c));
    if ok {
        Ok(())
    } else {
        Err(format!("bad job name {name:?}"))
    }
}

fn split_option(w: &str) -> Result<(&str, &str), String> {
    w.split_once('=').ok_or_else(|| format!("expected key=value, found {w:?}"))
}

fn parse_u64(what: &str, v: &str) -> Result<u64, String> {
    v.parse().map_err(|_| format!("bad {what} {v:?}"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_commands() {
        let t = parse(
            "policy base=10 max=100\n\
             # comment\n\
             0 submit a delay=5 attempts=2 script=retry,done\n\
             3 cancel a   # trailing comment\n\
             3 reschedule b delay=7\n\
             9 advance\n",
        )
        .unwrap();
        assert_eq!(t.policy, RetryPolicy { base_ms: 10, max_ms: 100 });
        assert_eq!(t.steps.len(), 4);
        assert_eq!(
            t.steps[0].command,
            Command::Submit {
                name: "a".into(),
                delay_ms: 5,
                max_attempts: 2,
                script: vec![Outcome::Retry, Outcome::Done]
            }
        );
        assert_eq!(t.steps[1], Step { line: 4, at: 3, command: Command::Cancel { name: "a".into() } });
    }

    #[test]
    fn rejects_bad_lines() {
        for (text, line) in [
            ("0 submit", 1),
            ("5 advance\n4 advance", 2),
            ("0 submit a script=maybe", 1),
            ("0 submit a attempts=0", 1),
            ("0 frobnicate a", 1),
            ("0 advance\npolicy base=1", 2),
            ("0 submit a script=retry*0", 1),
        ] {
            assert_eq!(parse(text).unwrap_err().line, line, "{text}");
        }
    }

    #[test]
    fn script_repeat() {
        assert_eq!(parse_script("retry*2,fatal").unwrap(), vec![Outcome::Retry, Outcome::Retry, Outcome::Fatal]);
    }
}
