"""RevenueCat Subscription Agent — a natural-language interface to RevenueCat's REST API v2.

Ask questions about your subscribers, offerings, and entitlements in plain English.
The agent interprets your query, calls the right RevenueCat API endpoints, and
returns structured results.

Architecture: Claude (tool calling) → RevenueCat REST API v2
Pattern adapted from a production agent executor (multi-round tool loop with safety limits).

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    export REVENUECAT_API_KEY=sk_...      # Your RevenueCat secret API key
    export REVENUECAT_PROJECT_ID=proj...   # Your RevenueCat project ID

    python agent.py "Show me subscriber abc123's current entitlements"
    python agent.py "List all offerings in my project"
    python agent.py                        # Interactive mode
"""

from __future__ import annotations

import os
import sys
import json
import httpx
import anthropic

# ── Config ────────────────────────────────────────────────────────────────────

MODEL = "claude-sonnet-4-6"
MAX_TOOL_ROUNDS = 5
RC_BASE_URL = "https://api.revenuecat.com/v2"

rc_api_key = os.environ.get("REVENUECAT_API_KEY", "")
rc_project_id = os.environ.get("REVENUECAT_PROJECT_ID", "")


def _rc_headers() -> dict:
    return {
        "Authorization": f"Bearer {rc_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ── RevenueCat API tools (Anthropic tool-calling format) ──────────────────────

TOOLS = [
    {
        "name": "get_subscriber",
        "description": (
            "Get a subscriber's full profile from RevenueCat, including their "
            "active subscriptions, entitlements, purchase history, and attributes. "
            "Use this when the user asks about a specific subscriber or customer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "app_user_id": {
                    "type": "string",
                    "description": "The subscriber's app user ID (the ID you set in your app, or the anonymous ID from RevenueCat)",
                }
            },
            "required": ["app_user_id"],
        },
    },
    {
        "name": "list_offerings",
        "description": (
            "List all offerings configured in the RevenueCat project. "
            "Offerings are the set of products shown to users on your paywall. "
            "Each offering contains packages, and each package maps to a product."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "expand": {
                    "type": "boolean",
                    "description": "If true, expand packages and products within each offering. Defaults to true.",
                }
            },
        },
    },
    {
        "name": "list_entitlements",
        "description": (
            "List all entitlements configured in the RevenueCat project. "
            "Entitlements represent access levels (e.g. 'pro', 'premium') that "
            "are granted when a user purchases a product."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "list_products",
        "description": (
            "List all products configured in the RevenueCat project. "
            "Products map to in-app purchases configured in the app stores "
            "(App Store, Google Play, Stripe, etc.)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "grant_entitlement",
        "description": (
            "Grant a promotional entitlement to a subscriber. "
            "Use this when the user wants to give a subscriber access to a feature "
            "without requiring a purchase. Useful for trials, promotions, or support."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "app_user_id": {
                    "type": "string",
                    "description": "The subscriber's app user ID",
                },
                "entitlement_id": {
                    "type": "string",
                    "description": "The identifier of the entitlement to grant",
                },
                "duration": {
                    "type": "string",
                    "enum": ["daily", "three_day", "weekly", "monthly", "two_month",
                             "three_month", "six_month", "yearly", "lifetime"],
                    "description": "How long the promotional entitlement should last",
                },
            },
            "required": ["app_user_id", "entitlement_id", "duration"],
        },
    },
    {
        "name": "revoke_entitlement",
        "description": (
            "Revoke a promotional entitlement from a subscriber. "
            "Only works for entitlements that were granted via the API (promotional), "
            "not for entitlements from store purchases."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "app_user_id": {
                    "type": "string",
                    "description": "The subscriber's app user ID",
                },
                "entitlement_id": {
                    "type": "string",
                    "description": "The identifier of the entitlement to revoke",
                },
            },
            "required": ["app_user_id", "entitlement_id"],
        },
    },
]


# ── Tool execution ────────────────────────────────────────────────────────────

def execute_tool(name: str, inputs: dict) -> dict:
    """Call the RevenueCat REST API v2 based on the tool name and inputs."""

    try:
        with httpx.Client(timeout=15.0) as client:
            if name == "get_subscriber":
                uid = inputs["app_user_id"]
                resp = client.get(
                    f"{RC_BASE_URL}/projects/{rc_project_id}/subscribers/{uid}",
                    headers=_rc_headers(),
                )

            elif name == "list_offerings":
                params = {}
                if inputs.get("expand", True):
                    params["expand"] = "items,items.package,items.package.product"
                resp = client.get(
                    f"{RC_BASE_URL}/projects/{rc_project_id}/offerings",
                    headers=_rc_headers(),
                    params=params,
                )

            elif name == "list_entitlements":
                resp = client.get(
                    f"{RC_BASE_URL}/projects/{rc_project_id}/entitlements",
                    headers=_rc_headers(),
                )

            elif name == "list_products":
                resp = client.get(
                    f"{RC_BASE_URL}/projects/{rc_project_id}/products",
                    headers=_rc_headers(),
                )

            elif name == "grant_entitlement":
                uid = inputs["app_user_id"]
                eid = inputs["entitlement_id"]
                resp = client.post(
                    f"{RC_BASE_URL}/projects/{rc_project_id}/subscribers/{uid}/entitlements/{eid}/grant_promotional",
                    headers=_rc_headers(),
                    json={"duration": inputs["duration"]},
                )

            elif name == "revoke_entitlement":
                uid = inputs["app_user_id"]
                eid = inputs["entitlement_id"]
                resp = client.post(
                    f"{RC_BASE_URL}/projects/{rc_project_id}/subscribers/{uid}/entitlements/{eid}/revoke_promotional",
                    headers=_rc_headers(),
                )

            else:
                return {"error": f"Unknown tool: {name}"}

            if resp.status_code >= 400:
                return {
                    "error": f"RevenueCat API error {resp.status_code}",
                    "detail": resp.text[:500],
                }
            return resp.json()

    except httpx.TimeoutException:
        return {"error": "Request to RevenueCat API timed out"}
    except Exception as e:
        return {"error": str(e)}


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a RevenueCat Subscription Agent — a helpful assistant that manages
in-app subscriptions through RevenueCat's REST API.

You help developers and product managers:
- Look up subscriber information and purchase history
- Browse offerings, products, and entitlements
- Grant or revoke promotional entitlements
- Explain RevenueCat concepts in plain language

When responding:
- Use the available tools to fetch real data before answering
- Present results clearly with key information highlighted
- If a query is ambiguous, ask for clarification
- Explain what you're doing at each step so the user can follow along

You have access to RevenueCat's REST API v2 through the provided tools. Always use
tools to fetch real data rather than guessing or making assumptions about the
user's RevenueCat configuration."""


# ── Agent loop ────────────────────────────────────────────────────────────────

def run_agent(user_query: str) -> str:
    """Run the agent loop: send query to Claude, execute tools, return final answer."""

    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": user_query}]

    for round_num in range(MAX_TOOL_ROUNDS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # If the model is done (no tool calls), return the text response
        if response.stop_reason == "end_turn":
            return "".join(
                block.text for block in response.content if block.type == "text"
            )

        # Process tool calls
        tool_results = []
        text_parts = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                print(f"  -> Calling {block.name}({json.dumps(block.input, indent=None)})")
                result = execute_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, indent=2, default=str),
                })

        if text_parts:
            print(f"  Agent: {''.join(text_parts)}")

        # Feed tool results back to Claude for the next round
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    return "Reached maximum tool rounds. The query may be too complex for a single interaction."


# ── CLI entry point ───────────────────────────────────────────────────────────

def main():
    if not rc_api_key:
        print("Error: REVENUECAT_API_KEY environment variable is required.")
        print("  export REVENUECAT_API_KEY=sk_...")
        sys.exit(1)

    if not rc_project_id:
        print("Error: REVENUECAT_PROJECT_ID environment variable is required.")
        print("  export REVENUECAT_PROJECT_ID=proj...")
        sys.exit(1)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable is required.")
        sys.exit(1)

    # Single query mode
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        print(f"\nQuery: {query}\n")
        result = run_agent(query)
        print(f"\n{result}\n")
        return

    # Interactive mode
    print("\nRevenueCat Subscription Agent")
    print("Ask questions about your subscribers, offerings, and entitlements.")
    print("Type 'quit' to exit.\n")

    while True:
        try:
            query = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not query:
            continue
        if query.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break

        result = run_agent(query)
        print(f"\nAgent: {result}\n")


if __name__ == "__main__":
    main()
