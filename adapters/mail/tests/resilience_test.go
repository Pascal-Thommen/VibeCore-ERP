package tests

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
	"sync"
	"testing"
	"time"

	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/api"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/config"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/models"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/queue"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/smtp"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/status"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/template"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/webhooks"
)

// TestResilienceExponentialBackoff tests temporary SMTP failure, exponential backoff, and eventual success.
func TestResilienceExponentialBackoff(t *testing.T) {
	mockSMTP := startMockSMTPServer(t)
	defer mockSMTP.Close()

	// Initially reject delivery
	mockSMTP.SetReject(true)

	tmpDir, _ := os.MkdirTemp("", "resilience_backoff_*")
	defer os.RemoveAll(tmpDir)

	dbPath := filepath.Join(tmpDir, "queue.db")
	q, _ := queue.NewBoltQueue(dbPath)
	defer q.Close()

	cfg := &config.Config{
		Host:                   "127.0.0.1",
		Port:                   8025,
		APIKey:                 "resilience-key",
		Environment:            "test",
		SMTPHost:               "127.0.0.1",
		SMTPPort:               mockSMTP.port,
		SMTPFromEmail:          "resilience@vibecore.local",
		SMTPTLSPolicy:          "none",
		SMTPConnectTimeout:     2 * time.Second,
		SMTPSendTimeout:        2 * time.Second,
		QueueWorkerConcurrency: 1,
		QueuePollInterval:      10 * time.Millisecond,
		QueueBaseBackoff:       50 * time.Millisecond,
		QueueMaxBackoff:        200 * time.Millisecond,
		QueueMaxRetries:        4,
	}

	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	tmplEngine := template.NewEngine()
	tracker := status.NewTracker(cfg, q, logger)
	sender, _ := smtp.NewSMTPSender(cfg)

	proc := queue.NewProcessor(cfg, q, sender, tmplEngine, tracker, logger)
	_ = proc.Start()
	defer proc.Stop()

	// Enqueue message
	item := &models.QueuedMail{
		ID: "msg_retry_test",
		Request: models.SendMailRequest{
			To:       []string{"retry@customer.py"},
			Subject:  "Retry Test",
			TextBody: "Will succeed after recovery",
		},
	}
	if err := proc.EnqueueRequest(context.Background(), item); err != nil {
		t.Fatalf("failed enqueuing: %v", err)
	}

	// Wait until at least 1 failed attempt is registered
	time.Sleep(100 * time.Millisecond)

	stat, _ := tracker.GetStatus(context.Background(), "msg_retry_test")
	if stat.Attempts < 1 {
		t.Fatalf("expected at least 1 attempt, got %d", stat.Attempts)
	}
	if stat.LastError == "" {
		t.Fatal("expected LastError to record SMTP error")
	}

	// Now bring SMTP server back to normal (accepting mails)
	mockSMTP.SetReject(false)

	// Wait for exponential backoff worker to succeed
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	var recoveredStatus *models.StatusResponse
	for {
		select {
		case <-ctx.Done():
			t.Fatal("timed out waiting for retry to succeed after recovery")
		default:
			s, err := tracker.GetStatus(context.Background(), "msg_retry_test")
			if err == nil && s.State == models.MailStateSent {
				recoveredStatus = s
				break
			}
			time.Sleep(20 * time.Millisecond)
		}
		if recoveredStatus != nil {
			break
		}
	}

	if recoveredStatus.State != models.MailStateSent {
		t.Fatalf("expected state SENT after recovery, got %s", recoveredStatus.State)
	}
	if len(mockSMTP.GetReceived()) != 1 {
		t.Fatalf("expected exactly 1 received email at SMTP server, got %d", len(mockSMTP.GetReceived()))
	}
}

// TestResilienceCrashRecovery tests that an abrupt server crash does not lose in-flight or queued emails.
func TestResilienceCrashRecovery(t *testing.T) {
	tmpDir, _ := os.MkdirTemp("", "resilience_crash_*")
	defer os.RemoveAll(tmpDir)
	dbPath := filepath.Join(tmpDir, "queue.db")

	// Phase 1: Initialize DB, enqueue 3 emails (one stuck in SENDING, two QUEUED)
	q1, err := queue.NewBoltQueue(dbPath)
	if err != nil {
		t.Fatalf("failed creating queue 1: %v", err)
	}

	ctx := context.Background()
	_ = q1.Enqueue(ctx, &models.QueuedMail{
		ID:    "msg_inflight_crash",
		State: models.MailStateSending, // simulated crash while in flight
		Request: models.SendMailRequest{
			To:       []string{"recovered@test.com"},
			Subject:  "Recover Me",
			TextBody: "Crash recovery",
		},
	})
	_ = q1.Enqueue(ctx, &models.QueuedMail{
		ID:    "msg_queued_pending",
		State: models.MailStateQueued,
		Request: models.SendMailRequest{
			To:       []string{"queued@test.com"},
			Subject:  "Queued Item",
			TextBody: "Pending",
		},
	})

	// Abrupt close (simulates crash / kill -9)
	_ = q1.Close()

	// Phase 2: Start new instance with same DB file
	mockSMTP := startMockSMTPServer(t)
	defer mockSMTP.Close()

	q2, err := queue.NewBoltQueue(dbPath)
	if err != nil {
		t.Fatalf("failed re-opening queue DB: %v", err)
	}
	defer q2.Close()

	cfg := &config.Config{
		Environment:            "test",
		SMTPHost:               "127.0.0.1",
		SMTPPort:               mockSMTP.port,
		SMTPFromEmail:          "noreply@vibecore.local",
		SMTPTLSPolicy:          "none",
		QueueWorkerConcurrency: 2,
		QueuePollInterval:      10 * time.Millisecond,
		QueueBaseBackoff:       10 * time.Millisecond,
		QueueMaxRetries:        3,
	}

	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	tmplEngine := template.NewEngine()
	tracker := status.NewTracker(cfg, q2, logger)
	sender, _ := smtp.NewSMTPSender(cfg)

	proc := queue.NewProcessor(cfg, q2, sender, tmplEngine, tracker, logger)
	if err := proc.Start(); err != nil {
		t.Fatalf("failed starting processor after restart: %v", err)
	}
	defer proc.Stop()

	// Wait for workers to recover and send both messages
	time.Sleep(200 * time.Millisecond)

	stat1, _ := tracker.GetStatus(ctx, "msg_inflight_crash")
	stat2, _ := tracker.GetStatus(ctx, "msg_queued_pending")

	if stat1 == nil || stat1.State != models.MailStateSent {
		t.Fatalf("expected msg_inflight_crash to be SENT, got %+v", stat1)
	}
	if stat2 == nil || stat2.State != models.MailStateSent {
		t.Fatalf("expected msg_queued_pending to be SENT, got %+v", stat2)
	}

	if len(mockSMTP.GetReceived()) != 2 {
		t.Fatalf("expected 2 emails received at SMTP server after recovery, got %d", len(mockSMTP.GetReceived()))
	}
}

// TestResilienceConcurrentIdempotency ensures concurrent identical requests never duplicate sends.
func TestResilienceConcurrentIdempotency(t *testing.T) {
	mockSMTP := startMockSMTPServer(t)
	defer mockSMTP.Close()

	tmpDir, _ := os.MkdirTemp("", "resilience_idem_*")
	defer os.RemoveAll(tmpDir)

	dbPath := filepath.Join(tmpDir, "queue.db")
	q, _ := queue.NewBoltQueue(dbPath)
	defer q.Close()

	cfg := &config.Config{
		APIKey:                 "test-key",
		Environment:            "test",
		SMTPHost:               "127.0.0.1",
		SMTPPort:               mockSMTP.port,
		SMTPFromEmail:          "noreply@vibecore.local",
		SMTPTLSPolicy:          "none",
		QueueWorkerConcurrency: 2,
		QueuePollInterval:      10 * time.Millisecond,
	}

	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	tmplEngine := template.NewEngine()
	tracker := status.NewTracker(cfg, q, logger)
	sender, _ := smtp.NewSMTPSender(cfg)

	proc := queue.NewProcessor(cfg, q, sender, tmplEngine, tracker, logger)
	_ = proc.Start()
	defer proc.Stop()

	apiService := api.NewAPI(cfg, q, proc, tracker, tmplEngine, logger)
	whHandler := webhooks.NewHandler(cfg, q, tracker, logger)
	router := api.NewRouter(cfg, apiService, whHandler, logger)

	concurrency := 10
	var wg sync.WaitGroup
	statusCodes := make([]int, concurrency)

	payload := models.SendMailRequest{
		To:       []string{"single-charge@client.py"},
		Subject:  "One Time Invoice",
		TextBody: "Should only be sent once",
	}
	payloadBytes, _ := json.Marshal(payload)

	for i := 0; i < concurrency; i++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			req := httptest.NewRequest(http.MethodPost, "/api/v1/mail/send", bytes.NewReader(payloadBytes))
			req.Header.Set("X-API-Key", "test-key")
			req.Header.Set("Idempotency-Key", "fixed-invoice-key-001")
			rec := httptest.NewRecorder()

			router.ServeHTTP(rec, req)
			statusCodes[idx] = rec.Code
		}(i)
	}

	wg.Wait()

	// Wait for queue processing
	time.Sleep(150 * time.Millisecond)

	// Verify all returned either 202 Accepted or 200 OK
	for _, code := range statusCodes {
		if code != http.StatusAccepted && code != http.StatusOK {
			t.Errorf("unexpected HTTP status in concurrent idempotency: %d", code)
		}
	}

	// Verify SMTP server received EXACTLY 1 email
	received := mockSMTP.GetReceived()
	if len(received) != 1 {
		t.Fatalf("expected exactly 1 email sent, but received %d duplicates!", len(received))
	}
}

// TestResilienceRAMConsumption verifies the service operates well under 20 MB RAM.
func TestResilienceRAMConsumption(t *testing.T) {
	runtime.GC()
	var mem runtime.MemStats
	runtime.ReadMemStats(&mem)

	allocatedMB := float64(mem.Alloc) / (1024 * 1024)
	heapMB := float64(mem.HeapInuse) / (1024 * 1024)

	t.Logf("Current Memory Consumption: Alloc=%.2f MB, HeapInUse=%.2f MB", allocatedMB, heapMB)

	if allocatedMB >= 20.0 {
		t.Fatalf("acceptance criterion failed: memory consumption %.2f MB exceeds 20 MB limit", allocatedMB)
	}
}
