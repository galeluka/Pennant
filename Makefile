# Pennant. No build step for the frontend: it is one HTML file with one inline
# script, so there is nothing to bundle and nothing to install.

BINARY := pennant
IMAGE  := pennant:0.14.0
DATA   := ./data

.PHONY: help up build run test image compose clean fmt vet

help:
	@echo "make up       build and run on 127.0.0.1:8080 with $(DATA)"
	@echo "make build    compile the binary"
	@echo "make test     the JS suites and the model validator"
	@echo "make vet      go vet + gofmt -l"
	@echo "make image    build the container image"
	@echo "make compose  docker compose up --build"
	@echo "make clean    remove the binary (never the data)"

build:
	CGO_ENABLED=0 go build -trimpath -o $(BINARY) .

# Loopback and a local data directory: the two defaults that make this safe to
# run without thinking about it.
up: build
	@mkdir -p $(DATA)
	./$(BINARY) --addr 127.0.0.1:8080 --data $(DATA)

run: up

fmt:
	gofmt -w .

vet:
	gofmt -l .
	go vet ./...

# Everything here runs on node and python3 alone. None of it needs the app to be
# running, and none of it touches the Go code.
test:
	node tools/smoke.js web/index.html web/landing.html
	node tools/test_analyzers.js
	node tools/test_llm_panel.js
	node tools/test_landing.js
	node tools/test_import.js
	node tools/test_templates.js
	node tools/test_plans.js
	python3 tools/model-v2.py --check samples/*.json templates/*.json

image:
	docker build -f Containerfile -t $(IMAGE) .

compose:
	docker compose up --build

clean:
	rm -f $(BINARY)
