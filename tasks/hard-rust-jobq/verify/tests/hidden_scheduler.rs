use std::collections::{HashMap, HashSet};

use jobq::{Event, JobId, JobSpec, Outcome, RetryPolicy, SchedError, Scheduler};

/// A small deterministic random generator (LCG of Knuth).
struct Lcg(u64);

impl Lcg {
    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        self.0 >> 33
    }
    fn below(&mut self, n: u64) -> u64 {
        self.next() % n
    }
}

fn ran_names(events: &[Event]) -> Vec<String> {
    events
        .iter()
        .filter_map(|e| match e {
            Event::Ran { name, .. } => Some(name.clone()),
            _ => None,
        })
        .collect()
}

#[test]
fn stale_id_cancel_is_not_found() {
    let mut s = Scheduler::default();
    let a = s.submit(JobSpec::new("a", 0, 1)).unwrap();
    s.advance(1, |_| Outcome::Done);
    let b = s.submit(JobSpec::new("b", 10, 1)).unwrap();
    assert_ne!(a, b);
    assert_eq!(s.cancel(a), Err(SchedError::NotFound));
    assert_eq!(s.pending(), 1);
    assert_eq!(s.due(a), None);
    assert_eq!(s.due(b), Some(11));
    let ev = s.advance(100, |_| Outcome::Done);
    assert_eq!(ran_names(&ev), vec!["b"]);
}

#[test]
fn stale_id_reschedule_is_not_found() {
    let mut s = Scheduler::default();
    let a = s.submit(JobSpec::new("a", 50, 1)).unwrap();
    s.cancel(a).unwrap();
    let b = s.submit(JobSpec::new("b", 10, 1)).unwrap();
    assert_eq!(s.reschedule(a, 500), Err(SchedError::NotFound));
    assert_eq!(s.due(b), Some(10));
    assert_eq!(s.cancel(a), Err(SchedError::NotFound));
    assert_eq!(s.lookup("b"), Some(b));
    assert_eq!(s.stats().cancelled, 1);
}

#[test]
fn ids_are_never_reused() {
    let mut s = Scheduler::default();
    let mut seen = HashSet::new();
    let mut rng = Lcg(5);
    let mut live: Vec<JobId> = Vec::new();
    for i in 0..3000u64 {
        match rng.below(4) {
            0 | 1 => {
                let id = s.submit(JobSpec::new(format!("j{i}"), rng.below(50), 1)).unwrap();
                assert!(seen.insert(id), "id {id:?} was given twice");
                live.push(id);
            }
            2 if !live.is_empty() => {
                let id = live.swap_remove(rng.below(live.len() as u64) as usize);
                let _ = s.cancel(id);
            }
            _ => {
                let to = s.now() + rng.below(30);
                s.advance(to, |_| Outcome::Done);
            }
        }
    }
    for id in seen {
        if !live.contains(&id) {
            assert_eq!(s.due(id), None);
        }
    }
}

/// The queue order of docs/SCHEDULER.md, kept in a plain list.
#[derive(Default)]
struct Model {
    seq: u64,
    jobs: HashMap<String, (u64, u64)>, // name -> (due, seq)
}

impl Model {
    fn put(&mut self, name: &str, due: u64) {
        self.jobs.insert(name.to_string(), (due, self.seq));
        self.seq += 1;
    }
    fn run_until(&mut self, to: u64) -> Vec<String> {
        let mut due: Vec<(u64, u64, String)> =
            self.jobs.iter().filter(|(_, v)| v.0 <= to).map(|(k, v)| (v.0, v.1, k.clone())).collect();
        due.sort();
        for (_, _, n) in &due {
            self.jobs.remove(n);
        }
        due.into_iter().map(|(_, _, n)| n).collect()
    }
}

#[test]
fn order_matches_the_specification() {
    for seed in 1..=40u64 {
        let mut rng = Lcg(seed);
        let mut s = Scheduler::default();
        let mut model = Model::default();
        let mut ids: HashMap<String, JobId> = HashMap::new();
        for step in 0..400u64 {
            let name = format!("n{}", rng.below(120));
            match rng.below(10) {
                0..=3 => {
                    let delay = rng.below(1000);
                    if let Ok(id) = s.submit(JobSpec::new(name.clone(), delay, 1)) {
                        ids.insert(name.clone(), id);
                        model.put(&name, s.now() + delay);
                    }
                }
                4..=6 => {
                    if let Some(id) = ids.get(&name) {
                        if s.cancel(*id).is_ok() {
                            assert!(model.jobs.remove(&name).is_some(), "seed {seed} step {step}: cancel of {name}");
                        }
                    }
                }
                7 => {
                    if let Some(id) = ids.get(&name) {
                        let delay = rng.below(1000);
                        if s.reschedule(*id, delay).is_ok() {
                            model.put(&name, s.now() + delay);
                        }
                    }
                }
                _ => {
                    let to = s.now() + rng.below(200);
                    let got = ran_names(&s.advance(to, |_| Outcome::Done));
                    let want = model.run_until(to);
                    assert_eq!(got, want, "seed {seed} step {step}: order of attempts");
                }
            }
        }
        let to = s.now() + 10_000;
        let got = ran_names(&s.advance(to, |_| Outcome::Done));
        assert_eq!(got, model.run_until(to), "seed {seed}: order at the end");
    }
}

#[test]
fn pending_names_follow_the_queue() {
    let mut s = Scheduler::default();
    let mut ids = Vec::new();
    for (i, d) in [70u64, 10, 60, 20, 50, 30, 40, 5, 65, 15, 55, 25].iter().enumerate() {
        ids.push(s.submit(JobSpec::new(format!("j{i}"), *d, 1)).unwrap());
    }
    for i in [3usize, 4, 9] {
        s.cancel(ids[i]).unwrap();
    }
    let mut dues: Vec<(u64, String)> = Vec::new();
    for (i, id) in ids.iter().enumerate() {
        if let Some(d) = s.due(*id) {
            dues.push((d, format!("j{i}")));
        }
    }
    dues.sort();
    let want: Vec<String> = dues.into_iter().map(|(_, n)| n).collect();
    assert_eq!(s.pending_names(), want);
    let got = ran_names(&s.advance(1000, |_| Outcome::Done));
    assert_eq!(got, want);
}

#[test]
fn backoff_is_exact_for_all_attempts() {
    let policies = [
        RetryPolicy::default(),
        RetryPolicy { base_ms: 1000, max_ms: u64::MAX },
        RetryPolicy { base_ms: 3, max_ms: 1 << 62 },
        RetryPolicy { base_ms: 5000, max_ms: 7_200_000 },
        RetryPolicy { base_ms: (1 << 63) + 1, max_ms: u64::MAX },
        RetryPolicy { base_ms: 1, max_ms: 1 },
    ];
    for p in policies {
        let mut last = 0;
        for n in 0..=300u32 {
            let e = n.max(1) - 1;
            let want = if e >= 128 {
                p.max_ms
            } else {
                let exact = (p.base_ms as u128).checked_mul(1u128 << e);
                match exact {
                    Some(v) if v <= p.max_ms as u128 => v as u64,
                    _ => p.max_ms,
                }
            };
            let got = p.delay(n);
            assert_eq!(got, want, "{p:?}: delay({n})");
            assert!(got >= last, "{p:?}: delay({n}) = {got} is less than the delay before ({last})");
            last = got;
        }
    }
}

#[test]
fn long_retry_chain_waits_the_full_delay() {
    let mut s = Scheduler::default();
    s.submit(JobSpec::new("sweeper", 0, 80)).unwrap();
    let ev = s.advance(u64::MAX / 2, |_| Outcome::Retry);
    let mut times = Vec::new();
    for e in &ev {
        if let Event::Ran { at, .. } = e {
            times.push(*at);
        }
    }
    assert_eq!(times.len(), 80);
    for (i, w) in times.windows(2).enumerate() {
        let n = i as u32 + 1;
        let want = RetryPolicy::default().max_ms.min(1000u64.saturating_mul(1u64 << n.min(40).saturating_sub(1)));
        assert_eq!(w[1] - w[0], want, "gap after attempt {n}");
    }
    assert!(matches!(ev.last(), Some(Event::GaveUp { attempts: 80, .. })));
}

#[test]
fn fatal_frees_the_name() {
    let mut s = Scheduler::default();
    let a = s.submit(JobSpec::new("build", 5, 3)).unwrap();
    s.advance(10, |_| Outcome::Fatal);
    assert_eq!(s.pending(), 0);
    assert_eq!(s.lookup("build"), None);
    assert_eq!(s.cancel(a), Err(SchedError::NotFound));
    let b = s.submit(JobSpec::new("build", 5, 3)).expect("the name of a failed job is free");
    assert_eq!(s.lookup("build"), Some(b));
    let st = s.stats();
    assert_eq!((st.submitted, st.fatal, st.attempts), (2, 1, 1));
}

#[test]
fn give_up_frees_the_name() {
    let mut s = Scheduler::new(RetryPolicy { base_ms: 1, max_ms: 1 });
    s.submit(JobSpec::new("x", 0, 2)).unwrap();
    s.advance(100, |_| Outcome::Retry);
    assert_eq!(s.lookup("x"), None);
    s.submit(JobSpec::new("x", 0, 2)).unwrap();
    assert_eq!(s.stats().gave_up, 1);
}

#[test]
fn errors_change_nothing() {
    let mut s = Scheduler::default();
    s.advance(10, |_| Outcome::Done);
    let a = s.submit(JobSpec::new("a", 5, 1)).unwrap();
    assert_eq!(s.reschedule(a, u64::MAX), Err(SchedError::TimeOverflow));
    assert_eq!(s.due(a), Some(15));
    assert_eq!(s.submit(JobSpec::new("a", 1, 1)), Err(SchedError::Duplicate("a".into())));
    assert_eq!(s.submit(JobSpec::new("b", u64::MAX - 5, 1)), Err(SchedError::TimeOverflow));
    assert_eq!(s.pending(), 1);
    assert_eq!(s.stats().submitted, 1);
}

#[test]
fn retry_gets_a_new_sequence_number() {
    let mut s = Scheduler::new(RetryPolicy { base_ms: 100, max_ms: 100 });
    s.submit(JobSpec::new("a", 0, 2)).unwrap();
    s.submit(JobSpec::new("b", 100, 1)).unwrap();
    let ev = s.advance(0, |_| Outcome::Retry);
    assert_eq!(ran_names(&ev), vec!["a"]);
    s.submit(JobSpec::new("c", 100, 1)).unwrap();
    assert_eq!(s.pending_names(), vec!["b", "a", "c"]);
    let ev = s.advance(500, |_| Outcome::Done);
    assert_eq!(ran_names(&ev), vec!["b", "a", "c"]);
}

#[test]
fn replay_resubmit_uses_the_new_script() {
    let trace = jobq::parse(
        "policy base=10 max=10\n\
         0 submit x attempts=2 script=fatal\n\
         5 submit x attempts=2 script=retry,done\n\
         5 submit y delay=10 attempts=1 script=done\n\
         100 advance\n",
    )
    .unwrap();
    assert_eq!(
        jobq::replay(&trace),
        "t=0 submit x due t=0\n\
         t=0 run x#1 fatal\n\
         t=5 submit x due t=5\n\
         t=5 run x#1 retry\n\
         t=5 retry x at t=15\n\
         t=5 submit y due t=15\n\
         t=15 run x#2 done\n\
         t=15 run y#1 done\n\
         end t=100 pending=0 submitted=3 cancelled=0 attempts=4 done=2 retries=1 gave_up=0 fatal=1\n"
    );
}
