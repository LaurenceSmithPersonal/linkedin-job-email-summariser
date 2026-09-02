# linkedin-job-email-summariser
Workflow to read LinkedIn job emails, extract useful fields, and de-duplicate them into a local JSON file.

Python is the preferred programming language for this project. 

## Python Guidelines:
- Please follow the PEP 8 style guide for Python code. Use 4 spaces per indentation level, and limit lines to 79 characters.  
- Use descriptive variable names  
- Include docstrings for all functions and classes. Docstrings should follow the PEP 257 conventions and use the Google style.  
- Avoid using global variables and keep functions small and focused on a single task. Use list comprehensions and generator expressions where appropriate, and prefer built-in functions over custom implementations.  
- For new projects, use python version 3.14 unless instructed otherwise.  
- Use typehints for all function parameters and return types. Use the typing module for complex types.  
- Use comments to explain non-obvious code, but avoid redundant comments that simply restate the code.  
- Comments should also explain why a particular approach was taken, especially if it is not immediately clear from the code itself.  
- Always check code syntax for external libraries against the version that is being used by the code as specified using 'uv pip list' to avoid using deprecated or removed features or features from newer versions.  
- Minimize Scope of Change  
  - Implement the smallest possible change that satisfies the request.  
  - Do not modify unrelated code or refactor for style unless explicitly asked.  
 
### Package Management:
- For new projects use virtual environments to manage dependencies.  
- Use 'uv' for all package management tasks and for running scripts.  

### Testing:
- Use pytest for testing. Write unit tests for all functions and classes, and aim for high test coverage. Use fixtures to set up test data and avoid hardcoding values in tests.  
- Use mock objects to isolate tests and avoid dependencies on external systems.  
- Run tests frequently during development  
