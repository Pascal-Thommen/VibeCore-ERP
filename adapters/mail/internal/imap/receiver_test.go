package imap

import (
	"io"
	"log/slog"
	"testing"
	"time"

	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/config"
)

func TestReceiverDisabled(t *testing.T) {
	cfg := &config.Config{
		IMAPEnabled: false,
	}
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	rcv := NewReceiver(cfg, nil, logger)

	if err := rcv.Start(); err != nil {
		t.Fatalf("expected nil error when IMAP is disabled, got %v", err)
	}

	rcv.Stop()
}

func TestReceiverEmptyHost(t *testing.T) {
	cfg := &config.Config{
		IMAPEnabled: true,
		IMAPHost:    "",
	}
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	rcv := NewReceiver(cfg, nil, logger)

	if err := rcv.Start(); err != nil {
		t.Fatalf("expected nil error for empty host, got %v", err)
	}

	rcv.Stop()
}

func TestReceiverLifecycle(t *testing.T) {
	cfg := &config.Config{
		IMAPEnabled:      true,
		IMAPHost:         "127.0.0.1",
		IMAPPort:         19993, // unreachable port
		IMAPUseTLS:       false,
		IMAPPollInterval: 100 * time.Millisecond,
	}
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	rcv := NewReceiver(cfg, nil, logger)

	if err := rcv.Start(); err != nil {
		t.Fatalf("unexpected start error: %v", err)
	}

	time.Sleep(50 * time.Millisecond)
	// Stop should cleanly shut down the reconnect loop
	rcv.Stop()
}
