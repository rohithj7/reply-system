# doctours-take-home

A reply system for the packet in `docs/assignment/pre-deposit-respond-packet.md`. It reads a JSON array of `{id, text}` messages and writes one `Reply` per message, in the same order.

## What runs

The served configuration is the modular system (S1) with a fine-tuned controller and an untuned writer:
- **Controller: `f100-e2`**, a LoRA adapter on `Qwen/Qwen3.8-27B`. It routes each message, picks the policy modules to load, plans the tool calls and decides whether to answer, clarify or escalate.
- **Writer: `Qwen/Qwen3.8-27B`**, the untuned base model. It writes the patient-facing reply from the turn's tool results and loaded policies, and it has no tools.
- One vLLM process on one RunPod GPU serves both, behind an authenticated gateway at one endpoint. No cloud model is called.

S0, the packet's monolithic prompt with its 14 tools, stays in the repo as the baseline (`docs/decisions/0003-baseline-fairness.md`). It needs an endpoint with tool calling, so it does not run against the served endpoint.

## Design

### Why this structure

S0 sends about 39k tokens of rules on every call and lets one call choose tools, write the reply and decide escalation together. On held-out v1, with the same cloud model in every role, S0 missed 51 of 81 required escalations and S1 missed none (`eval/results/phase3-s0-vs-s1.md`). S1 splits a turn into steps that can each be checked and traced, and loads only the rules a message needs (`docs/decisions/0002-modular-system.md`):

1. **Route.** One controller call classifies each intent and what supports it: a tool, self-service, a rule or nothing. It picks the skills to load. A request for a person, or an action no tool or rule can do, escalates here.
2. **Load.** The policy loader renders the policies for the step. The tools a step may call are the union of the loaded modules' `allowed_tools`.
3. **Decide.** One controller call per round plans tool calls from that allowlist, loads more skills at most once, or chooses answer, clarify or escalate. The first decide call must review the route's escalation decision.
4. **Execute and observe.** The shared executor runs the calls with argument checks, ID provenance, single writes and a budget of 8 calls, for at most 3 rounds. A call outside the allowlist returns `tool_not_loaded`.
5. **Write.** The writer sees the loaded skills, the writer modules, the context and the turn's observations, and drafts the reply and its memory update.
6. **Validate.** Validators check every price, fact and link in the draft against the turn's tool results and the loaded policies' declared facts and links. A failing draft gets one repair. If it still fails, the item escalates as `unverified_reply`.
7. **Commit memory.** The memory update runs as one `updateWorkingMemory` call after validation, so a rejected draft writes nothing.

### What stays loaded on every turn

- The core modules, `identity`, `boundaries` and `escalation`, on every controller step.
- The context modules whose condition matches the fixture: the pipeline stage and whether a promo is active.
- The skill catalog: each skill's summary and activation cues, not its rules.
- For the writer, the `output` and `memory` writer modules.

The 12 skill modules, such as pricing, payment links and financing, load only when route or decide picks them. A route call is about 4,800 prompt tokens. Policies are versioned Markdown modules with TOML front matter, and overlays in `resources/policy_sets/` change policy without a code change (`docs/decisions/0004-versioned-policies.md`). Every trace records the modules it loaded, with their versions and sha256.

### How escalation works

- Route escalates with one of eight codes: `human_requested`, `unsupported_payment_action`, `unsupported_money_movement`, `unsupported_clinic_contact`, `unsupported_date_hold`, `unsupported_booking_change`, `unsupported_document_action` or `unsupported_other`. Decide can escalate later with the same codes.
- The runtime adds two more. `unverified_reply` covers a draft that fails validation after its repair. `controller_failure` covers a controller decision that fails its schema or checks twice.
- An escalation closes the executor, so no tool or memory call follows it. The reply is the code's one-sentence template, for example "Of course, someone from our team will take it from here.", with `escalate: true` and a reason. There is no writer call.
- Card numbers are redacted before any model call and in traces.

## Prerequisites

- Python 3.12 and [uv](https://docs.astral.sh/uv/) 0.10 or later. A CPU-only machine is enough, because the models run on the endpoint.
- The endpoint key, which is sent to you separately.

## Install

```sh
git clone https://github.com/rohithj7/doctours-take-home.git
cd doctours-take-home
uv sync --locked
```

## Configure

`.env.example` holds the served endpoint and model IDs. Copy it to `.env`, which is git-ignored, set `MODEL_API_KEY` to the key you were sent, and export it:

```sh
cp .env.example .env
set -a; source ./.env; set +a
```

| variable | value |
|---|---|
| `MODEL_BASE_URL` | `https://31ixwh7mttywgt-8001.proxy.runpod.net/v1` |
| `MODEL_API_KEY` | the key you were sent; never commit it |
| `MODEL_ID` | `Qwen/Qwen3.8-27B`, the writer |
| `CONTROLLER_MODEL_ID` | `f100-e2`, the controller |

The client sends the key as `Authorization: Bearer <key>`. To check it, `curl -sS -H "Authorization: Bearer $MODEL_API_KEY" "$MODEL_BASE_URL/models"` lists exactly the two model IDs; a missing or wrong key gets 401.

The gateway serves only `GET /v1/models` and `POST /v1/chat/completions`, and only for those two models. It requires a JSON-schema `response_format`, rejects tool definitions, and sends every request with temperature 0, at most 2,048 completion tokens and thinking off. So the served configuration runs only as `--system modular`.

Optional settings: `MODEL_TIMEOUT_SECONDS` (default 60), `MODEL_MAX_RETRIES` (default 3; applies to timeouts, connection errors, 429 and 5xx) and `MODEL_STRUCTURED_OUTPUT` (`json_schema`, the default, or `json_object` for endpoints without JSON-schema support). `MODEL_TEMPERATURE` and `MODEL_REASONING_EFFORT` (`none`, `minimal`, `low`, `medium`, `high`, `xhigh` or `max`) are unset by default and sent only when set; some reasoning models need `MODEL_REASONING_EFFORT=none` for tool calling. `CONTROLLER_MODEL_ID` and `WRITER_MODEL_ID` send the modular system's controller and writer calls to other models at the same endpoint; each defaults to `MODEL_ID`, and the baseline always uses `MODEL_ID`. These are the only settings the client reads; concurrency is the `--concurrency` flag.

Any other OpenAI-compatible endpoint also works. Set the three `MODEL_*` variables and leave `CONTROLLER_MODEL_ID` unset to run S1 with one model in both roles, or S0 if the endpoint supports tool calls.

## Run

```sh
uv run doctours-reply run --system modular --input messages.json --output replies.json
```

- `--system modular` runs the served configuration. `--system baseline`, the default, runs S0.
- The packet's five messages are in that shape in `eval/official/human_messages.json`.
- `--input -` reads stdin and `--output -` writes stdout. The output file is written atomically.
- `--concurrency N` (1-16) runs items in parallel. Every item is isolated, and the output keeps the input order.
- Traces go to `runs/<run id>/traces.jsonl`, or to `--trace-dir`, never to the output. Card numbers are redacted before the model call and in traces.
- Exit codes: 0 success; 2 invalid input or reference; 3 missing or invalid model configuration; 4 model failure. On any failure, nothing is written to the output.

## Try messages interactively

```sh
uv run doctours-reply try --system modular
```

It prompts for patient messages until Ctrl-D, and runs each one through the same pipeline as `run`: route, policy loading, tools, writer, validation and finalizer. Each message is one isolated item against the packet fixture, with the same patient, conversation summary, working memory, saved clinics and assessment. A write in one message, such as a saved preference, does not carry over to the next. Messages can also be given as arguments: `uv run doctours-reply try --system modular "Do you offer financing?"`.

For each message it prints the patient-facing reply, the escalation reason if there is one, and the total elapsed time. Then it lists each model call with its model, time, completion tokens and finish reason, and each tool call with its time and status. The trace location comes last:

```
reply: The Silver package at Heva Clinic is $3,000 USD, with a $500 USD deposit. It includes 3 hotel nights.
elapsed: 17.79 s
  route             f100-e2              4.83 s  46 tokens, stop
  decide            f100-e2              5.24 s  62 tokens, stop
  decide            f100-e2              2.76 s  25 tokens, stop
  write             Qwen/Qwen3.8-27B     4.95 s  94 tokens, stop
  tool getClinicPackages                 0.00 s  ok
trace: runs/<run id>/traces.jsonl, item try-1
```

Tools read the fixture in process, so they take milliseconds. A failed message prints the error and its trace, and the prompt continues; the exit code is then 4.

## Results of the served configuration

The served configuration ran through the public endpoint at `3f0f582`, merged into `main` with its runtime unchanged, with no judge:

```sh
uv run doctours-reply eval --system modular --suite dev,adversarial --runs 3 --concurrency 8
uv run doctours-reply eval --system modular --suite regression --runs 3 --concurrency 8
```

The reference is S1 with `gpt-6-luna` as controller and writer, run at `0d4bb4f` in the same way. The later behavior changes, `490d09d` and `df46221`, change card redaction, so the comparison is indicative.

| dev and adversarial, 179 cases x 3 runs | served | S1, cloud |
|---|---|---|
| valid after finalize | 537/537 | 537/537 |
| missed escalations | 0/150 | 0/150 |
| escalation code correct | 147/150 | 147/150 |
| unnecessary escalations | 13/387 | 0/387 |
| tool selection | 286/354 (0.808) | 278/354 (0.785) |
| required facts | 137/150 | 144/150 |
| required links | 43/48 | 44/48 |
| goal coverage proxy | 180/198 (0.909) | 188/198 (0.950) |
| grounded on the first draft | 330/371 (0.889) | 366/384 (0.953) |
| validation-stage escalations | 4/537 | 0/537 |
| prompt tokens per item | 15,643 | 17,356 |

Remaining failures in dev and adversarial:
- **Unnecessary escalations, controller (9 of 13).** All three runs of each:
  - adv-003: decide escalates a promo-code request that claims admin authority.
  - adv-017: route escalates a card number sent with no request.
  - dev-095: route escalates a hypothetical question about talking to a person.
- **Unnecessary escalations, writer (4 of 13).** The writer's draft failed validation after its repair, so the reply became `unverified_reply`:
  - dev-018, all three runs: the draft states the wrong Gold deposit.
  - dev-036, one run: the draft names a Silver package that no tool returned.
- **Wrong escalation code:** adv-053 gets `unsupported_booking_change` instead of `unsupported_other`, as S1 does.
- **Missing required facts and links:**
  - Facts in adv-001, adv-025, dev-018 and dev-102.
  - Links in dev-035 and dev-105.
- **Wrong memory label:** dev-032.
- **Tool selection:** 68 misses in 23 cases.
- **Validation repairs:** 41 drafts in 16 cases needed one before they passed.

Regression, 19 cases x 3 runs:
- **Correct:** 57/57 outputs valid, 57/57 escalation decisions and 30/30 codes.
- **Facts and links:** all 9 required facts and all 3 required links.
- **Goals:** 12/12 complete, with no unnecessary escalation.
- **Remaining misses:** tool selection is 39/51, missing in RC-E-5, RC-E-6, RC-E-12 and RC-E-19. RC-E-8 and RC-E-12 need a validation repair in every run.

### Latency

These are five dev-fixture scenarios through the public endpoint with `try`, three rounds at concurrency 1 on 2026-10-06, with the frozen configuration. There were no failures and no retries. Every call finished with `stop`, so no reply was truncated, and each scenario gave the same reply and tool calls in all three runs. The first request of the session, a price question, took 13.7 s. The other 14 had a median of 12.1 s.

| scenario | calls | runs | median | slowest |
|---|---|---|---|---|
| price | route, 2 decide, write | 13.7, 12.1, 12.0 s | 12.1 s | 13.7 s |
| checkout link | route, 3 decide, write | 20.6, 18.1, 19.0 s | 19.0 s | 20.6 s |
| save a preference | route, 3 decide, write, repair | 32.2, 28.9, 29.3 s | 29.3 s | 32.2 s |
| financing | route, decide, write | 11.4, 12.0, 10.4 s | 11.4 s | 12.0 s |
| ask for a person | route | 3.9, 3.4, 3.3 s | 3.4 s | 3.9 s |

Controller calls take 1.7 to 8.6 s each and writer calls 4.2 to 8.2 s. Tools take milliseconds. The writer's longest reply in any suite was 370 completion tokens, far below the 2,048-token cap. The save-preference draft always needs one repair, because it adds an assessment link that no tool returned in that turn.

Latency is the main known limitation of this v0: a message takes 3 to 32 s. Nearly all of it is model calls, which run one after another, 1 to 6 per message. Each call costs about 0.7 to 0.9 s plus about 42 ms per generated token, from a linear fit over the 57 calls above. Possible improvements, not yet tried:
- **Fewer calls.** The number of calls drives most of the spread. Fixing the save-preference draft would remove its repair, a full writer call in every run. A route step that also plans the first tool calls would save a decide round on simple questions.
- **Faster tokens.** A smaller controller or an FP8-quantized model generates each token faster. Either can change decisions, so it would go through the same dev selection before serving.

## Controller training and selection

- **Why train.**
  - **The controller's task suits training.** The controller makes most of a turn's model calls: 42 of the 57 in the latency run above. Each one is a short JSON decision against a fixed schema, not prose. Narrow decisions that can be checked suit fine-tuning on a stronger model's verified traces.
  - **A served controller has no per-call price.** Its weights are also fixed and pinned by hash (Serving, below).
  - **Training is what makes a local controller usable.** Untuned, the base model agrees with the teacher on only 155 of 285 dev steps.
  - **One endpoint.** The writer stays untuned, so one served model handles both roles. Reviewers need one endpoint and one key, and no cloud account.
  - **The costs.** Quality is lower: against S1 on a cloud model, the served configuration escalates 13 of 387 messages that needed no escalation and covers fewer goals (results above). The GPU also bills by the hour whether or not it serves requests.
- **Data.** A cloud teacher (`gpt-6-sol`) ran this repo's S1 harness as controller and writer on generated patient messages. A row was accepted only after replay, format, leakage and judge (`gpt-5.4`) checks. The dataset has 1,066 rows after deduplication:
  - 623 train rows (1,559 controller-step examples);
  - 105 dev rows (285 steps);
  - 174 held-out v2 rows;
  - 164 sealed rows.
- **Training.** BF16 LoRA, rank 16, alpha 32 and dropout 0.05, on every linear layer of `Qwen/Qwen3.8-27B`'s language decoder, with the vision tower frozen. Runs used nested 1%, 25%, 50% and 100% subsets of the train split for 3 epochs, with an adapter exported each epoch. The maximum length was 8,448 tokens, and no example was truncated. Training read only the train split; held-out v2 and sealed rows never entered it.
- **Selection, on dev only.** Each adapter was served through vLLM and given every dev step with the controller's schema at temperature 0. Its decision was compared with the teacher's:
  - for route: intents, skills, outcome and escalation code;
  - for decide: the next action, the calls and their arguments, the skills and the escalation review.

  Free text is not compared, and an invalid output counts as a disagreement. The rule takes the most teacher agreement, then the most valid outputs; a tie goes to less data, then fewer epochs.
- **Result.** `f100-e2`, all train rows at epoch 2, agrees with the teacher on 247 of 285 dev steps (0.867): route 78/105 and decide 169/180. The untuned base model agrees on 155/285 (0.544). All 285 outputs were valid for every candidate.
  - Past 25% of the data the curve is flat. The best epochs at 25%, 50% and 100% agree on 245, 246 and 247 steps.
  - `f100-e2`'s 38 disagreements are on intents (16), skills (13) and calls (11), never on the next action, outcome or escalation.
  - The base model's 130 disagreements include 83 on the escalation review.
  - Teacher agreement on dataset steps is not end-to-end quality: the dev and adversarial suites above still show controller escalation errors.

## Serving

- **Hardware.** One RunPod Pod with an RTX PRO 6000 Blackwell Server Edition (97,887 MiB, compute capability 12.0) and driver 595.91.07 (CUDA 13.2). The image is `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404`.
- **Runtime.** vLLM 0.30.0 in its own Python 3.12.3 environment, with torch 2.13.0+cu130, transformers 5.19.0, triton 3.7.1 and flashinfer-python 0.6.18.post1.
- **Model.** `Qwen/Qwen3.8-27B` at revision `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`.
- **Adapter `f100-e2`.** `adapter_model.safetensors` has sha256 `87692e1200971eb2e5208ba1d5adf366ffc6a3f86d09e049796e29a9d1591817`, and `adapter_config.json` has sha256 `2eb1a333bf1dc975f4a77c555b1d09fee2ddd0a7fc7d9775fd625f48b1419781`. The weights are not in this repo.
- **Command.** One vLLM process on GPU 0 serves both names, on loopback only:

  ```sh
  VLLM_USE_FLASHINFER_SAMPLER=0 CUDA_VISIBLE_DEVICES=0 vllm serve <Qwen/Qwen3.8-27B snapshot at 1d4bf0f2> \
    --served-model-name Qwen/Qwen3.8-27B --host 127.0.0.1 --port 8000 --dtype bfloat16 \
    --max-model-len 32768 --max-num-seqs 8 \
    --enable-lora --max-lora-rank 16 --max-loras 1 --lora-modules f100-e2=<adapter directory>
  ```
- **Sampler.** FlashInfer's top-k/top-p sampler cannot be built for this GPU on this image, so `VLLM_USE_FLASHINFER_SAMPLER=0` uses vLLM's own sampler. Every request is greedy, at temperature 0, so the tokens are the same. On the Pod, `f100-e2` reproduces selection's 247 of 285 dev steps exactly, with the same 38 disagreements.
- **Gateway.** The gateway listens on port 8001 behind the Pod's HTTPS proxy. It checks the bearer key and enforces the rules under Configure. It logs one line per request, with the path, model, status and latency, and never logs bodies or keys. The image's nginx, which would expose vLLM's port directly, is stopped.
- **Restarts.** The operator runs vLLM and the gateway under restart loops that outlive the SSH session. A crashed process is restarted after 10 seconds. The gateway is back within seconds, and vLLM in 7 to 10 minutes, because it loads from a network volume. After a Pod restart, the operator starts both again; the model, adapter, environment and key stay on the volume. While vLLM is down, requests fail with 502. The client retries 3 times, then exits 4 with no output, so rerun the command once `/models` answers again.
- **Not yet built.** The endpoint has one key for all reviewers, with no rate limit and no health route.

## Evaluation status

- Held-out v1 rows `phase2-s0-baseline` and `phase3-s0-vs-s1` have run; their results are in `eval/results/`. The served configuration has not run on held-out v1.
- Held-out v2 has 174 cases. It is registered as a guarded suite, but its cases and hash are not committed. Its independent review has not happened, so its export stays blocked, and the official held-out evaluation (`phase5-s0-s3`, `phase6-hosted-parity`) has not run.
- The review sample of the data pilot used AI-generated labels, adopted by the author. They are not an independent human review.

## Evaluate

```sh
uv run doctours-reply eval --dry-run --suite all        # validate every case and label; no model calls
uv run doctours-reply eval --system modular --suite dev,adversarial,regression --runs 3
uv run doctours-reply eval --system baseline,modular --suite dev,adversarial --runs 3
```

The last command needs an endpoint with tool calling for S0.

Reports go to `runs/eval-<run id>/`: `report.json`, `cases.jsonl` and `summary.md`. They give Wilson 95% intervals over items and, with more than one run, 95% intervals from a case bootstrap, which treats a case's runs as one unit. With both systems, `modular_minus_baseline` gives the paired difference per metric, its case-level interval and an exact McNemar test on each case's majority outcome. The official five messages (`--suite official`) are a sanity check only. The held-out set runs only through its schedule row, for example `--suite heldout_v1 --log-entry phase2-s0-baseline --runs 3`, which first appends an entry to `eval/results/heldout-log.md`. Rows `phase2-s0-baseline` and `phase3-s0-vs-s1` have run; their results are in `eval/results/`. Held-out v2 (`heldout_v2`, rows `phase5-s0-s3` and `phase6-hosted-parity`) is guarded and frozen by hash the same way. Its cases and hash are not committed yet; until either is, `--suite all` skips it and `--suite heldout_v2` fails.

Each baseline model call sends about 39k prompt tokens, because the legacy prompt is long. Under a 2M tokens-per-minute limit, `--concurrency 2` with `MODEL_MAX_RETRIES=10` completed every run; `--concurrency 4` exhausted the default 3 retries on 429 responses. S1 sends about 17k prompt tokens per item over about 3 calls, and its development runs at `--concurrency 4` needed no rate-limit retries. The served endpoint runs at most 8 requests at once, so use `--concurrency 8` or lower.

## Develop

`AGENTS.md` lists the checks CI runs. The test suite is network-free; `RUN_LIVE=1 uv run pytest -m live` runs the live checks against the configured endpoint. They are the smoke test and, in `tests/live/test_rc_live.py`, S1's policy-change, fact-change and escalation checks, each repeated `LIVE_RUNS` times (default 3).

A policy change is a module edit with a version bump, or an overlay in `resources/policy_sets/` (`.agents/skills/policy-change/SKILL.md`).
