# Claude Code With Ollama: Beginner Step-by-Step Guide

![Claude Code with Ollama beginner setup guide thumbnail](claude-code-ollama-thumbnail.png)

This guide shows how to run Claude Code through Ollama so you can use local models from the Claude Code terminal tool.

Sources used:

- Official Ollama guide: [Claude Code - Ollama Docs](https://docs.ollama.com/integrations/claude-code)
- Official Ollama announcement: [Claude Code with Anthropic API compatibility](https://registry.ollama.ai/blog/claude)

## What You Are Setting Up

Normally, Claude Code talks to Anthropic's Claude API.

With Ollama, Claude Code can instead talk to Ollama's Anthropic-compatible API:

```text
Claude Code -> Ollama -> Local model
```

This means you can use models such as `qwen3.5`, `qwen3-coder`, or `gpt-oss:20b`, depending on what your computer can run.

## Before You Start

You need:

- A Windows, macOS, or Linux computer
- Internet connection for installation and model downloads
- Terminal access:
  - Windows: PowerShell
  - macOS/Linux: Terminal
- Enough RAM and storage for local models

## Step 1: Install Ollama

1. Go to the Ollama download page:

   <https://ollama.com/download>

2. Download Ollama for your operating system.

3. Install it like a normal app.

4. Open your terminal and check that Ollama works:

```bash
ollama --version
```

If you see a version number, Ollama is installed.

## Step 2: Install Claude Code

Install Claude Code using the command for your operating system.

### Windows PowerShell

```powershell
irm https://claude.ai/install.ps1 | iex
```

### macOS, Linux, or WSL

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

After installation, check that Claude Code works:

```bash
claude --version
```

If you see a version number, Claude Code is installed.

## Step 3: Try the Easy Ollama Launcher

The simplest way is to let Ollama launch Claude Code for you:

```bash
ollama launch claude
```

Ollama may ask you to choose or download a model.

If you already know which model you want, run:

```bash
ollama launch claude --model qwen3.5
```

## Step 4: Choose a Model

Good beginner options:

| Model         | Notes                                           |
| ------------- | ----------------------------------------------- |
| `qwen3.5`     | Good general option if your computer can run it |
| `qwen3-coder` | Better for coding tasks                         |
| `gpt-oss:20b` | Recommended by Ollama for coding use cases      |

These models run locally on your computer.

## Step 5: Use Claude Code in a Project Folder

Open a terminal inside the folder of the project you want to work on.

Example:

```bash
cd path/to/your/project
ollama launch claude --model qwen3.5
```

Then ask Claude Code something simple:

```text
Explain this project in simple terms.
```

Or:

```text
Find bugs in this codebase, but do not edit files yet.
```

## Step 6: Manual Setup Option

If `ollama launch claude` does not work, you can manually point Claude Code to Ollama.

### macOS, Linux, or WSL

```bash
export ANTHROPIC_AUTH_TOKEN=ollama
export ANTHROPIC_API_KEY=""
export ANTHROPIC_BASE_URL=http://localhost:11434
claude --model qwen3.5
```

### Windows PowerShell

```powershell
$env:ANTHROPIC_AUTH_TOKEN="ollama"
$env:ANTHROPIC_API_KEY=""
$env:ANTHROPIC_BASE_URL="http://localhost:11434"
claude --model qwen3.5
```

These variables tell Claude Code to use Ollama instead of the default Anthropic API.

## Step 7: Run a One-Time Prompt

You can run Claude Code without opening the full interactive chat.

Example:

```bash
ollama launch claude --model qwen3.5 --yes -- -p "Explain how this repository works."
```

This is useful for quick checks or scripts.

## Common Problems

### `claude` command is not found

Claude Code may not be installed correctly, or your terminal path may not be updated.

Try closing and reopening your terminal, then run:

```bash
claude --version
```

### Ollama is not running

Start Ollama from your apps menu, or run:

```bash
ollama serve
```

Then try again.

### The model is too slow

Use a smaller local model, or pick a lighter option from the model list when Ollama prompts you.

### Claude Code forgets too much context

Claude Code works best with models that support a large context window. Ollama recommends using at least 32K tokens, and its Claude Code guide mentions 64K tokens for best results.

## Beginner Tips

- Start with small requests.
- Ask Claude Code to explain before editing.
- Review file changes before accepting them.
- Use Git so you can undo mistakes.
- Local models keep your requests on your computer.

## Quick Command Summary

Install Claude Code on Windows:

```powershell
irm https://claude.ai/install.ps1 | iex
```

Install Claude Code on macOS/Linux:

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

Run Claude Code with Ollama:

```bash
ollama launch claude
```

Run with a specific model:

```bash
ollama launch claude --model qwen3.5
```

Manual setup:

```bash
export ANTHROPIC_AUTH_TOKEN=ollama
export ANTHROPIC_API_KEY=""
export ANTHROPIC_BASE_URL=http://localhost:11434
claude --model qwen3.5
```

## Simple Recommended Path

If you are a beginner, follow this order:

1. Install Ollama.
2. Install Claude Code.
3. Open your project folder in the terminal.
4. Run:

```bash
ollama launch claude
```

5. Choose a model.
6. Ask Claude Code to explain the project before asking it to edit anything.
