use std::fmt;
use std::str::FromStr;

/// An amount of memory in bytes.
///
/// The text form uses the notation of Kubernetes resource quantities,
/// limited to what the node inventory needs:
///
/// * `<digits>` is a number of bytes, for example `1048576`.
/// * `<digits><suffix>` multiplies the number by the suffix. The decimal
///   suffixes are `k` (10^3), `M` (10^6), `G` (10^9) and `T` (10^12). The
///   binary suffixes are `Ki` (2^10), `Mi` (2^20), `Gi` (2^30) and `Ti`
///   (2^40). The suffixes are case sensitive.
/// * `<digits>.<digits>` with or without a suffix is a decimal fraction,
///   for example `1.5Gi` (1610612736 bytes). The calculation is exact:
///   `2.3k` is 2300 bytes. When the result is not a whole number of bytes,
///   it is rounded down: `0.5` is 0 bytes and `1.0001k` is 1000 bytes.
///
/// There must be at least one digit before and after the dot. A sign, an
/// exponent, spaces and other suffixes are not allowed.
///
/// Parse errors:
///
/// * [`QuantityError::Empty`] for an empty text.
/// * [`QuantityError::Overflow`] when the value is larger than `u64::MAX`
///   bytes.
/// * [`QuantityError::Invalid`] for all other errors.
///
/// [`Display`](fmt::Display) writes the value with the largest binary
/// suffix that gives a whole number, for example `1536Mi`. Parsing the
/// text that `Display` writes gives the same value.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Quantity(u64);

impl Quantity {
    pub const ZERO: Quantity = Quantity(0);

    pub const fn from_bytes(bytes: u64) -> Self {
        Quantity(bytes)
    }

    pub const fn bytes(self) -> u64 {
        self.0
    }

    pub fn saturating_sub(self, other: Quantity) -> Quantity {
        Quantity(self.0.saturating_sub(other.0))
    }
}

impl fmt::Display for Quantity {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        const UNITS: [(&str, u64); 4] = [("Ti", 1 << 40), ("Gi", 1 << 30), ("Mi", 1 << 20), ("Ki", 1 << 10)];
        for (suffix, size) in UNITS {
            if self.0 != 0 && self.0.is_multiple_of(size) {
                return write!(f, "{}{}", self.0 / size, suffix);
            }
        }
        write!(f, "{}", self.0)
    }
}

/// The error of parsing a [`Quantity`]. The string is the input text.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum QuantityError {
    Empty,
    Invalid(String),
    Overflow(String),
}

impl fmt::Display for QuantityError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            QuantityError::Empty => write!(f, "empty quantity"),
            QuantityError::Invalid(s) => write!(f, "invalid quantity {s:?}"),
            QuantityError::Overflow(s) => write!(f, "quantity {s:?} is too large"),
        }
    }
}

impl std::error::Error for QuantityError {}

impl FromStr for Quantity {
    type Err = QuantityError;

    fn from_str(text: &str) -> Result<Self, Self::Err> {
        if text.is_empty() {
            return Err(QuantityError::Empty);
        }
        let invalid = || QuantityError::Invalid(text.to_string());
        let overflow = || QuantityError::Overflow(text.to_string());

        let number_end = text
            .find(|c: char| !c.is_ascii_digit() && c != '.')
            .unwrap_or(text.len());
        let (number, suffix) = text.split_at(number_end);
        let multiplier: u128 = match suffix {
            "" => 1,
            "k" => 1_000,
            "M" => 1_000_000,
            "G" => 1_000_000_000,
            "T" => 1_000_000_000_000,
            "Ki" => 1 << 10,
            "Mi" => 1 << 20,
            "Gi" => 1 << 30,
            "Ti" => 1 << 40,
            _ => return Err(invalid()),
        };

        let (whole, fraction) = match number.split_once('.') {
            Some((whole, fraction)) => (whole, Some(fraction)),
            None => (number, None),
        };
        let is_digits = |t: &str| !t.is_empty() && t.bytes().all(|b| b.is_ascii_digit());
        if !is_digits(whole) || fraction.is_some_and(|f| !is_digits(f)) {
            return Err(invalid());
        }

        // The text has only digits here, so a parse error is an overflow.
        let whole: u128 = whole.parse().map_err(|_| overflow())?;
        let mut bytes = whole.checked_mul(multiplier).ok_or_else(overflow)?;

        if let Some(fraction) = fraction {
            // 24 digits keep the product below u128::MAX.
            let digits = &fraction[..fraction.len().min(24)];
            let numerator: u128 = digits.parse().map_err(|_| invalid())?;
            let denominator = 10u128.pow(digits.len() as u32);
            bytes += numerator * multiplier / denominator;
        }

        u64::try_from(bytes).map(Quantity).map_err(|_| overflow())
    }
}
