inventory-api is down in staging and in production since the last change to `deploy/inventory-api/`. Argo CD applies that directory with Kustomize. Here is what I collected.

Staging, right after the sync:
```
$ kubectl -n inventory get pods -l app.kubernetes.io/name=inventory-api
NAME                             READY   STATUS                       RESTARTS   AGE
inventory-api-6b9d7f5c48-4mzqk   0/1     CreateContainerConfigError   0          6m
inventory-api-6b9d7f5c48-9rtwn   0/1     CreateContainerConfigError   0          6m
inventory-api-6b9d7f5c48-xq2lp   0/1     CreateContainerConfigError   0          6m
$ kubectl -n inventory describe pod inventory-api-6b9d7f5c48-4mzqk | tail -1
  Warning  Failed     52s (x26 over 6m)  kubelet  Error: couldn't find key DATABASE_URL in ConfigMap inventory/inventory-api-config
```
I patched that by hand in staging to get further (Argo CD has reverted it since). Then the pods ran but stayed `0/1`:
```
  Warning  Unhealthy  8s (x71 over 6m)  kubelet  Readiness probe failed: Get "http://10.42.3.17:8081/readyz": dial tcp 10.42.3.17:8081: connect: connection refused
$ kubectl -n inventory port-forward pod/inventory-api-6b9d7f5c48-4mzqk 8080 & curl -s localhost:8080/readyz
ok
$ kubectl -n inventory get endpointslices -l kubernetes.io/service-name=inventory-api
NAME                  ADDRESSTYPE   PORTS     ENDPOINTS   AGE
inventory-api-x7k2p   IPv4          <unset>   <unset>     41d
```
Production does not even create the pods:
```
$ kubectl -n inventory get events --field-selector involvedObject.kind=ReplicaSet | tail -1
12s  Warning  FailedCreate  replicaset/inventory-api-6b9d7f5c48  Error creating: pods "inventory-api-6b9d7f5c48-" is forbidden: failed quota: compute: must specify limits.memory for: api
```
Please fix the manifests so that the pods start, become ready and get traffic through the Service and the Ingress in both clusters. Do not change the image, the values in the ConfigMap or `deploy/namespaces/` (the platform team owns the quota).
