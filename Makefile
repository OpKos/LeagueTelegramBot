SHELL := /bin/bash

SRC_DIRS := src app scripts tests
PANTHEON_PROTO_ROOT := src/league_telegram_bot/integrations/pantheon
PANTHEON_PROTO_DIR := $(PANTHEON_PROTO_ROOT)/proto
PANTHEON_GEN_ROOT := src/league_telegram_bot/integrations/pantheon
PANTHEON_TWIRPY_PLUGIN := tools/protoc-gen-twirpy
PANTHEON_PROTOS := $(PANTHEON_PROTO_DIR)/atoms.proto $(PANTHEON_PROTO_DIR)/mimir.proto
PANTHEON_TWIRPY_URL := https://github.com/Cryptact/twirpy/releases/latest/download/protoc-gen-twirpy-linux-amd64.tar.gz
PANTHEON_TWIRPY_SHA256 := 69cc63748101f091c832b78fa72564edc0f7782e5b919db4014d6ac43cd812fd

.PHONY: lint format typecheck pre-commit run pantheon-gen pantheon-plugin contribute

lint:
	ruff check $(SRC_DIRS)

format:
	ruff format $(SRC_DIRS)

typecheck:
	mypy

pre-commit:
	pre-commit run -a

run:
	python scripts/run_bot.py

pantheon-plugin: $(PANTHEON_TWIRPY_PLUGIN)

$(PANTHEON_TWIRPY_PLUGIN):
	@mkdir -p $(dir $(PANTHEON_TWIRPY_PLUGIN))
	@curl -L -o /tmp/protoc-gen-twirpy.tar.gz $(PANTHEON_TWIRPY_URL)
	@echo "$(PANTHEON_TWIRPY_SHA256)  /tmp/protoc-gen-twirpy.tar.gz" | sha256sum -c -
	@tar -xzf /tmp/protoc-gen-twirpy.tar.gz -C $(dir $(PANTHEON_TWIRPY_PLUGIN))

pantheon-gen: $(PANTHEON_TWIRPY_PLUGIN)
	@mkdir -p $(PANTHEON_GEN_ROOT)/proto
	@touch $(PANTHEON_GEN_ROOT)/proto/__init__.py
	python -m grpc_tools.protoc \
		-I $(PANTHEON_PROTO_ROOT) \
		--python_out=$(PANTHEON_GEN_ROOT) \
		--twirpy_out=$(PANTHEON_GEN_ROOT) \
		--plugin=protoc-gen-twirpy=$(PANTHEON_TWIRPY_PLUGIN) \
		$(PANTHEON_PROTOS)
	@rg -l "^from proto import" $(PANTHEON_GEN_ROOT)/proto | xargs -r sed -i "s/^from proto import/from . import/"

contribute: pantheon-plugin
	python -m pip install -r requirements.txt -r requirements-dev.txt
	pre-commit install
	pre-commit install --hook-type commit-msg
