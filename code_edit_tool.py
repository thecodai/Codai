import json
import logging
import re
import time
import random
from typing import Dict, Any, List, Union, Tuple, Callable
from functools import wraps
from anthropic import Anthropic
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
import difflib

# Initialize logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize console for rich output
console = Console()

def retry_with_backoff(retries: int = 3, backoff_in_seconds: int = 1) -> Callable:
    def rwb(f: Callable) -> Callable:
        @wraps(f)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            x = 0
            while True:
                try:
                    return f(*args, **kwargs)
                except Exception as e:
                    if x == retries:
                        raise
                    sleep = (backoff_in_seconds * 2 ** x + 
                             random.uniform(0, 1))
                    time.sleep(sleep)
                    x += 1
        return wrapper
    return rwb

def parse_search_replace_blocks(response_text: str) -> List[Dict[str, Union[str, Dict[str, str]]]]:
    """
    Parse the AI response to extract SEARCH/REPLACE blocks from JSON.
    
    Args:
        response_text (str): The raw response text from the AI.
    
    Returns:
        List[Dict[str, Union[str, Dict[str, str]]]]: A list of parsed instructions or error dictionaries.
    """
    def extract_json(text: str) -> str:
        """Extract JSON object or array from a string."""
        json_match = re.search(r'(\{|\[).*?(\}|\])', text, re.DOTALL)
        return json_match.group(0) if json_match else text

    def safe_loads(json_str: str) -> Any:
        """Safely load JSON string, handling potential issues."""
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # If it fails, try to extract a valid JSON subset
            extracted = extract_json(json_str)
            return json.loads(extracted)

    try:
        # Remove outer quotes and cleanup the string
        cleaned_text = response_text.strip("'").strip('"').strip()
        
        # Attempt to parse the JSON
        parsed_data = safe_loads(cleaned_text)
        
        # Handle different potential structures
        if isinstance(parsed_data, dict) and "edit_instructions" in parsed_data:
            instructions = parsed_data["edit_instructions"]
        elif isinstance(parsed_data, list):
            instructions = parsed_data
        else:
            instructions = [parsed_data]  # Treat as a single instruction
        
        # Validate and clean instructions
        valid_instructions = []
        for idx, instruction in enumerate(instructions):
            if isinstance(instruction, dict) and 'search' in instruction and 'replace' in instruction:
                valid_instructions.append({
                    'search': str(instruction['search']),
                    'replace': str(instruction['replace'])
                })
            else:
                logger.warning(f"Skipping invalid instruction at index {idx}: {instruction}")
        
        if not valid_instructions:
            logger.error("No valid instructions found in the response")
            return [{"error": "NO_VALID_INSTRUCTIONS", "message": "No valid instructions found in the response"}]
        
        return valid_instructions

    except Exception as e:
        logger.error(f"Error parsing search/replace blocks: {str(e)}", exc_info=True)
        return [{"error": "PARSING_ERROR", "message": str(e)}]

@retry_with_backoff(retries=3)
def generate_edit_instructions(client: Anthropic, file_path: str, file_content: str, instructions: str, project_context: str, config: Dict[str, Any]) -> List[Dict[str, str]]:
    """Generate edit instructions using the Anthropic API with added robustness."""
    if not all([file_path, file_content, instructions, project_context]):
        raise ValueError("Missing required input for generating edit instructions")

    try:
        prompt = f"""
        You are an AI coding agent that generates edit instructions for code files in any programming language. Your task is to analyze the provided code and generate edit instructions in JSON format. Follow these steps:

        1. Review the entire file content to understand the context and identify the programming language used:
        {file_content}

        2. Carefully analyze the specific instructions:
        {instructions}

        3. Take into account the overall project context:
        {project_context}

        Generate a JSON array of edit instructions. Each instruction should be an object with "search" and "replace" keys. The values should be the exact code to search for and replace, including proper indentation and language-specific syntax.

        Your response should be in the following format:
        {{
        "edit_instructions": [
            {{
                "search": "code to search for",
                "replace": "code to replace with"
            }},
            ...
        ]
        }}

        If no changes are needed, return an empty array:
        {{
        "edit_instructions": []
        }}

        Ensure that your search and replace blocks:
        - Preserve the correct syntax of the programming language used in the file
        - Maintain proper indentation and formatting
        - Include enough context to uniquely identify the code to be changed
        - Respect language-specific conventions and best practices

        Do not include any explanatory text outside the JSON structure in your response.
        """

        response = client.messages.create(
            model=config.get("model_name", "claude-3-5-sonnet-20240620"),
            max_tokens=config.get("max_tokens", 8192),
            system=prompt,
            messages=[
                {"role": "user", "content": "Generate edit instructions based on the provided content and instructions."}
            ],
            temperature=0.5,
            extra_headers=config.get("anthropic_headers", {})
        )
        
        if not response.content:
            logger.error("Empty response from API")
            return [{"error": "EMPTY_RESPONSE", "message": "Received empty response from API"}]
        
        edit_instructions = parse_search_replace_blocks(response.content[0].text)
        
        # Log metrics
        logger.info(f"Generated {len(edit_instructions)} edit instructions for {file_path}")
        
        return edit_instructions

    except Exception as e:
        logger.error(f"Error in generate_edit_instructions: {str(e)}", exc_info=True)
        return [{"error": "GENERATION_ERROR", "message": str(e)}]

def apply_edits(file_path: str, edit_instructions: List[Dict[str, str]], original_content: str) -> Tuple[str, bool]:
    """Apply the edit instructions to the file content."""
    edited_content = original_content
    changes_made = False

    for edit in edit_instructions:
        if 'error' in edit:
            logger.error(f"Error in edit instruction: {edit['error']} - {edit['message']}")
            continue

        search_content = edit['search']
        replace_content = edit['replace']

        if search_content in edited_content:
            edited_content = edited_content.replace(search_content, replace_content)
            changes_made = True

            # Display the diff for this edit
            diff = generate_diff(search_content, replace_content, file_path)
            console.print(Panel(diff, title=f"Changes in {file_path}", expand=False))
        else:
            logger.warning(f"Search content not found in {file_path}: {search_content[:50]}...")

    return edited_content, changes_made

def generate_diff(original: str, new: str, path: str) -> str:
    """Generate a diff between original and new content."""
    diff = list(difflib.unified_diff(
        original.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        n=3
    ))
    return ''.join(diff)

def get_user_approval(path: str, edit_instructions: List[Dict[str, str]], config: Dict[str, Any]) -> bool:
    """
    Display proposed changes and ask for user approval.
    
    Args:
        path (str): The file path being edited.
        edit_instructions (List[Dict[str, str]]): List of edit instructions.
        config (Dict[str, Any]): Configuration settings.

    Returns:
        bool: True if user approves, False otherwise.
    """
    if not config.get("interactive_mode", True):
        return True

    console.print(f"\nProposed changes for {path}:")
    for edit in edit_instructions:
        if 'error' in edit:
            console.print(f"[bold red]Error: {edit['error']} - {edit['message']}[/bold red]")
        else:
            console.print(Panel(Syntax(edit['search'], "python", theme="monokai"), title="Original"))
            console.print(Panel(Syntax(edit['replace'], "python", theme="monokai"), title="Proposed Change"))
    
    console.show_cursor()
    approval = console.input("[bold yellow]Do you approve these changes? (yes/no): [/bold yellow]")
    return approval.lower() == "yes"

def process_file(client: Anthropic, file: Dict[str, Any], project_context: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process a single file for editing.
    """
    try:
        path = file['path']
        instructions = file['instructions']
        original_content = file['content']

        # Generate edit instructions
        edit_instructions = generate_edit_instructions(client, path, original_content, instructions, project_context, config)

        if edit_instructions and not any('error' in instruction for instruction in edit_instructions):
            if get_user_approval(path, edit_instructions, config):
                edited_content, changes_made = apply_edits(path, edit_instructions, original_content)
                if changes_made:
                    try:
                        with open(path, 'w') as f:
                            f.write(edited_content)
                        return {
                            "path": path,
                            "status": "success",
                            "message": f"Changes successfully applied and written to {path}",
                            "edited_content": edited_content
                        }
                    except IOError as e:
                        return {
                            "path": path,
                            "status": "error",
                            "message": f"Changes were made but could not be written to {path}",
                            "error": str(e)
                        }
                else:
                    return {
                        "path": path,
                        "status": "no_changes",
                        "message": f"No changes could be applied to {path}"
                    }
            else:
                return {
                    "path": path,
                    "status": "skipped",
                    "message": f"User skipped changes for {path}"
                }
        else:
            error_messages = [instruction['message'] for instruction in edit_instructions if 'error' in instruction]
            return {
                "path": path,
                "status": "error",
                "message": f"Failed to generate valid edit instructions for {path}",
                "errors": error_messages
            }
    except Exception as e:
        logger.error(f"Error processing file {file['path']}: {str(e)}", exc_info=True)
        return {
            "path": file['path'],
            "status": "error",
            "message": f"An unexpected error occurred while processing {file['path']}",
            "error": str(e)
        }

def code_edit_tool(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Edit multiple code files based on AI-generated instructions.
    
    Args:
        tool_input (Dict[str, Any]): A dictionary containing:
            - files (List[Dict[str, Any]]): List of files to edit, each with 'path', 'content', and 'instructions'.
            - project_context (str): Overall project context.
            - config (Dict[str, Any]): Configuration settings including model_name, max_tokens, anthropic_headers, and interactive_mode.

    Returns:
        Dict[str, Any]: A dictionary containing the results of the editing process and any error information.
    """
    try:
        files = tool_input.get("files", [])
        project_context = tool_input.get("project_context", "")
        config = tool_input.get("config", {})

        if not files:
            logger.error("No files provided for editing")
            return {"error": "No files provided for editing", "is_error": True}

        # Initialize Anthropic client
        client = Anthropic(api_key=config.get("api_key"))

        results = []
        console_output = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console
        ) as progress:
            edit_task = progress.add_task("[cyan]Editing files...", total=len(files))

            for file in files:
                # Hide progress bar
                progress.stop()

                file_result = process_file(client, file, project_context, config)

                # Show progress bar again
                progress.start()

                results.append(file_result)
                console_output.append(f"Processed file: {file['path']}")
                progress.update(edit_task, advance=1)

        return {
            "results": results,
            "console_output": "\n".join(console_output),
            "is_error": False
        }
    except Exception as e:
        logger.error(f"An unexpected error occurred during code editing: {str(e)}", exc_info=True)
        return {"error": f"An unexpected error occurred during code editing: {str(e)}", "is_error": True}

logger.info("code_edit_tool.py module loaded")