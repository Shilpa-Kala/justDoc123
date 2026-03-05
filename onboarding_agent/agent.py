#!/usr/bin/env python3
"""
Project Onboarding Agent
========================
Uses Claude (claude-opus-4-6) with tool use to automatically generate
a full project skeleton and boilerplate code based on the project type:
  - Python Web  (Flask / FastAPI / Django)
  - Java Web    (Spring Boot / Maven)
"""

import os
import sys
import json
import textwrap
from pathlib import Path

import anthropic
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.text import Text
from rich.tree import Tree

# ── CLI helpers ──────────────────────────────────────────────────────────────
console = Console()

def banner():
    console.print(Panel(
        Text("Project Onboarding Agent", style="bold cyan", justify="center"),
        subtitle="Powered by Claude claude-opus-4-6",
        border_style="cyan",
    ))

# ── Tool implementations ──────────────────────────────────────────────────────

def create_directory(path: str, base_dir: str) -> str:
    """Create a directory (and any parents) relative to base_dir."""
    full = Path(base_dir) / path
    full.mkdir(parents=True, exist_ok=True)
    return f"Directory created: {path}"


def create_file(path: str, content: str, base_dir: str) -> str:
    """Write content to a file relative to base_dir, creating parents as needed."""
    full = Path(base_dir) / path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    return f"File created: {path} ({len(content)} bytes)"


def list_created_files(base_dir: str) -> str:
    """Return a tree of all files created so far."""
    lines = []
    root = Path(base_dir)
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        indent = "  " * (len(rel.parts) - 1)
        icon = "📁" if p.is_dir() else "📄"
        lines.append(f"{indent}{icon} {rel.name}")
    return "\n".join(lines) if lines else "(empty)"


# ── Tool schemas (JSON Schema format) ────────────────────────────────────────

TOOLS = [
    {
        "name": "create_directory",
        "description": (
            "Create a directory (and all required parent directories) inside the "
            "project output folder. Use this before creating files in that directory."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path of the directory to create, e.g. 'src/main/java/com/example'",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "create_file",
        "description": (
            "Create a file with the given content inside the project output folder. "
            "Parent directories are created automatically. "
            "Provide complete, production-ready file content."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative file path, e.g. 'src/app.py' or 'pom.xml'",
                },
                "content": {
                    "type": "string",
                    "description": "Full file content (UTF-8 text)",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_created_files",
        "description": (
            "List all files and directories created so far in the project. "
            "Useful for verifying progress before finishing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]

# ── System prompt ─────────────────────────────────────────────────────────────

def build_system_prompt(project_type: str, framework: str, project_name: str, package: str) -> str:
    return textwrap.dedent(f"""
        You are an expert software architect and project scaffolding assistant.

        Your task is to generate a complete, production-ready project skeleton for:
          - Project name  : {project_name}
          - Project type  : {project_type}
          - Framework     : {framework}
          - Base package  : {package}

        ## Instructions

        1. Use the `create_directory` tool to create every directory you need.
        2. Use the `create_file` tool to create every file with its FULL content.
        3. Cover ALL of the following (adapt to the framework):
           - Project configuration / build files (requirements.txt / pom.xml / build.gradle)
           - Application entry point with a running "Hello World" HTTP endpoint
           - At least one model / entity class
           - At least one service / business-logic class
           - At least one controller / route handler with CRUD stubs
           - A repository / DAO layer (in-memory or JPA stubs)
           - Unit test scaffolding for the service layer
           - Environment / properties configuration file
           - A comprehensive README.md explaining how to run the project
           - .gitignore tuned for the language/framework
        4. Write idiomatic, well-commented code following best practices.
        5. When finished, call `list_created_files` to confirm the structure,
           then end your turn with a short summary of what was created.

        Do NOT ask for clarification — proceed directly with scaffolding.
    """).strip()


# ── Agentic loop ──────────────────────────────────────────────────────────────

def run_agent(project_type: str, framework: str, project_name: str,
              package: str, output_dir: str) -> None:

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    system = build_system_prompt(project_type, framework, project_name, package)
    user_msg = (
        f"Please scaffold the '{project_name}' {project_type} project using {framework}. "
        f"Base package/namespace: {package}. "
        f"Generate all files now."
    )

    messages = [{"role": "user", "content": user_msg}]

    console.print(f"\n[bold green]Starting agent …[/bold green]  Output → [cyan]{output_dir}[/cyan]\n")

    iteration = 0
    max_iterations = 30  # guard against runaway loops

    while iteration < max_iterations:
        iteration += 1

        # Stream so long generation doesn't time out
        with client.messages.stream(
            model="claude-opus-4-6",
            max_tokens=8192,
            thinking={"type": "adaptive"},
            system=system,
            tools=TOOLS,
            messages=messages,
        ) as stream:
            response = stream.get_final_message()

        # Append assistant turn
        messages.append({"role": "assistant", "content": response.content})

        # Check stop reason
        if response.stop_reason == "end_turn":
            console.print("\n[bold green]✔ Agent finished.[/bold green]")
            break

        if response.stop_reason != "tool_use":
            console.print(f"[yellow]Unexpected stop_reason: {response.stop_reason}[/yellow]")
            break

        # Process tool calls
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                # Print any text the model emits before tool calls
                if hasattr(block, "text") and block.text:
                    console.print(f"[dim]{block.text}[/dim]")
                continue

            tool_name = block.name
            tool_input = block.input
            console.print(f"  [bold yellow]⚙  {tool_name}[/bold yellow]  {json.dumps(tool_input)[:120]}")

            try:
                if tool_name == "create_directory":
                    result = create_directory(tool_input["path"], output_dir)
                elif tool_name == "create_file":
                    result = create_file(tool_input["path"], tool_input["content"], output_dir)
                elif tool_name == "list_created_files":
                    result = list_created_files(output_dir)
                else:
                    result = f"Unknown tool: {tool_name}"
            except Exception as exc:
                result = f"Error: {exc}"

            console.print(f"  [green]  → {result[:120]}[/green]")

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result,
            })

        # Feed results back
        messages.append({"role": "user", "content": tool_results})

    else:
        console.print("[red]Reached max iterations limit.[/red]")

    # Print final tree
    _print_tree(output_dir, project_name)


def _print_tree(base_dir: str, project_name: str) -> None:
    root = Path(base_dir)
    tree = Tree(f"[bold cyan]{project_name}/[/bold cyan]")

    def _add(node, path: Path):
        for child in sorted(path.iterdir()):
            if child.name.startswith(".") and child.name not in {".gitignore", ".env"}:
                continue
            if child.is_dir():
                branch = node.add(f"[bold blue]{child.name}/[/bold blue]")
                _add(branch, child)
            else:
                node.add(f"[green]{child.name}[/green]")

    _add(tree, root)
    console.print("\n")
    console.print(Panel(tree, title="[bold]Generated Project Structure[/bold]", border_style="green"))


# ── User interaction ──────────────────────────────────────────────────────────

PROJECT_TYPES = {
    "1": ("Python Web", ["Flask", "FastAPI", "Django"]),
    "2": ("Java Web",   ["Spring Boot (Maven)", "Spring Boot (Gradle)"]),
}

def choose_project_config() -> tuple[str, str, str, str]:
    console.print("\n[bold]Select project type:[/bold]")
    console.print("  [cyan]1[/cyan]  Python Web")
    console.print("  [cyan]2[/cyan]  Java Web")

    choice = Prompt.ask("Enter choice", choices=["1", "2"])
    project_type, frameworks = PROJECT_TYPES[choice]

    console.print(f"\n[bold]Select framework for {project_type}:[/bold]")
    for i, fw in enumerate(frameworks, 1):
        console.print(f"  [cyan]{i}[/cyan]  {fw}")

    fw_idx = Prompt.ask("Enter choice", choices=[str(i) for i in range(1, len(frameworks) + 1)])
    framework = frameworks[int(fw_idx) - 1]

    project_name = Prompt.ask("\n[bold]Project name[/bold]", default="my-app")
    project_name = project_name.strip().replace(" ", "-").lower()

    if project_type == "Python Web":
        default_pkg = project_name.replace("-", "_")
    else:
        default_pkg = f"com.example.{project_name.replace('-', '')}"

    package = Prompt.ask("[bold]Base package / namespace[/bold]", default=default_pkg)

    return project_type, framework, project_name, package


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print("[red]Error:[/red] ANTHROPIC_API_KEY environment variable is not set.")
        sys.exit(1)

    banner()
    project_type, framework, project_name, package = choose_project_config()

    default_output = str(Path.cwd() / "generated" / project_name)
    output_dir = Prompt.ask("\n[bold]Output directory[/bold]", default=default_output)

    if Path(output_dir).exists():
        overwrite = Confirm.ask(
            f"[yellow]Directory '{output_dir}' already exists. Overwrite?[/yellow]"
        )
        if not overwrite:
            console.print("Aborted.")
            sys.exit(0)

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    console.print(Panel(
        f"[bold]Project type:[/bold] {project_type}\n"
        f"[bold]Framework   :[/bold] {framework}\n"
        f"[bold]Name        :[/bold] {project_name}\n"
        f"[bold]Package     :[/bold] {package}\n"
        f"[bold]Output      :[/bold] {output_dir}",
        title="Configuration",
        border_style="blue",
    ))

    run_agent(project_type, framework, project_name, package, output_dir)

    console.print(f"\n[bold green]Done![/bold green]  Your project is at: [cyan]{output_dir}[/cyan]")


if __name__ == "__main__":
    main()
