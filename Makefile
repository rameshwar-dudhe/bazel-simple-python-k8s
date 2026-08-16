# Convenience wrappers. Everything here just calls bazel or a script in
# scripts/ - there is no build logic hiding in this file.
.PHONY: help build test lint image run-api run-worker release-dry release deploy smoke graph teardown clean

TAG ?= 1.4.0
NS  ?= pyplatform

help: ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

build: ## build every target
	bazel build //...

test: ## run every hermetic test
	bazel test //...

lint: ## fast pre-flight checks (same as the CI lint job)
	scripts/lint.sh

image: ## build both OCI images and load them into docker
	bazel run //services/api:image_tarball
	bazel run //services/worker:image_tarball

run-api: ## run the API locally (no container)
	bazel run //services/api

run-worker: ## run one worker batch locally
	bazel run //services/worker -- --batch 3

release-dry: ## show what a nightly release would publish
	bazel run //tools/release -- --mode nightly --dry-run

release: ## build + push the versions in release/manifest.yaml
	scripts/release.sh release

deploy: ## helm install/upgrade into the cluster (TAG=..., NS=...)
	scripts/deploy.sh $(TAG) $(NS)

smoke: ## post-deploy validation against the cluster
	scripts/smoke.sh $(TAG) $(NS)

graph: ## what rebuilds when the version file changes?
	bazel query 'rdeps(//..., //release:version.txt)' --output=label

teardown: ## remove the helm release, namespace, images and build outputs
	scripts/teardown.sh

clean:
	bazel clean
