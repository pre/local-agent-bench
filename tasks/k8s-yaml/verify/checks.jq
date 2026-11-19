# Assertions on the inventory-api manifests. Input: a JSON array of all
# objects from the resources of deploy/inventory-api/kustomization.yaml.
# The helpers take the input array as their input; arguments are bound to
# variables before the input changes.

def obj($kind; $name): [.[] | select(.kind == $kind and .metadata.name == $name)] | first;
def deployment: obj("Deployment"; "inventory-api");
def service: obj("Service"; "inventory-api");
def configmap: obj("ConfigMap"; "inventory-api-config");
def pdb: obj("PodDisruptionBudget"; "inventory-api");
def ingress: obj("Ingress"; "inventory-api");
def pod: deployment.spec.template;
def api: [pod.spec.containers[]? | select(.name == "api")] | first;
def migrate: [pod.spec.initContainers[]? | select(.name == "migrate")] | first;

# Kubernetes quantity to bytes.
def bytes:
  tostring
  | capture("^(?<n>[0-9]+(\\.[0-9]+)?)(?<u>[A-Za-z]*)$") as $m
  | ({"": 1, "k": 1000, "M": 1000000, "G": 1000000000, "T": 1000000000000,
      "Ki": 1024, "Mi": 1048576, "Gi": 1073741824, "Ti": 1099511627776}[$m.u]) as $f
  | if $f == null then error("unknown unit " + $m.u) else ($m.n | tonumber) * $f end;

# The input map is a non-empty subset of the map $labels.
def selects($labels):
  (type == "object") and (length > 0) and (to_entries | all(.value == $labels[.key]));

# Container port number of a port given as a number or a port name.
def port_number($container; $port):
  if ($port | type) == "number" then $port
  else ([$container.ports[]? | select(.name == $port) | .containerPort] | first)
  end;

def probe_port($probe): $probe.httpGet.port // $probe.tcpSocket.port // $probe.grpc.port;

# Value of an environment variable that comes from the ConfigMap $data.
def env_value($container; $data; $name):
  ([$container.env[]? | select(.name == $name)] | first) as $e
  | if $e.valueFrom.configMapKeyRef.name == "inventory-api-config"
       and $e.valueFrom.configMapKeyRef.optional != true
    then $data[$e.valueFrom.configMapKeyRef.key]
    else null
    end;

def expected_env: {
  "INVENTORY_DB_URL": "postgres://inventory_api@inventory-db-rw.inventory.svc:5432/inventory?sslmode=verify-full",
  "INVENTORY_LISTEN_ADDR": ":8080",
  "INVENTORY_METRICS_ADDR": ":9090",
  "INVENTORY_LOG_LEVEL": "info",
  "INVENTORY_CACHE_TTL": "30s",
  "INVENTORY_SYNC_INTERVAL": "5m"
};

def count($kind; $name): [.[] | select(.kind == $kind and .metadata.name == $name)] | length;

def check_objects_found:
  count("Deployment"; "inventory-api") == 1
  and count("Service"; "inventory-api") == 1
  and count("ConfigMap"; "inventory-api-config") == 1
  and count("PodDisruptionBudget"; "inventory-api") == 1
  and count("Ingress"; "inventory-api") == 1
  and api != null
  and migrate != null;

def check_service_selects_pods:
  pod.metadata.labels as $labels
  | (service.spec.selector | selects($labels))
  and (service.spec.selector | has("app.kubernetes.io/name"))
  and (deployment.spec.selector.matchLabels | selects($labels));

def check_pdb_selects_pods:
  pod.metadata.labels as $labels
  | pdb.spec.selector.matchLabels | selects($labels);

def check_readiness_probe:
  api as $c
  | $c.readinessProbe != null
  and port_number($c; probe_port($c.readinessProbe)) == 8080
  and port_number($c; probe_port($c.livenessProbe)) == 8080;

def check_memory_limit:
  api as $c
  | (deployment.spec.replicas // 1) as $replicas
  | ($c.resources.limits.memory | bytes) as $limit
  | ($c.resources.requests.memory | bytes) as $request
  | $limit >= $request
  and ($limit * $replicas) <= ("8Gi" | bytes)
  and $c.resources.limits.cpu != null
  and $c.resources.requests.cpu != null;

def check_configmap_refs:
  (configmap.data // {}) as $data
  | api as $api
  | migrate as $migrate
  | ([pod.spec.initContainers[]?, pod.spec.containers[]?
      | .env[]?.valueFrom.configMapKeyRef | select(. != null)]
     | all(.name == "inventory-api-config" and $data[.key] != null))
  and (expected_env | to_entries | all(env_value($api; $data; .key) == .value))
  and env_value($migrate; $data; "INVENTORY_DB_URL") == expected_env.INVENTORY_DB_URL;

def check_service_routes_to_pods:
  api as $c
  | service as $svc
  | ([ingress.spec.rules[]?.http.paths[]?.backend.service] | first) as $backend
  | ([$svc.spec.ports[]? | select(
        ($backend.port.name != null and .name == $backend.port.name)
        or ($backend.port.number != null and .port == $backend.port.number))] | first) as $port
  | $backend.name == "inventory-api"
  and $port != null
  and port_number($c; $port.targetPort // $port.port) == 8080;

def check_image_unchanged:
  [pod.spec.initContainers[]?, pod.spec.containers[]? | .image]
  | length > 0 and all(. == "registry.example.internal/platform/inventory-api:2.14.3");
