"""
Run the YAML export graph agent (no MCP, no Neo4j).

From repo root:
  python rag_adk_agent/run_export_graph_agent.py --graph .clangd-graph-rag/code_graph.yaml --query "List graph stats"

PowerShell:
  $env:DEEPSEEK_API_KEY = "..."
  python rag_adk_agent/run_export_graph_agent.py --graph D:\\proj\\.clangd-graph-rag\\code_graph.yaml

Optional env: LLM_MODEL (default deepseek/deepseek-chat), CODE_GRAPH_YAML if you omit --graph.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


async def _async_main(user_id: str, session_id: str | None, query: str | None, root_agent) -> None:
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    app_name = "export_graph_agent"
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name=app_name, user_id=user_id, session_id=session_id, state=None
    )
    if not session:
        session = await session_service.create_session(app_name=app_name, user_id=user_id, state=None)

    runner = Runner(agent=root_agent, app_name=app_name, session_service=session_service)

    if query:
        print(f"\n[User]: {query}")
        content = types.Content(role="user", parts=[types.Part(text=query)])
        final_text = ""
        async for event in runner.run_async(user_id=user_id, session_id=session.id, new_message=content):
            calls = event.get_function_calls()
            if calls:
                for call in calls:
                    print(f"Tool: {call.name} {call.args}")
            if event.is_final_response():
                if event.content and event.content.parts:
                    final_text = event.content.parts[0].text or ""
                elif event.actions and event.actions.escalate:
                    final_text = f"Escalated: {getattr(event, 'error_message', '') or 'unknown'}"
        print(f"\nAgent: {final_text}\n")
    else:
        current = input("\n[User] ('quit' to exit): ").strip()
        while current.lower() not in ("quit", "exit", ""):
            print(f"\n[User]: {current}")
            content = types.Content(role="user", parts=[types.Part(text=current)])
            final_text = ""
            async for event in runner.run_async(user_id=user_id, session_id=session.id, new_message=content):
                calls = event.get_function_calls()
                if calls:
                    for call in calls:
                        print(f"Tool: {call.name} {call.args}")
                if event.is_final_response():
                    if event.content and event.content.parts:
                        final_text = event.content.parts[0].text or ""
            print(f"\nAgent: {final_text}\n")
            current = input("\n[User] ('quit' to exit): ").strip()

    session = await runner.session_service.get_session(
        app_name=app_name, user_id=user_id, session_id=session.id
    )
    out_key = runner.agent.output_key
    await runner.close()
    if session and session.state.get(out_key):
        print(f"Session[{out_key}]: {session.state[out_key]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run export-graph ADK agent (YAML/JSON, no Neo4j/MCP)")
    parser.add_argument("--graph", default=None, help="Path to code_graph.yaml or .json (sets CODE_GRAPH_YAML)")
    parser.add_argument("--user-id", default="user_1")
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--query", default=None)
    args = parser.parse_args()

    if args.graph:
        os.environ["CODE_GRAPH_YAML"] = str(Path(args.graph).expanduser().resolve())

    if not (os.environ.get("CODE_GRAPH_YAML") or os.environ.get("GRAPH_PATH")):
        print(
            "Error: pass --graph <path/to/code_graph.yaml> or set CODE_GRAPH_YAML / GRAPH_PATH",
            file=sys.stderr,
        )
        sys.exit(2)

    from rag_adk_agent.export_graph_agent import root_agent

    try:
        asyncio.run(_async_main(args.user_id, args.session_id, args.query, root_agent))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
