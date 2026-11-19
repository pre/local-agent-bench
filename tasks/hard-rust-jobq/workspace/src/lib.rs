//! `jobq`: a job scheduler with retries and exponential backoff, and a replay
//! tool that runs recorded traces against it.
//!
//! - docs/SCHEDULER.md: the behavior of [`Scheduler`] and [`RetryPolicy`].
//! - docs/TRACE.md: the trace format and the log of the replay.

pub mod backoff;
pub mod heap;
pub mod job;
pub mod replay;
pub mod scheduler;
pub mod slab;
pub mod trace;

pub use backoff::RetryPolicy;
pub use job::{Event, JobId, JobInfo, JobSpec, Outcome, SchedError};
pub use replay::replay;
pub use scheduler::{Scheduler, Stats};
pub use trace::{parse, ParseError, Trace};
