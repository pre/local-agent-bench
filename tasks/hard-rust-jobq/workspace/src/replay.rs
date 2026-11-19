//! Runs a trace against a scheduler and writes the log. docs/TRACE.md
//! describes the log lines.

use std::collections::HashMap;
use std::fmt::Write as _;

use crate::job::{JobId, JobSpec, Outcome, SchedError};
use crate::scheduler::Scheduler;
use crate::trace::{Command, Trace};

/// The scripts of the jobs: the outcome of each attempt. An attempt after the
/// end of its script is done.
#[derive(Default)]
struct Scripts {
    by_name: HashMap<String, Vec<Outcome>>,
}

impl Scripts {
    fn outcome(&self, name: &str, attempt: u32) -> Outcome {
        self.by_name
            .get(name)
            .and_then(|s| s.get(attempt as usize - 1))
            .copied()
            .unwrap_or(Outcome::Done)
    }
}

/// Runs the trace and gives the log.
pub fn replay(trace: &Trace) -> String {
    let mut sched = Scheduler::new(trace.policy);
    let mut scripts = Scripts::default();
    // Like a client, the replay keeps the id that submit gave for each name.
    let mut ids: HashMap<String, JobId> = HashMap::new();
    let mut log = String::new();

    for step in &trace.steps {
        let at = step.at;
        for event in sched.advance(at, |info| scripts.outcome(&info.name, info.attempt)) {
            writeln!(log, "{event}").unwrap();
        }
        match &step.command {
            Command::Submit { name, delay_ms, max_attempts, script } => {
                match sched.submit(JobSpec::new(name.clone(), *delay_ms, *max_attempts)) {
                    Ok(id) => {
                        ids.insert(name.clone(), id);
                        scripts.by_name.entry(name.clone()).or_insert_with(|| script.clone());
                        let due = sched.due(id).expect("a new job is pending");
                        writeln!(log, "t={at} submit {name} due t={due}").unwrap();
                    }
                    Err(e) => writeln!(log, "t={at} submit {name}: {}", short(&e)).unwrap(),
                }
            }
            Command::Cancel { name } => {
                let result = match ids.get(name) {
                    Some(id) => sched.cancel(*id).map(|_| "ok".to_string()).unwrap_or_else(|e| short(&e)),
                    None => "unknown".to_string(),
                };
                writeln!(log, "t={at} cancel {name}: {result}").unwrap();
            }
            Command::Reschedule { name, delay_ms } => {
                let result = match ids.get(name) {
                    Some(id) => match sched.reschedule(*id, *delay_ms) {
                        Ok(()) => format!("due t={}", sched.due(*id).expect("a pending job has a due time")),
                        Err(e) => short(&e),
                    },
                    None => "unknown".to_string(),
                };
                writeln!(log, "t={at} reschedule {name}: {result}").unwrap();
            }
            Command::Advance => {}
        }
    }

    let s = sched.stats();
    writeln!(
        log,
        "end t={} pending={} submitted={} cancelled={} attempts={} done={} retries={} gave_up={} fatal={}",
        sched.now(),
        sched.pending(),
        s.submitted,
        s.cancelled,
        s.attempts,
        s.done,
        s.retries,
        s.gave_up,
        s.fatal
    )
    .unwrap();
    let names = sched.pending_names();
    if !names.is_empty() {
        writeln!(log, "pending: {}", names.join(" ")).unwrap();
    }
    log
}

fn short(e: &SchedError) -> String {
    match e {
        SchedError::Duplicate(_) => "duplicate".into(),
        SchedError::NotFound => "not found".into(),
        SchedError::NoAttempts => "no attempts".into(),
        SchedError::TimeOverflow => "time overflow".into(),
    }
}
