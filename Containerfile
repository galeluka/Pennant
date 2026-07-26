# Pennant — container image. Works with docker build or podman build.
#
# Two stages. The builder needs the Go toolchain; the result needs nothing at all,
# because the binary is static and the frontend and samples are embedded in it.

FROM golang:1.22-alpine AS build
WORKDIR /src

# No third-party Go dependencies, so there is nothing to download and no module
# cache layer worth keeping. Copy everything and build.
COPY . .

# CGO off makes the binary static, which is what lets the final stage be scratch.
# -trimpath keeps build machine paths out of it; -s -w drop the symbol table.
ENV CGO_ENABLED=0 GOOS=linux
RUN go vet ./... && go build -trimpath -ldflags="-s -w" -o /pennant .

FROM alpine:3.20
RUN apk add --no-cache ca-certificates
COPY --from=build /pennant /pennant

# Runs as a non-root uid. There is no /etc/passwd in scratch, so this is a bare
# numeric id on purpose; the volume must be writable by it.
USER 65532:65532

ENV KE_ADDR=0.0.0.0:8080 \
    KE_DATA=/data

EXPOSE 8080
VOLUME ["/data"]

# If you enable AI assistance against an https endpoint, a scratch image has no
# root certificates and TLS will fail. Either use http to a LiteLLM or Ollama on
# your own network, or swap the final stage for alpine and add ca-certificates:
#
#   FROM alpine:3.20
#   RUN apk add --no-cache ca-certificates
#   COPY --from=build /pennant /pennant
#
ENTRYPOINT ["/pennant"]

