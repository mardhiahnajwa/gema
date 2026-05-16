.PHONY: up down build logs restart shell-api shell-db clean

## ── Start all services (detached) ───────────────────────────────────────────
up:
	docker compose up -d

## ── Start in foreground (with logs) ─────────────────────────────────────────
dev:
	docker compose up

## ── Stop all services ────────────────────────────────────────────────────────
down:
	docker compose down

## ── Rebuild images ───────────────────────────────────────────────────────────
build:
	docker compose build --no-cache

## ── Tail logs ────────────────────────────────────────────────────────────────
logs:
	docker compose logs -f

logs-api:
	docker compose logs -f api

logs-worker:
	docker compose logs -f worker

## ── Restart a single service ─────────────────────────────────────────────────
restart:
	docker compose restart $(s)

## ── Open shell inside API container ─────────────────────────────────────────
shell-api:
	docker compose exec api bash

## ── Open psql shell ──────────────────────────────────────────────────────────
shell-db:
	docker compose exec db psql -U gema -d gema

## ── Stop & remove volumes (WARNING: deletes all data) ────────────────────────
clean:
	docker compose down -v --remove-orphans

## ── Copy env.example to .env ─────────────────────────────────────────────────
env:
	cp env.example .env
	@echo ".env created — add your API keys"

## ── Quick status check ───────────────────────────────────────────────────────
status:
	docker compose ps
