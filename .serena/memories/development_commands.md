# Development Commands and Tools

## Sender (Firmware) Commands

```bash
cd sender/
pio run                    # Build firmware
pio run -t upload         # Upload to device (requires DFU mode)
pio device monitor -b 115200  # Monitor serial output
```

## Receiver (Python) Commands

### Package Management (CRITICAL: ONLY use uv, NEVER pip)
```bash
cd receiver/
uv sync                   # Install dependencies
uv add package            # Add new dependency
uv run tool               # Run any tool
uv add --dev package --upgrade-package package  # Upgrade packages
```

### Application
```bash
uv run xiao-nrf52840-sense-receiver --no-header --drop-missing-audio
```

### Development Tools
```bash
# Code Quality (MUST run before commits)
uv run --frozen ruff format .     # Format code
uv run --frozen ruff check .      # Check linting
uv run --frozen ruff check . --fix # Fix linting issues
uv run --frozen pyright           # Type checking

# Testing
uv run --frozen pytest            # Run tests
PYTEST_DISABLE_PLUGIN_AUTOLOAD="" uv run --frozen pytest  # If anyio issues

# Pre-commit hooks
uv run pre-commit install         # Setup hooks
uv run pre-commit run --all-files # Run manually
```

## System Commands (Darwin/macOS)

```bash
ls                        # List files
cd directory              # Change directory
grep pattern files        # Search in files
find . -name pattern      # Find files
git status                # Git status
git add .                 # Stage changes
git commit -m "message"   # Commit changes
```

## Project Commands

```bash
# Activate project in Serena
/serena activate project-path

# Common development workflow
cd receiver/
uv sync
uv run --frozen ruff format .
uv run --frozen ruff check . --fix
uv run --frozen pyright
uv run --frozen pytest
```
