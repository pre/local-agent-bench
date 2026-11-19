package formula

import (
	"errors"
	"fmt"
	"strconv"
	"strings"

	"example.com/sheet/internal/addr"
)

// ErrSyntax is the error for a formula that does not parse.
var ErrSyntax = errors.New("syntax error")

// Parse reads the text of a formula without the leading "=".
func Parse(src string) (Expr, error) {
	toks, err := lex(src)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrSyntax, err)
	}
	p := &parser{toks: toks}
	e, err := p.parseExpr(0)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrSyntax, err)
	}
	if t := p.peek(); t.kind != tokEOF {
		return nil, fmt.Errorf("%w: unexpected %v at %d", ErrSyntax, t, t.pos)
	}
	if err := checkRanges(e, false); err != nil {
		return nil, fmt.Errorf("%w: %v", ErrSyntax, err)
	}
	return e, nil
}

type parser struct {
	toks []token
	i    int
}

func (p *parser) peek() token { return p.toks[p.i] }

func (p *parser) next() token {
	t := p.toks[p.i]
	if t.kind != tokEOF {
		p.i++
	}
	return t
}

// Binding power of the infix operators. A higher value binds tighter.
var infix = map[string]int{
	"=": 1, "<>": 1, "<": 1, "<=": 1, ">": 1, ">=": 1,
	"&": 2,
	"+": 3, "-": 3,
	"*": 4, "/": 4,
	"^": 5,
}

// The prefix operators bind tighter than all infix operators, so -2^2 is 4.
const prefixPower = 6

func (p *parser) parseExpr(minPower int) (Expr, error) {
	left, err := p.parsePrefix()
	if err != nil {
		return nil, err
	}
	for {
		t := p.peek()
		if t.kind != tokOp {
			return left, nil
		}
		power := infix[t.text]
		if power <= minPower {
			return left, nil
		}
		p.next()
		next := power
		if t.text == "^" {
			next = power - 1 // right associative
		}
		right, err := p.parseExpr(next)
		if err != nil {
			return nil, err
		}
		left = &Binary{Op: t.text, L: left, R: right}
	}
}

func (p *parser) parsePrefix() (Expr, error) {
	t := p.next()
	switch t.kind {
	case tokOp:
		if t.text != "-" && t.text != "+" {
			return nil, fmt.Errorf("unexpected %v at %d", t, t.pos)
		}
		x, err := p.parseExpr(prefixPower)
		if err != nil {
			return nil, err
		}
		return &Unary{Op: t.text, X: x}, nil
	case tokNumber:
		f, err := strconv.ParseFloat(t.text, 64)
		if err != nil {
			return nil, fmt.Errorf("bad number %v at %d", t, t.pos)
		}
		return &NumberLit{Val: f}, nil
	case tokText:
		return &TextLit{Val: t.text}, nil
	case tokLParen:
		e, err := p.parseExpr(0)
		if err != nil {
			return nil, err
		}
		if c := p.next(); c.kind != tokRParen {
			return nil, fmt.Errorf("expected \")\" at %d, found %v", c.pos, c)
		}
		return e, nil
	case tokIdent:
		return p.parseIdent(t)
	}
	return nil, fmt.Errorf("unexpected %v at %d", t, t.pos)
}

func (p *parser) parseIdent(t token) (Expr, error) {
	upper := strings.ToUpper(t.text)
	if p.peek().kind == tokLParen {
		p.next()
		return p.parseCall(upper)
	}
	switch upper {
	case "TRUE":
		return &BoolLit{Val: true}, nil
	case "FALSE":
		return &BoolLit{Val: false}, nil
	}
	a, err := addr.Parse(t.text)
	if err != nil {
		return nil, fmt.Errorf("unknown name %v at %d", t, t.pos)
	}
	if p.peek().kind != tokColon {
		return &Ref{Addr: a}, nil
	}
	p.next()
	end := p.next()
	if end.kind != tokIdent {
		return nil, fmt.Errorf("expected a cell after \":\" at %d", end.pos)
	}
	b, err := addr.Parse(end.text)
	if err != nil {
		return nil, fmt.Errorf("bad range end %v at %d", end, end.pos)
	}
	return &RangeRef{Range: addr.NewRange(a, b)}, nil
}

func (p *parser) parseCall(name string) (Expr, error) {
	call := &Call{Name: name}
	if p.peek().kind == tokRParen {
		p.next()
		return call, nil
	}
	for {
		arg, err := p.parseExpr(0)
		if err != nil {
			return nil, err
		}
		call.Args = append(call.Args, arg)
		switch t := p.next(); t.kind {
		case tokComma:
		case tokRParen:
			return call, nil
		default:
			return nil, fmt.Errorf("expected \",\" or \")\" at %d, found %v", t.pos, t)
		}
	}
}

// checkRanges rejects a range that is not a direct function argument.
func checkRanges(e Expr, isArg bool) error {
	switch n := e.(type) {
	case *RangeRef:
		if !isArg {
			return fmt.Errorf("range %v is permitted only as a function argument", n.Range)
		}
	case *Unary:
		return checkRanges(n.X, false)
	case *Binary:
		if err := checkRanges(n.L, false); err != nil {
			return err
		}
		return checkRanges(n.R, false)
	case *Call:
		for _, a := range n.Args {
			if err := checkRanges(a, true); err != nil {
				return err
			}
		}
	}
	return nil
}
