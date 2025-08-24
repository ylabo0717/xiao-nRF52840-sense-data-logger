# Task Completion Checklist

## Before Committing Code

### Code Quality (MANDATORY)
1. **Format code**: `uv run --frozen ruff format .`
2. **Fix linting**: `uv run --frozen ruff check . --fix`
3. **Type checking**: `uv run --frozen pyright` (must pass)
4. **Run tests**: `uv run --frozen pytest`

### Pre-commit Validation
- Pre-commit hooks should run automatically on commit
- If hooks fail, fix issues and recommit
- Check that both Ruff and type checking pass

## For New Features

### Implementation Requirements
- [ ] Type hints for all new code
- [ ] Docstrings for public APIs
- [ ] Follow existing code patterns
- [ ] Error handling implemented
- [ ] Thread safety considered (for async/BLE code)

### Testing Requirements
- [ ] Unit tests for new functionality
- [ ] Integration tests if applicable
- [ ] Edge case testing
- [ ] Error condition testing
- [ ] Async testing with anyio (not asyncio)

### Documentation
- [ ] Update README if user-facing changes
- [ ] Update CLAUDE.md if development process changes
- [ ] Add inline comments for complex logic

## For Bug Fixes

### Analysis and Testing
- [ ] Root cause identified and documented
- [ ] Regression test added to prevent reoccurrence
- [ ] Fix tested in isolation
- [ ] No side effects introduced

### Git Commit Guidelines
- [ ] Descriptive commit message
- [ ] Add trailers for user reports: `git commit --trailer "Reported-by:<name>"`
- [ ] Add GitHub issue reference: `git commit --trailer "Github-Issue:#<number>"`
- [ ] NEVER mention co-authored-by or AI tools

## Pull Request Requirements

### Content
- [ ] Detailed description of changes
- [ ] High-level problem description and solution approach
- [ ] Avoid code-level details unless they add clarity
- [ ] Add `jerome3o-anthropic` and `jspahrsummers` as reviewers

### Quality Gates
- [ ] All CI checks passing
- [ ] No merge conflicts
- [ ] Code review completed
- [ ] Documentation updated if needed

## Deployment/Release

### Python Package (Receiver)
- [ ] Version bump in pyproject.toml if needed
- [ ] Dependencies properly pinned
- [ ] uv.lock updated and committed

### Firmware (Sender)
- [ ] Build successful: `pio run`
- [ ] Upload tested: `pio run -t upload`
- [ ] Serial monitoring functional: `pio device monitor -b 115200`

## Emergency Fixes

### CI Failures
1. **Fix order**: Formatting → Type errors → Linting → Tests
2. **Type errors**: Get full context, check Optional types, add narrowing
3. **Common issues**: Line length, unused imports, missing type annotations

### Quick Recovery
- Use `uv run --frozen` for all tool commands
- Check git status before making changes
- Keep changes minimal and focused
- Test thoroughly before committing