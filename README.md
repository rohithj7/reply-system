# Doctours reply system

A modular reply system for the [assignment packet](docs/assignment/pre-deposit-respond-packet.md). It reads a JSON array of `{id, text}` messages and returns one `Reply` per message, in the same order.

I split the original prompt into policies that load as needed, separated tool decisions from reply writing, and added an explicit human handoff. The hosted version uses a fine-tuned controller and an untuned writer on the same RunPod GPU. Reviewers need one endpoint key and no local GPU or cloud model account.

## Quickstart

You need Python 3.12, [uv](https://docs.astral.sh/uv/) 0.10 or later, repository access, and the endpoint key supplied separately.

```sh
git clone https://github.com/rohithj7/doctours-take-home.git
cd doctours-take-home
uv sync --locked
cp .env.example .env
```

Set `MODEL_API_KEY` in `.env`, then load it and run the packet's five messages:

```sh
set -a; source ./.env; set +a
uv run doctours-reply run --system modular \
  --input eval/official/human_messages.json --output replies.json
```

`.env.example` includes these settings. `.env` is git-ignored.

| Variable | Value |
|---|---|
| `MODEL_BASE_URL` | `https://31ixwh7mttywgt-8001.proxy.runpod.net/v1` |
| `MODEL_API_KEY` | The supplied key; never commit it |
| `MODEL_ID` | `Qwen/Qwen3.8-27B`, the writer's default |
| `CONTROLLER_MODEL_ID` | `f100-e2`, the controller |

To check authentication and the advertised model IDs:

```sh
curl -sS -H "Authorization: Bearer $MODEL_API_KEY" "$MODEL_BASE_URL/models"
```

A missing or incorrect key returns 401.

### Your own messages

Save an array like this as `messages.json`:

```json
[
  {"id": "price", "text": "What does Dr. Hakan Clinic cost?"},
  {"id": "handoff", "text": "I'd like to speak to a person."}
]
```

```sh
uv run doctours-reply run --system modular --input messages.json --output replies.json
```

The output follows the packet's [Reply schema](docs/assignment/pre-deposit-respond-packet.md#output). Each item uses the same packet history and fixture independently; changes made for one message do not carry into the next.

- `--input -` and `--output -` use stdin and stdout.
- `--concurrency N` preserves output order. Use 8 or fewer with the hosted endpoint.
- Traces go to `runs/<run id>/traces.jsonl`, or `--trace-dir`. They stay out of the reply output, and card numbers are redacted.
- Output is written atomically. Exit codes are 0 for success, 2 for invalid input, 3 for model configuration errors, and 4 for model failures. A failed batch writes no output.

**Keep `--system modular` in the command.** The CLI defaults to the original baseline, which needs tool-calling support and cannot use this hosted gateway.

### Interactive trial

```sh
uv run doctours-reply try --system modular
# Or pass a message directly:
uv run doctours-reply try --system modular "Do you offer financing?"
```

The interactive command runs the same pipeline as `run`. It prints the reply, any escalation reason, total elapsed time, model and tool timings, token counts, finish reasons, and the trace location. Enter messages until Ctrl-D. Each message starts from the packet fixture; this is an interactive trial, not a persistent conversation. A failed message prints its error and trace, then the prompt continues.

## Design

The original system, S0, sends roughly 39,000 prompt tokens per call and combines tool use, reply writing and escalation. I kept it as a baseline and built S1 around smaller steps that can be inspected separately.

1. **Route and load policies.** The controller identifies the intents, decides what can handle them, and selects the relevant skills. A request for a person or an unsupported action can escalate immediately.
2. **Plan and execute tools.** The controller can use only tools allowed by the loaded policies. The executor checks arguments and ID provenance, guards writes, and limits a turn to 8 tool calls across 3 rounds. The first decision reviews the route's escalation decision; the controller can also load more skills once.
3. **Write.** The writer drafts a reply and memory update from the context, loaded policies and tool results. It has no tools.
4. **Validate and commit.** Validators check prices, facts and links against the turn's evidence. A failing draft gets one repair; a second failure escalates as `unverified_reply`. Working memory is committed only after the draft passes validation.

### What stays loaded

Every controller step receives the core identity, boundaries and escalation rules, the matching stage/promo context, and a catalog of skill summaries and activation cues. The 12 topic skills, including pricing, payment links and financing, load only when selected. The writer also receives the output and memory rules.

A route call is about 4,800 prompt tokens. Policies are versioned Markdown with TOML front matter; overlays in `resources/policy_sets/` let a policy change without changing code. Traces record the loaded modules, versions and hashes.

### Human handoff

Requests to charge a card, move money already paid, contact a clinic to hold a date, or perform another unsupported action go to a person. Explicit requests for a human do too.

An escalation returns `escalate: true`, a reason, and one short sentence. It closes the executor, with no subsequent tools, memory writes or writer call. Reason codes distinguish human requests and unsupported actions. The runtime also uses `controller_failure` after two invalid controller decisions and `unverified_reply` after a failed draft repair. Card numbers are redacted before model calls and in traces.

Design notes: [modular system](docs/decisions/0002-modular-system.md), [baseline fairness](docs/decisions/0003-baseline-fairness.md), and [versioned policies](docs/decisions/0004-versioned-policies.md).

## Models and training

| Role | Served model | Job |
|---|---|---|
| Controller | `f100-e2`, a LoRA adapter on `Qwen/Qwen3.8-27B` | Routing, policy selection and tool decisions |
| Writer | Base `Qwen/Qwen3.8-27B` | Patient-facing replies |

I fine-tuned the controller because its outputs are short JSON decisions against fixed schemas. It accounted for 42 of the 57 model calls in the latency sample. The untuned base agreed with the teacher on 54.4% of dev steps; the selected adapter reached 86.7%. Keeping the writer untuned lets both roles share the same base weights and endpoint. There is no per-call cloud model charge, but the GPU bills by the hour, and the hosted system has more quality failures than the cloud reference below.

- **Data:** `gpt-6-sol` generated teacher traces through S1. Acceptance included replay, format, leakage and `gpt-5.4` judge checks. After deduplication, the dataset has 623 train rows (1,559 controller steps), 105 dev rows (285 steps), 174 held-out v2 rows and 164 sealed rows.
- **Training:** BF16 LoRA, rank 16, alpha 32, dropout 0.05, on the language decoder's linear layers with the vision tower frozen. Nested 1%, 25%, 50% and 100% train subsets ran for 3 epochs, exporting an adapter each epoch. Maximum length was 8,448 tokens; no example was truncated. Held-out and sealed rows never entered training.
- **Selection:** Dev-only agreement with the teacher's structured decisions at temperature 0. Free text is excluded and invalid outputs count as disagreements. Ties favor more valid outputs, then less data, then fewer epochs.
- **Winner:** `f100-e2`, the 100% subset at epoch 2, matched 247/285 steps: 78/105 route and 169/180 decide. The base matched 155/285. Every candidate returned 285 valid outputs. The best 25%, 50% and 100% checkpoints matched 245, 246 and 247 steps, so gains flattened after 25%.

Teacher agreement measures controller imitation, not end-to-end reply quality.

## Results and limitations

An earlier held-out v1 comparison used the same cloud model for both systems: S0 missed 51/81 required escalations, while S1 missed none. That supports the structural change, not the hosted model's quality ([report](eval/results/phase3-s0-vs-s1.md)).

The hosted configuration was tested at `3f0f582`, then merged into `main` without changing its runtime. The table compares it with S1 using `gpt-6-luna` for both roles at `0d4bb4f`. Later card-redaction changes (`490d09d`, `df46221`) mean the comparison is indicative. These runs used deterministic checks, with no judge.

| Dev + adversarial: 179 cases × 3 runs | Hosted | Cloud S1 |
|---|---|---|
| Valid after finalization | 537/537 | 537/537 |
| Missed escalations | 0/150 | 0/150 |
| Correct escalation code | 147/150 | 147/150 |
| Unnecessary escalations | 13/387 | 0/387 |
| Tool selection | 286/354 | 278/354 |
| Required facts | 137/150 | 144/150 |
| Required links | 43/48 | 44/48 |
| Goal coverage proxy | 180/198 | 188/198 |
| Grounded first draft | 330/371 | 366/384 |
| Validation-stage escalations | 4/537 | 0/537 |
| Prompt tokens per item | 15,643 | 17,356 |

The hosted system missed no required handoffs, but still makes mistakes:

- Nine unnecessary handoffs came from the controller: a claimed-admin promo request, a card number with no payment request, and a hypothetical question about talking to a person.
- Four came from failed writer repairs: three wrong Gold deposits and one package no tool returned.
- Other misses include facts, links, tool selection, one memory label, and a booking-change reason used for an unsupported action. Across these runs, 41 drafts in 16 cases needed a repair before passing.

The regression suite had 57/57 valid outputs and correct escalation decisions, 30/30 correct escalation codes, all 9 required facts, all 3 links, and 12/12 complete goals. Tool selection was 39/51; two cases needed a repair in every run.

### Latency

Five scenarios ran three times through the public endpoint at concurrency 1 on 2026-10-06. There were no failures, retries or truncated outputs. Replies and tool calls were the same across all three runs. The first request took 13.7 seconds; the other 14 had a median of 12.1 seconds.

| Scenario | Model calls | Median | Slowest |
|---|---|---|---|
| Price | Route, 2 decide, write | 12.1 s | 13.7 s |
| Checkout link | Route, 3 decide, write | 19.0 s | 20.6 s |
| Save a preference | Route, 3 decide, write, repair | 29.3 s | 32.2 s |
| Financing | Route, decide, write | 11.4 s | 12.0 s |
| Ask for a person | Route | 3.4 s | 3.9 s |

Latency is the main limitation: these messages took 3–32 seconds, mostly in sequential model calls. Tools run against local fixtures and take milliseconds. The save-preference draft always needed a repair because it added an assessment link absent from that turn's tool results. Removing that repair and combining routing with the first tool plan are possible improvements. A smaller controller or quantization would also need validation before serving. The longest writer reply in the suites was 370 tokens, below the 2,048-token cap.

### Evaluation still unfinished

The hosted configuration has not run on held-out v1 or v2. Held-out v2 is registered but its 174 cases and hash remain unexported pending independent review. The pilot labels were AI-generated and adopted by the author, not independently reviewed by a human. The planned `phase5-s0-s3` and `phase6-hosted-parity` evaluations have not run.

## Evaluation and development

```sh
# Validate available cases without model calls:
uv run doctours-reply eval --dry-run --suite all

# Evaluate the hosted configuration:
uv run doctours-reply eval --system modular \
  --suite dev,adversarial,regression --runs 3 --concurrency 8
```

Reports are written under `runs/eval-<run id>/`: `report.json`, `cases.jsonl` and `summary.md`. They include item-level Wilson intervals and, for repeated runs, case-bootstrap intervals. Comparisons between systems include paired differences and McNemar tests. The packet's five messages (`--suite official`) are a sanity check, not a generalization test.

Held-out suites require their scheduled `--log-entry` and frozen hash. Until v2 is exported, `--suite all` skips it and an explicit `--suite heldout_v2` fails. Completed v1 results are in `eval/results/`.

`AGENTS.md` lists CI checks. The regular tests are network-free; `RUN_LIVE=1 uv run pytest -m live` runs smoke, policy-change, fact-change and escalation checks against the configured endpoint. Live checks repeat 3 times by default (`LIVE_RUNS`). For policy edits, bump the module version or add an overlay; see the [policy-change workflow](.agents/skills/policy-change/SKILL.md).

## Serving and configuration

The gateway accepts only `GET /v1/models` and `POST /v1/chat/completions` for the two served model IDs. Completions require JSON-schema output and cannot include tool definitions. The gateway enforces temperature 0, thinking off and a 2,048-token completion cap. vLLM listens privately on port 8000; the authenticated gateway is exposed over HTTPS on port 8001. No cloud model is called during inference.

The endpoint has one shared reviewer key, no rate limit and no health route. Process restart loops survive SSH disconnects and retry crashes after 10 seconds. After a Pod restart, the operator starts both services again. Model loading takes 7–10 minutes; while vLLM is down, completions return 502. The client retries, then exits with no batch output if failures persist.

<details>
<summary>Runtime pins and serving command</summary>

- **GPU:** RTX PRO 6000 Blackwell Server Edition, 97,887 MiB, compute capability 12.0; driver 595.91.07 (CUDA 13.2).
- **Image:** `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404`.
- **Environment:** Python 3.12.3; vLLM 0.30.0; torch 2.13.0+cu130; transformers 5.19.0; triton 3.7.1; flashinfer-python 0.6.18.post1. Model, adapter, environment and key are stored on the network volume.
- **Model revision:** `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`.
- **Adapter weights SHA-256:** `87692e1200971eb2e5208ba1d5adf366ffc6a3f86d09e049796e29a9d1591817`.
- **Adapter config SHA-256:** `2eb1a333bf1dc975f4a77c555b1d09fee2ddd0a7fc7d9775fd625f48b1419781`. Weights are not stored in this repository.

Replace the snapshot and adapter placeholders with their local paths:

```sh
VLLM_USE_FLASHINFER_SAMPLER=0 CUDA_VISIBLE_DEVICES=0 \
  vllm serve <snapshot-path> \
  --served-model-name Qwen/Qwen3.8-27B --host 127.0.0.1 --port 8000 \
  --dtype bfloat16 --max-model-len 32768 --max-num-seqs 8 \
  --enable-lora --max-lora-rank 16 --max-loras 1 \
  --lora-modules f100-e2=<adapter-path>
```

FlashInfer's top-k/top-p sampler could not be built on this image/GPU, so serving uses vLLM's sampler. The hosted adapter reproduced the selection run's 247/285 dev matches and the same 38 disagreements. The image's nginx is stopped to prevent direct exposure of vLLM. Gateway logs contain path, model, status and latency, not bodies or keys.

</details>

<details>
<summary>Other endpoints and client settings</summary>

For a different endpoint, set `MODEL_BASE_URL`, `MODEL_API_KEY` and `MODEL_ID`. Controller and writer IDs default to `MODEL_ID`; set `CONTROLLER_MODEL_ID` and `WRITER_MODEL_ID` to split roles at that endpoint. S0 always uses `MODEL_ID` and requires tool-calling support and enough context for its roughly 39,000-token prompt.

```sh
uv run doctours-reply eval --system baseline,modular \
  --suite dev,adversarial --runs 3
```

Optional client settings:

| Variable | Default / behavior |
|---|---|
| `MODEL_TIMEOUT_SECONDS` | 60 |
| `MODEL_MAX_RETRIES` | 3; timeouts, connection errors, 429 and 5xx |
| `MODEL_STRUCTURED_OUTPUT` | `json_schema`; `json_object` for compatible alternative endpoints |
| `MODEL_TEMPERATURE` | Unset; sent only when configured |
| `MODEL_REASONING_EFFORT` | Unset; sent only when configured. Values: `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max` |

These settings do not override the hosted gateway's restrictions. Concurrency is set through the CLI. For the cloud baseline, concurrency 2 with 10 retries completed runs under a 2M-token-per-minute limit; concurrency 4 exhausted the default retries.

</details>
