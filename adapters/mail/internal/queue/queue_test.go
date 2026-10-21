package queue

import (
	"context"
	"errors"
	"log/slog"
	"os"
	"path/filepath"
	"sync"
	"testing"
	"time"

	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/config"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/models"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/template"
)

// MockSender tracks send calls and simulates successes or transient/permanent errors.
type MockSender struct {
	mu        sync.Mutex
	failCount int
	calls     int
}

func (m *MockSender) Send(ctx context.Context, req *models.SendMailRequest) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.calls++
	if m.failCount > 0 {
		m.failCount--
		return errors.New("simulated network connection failure")
	}
	return nil
}

// MockDispatcher captures events.
type MockDispatcher struct {
	mu     sync.Mutex
	events []models.StatusEvent
}

func (m *MockDispatcher) Dispatch(ctx context.Context, event models.StatusEvent) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.events = append(m.events, event)
}

func setupTestQueue(t *testing.T) (*BoltQueue, string) {
	tmpDir, err := os.MkdirTemp("", "bolt_test_*")
	if err != nil {
		t.Fatalf("failed creating temp dir: %v", err)
	}
	dbPath := filepath.Join(tmpDir, "queue.db")

	q, err := NewBoltQueue(dbPath)
	if err != nil {
		os.RemoveAll(tmpDir)
		t.Fatalf("failed creating bolt queue: %v", err)
	}

	return q, tmpDir
}

func TestQueueEnqueueAndGet(t *testing.T) {
	q, tmpDir := setupTestQueue(t)
	defer os.RemoveAll(tmpDir)
	defer q.Close()

	ctx := context.Background()
	item := &models.QueuedMail{
		ID:             "msg_001",
		IdempotencyKey: "idem_abc",
		Request: models.SendMailRequest{
			To:      []string{"test@example.com"},
			Subject: "Test Subject",
			TextBody: "Hello",
		},
		State: models.MailStateQueued,
	}

	if err := q.Enqueue(ctx, item); err != nil {
		t.Fatalf("failed enqueuing item: %v", err)
	}

	got, err := q.Get(ctx, "msg_001")
	if err != nil {
		t.Fatalf("failed getting item: %v", err)
	}
	if got.ID != "msg_001" || got.Request.Subject != "Test Subject" {
		t.Fatalf("mismatched retrieved item: %+v", got)
	}

	gotIdem, err := q.GetByIdempotencyKey(ctx, "idem_abc")
	if err != nil {
		t.Fatalf("failed getting item by idempotency key: %v", err)
	}
	if gotIdem.ID != "msg_001" {
		t.Fatalf("expected ID 'msg_001', got '%s'", gotIdem.ID)
	}

	// Test duplicate idempotency key
	dup := &models.QueuedMail{
		ID:             "msg_002",
		IdempotencyKey: "idem_abc",
		Request: models.SendMailRequest{
			To: []string{"test2@example.com"},
		},
	}
	if err := q.Enqueue(ctx, dup); err == nil {
		t.Fatal("expected duplicate idempotency key error, got nil")
	}
}

func TestQueueInflightRecovery(t *testing.T) {
	q, tmpDir := setupTestQueue(t)
	defer os.RemoveAll(tmpDir)
	defer q.Close()

	ctx := context.Background()
	item := &models.QueuedMail{
		ID:    "msg_hanging",
		State: models.MailStateSending, // simulated crash during send
	}
	if err := q.Enqueue(ctx, item); err != nil {
		t.Fatalf("failed enqueue: %v", err)
	}

	recovered, err := q.RecoverInflight(ctx)
	if err != nil {
		t.Fatalf("failed inflight recovery: %v", err)
	}
	if recovered != 1 {
		t.Fatalf("expected 1 recovered item, got %d", recovered)
	}

	got, _ := q.Get(ctx, "msg_hanging")
	if got.State != models.MailStateQueued {
		t.Fatalf("expected recovered item state QUEUED, got %s", got.State)
	}
}

func TestProcessorSuccessDelivery(t *testing.T) {
	q, tmpDir := setupTestQueue(t)
	defer os.RemoveAll(tmpDir)
	defer q.Close()

	cfg := &config.Config{
		QueueWorkerConcurrency: 1,
		QueuePollInterval:      10 * time.Millisecond,
		QueueBaseBackoff:       50 * time.Millisecond,
		QueueMaxRetries:        3,
		SMTPSendTimeout:        1 * time.Second,
	}

	sender := &MockSender{}
	dispatcher := &MockDispatcher{}
	tmplEngine := template.NewEngine()
	logger := slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelError}))

	proc := NewProcessor(cfg, q, sender, tmplEngine, dispatcher, logger)
	if err := proc.Start(); err != nil {
		t.Fatalf("failed starting processor: %v", err)
	}
	defer proc.Stop()

	item := &models.QueuedMail{
		ID: "msg_success",
		Request: models.SendMailRequest{
			To:      []string{"buyer@example.com"},
			Subject: "Order Confirmation",
			Template: "invoice",
			TemplateData: map[string]any{
				"InvoiceNumber": "INV-100",
				"CustomerName":  "Ana Gomez",
				"DueDate":        "2026-10-30",
				"TotalAmount":   "500.000",
				"Currency":      "PYG",
			},
		},
	}

	if err := proc.EnqueueRequest(context.Background(), item); err != nil {
		t.Fatalf("failed enqueuing request: %v", err)
	}

	// Wait for worker to process
	time.Sleep(100 * time.Millisecond)

	stored, err := q.Get(context.Background(), "msg_success")
	if err != nil {
		t.Fatalf("failed retrieving processed item: %v", err)
	}

	if stored.State != models.MailStateSent {
		t.Fatalf("expected state SENT, got %s (last error: %s)", stored.State, stored.LastError)
	}
	if stored.SentAt == nil {
		t.Fatal("expected SentAt timestamp to be set")
	}
}

func TestProcessorRetryAndDeadLetterQueue(t *testing.T) {
	q, tmpDir := setupTestQueue(t)
	defer os.RemoveAll(tmpDir)
	defer q.Close()

	cfg := &config.Config{
		QueueWorkerConcurrency: 1,
		QueuePollInterval:      10 * time.Millisecond,
		QueueBaseBackoff:       10 * time.Millisecond,
		QueueMaxBackoff:        50 * time.Millisecond,
		QueueMaxRetries:        2, // Max 2 attempts then FAILED
		SMTPSendTimeout:        1 * time.Second,
	}

	sender := &MockSender{failCount: 5} // always fails
	dispatcher := &MockDispatcher{}
	tmplEngine := template.NewEngine()
	logger := slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelError}))

	proc := NewProcessor(cfg, q, sender, tmplEngine, dispatcher, logger)
	if err := proc.Start(); err != nil {
		t.Fatalf("failed starting processor: %v", err)
	}
	defer proc.Stop()

	item := &models.QueuedMail{
		ID: "msg_fail",
		Request: models.SendMailRequest{
			To:       []string{"fail@example.com"},
			Subject:  "Will Fail",
			TextBody: "Error test",
		},
	}

	if err := proc.EnqueueRequest(context.Background(), item); err != nil {
		t.Fatalf("failed enqueuing request: %v", err)
	}

	// Poll until attempts reach max
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	for {
		select {
		case <-ctx.Done():
			t.Fatal("timed out waiting for message to fail")
		default:
			stored, _ := q.Get(context.Background(), "msg_fail")
			if stored != nil && stored.State == models.MailStateFailed {
				if stored.Attempts != 2 {
					t.Fatalf("expected 2 attempts, got %d", stored.Attempts)
				}
				if stored.LastError == "" {
					t.Fatal("expected last_error to be recorded")
				}
				return
			}
			time.Sleep(20 * time.Millisecond)
		}
	}
}
