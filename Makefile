.PHONY: help install start start-ml start-all test test-js test-py generate-data train-ml eval-ml clean

help:
	@echo "Chargeback Sentinel - Enterprise Makefile Commands:"
	@echo "  make install        Install Node.js & Python dependencies"
	@echo "  make start          Start the Node.js API server & web dashboard (:3000)"
	@echo "  make start-ml       Start the Python ML microservice (:8000)"
	@echo "  make start-all      Start both ML microservice (:8000) and API server (:3000)"
	@echo "  make test           Run all JavaScript and Python test suites"
	@echo "  make test-js        Run Node.js unit tests"
	@echo "  make test-py        Run Python ML unit tests"
	@echo "  make generate-data  Generate synthetic chargeback dataset"
	@echo "  make train-ml       Train Logistic Regression dispute win scorer"
	@echo "  make eval-ml        Evaluate ML model on held-out test split"
	@echo "  make clean          Clean build artifacts and temporary files"

install:
	npm install
	pip install -r requirements.txt

start:
	npm start

start-ml:
	npm run start:ml

start-all:
	@echo "Starting ML microservice on :8000 and API server on :3000..."
	@trap 'kill 0' INT TERM; npm run start:ml & npm start & wait

test: test-js test-py

test-js:
	npm test

test-py:
	npm run test:python

generate-data:
	npm run data:generate

train-ml:
	npm run ml:train

eval-ml:
	npm run ml:evaluate

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage
