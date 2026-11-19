use agentconf::{parse, Value};

fn s(v: &str) -> Value {
    Value::Str(v.to_string())
}

#[test]
fn basic_file() {
    let cfg = parse(
        "# comment\nname = \"runner-01\"\nconcurrency = 4\n\n[cache]\nenabled = true\nmax_size_mb = -1\n",
    )
    .unwrap();
    assert_eq!(cfg.get("name"), Some(&s("runner-01")));
    assert_eq!(cfg.get("concurrency"), Some(&Value::Int(4)));
    assert_eq!(cfg.get("cache.enabled"), Some(&Value::Bool(true)));
    assert_eq!(cfg.get("cache.max_size_mb"), Some(&Value::Int(-1)));
    assert_eq!(cfg.len(), 4);
}

#[test]
fn comment_after_value() {
    let cfg = parse("a = 1 # one\nb = \"two\"   # two\nc = 'x'# three\n").unwrap();
    assert_eq!(cfg.get("a"), Some(&Value::Int(1)));
    assert_eq!(cfg.get("b"), Some(&s("two")));
    assert_eq!(cfg.get("c"), Some(&s("x")));
}

#[test]
fn hash_inside_quotes() {
    let cfg = parse("a = \"#1 runner\" # c\nb = 'x#y'\n").unwrap();
    assert_eq!(cfg.get("a"), Some(&s("#1 runner")));
    assert_eq!(cfg.get("b"), Some(&s("x#y")));
}

#[test]
fn escapes_in_double_quotes() {
    let cfg = parse(r#"a = "say \"hi\"\tnow\n" # c"#).unwrap();
    assert_eq!(cfg.get("a"), Some(&s("say \"hi\"\tnow\n")));
}

#[test]
fn escaped_quote_then_hash() {
    let cfg = parse(r#"a = "x\" # not a comment" # comment"#).unwrap();
    assert_eq!(cfg.get("a"), Some(&s("x\" # not a comment")));
}

#[test]
fn trailing_backslash_with_comment() {
    let cfg = parse("[cache]\ndir = \"D:\\\\cache\\\\\" # windows runners\n").unwrap();
    assert_eq!(cfg.get("cache.dir"), Some(&s("D:\\cache\\")));
}

#[test]
fn backslashes_before_quote() {
    let input = concat!(
        "a = \"\\\\\\\\\" # two backslashes\n",
        "b = \"\\\\\\\"\" # backslash and quote\n",
        "c = \"\\\\\"\n",
        "d = [\"x\\\\\", \"y\"] # list\n",
    );
    let cfg = parse(input).unwrap();
    assert_eq!(cfg.get("a"), Some(&s("\\\\")));
    assert_eq!(cfg.get("b"), Some(&s("\\\"")));
    assert_eq!(cfg.get("c"), Some(&s("\\")));
    assert_eq!(cfg.get("d"), Some(&Value::List(vec![s("x\\"), s("y")])));
}

#[test]
fn single_quotes_are_literal() {
    let cfg = parse("a = 'C:\\temp\\'\nb = 'C:\\temp\\' # literal\nc = 'a\\nb' # c\n").unwrap();
    assert_eq!(cfg.get("a"), Some(&s("C:\\temp\\")));
    assert_eq!(cfg.get("b"), Some(&s("C:\\temp\\")));
    assert_eq!(cfg.get("c"), Some(&s("a\\nb")));
}

#[test]
fn mixed_quotes() {
    let cfg = parse("a = \"it's\" # c\nb = '\"quoted\"' # c\nc = ['a\\', \"b # c\"] # d\n").unwrap();
    assert_eq!(cfg.get("a"), Some(&s("it's")));
    assert_eq!(cfg.get("b"), Some(&s("\"quoted\"")));
    assert_eq!(cfg.get("c"), Some(&Value::List(vec![s("a\\"), s("b # c")])));
}

#[test]
fn lists() {
    let cfg = parse("tags = [\"gpu\", 'mi300', 3, false]\nempty = [ ]\n").unwrap();
    assert_eq!(
        cfg.get("tags"),
        Some(&Value::List(vec![s("gpu"), s("mi300"), Value::Int(3), Value::Bool(false)]))
    );
    assert_eq!(cfg.get("empty"), Some(&Value::List(vec![])));
}

#[test]
fn errors_have_line_numbers() {
    let e = parse("a = 1\nb = \"open\n").unwrap_err();
    assert_eq!(e.line, 2);
    let e = parse("a = 1\n\nb = \"x\\q\"\n").unwrap_err();
    assert_eq!(e.line, 3);
    let e = parse("a = 1\na = 2\n").unwrap_err();
    assert_eq!(e.line, 2);
    let e = parse("[x]\nkey value\n").unwrap_err();
    assert_eq!(e.line, 2);
    let e = parse("a = [[1]]\n").unwrap_err();
    assert_eq!(e.line, 1);
}

#[test]
fn unterminated_strings_are_errors() {
    assert_eq!(parse("a = \"abc\\\"\n").unwrap_err().line, 1);
    assert_eq!(parse("a = \"abc\\\" # c\n").unwrap_err().line, 1);
    assert_eq!(parse("x = 1\na = 'abc\n").unwrap_err().line, 2);
    assert!(parse("a = \"x\" y\n").is_err());
}
