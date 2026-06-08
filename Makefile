-include .env

.PHONY: deploy-local deploy-cluster test-unit test-integration test-integration-llm test-cluster test-cluster-llm

deploy-local:
	podman compose --env-file .env -f deploy/local/compose.yml up --build

deploy-cluster:
ifndef NAMESPACE
	$(error NAMESPACE is required. Usage: make deploy-cluster NAMESPACE=<oc-project>)
endif
	helm upgrade --install investment-advisor-agent deploy/helm \
		-n $(NAMESPACE) --create-namespace \
		--set namespace=$(NAMESPACE) \
		$(if $(OPENAI_API_ENDPOINT),--set-string "ui.llm.endpoint=$(OPENAI_API_ENDPOINT)") \
		$(if $(OPENAI_API_TOKEN),--set-string "ui.llm.apiToken=$(OPENAI_API_TOKEN)") \
		$(if $(OPENAI_MODEL),--set-string "ui.llm.model=$(OPENAI_MODEL)") \
		$(if $(VITE_ORCHESTRATOR_URL),--set-string "ui.orchestratorUrl=$(VITE_ORCHESTRATOR_URL)")

test-unit:
	pytest tests/unit -m unit -v

test-integration:
	pytest tests/integration -m "integration and not llm and not cluster_only" -v

test-integration-llm:
	pytest tests/integration -m "integration and not cluster_only" -v

test-cluster:
ifndef NAMESPACE
	$(error NAMESPACE is required. Usage: make test-cluster NAMESPACE=<oc-project>)
endif
	UI_BASE=http://$(shell oc get route ui -n $(NAMESPACE) -o jsonpath='{.spec.host}') \
	ORCH_BASE=http://$(shell oc get route orchestrator -n $(NAMESPACE) -o jsonpath='{.spec.host}') \
	pytest tests/integration -m "integration and not llm and not local_only" -v

test-cluster-llm:
ifndef NAMESPACE
	$(error NAMESPACE is required. Usage: make test-cluster-llm NAMESPACE=<oc-project>)
endif
	UI_BASE=http://$(shell oc get route ui -n $(NAMESPACE) -o jsonpath='{.spec.host}') \
	ORCH_BASE=http://$(shell oc get route orchestrator -n $(NAMESPACE) -o jsonpath='{.spec.host}') \
	pytest tests/integration -m "integration and not local_only" -v
