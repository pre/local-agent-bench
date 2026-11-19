package sql

import (
	"strconv"
	"strings"

	"example.com/minisql/value"
)

// Parse reads one SELECT statement. A final ";" is permitted.
func Parse(src string) (*Select, error) {
	toks, err := lex(src)
	if err != nil {
		return nil, err
	}
	p := &parser{toks: toks}
	s, err := p.parseSelect()
	if err != nil {
		return nil, err
	}
	p.accept(tOp, ";")
	if t := p.peek(); t.kind != tEOF {
		return nil, p.unexpected(t)
	}
	return s, nil
}

type parser struct {
	toks []token
	i    int
}

func (p *parser) peek() token { return p.toks[p.i] }

func (p *parser) next() token {
	t := p.toks[p.i]
	if t.kind != tEOF {
		p.i++
	}
	return t
}

func (p *parser) is(kind tokKind, text string) bool {
	t := p.peek()
	return t.kind == kind && t.text == text
}

func (p *parser) accept(kind tokKind, text string) bool {
	if p.is(kind, text) {
		p.next()
		return true
	}
	return false
}

func (p *parser) expect(kind tokKind, text string) error {
	if !p.accept(kind, text) {
		return p.unexpected(p.peek())
	}
	return nil
}

func (p *parser) unexpected(t token) error {
	if t.kind == tEOF {
		return Errorf("syntax", "unexpected end of query")
	}
	return Errorf("syntax", "unexpected %q at %d", t.text, t.pos)
}

func (p *parser) notSupported(word string) error {
	return Errorf("unsupported", "%s is not supported", word)
}

func (p *parser) parseSelect() (*Select, error) {
	if err := p.expect(tKeyword, "SELECT"); err != nil {
		return nil, err
	}
	if p.is(tKeyword, "DISTINCT") {
		return nil, p.notSupported("SELECT DISTINCT")
	}
	s := &Select{Limit: -1}
	for {
		item, err := p.parseItem()
		if err != nil {
			return nil, err
		}
		s.Items = append(s.Items, item)
		if !p.accept(tOp, ",") {
			break
		}
	}
	if err := p.expect(tKeyword, "FROM"); err != nil {
		return nil, err
	}
	t := p.next()
	if t.kind != tIdent {
		return nil, p.unexpected(t)
	}
	s.From = t.text
	if p.accept(tKeyword, "WHERE") {
		e, err := p.parseExpr()
		if err != nil {
			return nil, err
		}
		s.Where = e
	}
	if p.is(tKeyword, "GROUP") {
		return nil, p.notSupported("GROUP BY")
	}
	if p.is(tKeyword, "HAVING") {
		return nil, p.notSupported("HAVING")
	}
	if p.accept(tKeyword, "ORDER") {
		if err := p.expect(tKeyword, "BY"); err != nil {
			return nil, err
		}
		for {
			e, err := p.parseExpr()
			if err != nil {
				return nil, err
			}
			item := OrderItem{Expr: e}
			if p.accept(tKeyword, "DESC") {
				item.Desc = true
			} else {
				p.accept(tKeyword, "ASC")
			}
			s.OrderBy = append(s.OrderBy, item)
			if !p.accept(tOp, ",") {
				break
			}
		}
	}
	if p.accept(tKeyword, "LIMIT") {
		n, err := p.parseCount()
		if err != nil {
			return nil, err
		}
		s.Limit = n
		if p.accept(tKeyword, "OFFSET") {
			if s.Offset, err = p.parseCount(); err != nil {
				return nil, err
			}
		}
	}
	return s, nil
}

func (p *parser) parseCount() (int64, error) {
	t := p.next()
	if t.kind != tInt {
		return 0, p.unexpected(t)
	}
	n, err := strconv.ParseInt(t.text, 10, 64)
	if err != nil {
		return 0, Errorf("syntax", "bad count %q", t.text)
	}
	return n, nil
}

func (p *parser) parseItem() (SelectItem, error) {
	if p.accept(tOp, "*") {
		return SelectItem{Star: true}, nil
	}
	e, err := p.parseExpr()
	if err != nil {
		return SelectItem{}, err
	}
	item := SelectItem{Expr: e}
	if p.accept(tKeyword, "AS") {
		t := p.next()
		if t.kind != tIdent {
			return SelectItem{}, p.unexpected(t)
		}
		item.Alias = t.text
	} else if t := p.peek(); t.kind == tIdent {
		p.next()
		item.Alias = t.text
	}
	return item, nil
}

// Precedence, from the weakest: OR, AND, NOT, comparison and IS, ||, + -,
// * / %, unary minus.
func (p *parser) parseExpr() (Expr, error) { return p.parseOr() }

func (p *parser) parseOr() (Expr, error) {
	l, err := p.parseAnd()
	for err == nil && p.accept(tKeyword, "OR") {
		var r Expr
		if r, err = p.parseAnd(); err == nil {
			l = &Binary{Op: "OR", L: l, R: r}
		}
	}
	return l, err
}

func (p *parser) parseAnd() (Expr, error) {
	l, err := p.parseNot()
	for err == nil && p.accept(tKeyword, "AND") {
		var r Expr
		if r, err = p.parseNot(); err == nil {
			l = &Binary{Op: "AND", L: l, R: r}
		}
	}
	return l, err
}

func (p *parser) parseNot() (Expr, error) {
	if p.accept(tKeyword, "NOT") {
		x, err := p.parseNot()
		if err != nil {
			return nil, err
		}
		return &Unary{Op: "NOT", X: x}, nil
	}
	return p.parseComparison()
}

var comparisons = map[string]bool{"=": true, "<>": true, "<": true, "<=": true, ">": true, ">=": true}

func (p *parser) parseComparison() (Expr, error) {
	l, err := p.parseConcat()
	if err != nil {
		return nil, err
	}
	if t := p.peek(); t.kind == tOp && comparisons[t.text] {
		p.next()
		r, err := p.parseConcat()
		if err != nil {
			return nil, err
		}
		return &Binary{Op: t.text, L: l, R: r}, nil
	}
	if p.accept(tKeyword, "IS") {
		not := p.accept(tKeyword, "NOT")
		if err := p.expect(tKeyword, "NULL"); err != nil {
			return nil, err
		}
		return &IsNull{X: l, Not: not}, nil
	}
	return l, nil
}

func (p *parser) parseConcat() (Expr, error) {
	return p.parseLeft(p.parseAdd, "||")
}

func (p *parser) parseAdd() (Expr, error) {
	return p.parseLeft(p.parseMul, "+", "-")
}

func (p *parser) parseMul() (Expr, error) {
	return p.parseLeft(p.parseUnary, "*", "/", "%")
}

func (p *parser) parseLeft(sub func() (Expr, error), ops ...string) (Expr, error) {
	l, err := sub()
	if err != nil {
		return nil, err
	}
	for {
		t := p.peek()
		if t.kind != tOp || !contains(ops, t.text) {
			return l, nil
		}
		p.next()
		r, err := sub()
		if err != nil {
			return nil, err
		}
		l = &Binary{Op: t.text, L: l, R: r}
	}
}

func contains(list []string, s string) bool {
	for _, x := range list {
		if x == s {
			return true
		}
	}
	return false
}

func (p *parser) parseUnary() (Expr, error) {
	if p.accept(tOp, "-") {
		// A minus sign before a number is part of the literal, so
		// -9223372036854775808 is a valid INT.
		if t := p.peek(); t.kind == tInt || t.kind == tFloat {
			p.next()
			return numberLiteral(token{t.kind, "-" + t.text, t.pos})
		}
		x, err := p.parseUnary()
		if err != nil {
			return nil, err
		}
		return &Unary{Op: "-", X: x}, nil
	}
	return p.parsePrimary()
}

func (p *parser) parsePrimary() (Expr, error) {
	t := p.next()
	switch t.kind {
	case tInt, tFloat:
		return numberLiteral(t)
	case tString:
		return &Literal{Value: value.NewText(t.text)}, nil
	case tKeyword:
		switch t.text {
		case "NULL":
			return &Literal{Value: value.NullValue}, nil
		case "TRUE":
			return &Literal{Value: value.NewBool(true)}, nil
		case "FALSE":
			return &Literal{Value: value.NewBool(false)}, nil
		}
	case tIdent:
		if p.accept(tOp, "(") {
			return p.parseCall(strings.ToUpper(t.text))
		}
		return &ColumnRef{Name: t.text}, nil
	case tOp:
		if t.text == "(" {
			e, err := p.parseExpr()
			if err != nil {
				return nil, err
			}
			if err := p.expect(tOp, ")"); err != nil {
				return nil, err
			}
			return e, nil
		}
	}
	return nil, p.unexpected(t)
}

func (p *parser) parseCall(name string) (Expr, error) {
	c := &Call{Name: name}
	if p.accept(tOp, "*") {
		c.Star = true
		return c, p.expect(tOp, ")")
	}
	if p.is(tKeyword, "DISTINCT") {
		return nil, p.notSupported(name + "(DISTINCT ...)")
	}
	if p.accept(tOp, ")") {
		return c, nil
	}
	for {
		a, err := p.parseExpr()
		if err != nil {
			return nil, err
		}
		c.Args = append(c.Args, a)
		if p.accept(tOp, ")") {
			return c, nil
		}
		if err := p.expect(tOp, ","); err != nil {
			return nil, err
		}
	}
}

func numberLiteral(t token) (Expr, error) {
	if t.kind == tInt {
		i, err := strconv.ParseInt(t.text, 10, 64)
		if err != nil {
			return nil, Errorf("overflow", "integer literal %s does not fit in INT", t.text)
		}
		return &Literal{Value: value.NewInt(i)}, nil
	}
	f, err := strconv.ParseFloat(t.text, 64)
	if err != nil {
		return nil, Errorf("syntax", "bad number %s", t.text)
	}
	return &Literal{Value: value.NewFloat(f)}, nil
}
