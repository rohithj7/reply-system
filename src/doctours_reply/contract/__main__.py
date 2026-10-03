"""Print the `Reply` JSON schema: `uv run python -m doctours_reply.contract`."""

import json

from doctours_reply.contract.reply import Reply

print(json.dumps(Reply.model_json_schema(), indent=2))
