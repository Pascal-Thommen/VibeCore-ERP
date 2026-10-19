package api

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
	"testing"
	"time"

	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/config"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/models"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/queue"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/status"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/template"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/webhooks"
)

type dummySender struct{}

func (d *dummySender) Send(ctx context.Context, req *models.SendMailRequest) error {
	return nil
}

func setupTestRouter(t *testing.T, apiKey string) (http.Handler, *queue.BoltQueue, string) {
	tmpDir, err := os.MkdirTemp("", "api_test_*")
	if err != nil {
		t.Fatalf("failed creating temp dir: %v", err)
	}
	dbPath := filepath.Join(tmpDir, "queue.db")

	q, err := queue.NewBoltQueue(dbPath)
	if err != nil {
		os.RemoveAll(tmpDir)
		t.Fatalf("failed creating queue: %v", err)
	}

	cfg := &config.Config{
		APIKey:                 apiKey,
		QueueWorkerConcurrency: 1,
		QueuePollInterval:      10 * time.Millisecond,
		MaxAttachmentSizeBytes: 10 * 1024 * 1024,
	}

	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	tmplEngine := template.NewEngine()
	tracker := status.NewTracker(cfg, q, logger)
	proc := queue.NewProcessor(cfg, q, &dummySender{}, tmplEngine, tracker, logger)
	_ = proc.Start()

	apiService := NewAPI(cfg, q, proc, tracker, tmplEngine, logger)
	whHandler := webhooks.NewHandler(cfg, q, tracker, logger)

	router := NewRouter(cfg, apiService, whHandler, logger)
	return router, q, tmpDir
}

func TestHealthAndMetricsEndpoints(t *testing.T) {
	router, q, tmpDir := setupTestRouter(t, "test-api-key")
	defer os.RemoveAll(tmpDir)
	defer q.Close()

	// 1. Health
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected /health 200 OK, got %d", rec.Code)
	}

	// 2. Ready
	reqReady := httptest.NewRequest(http.MethodGet, "/ready", nil)
	recReady := httptest.NewRecorder()
	router.ServeHTTP(recReady, reqReady)

	if recReady.Code != http.StatusOK {
		t.Fatalf("expected /ready 200 OK, got %d", recReady.Code)
	}

	// 3. Metrics
	reqMetrics := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	recMetrics := httptest.NewRecorder()
	router.ServeHTTP(recMetrics, reqMetrics)

	if recMetrics.Code != http.StatusOK {
		t.Fatalf("expected /metrics 200 OK, got %d", recMetrics.Code)
	}

	var metricsResp map[string]any
	if err := json.Unmarshal(recMetrics.Body.Bytes(), &metricsResp); err != nil {
		t.Fatalf("invalid metrics json: %v", err)
	}
	memData, ok := metricsResp["memory"].(map[string]any)
	if !ok {
		t.Fatalf("metrics missing memory block: %+v", metricsResp)
	}
	if underTarget, ok := memData["under_20mb_target"].(bool); !ok || !underTarget {
		t.Errorf("expected memory consumption under 20MB, got: %+v", memData)
	}
}

func TestAuthMiddleware(t *testing.T) {
	router, q, tmpDir := setupTestRouter(t, "secret-key-123")
	defer os.RemoveAll(tmpDir)
	defer q.Close()

	// Request without API Key -> 401 Unauthorized
	req := httptest.NewRequest(http.MethodPost, "/api/v1/mail/send", bytes.NewReader([]byte("{}")))
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401 Unauthorized, got %d", rec.Code)
	}

	// Request with wrong API Key -> 401 Unauthorized
	reqWrong := httptest.NewRequest(http.MethodPost, "/api/v1/mail/send", bytes.NewReader([]byte("{}")))
	reqWrong.Header.Set("X-API-Key", "wrong-key")
	recWrong := httptest.NewRecorder()
	router.ServeHTTP(recWrong, reqWrong)

	if recWrong.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401 Unauthorized for wrong key, got %d", recWrong.Code)
	}
}

func TestSendMailAndIdempotency(t *testing.T) {
	router, q, tmpDir := setupTestRouter(t, "secret-key-123")
	defer os.RemoveAll(tmpDir)
	defer q.Close()

	payload := models.SendMailRequest{
		To:       []string{"client@test.com"},
		Subject:  "Factura electrónica 001",
		Template: "invoice",
		TemplateData: map[string]any{
			"InvoiceNumber": "F-001-002",
			"CustomerName":  "Carlos Gomez",
			"DueDate":        "2026-11-15",
			"TotalAmount":   "750.000",
			"Currency":      "PYG",
		},
	}
	bodyBytes, _ := json.Marshal(payload)

	// Send with Idempotency-Key
	req := httptest.NewRequest(http.MethodPost, "/api/v1/mail/send", bytes.NewReader(bodyBytes))
	req.Header.Set("X-API-Key", "secret-key-123")
	req.Header.Set("Idempotency-Key", "idem_factura_001")
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusAccepted {
		t.Fatalf("expected 202 Accepted, got %d, body: %s", rec.Code, rec.Body.String())
	}

	var resp map[string]any
	_ = json.Unmarshal(rec.Body.Bytes(), &resp)
	mailID, ok := resp["id"].(string)
	if !ok || mailID == "" {
		t.Fatalf("expected response id, got: %+v", resp)
	}

	// Send identical request with same Idempotency-Key -> should return 200 with duplicate=true
	reqDup := httptest.NewRequest(http.MethodPost, "/api/v1/mail/send", bytes.NewReader(bodyBytes))
	reqDup.Header.Set("X-API-Key", "secret-key-123")
	reqDup.Header.Set("Idempotency-Key", "idem_factura_001")
	recDup := httptest.NewRecorder()
	router.ServeHTTP(recDup, reqDup)

	if recDup.Code != http.StatusOK {
		t.Fatalf("expected 200 OK for duplicate idempotency key, got %d, body: %s", recDup.Code, recDup.Body.String())
	}

	var respDup map[string]any
	_ = json.Unmarshal(recDup.Body.Bytes(), &respDup)
	if respDup["duplicate"] != true || respDup["id"] != mailID {
		t.Fatalf("expected duplicate record matching original mailID, got: %+v", respDup)
	}

	// Wait for worker to send and update status
	time.Sleep(100 * time.Millisecond)

	// Query status via GET /api/v1/mail/status/{id}
	reqStatus := httptest.NewRequest(http.MethodGet, "/api/v1/mail/status/"+mailID, nil)
	reqStatus.Header.Set("X-API-Key", "secret-key-123")
	recStatus := httptest.NewRecorder()
	router.ServeHTTP(recStatus, reqStatus)

	if recStatus.Code != http.StatusOK {
		t.Fatalf("expected 200 OK for status, got %d, body: %s", recStatus.Code, recStatus.Body.String())
	}

	var statusData models.StatusResponse
	_ = json.Unmarshal(recStatus.Body.Bytes(), &statusData)
	if statusData.ID != mailID || statusData.State != models.MailStateSent {
		t.Fatalf("expected status SENT for mail %s, got %+v", mailID, statusData)
	}
}

func TestTemplateEndpoints(t *testing.T) {
	router, q, tmpDir := setupTestRouter(t, "key")
	defer os.RemoveAll(tmpDir)
	defer q.Close()

	// List templates
	reqList := httptest.NewRequest(http.MethodGet, "/api/v1/mail/templates", nil)
	reqList.Header.Set("X-API-Key", "key")
	recList := httptest.NewRecorder()
	router.ServeHTTP(recList, reqList)

	if recList.Code != http.StatusOK {
		t.Fatalf("expected 200 OK, got %d", recList.Code)
	}

	// Register new template
	regPayload := map[string]string{
		"name": "receipt",
		"html": "<h2>Recibo {{.ReceiptNo}}</h2>",
		"text": "Recibo {{.ReceiptNo}}",
	}
	regBytes, _ := json.Marshal(regPayload)
	reqReg := httptest.NewRequest(http.MethodPost, "/api/v1/mail/templates", bytes.NewReader(regBytes))
	reqReg.Header.Set("X-API-Key", "key")
	recReg := httptest.NewRecorder()
	router.ServeHTTP(recReg, reqReg)

	if recReg.Code != http.StatusCreated {
		t.Fatalf("expected 201 Created, got %d, body: %s", recReg.Code, recReg.Body.String())
	}
}
