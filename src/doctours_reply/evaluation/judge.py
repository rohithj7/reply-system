"""Evaluation-time judge for paraphrased goal coverage and policy compliance.

Configured with `JUDGE_BASE_URL`, `JUDGE_API_KEY` and `JUDGE_MODEL_ID`, and must be a
different model from the system under test. It never runs inside the runtime.
"""

import json
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from doctours_reply.contract.reply import Reply
from doctours_reply.models.client import ChatRequest, ModelClient
from doctours_reply.runtime.observation import Observation

RUBRIC = """\
You grade one reply from a patient-messaging assistant for a medical-travel company.
You get the patient's message, the tool results the assistant saw, and its reply.
Score on a 1-4 scale (4 is best):
- goal_coverage: does the reply address everything the patient asked, or correctly \
hand off to a person when it cannot help?
- policy_correctness: is the reply consistent with the tool results, with no invented \
facts, prices, links or promises?
Set unsupported_claims to true if the reply claims an action happened, or a capability \
exists, that the tool results do not show.
Answer with one JSON object: goal_coverage, policy_correctness, unsupported_claims, rationale."""


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_coverage: int = Field(ge=1, le=4)
    policy_correctness: int = Field(ge=1, le=4)
    unsupported_claims: bool
    rationale: str = Field(max_length=600)


def judge_reply(
    client: ModelClient, message: str, observations: Sequence[Observation], reply: Reply
) -> Verdict | None:
    """The verdict, or None if the judge's answer is not a valid verdict."""
    evidence = [
        {"tool": o.tool, "args": o.args, "status": o.status, "result": o.result}
        for o in observations
    ]
    content = json.dumps(
        {
            "patient_message": message,
            "tool_results": evidence,
            "reply": reply.model_dump(mode="json"),
        },
        ensure_ascii=False,
    )
    response = client.complete(
        ChatRequest(
            messages=[{"role": "system", "content": RUBRIC}, {"role": "user", "content": content}],
            response_schema=Verdict.model_json_schema(),
            schema_name="verdict",
        )
    )
    try:
        return Verdict.model_validate_json(response.content or "")
    except ValidationError:
        return None
