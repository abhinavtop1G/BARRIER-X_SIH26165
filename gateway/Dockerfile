FROM golang:1.22-alpine AS builder

WORKDIR /app

COPY go.mod ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -buildvcs=false -o gateway ./cmd/server

FROM alpine:3.19

WORKDIR /app
COPY --from=builder /app/gateway /app/gateway

EXPOSE 8080

CMD ["/app/gateway"]

