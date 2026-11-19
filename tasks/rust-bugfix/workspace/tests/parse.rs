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
