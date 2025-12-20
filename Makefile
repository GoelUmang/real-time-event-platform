.PHONY: up down logs test bench seed reset

up:
	cd docker && docker compose up -d --build --scale worker=4

down:
	cd docker && docker compose down -v

logs:
	cd docker && docker compose logs -f

test:
	pytest -v --cov=app --cov-report=term-missing

bench:
	bash scripts/run_benchmark.sh

seed:
	python scripts/seed_data.py

reset:
	bash scripts/reset_env.sh
