# RevenueCat Subscription Agent

A natural-language interface to RevenueCat's REST API v2, powered by Claude.

Ask questions about your subscribers, offerings, and entitlements in plain English. The agent interprets your query, calls the right RevenueCat API endpoints, and returns structured results.

## How it works

```
You: "Show me subscriber abc123's current entitlements"
  -> Calling get_subscriber({"app_user_id": "abc123"})
Agent: Subscriber abc123 has an active "pro" entitlement, purchased via
       the App Store on 2024-11-15. Their subscription renews monthly...
```

The agent uses Claude's tool-calling capability to select the right RevenueCat API endpoints based on your natural language query. It can chain multiple API calls in a single interaction (e.g., look up a subscriber, then check their entitlements, then grant a promotional upgrade).

## Architecture

This demo adapts the agent executor pattern from a production multi-tenant agent platform:

- **Tool definitions** map to RevenueCat REST API v2 endpoints
- **Multi-round tool loop** with safety limits (max 5 rounds)
- **Structured error handling** for API failures and timeouts

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export ANTHROPIC_API_KEY=sk-ant-...
export REVENUECAT_API_KEY=sk_...         # Secret API key from RevenueCat dashboard
export REVENUECAT_PROJECT_ID=proj...     # Project ID from RevenueCat dashboard
```

## Usage

```bash
# Single query
python agent.py "List all offerings in my project"

# Interactive mode
python agent.py
```

## Available capabilities

| What you can ask | API endpoint used |
|---|---|
| Look up a subscriber's profile | `GET /subscribers/{id}` |
| List all offerings and packages | `GET /offerings` |
| List all entitlements | `GET /entitlements` |
| List all products | `GET /products` |
| Grant a promotional entitlement | `POST /subscribers/{id}/entitlements/{eid}/grant_promotional` |
| Revoke a promotional entitlement | `POST /subscribers/{id}/entitlements/{eid}/revoke_promotional` |

## Example queries

- "Show me subscriber user_abc's purchase history"
- "What offerings do we have configured?"
- "Grant user_abc a monthly pro trial"
- "What products are set up in our project?"
- "Revoke the promotional entitlement for user_xyz"
