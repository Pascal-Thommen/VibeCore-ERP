package tests

import (
	"bufio"
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"io"
	"log/slog"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
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

// MockSMTPServer is an RFC 5321 compliant local TCP SMTP test server.
type MockSMTPServer struct {
	listener net.Listener
	port     int
	mu       sync.Mutex
	received []string
	closed   bool
	reject   bool
}

func startMockSMTPServer(t *testing.T) *MockSMTPServer {
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed starting mock smtp server: %v", err)
	}

	server := &MockSMTPServer{
		listener: l,
		port:     l.Addr().(*net.TCPAddr).Port,
		received: make([]string, 0),
	}

	go server.serve()
	return server
}

func (s *MockSMTPServer) serve() {
	for {
		conn, err := s.listener.Accept()
		if err != nil {
			return
		}
		go s.handleConn(conn)
	}
}

func (s *MockSMTPServer) handleConn(conn net.Conn) {
	defer conn.Close()

	reader := bufio.NewReader(conn)
	writer := bufio.NewWriter(conn)

	// Send initial greeting
	_, _ = writer.WriteString("220 mock.smtp.vibecore.local ESMTP Mock\r\n")
	_ = writer.Flush()

	var dataBuf strings.Builder
	inData := false

	for {
		line, err := reader.ReadString('\n')
		if err != nil {
			return
		}

		if inData {
			if strings.TrimRight(line, "\r\n") == "." {
				inData = false
				s.mu.Lock()
				s.received = append(s.received, dataBuf.String())
				s.mu.Unlock()
				_, _ = writer.WriteString("250 2.0.0 OK queued as MOCK12345\r\n")
				_ = writer.Flush()
			} else {
				dataBuf.WriteString(line)
			}
			continue
		}

		upper := strings.ToUpper(strings.TrimSpace(line))
		switch {
		case strings.HasPrefix(upper, "EHLO") || strings.HasPrefix(upper, "HELO"):
			_, _ = writer.WriteString("250-mock.smtp.vibecore.local\r\n250-8BITMIME\r\n250 OK\r\n")
		case strings.HasPrefix(upper, "MAIL FROM:"):
			s.mu.Lock()
			reject := s.reject
			s.mu.Unlock()
			if reject {
				_, _ = writer.WriteString("451 4.3.0 Temporary delivery error\r\n")
			} else {
				_, _ = writer.WriteString("250 2.1.0 Sender OK\r\n")
			}
		case strings.HasPrefix(upper, "RCPT TO:"):
			_, _ = writer.WriteString("250 2.1.5 Recipient OK\r\n")
		case upper == "DATA":
			inData = true
			dataBuf.Reset()
			_, _ = writer.WriteString("354 Start mail input; end with <CRLF>.<CRLF>\r\n")
		case upper == "QUIT":
			_, _ = writer.WriteString("221 2.0.0 Bye\r\n")
			_ = writer.Flush()
			return
		default:
			_, _ = writer.WriteString("250 OK\r\n")
		}
		_ = writer.Flush()
	}
}

func (s *MockSMTPServer) Close() {
	s.mu.Lock()
	defer s.mu.Unlock()
	if !s.closed {
		s.closed = true
		_ = s.listener.Close()
	}
}

func (s *MockSMTPServer) GetReceived() []string {
	s.mu.Lock()
	defer s.mu.Unlock()
	res := make([]string, len(s.received))
	copy(res, s.received)
	return res
}

func (s *MockSMTPServer) SetReject(reject bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.reject = reject
}

func TestEndToEndEmailDelivery(t *testing.T) {
	mockSMTP := startMockSMTPServer(t)
	defer mockSMTP.Close()

	tmpDir, err := os.MkdirTemp("", "e2e_test_*")
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

	webhookReceived := make(chan models.StatusEvent, 5)
	webhookSecret := "e2e-webhook-secret-999"

	statusServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		sig := r.Header.Get("X-VibeCore-Signature")

		mac := hmac.New(sha256.New, []byte(webhookSecret))
		mac.Write(body)
		expectedSig := hex.EncodeToString(mac.Sum(nil))

		if sig != expectedSig {
			t.Errorf("webhook signature mismatch: got %s, expected %s", sig, expectedSig)
		}

		var evt models.StatusEvent
		_ = json.Unmarshal(body, &evt)
		webhookReceived <- evt
		w.WriteHeader(http.StatusOK)
	}))
	defer statusServer.Close()

	cfg := &config.Config{
		Host:                   "127.0.0.1",
		Port:                   8025,
		APIKey:                 "test-secret-key",
		Environment:            "test",
		SMTPHost:               "127.0.0.1",
		SMTPPort:               mockSMTP.port,
		SMTPFromEmail:          "billing@vibecore.local",
		SMTPFromName:           "VibeCore Billing",
		SMTPTLSPolicy:          "none",
		SMTPConnectTimeout:     5 * time.Second,
		SMTPSendTimeout:        5 * time.Second,
		QueueWorkerConcurrency: 1,
		QueuePollInterval:      10 * time.Millisecond,
		QueueBaseBackoff:       50 * time.Millisecond,
		QueueMaxRetries:        3,
		MaxAttachmentSizeBytes: 10 * 1024 * 1024,
		StatusWebhookURL:       statusServer.URL,
		StatusWebhookSecret:    webhookSecret,
		StatusWebhookTimeout:   2 * time.Second,
	}

	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	tmplEngine := template.NewEngine()
	tracker := status.NewTracker(cfg, q, logger)

	sender, err := smtp.NewSMTPSender(cfg)
	if err != nil {
		t.Fatalf("failed initializing smtp sender: %v", err)
	}

	proc := queue.NewProcessor(cfg, q, sender, tmplEngine, tracker, logger)
	if err := proc.Start(); err != nil {
		t.Fatalf("failed starting processor: %v", err)
	}
	defer proc.Stop()

	apiService := api.NewAPI(cfg, q, proc, tracker, tmplEngine, logger)
	whHandler := webhooks.NewHandler(cfg, q, tracker, logger)
	router := api.NewRouter(cfg, apiService, whHandler, logger)

	// 1. Submit email via POST /api/v1/mail/send
	pdfContent := "%PDF-1.4 Factura electronica de prueba"
	sendReq := models.SendMailRequest{
		To:       []string{"carlos.martinez@cliente.py"},
		Subject:  "Factura Electrónica F-001-002-000456",
		Template: "invoice",
		TemplateData: map[string]any{
			"InvoiceNumber": "F-001-002-000456",
			"CustomerName":  "Carlos Martinez",
			"DueDate":        "2026-10-31",
			"TotalAmount":   "2.450.000",
			"Currency":      "PYG",
		},
		Attachments: []models.Attachment{
			{
				Filename:    "factura_456.pdf",
				ContentType: "application/pdf",
				Data:        base64.StdEncoding.EncodeToString([]byte(pdfContent)),
			},
		},
		Metadata: map[string]any{
			"order_id": "ORD-1234",
		},
	}

	reqBytes, _ := json.Marshal(sendReq)
	httpReq := httptest.NewRequest(http.MethodPost, "/api/v1/mail/send", bytes.NewReader(reqBytes))
	httpReq.Header.Set("X-API-Key", "test-secret-key")
	httpReq.Header.Set("X-Correlation-ID", "corr_e2e_001")
	httpRec := httptest.NewRecorder()

	router.ServeHTTP(httpRec, httpReq)

	if httpRec.Code != http.StatusAccepted {
		t.Fatalf("expected 202 Accepted, got %d body: %s", httpRec.Code, httpRec.Body.String())
	}

	var acceptedResp map[string]any
	_ = json.Unmarshal(httpRec.Body.Bytes(), &acceptedResp)
	mailID := acceptedResp["id"].(string)

	// 2. Poll status endpoint until SENT
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	var finalStatus *models.StatusResponse
	for {
		select {
		case <-ctx.Done():
			t.Fatal("timed out waiting for email to be delivered")
		default:
			stat, err := tracker.GetStatus(context.Background(), mailID)
			if err == nil && stat.State == models.MailStateSent {
				finalStatus = stat
				break
			}
			time.Sleep(20 * time.Millisecond)
		}
		if finalStatus != nil {
			break
		}
	}

	if finalStatus.State != models.MailStateSent {
		t.Fatalf("expected state SENT, got %s", finalStatus.State)
	}
	if finalStatus.SentAt == nil {
		t.Fatal("expected non-nil SentAt")
	}

	// 3. Verify SMTP server received the message
	received := mockSMTP.GetReceived()
	if len(received) == 0 {
		t.Fatal("mock SMTP server did not receive any email")
	}

	smtpRaw := received[0]
	if !strings.Contains(smtpRaw, "F-001-002-000456") {
		t.Errorf("SMTP raw output missing invoice number: %s", smtpRaw)
	}
	if !strings.Contains(smtpRaw, "Carlos Martinez") {
		t.Errorf("SMTP raw output missing customer name: %s", smtpRaw)
	}
	if !strings.Contains(smtpRaw, "factura_456.pdf") {
		t.Errorf("SMTP raw output missing attachment filename: %s", smtpRaw)
	}

	// 4. Verify webhook received status events
	select {
	case evt := <-webhookReceived:
		if evt.MessageID != mailID {
			t.Errorf("expected webhook event message ID %s, got %s", mailID, evt.MessageID)
		}
	case <-time.After(1 * time.Second):
		t.Fatal("timed out waiting for status webhook event")
	}
}
