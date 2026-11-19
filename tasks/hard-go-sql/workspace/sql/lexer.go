package sql

import (
	"strings"
)

type tokKind int

const (
	tEOF tokKind = iota
	tIdent
	tKeyword
	tInt
	tFloat
	tString
	tOp // operators and punctuation
)

type token struct {
	kind tokKind
	text string // keywords in upper case
	pos  int
}

var keywords = map[string]bool{
	"SELECT": true, "FROM": true, "WHERE": true, "ORDER": true, "BY": true,
	"ASC": true, "DESC": true, "LIMIT": true, "OFFSET": true, "AS": true,
	"AND": true, "OR": true, "NOT": true, "IS": true, "NULL": true,
	"TRUE": true, "FALSE": true,
	// Reserved for features that are not implemented yet.
	"GROUP": true, "HAVING": true, "DISTINCT": true,
}

func lex(src string) ([]token, error) {
	var out []token
	i := 0
	for i < len(src) {
		c := src[i]
		switch {
		case c == ' ' || c == '\t' || c == '\n' || c == '\r':
			i++
		case c == '-' && i+1 < len(src) && src[i+1] == '-':
			for i < len(src) && src[i] != '\n' {
				i++
			}
		case isLetter(c) || c == '_':
			start := i
			for i < len(src) && (isLetter(src[i]) || isDigit(src[i]) || src[i] == '_') {
				i++
			}
			word := src[start:i]
			if up := strings.ToUpper(word); keywords[up] {
				out = append(out, token{tKeyword, up, start})
			} else {
				out = append(out, token{tIdent, word, start})
			}
		case isDigit(c) || c == '.' && i+1 < len(src) && isDigit(src[i+1]):
			start := i
			kind := tInt
			for i < len(src) && isDigit(src[i]) {
				i++
			}
			if i < len(src) && src[i] == '.' {
				kind = tFloat
				i++
				for i < len(src) && isDigit(src[i]) {
					i++
				}
			}
			if i < len(src) && (src[i] == 'e' || src[i] == 'E') {
				j := i + 1
				if j < len(src) && (src[j] == '+' || src[j] == '-') {
					j++
				}
				if j < len(src) && isDigit(src[j]) {
					kind = tFloat
					for i = j; i < len(src) && isDigit(src[i]); i++ {
					}
				}
			}
			out = append(out, token{kind, src[start:i], start})
		case c == '\'':
			start := i
			var b strings.Builder
			i++
			for {
				if i >= len(src) {
					return nil, Errorf("syntax", "text at %d has no closing quote", start)
				}
				if src[i] == '\'' {
					if i+1 < len(src) && src[i+1] == '\'' {
						b.WriteByte('\'')
						i += 2
						continue
					}
					i++
					break
				}
				b.WriteByte(src[i])
				i++
			}
			out = append(out, token{tString, b.String(), start})
		default:
			two := ""
			if i+1 < len(src) {
				two = src[i : i+2]
			}
			switch two {
			case "<=", ">=", "<>", "!=", "||":
				if two == "!=" {
					two = "<>"
				}
				out = append(out, token{tOp, two, i})
				i += 2
				continue
			}
			if strings.ContainsRune("+-*/%=<>(),;", rune(c)) {
				out = append(out, token{tOp, string(c), i})
				i++
				continue
			}
			return nil, Errorf("syntax", "unexpected character %q at %d", c, i)
		}
	}
	return append(out, token{tEOF, "", len(src)}), nil
}

func isLetter(c byte) bool { return c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z' }
func isDigit(c byte) bool  { return c >= '0' && c <= '9' }
