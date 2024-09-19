# CODAI - Coding Evolved

CODAI is a revolutionary system designed to evolve the art and science of coding. It leverages the power of the Anthropic Claude API to provide intelligent responses, perform various project-related tasks, and push the boundaries of software development.

## Features

- Interactive conversation with an AI assistant specialized in coding and software engineering
- File and project structure analysis
- Code reading and creation capabilities
- Intelligent code editing and suggestions
- Project study and comprehensive analysis
- Cache performance metrics and visualization

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/codai.git
   cd codai
   ```

2. Create and activate the virtual environment:
   ```
   python -m venv sandbox_env
   source sandbox_env/bin/activate  # On Windows, use `sandbox_env\Scripts\activate`
   ```

3. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Set up your configuration:
   - Copy the `.env.example` file to `.env`:
     ```
     cp .env.example .env
     ```
     (Note: A temporary config.yaml is currently being used)
   - Edit the `.env` file and add your Anthropic API key

5. Configure the `config.yaml` file with your preferred settings

## Usage

To start CODAI, ensure you're in the project directory and your virtual environment is activated, then run:

```
python codai.py
```

Once started, you can interact with CODAI using various commands:

- `/help`: Show the help message with available commands
- `/clear`: Clear the screen
- `/list files [path]`: List files in the specified path
- `/context files`: List files currently in the context
- `/read <filename>`: Display the contents of the specified file
- `/read folder [path] [subfolders]`: Read and display contents of all files in the specified folder
- `/create file <path> <content>`: Create a new file with the specified content
- `/create folder <path>`: Create a new folder at the specified path
- `/project structure [path] [options]`: Display the project structure
- `/project study [path] [include-ignored] [output=<filename>]`: Analyze project structure and create a detailed JSON report
- `/exit`: End the conversation and exit CODAI

For any other input, CODAI will interpret it as a question or task related to your project.

## Dependencies

CODAI relies on the following main libraries:

- anthropic
- PyYAML
- colorama
- rich
- matplotlib

For a complete list of dependencies, please refer to the `requirements.txt` file.

## Contributing

Contributions to CODAI are welcome! Please feel free to submit pull requests, create issues or spread the word.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Acknowledgements

CODAI is powered by the Anthropic Claude API and various open-source libraries. We thank all the contributors and maintainers of these projects.