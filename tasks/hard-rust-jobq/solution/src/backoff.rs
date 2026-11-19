//! The delay before a retry.

/// Exponential backoff with an upper limit.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct RetryPolicy {
    /// The delay after the first failed attempt, in milliseconds.
    pub base_ms: u64,
    /// The largest delay, in milliseconds.
    pub max_ms: u64,
}

impl Default for RetryPolicy {
    fn default() -> Self {
        RetryPolicy { base_ms: 1000, max_ms: 3_600_000 }
    }
}

impl RetryPolicy {
    /// The delay after the failed attempt number `attempt` (1 for the first
    /// attempt): `base_ms * 2^(attempt - 1)`, but not more than `max_ms`.
    /// See docs/SCHEDULER.md, "Retries".
    pub fn delay(&self, attempt: u32) -> u64 {
        let doublings = attempt.saturating_sub(1);
        let delay = 1u64
            .checked_shl(doublings)
            .and_then(|factor| self.base_ms.checked_mul(factor));
        match delay {
            Some(d) => d.min(self.max_ms),
            None => self.max_ms,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn doubles_until_the_limit() {
        let p = RetryPolicy { base_ms: 100, max_ms: 1000 };
        let got: Vec<u64> = (1..=6).map(|a| p.delay(a)).collect();
        assert_eq!(got, vec![100, 200, 400, 800, 1000, 1000]);
    }

    #[test]
    fn default_policy() {
        let p = RetryPolicy::default();
        assert_eq!(p.delay(1), 1000);
        assert_eq!(p.delay(12), 2_048_000);
        assert_eq!(p.delay(13), 3_600_000);
        assert_eq!(p.delay(100), 3_600_000);
    }
}
