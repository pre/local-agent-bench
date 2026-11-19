//! The retention planner. docs/RETENTION.md, section "Rules", describes the
//! behavior.

use std::collections::BTreeMap;
use std::fmt;

use crate::input::{Policy, Snapshot, Span};
use crate::time::{civil_from_days, days_from_civil, days_in_month, is_leap_year, weekday, Civil, Timestamp};

/// Why a snapshot is kept. The order of the variants is the order of R11.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum Reason {
    Last,
    Hourly,
    Daily,
    Weekly,
    Monthly,
    Yearly,
    Within,
    WithinDaily,
    Tag,
    Safety,
}

impl Reason {
    /// The name in the output: "last", ..., "within-daily", "tag", "safety".
    pub fn name(self) -> &'static str {
        match self {
            Reason::Last => "last",
            Reason::Hourly => "hourly",
            Reason::Daily => "daily",
            Reason::Weekly => "weekly",
            Reason::Monthly => "monthly",
            Reason::Yearly => "yearly",
            Reason::Within => "within",
            Reason::WithinDaily => "within-daily",
            Reason::Tag => "tag",
            Reason::Safety => "safety",
        }
    }
}

/// The decision for one snapshot. `reasons` is empty for a removed snapshot.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Decision {
    pub id: String,
    pub keep: bool,
    pub reasons: Vec<Reason>,
}

/// One group (R2). A field is None when it is not in `group-by`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Group {
    pub host: Option<String>,
    pub paths: Option<Vec<String>>,
    pub tags: Option<Vec<String>>,
    /// In the order of R3.
    pub decisions: Vec<Decision>,
}

/// The plan: the groups in the order of R2.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Plan {
    pub groups: Vec<Group>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum PlanError {
    /// R1.
    EmptyPolicy,
}

impl fmt::Display for PlanError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            PlanError::EmptyPolicy => f.write_str("the policy has no active rule"),
        }
    }
}

impl std::error::Error for PlanError {}

/// Makes the plan (R1 to R11).
pub fn plan(snapshots: &[Snapshot], policy: &Policy) -> Result<Plan, PlanError> {
    let active = |c: Option<i64>| matches!(c, Some(n) if n != 0);
    let any_rule = [policy.keep_last, policy.keep_hourly, policy.keep_daily, policy.keep_weekly, policy.keep_monthly, policy.keep_yearly]
        .into_iter()
        .any(active)
        || policy.keep_within.is_some()
        || policy.keep_within_daily.is_some()
        || !policy.keep_tags.is_empty();
    if !any_rule {
        return Err(PlanError::EmptyPolicy);
    }

    type Key = (Option<String>, Option<String>, Option<String>);
    let g = policy.group_by;
    let mut groups: BTreeMap<Key, Vec<&Snapshot>> = BTreeMap::new();
    for s in snapshots {
        let key = (
            g.host.then(|| s.host.clone()),
            g.paths.then(|| s.paths.join(",")),
            g.tags.then(|| s.tags.join(",")),
        );
        groups.entry(key).or_default().push(s);
    }

    let mut out = Vec::new();
    for (_, mut members) in groups {
        members.sort_by(|a, b| b.time.cmp(&a.time).then_with(|| b.id.cmp(&a.id)));
        let first = members[0];
        out.push(Group {
            host: g.host.then(|| first.host.clone()),
            paths: g.paths.then(|| first.paths.clone()),
            tags: g.tags.then(|| first.tags.clone()),
            decisions: decide(&members, policy),
        });
    }
    Ok(Plan { groups: out })
}

fn decide(members: &[&Snapshot], policy: &Policy) -> Vec<Decision> {
    let tz = policy.timezone;
    let n = members.len();
    let mut reasons: Vec<Vec<Reason>> = vec![Vec::new(); n];
    let local: Vec<Civil> = members.iter().map(|s| s.time.to_civil(tz)).collect();

    if let Some(count) = policy.keep_last {
        for r in reasons.iter_mut().take(limit(count, n)) {
            r.push(Reason::Last);
        }
    }
    let buckets: [(Option<i64>, Reason, fn(&Civil) -> (i64, i64, i64)); 5] = [
        (policy.keep_hourly, Reason::Hourly, |c| (days_from_civil(c.year, c.month, c.day), c.hour as i64, 0)),
        (policy.keep_daily, Reason::Daily, |c| (days_from_civil(c.year, c.month, c.day), 0, 0)),
        (policy.keep_weekly, Reason::Weekly, |c| iso_week(c)),
        (policy.keep_monthly, Reason::Monthly, |c| (c.year, c.month as i64, 0)),
        (policy.keep_yearly, Reason::Yearly, |c| (c.year, 0, 0)),
    ];
    for (count, reason, bucket) in buckets {
        let Some(count) = count else { continue };
        let max = limit(count, n);
        let mut kept = 0;
        let mut last = None;
        for (i, c) in local.iter().enumerate() {
            if kept == max {
                break;
            }
            let b = bucket(c);
            if last != Some(b) {
                reasons[i].push(reason);
                kept += 1;
                last = Some(b);
            }
        }
    }
    if let Some(span) = policy.keep_within {
        let cutoff = cutoff(members[0].time, span, policy);
        for (i, s) in members.iter().enumerate() {
            if s.time >= cutoff {
                reasons[i].push(Reason::Within);
            }
        }
    }
    if let Some(span) = policy.keep_within_daily {
        let cutoff = cutoff(members[0].time, span, policy);
        let mut last = None;
        for (i, s) in members.iter().enumerate() {
            if s.time < cutoff {
                break;
            }
            let day = days_from_civil(local[i].year, local[i].month, local[i].day);
            if last != Some(day) {
                reasons[i].push(Reason::WithinDaily);
                last = Some(day);
            }
        }
    }
    for (i, s) in members.iter().enumerate() {
        if s.tags.iter().any(|t| policy.keep_tags.contains(t)) {
            reasons[i].push(Reason::Tag);
        }
    }
    if reasons.iter().all(|r| r.is_empty()) {
        reasons[0].push(Reason::Safety);
    }
    members
        .iter()
        .zip(reasons)
        .map(|(s, mut r)| {
            r.sort();
            r.dedup();
            Decision { id: s.id.clone(), keep: !r.is_empty(), reasons: r }
        })
        .collect()
}

fn limit(count: i64, n: usize) -> usize {
    if count < 0 {
        n
    } else {
        count as usize
    }
}

/// The ISO 8601 week of a date: (week-year, week, 0).
fn iso_week(c: &Civil) -> (i64, i64, i64) {
    let days = days_from_civil(c.year, c.month, c.day);
    let thursday = days - weekday(days) as i64 + 3;
    let (year, _, _) = civil_from_days(thursday);
    let week = (thursday - days_from_civil(year, 1, 1)) / 7 + 1;
    (year, week, 0)
}

/// R7: the local time of `newest` minus the span.
fn cutoff(newest: Timestamp, span: Span, policy: &Policy) -> Timestamp {
    let mut c = newest.to_civil(policy.timezone);
    c.year -= span.years as i64;
    if c.month == 2 && c.day == 29 && !is_leap_year(c.year) {
        c.day = 28;
    }
    let months = c.year * 12 + (c.month as i64 - 1) - span.months as i64;
    c.year = months.div_euclid(12);
    c.month = (months.rem_euclid(12) + 1) as u32;
    c.day = c.day.min(days_in_month(c.year, c.month));
    let (y, m, d) = civil_from_days(days_from_civil(c.year, c.month, c.day) - span.days as i64);
    c.year = y;
    c.month = m;
    c.day = d;
    Timestamp(Timestamp::from_civil(c, policy.timezone).0 - span.hours as i64 * 3600)
}

/// Gives the text of the plan (R12). `snapshots` are the snapshots that the
/// plan was made from.
pub fn render(plan: &Plan, snapshots: &[Snapshot], policy: &Policy) -> String {
    let times: BTreeMap<&str, Timestamp> = snapshots.iter().map(|s| (s.id.as_str(), s.time)).collect();
    let mut out = String::new();
    let (mut kept, mut removed) = (0, 0);
    for g in &plan.groups {
        out.push_str("group");
        if g.host.is_none() && g.paths.is_none() && g.tags.is_none() {
            out.push_str(" *");
        }
        if let Some(h) = &g.host {
            out.push_str(&format!(" host={h}"));
        }
        if let Some(p) = &g.paths {
            out.push_str(&format!(" paths={}", p.join(",")));
        }
        if let Some(t) = &g.tags {
            out.push_str(&format!(" tags={}", t.join(",")));
        }
        out.push('\n');
        for d in &g.decisions {
            let time = times[d.id.as_str()].format(policy.timezone);
            if d.keep {
                kept += 1;
                let names: Vec<&str> = d.reasons.iter().map(|r| r.name()).collect();
                out.push_str(&format!("keep {} {} {}\n", d.id, time, names.join(",")));
            } else {
                removed += 1;
                out.push_str(&format!("remove {} {}\n", d.id, time));
            }
        }
        out.push('\n');
    }
    out.push_str(&format!("kept {kept}, removed {removed}\n"));
    out
}
