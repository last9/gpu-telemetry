# Copyright (c) Meta Platforms, Inc. and affiliates.
# Copyright (c) Last9, Inc.
SHELL:=/bin/bash -o pipefail -o errexit -o nounset

L9GPU_SRCS:=$(shell find l9gpu/ -type f -name '*.py')
VERSION:=$(shell cat l9gpu/version.txt)

.PHONY: all
all: lint test

.PHONY: lint
lint:
	nox -s lint

.PHONY: test
test:
	nox -s tests

.PHONY: typecheck
typecheck:
	nox -s typecheck

.PHONY: format
format:
	nox -s format

.PHONY: build
build:
	python -m build

.PHONY: clean
clean:
	rm -rf build/ dist/ *.egg-info
