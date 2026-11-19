// Package config reads the settings of jobq-server from environment variables.
package config

import (
	"fmt"
	"strconv"
)

// Config holds the settings of the server.
type Config struct {
	// Port is the TCP port of the HTTP listener (API, health and metrics).
	Port int
	// MaxTimeoutSeconds is the largest timeout that a job can have.
	MaxTimeoutSeconds int
	// QueueLimit is the largest number of queued jobs.
	QueueLimit int
}

// Defaults returns the settings that apply when no variable is set.
func Defaults() Config {
	return Config{Port: 8080, MaxTimeoutSeconds: 3600, QueueLimit: 100}
}

// FromEnv reads the settings with getenv, for example os.Getenv.
// An empty variable gives the default value.
func FromEnv(getenv func(string) string) (Config, error) {
	cfg := Defaults()
	var err error
	if cfg.Port, err = intVar(getenv, "JOBQ_PORT", cfg.Port, 1, 65535); err != nil {
		return Config{}, err
	}
	if cfg.MaxTimeoutSeconds, err = intVar(getenv, "JOBQ_MAX_TIMEOUT_SECONDS", cfg.MaxTimeoutSeconds, 1, 7*24*3600); err != nil {
		return Config{}, err
	}
	if cfg.QueueLimit, err = intVar(getenv, "JOBQ_QUEUE_LIMIT", cfg.QueueLimit, 1, 1000000); err != nil {
		return Config{}, err
	}
	return cfg, nil
}

func intVar(getenv func(string) string, name string, def, lo, hi int) (int, error) {
	raw := getenv(name)
	if raw == "" {
		return def, nil
	}
	v, err := strconv.Atoi(raw)
	if err != nil {
		return 0, fmt.Errorf("%s: %q is not an integer", name, raw)
	}
	if v < lo || v > hi {
		return 0, fmt.Errorf("%s: %d is not in the range %d to %d", name, v, lo, hi)
	}
	return v, nil
}
