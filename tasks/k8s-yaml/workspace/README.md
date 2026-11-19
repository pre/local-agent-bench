# inventory-deploy

Kubernetes manifests of the node inventory service.

| Directory | Content |
|---|---|
| `deploy/namespaces/` | Namespace and quota. Owned by the platform team |
| `deploy/inventory-api/` | The API: Deployment, Service, Ingress, ConfigMap, PDB |

Argo CD applies `deploy/inventory-api/` with Kustomize to the staging and
production clusters. The database (`inventory-db`, CloudNativePG) and its
secret `inventory-db-app` come from a separate repository.
