//! Parser for the configuration file of the CI runner agent.
//!
//! The format is line based:
//!
//! ```text
//! # A comment line.
//! name = "runner-01"
//! concurrency = 4
//!
//! [cache]
//! dir = "/var/cache/runner"    # a comment after a value
//! max_size_mb = 2048
//! enabled = true
//! tags = ["gpu", 'mi300', "x86_64"]
//! ```
//!
//! Rules:
//!
//! * A `#` outside of a quoted string starts a comment that continues to the
//!   end of the line.
//! * A key inside a `[section]` is stored as `section.key`.
//! * A double-quoted string knows the escapes `\\`, `\"`, `\n` and `\t`.
//!   Any other escape is an error.
//! * A single-quoted string is literal. A backslash in it has no special
//!   meaning, and it cannot contain a single quote.
//! * Integers are `i64` with an optional sign. Booleans are `true` and
//!   `false`.
//! * A list holds values of the types above, separated by commas. Lists do
//!   not nest.
//! * A key can occur only once in a section.

mod value;

use std::collections::BTreeMap;
use std::fmt;

pub use value::Value;

/// An error with the line number (starting at 1) where it occurred.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ParseError {
    pub line: usize,
    pub msg: String,
}

impl fmt::Display for ParseError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "line {}: {}", self.line, self.msg)
    }
}

impl std::error::Error for ParseError {}

/// A parsed configuration file.
#[derive(Debug, Default, Clone, PartialEq)]
pub struct Config {
    entries: BTreeMap<String, Value>,
}

impl Config {
    /// Returns the value of `key`. Use `section.key` for a key in a section.
    pub fn get(&self, key: &str) -> Option<&Value> {
        self.entries.get(key)
    }

    /// Returns the value of `key` if it is a string.
    pub fn get_str(&self, key: &str) -> Option<&str> {
        match self.get(key)? {
            Value::Str(s) => Some(s),
            _ => None,
        }
    }

    /// Returns all keys in sorted order.
    pub fn keys(&self) -> impl Iterator<Item = &str> {
        self.entries.keys().map(String::as_str)
    }

    pub fn len(&self) -> usize {
        self.entries.len()
    }

    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }
}

/// Parses a complete configuration file.
pub fn parse(input: &str) -> Result<Config, ParseError> {
    let mut config = Config::default();
    let mut section = String::new();

    for (idx, raw) in input.lines().enumerate() {
        let line_no = idx + 1;
        let err = |msg: String| ParseError { line: line_no, msg };

        let line = strip_comment(raw).trim();
        if line.is_empty() {
            continue;
        }

        if let Some(rest) = line.strip_prefix('[') {
            let name = rest
                .strip_suffix(']')
                .ok_or_else(|| err("section header without closing ']'".to_string()))?
                .trim();
            if !is_valid_key(name) {
                return Err(err(format!("invalid section name {name:?}")));
            }
            section = name.to_string();
            continue;
        }

        let (key, raw_value) = line
            .split_once('=')
            .ok_or_else(|| err("expected 'key = value'".to_string()))?;
        let key = key.trim();
        if !is_valid_key(key) {
            return Err(err(format!("invalid key {key:?}")));
        }

        let value = value::parse(raw_value.trim()).map_err(err)?;

        let full_key = if section.is_empty() {
            key.to_string()
        } else {
            format!("{section}.{key}")
        };
        if config.entries.contains_key(&full_key) {
            return Err(err(format!("duplicate key {full_key:?}")));
        }
        config.entries.insert(full_key, value);
    }

    Ok(config)
}

fn is_valid_key(key: &str) -> bool {
    !key.is_empty()
        && key
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-')
}

/// Removes a trailing comment. A `#` inside a quoted string is not a comment.
fn strip_comment(line: &str) -> &str {
    let mut quote: Option<char> = None;
    let mut escaped = false;
    for (i, c) in line.char_indices() {
        match quote {
            Some('"') if escaped => escaped = false,
            Some('"') if c == '\\' => escaped = true,
            Some(q) if c == q => quote = None,
            Some(_) => {}
            None if c == '"' || c == '\'' => quote = Some(c),
            None if c == '#' => return &line[..i],
            None => {}
        }
    }
    line
}
