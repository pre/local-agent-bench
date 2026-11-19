//! The public types of jobs and events.

use std::fmt;

use crate::slab::Key;

/// The handle of a submitted job. It stays valid until the job finishes or is
/// cancelled. After that, the scheduler rejects it with
/// [`SchedError::NotFound`], also when a new job was submitted later.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct JobId(pub(crate) Key);

/// What to submit.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct JobSpec {
    /// The name of the job. Two pending jobs cannot have the same name.
    pub name: String,
    /// The time from now to the first attempt, in milliseconds.
    pub delay_ms: u64,
    /// The largest number of attempts, at least 1.
    pub max_attempts: u32,
}

impl JobSpec {
    pub fn new(name: impl Into<String>, delay_ms: u64, max_attempts: u32) -> Self {
        JobSpec { name: name.into(), delay_ms, max_attempts }
    }
}

/// What the handler tells about one attempt.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Outcome {
    /// The job is complete.
    Done,
    /// The attempt failed. The scheduler retries the job if it has attempts
    /// left.
    Retry,
    /// The job failed and must not be retried.
    Fatal,
}

impl fmt::Display for Outcome {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Outcome::Done => "done",
            Outcome::Retry => "retry",
            Outcome::Fatal => "fatal",
        })
    }
}

/// The data that the handler gets for one attempt.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct JobInfo {
    pub id: JobId,
    pub name: String,
    /// The number of this attempt, 1 for the first attempt.
    pub attempt: u32,
    pub max_attempts: u32,
    /// The time of the attempt.
    pub now: u64,
}

/// Something that happened in [`crate::Scheduler::advance`].
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Event {
    /// The handler ran an attempt.
    Ran { at: u64, name: String, attempt: u32, outcome: Outcome },
    /// The job will run again at `due`.
    RetryAt { at: u64, name: String, due: u64 },
    /// The last permitted attempt failed with [`Outcome::Retry`].
    GaveUp { at: u64, name: String, attempts: u32 },
}

impl fmt::Display for Event {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Event::Ran { at, name, attempt, outcome } => write!(f, "t={at} run {name}#{attempt} {outcome}"),
            Event::RetryAt { at, name, due } => write!(f, "t={at} retry {name} at t={due}"),
            Event::GaveUp { at, name, attempts } => write!(f, "t={at} give up {name} after {attempts} attempts"),
        }
    }
}

/// The errors of the scheduler.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum SchedError {
    /// A pending job has the same name.
    Duplicate(String),
    /// The job finished or was cancelled, or the id is not from this
    /// scheduler.
    NotFound,
    /// `max_attempts` is 0.
    NoAttempts,
    /// The due time does not fit in 64 bits.
    TimeOverflow,
}

impl fmt::Display for SchedError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            SchedError::Duplicate(name) => write!(f, "a pending job has the name {name:?}"),
            SchedError::NotFound => f.write_str("no such job"),
            SchedError::NoAttempts => f.write_str("max_attempts must be at least 1"),
            SchedError::TimeOverflow => f.write_str("the due time is too large"),
        }
    }
}

impl std::error::Error for SchedError {}
