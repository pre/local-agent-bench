// Package sheetfile reads sheet files and edit files.
//
// A sheet file has one cell on each line: the address, a colon and the
// input, for example "B2: =A1*2". Blank lines and lines that start with "#"
// are ignored. Spaces after the colon are not part of the input.
//
// An edit file has the same lines, in groups. A line "---" ends a group. Each
// group is one update of the sheet (engine.Sheet.Apply).
package sheetfile

import (
	"bufio"
	"fmt"
	"io"
	"os"
	"strings"

	"example.com/sheet/engine"
)

// Read reads the lines of a sheet file or an edit file into groups.
func Read(r io.Reader) ([][]engine.Edit, error) {
	var groups [][]engine.Edit
	var cur []engine.Edit
	sc := bufio.NewScanner(r)
	sc.Buffer(make([]byte, 0, 64*1024), 16*1024*1024)
	line := 0
	for sc.Scan() {
		line++
		text := strings.TrimRight(sc.Text(), " \t\r")
		trimmed := strings.TrimSpace(text)
		switch {
		case trimmed == "" || strings.HasPrefix(trimmed, "#"):
			continue
		case trimmed == "---":
			if len(cur) > 0 {
				groups = append(groups, cur)
				cur = nil
			}
			continue
		}
		cell, input, ok := strings.Cut(trimmed, ":")
		if !ok {
			return nil, fmt.Errorf("line %d: expected \"<cell>: <input>\"", line)
		}
		cur = append(cur, engine.Edit{Cell: strings.TrimSpace(cell), Input: strings.TrimLeft(input, " \t")})
	}
	if err := sc.Err(); err != nil {
		return nil, err
	}
	if len(cur) > 0 {
		groups = append(groups, cur)
	}
	return groups, nil
}

// ReadFile reads a file with Read.
func ReadFile(path string) ([][]engine.Edit, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	groups, err := Read(f)
	if err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	return groups, nil
}

// Flatten joins the groups into one list of edits.
func Flatten(groups [][]engine.Edit) []engine.Edit {
	var out []engine.Edit
	for _, g := range groups {
		out = append(out, g...)
	}
	return out
}
