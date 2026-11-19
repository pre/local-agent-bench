"""Go durations: the text of time.ParseDuration and time.Duration.String()."""

import re
from datetime import timedelta
from fractions import Fraction

_NS = {
    "ns": 1,
    "us": 1_000,
    "µs": 1_000,  # micro sign
    "μs": 1_000,  # Greek small letter mu
    "ms": 1_000_000,
    "s": 1_000_000_000,
    "m": 60 * 1_000_000_000,
    "h": 3600 * 1_000_000_000,
}
_PART = re.compile(r"(\d+\.?\d*|\.\d+)(ns|us|µs|μs|ms|s|m|h)")


def to_nanoseconds(td):
    return ((td.days * 86400 + td.seconds) * 1_000_000 + td.microseconds) * 1000


def parse_duration(text):
    """Parse a Go duration into a timedelta (truncated to microseconds)."""
    s = text
    negative = False
    if s[:1] in ("+", "-"):
        negative = s[0] == "-"
        s = s[1:]
    if s == "0":
        return timedelta(0)
    if not s:
        raise ValueError(f"invalid duration {text!r}")
    total = Fraction(0)
    pos = 0
    while pos < len(s):
        m = _PART.match(s, pos)
        if not m:
            raise ValueError(f"invalid duration {text!r}")
        total += Fraction(m.group(1).rstrip(".") or "0") * _NS[m.group(2)]
        pos = m.end()
    micros = int(total) // 1000
    return timedelta(microseconds=-micros if negative else micros)


def _fraction(value, digits):
    whole, frac = divmod(value, 10**digits)
    if frac == 0:
        return str(whole)
    return f"{whole}." + str(frac).rjust(digits, "0").rstrip("0")


def format_duration(td):
    """Return the text of Go time.Duration.String() for a timedelta."""
    ns = to_nanoseconds(td)
    if ns == 0:
        return "0s"
    sign = "-" if ns < 0 else ""
    u = abs(ns)
    if u < 1_000:
        text = f"{u}ns"
    elif u < 1_000_000:
        text = _fraction(u, 3) + "µs"
    elif u < 1_000_000_000:
        text = _fraction(u, 6) + "ms"
    else:
        hours, rest = divmod(u, 3600 * 1_000_000_000)
        minutes, rest = divmod(rest, 60 * 1_000_000_000)
        text = _fraction(rest, 9) + "s"
        if hours:
            text = f"{hours}h{minutes}m{text}"
        elif minutes:
            text = f"{minutes}m{text}"
    return sign + text
