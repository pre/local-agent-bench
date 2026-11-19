package formula

import (
	"fmt"
	"strings"
)

type tokenKind int

const (
	tokEOF tokenKind = iota
	tokNumber
	tokText
	tokIdent // a name or a cell address
	tokOp
	tokLParen
	tokRParen
	tokComma
	tokColon
)

type token struct {
	kind tokenKind
	text string
	pos  int // byte offset in the formula
}

func (t token) String() string {
	if t.kind == tokEOF {
		return "end of formula"
	}
	return fmt.Sprintf("%q", t.text)
}

func lex(src string) ([]token, error) {
	var toks []token
	i := 0
	for i < len(src) {
		c := src[i]
		switch {
		case c == ' ' || c == '\t':
			i++
		case isDigit(c) || c == '.' && i+1 < len(src) && isDigit(src[i+1]):
			start := i
			for i < len(src) && isDigit(src[i]) {
				i++
			}
			if i < len(src) && src[i] == '.' {
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
					i = j
					for i < len(src) && isDigit(src[i]) {
						i++
					}
				}
			}
			toks = append(toks, token{tokNumber, src[start:i], start})
		case c == '"':
			start := i
			var b strings.Builder
			i++
			for {
				if i >= len(src) {
					return nil, fmt.Errorf("text at %d has no closing quote", start)
				}
				if src[i] == '"' {
					if i+1 < len(src) && src[i+1] == '"' {
						b.WriteByte('"')
						i += 2
						continue
					}
					i++
					break
				}
				b.WriteByte(src[i])
				i++
			}
			toks = append(toks, token{tokText, b.String(), start})
		case isLetter(c):
			start := i
			for i < len(src) && (isLetter(src[i]) || isDigit(src[i]) || src[i] == '_') {
				i++
			}
			toks = append(toks, token{tokIdent, src[start:i], start})
		case c == '(':
			toks = append(toks, token{tokLParen, "(", i})
			i++
		case c == ')':
			toks = append(toks, token{tokRParen, ")", i})
			i++
		case c == ',':
			toks = append(toks, token{tokComma, ",", i})
			i++
		case c == ':':
			toks = append(toks, token{tokColon, ":", i})
			i++
		case strings.ContainsRune("+-*/^&=", rune(c)):
			toks = append(toks, token{tokOp, string(c), i})
			i++
		case c == '<' || c == '>':
			op := string(c)
			if i+1 < len(src) && (src[i+1] == '=' || c == '<' && src[i+1] == '>') {
				op += string(src[i+1])
			}
			toks = append(toks, token{tokOp, op, i})
			i += len(op)
		default:
			return nil, fmt.Errorf("unexpected character %q at %d", c, i)
		}
	}
	toks = append(toks, token{tokEOF, "", len(src)})
	return toks, nil
}

func isDigit(c byte) bool  { return c >= '0' && c <= '9' }
func isLetter(c byte) bool { return c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z' }
