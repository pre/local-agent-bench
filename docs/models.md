# Models

| File | Model, quant | Files | Expected GTT | License | Known caveat |
|---|---|---|---|---|---|
| `qwen38-base.toml` | Qwen3.8-Flash-Next, UD-Q4_K_XL, MTP head | 4 parts and a draft file | 88017 MiB GTT used with the desktop (measured) | Qwen Community License | Needs the patched chat template and `-lzm on` |
| `gpt-oss-120b.toml` | gpt-oss-120b, F16 of unsloth (MXFP4 experts) | 1 file, 65.4 GB | about 68 GiB (estimate) | Apache 2.0 | The embedded template drops each system message after the first message, thus also the environment block of Claude Code |
| `gpt-oss-120b-sysmsg.toml` | The same as `gpt-oss-120b.toml` | 1 file, 65.4 GB | about 68 GiB (estimate) | Apache 2.0 | Only the chat template is different: `templates/gpt-oss-120b.jinja` writes a system message after the first message at its position as a harmony developer message. Without such a message the prompt is the same as with the embedded template. A unit test compares the template with the embedded template (`tests/gpt-oss-120b-embedded-template.jinja`) |
| `qwen3-coder-next.toml` | Qwen3-Coder-Next 80B-A3B, UD-Q8_K_XL | 3 parts, 86.3 GB | about 85 to 87 GiB (estimate) | Apache 2.0, card metadata only (the LICENSE link gives HTTP 404) | No thinking mode |
| `qwen38-27b.toml` | Qwen3.8-27B dense, Q8_0, MTP layer inside (not verified) | 1 file, 29.0 GB | about 37 GiB (estimate) | Apache 2.0 | Needs the patched chat template of Flash-Next. MTP with no draft file. Check at the first start that the file has the MTP layer |
| `glm-53-flash.toml` | GLM-5.3 Flash 320.8B-A18B, UD-IQ2_XXS, no MTP | 4 parts, 101.8 GB | about 93 to 95 GiB (estimate) | MIT | At the memory limit: starts only when GTT used is 6000 MiB or less. Published top-1 agreement 76 %. Reports of reasoning that collapses in long sessions |

The new configurations use `-lm none` (resident load, recommended on Strix Halo), port 8090, context 131072 and the image of `qwen38-base.toml`. The comments of each file give the source of each value. A unit test checks that each flag of each configuration is in the help text of llama-server build 12531 (`tests/llama-server-help-build12531.txt`). When the help text names the values of a flag (for example `-fa`, `-lm`, `-ctk`, `--reasoning-effort`, `--spec-type`), the value must be one of them. A flag with the placeholder `N` also accepts a number. The test also checks that the `model_file` of each new configuration is a file of `download/models.tsv`.

## Download

```sh
just download-model gpt-oss-120b qwen3-coder-next   # detached container "model-download"
podman logs -f model-download                       # progress, "VERIFIED <model>" or "FAILED <model>"
just verify-model gpt-oss-120b                      # SHA-256 check on the host, downloads nothing
```

`download/models.tsv` has one line for each file: model (the directory below `~/models`), repository, revision, date of the revision, path, size and SHA-256 (from the tree API of Hugging Face). The URL has the pinned revision, not `main`.

`download/download.sh` runs in an Alpine container (pinned by digest) with the CA bundle of the host. It does the models one after the other. For each model it writes `expected-sha256.tsv` and `source.txt` in the model directory and downloads the missing files with aria2 (16 connections for each file, `.part` files, a second run continues them). `RATE` (default `28M`, aria2 unit MiB/s) is the limit for all connections together. When the TLS proxy breaks connections, aria2 stops. The script then starts it again, at most `ATTEMPTS` times (default 5), `RETRY_WAIT` seconds apart (default 60). The status lines (start, downloaded, VERIFIED, FAILED) also go to `download.log` in the model directory, because `podman logs` can lose lines of a long log.

When a `.part` file is complete, the script checks it with SHA-256 at low CPU and I/O priority. Only a file that matches gets its final name. The harness and the server use only the final name, so they cannot load a file that is not verified. A file that does not match becomes `<file>.bad` and is downloaded again once. The next download of that file removes `<file>.bad`. At the end the script checks all files of the model with their final names and prints `VERIFIED <model>` or `FAILED <model>`.

`just verify-model <model>...` (`download.sh --verify <model>...` with `TSV` and `MODELS` set to the paths on the host) checks the files with their final names against `download/models.tsv`. It downloads nothing. The exit code is 1 when a file is missing (also a file that is only a `.part` file) or when its SHA-256 does not match. Use it before a run with a model that a download changed.

`just download-model` stops with a message when the container `model-download` runs, so a second command cannot stop a running download. A stopped container of that name is replaced.
