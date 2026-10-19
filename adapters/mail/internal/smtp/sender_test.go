package smtp

import (
	"encoding/base64"
	"strings"
	"testing"
	"time"

	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/config"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/models"
	"github.com/wneessen/go-mail"
)

func TestBuildMessageValid(t *testing.T) {
	cfg := &config.Config{
		SMTPHost:           "127.0.0.1",
		SMTPPort:           1025,
		SMTPFromEmail:      "noreply@vibecore.local",
		SMTPFromName:       "VibeCore Test",
		SMTPTLSPolicy:      "none",
		SMTPConnectTimeout: 5 * time.Second,
	}

	sender, err := NewSMTPSender(cfg)
	if err != nil {
		t.Fatalf("failed creating sender: %v", err)
	}

	pdfData := base64.StdEncoding.EncodeToString([]byte("%PDF-1.4 mock pdf content"))

	req := &models.SendMailRequest{
		From:     "billing@vibecore.local",
		FromName: "VibeCore Billing",
		To:       []string{"client@example.com"},
		Cc:       []string{"cc@example.com"},
		Bcc:      []string{"bcc@example.com"},
		ReplyTo:  "support@vibecore.local",
		Subject:  "Factura electrónica F-001-002-1234567",
		TextBody: "Anbei Ihre Rechnung.",
		HTMLBody: "<p>Anbei Ihre Rechnung.</p>",
		Headers: map[string]string{
			"X-VibeCore-Invoice": "1234567",
		},
		Attachments: []models.Attachment{
			{
				Filename:    "factura.pdf",
				ContentType: "application/pdf",
				Data:        pdfData,
			},
		},
	}

	msg, err := sender.BuildMessage(req)
	if err != nil {
		t.Fatalf("failed building message: %v", err)
	}

	subjects := msg.GetGenHeader(mail.HeaderSubject)
	if len(subjects) == 0 || !strings.Contains(subjects[0], "Factura") {
		t.Errorf("expected subject to contain 'Factura', got '%v'", subjects)
	}

	toRecipients := msg.GetToString()
	if len(toRecipients) == 0 || !strings.Contains(toRecipients[0], "client@example.com") {
		t.Errorf("expected to recipient to contain 'client@example.com', got '%v'", toRecipients)
	}

	attachments := msg.GetAttachments()
	if len(attachments) != 1 {
		t.Fatalf("expected 1 attachment, got %d", len(attachments))
	}
}

func TestBuildMessageMissingRecipients(t *testing.T) {
	cfg := &config.Config{
		SMTPHost:      "127.0.0.1",
		SMTPPort:      1025,
		SMTPFromEmail: "noreply@vibecore.local",
		SMTPTLSPolicy: "none",
	}

	sender, _ := NewSMTPSender(cfg)

	req := &models.SendMailRequest{
		Subject:  "No Recipients",
		TextBody: "Hello",
	}

	_, err := sender.BuildMessage(req)
	if err == nil {
		t.Fatal("expected error when recipients list is empty, got nil")
	}
}

func TestBuildMessageInvalidAttachmentBase64(t *testing.T) {
	cfg := &config.Config{
		SMTPHost:      "127.0.0.1",
		SMTPPort:      1025,
		SMTPFromEmail: "noreply@vibecore.local",
		SMTPTLSPolicy: "none",
	}

	sender, _ := NewSMTPSender(cfg)

	req := &models.SendMailRequest{
		To:       []string{"test@example.com"},
		Subject:  "Invalid Attachment",
		TextBody: "Hello",
		Attachments: []models.Attachment{
			{
				Filename: "corrupted.bin",
				Data:     "not-valid-base64!@@#$",
			},
		},
	}

	_, err := sender.BuildMessage(req)
	if err == nil {
		t.Fatal("expected error for corrupted attachment data, got nil")
	}
}
