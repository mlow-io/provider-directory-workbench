.PHONY: demo test validate validate-public clean review-api remediation-api review-web review-test
export PYTHONPATH := src
export PDTL_ROOT ?= $(CURDIR)/.runtime/demo

demo:
	python3 -m provider_directory_truth_layer.cli run --as-of 2026-06-26 --payer-listings data/raw/synthetic_payer_directory_listings.csv

fetch-demo:
	python3 -m provider_directory_truth_layer.cli fetch-npi --city Nashville --state TN --limit 25 --as-of 2026-06-26

test:
	python3 -m pytest

validate: test
	python3 scripts/run_validation.py

validate-public:
	python3 scripts/run_validation.py --public

clean:
	@echo 'Storage is retained. Remove an explicitly selected disposable .runtime directory manually.'

review-api:
	python3 -m provider_directory_truth_layer.review_api

remediation-api:
	python3 -m provider_directory_truth_layer.remediation_api

review-web:
	cd web && npm run dev

review-test:
	python3 -m pytest tests/test_review_api.py
	cd web && npm test && npm run test:e2e

workbench:
	python3 scripts/demo.py
