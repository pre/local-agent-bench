//! The snapshot list and the policy file. docs/RETENTION.md, section
//! "Files", describes the formats.

use std::collections::HashSet;
use std::fmt;

use crate::time::{Offset, Timestamp};

/// One backup snapshot.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Snapshot {
    pub id: String,
    pub time: Timestamp,
    pub host: String,
    /// Sorted, without duplicates, not empty.
    pub paths: Vec<String>,
    /// Sorted, without duplicates, can be empty.
    pub tags: Vec<String>,
}

/// A calendar span such as "1y2m3d4h".
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Span {
    pub years: u32,
    pub months: u32,
    pub days: u32,
    pub hours: u32,
}

/// The fields that make the group of a snapshot.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct GroupBy {
    pub host: bool,
    pub paths: bool,
    pub tags: bool,
}

/// A retention policy. A count is None when the policy does not set it;
/// -1 means "no limit".
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Policy {
    pub keep_last: Option<i64>,
    pub keep_hourly: Option<i64>,
    pub keep_daily: Option<i64>,
    pub keep_weekly: Option<i64>,
    pub keep_monthly: Option<i64>,
    pub keep_yearly: Option<i64>,
    pub keep_within: Option<Span>,
    pub keep_within_daily: Option<Span>,
    pub keep_tags: Vec<String>,
    pub group_by: GroupBy,
    pub timezone: Offset,
}

impl Default for Policy {
    fn default() -> Self {
        Policy {
            keep_last: None,
            keep_hourly: None,
            keep_daily: None,
            keep_weekly: None,
            keep_monthly: None,
            keep_yearly: None,
            keep_within: None,
            keep_within_daily: None,
            keep_tags: Vec::new(),
            group_by: GroupBy { host: true, paths: true, tags: false },
            timezone: Offset(0),
        }
    }
}

/// An error in an input file, with the line number.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct InputError {
    pub line: usize,
    pub message: String,
}

impl fmt::Display for InputError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "line {}: {}", self.line, self.message)
    }
}

impl std::error::Error for InputError {}

fn content(raw: &str) -> &str {
    raw.split('#').next().unwrap_or("").trim()
}

fn list(v: &str) -> Vec<String> {
    let mut items: Vec<String> = v.split(',').filter(|s| !s.is_empty()).map(str::to_string).collect();
    items.sort();
    items.dedup();
    items
}

/// Reads a snapshot list.
pub fn parse_snapshots(text: &str) -> Result<Vec<Snapshot>, InputError> {
    let mut out = Vec::new();
    let mut ids = HashSet::new();
    for (i, raw) in text.lines().enumerate() {
        let line = i + 1;
        let err = |message: String| InputError { line, message };
        let c = content(raw);
        if c.is_empty() {
            continue;
        }
        let mut words = c.split_whitespace();
        let id = words.next().unwrap_or_default().to_string();
        if id.is_empty() || !id.chars().all(|ch| ch.is_ascii_hexdigit()) {
            return Err(err(format!("bad snapshot id {id:?}")));
        }
        if !ids.insert(id.clone()) {
            return Err(err(format!("snapshot id {id} is used twice")));
        }
        let time = Timestamp::parse(words.next().ok_or_else(|| err("missing time".into()))?).map_err(err)?;
        let (mut host, mut paths, mut tags) = (None, None, Vec::new());
        for w in words {
            let (k, v) = w.split_once('=').ok_or_else(|| err(format!("expected key=value, found {w:?}")))?;
            match k {
                "host" if !v.is_empty() => host = Some(v.to_string()),
                "paths" if !list(v).is_empty() => paths = Some(list(v)),
                "tags" => tags = list(v),
                _ => return Err(err(format!("bad field {w:?}"))),
            }
        }
        let host = host.ok_or_else(|| err("missing host=".into()))?;
        let paths = paths.ok_or_else(|| err("missing paths=".into()))?;
        out.push(Snapshot { id, time, host, paths, tags });
    }
    Ok(out)
}

/// Reads a span such as "1y2m3d4h". Each unit is optional, but the order is
/// y, m, d, h and at least one unit is needed.
pub fn parse_span(s: &str) -> Result<Span, String> {
    let mut span = Span::default();
    let mut rest = s;
    let mut last_unit = 0;
    if s.is_empty() {
        return Err("empty span".into());
    }
    while !rest.is_empty() {
        let digits = rest.find(|c: char| !c.is_ascii_digit()).ok_or_else(|| format!("span {s:?}: missing unit"))?;
        if digits == 0 {
            return Err(format!("span {s:?}: missing number"));
        }
        let n: u32 = rest[..digits].parse().map_err(|_| format!("span {s:?}: number is too large"))?;
        let unit = rest[digits..].chars().next().unwrap();
        let order = match unit {
            'y' => 1,
            'm' => 2,
            'd' => 3,
            'h' => 4,
            _ => return Err(format!("span {s:?}: unknown unit {unit:?}")),
        };
        if order <= last_unit {
            return Err(format!("span {s:?}: units must be in the order y, m, d, h"));
        }
        last_unit = order;
        match unit {
            'y' => span.years = n,
            'm' => span.months = n,
            'd' => span.days = n,
            _ => span.hours = n,
        }
        rest = &rest[digits + 1..];
    }
    Ok(span)
}

/// Reads a policy file.
pub fn parse_policy(text: &str) -> Result<Policy, InputError> {
    let mut p = Policy::default();
    for (i, raw) in text.lines().enumerate() {
        let line = i + 1;
        let err = |message: String| InputError { line, message };
        let c = content(raw);
        if c.is_empty() {
            continue;
        }
        let (k, v) = c.split_once('=').ok_or_else(|| err("expected key = value".into()))?;
        let (k, v) = (k.trim(), v.trim());
        let count = |v: &str| -> Result<Option<i64>, InputError> {
            match v.parse::<i64>() {
                Ok(n) if n >= -1 => Ok(Some(n)),
                _ => Err(err(format!("{k}: expected a count (-1 or more), found {v:?}"))),
            }
        };
        match k {
            "keep-last" => p.keep_last = count(v)?,
            "keep-hourly" => p.keep_hourly = count(v)?,
            "keep-daily" => p.keep_daily = count(v)?,
            "keep-weekly" => p.keep_weekly = count(v)?,
            "keep-monthly" => p.keep_monthly = count(v)?,
            "keep-yearly" => p.keep_yearly = count(v)?,
            "keep-within" => p.keep_within = Some(parse_span(v).map_err(err)?),
            "keep-within-daily" => p.keep_within_daily = Some(parse_span(v).map_err(err)?),
            "keep-tag" if !v.is_empty() && !v.contains(',') => p.keep_tags.push(v.to_string()),
            "group-by" => {
                let mut g = GroupBy { host: false, paths: false, tags: false };
                if v != "none" {
                    for f in v.split(',') {
                        match f.trim() {
                            "host" => g.host = true,
                            "paths" => g.paths = true,
                            "tags" => g.tags = true,
                            other => return Err(err(format!("group-by: unknown field {other:?}"))),
                        }
                    }
                }
                p.group_by = g;
            }
            "timezone" => p.timezone = Offset::parse(v).map_err(err)?,
            _ => return Err(err(format!("unknown key {k:?}"))),
        }
    }
    Ok(p)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn snapshots() {
        let s = parse_snapshots("# list\na1 2026-01-02T03:04:05Z host=h paths=/b,/a,/b tags=x\n\nb2 2026-01-02T03:04:05+01:00 host=h paths=/a\n").unwrap();
        assert_eq!(s.len(), 2);
        assert_eq!(s[0].paths, vec!["/a", "/b"]);
        assert_eq!(s[0].tags, vec!["x"]);
        assert!(s[1].tags.is_empty());
        assert_eq!(s[1].time.0 + 3600, s[0].time.0);
        assert_eq!(parse_snapshots("a1 2026-01-02T03:04:05Z host=h").unwrap_err().line, 1);
        assert_eq!(parse_snapshots("a1 2026-01-02T03:04:05Z host=h paths=/\na1 2026-01-02T03:04:05Z host=h paths=/").unwrap_err().line, 2);
    }

    #[test]
    fn spans() {
        assert_eq!(parse_span("1y2m3d4h").unwrap(), Span { years: 1, months: 2, days: 3, hours: 4 });
        assert_eq!(parse_span("36h").unwrap(), Span { hours: 36, ..Span::default() });
        for bad in ["", "3", "d", "1d1y", "1w", "1d1d"] {
            assert!(parse_span(bad).is_err(), "{bad}");
        }
    }

    #[test]
    fn policy() {
        let p = parse_policy("keep-daily = 7\nkeep-last=-1\nkeep-tag = pin\nkeep-tag = gold\ngroup-by = host\ntimezone = +05:30\n").unwrap();
        assert_eq!(p.keep_daily, Some(7));
        assert_eq!(p.keep_last, Some(-1));
        assert_eq!(p.keep_tags, vec!["pin", "gold"]);
        assert_eq!(p.group_by, GroupBy { host: true, paths: false, tags: false });
        assert_eq!(p.timezone, Offset(19800));
        assert!(parse_policy("keep-daily = -2").is_err());
        assert!(parse_policy("keep-weekly 3").is_err());
    }
}
