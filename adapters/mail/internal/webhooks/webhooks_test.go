package webhooks

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"io"
	"log/slog"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"

	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/config"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/models"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/queue"
)

type mockDispatcher struct {
	mu     sync.Mutex
	events []models.StatusEvent
}

func (m *mockDispatcher) Dispatch(ctx context.Context, event models.StatusEvent) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.events = append(m.events, event)
}

func (m *mockDispatcher) getEvents() []models.StatusEvent {
	m.mu.Lock()
	defer m.mu.Unlock()
	copied := make([]models.StatusEvent, len(m.events))
	copy(copied, m.events)
	return copied
}

func TestParseRawMIMEWithAttachment(t *testing.T) {
	rawMIME := `From: invoice-sender@supplier.com
To: ap@vibecore.local
Subject: Rechnung R-2026-888
Date: Mon, 19 Oct 2026 15:30:00 +0000
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="====BOUNDARY===="

--====BOUNDARY====
Content-Type: text/plain; charset=utf-8

Guten Tag, anbei finden Sie Ihre Rechnung.
--====BOUNDARY====
Content-Type: text/html; charset=utf-8

<p>Guten Tag, anbei finden Sie Ihre <b>Rechnung</b>.</p>
--====BOUNDARY====
Content-Type: application/pdf
Content-Disposition: attachment; filename="rechnung_888.pdf"
Content-Transfer-Encoding: base64

JVBERi0xLjQKJeLjz9MKMSAwIG9iaiA8PC9UeXBlIC9DYXRhbG9nIC9QYWdlcyAyIDAgUj4+
IGVuZG9iagoyIDAgb2JqIDw8L1R5cGUgL1BhZ2VzIC9LaWRzIFszIDAgUl0gL0NvdW50IDE+
PiBlbmRvYmoKMyAwIG9iaiA8PC9UeXBlIC9QYWdlIC9QYXJlbnQgMiAwIFIgL01lZGlhQm94
IFswIDAgNjEyIDc5Ml0+PiBlbmRvYmoKeHJlZgowIDQKMDAwMDAwMDAwMCA2NTUzNSBmIAow
MDAwMDAwMDE4IDAwMDAwIG4gCjAwMDAwMDAwNjggMDAwMDAgbiAKMDAwMDAwMDEyNSAwMDAw
MCBuIAp0cmFpbGVyIDw8L1NpemUgND4+CiUlRU9G
--====BOUNDARY====--
`

	inbound, err := ParseRawMIME(strings.NewReader(rawMIME), 10*1024*1024)
	if err != nil {
		t.Fatalf("failed parsing raw MIME: %v", err)
	}

	if inbound.Subject != "Rechnung R-2026-888" {
		t.Errorf("expected subject 'Rechnung R-2026-888', got '%s'", inbound.Subject)
	}
	if inbound.From != "invoice-sender@supplier.com" {
		t.Errorf("expected from 'invoice-sender@supplier.com', got '%s'", inbound.From)
	}
	if len(inbound.To) == 0 || inbound.To[0] != "ap@vibecore.local" {
		t.Errorf("expected to 'ap@vibecore.local', got '%v'", inbound.To)
	}
	if !strings.Contains(inbound.TextBody, "Guten Tag, anbei") {
		t.Errorf("missing text body content: %s", inbound.TextBody)
	}
	if !strings.Contains(inbound.HTMLBody, "<b>Rechnung</b>") {
		t.Errorf("missing html body content: %s", inbound.HTMLBody)
	}
	if len(inbound.Attachments) != 1 {
		t.Fatalf("expected 1 attachment, got %d", len(inbound.Attachments))
	}

	att := inbound.Attachments[0]
	if att.Filename != "rechnung_888.pdf" {
		t.Errorf("expected filename 'rechnung_888.pdf', got '%s'", att.Filename)
	}
	if att.ContentType != "application/pdf" {
		t.Errorf("expected Content-Type 'application/pdf', got '%s'", att.ContentType)
	}
	if att.Size <= 0 {
		t.Errorf("expected attachment size > 0, got %d", att.Size)
	}
	if att.SHA256 == "" {
		t.Errorf("expected computed SHA256 checksum, got empty")
	}
}

func TestHandleResendWebhook(t *testing.T) {
	tmpDir, _ := os.MkdirTemp("", "wh_test_*")
	defer os.RemoveAll(tmpDir)
	q, _ := queue.NewBoltQueue(filepath.Join(tmpDir, "queue.db"))
	defer q.Close()

	dispatcher := &mockDispatcher{}
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	handler := NewHandler(&config.Config{}, q, dispatcher, logger)

	payload := models.ResendWebhookPayload{
		Type: "email.delivered",
	}
	payload.Data.EmailID = "resend_msg_123"
	payload.Data.To = []string{"user@example.com"}

	bodyBytes, _ := json.Marshal(payload)
	req := httptest.NewRequest(http.MethodPost, "/api/v1/mail/webhooks/resend", bytes.NewReader(bodyBytes))
	rec := httptest.NewRecorder()

	handler.HandleResend(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 OK, got %d", rec.Code)
	}

	events := dispatcher.getEvents()
	if len(events) != 1 {
		t.Fatalf("expected 1 dispatched event, got %d", len(events))
	}
	if events[0].State != models.MailStateDelivered {
		t.Errorf("expected state DELIVERED, got %s", events[0].State)
	}
	if events[0].MessageID != "resend_msg_123" {
		t.Errorf("expected MessageID 'resend_msg_123', got '%s'", events[0].MessageID)
	}
}

func TestHandleBrevoWebhookBounce(t *testing.T) {
	tmpDir, _ := os.MkdirTemp("", "wh_brevo_*")
	defer os.RemoveAll(tmpDir)
	q, _ := queue.NewBoltQueue(filepath.Join(tmpDir, "queue.db"))
	defer q.Close()

	dispatcher := &mockDispatcher{}
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	handler := NewHandler(&config.Config{}, q, dispatcher, logger)

	payload := models.BrevoWebhookPayload{
		Event:     "hard_bounce",
		Email:     "invalid@nowhere.local",
		MessageID: "<brevo_msg_456@smtp.brevo.com>",
		Reason:    "mailbox does not exist",
	}

	bodyBytes, _ := json.Marshal(payload)
	req := httptest.NewRequest(http.MethodPost, "/api/v1/mail/webhooks/brevo", bytes.NewReader(bodyBytes))
	rec := httptest.NewRecorder()

	handler.HandleBrevo(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 OK, got %d", rec.Code)
	}

	events := dispatcher.getEvents()
	if len(events) != 1 {
		t.Fatalf("expected 1 dispatched event, got %d", len(events))
	}
	if events[0].State != models.MailStateBounced {
		t.Errorf("expected state BOUNCED, got %s", events[0].State)
	}
	if events[0].Error != "mailbox does not exist" {
		t.Errorf("expected bounce error recorded, got '%s'", events[0].Error)
	}
}

func TestHandleSendGridInboundParse(t *testing.T) {
	tmpDir, _ := os.MkdirTemp("", "wh_sg_*")
	defer os.RemoveAll(tmpDir)
	q, _ := queue.NewBoltQueue(filepath.Join(tmpDir, "queue.db"))
	defer q.Close()

	dispatcher := &mockDispatcher{}
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	handler := NewHandler(&config.Config{MaxAttachmentSizeBytes: 10 * 1024 * 1024}, q, dispatcher, logger)

	var b bytes.Buffer
	w := multipart.NewWriter(&b)
	_ = w.WriteField("from", "carlos@customer.com")
	_ = w.WriteField("to", "invoices@vibecore.local")
	_ = w.WriteField("subject", "Order Confirmation")
	_ = w.WriteField("text", "Please find attached the order sheet.")

	fw, _ := w.CreateFormFile("attachment1", "order.csv")
	_, _ = fw.Write([]byte("id,item,quantity\n1,Widget,5\n"))
	w.Close()

	req := httptest.NewRequest(http.MethodPost, "/api/v1/mail/webhooks/sendgrid", &b)
	req.Header.Set("Content-Type", w.FormDataContentType())
	rec := httptest.NewRecorder()

	handler.HandleSendGrid(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 OK, got %d", rec.Code)
	}

	events := dispatcher.getEvents()
	if len(events) != 1 {
		t.Fatalf("expected 1 event, got %d", len(events))
	}
	if events[0].EventType != "mail.inbound" {
		t.Errorf("expected event type 'mail.inbound', got '%s'", events[0].EventType)
	}
}

func TestHandleGenericInboundJSON(t *testing.T) {
	tmpDir, _ := os.MkdirTemp("", "wh_gen_*")
	defer os.RemoveAll(tmpDir)
	q, _ := queue.NewBoltQueue(filepath.Join(tmpDir, "queue.db"))
	defer q.Close()

	dispatcher := &mockDispatcher{}
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	handler := NewHandler(&config.Config{MaxAttachmentSizeBytes: 10 * 1024 * 1024}, q, dispatcher, logger)

	reqPayload := models.GenericInboundRequest{
		From:     "boss@enterprise.com",
		To:       []string{"notify@vibecore.local"},
		Subject:  "Direct Inbound API Notification",
		TextBody: "Operation confirmed.",
		Attachments: []models.Attachment{
			{
				Filename:    "doc.txt",
				ContentType: "text/plain",
				Data:        base64.StdEncoding.EncodeToString([]byte("Secret data")),
			},
		},
	}

	bodyBytes, _ := json.Marshal(reqPayload)
	req := httptest.NewRequest(http.MethodPost, "/api/v1/mail/webhooks/generic", bytes.NewReader(bodyBytes))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()

	handler.HandleGeneric(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 OK, got %d, body: %s", rec.Code, rec.Body.String())
	}

	events := dispatcher.getEvents()
	if len(events) != 1 {
		t.Fatalf("expected 1 event, got %d", len(events))
	}
	inbound, ok := events[0].Payload.(*models.InboundMail)
	if !ok {
		t.Fatalf("expected payload to be *models.InboundMail, got %T", events[0].Payload)
	}
	if inbound.Subject != "Direct Inbound API Notification" {
		t.Errorf("expected subject matched, got '%s'", inbound.Subject)
	}
	if len(inbound.Attachments) != 1 || inbound.Attachments[0].Filename != "doc.txt" {
		t.Errorf("expected 1 sanitized attachment, got %+v", inbound.Attachments)
	}
}
