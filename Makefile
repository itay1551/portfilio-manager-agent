.PHONY: deploy-local deploy-cluster

deploy-local:
	podman compose -f deploy/local/compose.yml up -d --build

deploy-cluster:
	oc apply -f deploy/helm/
