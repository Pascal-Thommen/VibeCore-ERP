package template

import (
	"strings"
	"testing"
)

func TestDefaultTemplates(t *testing.T) {
	engine := NewEngine()

	// Test invoice template
	data := map[string]any{
		"InvoiceNumber": "INV-2026-001",
		"CustomerName":  "Carlos Martinez",
		"DueDate":        "2026-11-01",
		"TotalAmount":   "1.500.000",
		"Currency":      "PYG",
	}

	html, text, err := engine.Render("invoice", data)
	if err != nil {
		t.Fatalf("unexpected error rendering invoice template: %v", err)
	}

	if !strings.Contains(html, "INV-2026-001") || !strings.Contains(html, "Carlos Martinez") {
		t.Errorf("HTML output missing expected invoice data: %s", html)
	}
	if !strings.Contains(text, "INV-2026-001") || !strings.Contains(text, "1.500.000 PYG") {
		t.Errorf("Text output missing expected invoice data: %s", text)
	}
}

func TestTemplateXSSAutoEscaping(t *testing.T) {
	engine := NewEngine()

	data := map[string]any{
		"Title":   "<script>alert('xss')</script>",
		"Message": "Hello <world>",
	}

	html, _, err := engine.Render("notification", data)
	if err != nil {
		t.Fatalf("unexpected error rendering notification template: %v", err)
	}

	if strings.Contains(html, "<script>") {
		t.Errorf("XSS script tag was not auto-escaped in HTML output: %s", html)
	}
	if !strings.Contains(html, "&lt;script&gt;") {
		t.Errorf("Expected HTML entity escaping in output: %s", html)
	}
}

func TestCustomTemplateRegistration(t *testing.T) {
	engine := NewEngine()

	err := engine.Register("custom_order", "<h1>Order {{.OrderID}}</h1>", "Order {{.OrderID}}")
	if err != nil {
		t.Fatalf("failed to register custom template: %v", err)
	}

	html, text, err := engine.Render("custom_order", map[string]any{"OrderID": "ORD-999"})
	if err != nil {
		t.Fatalf("failed to render custom template: %v", err)
	}

	if !strings.Contains(html, "<h1>Order ORD-999</h1>") {
		t.Errorf("unexpected HTML output: %s", html)
	}
	if text != "Order ORD-999" {
		t.Errorf("unexpected text output: %s", text)
	}
}

func TestMissingTemplate(t *testing.T) {
	engine := NewEngine()
	_, _, err := engine.Render("non_existent", nil)
	if err == nil {
		t.Fatal("expected error for non-existent template, got nil")
	}
}
