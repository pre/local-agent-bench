//! The scheduler. docs/SCHEDULER.md describes the behavior.

use std::collections::HashMap;

use crate::backoff::RetryPolicy;
use crate::heap::{Entry, Heap};
use crate::job::{Event, JobId, JobInfo, JobSpec, Outcome, SchedError};
use crate::slab::{Key, Slab};

#[derive(Debug)]
struct Job {
    name: String,
    /// The attempts that were made.
    attempts: u32,
    max_attempts: u32,
    /// The time of the next attempt. The heap has the same value.
    due: u64,
}

/// Counters of a scheduler, since it was made.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Stats {
    pub submitted: u64,
    pub cancelled: u64,
    pub attempts: u64,
    pub done: u64,
    pub retries: u64,
    pub gave_up: u64,
    pub fatal: u64,
}

/// A job scheduler with a manual clock. The clock starts at 0 and moves only
/// in [`Scheduler::advance`].
#[derive(Debug)]
pub struct Scheduler {
    policy: RetryPolicy,
    now: u64,
    next_seq: u64,
    jobs: Slab<Job>,
    queue: Heap,
    names: HashMap<String, Key>,
    stats: Stats,
}

impl Default for Scheduler {
    fn default() -> Self {
        Self::new(RetryPolicy::default())
    }
}

impl Scheduler {
    pub fn new(policy: RetryPolicy) -> Self {
        Scheduler {
            policy,
            now: 0,
            next_seq: 0,
            jobs: Slab::new(),
            queue: Heap::new(),
            names: HashMap::new(),
            stats: Stats::default(),
        }
    }

    /// The current time in milliseconds.
    pub fn now(&self) -> u64 {
        self.now
    }

    pub fn policy(&self) -> RetryPolicy {
        self.policy
    }

    pub fn stats(&self) -> Stats {
        self.stats
    }

    /// The number of pending jobs.
    pub fn pending(&self) -> usize {
        self.jobs.len()
    }

    /// The id of the pending job with this name.
    pub fn lookup(&self, name: &str) -> Option<JobId> {
        self.names.get(name).map(|k| JobId(*k))
    }

    /// The time of the next attempt of a pending job.
    pub fn due(&self, id: JobId) -> Option<u64> {
        self.jobs.get(id.0).map(|j| j.due)
    }

    /// The names of the pending jobs in the order in which they will run, if
    /// no job is added, changed or retried.
    pub fn pending_names(&self) -> Vec<String> {
        let mut order: Vec<(u64, u64, &str)> = Vec::new();
        let mut copy = Heap::new();
        for (key, job) in self.jobs.iter() {
            copy.push(Entry { due: job.due, seq: self.seq_of(key), key });
        }
        while let Some(e) = copy.pop() {
            order.push((e.due, e.seq, &self.jobs[e.key].name));
        }
        order.into_iter().map(|(_, _, n)| n.to_string()).collect()
    }

    fn seq_of(&self, key: Key) -> u64 {
        self.queue.seq_of(key).expect("a pending job is in the queue")
    }

    /// Adds a job. Its first attempt is due at `now + spec.delay_ms`.
    pub fn submit(&mut self, spec: JobSpec) -> Result<JobId, SchedError> {
        if spec.max_attempts == 0 {
            return Err(SchedError::NoAttempts);
        }
        if self.names.contains_key(&spec.name) {
            return Err(SchedError::Duplicate(spec.name));
        }
        let due = self.now.checked_add(spec.delay_ms).ok_or(SchedError::TimeOverflow)?;
        let key = self.jobs.insert(Job { name: spec.name.clone(), attempts: 0, max_attempts: spec.max_attempts, due });
        let seq = self.take_seq();
        self.queue.push(Entry { due, seq, key });
        self.names.insert(spec.name, key);
        self.stats.submitted += 1;
        Ok(JobId(key))
    }

    /// Removes a pending job.
    pub fn cancel(&mut self, id: JobId) -> Result<(), SchedError> {
        let job = self.jobs.remove(id.0).ok_or(SchedError::NotFound)?;
        self.queue.remove(id.0);
        self.names.remove(&job.name);
        self.stats.cancelled += 1;
        Ok(())
    }

    /// Moves the next attempt of a pending job to `now + delay_ms`.
    pub fn reschedule(&mut self, id: JobId, delay_ms: u64) -> Result<(), SchedError> {
        let due = self.now.checked_add(delay_ms).ok_or(SchedError::TimeOverflow)?;
        if !self.jobs.contains(id.0) {
            return Err(SchedError::NotFound);
        }
        let seq = self.take_seq();
        self.jobs[id.0].due = due;
        self.queue.update(id.0, due, seq);
        Ok(())
    }

    /// Runs the attempts that are due at or before `to`, in order, and moves
    /// the clock to `to`. The handler runs each attempt. A time before `now`
    /// runs nothing and does not move the clock back.
    pub fn advance<F>(&mut self, to: u64, mut handler: F) -> Vec<Event>
    where
        F: FnMut(&JobInfo) -> Outcome,
    {
        let mut events = Vec::new();
        while let Some(&Entry { due, seq, key }) = self.queue.peek() {
            if due > to {
                break;
            }
            self.queue.pop();
            self.now = self.now.max(due);
            let job = &mut self.jobs[key];
            job.attempts += 1;
            let info = JobInfo {
                id: JobId(key),
                name: job.name.clone(),
                attempt: job.attempts,
                max_attempts: job.max_attempts,
                now: self.now,
            };
            self.stats.attempts += 1;
            let outcome = handler(&info);
            events.push(Event::Ran { at: self.now, name: info.name.clone(), attempt: info.attempt, outcome });
            match outcome {
                Outcome::Done => {
                    self.stats.done += 1;
                    self.finish(key);
                }
                Outcome::Fatal => {
                    // A fatal failure is never retried.
                    self.stats.fatal += 1;
                    self.jobs.remove(key);
                }
                Outcome::Retry if info.attempt < info.max_attempts => {
                    // The retry keeps the sequence number of the job, so a
                    // job keeps its place among jobs with the same due time.
                    let due = self.now.saturating_add(self.policy.delay(info.attempt));
                    self.jobs[key].due = due;
                    self.queue.push(Entry { due, seq, key });
                    self.stats.retries += 1;
                    events.push(Event::RetryAt { at: self.now, name: info.name, due });
                }
                Outcome::Retry => {
                    self.stats.gave_up += 1;
                    events.push(Event::GaveUp { at: self.now, name: info.name, attempts: info.attempt });
                    self.finish(key);
                }
            }
        }
        self.now = self.now.max(to);
        events
    }

    /// Removes a job that has no more attempts.
    fn finish(&mut self, key: Key) {
        if let Some(job) = self.jobs.remove(key) {
            self.names.remove(&job.name);
        }
    }

    fn take_seq(&mut self) -> u64 {
        let seq = self.next_seq;
        self.next_seq += 1;
        seq
    }
}
