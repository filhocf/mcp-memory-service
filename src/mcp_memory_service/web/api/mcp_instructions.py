# Copyright 2024 Heinrich Krupp
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Usage doctrine returned as `instructions` in the MCP `initialize` result.

The MCP specification lets the server ship a short, human-readable note that
clients may surface to the model. It is a module constant (not generated per
request) so every handshake in a process sees byte-identical text, and it is
kept under 1200 characters so it does not bloat every session.

Set `MCP_DISABLE_INSTRUCTIONS=1` (or `true`, case-insensitive, trimmed) to omit
the field entirely. See SPEC-F006.
"""

import os

# Keep this under 1200 characters (SPEC-F006 R3). Doctrine only: what to do
# before answering, how to keep reads cheap, what is worth persisting, and who
# owns `agent_id`.
MCP_INSTRUCTIONS = (
    "This server is persistent long-term memory. "
    "Before answering questions about prior state, decisions, or where work "
    "left off, call memory_search first. "
    "Keep reads cheap: memory_search(query=..., limit<=3, "
    "max_response_chars<=2000). "
    "Store decisions, measured numbers, procedures, and pitfalls; do not store "
    "what is already in the repository or the conversation. "
    "agent_id is supplied by the transport (X-Agent-ID); do not invent one."
)

DISABLE_ENV = "MCP_DISABLE_INSTRUCTIONS"


def instructions_enabled() -> bool:
    """Return False when `MCP_DISABLE_INSTRUCTIONS` is `1` or `true`.

    The comparison is case-insensitive and ignores surrounding whitespace, so
    `TRUE` and ` 1 ` both suppress the field. `0`, `false`, empty and unset all
    keep it.
    """
    value = os.environ.get(DISABLE_ENV, "").strip().lower()
    return value not in {"1", "true"}
