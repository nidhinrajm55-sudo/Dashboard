.PHONY: install test up down

install:
	python3 -m pip install -r requirements.txt

test:
	pytest -q

up:
	docker compose up --build

down:
	docker compose down
