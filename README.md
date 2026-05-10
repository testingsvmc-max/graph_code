# C/C++ Source Code Graph RAG (using Clang/Clangd)

This project builds a Neo4j graph RAG (Retrieval-Augmented Generation) for a C/C++ software project based on clang/clangd, which can be queried for deep software project analysis. It works well with large and complex codebases like the Linux, llvm, llama.cpp, etc. 

The project includes an example MCP server and an AI expert agent. You can also develop your own MCP servers and agents around the graph RAG for your specific purposes, such as:

**Software Analysis**
*   Analyze project organization (folders, files, modules)
*   Analyze code patterns and structures
*   Understand call chains and class relationships
*   Examine architectural design and workflows
*   Trace dependencies and interactions

**Expert Assistance**
*   **Code Refactoring Advice**: Provide guidance on design improvements and optimizations
*   **Bug Analysis**: Help identify root causes of bugs or race conditions
*   **Documentation**: Assist with software design documentation
*   **Feature Implementation**: Guide on implementing features based on requirements
*   **Architecture Review**: Analyze and suggest improvements to system architecture

## Quick Start (No Neo4j)

If you only need query/search and call graph exploration, you can run a full flow with **clangd-graph-rag only** (no Neo4j, no extra graph-review apps).

For VSCode + Cline users: after opening this repo, you can ask Cline:

```text
setup clangd graph
```

Or to build graph directly for current project/code directory:

```text
Build graph code for this project or code directory
```

Or to query callers/callees and traverse call graph:

```text
search callers/callees and graph traversal
```

Cline can use project skills under `.cline/skills/` and run:

```bash
python standalone_tools/setup_clangd_graph.py
```

For **deterministic graph quality metrics** (node/edge counts, cross-file `CALLS`, function `file_path` coverage), see [eval/README.md](eval/README.md) and run `python eval/run_graph_eval.py --help`.

### Export graph tools — MCP-style `*_tool` API (HTTP + MCP + CLI)

On a **YAML/JSON export** (no Neo4j), use stable ``*_tool`` names (where the data exists in this graph):

| HTTP | `GET /tools/catalog` — list tools; `POST /tools/invoke` — body `{"tool":"list_graph_stats_tool","arguments":{}}` |
| CLI | `python standalone_tools/code_graph_tools.py <code_graph.yaml> catalog` and `... invoke <tool_name> --args '{...}'` |
| MCP | `python code_graph_mcp_tools_server.py <graph.yaml>` — tools `invoke_graph_tool`, `list_graph_tools` (set `GRAPH_PATH` or pass path as argv); default port **8810** |

Implemented tools include `list_graph_stats_tool`, `query_graph_tool`, `traverse_graph_tool`, `get_impact_radius_tool`, `semantic_search_nodes_tool`, `get_minimal_context_tool`, `get_review_context_tool`, `find_large_functions_tool`, `get_hub_nodes_tool`, `get_bridge_nodes_tool`, `detect_changes_tool`, `get_knowledge_gaps_tool`, `get_surprising_connections_tool`, `get_suggested_questions_tool`. Flows, communities, wiki, refactor, multi-repo, and embed-on-export return `status: unsupported` with a short reason.

`setup_clangd_graph.py` now also checks `clangd-indexer` and tries to install it:
- Windows: via `winget` (`LLVM.clangd`, fallback `LLVM.LLVM`)
- Linux (Debian/Ubuntu): via `apt-get install clangd clang-tools`

If you prefer manual handling, use:

```bash
python standalone_tools/setup_clangd_graph.py --skip-clangd-indexer
```

For direct build, Cline can run:

```bash
python standalone_tools/build_graph_code.py --also-db
```

For query/traversal, Cline can run API flow from:

```bash
python -m code_graph_api <graph.yaml> --host 127.0.0.1 --port 8090
```

During setup, the script asks for confirmation whether you want to provide a
`compile_commands.json` path now. If yes, it stores the value into
`.env.clangd_graph` as `COMPILE_COMMANDS_PATH`.

1. Install Python dependencies:
   ```bash
   # default profile: no Neo4j
   pip install -r requirements-core.txt

   # optional Neo4j extras
   # pip install -r requirements-core.txt -r requirements-neo4j.txt
   ```
2. Prepare compilation inputs for your target C/C++ repo:
   ```bash
   # compile_commands.json (example with CMake)
   cmake -DCMAKE_EXPORT_COMPILE_COMMANDS=ON <your-original-cmake-options>

   # clangd index YAML
   clangd-indexer --executor=all-TUs --format=yaml <path/to/compile_commands.json> > clangd-index.yaml
   ```
   If `clangd-indexer` is missing, run setup first (recommended), or install manually:
   - Windows: `winget install -e --id LLVM.clangd` (or `LLVM.LLVM`)
   - Linux (Debian/Ubuntu): `sudo apt-get install -y clangd clang-tools`
   Optional (recommended): set once so you do not repeat `--compile-commands` on every command:
   ```bash
   # Linux/macOS
   export COMPILE_COMMANDS_PATH=<path/to/compile_commands.json>

   # PowerShell
   $env:COMPILE_COMMANDS_PATH="<path/to/compile_commands.json>"
   ```
3. Export graph to JSON/YAML using this repo:
   ```bash
   python standalone_tools/export_code_graph_json.py <path/to/clangd-index.yaml> <path/to/project> \
     -o <path/to/code_graph.yaml>
   ```
   If `COMPILE_COMMANDS_PATH` is not set, pass `--compile-commands <path/to/compile_commands.json>`.
4. Query/search via HTTP API (no Neo4j):
   ```bash
   python -m code_graph_api <path/to/code_graph.yaml> --host 127.0.0.1 --port 8090
   ```
   Then use:
   - `GET /functions/search?q=...`
   - `GET /functions/{func_id}/callers`
   - `GET /functions/{func_id}/callees`
   - `GET /functions/{func_id}/call-graph?direction=both&depth=2`

5. Optional visualize:
   ```bash
   python standalone_tools/export_code_graph_html.py <path/to/code_graph.yaml> -o graph_vis.html --edge-types CALLS,INCLUDES
   ```

6. Optional local CLI query tools (no MCP):
   ```bash
   python standalone_tools/query_code_graph.py <path/to/code_graph.yaml> stats
   python standalone_tools/query_code_graph.py <path/to/code_graph.yaml> search "auth"
   python standalone_tools/query_code_graph.py <path/to/code_graph.yaml> query callers_of "<func_id>"
   python standalone_tools/query_code_graph.py <path/to/code_graph.yaml> traverse "<func_id>" --direction both --depth 2
   python standalone_tools/query_code_graph.py <path/to/code_graph.yaml> impact-radius src/a.c include/a.h
   ```

7. Build both YAML + SQLite DB in one command (recommended personal setup):
   ```bash
   python standalone_tools/build_graph_code.py <path/to/project> \
     --index-file <path/to/clangd-index.yaml> \
     --compile-commands <path/to/compile_commands.json> \
     --also-db
   ```
   Outputs:
   - `<path/to/project>/.clangd-graph-rag/code_graph.yaml`
   - `<path/to/project>/.clangd-graph-rag/graph.db`

8. Optional standalone SQLite `graph.db` export (if you already have YAML/JSON flow separate):
   ```bash
   python standalone_tools/export_code_graph_db.py <path/to/clangd-index.yaml> <path/to/project> \
     --compile-commands <path/to/compile_commands.json> \
     --db <path/to/project>/.clangd-graph-rag/graph.db

   python standalone_tools/crg_db_query.py --db <path/to/project>/.clangd-graph-rag/graph.db search "auth"
   python standalone_tools/crg_db_query.py --db <path/to/project>/.clangd-graph-rag/graph.db callers "<qualified_name>"
   ```

API extras (still no MCP):
- `GET /graph/stats`
- `GET /nodes/search?q=...`
- `GET /graph/query?pattern=callers_of&target=<id>`
- `GET /graph/traverse?start=<id>&direction=both&edge_type=CALLS&depth=2`
- `POST /graph/impact-radius` with body: `{"changed_files":["src/a.c","include/a.h"]}`

---

### Current Schema
Here is a simplified version of the [current neo4j schema](neo4j_simplified_schema.txt) for AI agent to use.

![Current Schema](docs/reference/neo4j_current_schema.png)

---
### A benchmark: The Linux Kernel

When building a code graph for the Linux kernel (WSL2 release) on a workstation (12 cores, 64GB RAM), it takes about ~4 hours using 10 parallel worker processes, with peak memory usage at ~32GB. Note this process does not include the LLM summary generation, so the total time (and cost) may vary based on your LLM provider. Local LLM API with Ollama is supported.

## Table of Contents
- [Quick Start (No Neo4j)](#quick-start-no-neo4j)
- [Why This Project?](#why-this-project)
- [Why Clang instead of Tree-sitter?](#why-clang-instead-of-tree-sitter)
- [Key Features & Design Principles](#key-features--design-principles)
- [Prerequisites](#prerequisites)
- [End-to-end: build the graph from scratch](#end-to-end-build-the-graph-from-scratch)
- [Primary Usage](#primary-usage)
  - [Full Graph Build](#full-graph-build)
  - [Incremental Graph Update](#incremental-graph-update)
  - [Common Options](#common-options)
- [Interacting with the Graph: MCP and Agent](#interacting-with-the-graph-ai-agent)
- [Supporting Scripts](#supporting-scripts)
- [Rebuild or Clean Up Graph](#rebuild-or-clean-up-graph)
- [Documentation & Contributing](#documentation--contributing)

## Why This Project?

For C/C++ project, Clangd language server has been very useful for developers using an IDE. The symbols in the code are represented in an intermediate data format from [Clangd-indexer](https://clangd.llvm.org/design/indexing.html) containing detailed syntactical information used by language servers for code navigation and completion. However, while powerful for IDEs, the raw index data doesn't expose the full graph structure of a codebase (e.g., the call graph, header dependence graph, macro expansion graph, etc.) or integrate the semantic understanding that Large Language Models (LLMs) can leverage.

This project fills that gap. It reconciles the Clangd index data and Clang parsing data, and ingests them into a Neo4j graph database, reconstructing the complete file, symbol, and relationship hierarchy. It then enriches this structure with AI-generated summaries and vector embeddings, transforming the raw compiler index into a semantically rich knowledge graph. In essence, `clangd-graph-rag` extends Clangd's powerful foundation into an AI-ready code graph, enabling LLMs to reason about a codebase's structure and behavior for advanced tasks like in-depth code analysis, refactoring, and automated reviewing.

Another powerful feature is that this project supports building the graphRAG incrementally, which means it can update the graph based on the diff of git commits without rebuilding the entire graph from scratch. This significantly reduces the time and cost of maintaining the graphRAG.

Note, this is an independent project and is not affiliated with the official Clang or clangd projects.

## Why Clang instead of Tree-sitter?

While Tree-sitter is an excellent tool for syntax highlighting and simple code navigation, it falls short when building a high-fidelity, semantically accurate code graph for C/C++, especially for large-scale production codebases. This project deliberately leverages Clang for several critical reasons:

*   **Macro and Preprocessor Awareness**: C/C++ development relies heavily on the preprocessor. Tree-sitter is purely syntactic and lacks a preprocessor; it cannot resolve macro expansions or track the relationship between a macro definition and the code it generates. Clang provides "causality tracking" for macro-expanded entities.
*   **Semantic Accuracy with Conditional Compilation**: In real-world code, `#ifdef` and `#else` blocks are ubiquitous. Tree-sitter often sees both branches of a conditional block simultaneously and may give dependence relationships incorrectly. Clang (using `compile_commands.json`) knows exactly which code path is actually compiled and "visible" to the compiler.
*   **Global Symbol Identity (USR)**: This project uses Unified Symbol Resolution (USR) to uniquely identify entities across the entire codebase. E.g., USRs allow the graph to link template specializations to their primary templates and resolve overloads accurately—tasks that are impossible with a file-local syntactic parser.
*   **Cross-File Semantic Integrity**: Many C/C++ constructs are fragmented across files (e.g., a struct whose fields are defined in an included header). Because Tree-sitter parses files in isolation, it cannot "see" the complete definition of such entities. Clang parses Translation Units (TUs) with full header context and preprocessing, ensuring a complete and accurate model.
*   **Compiler-Grade Fidelity**: By leveraging the same engine used for compilation, we ensure the graph reflects the code exactly as it is understood by the compiler, including complex C++ template metaprogramming and name lookup rules.

## Key Features & Design Principles

*   **AI-Enriched Code Graph**: Builds a comprehensive graph of files, folders, symbols, and function calls, then enriches it with AI-generated summaries and vector embeddings for semantic understanding.
*   **Robust Dependency Analysis**: Builds a complete graph for call chain, header inclusion, macro expansion, class specialization, and type alias relationships, enabling accurate code structure and architecture analysis.
*   **Compiler-Accurate Parsing**: Leverages `clang` via its compilation database (the `compile_commands.json` file) to parse source code with full semantic context, correctly handling complex macros and include paths.
*   **Incremental Updates**: Includes a Git-aware updater script that efficiently processes only the files changed between commits, avoiding the need for a full rebuild.
*   **AI Agent Interaction**: Provides a tool server and an example agent to allow for interactive, natural language-based exploration and analysis of the code graph.
*   **High-Performance & Memory Efficient**: Designed for performance with multi-process, multi-threaded, and asyncio coroutine parallelism, efficient batching for database operations, and intelligent memory management to handle large codebases.
*   **Modular & Reusable**: The core logic is encapsulated in modular classes and helper scripts, promoting code reuse and maintainability.

## Prerequisites
### Input file dependencies
To successfully build the graph, this project leverages the power of the LLVM ecosystem. Before starting, ensure you have the following two files ready:

1. **JSON Compilation Database (.json)**
 
    The project requires a compilation database file, usually named `compile_commands.json`, which provides the necessary compiler flags and include paths for your source code. This file is usually generated by your build system. There are usually two ways:
   - If you are using CMake, you can use the following command:
     ```
     cmake -DCMAKE_EXPORT_COMPILE_COMMANDS=ON <your_original_cmake_option>
     ```
   - If you are using Make, you can use the following command: 
     ```
     bear -- make <your_original_make_option>
     ```
   For other build system like Bazel, please refer to [LLVM original document](https://clang.llvm.org/docs/JSONCompilationDatabase.html) for more details.

   By default, the system looks for the `compile_commands.json` file in the project root. If it is elsewhere, use `--compile-commands` or set `COMPILE_COMMANDS_PATH` once in your environment. For more details on customizing paths, see the [Common Options](#common-options) section.

2. **Clangd Index File (.yaml)**

   In addition to the compilation database, you will need a static index generated by clangd-indexer （version >= 21.0.0). (If you don't have it, you can download the indexing-tools directly from the official [clangd releases](https://github.com/clangd/clangd/releases), or you can build it from [llvm source](https://github.com/llvm/llvm-project).)

   Then you can use the following command to generate the index file:
   ```
   clangd-indexer --executor=all-TUs --format=yaml <path/to/compile_commands.json> > your-clangd-index.yaml
   ```
   The `<path/to/compile_commands.json>` can be `.` (a dot) if it is in the current directory.

   By default, the system does not assume the index file is in the root of your project path. You should specify its path explicitly in command line as the first argument. For more details, see the [Primary Usage](#primary-usage) section.

### Other installation dependencies
1. **clang**
 
   The project requires a clang installed on your system (that has libclang included). Your system usually has it by default. If not, you can download it from the official [clang website](https://clang.llvm.org/)， version >= 21.0.0. (The project originally targeted clang version >= 16.x, but versions below 21.0.0 are not actively maintained.)

2. **Neo4j (optional if you only use SQLite `graph.db` query/API)**

   The project requires a Neo4j database running to store the graph data **for the Neo4j pipeline**.  
   If you only use **clangd-graph-rag** SQLite ``graph.db`` (for example ``<project>/.clangd-graph-rag/graph.db``) with `standalone_tools/crg_db_query.py` or `code_graph_api/crg_db_main.py`, you can skip this dependency.
   
   Check if your system supports neo4j in its package management (like apt). Or you can download its Desktop version (encouraged) or service version (the Community version works fine) from the official [Neo4j website](https://neo4j.com/download/), version >= 5.0.0. (I used to work with version 4.x. Not sure if it still works.) 

   The project also needs the neo4j's APOC plugin (core + extension), which can be easily installed from the Desktop version. That's why the Desktop version is suggested. If you use neo4j service version, you need download [APOC core](https://github.com/neo4j/apoc/releases) and [APOC extension](https://github.com/neo4j-contrib/neo4j-apoc-procedures/releases), and put them to your neo4j's plugins folder (mine is at /var/lib/neo4j/plugins) then restart neo4j service. Note the downloaded APOC version should match with your neo4j version. 
   
   The project by default uses the neo4j default values for its `NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD`. If you use different values, please set them in your environment variables or modify the default values in the following lines of `neo4j_manager/base.py`: 
    ```
    NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687") 
    NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4j")
    ```

   > Quick skip note: during setup, if you are not using Neo4j now, comment this block in your local checklist and continue with the SQLite-only section [7b. Query `graph.db` directly (no Neo4j)](#7b-query-graphdb-directly-no-neo4j).

3. **LLM model and its API key**

   If you want to generate summaries in the neo4j graph with LLM, you need have access to an LLM model service either remotely or locally. The project uses Litellm package to access LLM APIs, which can virtually support almost all popular LLM services. You need set environment variable for the API key for your remote LLM service, such as OPENAI_API_KEY, or DEEPSEEK_API_KEY, etc. If you want to use your specific model, you can simply add it in file `llm_client.py`, by modifying the constructor `__init__()` of the `LiteLlmClient` class. The code retrieves the max context window size from the service by default. You can also specify a window size by modifying the code there.

4. **Python**

   The project requires `Python 3.13` (or higher). 
   Actually `Python 3.11 (or higher)` is enough, if you only want to build the graphRAG and don't plan to run the example AI agent. The example agent is developed using Google ADK that requires `Python 3.13`. Then you can remove the `google-adk` dependency from the provided `requirements.txt`, and maintain your own requirements file.

## End-to-end: build the graph from scratch

This section is a single ordered checklist: from an empty machine to a populated **Neo4j** graph (the graph database used by this repo), optional HTML visualizations, and how clients connect to Neo4j.

### 1. Clone and install Python dependencies

```bash
git clone https://github.com/2015xli/clangd-graph-rag.git
cd clangd-graph-rag
   pip install -r requirements-core.txt
```

If you will not run the Google ADK example agent, you may remove the `google-adk` line from `requirements.txt` first (see [Prerequisites](#prerequisites)).

### 2. Start Neo4j and configure connection (“call into” the graph DB)

The builder and updater talk to Neo4j over the Bolt protocol.

1. Install and start **Neo4j** (Desktop or server, Community is fine), **version ≥ 5**, with the **APOC** plugin (core + extended) enabled, as described in [Prerequisites](#prerequisites).
2. Set environment variables if you are not using the defaults (`neo4j` / `neo4j`):

   ```bash
   export NEO4J_URI="bolt://localhost:7687"
   export NEO4J_USER="neo4j"
   export NEO4J_PASSWORD="<your-password>"
   ```

   Defaults are defined in `neo4j_manager/base.py` and match a typical local install.

3. Confirm the database is reachable from Neo4j Browser (usually `http://localhost:7474`) or with a trivial Cypher `RETURN 1`. The MCP server and `Neo4jManager` use the same URI and credentials.

### 3. Produce `compile_commands.json`

Your C/C++ tree must have a [JSON compilation database](https://clang.llvm.org/docs/JSONCompilationDatabase.html) at the project root (or pass `--compile-commands` later). Typical examples:

```bash
# CMake
cmake -DCMAKE_EXPORT_COMPILE_COMMANDS=ON <options> <source-dir>

# Make (with Bear)
bear -- make <your-target>
```

### 4. Build the clangd static index (YAML)

Install **clangd-indexer** (LLVM / clangd releases, version aligned with your toolchain), then from the directory that contains `compile_commands.json`:

```bash
clangd-indexer --executor=all-TUs --format=yaml . > clangd-index.yaml
```

You will pass the path to `clangd-index.yaml` as the first argument to `graph_builder.py`.

### 5. Ingest the graph into Neo4j

With Neo4j running and env vars set, run the main orchestrator (structural graph only first is recommended):

```bash
# Structural graph only (no LLM cost)
python3 graph_builder.py /absolute/path/to/clangd-index.yaml /absolute/path/to/your/project/

# Same, but also generate summaries (see --llm-api)
python3 graph_builder.py /absolute/path/to/clangd-index.yaml /absolute/path/to/your/project/ --generate-summary --llm-api fake
```

This populates Neo4j with project, file, symbol, call, include, and related nodes and relationships. Details: [Graph Builder](./docs/graph_builder.md).

Optional later step — summaries only on an existing graph:

```bash
python3 -m summary_driver /absolute/path/to/clangd-index.yaml /absolute/path/to/your/project/ --llm-api openai
```

### 6. Verify and query Neo4j

- Open **Neo4j Browser**, connect with the same user/password, and run schema or pattern queries (for example counts by label).
- From the shell you can introspect the schema:

  ```bash
  python3 -m neo4j_manager dump-schema
  ```

- Programmatic access: use `Neo4jManager` as elsewhere in the codebase, or start **`graph_mcp_server.py`** so an agent can run Cypher via MCP ([Example Workflow](#example-workflow)).

### 7. Optional visualizations (not required for Neo4j)

The primary artifact of this repo is the **Neo4j** graph. Separately, this repository ships **SQLite `graph.db` + HTML** helpers that work on exports from **clangd-graph-rag** (same ``nodes``/``edges`` layout many graph-review tools use):

| Goal | What to run |
|------|----------------|
| D3 ``graph.html`` with per-function **CALLS** (full mode) | Prefer **clangd-graph-rag** export + ``crg_visualize_full_d3.py``. If you use an external graph-review visualize pipeline, use **full** mode so function-level ``CALLS`` are not aggregated away. |
| Orange cross-file call edges in D3 | `python standalone_tools/crg_enhance_d3_html.py <path/to/graph.html> -o graph_d3.html` |
| One-step full D3 + enhancement from `graph.db` | `python standalone_tools/crg_visualize_full_d3.py --db <path/to/graph.db> -o graph_d3.html` |
| vis-network HTML from `graph.db` | `python standalone_tools/crg_db_to_vis_html.py --db <path/to/graph.db> -o calls.html` (see `--help` for `--inter-file-full` and related flags). |

These paths do **not** replace Neo4j ingestion; they are optional analysis and reporting tools. ``crg_visualize_full_d3.py`` can optionally call an external visualize package if installed; otherwise use post-process + enhance scripts on HTML you already have.

### 7b. Query `graph.db` directly (no Neo4j)

If you only want query/search on **clangd-graph-rag** SQLite ``graph.db`` (for example ``<project>/.clangd-graph-rag/graph.db``), use:

```bash
# CLI
python standalone_tools/crg_db_query.py --db <path/to/graph.db> search "wpa_auth" --limit 20
python standalone_tools/crg_db_query.py --db <path/to/graph.db> callers "src/wpa.c::wpa_init"
python standalone_tools/crg_db_query.py --db <path/to/graph.db> callees "src/wpa.c::wpa_init"
python standalone_tools/crg_db_query.py --db <path/to/graph.db> call-graph "src/wpa.c::wpa_init" --direction both --depth 2 --limit 800
```

```bash
# HTTP API (FastAPI, still no Neo4j)
python -m code_graph_api.crg_db_main <path/to/graph.db> --host 127.0.0.1 --port 8091
```

Main endpoints:
- `GET /functions/search?q=...&limit=...`
- `GET /functions/{target}/resolve`
- `GET /functions/{target}/callers`
- `GET /functions/{target}/callees`
- `GET /functions/{target}/call-graph?direction=both&depth=2&limit=800`

### 8. Incremental updates (after the first full build)

Once the graph exists in Neo4j and the project is a Git repository, use `graph_updater.py` with a fresh clangd index YAML instead of rebuilding everything. See [Incremental Graph Update](#incremental-graph-update).

## Primary Usage

**Note 1**: To build graph, please follow [the prerequisites](#prerequisites) to prepare the clang compilation database file `compile_commands.json` and the clangd index `.yaml` file, and have the neo4j server started. The examples below assume the `compile_commands.json` file is located in the root of your project path. If it is located elsewhere, specify it with `--compile-commands` or set `COMPILE_COMMANDS_PATH` (see [Common Options](#common-options)).  

**Note 2**: To generate LLM summaries for the graph, it is highly recommended to create a `project-info.md` file in the project root folder as the project context information, which is extremely useful for the LLM to have a right context. The file content can be a few words or a few paragraphs as you want, such as "This LLVM project is a collection of modular compiler and toolchain technologies."


   Before building graph for your C/C++ code, checkout a copy of the project:
   ```
   git clone https://github.com/2015xli/clangd-graph-rag.git
   cd clangd-graph-rag
   ```
   Then you need install the required packages using the following command:
   ```
   #If you don't want to run the example AI agent, you can remove the `google-adk` dependence
   pip install -r requirements-core.txt
   ```

The two main entry points of the project are the graph builder and the graph updater.
For all the scripts that can run standalone, you can always use `--help` to see the full CLI options.

### Full Graph Build

Used for the initial, from-scratch ingestion of a project. Orchestrated by `graph_builder.py`.

```bash
# Build the graph only (no LLM summary generation, which you can generate separately later)
python3 graph_builder.py /path/to/clangd-index.yaml /path/to/project/

# Build the graph with LLM summary generation (single command for both graph construction and summary generation)
python3 graph_builder.py /path/to/clangd-index.yaml /path/to/project/ --generate-summary [--llm-api [openai|deepseek|ollama|fake]]
```
* Without `--generate-summary`, the tool will only perform the graph construction phase. This is to give you an option to check the graph results before generating LLM summaries that may cost time and money.
* With `--generate-summary` enabled, the tool will generate summary. By default it will use `--llm-api fake` to test the summary generation without actually calling an LLM API. You can use `--llm-api [openai|deepseek|ollama|fake]` to specify the LLM API to use. Adding an API for your use case is super easy. Please check the `llm_client.py` file for the details. 
* The generated summaries are cached in two levels of caches, so that you don't need to regenerate them if the source code of the project remains unchanged. If you used the default `fake` llm client in previous run, and now you specify a real LLM API, the fake summaries will be removed automatically, so that your graphRAG does not have mixed fake and real summaries. 

Please check the detailed design document for more details: [Graph Builder](./docs/graph_builder.md) or go to the [Documentation](#documentation) section for a full description.

### Summary RAG Data Generation

After the graph is fully built (without --generate-summary enabled), you can generate LLM summary RAG data with the following command. If you don't specify the --llm-api, it will use the `fake` llm client for testing purpose.
```bash
python3 -m summary_driver /path/to/clangd-index.yaml /path/to/project/ --llm-api [openai|deepseek|ollama|fake]
```
Please check the detailed design document for more details: [Summary Generation](./summary_driver/README.md) or go to the [Documentation](#documentation) section for a full description.

### Incremental Graph Update

Used to efficiently update an existing graph with changes from Git. Orchestrated by `graph_updater.py`. Note graph incremental update only supports source tree that is a git repo.

```bash
# Update the graph to the current HEAD 
python3 graph_updater.py /path/to/new/clangd-index.yaml /path/to/project/ --generate-summary --llm-api [openai|deepseek|ollama|fake]

# Update between two specific commits 
python3 graph_updater.py /path/to/new/clangd-index.yaml /path/to/project/ --old-commit <hash1> --new-commit <hash2> --generate-summary --llm-api [openai|deepseek|ollama|fake]
```
Note: If your full build graph has been generated with a real LLM API, you definitely want to use a real one for the incremental update as well, to avoid the `fake` llm client polluting your graphRAG with meaningless summaries. If you accidently used the `fake` llm client, and your graphRAG is polluted, no worry. It can be simply cleaned up. Please check section [Rebuild or Clean Up Graph](#rebuild-or-clean-up-graph) on how to deal with it. 

Please check the detailed design document for more details: [Graph Updater](./docs/graph_updater.md) or go to the [Documentation](#documentation) section for a full description.

### Common Options

You can always use `--help` option to check all the available options for any script. Here is a list of commonly used options.

Both the builder, updater and other scripts accept a wide range of common arguments, which are centralized in `input_params.py`. These include:

*   **Compilation Arguments**:
    *   `--compile-commands`: Path to the `compile_commands.json` file. This file is essential for the new accurate parsing engine. By default, the tool uses `COMPILE_COMMANDS_PATH` if set; otherwise it searches for `compile_commands.json` in the project's root directory.
*   **RAG Arguments**: Control summary and embedding generation (e.g., `--generate-summary`, `--llm-api`).
*   **Worker Arguments**: Configure parallelism depends on your system resources
    *   `--num-parse-workers`: Number of parallel parsing worker processes for YAML index file and source file parsing, in case you have a large codebase with lots of files (like Linux kernel). This may need to be tuned based on your system resources. Usually set to a number close to the number of available CPU cores.
    *   `--num-remote-workers`: Number of remote worker threads for LLM API calls. This is for IO bound operation, can be set to a big number. May use coroutines in future, but threads works fine for now.
*   **Batching Arguments**: Tune performance for database ingestion (e.g., `--ingest-batch-size`, `--cypher-tx-size`).

## Interacting with the Graph: AI Agent

Once the code graph is built and enriched, you can interact with it using natural language through an AI agent. The project provides an example implementation of an MCP tool server and an agent built with the Google Agent Development Kit (ADK) to enable this.

1.  **`graph_mcp_server.py`**: This is a tool server that exposes the Neo4j graph to an AI agent. It provides example tools like `get_graph_schema`, `execute_cypher_query`, and `get_file_source_code_by_path`. They are bare minimum yet super powerful tools for AI agent to interact with the graph.
2.  **`rag_adk_agent/`**: This directory contains an example agent built with the Google Agent Development Kit (ADK). This agent is pre-configured to use the tools from the MCP server to answer questions about your codebase. It just scratches the surface of what is possible with the tools provided.
3.  **YAML/JSON export agent (no Neo4j, no MCP)**: `rag_adk_agent/export_graph_agent.py` defines `root_agent` that calls **`graph_toolkit`** as plain Python tools (`list_export_graph_tools`, `invoke_export_graph_tool`). Point **`CODE_GRAPH_YAML`** or **`GRAPH_PATH`** at `code_graph.yaml` (or JSON), set your LLM API key for LiteLLM (e.g. `DEEPSEEK_API_KEY`), then run `python rag_adk_agent/run_export_graph_agent.py --graph <path> --query "..."` or `adk run rag_adk_agent.export_graph_agent` with the same env vars. See [rag_adk_agent/README.md](rag_adk_agent/README.md).

### Example Workflow

1.  **Start the Tool Server**: In one terminal, start the server. It will connect to Neo4j and wait for agent requests.
    ```bash
    python3 graph_mcp_server.py
    ```
    It starts the MCP server at `http://0.0.0.0:8800/mcp`.

2.  **Run the Agent**: In a second terminal, run the agent. 

    By default, the agent connects the MCP server at `http://127.0.0.1:8800/mcp`, and uses LLM model `deepseek/deepseek-chat` via LiteLlm package. You can change the LLM_MODEL by setting the `LLM_MODEL` variable in the `rag_adk_agent/agent.py` file. For whatever LLM model you use, you need setup its API key per request by LiteLlm package.

    The recommended way is to use the ADK web UI.
    ```bash
    # For a web UI interaction
    adk web
    ```
    Then point to the server URL in your browser (default is `http://127.0.0.1:8000`) and select the agent `rag_adk_agent`.
    
    Or you can run it in a command-line session.
    ```bash
    # For an interactive command-line session
    adk run rag_adk_agent
    ```
    You can now ask the agent questions.

**YAML-only agent (no `graph_mcp_server.py`):** set `CODE_GRAPH_YAML` to your export, then e.g. `adk run rag_adk_agent.export_graph_agent` or `python rag_adk_agent/run_export_graph_agent.py --graph path/to/code_graph.yaml --query "Who calls foo?"`.

For more details, see the documentation for Agentic Components section in [Design Documentation](./docs/README.md#integration-and-agents).

## Supporting Scripts

These scripts are the core components of the pipeline and can also be run standalone for debugging or partial processing.

*   **`python3 -m source_parser`**:
    *   **Purpose**: Parses source code to extract function spans and include relations. Useful for AST inspection and header impact analysis.
    *   **Usage**: `python3 -m source_parser /path/to/source/`

*   **`python3 -m summary_driver`**:
    *   **Purpose**: Runs the RAG enrichment process on an *existing* graph.
    *   **Assumption**: The structural graph (files, symbols, calls) must already be populated in the database.
    *   **Usage**: `python3 -m summary_driver <index.yaml> <project_path/> --llm-api [openai|deepseek|ollama|fake]`

*   **`python3 -m summary_engine`**:
    *   **Purpose**: Manages the RAG summary cache (backup and restore).
    *   **Usage**: `python3 -m summary_engine backup`

*   **`python3 -m neo4j_manager`**:
    *   **Purpose**: A command-line utility for database maintenance.
    *   **Functionality**: Includes tools to inspect schema, clean properties, and query call graph data quickly from terminal.
    *   **Usage**:
        ```bash
        # Schema / maintenance
        python3 -m neo4j_manager dump-schema
        python3 -m neo4j_manager delete-property --label FUNCTION --key summary

        # Search (similar to export-graph query / MCP-style search)
        python3 -m neo4j_manager search "wpa_auth" --labels FUNCTION,METHOD --limit 20

        # Direct call relationships
        python3 -m neo4j_manager callers "src/wpa.c::wpa_init"
        python3 -m neo4j_manager callees "src/wpa.c::wpa_init"

        # Local call neighborhood (up/down/both)
        python3 -m neo4j_manager call-graph "src/wpa.c::wpa_init" --direction both --depth 2 --limit 800
        ```

*   **`graph_ingester/symbol.py`**:
    *   **Purpose**: Ingests the file/folder structure and symbol definitions, mainly for debugging.
    *   **Assumption**: Best run on a clean database.
    *   **Usage**: `python3 -m graph_ingester symbol <index.yaml> <project_path/>`

*   **`graph_ingester/call.py`**:
    *   **Purpose**: Dumps or ingests *only* the function call graph relationships, mainly for debugging.
    *   **Assumption**: Symbol nodes (such as `:FILE`, `:FUNCTION`) must already exist in the database.
    *   **Usage**: `python3 -m graph_ingester call <index.yaml> <project_path/> --ingest`


## Rebuild or Clean Up Graph

In this section, I will show you how to rebuild the graph or clean up the summaries. If you only want to regenerate the summaries, please check next section [Regenerate the summaries](#regenerate-the-summaries); or if you only want to clean up the fake summaries from your graph (and cache), you can check [Clean up fake summaries](#clean-up-fake-summaries).

### Rebuild the graphRAG

Graph rebuilding is not needed normally. If your project source code is not managed by git, you can rebuild the graph when the code base has changed significantly. (If it is managed by git, you can use incremental update.) Or if your graph was built with old version of clangd-graph-rag, you can rebuild it to enjoy the newly added features. 

There are two parsing cache files that you probably need to delete depending on the following cases:

1. **Index yaml parsing cache file**: If your project source code has been changed, you should regenerate the clangd index yaml file, and remove the old yaml parsing cache file that is under the same folder as the yaml file, and has the same name as the yaml file but with a different suffix .pkl. 

2. **Source code parsing cache file**: If your project source code does not change, but you want to try with new version of clangd-graph-rag, you should remove the old source parsing cache file under `<project_path>/.cache/`, with name of `parsing_<project_name>_<time_stamp>.pkl`. 

3. **Keep the cache files**: If you rebuild the graph because of other reasons (not due to project code base changes or new version of clangd-graph-rag), you don't need to remove the two parsing cache files. They can speed up your rebuilding process significantly.
 
Rebuilding your graph may not take the same time/cost as the first time graph building, because of the two parsing cache files and two-level summary caching supports. 

1. **Graph rebuilding time**: If you had a full build with your project before, and the source code has no change since then, the rebuilding of its graphRAG can be quite fast, because the previous run already caches the parsing results of the long time operations, i.e., the yaml parsing and the source parsing. It may take only several minutes to rebuild the graph with the cached results. 

2. **Summarization time/cost**: If you had used real LLM API to generate the summaries, the results are not lost in graphRAG rebuilding. They are cached by the `llm-cache` separately in the disk, managed by `llm_client.py`. So rebuilding does not increase your time or cost for summarization either.

3. **A minor consideration**: The way Clangd-indexer works may introduce some inconsistance in your graph after many times of incremental update. E.g., your project source code may have two classes of same name, while clangd-indexer will choose one "winner" to represent the class (since they have the same USR: "Unified Symbol Resolution"), but merge the other class's relationships to the "winner". Different incremental updates may choose different "winner". This is not a bug of clangd-indexer or clangd-graph-rag, but an issue in your project source code. A graph rebuilding does not solve the issue of your project source code, but it helps to keep the graph consistent with the same "winner".

#### What if the database is huge when rebuilding

Rebuilding the graph will delete existing nodes/relationships. If your graph is really big (millions of nodes/relationships like Linux kernel), it may take some time to reset the database. It is recommended to reset your database through Neo4j commands before you start the rebuilding. Please check Neo4j manual or Google a solution on how to reset it. 

What I sometimes do is to delete the database files directly with the following commands. Do _NOT_ use them unless you really know what you are doing. You need first check your Neo4j conf file (mine is /etc/neo4j/neo4j.conf) for its data path.

```
sudo systemctl stop neo4j 
sudo rm -fr <your_neo4j_data_path>/databases/neo4j/*
sudo rm -fr <your_neo4j_data_path>/transactions/neo4j/*
sudo systemctl start neo4j 
```

### Regenerate the summaries

If you don't want to rebuild your graph, but regenerate the summaries, you can do it by following the instruction in section [Summary Data Generation](#summary-rag-data-generation). We have two-level summary caching mechanism built-in, which can help you avoid regenerating summaries for unchanged code, thus saving your LLM credits. 

#### Just in case you are interested

1. **Node cache**: This is the Level-1 summary cache. When you generate summaries, the `summary_engine` will cache all the summaries in `<project_path>/.cache/summary_backup.json`. This cache is indexed by node ID (or file path for `FILE|FOLDER` nodes). It saves the `code_hash` of the node if the node is a function/method. When checking the cache validity, it compares the latest source code's hash value with the `code_hash` saved in the cache. If the function source code is modified, the cache will be invalidated and the cache has a miss. But if you only changed the prompt, the cache is still valid.

    Before calling the LLM to generate a summary, it will first check if the node cache has a valid summary for this node, and if so, it will return the cached summary. Please check the `summary_engine/node_cache.py` for more details. 

    Node cache caches summaries returned by the llm client, no matter which client it is, real or fake. So if you have used both real and fake clients to generate summaries, the node cache will contain both fake and real summaries. If you don't want to use the fake summaries, you can simply delete the entire cache file (see **LLM cache** below for why this is fine); or if you like, you can just remove the fake summaries in a surgical way.  

    For more details, please check the documentation for [Summary Engine](./summary_engine/README.md).

2. **LLM cache**: This is the Level-2 summary cache. When the summarizer has a cache miss in the Level-1 cache, it will issue an LLM request. The LLM client caches all the responses from real LLMs in `llm cache`, bypassing the responses from the fake client. The cache is indexed by the hash value of prompts. If the same prompt is issued again, the cached response will be returned. If your project source code has no change, but you changed the prompt, the `llm cache` will become invalid.

    This design ensures the `llm cache` has only real summaries. That means, all your real summaries won't be lost, even if you delete the Level-1 cache file at `<project_path>/.cache/summary_backup.json`. Of course you can also delete this Level-2 llm cache at `<project_path>/.cache/llm_cache/` if you want to start fresh. For example, you want to use a different LLM model, but usually you don't need to do that. 

    The llm cache is built with `diskcache (fanout)`, which is based on `sqlite`. The `fanout` configuration improves the concurrency performance. You can access its contents with sqlite tools like `sqlitebrowser` to view and edit the contents.

    For more details, please check the documentation for [LLM Client](./docs/llm_client.md).

3. **Why two levels of caches** As mentioned above, the node cache is valid as long as the source code is not modified, while the llm cache is valid only if the whole prompt matches. The node cache has both fake and real summaries, and the llm cache has only the real summaries. They can be used for different purposes. The node cache can be used to develop out-of-graph RAG systems; the llm cache can be shared by different projects if they point to the same cache folder.

### Clean up fake summaries

If your graph has mixed summaries of fake and real LLM API, you don't really need to do anything, because the system will clean them up automatically whenever you generate summaries with real LLM API. The system uses the following command to clean up the fake summaries automatically for you. You can also execute it manually.

```bash
python3 -m summary_engine clean-fakes
```

This will surgically remove fake content from both the Neo4j graph database and the summary cache, leaving you a clean graph and cache that have only real summaries.

#### What it really does

Here is what it really does:

1. **Delete the fake summary property from Neo4j**:
    ```bash
    python3 -m neo4j_manager delete-property --key fake_summary --all-labels --rebuild-indices
    ```

2. **Delete the fake summaries in the L1 summary cache (node cache)**:
    Fake summary can be cached in the file at `<project_path>/.cache/summary_cache.json`. You can manually delete the fake summaries from this file.
    ```bash
    python3 -m summary_engine clean-fake-cache
    ```
    You don't need to clean up the L2 summary cache (llm cache), because it only caches real LLM responses.

## Documentation & Contributing

### Documentation

Detailed design documents for each component can be found at [docs/README.md](docs/README.md) under [docs/](docs/) folder. 
For a comprehensive overview of the project's architecture, design principles, and pipelines, please refer to [docs/Building_an_AI-Ready_Code_Graph_RAG_based_on_Clangd_index.md](docs/Building_an_AI-Ready_Code_Graph_RAG_based_on_Clangd_index.md).

### Contributing

Contributions are welcome! This includes bug reports, feature requests, and pull requests. Feel free to try `clangd-graph-rag` on your own `clang` built projects and share your feedback.

### Future Work

The support to C/C++ is basically done. For next steps, we can focus on:
- Support data-dependence relationships. (What?!)
- Support to merge multiple projects into one graph.

## License

This project is licensed under the Apache License 2.0.
