.PHONY: help install install-etl install-training install-all dev clean shell

# Default target
help:
	@echo "UN Draft - Dependency Management"
	@echo ""
	@echo "Installation targets:"
	@echo "  make install          - Core dependencies (app, rag, db, gym)"
	@echo "  make install-etl      - Core + ETL (adds PDF parsing)"
	@echo "  make install-training - Core + Training (adds PyTorch)"
	@echo "  make install-all      - Everything (core + ETL + training)"
	@echo "  make dev              - Full dev setup (all + dev tools)"
	@echo ""
	@echo "ETL commands:"
	@echo "  make etl-fetch        - Fetch metadata for session 78"
	@echo "  make etl-parse        - Parse metadata XML"
	@echo "  make etl-download     - Download PDFs"
	@echo ""
	@echo "Gym commands:"
	@echo "  make gym-play         - Play gym interactively"
	@echo ""
	@echo "Training commands:"
	@echo "  make train-world      - Train world model"
	@echo "  make train-irl        - Train IRL model"
	@echo ""
	@echo "App commands:"
	@echo "  make app              - Run FastAPI app locally (hot reload)"
	@echo "  make docker-up        - Start Docker services (production UI)"
	@echo "  make docker-reload    - Start Docker UI with hot reload (production DB)"
	@echo "  make docker-reload-dev-db - Start Docker UI with hot reload (dev DB)"
	@echo "  make docker-down      - Stop Docker services"
	@echo "  make shell            - Launch interactive shell in the UI container"
	@echo ""
	@echo "Database commands:"
	@echo "  make db-setup         - Setup production database"
	@echo "  make db-setup-dev     - Setup dev database"
	@echo "  make db-shell         - Open psql shell (production)"
	@echo "  make db-shell-dev     - Open psql shell (dev)"
	@echo "  make db-query SQL='...' - Run SQL query (production)"
	@echo "  make db-query-dev SQL='...' - Run SQL query (dev)"
	@echo ""
	@echo "Logging commands:"
	@echo "  make logs-tail        - Tail multistep tool logs (debugging)"
	@echo "  make logs-app         - Tail app logs"
	@echo "  make logs-all         - Tail all logs"
	@echo ""
	@echo "Other:"
	@echo "  make clean            - Remove .venv and __pycache__"

# Installation targets
install:
	@echo "Installing core dependencies..."
	uv sync

install-etl: install
	@echo "Installing ETL dependencies (PDF parsing)..."
	uv sync --group etl

install-training: install
	@echo "Installing training dependencies (PyTorch)..."
	uv sync --group training

install-all: install
	@echo "Installing all optional dependencies..."
	uv sync --group etl --group training

dev: install-all
	@echo "Installing development tools..."
	uv sync --group dev

# ETL commands
etl-fetch:
	uv run -m etl.fetch_download.fetch_metadata 78

etl-parse:
	@echo "Usage: make etl-parse FILE=data/raw/xml/session_78_resolutions.xml"
	@if [ -z "$(FILE)" ]; then \
		echo "Error: FILE not specified"; \
		exit 1; \
	fi
	uv run -m etl.parsing.parse_metadata $(FILE)

etl-download:
	@echo "Usage: make etl-download FILE=data/parsed/metadata/session_78_resolutions.json"
	@if [ -z "$(FILE)" ]; then \
		echo "Error: FILE not specified"; \
		exit 1; \
	fi
	uv run -m etl.fetch_download.download_pdfs $(FILE)

# Gym commands
gym-play:
	uv run python -m un_gym.cli.play --country France

# Training commands
train-world:
	uv run python training/train_world_model.py

train-irl:
	uv run python training/train_irl.py

# App commands
app:
	uv run uvicorn ui.app:app --reload

docker-up:
	docker-compose up -d ui

docker-reload:
	docker-compose up ui_reload

docker-reload-dev-db:
	docker-compose up ui_reload_dev_db

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f ui

docker-logs-reload:
	docker-compose logs -f ui_reload

shell:
	docker-compose run --rm --service-ports --entrypoint /bin/bash ui_reload

# Logging commands
logs-tail:
	@echo "📊 Tailing multistep tool logs..."
	@./scripts/tail_multistep_logs.sh

logs-app:
	@echo "📊 Tailing app logs..."
	@tail -f logs/app.log

logs-all:
	@echo "📊 Tailing all logs..."
	@tail -f logs/app.log logs/multistep_tools.log

# Database commands
db-setup:
	uv run -m db.setup_db

db-setup-dev:
	uv run -m db.setup_db --dev

db-shell:
	@echo "🐘 Opening PostgreSQL shell (production database)..."
	docker-compose exec postgres psql -U un_user -d un_documents

db-shell-dev:
	@echo "🐘 Opening PostgreSQL shell (dev database)..."
	docker-compose exec postgres_dev psql -U un_user -d un_documents_dev

db-query:
	@echo "Usage: make db-query SQL='SELECT * FROM resolutions LIMIT 5;'"
	@if [ -z "$(SQL)" ]; then \
		echo "Error: SQL not specified"; \
		exit 1; \
	fi
	@docker-compose exec postgres psql -U un_user -d un_documents -P pager=off -c "$(SQL)"

db-query-dev:
	@echo "Usage: make db-query-dev SQL='SELECT * FROM resolutions LIMIT 5;'"
	@if [ -z "$(SQL)" ]; then \
		echo "Error: SQL not specified"; \
		exit 1; \
	fi
	@docker-compose exec postgres_dev psql -U un_user -d un_documents_dev -P pager=off -c "$(SQL)"
# Cleanup
clean:
	@echo "Cleaning up..."
	rm -rf .venv
	find . -type d -name __pycache__ -exec rm -r {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -r {} + 2>/dev/null || true
