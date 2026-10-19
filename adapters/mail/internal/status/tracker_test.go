package status

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/config"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/models"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/queue"
)

func TestTrackerGetStatus(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "tracker_test_*")
	if err != nil {
		t.Fatalf("failed creating temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	dbPath := filepath.Join(tmpDir, "queue.db")
	q, err := queue.NewBoltQueue(dbPath)
	if err != nil {
		t.Fatalf("failed creating queue: %v", err)
	}
	defer q.Close()

	ctx := context.Background()
	now := time.Now()
	item := &models.QueuedMail{
		ID:            "msg_status_test",
		CorrelationID: "corr_123",
		State:         models.MailStateSent,
		Attempts:      1,
		MaxAttempts:   5,
		CreatedAt:     now,
		UpdatedAt:     now,
		SentAt:        &now,
		Request: models.SendMailRequest{
			To: []string{"client@test.com"},
			Metadata: map[string]any{
				"invoice_id": "INV-555",
			},
		},
	}
	if err := q.Enqueue(ctx, item); err != nil {
		t.Fatalf("failed enqueuing item: %v", err)
	}

	cfg := &config.Config{}
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	tracker := NewTracker(cfg, q, logger)

	statusResp, err := tracker.GetStatus(ctx, "msg_status_test")
	if err != nil {
		t.Fatalf("unexpected error getting status: %v", err)
	}

	if statusResp.ID != "msg_status_test" || statusResp.State != models.MailStateSent {
		t.Fatalf("mismatched status response: %+v", statusResp)
	}
	if statusResp.Metadata["invoice_id"] != "INV-555" {
		t.Fatalf("expected invoice_id metadata, got %+v", statusResp.Metadata)
	}
}

func TestTrackerWebhookDispatchWithHMAC(t *testing.T) {
	tmpDir, _ := os.MkdirTemp("", "tracker_wh_*")
	defer os.RemoveAll(tmpDir)
	q, _ := queue.NewBoltQueue(filepath.Join(tmpDir, "queue.db"))
	defer q.Close()

	secret := "super-secure-webhook-secret-32b"
	receivedSig := ""
	receivedCorr := ""
	var receivedBody []byte

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedSig = r.Header.Get("X-VibeCore-Signature")
		receivedCorr = r.Header.Get("X-Correlation-ID")
		receivedBody, _ = io.ReadAll(r.Body)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	cfg := &config.Config{
		StatusWebhookURL:     srv.URL,
		StatusWebhookSecret:  secret,
		StatusWebhookTimeout: 2 * time.Second,
	}
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	tracker := NewTracker(cfg, q, logger)

	event := models.StatusEvent{
		EventID:       "evt_001",
		EventType:     "mail.sent",
		Timestamp:     time.Now(),
		MessageID:     "msg_999",
		CorrelationID: "corr_xyz",
		State:         models.MailStateSent,
	}

	err := tracker.forwardWebhookWithRetry(context.Background(), event)
	if err != nil {
		t.Fatalf("unexpected webhook error: %v", err)
	}

	if receivedCorr != "corr_xyz" {
		t.Errorf("expected correlation ID 'corr_xyz', got '%s'", receivedCorr)
	}

	// Verify HMAC signature
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(receivedBody)
	expectedSig := hex.EncodeToString(mac.Sum(nil))

	if receivedSig != expectedSig {
		t.Errorf("expected HMAC signature '%s', got '%s'", expectedSig, receivedSig)
	}
}
