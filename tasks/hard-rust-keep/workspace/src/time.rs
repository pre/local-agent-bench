//! Instants, fixed UTC offsets and the civil calendar (proleptic Gregorian).

use std::fmt;

/// An instant: seconds since 1970-01-01T00:00:00Z.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Timestamp(pub i64);

/// A fixed offset from UTC in seconds, for example +02:00 is 7200.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash)]
pub struct Offset(pub i32);

/// A date and a time of day in some time zone.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Civil {
    pub year: i64,
    pub month: u32, // 1..=12
    pub day: u32,   // 1..=31
    pub hour: u32,
    pub minute: u32,
    pub second: u32,
}

/// Days from 1970-01-01 to the date (negative before it).
pub fn days_from_civil(year: i64, month: u32, day: u32) -> i64 {
    let y = if month <= 2 { year - 1 } else { year };
    let era = y.div_euclid(400);
    let yoe = y - era * 400;
    let m = month as i64;
    let doy = (153 * (if m > 2 { m - 3 } else { m + 9 }) + 2) / 5 + day as i64 - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    era * 146097 + doe - 719468
}

/// The date of a day number of `days_from_civil`.
pub fn civil_from_days(days: i64) -> (i64, u32, u32) {
    let z = days + 719468;
    let era = z.div_euclid(146097);
    let doe = z - era * 146097;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = (doy - (153 * mp + 2) / 5 + 1) as u32;
    let month = if mp < 10 { mp + 3 } else { mp - 9 } as u32;
    let year = yoe + era * 400 + if month <= 2 { 1 } else { 0 };
    (year, month, day)
}

pub fn is_leap_year(year: i64) -> bool {
    year % 4 == 0 && (year % 100 != 0 || year % 400 == 0)
}

pub fn days_in_month(year: i64, month: u32) -> u32 {
    match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        _ if is_leap_year(year) => 29,
        _ => 28,
    }
}

/// The day of the week of a day number: 0 is Monday, 6 is Sunday.
pub fn weekday(days: i64) -> u32 {
    // 1970-01-01 was a Thursday.
    (days + 3).rem_euclid(7) as u32
}

impl Timestamp {
    /// The civil date and time of the instant at the offset.
    pub fn to_civil(self, offset: Offset) -> Civil {
        let local = self.0 + offset.0 as i64;
        let days = local.div_euclid(86400);
        let secs = local.rem_euclid(86400) as u32;
        let (year, month, day) = civil_from_days(days);
        Civil { year, month, day, hour: secs / 3600, minute: secs / 60 % 60, second: secs % 60 }
    }

    /// The instant of a civil date and time at the offset.
    pub fn from_civil(c: Civil, offset: Offset) -> Timestamp {
        let days = days_from_civil(c.year, c.month, c.day);
        let local = days * 86400 + c.hour as i64 * 3600 + c.minute as i64 * 60 + c.second as i64;
        Timestamp(local - offset.0 as i64)
    }

    /// Reads "2026-03-14T09:30:00Z" or "2026-03-14T09:30:00+02:00".
    pub fn parse(s: &str) -> Result<Timestamp, String> {
        let bad = || format!("bad time {s:?}, expected YYYY-MM-DDTHH:MM:SS and Z or +HH:MM");
        if s.len() < 20 || !s.is_ascii() {
            return Err(bad());
        }
        let (dt, zone) = s.split_at(19);
        let b = dt.as_bytes();
        if b[4] != b'-' || b[7] != b'-' || b[10] != b'T' || b[13] != b':' || b[16] != b':' {
            return Err(bad());
        }
        let num = |r: std::ops::Range<usize>| dt[r].parse::<u32>().map_err(|_| bad());
        let c = Civil {
            year: num(0..4)? as i64,
            month: num(5..7)?,
            day: num(8..10)?,
            hour: num(11..13)?,
            minute: num(14..16)?,
            second: num(17..19)?,
        };
        if c.month == 0 || c.month > 12 || c.day == 0 || c.day > days_in_month(c.year, c.month) || c.hour > 23
            || c.minute > 59 || c.second > 59
        {
            return Err(bad());
        }
        let offset = if zone == "Z" { Offset(0) } else { Offset::parse(zone).map_err(|_| bad())? };
        Ok(Timestamp::from_civil(c, offset))
    }

    /// Formats the instant at the offset: "2026-03-14T09:30:00+02:00", or
    /// with "Z" when the offset is 0.
    pub fn format(self, offset: Offset) -> String {
        let c = self.to_civil(offset);
        format!(
            "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}{}",
            c.year, c.month, c.day, c.hour, c.minute, c.second, offset
        )
    }
}

impl Offset {
    /// Reads "+HH:MM" or "-HH:MM" (at most 14:00), or "Z".
    pub fn parse(s: &str) -> Result<Offset, String> {
        if s == "Z" {
            return Ok(Offset(0));
        }
        let bad = || format!("bad offset {s:?}, expected +HH:MM or -HH:MM");
        let b = s.as_bytes();
        if b.len() != 6 || (b[0] != b'+' && b[0] != b'-') || b[3] != b':' {
            return Err(bad());
        }
        let h: i32 = s[1..3].parse().map_err(|_| bad())?;
        let m: i32 = s[4..6].parse().map_err(|_| bad())?;
        if m > 59 || h * 60 + m > 14 * 60 {
            return Err(bad());
        }
        let secs = (h * 60 + m) * 60;
        Ok(Offset(if b[0] == b'-' { -secs } else { secs }))
    }
}

impl fmt::Display for Offset {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        if self.0 == 0 {
            return f.write_str("Z");
        }
        let sign = if self.0 < 0 { '-' } else { '+' };
        let m = self.0.unsigned_abs() / 60;
        write!(f, "{sign}{:02}:{:02}", m / 60, m % 60)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn civil_round_trip() {
        for days in [-1_000_000, -719468, -1, 0, 1, 11016, 20000, 2_000_000] {
            let (y, m, d) = civil_from_days(days);
            assert_eq!(days_from_civil(y, m, d), days);
        }
        assert_eq!(civil_from_days(0), (1970, 1, 1));
        assert_eq!(weekday(0), 3);
    }

    #[test]
    fn parse_and_format() {
        let t = Timestamp::parse("2026-03-14T09:30:00+02:00").unwrap();
        assert_eq!(t, Timestamp::parse("2026-03-14T07:30:00Z").unwrap());
        assert_eq!(t.format(Offset(0)), "2026-03-14T07:30:00Z");
        assert_eq!(t.format(Offset::parse("-05:30").unwrap()), "2026-03-14T02:00:00-05:30");
        assert!(Timestamp::parse("2026-02-29T00:00:00Z").is_err());
        assert!(Timestamp::parse("2024-02-29T00:00:00Z").is_ok());
        assert!(Timestamp::parse("2026-03-14 09:30:00Z").is_err());
    }
}
