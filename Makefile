.PHONY: deploy-local deploy-cluster test-unit test-integration test-integration-llm

deploy-local:
	podman compose --env-file .env -f deploy/local/compose.yml up --build

deploy-cluster:
	helm upgrade --install investment-advisor-agent deploy/helm -n investment-advisor-agent --create-namespace

test-unit:
	pytest tests/unit -m unit -v

test-integration:
	pytest tests/integration -m "integration and not llm" -v

test-integration-llm:
	pytest tests/integration -m integration -v
