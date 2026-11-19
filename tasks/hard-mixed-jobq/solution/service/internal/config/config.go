// Package config reads the settings of jobq-server from environment variables
// (contract version 2, rules 1 and 2).
package config

import (
	"errors"
	"fmt"
	"net"
	"os"
	"strconv"
	"strings"
	"time"
)

// Config holds the settings of the server.
type Config struct {
	APIAddr     string
	MetricsAddr string
	TokenFile   string
	MaxTimeout  time.Duration
	QueueLimit  int
	DrainDelay  time.Duration
}

// Defaults returns the settings that apply when no variable is set.
// TokenFile has no default.
func Defaults() Config {
	return Config{
		APIAddr:     ":7070",
		MetricsAddr: ":9102",
		MaxTimeout:  time.Hour,
		QueueLimit:  100,
		DrainDelay:  5 * time.Second,
	}
}

// removedVars are the version 1 variables. The server refuses to start when
// one of them is set, so that an old manifest cannot start it.
var removedVars = []string{"JOBQ_PORT", "JOBQ_MAX_TIMEOUT_SECONDS"}

// FromEnv reads the settings with getenv, for example os.Getenv.
// An empty variable gives the default value.
func FromEnv(getenv func(string) string) (Config, error) {
	for _, name := range removedVars {
		if getenv(name) != "" {
			return Config{}, fmt.Errorf("%s is a version 1 variable and is not supported", name)
		}
	}
	cfg := Defaults()
	var err error
	if cfg.APIAddr, err = addrVar(getenv, "JOBQ_API_ADDR", cfg.APIAddr); err != nil {
		return Config{}, err
	}
	if cfg.MetricsAddr, err = addrVar(getenv, "JOBQ_METRICS_ADDR", cfg.MetricsAddr); err != nil {
		return Config{}, err
	}
	cfg.TokenFile = getenv("JOBQ_TOKEN_FILE")
	if cfg.TokenFile == "" {
		return Config{}, errors.New("JOBQ_TOKEN_FILE is required")
	}
	if cfg.MaxTimeout, err = durationVar(getenv, "JOBQ_MAX_TIMEOUT", cfg.MaxTimeout, false); err != nil {
		return Config{}, err
	}
	if cfg.DrainDelay, err = durationVar(getenv, "JOBQ_DRAIN_DELAY", cfg.DrainDelay, true); err != nil {
		return Config{}, err
	}
	if raw := getenv("JOBQ_QUEUE_LIMIT"); raw != "" {
		cfg.QueueLimit, err = strconv.Atoi(raw)
		if err != nil || cfg.QueueLimit < 1 {
			return Config{}, fmt.Errorf("JOBQ_QUEUE_LIMIT: %q is not an integer of 1 or more", raw)
		}
	}
	return cfg, nil
}

// ReadToken reads the API token: the file content without leading and
// trailing white space. An empty token is an error.
func ReadToken(path string) (string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return "", fmt.Errorf("token file: %w", err)
	}
	token := strings.TrimSpace(string(data))
	if token == "" {
		return "", fmt.Errorf("token file %s is empty", path)
	}
	return token, nil
}

func addrVar(getenv func(string) string, name, def string) (string, error) {
	raw := getenv(name)
	if raw == "" {
		return def, nil
	}
	if _, port, err := net.SplitHostPort(raw); err != nil || port == "" {
		return "", fmt.Errorf("%s: %q is not a listen address such as :7070", name, raw)
	}
	return raw, nil
}

func durationVar(getenv func(string) string, name string, def time.Duration, zeroOK bool) (time.Duration, error) {
	raw := getenv(name)
	if raw == "" {
		return def, nil
	}
	d, err := time.ParseDuration(raw)
	if err != nil || d < 0 || (d == 0 && !zeroOK) {
		return 0, fmt.Errorf("%s: %q is not a valid duration", name, raw)
	}
	return d, nil
}
