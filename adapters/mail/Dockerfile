# Stage 1: Build static Go binary
FROM golang:1.26-alpine AS builder

WORKDIR /src

# Cache dependencies
COPY go.mod go.sum ./
RUN go mod download

# Copy source code and build statically
COPY . .
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build \
    -trimpath \
    -ldflags="-s -w -extldflags '-static'" \
    -o /bin/mail-server ./cmd/server

# Stage 2: Minimal runtime image
FROM alpine:3.21

# Install CA certificates and tzdata for secure TLS & timestamps
RUN apk --no-cache add ca-certificates tzdata

# Create non-root user
RUN addgroup -S vibecore && adduser -S vibecore -G vibecore

WORKDIR /app
COPY --from=builder /bin/mail-server /app/mail-server

# Create data directory for bbolt queue
RUN mkdir -p /data && chown -R vibecore:vibecore /data /app

USER vibecore

ENV PORT=8025 \
    HOST=0.0.0.0 \
    QUEUE_DB_PATH=/data/mail_queue.db

EXPOSE 8025

HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q -O - http://127.0.0.1:8025/health | grep healthy || exit 1

ENTRYPOINT ["/app/mail-server"]
