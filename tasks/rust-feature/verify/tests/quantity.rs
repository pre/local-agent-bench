use placer::{Quantity, QuantityError};

fn q(text: &str) -> u64 {
    match text.parse::<Quantity>() {
        Ok(v) => v.bytes(),
        Err(e) => panic!("parse {text:?}: {e}"),
    }
}

#[test]
fn plain_bytes() {
    assert_eq!(q("0"), 0);
    assert_eq!(q("1048576"), 1_048_576);
    assert_eq!(q("007"), 7);
}

#[test]
fn decimal_suffixes() {
    assert_eq!(q("1k"), 1_000);
    assert_eq!(q("3M"), 3_000_000);
    assert_eq!(q("2G"), 2_000_000_000);
    assert_eq!(q("5T"), 5_000_000_000_000);
}

#[test]
fn binary_suffixes() {
    assert_eq!(q("1Ki"), 1 << 10);
    assert_eq!(q("3Mi"), 3 << 20);
    assert_eq!(q("2Gi"), 2 << 30);
    assert_eq!(q("5Ti"), 5 << 40);
    assert_eq!(q("1536Gi"), 1536 << 30);
}

#[test]
fn fractions() {
    assert_eq!(q("1.5Gi"), 1_610_612_736);
    assert_eq!(q("0.5Ki"), 512);
    assert_eq!(q("12.75Mi"), 13_369_344);
    assert_eq!(q("0.25"), 0);
    assert_eq!(q("2.0"), 2);
}

#[test]
fn fractions_are_exact() {
    assert_eq!(q("2.3k"), 2_300);
    assert_eq!(q("4.35M"), 4_350_000);
    assert_eq!(q("0.1G"), 100_000_000);
    assert_eq!(q("1.1T"), 1_100_000_000_000);
    assert_eq!(q("9.7k"), 9_700);
    assert_eq!(q("1.005k"), 1_005);
    assert_eq!(q("1.001M"), 1_001_000);
    assert_eq!(q("1.007G"), 1_007_000_000);
}

#[test]
fn fractions_round_down() {
    assert_eq!(q("1.0001k"), 1_000);
    assert_eq!(q("0.333333333Ki"), 341);
    assert_eq!(q("1.9999"), 1);
    assert_eq!(q("0.0009k"), 0);
}

#[test]
fn invalid_text() {
    for text in [
        "Gi", "1.5.5Gi", "-1", "+1", "1e3", "1 Gi", " 1Gi", "1Gi ", "1gi", "1K", "1KI", "1Kb", "1Ei", ".5Gi",
        "1.Gi", "1.", "Ki1", "1,5Gi", "0x10",
    ] {
        match text.parse::<Quantity>() {
            Err(QuantityError::Invalid(s)) => assert_eq!(s, text),
            other => panic!("parse {text:?}: expected Invalid, got {other:?}"),
        }
    }
}

#[test]
fn empty_text() {
    assert_eq!("".parse::<Quantity>(), Err(QuantityError::Empty));
}

#[test]
fn largest_values() {
    assert_eq!(q("18446744073709551615"), u64::MAX);
    assert_eq!(q("16777215.999Ti"), 18_446_744_072_610_039_988);
    for text in ["18446744073709551616", "16777216Ti", "18446744073709551.616k", "99999999999999999999999999999999999999999999"] {
        match text.parse::<Quantity>() {
            Err(QuantityError::Overflow(s)) => assert_eq!(s, text),
            other => panic!("parse {text:?}: expected Overflow, got {other:?}"),
        }
    }
}

#[test]
fn display_round_trip() {
    for bytes in [0, 1, 1000, 1024, 1_610_612_736, 3 << 40, u64::MAX, (1 << 30) + 1] {
        let value = Quantity::from_bytes(bytes);
        assert_eq!(value.to_string().parse::<Quantity>(), Ok(value), "{value}");
    }
}
