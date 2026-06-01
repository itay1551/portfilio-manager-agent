.PHONY: deploy-local deploy-cluster

deploy-local:
	podman compose -f deploy/local/compose.yml up -d --build

deploy-cluster:
	helm upgrade --install neurosymbolic-ai deploy/helm -n neurosymbolic-ai --create-namespace
