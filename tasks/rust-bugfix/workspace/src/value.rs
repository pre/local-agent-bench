use std::fmt;
use std::iter::Peekable;
use std::str::Chars;

/// A value of a configuration key.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Value {
    Str(String),
    Int(i64),
    Bool(bool),
    List(Vec<Value>),
}

impl fmt::Display for Value {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Value::Str(s) => write!(f, "{s:?}"),
            Value::Int(n) => write!(f, "{n}"),
            Value::Bool(b) => write!(f, "{b}"),
            Value::List(items) => {
                write!(f, "[")?;
                for (i, item) in items.iter().enumerate() {
                    if i > 0 {
                        write!(f, ", ")?;
                    }
                    write!(f, "{item}")?;
                }
                write!(f, "]")
            }
        }
    }
}

/// Parses the text after `=`. The comment is already removed and the text
/// is trimmed.
pub(crate) fn parse(raw: &str) -> Result<Value, String> {
    if raw.is_empty() {
        return Err("missing value".to_string());
    }
    let mut chars = raw.chars().peekable();
    let value = parse_value(&mut chars, false)?;
    skip_spaces(&mut chars);
    match chars.peek() {
        None => Ok(value),
        Some(_) => {
            let rest: String = chars.collect();
            Err(format!("unexpected characters after value: {rest:?}"))
        }
    }
}

fn parse_value(chars: &mut Peekable<Chars<'_>>, in_list: bool) -> Result<Value, String> {
    skip_spaces(chars);
    match chars.peek() {
        Some('"') => {
            chars.next();
            parse_double_quoted(chars).map(Value::Str)
        }
        Some('\'') => {
            chars.next();
            parse_single_quoted(chars).map(Value::Str)
        }
        Some('[') if in_list => Err("nested lists are not supported".to_string()),
        Some('[') => {
            chars.next();
            parse_list(chars)
        }
        Some(_) => parse_scalar(chars),
        None => Err("missing value".to_string()),
    }
}

fn parse_double_quoted(chars: &mut Peekable<Chars<'_>>) -> Result<String, String> {
    let mut out = String::new();
    while let Some(c) = chars.next() {
        match c {
            '"' => return Ok(out),
            '\\' => match chars.next() {
                Some('\\') => out.push('\\'),
                Some('"') => out.push('"'),
                Some('n') => out.push('\n'),
                Some('t') => out.push('\t'),
                Some(other) => return Err(format!("unknown escape \\{other}")),
                None => break,
            },
            _ => out.push(c),
        }
    }
    Err("unterminated string".to_string())
}

fn parse_single_quoted(chars: &mut Peekable<Chars<'_>>) -> Result<String, String> {
    let mut out = String::new();
    for c in chars.by_ref() {
        if c == '\'' {
            return Ok(out);
        }
        out.push(c);
    }
    Err("unterminated string".to_string())
}

fn parse_list(chars: &mut Peekable<Chars<'_>>) -> Result<Value, String> {
    let mut items = Vec::new();
    skip_spaces(chars);
    if chars.peek() == Some(&']') {
        chars.next();
        return Ok(Value::List(items));
    }
    loop {
        items.push(parse_value(chars, true)?);
        skip_spaces(chars);
        match chars.next() {
            Some(',') => continue,
            Some(']') => return Ok(Value::List(items)),
            Some(c) => return Err(format!("expected ',' or ']' in list, found {c:?}")),
            None => return Err("list without closing ']'".to_string()),
        }
    }
}

/// Parses an integer or a boolean. It stops at a space, a comma or a `]`.
fn parse_scalar(chars: &mut Peekable<Chars<'_>>) -> Result<Value, String> {
    let mut word = String::new();
    while let Some(&c) = chars.peek() {
        if c.is_whitespace() || c == ',' || c == ']' {
            break;
        }
        word.push(c);
        chars.next();
    }
    match word.as_str() {
        "true" => Ok(Value::Bool(true)),
        "false" => Ok(Value::Bool(false)),
        _ => word
            .parse::<i64>()
            .map(Value::Int)
            .map_err(|_| format!("invalid value {word:?}")),
    }
}

fn skip_spaces(chars: &mut Peekable<Chars<'_>>) {
    while chars.peek().is_some_and(|c| c.is_whitespace()) {
        chars.next();
    }
}
