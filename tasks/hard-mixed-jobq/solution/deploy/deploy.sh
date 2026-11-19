#!/usr/bin/env bash
# Render the Kubernetes manifests of jobq for one environment and apply them.
#
# Usage: deploy/deploy.sh --env NAME --token-file FILE [--render-only DIR]
#
#   --env NAME          read the values from deploy/env/NAME.env
#   --token-file FILE   the API token. It goes only into the Secret jobq-api-token
#   --render-only DIR   write the rendered manifests to DIR and do not call kubectl
#
# Each template in deploy/templates/*.yaml can contain ${KEY} placeholders.
# KEY must be set in the env file. The env file has KEY=VALUE lines, empty
# lines and comment lines that start with #. The script does not source it.
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
templates_dir=$script_dir/templates

usage() {
    echo "usage: $0 --env NAME --token-file FILE [--render-only DIR]" >&2
    exit 2
}

env_name=""
token_file=""
render_dir=""
while [ $# -gt 0 ]; do
    case $1 in
        --env)
            [ $# -ge 2 ] || usage
            env_name=$2
            shift 2
            ;;
        --token-file)
            [ $# -ge 2 ] || usage
            token_file=$2
            shift 2
            ;;
        --render-only)
            [ $# -ge 2 ] || usage
            render_dir=$2
            shift 2
            ;;
        *) usage ;;
    esac
done
[ -n "$env_name" ] || usage
[ -n "$token_file" ] || usage
if [ ! -r "$token_file" ] || [ ! -f "$token_file" ]; then
    echo "deploy: cannot read the token file $token_file" >&2
    exit 1
fi
if [ -z "$(tr -d '[:space:]' <"$token_file")" ]; then
    echo "deploy: the token file $token_file is empty" >&2
    exit 1
fi

env_file=$script_dir/env/$env_name.env
[ -f "$env_file" ] || { echo "deploy: no env file $env_file" >&2; exit 1; }

declare -A values=()

# load_env FILE: read KEY=VALUE lines into the array "values".
load_env() {
    local line key value n=0
    while IFS= read -r line || [ -n "$line" ]; do
        n=$((n + 1))
        case $line in
            '' | '#'*) continue ;;
        esac
        if [[ ! $line =~ ^([A-Z][A-Z0-9_]*)=(.*)$ ]]; then
            echo "deploy: $1:$n: not a KEY=VALUE line" >&2
            return 1
        fi
        key=${BASH_REMATCH[1]}
        value=${BASH_REMATCH[2]}
        values[$key]=$value
    done <"$1"
}

# render FILE: write FILE to stdout with each ${KEY} replaced by its value.
render() {
    local text key out=""
    text=$(<"$1")
    while [[ $text =~ \$\{([A-Z][A-Z0-9_]*)\} ]]; do
        key=${BASH_REMATCH[1]}
        if [ -z "${values[$key]+set}" ]; then
            echo "deploy: $1: ${key} is not set in $env_file" >&2
            return 1
        fi
        out+=${text%%"${BASH_REMATCH[0]}"*}${values[$key]}
        text=${text#*"${BASH_REMATCH[0]}"}
    done
    printf '%s%s\n' "$out" "$text"
}

load_env "$env_file"

cleanup_dir=""
if [ -z "$render_dir" ]; then
    render_dir=$(mktemp -d)
    cleanup_dir=$render_dir
    trap 'rm -rf "$cleanup_dir"' EXIT
fi
mkdir -p "$render_dir"

for template in "$templates_dir"/*.yaml; do
    render "$template" >"$render_dir/$(basename "$template")"
done
# The Secret is not a template, so that no other manifest can contain the token.
{
    echo "apiVersion: v1"
    echo "kind: Secret"
    echo "metadata:"
    echo "  name: jobq-api-token"
    echo "  namespace: ${values[NAMESPACE]}"
    echo "type: Opaque"
    echo "data:"
    echo "  token: $(base64 -w0 <"$token_file")"
} >"$render_dir/secret.yaml"
echo "deploy: rendered $(find "$render_dir" -name '*.yaml' | wc -l) manifest(s) for $env_name in $render_dir" >&2

if [ -n "$cleanup_dir" ]; then
    kubectl apply --namespace "${values[NAMESPACE]}" -f "$render_dir"
fi
