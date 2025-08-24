# Code Style and Conventions

## Python Code Standards (Receiver)

### Core Requirements
- **Type hints**: Required for all code (functions, methods, variables)
- **Docstrings**: Required for all public APIs
- **Line length**: 88 characters maximum
- **Functions**: Must be focused and small
- **Patterns**: Follow existing patterns exactly

### Formatting and Linting
- **Ruff**: Primary formatter and linter
- **Line wrapping**: 
  - Strings: use parentheses `("long string " "continued")`
  - Function calls: multi-line with proper indentation
  - Imports: split into multiple lines when long

### Type Checking
- **Tool**: pyright (strict mode)
- **Requirements**:
  - Explicit None checks for Optional types
  - Type narrowing for strings and unions
  - Proper function signature matching

### Import Organization
- Standard library imports first
- Third-party imports second  
- Local imports last
- Sort within each group
- Use `from` imports judiciously

### Error Handling
- Use specific exception types
- Handle async operation errors
- Provide meaningful error messages
- Log errors appropriately

### Async Code
- Use `anyio` for testing, not `asyncio`
- Proper async context manager usage
- Handle cancellation gracefully
- Use typed async generators where appropriate

### Testing
- Framework: pytest with anyio plugin
- Coverage: test edge cases and error conditions
- New features require tests
- Bug fixes require regression tests

## C++ Code Standards (Sender)

### PlatformIO/Arduino
- Follow Arduino-style naming conventions
- Use proper header guards
- Minimize memory allocations
- Handle sensor errors gracefully
- Use appropriate data types for sensor values

## Documentation Standards

- README files for each component
- CLAUDE.md files for development guidance  
- Inline comments for complex algorithms
- Type hints serve as primary documentation for parameters