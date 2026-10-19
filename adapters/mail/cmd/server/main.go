package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/api"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/config"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/imap"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/queue"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/smtp"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/status"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/template"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/webhooks"
)

func main() {
	cfg := config.LoadFromEnv()

	// Initialize structured JSON logging
	var logLevel slog.Level
	switch strings.ToLower(cfg.LogLevel) {
	case "debug":
		logLevel = slog.LevelDebug
	case "warn":
		logLevel = slog.LevelWarn
	case "error":
		logLevel = slog.LevelError
	default:
		logLevel = slog.LevelInfo
	}

	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: logLevel,
	}))
	slog.SetDefault(logger)

	logger.Info("starting VibeCore Mail Microservice",
		"environment", cfg.Environment,
		"host", cfg.Host,
		"port", cfg.Port,
		"queue_db", cfg.QueueDBPath,
		"smtp_host", cfg.SMTPHost,
		"imap_enabled", cfg.IMAPEnabled,
	)

	// 1. Initialize persistent queue database
	q, err := queue.NewBoltQueue(cfg.QueueDBPath)
	if err != nil {
		logger.Error("failed initializing persistent bbolt queue", "error", err)
		os.Exit(1)
	}
	defer q.Close()

	// 2. Initialize template engine
	tmplEngine := template.NewEngine()

	// 3. Initialize status tracker & event dispatcher
	tracker := status.NewTracker(cfg, q, logger)

	// 4. Initialize SMTP sender
	smtpSender, err := smtp.NewSMTPSender(cfg)
	if err != nil {
		logger.Error("failed initializing SMTP sender", "error", err)
		os.Exit(1)
	}

	// 5. Initialize & start queue processor
	proc := queue.NewProcessor(cfg, q, smtpSender, tmplEngine, tracker, logger)
	if err := proc.Start(); err != nil {
		logger.Error("failed starting queue processor", "error", err)
		os.Exit(1)
	}
	defer proc.Stop()

	// 6. Initialize & start IMAP receiver
	imapReceiver := imap.NewReceiver(cfg, tracker, logger)
	if err := imapReceiver.Start(); err != nil {
		logger.Error("failed starting IMAP receiver", "error", err)
	}
	defer imapReceiver.Stop()

	// 7. Initialize webhooks handler & HTTP API router
	whHandler := webhooks.NewHandler(cfg, q, tracker, logger)
	apiService := api.NewAPI(cfg, q, proc, tracker, tmplEngine, logger)
	router := api.NewRouter(cfg, apiService, whHandler, logger)

	// 8. Start HTTP Server
	serverAddr := fmt.Sprintf("%s:%d", cfg.Host, cfg.Port)
	server := &http.Server{
		Addr:              serverAddr,
		Handler:           router,
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       15 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}

	// Graceful shutdown handling
	stopChan := make(chan os.Signal, 1)
	signal.Notify(stopChan, os.Interrupt, syscall.SIGTERM)

	go func() {
		logger.Info("HTTP server listening", "address", serverAddr)
		if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			logger.Error("HTTP server failed", "error", err)
			os.Exit(1)
		}
	}()

	<-stopChan
	logger.Info("shutting down VibeCore Mail Microservice gracefully...")

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()

	if err := server.Shutdown(shutdownCtx); err != nil {
		logger.Error("server shutdown forced", "error", err)
	}

	logger.Info("VibeCore Mail Microservice stopped cleanly")
}
