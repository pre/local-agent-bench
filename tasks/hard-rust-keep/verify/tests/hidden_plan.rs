use keepr::{parse_policy, parse_snapshots, plan, render, PlanError};

fn run(snapshots: &str, policy: &str) -> String {
    let s = parse_snapshots(snapshots).expect("snapshot list");
    let p = parse_policy(policy).expect("policy");
    let pl = plan(&s, &p).expect("plan");
    render(&pl, &s, &p)
}

fn lines(v: &[&str]) -> String {
    v.iter().map(|l| format!("{l}\n")).collect()
}

#[test]
fn empty_policy_is_an_error() {
    let s = parse_snapshots("a1 2026-01-01T00:00:00Z host=h paths=/").unwrap();
    for text in ["", "keep-daily = 0\nkeep-last = 0\ntimezone = +02:00", "group-by = none"] {
        let p = parse_policy(text).unwrap();
        assert_eq!(plan(&s, &p), Err(PlanError::EmptyPolicy), "policy {text:?}");
    }
    let p = parse_policy("keep-within = 0h").unwrap();
    assert!(plan(&s, &p).is_ok(), "a span of 0 is an active rule");
}

#[test]
fn ties_use_the_id() {
    let got = run(
        "0a 2026-01-05T10:00:00Z host=h paths=/\n\
         b 2026-01-05T10:00:00Z host=h paths=/\n\
         a1 2026-01-05T10:00:00Z host=h paths=/\n\
         ff 2026-01-04T10:00:00Z host=h paths=/\n",
        "keep-last = 2\nkeep-daily = 2",
    );
    assert_eq!(
        got,
        lines(&[
            "group host=h paths=/",
            "keep b 2026-01-05T10:00:00Z last,daily",
            "keep a1 2026-01-05T10:00:00Z last",
            "remove 0a 2026-01-05T10:00:00Z",
            "keep ff 2026-01-04T10:00:00Z daily",
            "",
            "kept 3, removed 1",
        ])
    );
}

#[test]
fn iso_weeks_at_year_ends() {
    let got = run(
        "01 2020-12-31T12:00:00Z host=h paths=/\n\
         02 2021-01-03T12:00:00Z host=h paths=/\n\
         03 2025-12-28T12:00:00Z host=h paths=/\n\
         04 2025-12-29T12:00:00Z host=h paths=/\n\
         05 2026-12-28T12:00:00Z host=h paths=/\n\
         06 2027-01-03T12:00:00Z host=h paths=/\n\
         07 2027-01-04T12:00:00Z host=h paths=/\n",
        "keep-weekly = -1",
    );
    assert_eq!(
        got,
        lines(&[
            "group host=h paths=/",
            "keep 07 2027-01-04T12:00:00Z weekly",
            "keep 06 2027-01-03T12:00:00Z weekly",
            "remove 05 2026-12-28T12:00:00Z",
            "keep 04 2025-12-29T12:00:00Z weekly",
            "keep 03 2025-12-28T12:00:00Z weekly",
            "keep 02 2021-01-03T12:00:00Z weekly",
            "remove 01 2020-12-31T12:00:00Z",
            "",
            "kept 5, removed 2",
        ])
    );
}

#[test]
fn buckets_use_the_policy_timezone() {
    let got = run(
        "aa 2026-05-02T03:00:00Z host=h paths=/\n\
         bb 2026-05-01T23:00:00Z host=h paths=/\n\
         cc 2026-05-01T04:00:00Z host=h paths=/\n\
         dd 2026-04-30T06:00:00+01:00 host=h paths=/\n",
        "keep-daily = 2\nkeep-monthly = 2\ntimezone = -05:00",
    );
    assert_eq!(
        got,
        lines(&[
            "group host=h paths=/",
            "keep aa 2026-05-01T22:00:00-05:00 daily,monthly",
            "remove bb 2026-05-01T18:00:00-05:00",
            "keep cc 2026-04-30T23:00:00-05:00 daily,monthly",
            "remove dd 2026-04-30T00:00:00-05:00",
            "",
            "kept 2, removed 2",
        ])
    );
}

#[test]
fn hourly_with_a_half_hour_offset() {
    let got = run(
        "01 2026-06-01T10:20:00Z host=h paths=/\n\
         02 2026-06-01T10:40:00Z host=h paths=/\n\
         03 2026-06-01T10:50:00Z host=h paths=/\n\
         04 2026-06-01T09:10:00Z host=h paths=/\n",
        "keep-hourly = 3\ntimezone = +05:30",
    );
    assert_eq!(
        got,
        lines(&[
            "group host=h paths=/",
            "keep 03 2026-06-01T16:20:00+05:30 hourly",
            "remove 02 2026-06-01T16:10:00+05:30",
            "keep 01 2026-06-01T15:50:00+05:30 hourly",
            "keep 04 2026-06-01T14:40:00+05:30 hourly",
            "",
            "kept 3, removed 1",
        ])
    );
}

#[test]
fn within_clamps_month_ends_and_leap_days() {
    let got = run(
        "a1 2024-03-31T10:00:00Z host=one paths=/\n\
         a2 2024-02-29T00:00:00Z host=one paths=/\n\
         a3 2024-02-28T10:00:00Z host=one paths=/\n\
         a4 2024-02-28T09:59:59Z host=one paths=/\n\
         b1 2028-02-29T12:00:00Z host=two paths=/\n\
         b2 2027-02-28T12:00:00Z host=two paths=/\n\
         b3 2027-02-28T11:00:00Z host=two paths=/\n",
        "keep-within = 1m1d\ngroup-by = host",
    );
    assert_eq!(
        got,
        lines(&[
            "group host=one",
            "keep a1 2024-03-31T10:00:00Z within",
            "keep a2 2024-02-29T00:00:00Z within",
            "keep a3 2024-02-28T10:00:00Z within",
            "remove a4 2024-02-28T09:59:59Z",
            "",
            "group host=two",
            "keep b1 2028-02-29T12:00:00Z within",
            "remove b2 2027-02-28T12:00:00Z",
            "remove b3 2027-02-28T11:00:00Z",
            "",
            "kept 4, removed 3",
        ])
    );
    let got = run(
        "b1 2028-02-29T12:00:00Z host=two paths=/\n\
         b2 2027-02-28T12:00:00Z host=two paths=/\n\
         b3 2027-02-28T11:00:00Z host=two paths=/\n",
        "keep-within = 1y",
    );
    assert_eq!(
        got,
        lines(&[
            "group host=two paths=/",
            "keep b1 2028-02-29T12:00:00Z within",
            "keep b2 2027-02-28T12:00:00Z within",
            "remove b3 2027-02-28T11:00:00Z",
            "",
            "kept 2, removed 1",
        ])
    );
}

#[test]
fn within_hours_in_local_time() {
    let got = run(
        "c1 2026-01-01T05:00:00+03:00 host=h paths=/\n\
         c2 2024-12-31T20:00:00Z host=h paths=/\n\
         c3 2024-12-31T19:59:00Z host=h paths=/\n",
        "keep-within = 1y6h\ntimezone = +03:00",
    );
    assert_eq!(
        got,
        lines(&[
            "group host=h paths=/",
            "keep c1 2026-01-01T05:00:00+03:00 within",
            "keep c2 2024-12-31T23:00:00+03:00 within",
            "remove c3 2024-12-31T22:59:00+03:00",
            "",
            "kept 2, removed 1",
        ])
    );
}

#[test]
fn within_daily_keeps_one_each_local_day() {
    let got = run(
        "01 2026-07-09T23:00:00Z host=h paths=/\n\
         02 2026-07-09T17:00:00Z host=h paths=/\n\
         03 2026-07-09T14:00:00Z host=h paths=/\n\
         04 2026-07-09T01:00:00Z host=h paths=/\n\
         05 2026-07-08T00:00:00Z host=h paths=/\n\
         06 2026-07-07T22:00:00Z host=h paths=/\n\
         07 2026-07-07T03:00:00Z host=h paths=/\n",
        "keep-within-daily = 2d\ntimezone = +09:00",
    );
    assert_eq!(
        got,
        lines(&[
            "group host=h paths=/",
            "keep 01 2026-07-10T08:00:00+09:00 within-daily",
            "remove 02 2026-07-10T02:00:00+09:00",
            "keep 03 2026-07-09T23:00:00+09:00 within-daily",
            "remove 04 2026-07-09T10:00:00+09:00",
            "keep 05 2026-07-08T09:00:00+09:00 within-daily",
            "remove 06 2026-07-08T07:00:00+09:00",
            "remove 07 2026-07-07T12:00:00+09:00",
            "",
            "kept 3, removed 4",
        ])
    );
}

#[test]
fn zero_span_keeps_the_newest_time() {
    let got = run(
        "01 2026-02-02T02:00:00Z host=h paths=/\n\
         02 2026-02-02T02:00:00Z host=h paths=/\n\
         03 2026-02-02T01:59:59Z host=h paths=/\n",
        "keep-within = 0d",
    );
    assert_eq!(
        got,
        lines(&[
            "group host=h paths=/",
            "keep 02 2026-02-02T02:00:00Z within",
            "keep 01 2026-02-02T02:00:00Z within",
            "remove 03 2026-02-02T01:59:59Z",
            "",
            "kept 2, removed 1",
        ])
    );
}

#[test]
fn groups_by_tags_with_safety() {
    let got = run(
        "01 2026-03-01T00:00:00Z host=h paths=/ tags=pin,nightly\n\
         02 2026-03-02T00:00:00Z host=h paths=/ tags=nightly\n\
         03 2026-03-03T00:00:00Z host=h paths=/\n\
         04 2026-03-04T00:00:00Z host=h paths=/ tags=nightly\n\
         05 2026-03-05T00:00:00Z host=h paths=/ tags=pin\n\
         06 2026-03-06T00:00:00Z host=h paths=/\n",
        "keep-tag = pin\ngroup-by = tags",
    );
    assert_eq!(
        got,
        lines(&[
            "group tags=",
            "keep 06 2026-03-06T00:00:00Z safety",
            "remove 03 2026-03-03T00:00:00Z",
            "",
            "group tags=nightly",
            "keep 04 2026-03-04T00:00:00Z safety",
            "remove 02 2026-03-02T00:00:00Z",
            "",
            "group tags=nightly,pin",
            "keep 01 2026-03-01T00:00:00Z tag",
            "",
            "group tags=pin",
            "keep 05 2026-03-05T00:00:00Z tag",
            "",
            "kept 4, removed 2",
        ])
    );
}

#[test]
fn group_order_and_fields() {
    let snaps = "01 2026-03-01T00:00:00Z host=beta paths=/a\n\
                 02 2026-03-02T00:00:00Z host=alpha paths=/b,/a\n\
                 03 2026-03-03T00:00:00Z host=Alpha paths=/z\n\
                 04 2026-03-04T00:00:00Z host=alpha paths=/a\n\
                 05 2026-03-05T00:00:00Z host=alpha paths=/a,/b tags=x\n";
    assert_eq!(
        run(snaps, "keep-last = 1"),
        lines(&[
            "group host=Alpha paths=/z",
            "keep 03 2026-03-03T00:00:00Z last",
            "",
            "group host=alpha paths=/a",
            "keep 04 2026-03-04T00:00:00Z last",
            "",
            "group host=alpha paths=/a,/b",
            "keep 05 2026-03-05T00:00:00Z last",
            "remove 02 2026-03-02T00:00:00Z",
            "",
            "group host=beta paths=/a",
            "keep 01 2026-03-01T00:00:00Z last",
            "",
            "kept 4, removed 1",
        ])
    );
    assert_eq!(
        run(snaps, "keep-last = 2\ngroup-by = none"),
        lines(&[
            "group *",
            "keep 05 2026-03-05T00:00:00Z last",
            "keep 04 2026-03-04T00:00:00Z last",
            "remove 03 2026-03-03T00:00:00Z",
            "remove 02 2026-03-02T00:00:00Z",
            "remove 01 2026-03-01T00:00:00Z",
            "",
            "kept 2, removed 3",
        ])
    );
    assert_eq!(
        run(snaps, "keep-yearly = 1\ngroup-by = paths,host"),
        lines(&[
            "group host=Alpha paths=/z",
            "keep 03 2026-03-03T00:00:00Z yearly",
            "",
            "group host=alpha paths=/a",
            "keep 04 2026-03-04T00:00:00Z yearly",
            "",
            "group host=alpha paths=/a,/b",
            "keep 05 2026-03-05T00:00:00Z yearly",
            "remove 02 2026-03-02T00:00:00Z",
            "",
            "group host=beta paths=/a",
            "keep 01 2026-03-01T00:00:00Z yearly",
            "",
            "kept 4, removed 1",
        ])
    );
    assert_eq!(
        run(snaps, "keep-last = 1\ngroup-by = paths"),
        lines(&[
            "group paths=/a",
            "keep 04 2026-03-04T00:00:00Z last",
            "remove 01 2026-03-01T00:00:00Z",
            "",
            "group paths=/a,/b",
            "keep 05 2026-03-05T00:00:00Z last",
            "remove 02 2026-03-02T00:00:00Z",
            "",
            "group paths=/z",
            "keep 03 2026-03-03T00:00:00Z last",
            "",
            "kept 3, removed 2",
        ])
    );
}

#[test]
fn rules_are_independent_and_reasons_are_ordered() {
    let got = run(
        "01 2026-11-30T12:00:00Z host=h paths=/ tags=pin\n\
         02 2026-11-29T12:00:00Z host=h paths=/\n\
         03 2026-10-31T12:00:00Z host=h paths=/\n\
         04 2026-10-15T12:00:00Z host=h paths=/\n\
         05 2025-12-31T12:00:00Z host=h paths=/ tags=pin\n\
         06 2025-06-30T12:00:00Z host=h paths=/\n\
         07 2024-01-01T12:00:00Z host=h paths=/\n",
        "keep-tag = pin\nkeep-yearly = 3\nkeep-monthly = 3\nkeep-within = 1m\nkeep-last = 1\nkeep-weekly = 1",
    );
    assert_eq!(
        got,
        lines(&[
            "group host=h paths=/",
            "keep 01 2026-11-30T12:00:00Z last,weekly,monthly,yearly,within,tag",
            "keep 02 2026-11-29T12:00:00Z within",
            "keep 03 2026-10-31T12:00:00Z monthly,within",
            "remove 04 2026-10-15T12:00:00Z",
            "keep 05 2025-12-31T12:00:00Z monthly,yearly,tag",
            "remove 06 2025-06-30T12:00:00Z",
            "keep 07 2024-01-01T12:00:00Z yearly",
            "",
            "kept 5, removed 2",
        ])
    );
}

#[test]
fn counts_limit_the_buckets() {
    let got = run(
        "01 2026-05-20T00:00:00Z host=h paths=/\n\
         02 2026-05-03T00:00:00Z host=h paths=/\n\
         03 2026-04-28T00:00:00Z host=h paths=/\n\
         04 2026-04-02T00:00:00Z host=h paths=/\n\
         05 2026-02-10T00:00:00Z host=h paths=/\n\
         06 2025-11-11T00:00:00Z host=h paths=/\n",
        "keep-monthly = 3\nkeep-daily = 1\nkeep-yearly = -1",
    );
    assert_eq!(
        got,
        lines(&[
            "group host=h paths=/",
            "keep 01 2026-05-20T00:00:00Z daily,monthly,yearly",
            "remove 02 2026-05-03T00:00:00Z",
            "keep 03 2026-04-28T00:00:00Z monthly",
            "remove 04 2026-04-02T00:00:00Z",
            "keep 05 2026-02-10T00:00:00Z monthly",
            "keep 06 2025-11-11T00:00:00Z yearly",
            "",
            "kept 4, removed 2",
        ])
    );
}

#[test]
fn plan_structure() {
    let s = parse_snapshots(
        "01 2026-01-01T00:00:00Z host=h paths=/ tags=pin\n02 2026-01-02T00:00:00Z host=h paths=/\n",
    )
    .unwrap();
    let p = parse_policy("keep-tag = pin\ngroup-by = host,tags").unwrap();
    let pl = plan(&s, &p).unwrap();
    assert_eq!(pl.groups.len(), 2);
    assert_eq!(pl.groups[0].host.as_deref(), Some("h"));
    assert_eq!(pl.groups[0].paths, None);
    assert_eq!(pl.groups[0].tags, Some(vec![]));
    assert_eq!(pl.groups[0].decisions[0].reasons, vec![keepr::Reason::Safety]);
    assert!(pl.groups[0].decisions[0].keep);
    assert_eq!(pl.groups[1].tags, Some(vec!["pin".to_string()]));
    assert_eq!(pl.groups[1].decisions[0].reasons, vec![keepr::Reason::Tag]);
    let empty = plan(&[], &p).unwrap();
    assert!(empty.groups.is_empty());
    assert_eq!(render(&empty, &[], &p), "kept 0, removed 0\n");
}
