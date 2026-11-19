use jobq::{Event, JobSpec, Outcome, RetryPolicy, SchedError, Scheduler};

fn names(events: &[Event]) -> Vec<String> {
    events.iter().map(|e| e.to_string()).collect()
}

#[test]
fn runs_in_due_order() {
    let mut s = Scheduler::default();
    s.submit(JobSpec::new("b", 20, 1)).unwrap();
    s.submit(JobSpec::new("a", 10, 1)).unwrap();
    s.submit(JobSpec::new("c", 20, 1)).unwrap();
    let ev = s.advance(100, |_| Outcome::Done);
    assert_eq!(names(&ev), vec!["t=10 run a#1 done", "t=20 run b#1 done", "t=20 run c#1 done"]);
    assert_eq!(s.now(), 100);
    assert_eq!(s.pending(), 0);
}

#[test]
fn retries_with_backoff() {
    let mut s = Scheduler::new(RetryPolicy { base_ms: 100, max_ms: 250 });
    s.submit(JobSpec::new("job", 0, 4)).unwrap();
    let ev = s.advance(10_000, |_| Outcome::Retry);
    assert_eq!(
        names(&ev),
        vec![
            "t=0 run job#1 retry",
            "t=0 retry job at t=100",
            "t=100 run job#2 retry",
            "t=100 retry job at t=300",
            "t=300 run job#3 retry",
            "t=300 retry job at t=550",
            "t=550 run job#4 retry",
            "t=550 give up job after 4 attempts",
        ]
    );
    assert!(s.lookup("job").is_none());
    s.submit(JobSpec::new("job", 0, 1)).unwrap();
}

#[test]
fn cancel_and_reschedule() {
    let mut s = Scheduler::default();
    let a = s.submit(JobSpec::new("a", 10, 1)).unwrap();
    let b = s.submit(JobSpec::new("b", 20, 1)).unwrap();
    s.reschedule(b, 5).unwrap();
    assert_eq!(s.due(b), Some(5));
    s.cancel(a).unwrap();
    assert_eq!(s.cancel(a), Err(SchedError::NotFound));
    let ev = s.advance(50, |_| Outcome::Done);
    assert_eq!(names(&ev), vec!["t=5 run b#1 done"]);
    assert_eq!(s.reschedule(b, 5), Err(SchedError::NotFound));
}

#[test]
fn duplicate_names() {
    let mut s = Scheduler::default();
    s.submit(JobSpec::new("a", 10, 1)).unwrap();
    assert_eq!(s.submit(JobSpec::new("a", 5, 1)), Err(SchedError::Duplicate("a".into())));
    assert_eq!(s.submit(JobSpec::new("z", 5, 0)), Err(SchedError::NoAttempts));
    s.advance(10, |_| Outcome::Done);
    s.submit(JobSpec::new("a", 5, 1)).unwrap();
}

#[test]
fn time_does_not_go_back() {
    let mut s = Scheduler::default();
    s.advance(100, |_| Outcome::Done);
    s.submit(JobSpec::new("a", 0, 1)).unwrap();
    let ev = s.advance(50, |_| Outcome::Done);
    assert!(ev.is_empty());
    assert_eq!(s.now(), 100);
    assert_eq!(s.submit(JobSpec::new("b", u64::MAX, 1)), Err(SchedError::TimeOverflow));
}

#[test]
fn replay_small_trace() {
    let trace = jobq::parse(
        "policy base=10 max=40\n\
         0 submit a delay=5 attempts=3 script=retry,retry,done\n\
         0 submit b delay=7 script=fatal\n\
         6 cancel b\n\
         100 advance\n",
    )
    .unwrap();
    let log = jobq::replay(&trace);
    assert_eq!(
        log,
        "t=0 submit a due t=5\n\
         t=0 submit b due t=7\n\
         t=5 run a#1 retry\n\
         t=5 retry a at t=15\n\
         t=6 cancel b: ok\n\
         t=15 run a#2 retry\n\
         t=15 retry a at t=35\n\
         t=35 run a#3 done\n\
         end t=100 pending=0 submitted=2 cancelled=1 attempts=3 done=1 retries=2 gave_up=0 fatal=0\n"
    );
}
