#!/usr/bin/env bash
# Hidden check of the k8s-yaml task: assertions on the manifests that
# deploy/inventory-api/kustomization.yaml lists. Any valid correction passes,
# for example a changed Service selector or changed pod labels.
# The test functions run through "check" from lib.sh.
# shellcheck disable=SC2329
set -u
VERIFY_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib.sh
. "$VERIFY_DIR/lib.sh"

cd /work || exit 1
APP_DIR=deploy/inventory-api
ALL=/tmp/k8s-yaml-all.json
rm -f "$ALL"

load_manifests() {
    local files=() resource
    [ -f "$APP_DIR/kustomization.yaml" ] || { echo "missing $APP_DIR/kustomization.yaml"; return 1; }
    while IFS= read -r resource; do
        [ -f "$APP_DIR/$resource" ] || { echo "missing resource file $APP_DIR/$resource"; return 1; }
        files+=("$APP_DIR/$resource")
    done < <(yq '.resources[]' "$APP_DIR/kustomization.yaml")
    [ "${#files[@]}" -gt 0 ] || { echo "no resources in kustomization.yaml"; return 1; }
    yq ea -o=json -I=0 '[.] | map(select(. != null))' "${files[@]}" >"$ALL" || return 1
    jq -e -L "$VERIFY_DIR" 'include "checks"; check_objects_found' "$ALL"
}

assert() {
    [ -s "$ALL" ] || { echo "manifests not loaded"; return 1; }
    jq -e -L "$VERIFY_DIR" "include \"checks\"; $1" "$ALL"
}

namespaces_unchanged() {
    local git=(git -c safe.directory='*')
    "${git[@]}" diff --exit-code "$EVAL_BASELINE" -- deploy/namespaces &&
        [ -z "$("${git[@]}" status --porcelain -- deploy/namespaces)" ]
}

check manifests_load load_manifests
check service_selects_pods assert check_service_selects_pods
check pdb_selects_pods assert check_pdb_selects_pods
check readiness_probe_port assert check_readiness_probe
check memory_limit assert check_memory_limit
check configmap_refs assert check_configmap_refs
check ingress_reaches_pods assert check_service_routes_to_pods
check image_unchanged assert check_image_unchanged
check namespaces_unchanged namespaces_unchanged

write_result
exit 0
