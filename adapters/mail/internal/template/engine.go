package template

import (
	"bytes"
	"fmt"
	htmltmpl "html/template"
	"sync"
	texttmpl "text/template"
)

// Engine manages HTML and text templates with safe auto-escaping.
type Engine struct {
	mu            sync.RWMutex
	htmlTemplates map[string]*htmltmpl.Template
	textTemplates map[string]*texttmpl.Template
}

// NewEngine initializes a template engine with default VibeCore templates.
func NewEngine() *Engine {
	e := &Engine{
		htmlTemplates: make(map[string]*htmltmpl.Template),
		textTemplates: make(map[string]*texttmpl.Template),
	}

	e.registerDefaults()
	return e
}

// Register registers or updates a template pair (HTML and Plaintext).
func (e *Engine) Register(name, htmlSrc, textSrc string) error {
	e.mu.Lock()
	defer e.mu.Unlock()

	ht, err := htmltmpl.New(name).Parse(htmlSrc)
	if err != nil {
		return fmt.Errorf("failed to parse HTML template '%s': %w", name, err)
	}

	tt, err := texttmpl.New(name).Parse(textSrc)
	if err != nil {
		return fmt.Errorf("failed to parse text template '%s': %w", name, err)
	}

	e.htmlTemplates[name] = ht
	e.textTemplates[name] = tt
	return nil
}

// Render renders both HTML and text representations of the given template.
func (e *Engine) Render(name string, data any) (htmlBody, textBody string, err error) {
	e.mu.RLock()
	ht, hExists := e.htmlTemplates[name]
	tt, tExists := e.textTemplates[name]
	e.mu.RUnlock()

	if !hExists && !tExists {
		return "", "", fmt.Errorf("template '%s' not found", name)
	}

	if hExists {
		var hBuf bytes.Buffer
		if err := ht.Execute(&hBuf, data); err != nil {
			return "", "", fmt.Errorf("failed executing HTML template '%s': %w", name, err)
		}
		htmlBody = hBuf.String()
	}

	if tExists {
		var tBuf bytes.Buffer
		if err := tt.Execute(&tBuf, data); err != nil {
			return "", "", fmt.Errorf("failed executing text template '%s': %w", name, err)
		}
		textBody = tBuf.String()
	}

	return htmlBody, textBody, nil
}

// List returns a list of all registered template names.
func (e *Engine) List() []string {
	e.mu.RLock()
	defer e.mu.RUnlock()

	names := make([]string, 0, len(e.htmlTemplates))
	for name := range e.htmlTemplates {
		names = append(names, name)
	}
	return names
}

// registerDefaults configures standard VibeCore templates.
func (e *Engine) registerDefaults() {
	// 1. Invoice template
	invoiceHTML := `<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Rechnung {{.InvoiceNumber}}</title></head>
<body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
  <div style="max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
    <h2 style="color: #1a365d;">VibeCore ERP - Rechnung {{.InvoiceNumber}}</h2>
    <p>Sehr geehrte(r) {{.CustomerName}},</p>
    <p>anbei erhalten Sie Ihre Rechnung mit der Rechnungsnummer <strong>{{.InvoiceNumber}}</strong>.</p>
    <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
      <tr style="background-color: #f7fafc;">
        <th style="padding: 8px; border: 1px solid #edf2f7; text-align: left;">Fälligkeitsdatum</th>
        <td style="padding: 8px; border: 1px solid #edf2f7;">{{.DueDate}}</td>
      </tr>
      <tr>
        <th style="padding: 8px; border: 1px solid #edf2f7; text-align: left;">Gesamtbetrag</th>
        <td style="padding: 8px; border: 1px solid #edf2f7;"><strong>{{.TotalAmount}} {{.Currency}}</strong></td>
      </tr>
    </table>
    <p>Vielen Dank für Ihr Vertrauen.</p>
    <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
    <small style="color: #718096;">VibeCore ERP System</small>
  </div>
</body>
</html>`

	invoiceText := `VibeCore ERP - Rechnung {{.InvoiceNumber}}
Sehr geehrte(r) {{.CustomerName}},

anbei erhalten Sie Ihre Rechnung mit der Rechnungsnummer {{.InvoiceNumber}}.
Fälligkeitsdatum: {{.DueDate}}
Gesamtbetrag: {{.TotalAmount}} {{.Currency}}

Vielen Dank für Ihr Vertrauen.
VibeCore ERP System`

	_ = e.Register("invoice", invoiceHTML, invoiceText)

	// 2. Notification template
	notifHTML := `<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{{.Title}}</title></head>
<body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
  <div style="max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
    <h2 style="color: #2b6cb0;">{{.Title}}</h2>
    <p>{{.Message}}</p>
    {{if .ActionURL}}
    <div style="margin: 25px 0;">
      <a href="{{.ActionURL}}" style="background-color: #3182ce; color: #ffffff; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: bold;">{{.ActionText}}</a>
    </div>
    {{end}}
    <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
    <small style="color: #718096;">VibeCore Benachrichtigungssystem</small>
  </div>
</body>
</html>`

	notifText := `{{.Title}}

{{.Message}}
{{if .ActionURL}}
{{.ActionText}}: {{.ActionURL}}
{{end}}

VibeCore Benachrichtigungssystem`

	_ = e.Register("notification", notifHTML, notifText)
}
