fn check(trace: &str, want: &str) {
    let trace = jobq::parse(trace).expect("the trace parses");
    let got = jobq::replay(&trace);
    if got == want {
        return;
    }
    for (i, (g, w)) in got.lines().zip(want.lines()).enumerate() {
        assert_eq!(g, w, "first difference at log line {}", i + 1);
    }
    assert_eq!(got.lines().count(), want.lines().count(), "the logs have a different length");
}

#[test]
fn replay_trace1() {
    check(include_str!("hidden/trace1.trace"), include_str!("hidden/trace1.log"));
}

#[test]
fn replay_trace2() {
    check(include_str!("hidden/trace2.trace"), include_str!("hidden/trace2.log"));
}

#[test]
fn replay_trace3() {
    check(include_str!("hidden/trace3.trace"), include_str!("hidden/trace3.log"));
}
