# Standard library imports
import os
import sys
import textwrap
import threading
import itertools
import copy
import json
import asyncio
import logging
import time
from datetime import datetime
from pathlib import Path
import matplotlib.pyplot as plt
from typing import Dict, List, Any, Union, Tuple, Optional
from dataclasses import dataclass, field

# Third-party imports
import anthropic
import yaml
from colorama import init, Fore, Style

# Rich library imports
from rich.console import Console, Group
from rich.panel import Panel
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.text import Text
from rich.tree import Tree

# New import for FilesContext
from files_context import FilesContext
from tools import execute_tool, TOOLS, FileReadError, _list_files, _read_file, read_files_in_folder, _create_file, _create_folder, project_structure, project_study
from initial_review import InitialReview
from wise_counsel import WiseCounsel

# Constants
EXIT_COMMAND = 'exit'
LOG_DIR = Path("C-Logs")
LOG_FILE = LOG_DIR / "codai.log"
CONFIG_FILE = "config.yaml"
TOOL_CHOICE = {"type": "auto"}

# Color constants
COLOR_USER = Fore.MAGENTA
COLOR_ASSISTANT = Fore.GREEN
COLOR_SYSTEM = Fore.YELLOW
COLOR_ERROR = Fore.RED
COLOR_TOOL = Fore.CYAN

# Constants
REASONING_EMOJI = "🧠"
RESPONSE_EMOJI = "💬"
REASONING_TITLE = "Reasoning"
RESPONSE_TITLE = "Response"
PANEL_TITLE = "🤖 CODAI Response"

# Initialize colorama for cross-platform colored terminal output
init()

# Initialize Rich console
console = Console()

# Exception classes
class CodaiError(Exception):
    """Base exception class for Codai"""

class ConfigurationError(CodaiError):
    """Raised when there's an issue with the configuration"""

class FileReadError(CodaiError):
    """Raised when there's an error reading a file"""

class APIError(CodaiError):
    """Raised when there's an error with the API call"""

def setup_logging() -> None:
    """
    Set up logging configuration for the application.
    
    This function creates a log directory, clears the existing log file content,
    and configures the root logger to write to the log file.
    """
    LOG_DIR.mkdir(exist_ok=True)
    
    # Clear the content of the existing log file if it exists
    if LOG_FILE.exists():
        with open(LOG_FILE, 'w') as log_file:
            pass  # Opening the file in write mode and immediately closing it clears the content
    
    handler = logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8')  # Changed mode to 'a' for append
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    
    # Remove any existing handlers (e.g., StreamHandler to console)
    for h in logger.handlers[:]:
        if not isinstance(h, logging.FileHandler):
            logger.removeHandler(h)
    
    # Log the start of a new session
    logger.info(f"New Codai session started at {datetime.now()}")

# Call setup_logging at the start of the script
setup_logging()

# Get logger for this module
logger = logging.getLogger(__name__)

@dataclass
class Config:
    """Configuration class for the Codai application."""
    api_key: str
    model_name: str
    anthropic_headers: Dict[str, str] = field(default_factory=dict)
    max_tokens: int = 8192  # Default value, adjust as needed
    interactive_mode: bool = True  # New attribute with a default value
    exclude_dirs: List[str] = field(default_factory=list)  # New attribute for excluded directories

    @classmethod
    def load(cls, config_path: str = CONFIG_FILE) -> 'Config':
        """
        Load configuration from a YAML file.

        Args:
            config_path (str): Path to the configuration file. Defaults to CONFIG_FILE.

        Returns:
            Config: An instance of the Config class with loaded values.

        Raises:
            ConfigurationError: If there's an error loading the configuration.
        """
        try:
            with open(config_path, 'r') as config_file:
                config_data = yaml.safe_load(config_file)
            
            if 'anthropic_headers' not in config_data:
                config_data['anthropic_headers'] = {
                    "anthropic-beta": "prompt-caching-2024-07-31,max-tokens-3-5-sonnet-2024-07-15"
                }
            
            if 'max_tokens' not in config_data:
                config_data['max_tokens'] = 8192  # Default value if not specified in config file
            
            if 'interactive_mode' not in config_data:
                config_data['interactive_mode'] = True  # Default to True if not specified
            
            if 'exclude_dirs' not in config_data:
                config_data['exclude_dirs'] = []  # Default to an empty list if not specified
            
            return cls(**config_data)
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            raise ConfigurationError(f"Failed to load configuration: {e}") from e

@dataclass
class SystemMessage:
    base_prompt: str = """Your name is CODAI, an advanced AI system dedicated to evolving the art and science of coding. As CODAI, you are an X10 AI high-grade developer and software engineer, with exceptional expertise in analysing, optimising, and revolutionising complex software projects. Your mission is to push the boundaries of software development, introducing innovative approaches and cutting-edge methodologies.

You are tasked with providing advanced insights, architectural recommendations, and code improvements based on project files and structures. Your analysis should not only solve immediate problems but also elevate the overall quality and sophistication of the codebase, fostering the evolution of coding practices.

CRITICAL AI INSTRUCTIONS: You MUST adhere to these principles at all times

1. File Content Primacy: ALWAYS analyse available file contents thoroughly before making any statements about the project structure or requesting additional information. Your primary source of truth is the content of the files themselves.

2. Zero Assumptions Policy: DO NOT make assumptions about the existence of files, project structures, or functionalities that are not explicitly mentioned in the file contents or your given context. Base all inferences strictly on the information present in the file contents.

3. Explicit Uncertainty and Reasoning: Clearly state any uncertainties in your analysis and always explain your reasoning process, citing specific parts of the file contents that led to your conclusions.

4. Continuous Reappraisal: Continuously update and refine your understanding of the project as you analyse more file contents. Be prepared to revise earlier conclusions based on new information.

5. Confirmation Before Tool Use: Before suggesting or using any external tools (like list_files or read_file), explicitly confirm that you have exhaustively analysed all available file contents and explain why additional information is necessary.

IMPORTANT: You have access to a file context that contains information about the project's files and their contents. Always check this context before responding to queries or performing analysis. When referencing or discussing specific files or code snippets, make sure to use the information provided in the file context. If a file or information is not present in the context, use the appropriate tools to request it.

CRITICAL AI INSTRUCTIONS FOR CODE CHANGES:
1. Always use the code_change_analysis_action_plan tool before making any code modifications.
2. Review and present the action plan to the user, highlighting the five reports to be generated.
3. Wait for explicit user approval before proceeding with any code changes or report generation.
4. When using the intelligent_edit tool, always refer to the action plan and any generated reports.
5. Never attempt to make code changes without first creating and reviewing a code change analysis action plan.

Guidelines for utilising the file context:
1. Always review the file context before answering questions about the project structure or specific files.
2. When discussing code, reference the specific files and line numbers from the context.
3. If you need information about a file that's not in the context, use the read_file tool to request it.
4. Use the list_files tool to get an updated view of the project structure if needed.
5. Base your analysis and recommendations on the actual content of the files in the context.
6. If the file context seems outdated or inconsistent with the user's questions, suggest refreshing the context using the appropriate tools.
7. For a comprehensive view of the project hierarchy, consider using the project_structure tool, which provides a detailed JSON representation of the project's directory structure.

You have access to sophisticated tools for listing files, reading file contents, and analysing code changes. 
Leverage your extensive knowledge of software design patterns, system architecture, performance optimisation, and security best practices in your analysis.

IMPORTANT: Always communicate your responses in Australian English.

IMPORTANT: The project_study function requires the output of the project_structure function. When using or recommending the project_study function, consider the following:
1. Ensure that project_structure has been run and its output is available before running project_study.
2. Inform users about the need to run project_structure first if it hasn't been done recently.
3. The project_study function now provides detailed metadata about the analysis, including whether it used the project structure data.
4. Be prepared to interpret and explain any error codes or messages returned by project_study, especially those related to missing or invalid project structure data.

Follow these guidelines to ensure your responses meet the highest standards of thoroughness, accuracy, and engineering excellence:

1. Use the list_files tool when needed to get up-to-date information about file listings or project structure, especially if the current context seems outdated or incomplete.
2. Use the read_file tool when needed to access the content of a specific file, particularly if it's not already available in your current context or if you need to verify recent changes.
3. When you use a tool, wait for the result before continuing your response.
4. Explicit Completeness: Only consider a task complete if you have exhaustively verified it across all relevant project files and contexts.
5. Demand Evidence: Provide specific evidence and examples for each claim or analysis you make about the project or its files.
6. Self-Questioning: Before concluding any analysis, ask yourself: "Have I checked this in every relevant file and context within the project?" If there's any doubt, express uncertainty.
7. Methodology Explanation: Explain your methodology for verifying information or performing analysis. Detail the steps you've taken to ensure comprehensive coverage.
8. Double-Check System: After completing your analysis, revisit each point and re-verify it, actively looking for any aspects you might have missed in the first pass.
9. Zero Tolerance for Assumptions: Do not make any assumptions. If you haven't directly observed or verified something using the provided tools, consider it unknown and incomplete.
10. Explicit Uncertainty: If you are unsure about any aspect of your analysis, clearly state your uncertainty and explain why. It's better to express doubt than to make an incorrect assertion.
11. Scope Definition: Before beginning any analysis, clearly define the scope of what you're examining and what constitutes a complete analysis. Review and confirm this scope before concluding your response.
12. When referencing file contents, use direct quotes from the files. Format quotes like this: "{{quote}}"
13. After making any claim about file contents, verify it by finding a supporting quote. If you can't find a supporting quote, retract the claim.
14. Base your responses ONLY on the information from the tools and provided context. Do not use external knowledge.
15. Before answering, explain your reasoning step-by-step within <reasoning></reasoning> tags.
16. If asked about multiple files or complex scenarios, break down your analysis into clear, verifiable steps.
17. Performance Optimisation: Always consider the performance implications of your suggestions, especially for large-scale systems.
18. Security-First Approach: Prioritise security best practices in all code-related discussions and recommendations.
19. Scalability Considerations: Evaluate and discuss the scalability aspects of the project architecture and code.
20. Code Quality: Emphasise clean code principles, SOLID design, and maintainability in your analysis and suggestions.
21. Error Handling and Logging: Discuss robust error handling strategies and logging best practices when reviewing or suggesting code modifications.
22. Testing Strategies: Recommend appropriate testing methodologies, including unit testing, integration testing, and end-to-end testing where applicable.
23. Australian English: Ensure all your responses use Australian English spellings, terminology, and expressions.
24. Evolutionary Approach: As CODAI, always look for opportunities to evolve coding practices, suggesting innovative solutions that push the boundaries of traditional software development.
25. Tool Use Approval: NEVER execute a tool without explicitly asking for and receiving user approval first. Always explain why you need to use the tool and wait for the user's confirmation before proceeding.

Remember, as CODAI, your role goes beyond being an X10 AI high-grade developer. You are at the forefront of evolving coding practices. Your analysis should be comprehensive, insightful, and reflect the highest standards of software engineering while also introducing revolutionary ideas and approaches. Thorough verification, explicit expression of uncertainty, and a focus on code quality, performance, and security are crucial for maintaining the excellence expected at this level of expertise. Always communicate these insights in Australian English, and strive to elevate the art of coding with each interaction."""


    def get_message_for_api(self, files_context: FilesContext) -> List[Dict[str, Any]]:
        """
        Get the system message formatted for the API, including file context.

        Args:
            files_context (FilesContext): The current file context.

        Returns:
            List[Dict[str, Any]]: Formatted system message with file context and cache control.
        """
        message = [{"type": "text", "text": self.base_prompt}]
        existing_files, new_modified_files = files_context.split_files_for_api_context()

        if not existing_files and not new_modified_files:
            # If both are empty, add a cache control message
            return [{
                "type": "text",
                "text": json.dumps(message),
                "cache_control": {"type": "ephemeral"}
            }]
        else:
            if existing_files:
                existing_files_content = "Existing files:\n" + "\n".join(f"File: {path}\nContent: {content}" for path, content in existing_files)
                message.append({
                    "type": "text", 
                    "text": existing_files_content
                })
                message = [{
                    "type": "text",
                    "text": json.dumps(message),
                    "cache_control": {"type": "ephemeral"}
                }]
            if new_modified_files:
                new_modified_files_content = "New or modified files:\n" + "\n".join(f"File: {path}\nContent: {content}" for path, content in new_modified_files)
                message.append({
                    "type": "text", 
                    "text": new_modified_files_content
                })
                return [{
                    "type": "text",
                    "text": json.dumps(message),
                    "cache_control": {"type": "ephemeral"}
                }]
            else:
                return message
       
@dataclass
class CacheMetrics:
    total_requests: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_creation_tokens: int = 0
    total_time: float = 0
    
    current_input_tokens: int = 0
    current_output_tokens: int = 0
    current_cache_read_tokens: int = 0
    current_cache_creation_tokens: int = 0
    current_time: float = 0

    def update(self, response: anthropic.types.Message, elapsed_time: float) -> None:
        self.total_requests += 1
        self.total_input_tokens += response.usage.input_tokens
        self.total_output_tokens += response.usage.output_tokens
        self.total_cache_read_tokens += getattr(response.usage, 'cache_read_input_tokens', 0)
        self.total_cache_creation_tokens += getattr(response.usage, 'cache_creation_input_tokens', 0)
        self.total_time += elapsed_time
        
        # Update current interaction metrics
        self.current_input_tokens = response.usage.input_tokens
        self.current_output_tokens = response.usage.output_tokens
        self.current_cache_read_tokens = getattr(response.usage, 'cache_read_input_tokens', 0)
        self.current_cache_creation_tokens = getattr(response.usage, 'cache_creation_input_tokens', 0)
        self.current_time = elapsed_time

    def generate_report(self) -> str:
        # Calculate overall cache hit rate
        total_input_tokens = self.total_input_tokens + self.total_cache_read_tokens
        percentage_cached = (self.total_cache_read_tokens / total_input_tokens * 100 
                             if total_input_tokens > 0 else 0)
        
        # Calculate current cache hit rate
        current_total_tokens = self.current_input_tokens + self.current_cache_read_tokens
        current_percentage_cached = (self.current_cache_read_tokens / current_total_tokens * 100 
                                     if current_total_tokens > 0 else 0)
        
        return f"""
        Cache Performance Report:
        -------------------------
        Current Interaction:
        Input Tokens: {self.current_input_tokens}
        Output Tokens: {self.current_output_tokens}
        Cache Read Tokens: {self.current_cache_read_tokens}
        Cache Write Tokens: {self.current_cache_creation_tokens}
        Current Cache Hit Rate: {current_percentage_cached:.1f}%
        Response Time: {self.current_time:.2f} seconds
        
        Overall Metrics:
        Total Requests: {self.total_requests}
        Total Input Tokens: {self.total_input_tokens}
        Total Output Tokens: {self.total_output_tokens}
        Total Cache Read Tokens: {self.total_cache_read_tokens}
        Total Cache Write Tokens: {self.total_cache_creation_tokens}
        Overall Cache Hit Rate: {percentage_cached:.1f}%
        Total Time Taken: {self.total_time:.2f} seconds
        
        Average per Request:
        Avg Input Tokens: {self.total_input_tokens / self.total_requests:.2f}
        Avg Output Tokens: {self.total_output_tokens / self.total_requests:.2f}
        Avg Response Time: {self.total_time / self.total_requests:.2f} seconds
        """

@dataclass
class Conversation:
    """Represents a conversation with the AI assistant."""
    system_message: SystemMessage = field(default_factory=SystemMessage)
    messages: List[Dict[str, Any]] = field(default_factory=list)
    cache_metrics: CacheMetrics = field(default_factory=CacheMetrics)
    files_context: FilesContext = field(default_factory=FilesContext)

    def add_message(self, role: str, content: Any) -> None:
        """
        Add a message to the conversation.

        Args:
            role (str): The role of the message sender (e.g., "user", "assistant").
            content (Any): The content of the message.
        """
        self.messages.append({"role": role, "content": content})

    def get_messages_for_api(self) -> List[Dict[str, Any]]:
        """
        Get the conversation messages formatted for the API.
        
        Returns:
            List[Dict[str, Any]]: Formatted conversation messages.
        """
        formatted_messages = copy.deepcopy(self.messages)
        user_messages = [msg for msg in formatted_messages if msg["role"] == "user"]
        last_two_user_indices = [formatted_messages.index(msg) for msg in user_messages[-2:]]

        for i in last_two_user_indices:
            msg = formatted_messages[i]
            if isinstance(msg["content"], list) and msg["content"]:
                if isinstance(msg["content"][0], dict):
                    msg["content"][0]["cache_control"] = {"type": "ephemeral"}
                else:
                    msg["content"][0] = {
                        "type": "text",
                        "text": str(msg["content"][0]),
                        "cache_control": {"type": "ephemeral"}
                    }
            elif isinstance(msg["content"], (str, dict)):
                msg["content"] = [{
                    "type": "text",
                    "text": str(msg["content"]),
                    "cache_control": {"type": "ephemeral"}
                }]

        return formatted_messages

def print_welcome_message():
    welcome_text = """
╔══════════════════════════════════════════════════════════════════════════════╗
║                               Welcome to CODAI                               ║
╚══════════════════════════════════════════════════════════════════════════════╝

CODAI is an advanced AI system designed to assist you with coding tasks,
project analysis, and software engineering questions.

Available commands:
• /help                 : Show this help message
• /clear                : Clear the screen
• /list files [path]    : List files in the specified path (default: current directory)
• /context files        : List files currently in the context
• /read <filename>      : Display the contents of the specified file
• /read folder [path] [subfolders] : Read and display contents of all files in the specified folder
                                    (default: root, no subfolders)
• /create file <path> <content>: Create a new file with the specified content
• /create folder <path> : Create a new folder at the specified path
• /project structure [path] [include-ignored] : Display the project structure
                                               (default: current directory, respects .gitignore)
• /project study [path] [include-ignored] [output=<filename>] : Analyze project structure and create a detailed JSON report
                                              (default: current directory, respects .gitignore, output to project_study.json)
• /exit                 : End the conversation and exit CODAI

You can also use these commands without the '/' prefix.

Tips:
- Be specific in your questions about your project or code.
- You can ask CODAI to explain its reasoning by adding "Explain your thinking" to your query.
- For complex tasks, break them down into smaller steps and ask about each step separately.
- Use the project structure command to get an overview of your project's file organization.
- Use the project study command for a detailed analysis of your project's structure and dependencies.
- Both project structure and project study respect .gitignore by default. Use 'include-ignored' to see all files.

Let's get started! How can I assist you with your project today?
"""
    print(COLOR_ASSISTANT + welcome_text + Style.RESET_ALL)

def print_help_message():
    help_text = """
Available commands:
• /help                 : Show this help message
• /clear                : Clear the screen
• /list files [path]    : List files in the specified path (default: current directory)
• /context files        : List files currently in the context
• /read <filename>      : Display the contents of the specified file
• /read folder [path] [subfolders] : Read and display contents of all files in the specified folder
                                    (default: root, no subfolders)
• /create file <path> <content>: Create a new file with the specified content
• /create folder <path> : Create a new folder at the specified path
• /project structure [path] [options] : Display the project structure
                                        Options:
                                        - include-ignored : Include files/dirs ignored by .gitignore
                                        - non-interactive : Disable interactive mode
                                        - output=<path>   : Specify output JSON file path
                                        - exclude=<dirs>  : Comma-separated list of dirs to exclude
• /project study [path] [include-ignored] [output=<filename>] : Analyze project structure and create a detailed JSON report
                                              (default: current directory, respects .gitignore, output to project_study.json)
                                              Note: Requires a project structure file. If not found, you'll be prompted to create or provide one.
• /exit                 : End the conversation and exit CODAI

You can also use these commands without the '/' prefix.

For any other input, CODAI will interpret it as a question or task related to your project.
"""
    print(COLOR_SYSTEM + help_text + Style.RESET_ALL)

def get_user_input() -> str:
    print(COLOR_USER + "\nYou:" + Style.RESET_ALL, end=" ")
    return input()

def print_error_message(error: str) -> None:
    error_box = f"""
╔{'═' * (len(error) + 2)}╗
║ {error} ║
╚{'═' * (len(error) + 2)}╝
"""
    print(COLOR_ERROR + error_box + Style.RESET_ALL)
    print(COLOR_SYSTEM + "Please try again or type 'help' for available commands." + Style.RESET_ALL)

def check_console_encoding():
    if sys.stdout.encoding.lower() != 'utf-8':
        print("Warning: Console encoding is not UTF-8. Some characters may not display correctly.")
        print(f"Current encoding: {sys.stdout.encoding}")
        # Optionally, try to set UTF-8 encoding
        # sys.stdout.reconfigure(encoding='utf-8')

def handle_api_error(e: Exception) -> None:
    error_message = f"An error occurred while communicating with the AI: {str(e)}"
    print_error_message(error_message)
    logger.error(f"API Error: {error_message}", exc_info=True)

spinner_active = False
spinner_thread = None
spinner_mode = "thinking"  # New variable to track the current mode

def thinking_spinner():
    global spinner_active, spinner_mode
    spinner = itertools.cycle(['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'])
    start_time = time.time()
    while spinner_active:
        elapsed_time = int(time.time() - start_time)
        mode_text = "reviewing" if spinner_mode == "review" else "thinking"
        sys.stdout.write(COLOR_SYSTEM + f'\rCODAI is {mode_text} {next(spinner)} ({elapsed_time}s)' + Style.RESET_ALL)
        sys.stdout.flush()
        time.sleep(0.1)
    sys.stdout.write('\r' + ' ' * 50 + '\r')
    sys.stdout.flush()

def start_thinking_spinner(mode="thinking"):
    global spinner_active, spinner_thread, spinner_mode
    spinner_mode = mode
    if not spinner_active:
        spinner_active = True
        spinner_thread = threading.Thread(target=thinking_spinner, daemon=True)
        spinner_thread.start()

def stop_thinking_spinner():
    global spinner_active, spinner_thread
    if spinner_active:
        spinner_active = False
        if spinner_thread:
            spinner_thread.join(timeout=1)
        spinner_thread = None

def handle_command(command: str, conversation: Conversation) -> str:
    """
    Process user commands.

    Args:
        command (str): The user's command.
        conversation (Conversation): The current conversation object.

    Returns:
        str: "exit" to end the conversation, "continue" otherwise.
    """
    command = command.strip().lower()
    if command.startswith('/'):
        command = command[1:]  # Remove the leading '/'
    
    if command == 'exit':
        print(COLOR_SYSTEM + "Thank you for using CODAI. Goodbye!" + Style.RESET_ALL)
        return "exit"
    elif command == 'help':
        print_help_message()
    elif command == 'clear':
        os.system('cls' if os.name == 'nt' else 'clear')
        print_welcome_message()
    elif command == 'context files':
        file_list = conversation.files_context.list_files_in_context()
        console.print(Panel(file_list, title="Files in Context", border_style="cyan"))    
    elif command.startswith('list files'):
        path = command[10:].strip() or '.'
        result = _list_files({"path": path})
        print_file_list(result, path)
    elif command.startswith('read folder'):
        parts = command[11:].strip().split()
        folder_path = parts[0] if parts else '.'
        include_subfolders = 'subfolders' in parts
        result = read_files_in_folder({"folder_path": folder_path, "include_subfolders": include_subfolders})
        print_files_in_folder_contents(result, folder_path, include_subfolders)
    elif command.startswith('read'):
        file_path = command[4:].strip()
        if not file_path:
            print_error_message("Please specify a file to read.")
        else:
            result = _read_file({"file_path": file_path})
            print_file_content(result, file_path)
    elif command.startswith('create file'):
        parts = command[11:].strip().split(' ', 1)
        if len(parts) != 2:
            print_error_message("Please specify a file path and content. Usage: create file <path> <content>")
        else:
            file_path, content = parts
            result = _create_file({"file_path": file_path, "content": content})
            print_file_creation_result(result)
    elif command.startswith('create folder'):
        folder_path = command[13:].strip()
        if not folder_path:
            print_error_message("Please specify a folder path to create.")
        else:
            result = _create_folder({"folder_path": folder_path})
            print_folder_creation_result(result)
    elif command.startswith('project structure'):
        parts = command[17:].strip().split()
        folder_path = '.'
        output_path = ""
        include_ignored = False
        interactive = True  # Default to True as per the tool definition
        exclude_dirs = []
        
        i = 0
        while i < len(parts):
            if parts[i] == 'include-ignored':
                include_ignored = True
            elif parts[i].startswith('output='):
                output_path = parts[i].split('=')[1]
            elif parts[i] == 'non-interactive':
                interactive = False
            elif parts[i].startswith('exclude='):
                exclude_dirs = parts[i].split('=')[1].split(',')
            else:
                folder_path = parts[i]
            i += 1
        
        result = project_structure({
            "folder_path": folder_path,
            "include_ignored": include_ignored,
            "output_path": output_path,
            "interactive": interactive,
            "exclude_dirs": exclude_dirs
        })
        print_project_structure(result, folder_path, include_ignored, interactive, exclude_dirs)
    elif command.startswith('project study'):
        parts = command[13:].strip().split()
        folder_path = '.'
        output_file = "project_study.json"
        include_ignored = False
        
        for part in parts:
            if part.startswith('output='):
                output_file = part.split('=')[1]
            elif part == 'include-ignored':
                include_ignored = True
            else:
                folder_path = part
        
        print(COLOR_SYSTEM + "Note: Project study requires a project structure file. If not found, you'll be prompted to create or provide one." + Style.RESET_ALL)
        
        # Add check for project_structure file
        project_structure_file = os.path.join(folder_path, "project_structure.json")
        if not os.path.exists(project_structure_file):
            print(COLOR_SYSTEM + "Project structure file not found. Please run 'project structure' command first." + Style.RESET_ALL)
            return "continue"
        elif (time.time() - os.path.getmtime(project_structure_file)) > 3600:  # 1 hour
            print(COLOR_SYSTEM + "Project structure file may be outdated. Consider running 'project structure' command again." + Style.RESET_ALL)
        
        result = project_study({
            "folder_path": folder_path,
            "output_file": output_file,
            "include_ignored": include_ignored
        })
        print_project_study_result(result)
    
    return "continue"

def print_project_study_result(result: Dict[str, Any]) -> None:
    if result.get("status") == "success":
        console.print(Panel(
            f"[green]Project study completed successfully.[/green]\n\n"
            f"Output saved to: {result['data']['output_file']}\n"
            f"Files analyzed: {result['data']['files_analyzed']}\n"
            f"Analysis time: {result['data']['analysis_time']:.2f} seconds\n"
            f"Project structure used: {'Yes' if result['data']['project_structure_used'] else 'No'}",
            title="Project Study Result",
            expand=False,
            border_style="green"
        ))
    else:
        error_message = result.get("message", "Unknown error occurred")
        error_code = result.get("error_code", "UNKNOWN_ERROR")
        console.print(Panel(
            f"[red]Error in project study: {error_message}[/red]\n\n"
            f"Error code: {error_code}\n\n"
            "Please ensure that:\n"
            "1. The project structure file exists and is up-to-date.\n"
            "2. You have necessary permissions to read files in the project directory.\n"
            "3. The project structure accurately represents the current state of your project.",
            title="Project Study Error",
            expand=False,
            border_style="red"
        ))
    
    if result.get("data", {}).get("warnings"):
        console.print(Panel(
            "\n".join(f"- {warning}" for warning in result["data"]["warnings"]),
            title="Warnings",
            expand=False,
            border_style="yellow"
        ))

    # Print any additional metadata or insights
    if result.get("data", {}).get("insights"):
        console.print(Panel(
            "\n".join(f"- {insight}" for insight in result["data"]["insights"]),
            title="Analysis Insights",
            expand=False,
            border_style="blue"
        ))

def print_project_structure(result: Dict[str, Any], folder_path: str, include_ignored: bool, interactive: bool, exclude_dirs: List[str]) -> None:
    if result.get('is_error', False):
        print_error_message(result.get('error', 'Unknown error occurred'))
        return

    json_file_path = result.get('json_file_path')
    if not json_file_path or not os.path.exists(json_file_path):
        print_error_message("JSON file not found or not created")
        return

    try:
        with open(json_file_path, 'r', encoding='utf-8') as json_file:
            structure = json.load(json_file)
    except json.JSONDecodeError:
        print_error_message("Error parsing project structure JSON file")
        return
    except UnicodeDecodeError:
        print_error_message("Error reading project structure file: file is not UTF-8 encoded")
        return
    except Exception as e:
        print_error_message(f"Unexpected error reading project structure file: {str(e)}")
        return

    print(COLOR_SYSTEM + f"\nProject Structure for: {folder_path}" + Style.RESET_ALL)
    print(COLOR_SYSTEM + f"Include ignored: {include_ignored}" + Style.RESET_ALL)
    print(COLOR_SYSTEM + f"Interactive mode: {interactive}" + Style.RESET_ALL)
    if exclude_dirs:
        print(COLOR_SYSTEM + f"Excluded directories: {', '.join(exclude_dirs)}" + Style.RESET_ALL)
    print("=" * 60)

    def print_structure(node: Dict[str, Any], indent: str = '') -> None:
        if node['type'] == 'directory':
            icon = '📁'
        else:
            icon = '📄'
        
        try:
            print(f"{indent}{COLOR_SYSTEM}{icon} {node['name']}{Style.RESET_ALL}")
        except UnicodeEncodeError:
            fallback_icon = 'D' if node['type'] == 'directory' else 'F'
            print(f"{indent}{COLOR_SYSTEM}[{fallback_icon}] {node['name']}{Style.RESET_ALL}")
        
        if node['type'] == 'directory':
            for child in node.get('children', []):
                print_structure(child, indent + '  ')

    try:
        print_structure(structure)
    except Exception as e:
        print_error_message(f"Error occurred while printing structure: {str(e)}")

    print("\n" + COLOR_SYSTEM + "=" * 60 + Style.RESET_ALL)
    
    print(COLOR_SYSTEM + f"\nJSON file created at: {json_file_path}" + Style.RESET_ALL)
    print(COLOR_SYSTEM + "You can use this file for further analysis or processing." + Style.RESET_ALL)

    # Additional information from the result
    if 'summary' in result:
        print("\nSummary:")
        print(f"Total files: {result['summary'].get('total_files', 'N/A')}")
        print(f"Total directories: {result['summary'].get('total_directories', 'N/A')}")
        print("Traversed directories:")
        for dir in result['summary'].get('traversed_directories', []):
            print(f"  - {dir}")
        print("Excluded directories:")
        for dir in result['summary'].get('excluded_directories', []):
            print(f"  - {dir}")

def print_files_in_folder_contents(result: Dict[str, Any], folder_path: str, include_subfolders: bool) -> None:
    if 'error' in result:
        print_error_message(result['error'])
    else:
        print(COLOR_SYSTEM + f"\nContents of files in folder: {folder_path} (including subfolders: {include_subfolders})" + Style.RESET_ALL)
        print("=" * 40)
        for file_path, file_result in result['results'].items():
            if file_result.get('is_error', False):
                print(f"{COLOR_ERROR}Error reading {file_path}: {file_result['error']}{Style.RESET_ALL}")
            else:
                print(f"{COLOR_SYSTEM}File: {file_path}{Style.RESET_ALL}")
                print("-" * 20)
                print(file_result['file_content'][:500] + "..." if len(file_result['file_content']) > 500 else file_result['file_content'])
                print("\n")
        print(COLOR_SYSTEM + f"Total files processed: {len(result['results'])}" + Style.RESET_ALL)

def print_file_creation_result(result: Dict[str, Any]) -> None:
    if result.get('is_error', False):
        print_error_message(result['error'])
    else:
        print(COLOR_SYSTEM + result['message'] + Style.RESET_ALL)

def print_folder_creation_result(result: Dict[str, Any]) -> None:
    if result.get('is_error', False):
        print_error_message(result['error'])
    else:
        print(COLOR_SYSTEM + result['message'] + Style.RESET_ALL)

def print_file_list(result: Dict[str, Any], path: str) -> None:
    if 'error' in result:
        print_error_message(result['error'])
    else:
        print(COLOR_SYSTEM + f"\nContents of directory: {path}" + Style.RESET_ALL)
        print("=" * (24 + len(path)))
        if not result['files'] and not result['folders']:
            print("(Empty directory)")
        else:
            if result['folders']:
                print(COLOR_SYSTEM + "\nFolders:" + Style.RESET_ALL)
                for folder in sorted(result['folders']):
                    print(f"  📁 {folder}")
            if result['files']:
                print(COLOR_SYSTEM + "\nFiles:" + Style.RESET_ALL)
                for file in sorted(result['files']):
                    print(f"  📄 {file}")

def print_file_content(result: Dict[str, Any], file_path: str) -> None:
    if 'error' in result:
        print_error_message(result['error'])
    else:
        print(COLOR_SYSTEM + f"\nWhat to do with contents of file?: {file_path}" + Style.RESET_ALL)
        print("=" * (20 + len(file_path)))
        #print(result['content'])
        #print(COLOR_SYSTEM + "=" * (20 + len(file_path)) + Style.RESET_ALL)

def print_ai_response(response_content):
    print("\n" + "=" * 80)
    print("🤖 AI Response:")
    print("=" * 80)
    for content in response_content:
        if content.type == 'text':
            print(textwrap.fill(content.text, width=78, initial_indent="  ", subsequent_indent="  "))
        elif content.type == 'tool_use':
            print(f"\n  🛠️  Requesting to use tool: {content.name}")
            print("  Tool input:")
            print(textwrap.fill(json.dumps(content.input, indent=2), width=76, initial_indent="    ", subsequent_indent="    "))
    print("=" * 80 + "\n")

def print_tool_execution(tool_name, tool_args):
    print("\n" + "-" * 80)
    print(f"⚙️  Executing tool: {tool_name}")
    print(f"   Arguments: {json.dumps(tool_args, indent=2)}")
    print("-" * 80 + "\n")

def print_tool_result(tool_name, result):
    result_type = type(result).__name__
    
    header = Group(
        Text(f"📊 Tool: ", style="bold cyan") + Text(f"{tool_name}", style="cyan"),
        Text(f"Result Type: ", style="bold magenta") + Text(f"{result_type}", style="magenta")
    )
    
    if tool_name == "list_files":
        content = format_list_files_result(result)
    elif isinstance(result, str):
        content = Group(
            Text("🔤 String Result:", style="bold green"),
            Syntax(result, "text", theme="monokai")
        )
    elif isinstance(result, dict):
        content = Group(
            Text("🗃️ Dictionary Result:", style="bold green"),
            Syntax(json.dumps(result, indent=2), "json", theme="monokai")
        )
    elif isinstance(result, list):
        content = Group(
            Text("📋 List Result:", style="bold green"),
            Syntax(json.dumps(result, indent=2), "json", theme="monokai")
        )
    else:
        content = Group(
            Text("❓ Other Result Type:", style="bold yellow"),
            Text(str(result))
        )
    
    panel = Panel(
        Group(header, content),
        title="[bold blue]🛠️ Tool Execution Result[/bold blue]",
        expand=False,
        border_style="green"
    )
    
    console.print(panel)

def format_list_files_result(result):
    tree = Tree("📁 Root")
    
    if 'folders' in result:
        folders_branch = tree.add("📁 Folders", style="bold yellow")
        for folder in result['folders']:
            folders_branch.add(f"📁 {folder}")
    
    if 'files' in result:
        files_branch = tree.add("📄 Files", style="bold green")
        for file in result['files']:
            files_branch.add(f"📄 {file}")
    
    return Group(
        Text("📂 Directory Contents:", style="bold blue"),
        tree
    )

async def process_claude_response(
    response: anthropic.types.Message,
    conversation: Conversation,
    client: anthropic.Anthropic,
    config: Config
) -> Union[List[Dict[str, Any]], str, None]:
    """
    Process Claude's response, handling tool calls and extracting the final response.

    Args:
        response (anthropic.types.Message): The response from Claude.
        conversation (Conversation): The current conversation object.
        client (anthropic.Anthropic): The Anthropic client.
        config (Config): The configuration object.

    Returns:
        Union[List[Dict[str, Any]], str, None]: Tool results, final response, or None if no response.
    """
    logger.debug(f"Processing Claude's response: {json.dumps(response.model_dump(), indent=2)}")

    assistant_message_content = []
    tool_results = []
    final_response = ""

    # Process the response
    for content in response.content:
        if content.type == 'text':
            final_response += _process_text_content(content, assistant_message_content)
        elif content.type == 'tool_use':

            # Print the complete AI response
            print_ai_response(response.content)

            print_tool_execution(content.name, content.input)
            tool_result = execute_tool(content.name, content.input)
            print_tool_result(content.name, tool_result)
            tool_results.extend(_process_tool_use(content, assistant_message_content, tool_result))

    conversation.add_message("assistant", assistant_message_content)
    logger.debug("Added assistant's response to conversation history")

    if tool_results:
        logger.debug(f"Returning tool results: {json.dumps(tool_results, indent=2)}")
        return tool_results
    elif final_response:
        logger.debug(f"Final response from Claude: {final_response.strip()}")
        return final_response.strip()
    else:
        logger.warning("Received empty response from Claude")
        return None

def _process_text_content(content: anthropic.types.ContentBlock, message_content: List[Dict[str, Any]]) -> str:
    """Process text content from Claude's response."""
    message_content.append({"type": "text", "text": content.text})
    logger.debug(f"Added text to final response: {content.text}")
    return content.text + "\n"

def _process_tool_use(content: anthropic.types.ContentBlock, message_content: List[Dict[str, Any]], tool_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Process tool use content from Claude's response."""
    logger.info(f"Processing tool use: {json.dumps(content.model_dump(), indent=2)}")
    tool_name = content.name
    tool_id = content.id
    tool_args = content.input

    message_content.append({
        "type": "tool_use",
        "id": tool_id,
        "name": tool_name,
        "input": tool_args
    })

    logger.debug(f"Tool '{tool_name}' result: {json.dumps(tool_result, indent=2)}")

    return [{
        "tool_use_id": tool_id,
        "tool_name": tool_name,
        "result": tool_result
    }]

async def generate_response(conversation: Conversation, client: anthropic.Anthropic, config: Config, wise_counsel: WiseCounsel, initial_review: InitialReview) -> None:
    """
    Generate a response from Claude, perform reviews until approved, and handle multiple tool uses if necessary.
    Uses a temporary context for feedback without modifying the main conversation history.

    Args:
        conversation (Conversation): The current conversation object.
        client (anthropic.Anthropic): The Anthropic client.
        config (Config): The configuration object.
        initial_review (InitialReview): The InitialReview instance for initial assessment.
        wise_counsel (WiseCounsel): The WiseCounsel instance for response review.
    """
    while True: 
        try:
            start_thinking_spinner()
            
            max_attempts = 5  # Maximum number of attempts to get an approved response
            attempt = 0
            approved_response = None
            proceed_with_wise_counsel = False  # Default to False
            is_first_pass = True  # Add this line to initialize is_first_pass

            # Create a deep copy of the conversation for temporary use
            temp_conversation = copy.deepcopy(conversation)

            while attempt < max_attempts and approved_response is None:
                start_time = time.time()
                
                # Get a response from Claude using the temporary conversation
                response = await _get_claude_response(temp_conversation, client, config)

                # Handle max_tokens stop reason
                while response.stop_reason == "max_tokens":
                    truncation_message, partial_content = await handle_max_tokens_exceeded(response)
                    
                    elapsed_time = time.time() - start_time
                    stop_thinking_spinner()

                    # Add the partial response to the conversation
                    conversation.add_message("assistant", [{"type": "text", "text": truncation_message}])

                    _handle_final_response(truncation_message)
                    return  # Exit the function after handling the truncation

                stop_thinking_spinner()
                start_thinking_spinner("review")  # Switch to review mode

                if is_first_pass:
                    # Extract the last user message and AI response
                    last_user_message = next((msg for msg in reversed(temp_conversation.messages) if msg['role'] == 'user'), None)
                    
                    def extract_response_content(response):
                        if response.content:
                            content = response.content[0]
                            if content.type == 'text':
                                return content.text
                            elif content.type == 'tool_use':
                                return f"Tool use requested: {content.name}"
                            else:
                                return f"Unexpected content type: {content.type}"
                        else:
                            return ""

                    ai_response_text = extract_response_content(response)

                    # Check if the last user message is a tool_result
                    is_tool_result = False
                    if last_user_message:
                        if isinstance(last_user_message['content'], list):
                            is_tool_result = any(item.get('type') == 'tool_result' for item in last_user_message['content'] if isinstance(item, dict))
                        elif isinstance(last_user_message['content'], dict):
                            is_tool_result = last_user_message['content'].get('type') == 'tool_result'

                    if is_tool_result:
                        logger.info("Last message is a tool_result. Skipping all review processes.")
                        approved_response = response
                        break  # Exit the loop as we have an approved response

                    # Perform initial review
                    #initial_review_result = await initial_review.assess_simplicity_clarity(
                        json.dumps(last_user_message['content']) if last_user_message else "",
                        ai_response_text
                    #)
                    #proceed_with_wise_counsel = initial_review_result['proceed_with_wise_counsel']
                    #logger.info(f"Initial review result: {initial_review_result}")

                    is_first_pass = False  # Set to False after the first pass

                if proceed_with_wise_counsel:
                    # Proceed with WiseCounsel review
                    context = json.dumps(temp_conversation.get_messages_for_api())
                    review_result = await wise_counsel.review_response(response, context, conversation.system_message.base_prompt)

                    logger.info(f"Response review result (Attempt {attempt + 1}): {review_result}")

                    if review_result.get('approved', False):
                        approved_response = response
                        logger.info("Response approved")
                    else:
                        logger.info("Response not approved. Requesting a new response.")

                        # Modify the last message (which should be the user message) in the temporary conversation
                        if temp_conversation.messages and temp_conversation.messages[-1]['role'] == 'user':
                            feedback = review_result.get('feedback', 'No specific feedback provided.')
                            feedback_text = f"\n[FEEDBACK]: The previous response was not satisfactory. Please revise your answer, considering this feedback: {feedback}"
                            
                            if isinstance(temp_conversation.messages[-1]['content'], list):
                                # If content is a list, add a new text item
                                temp_conversation.messages[-1]['content'].append({
                                    "type": "text",
                                    "text": feedback_text
                                })
                            elif isinstance(temp_conversation.messages[-1]['content'], str):
                                # If content is a string, append to it
                                temp_conversation.messages[-1]['content'] += feedback_text
                            else:
                                logger.warning(f"Unexpected content type in last user message: {type(temp_conversation.messages[-1]['content'])}")
                        else:
                            logger.warning("Last message is not from user, cannot append feedback")
                    
                    attempt += 1  # Increment attempt only when full review is conducted
                else:
                    # Skip WiseCounsel review on first pass if initial review deems it unnecessary
                    logger.info("Skipping WiseCounsel review based on initial assessment")
                    approved_response = response  # Consider the response approved without full review
                    break  # Exit the loop as we have an approved response

            if approved_response is None:
                logger.warning(f"Failed to get an approved response after {max_attempts} attempts.")
                print(COLOR_ERROR + f"I apologize, but I couldn't generate a satisfactory response after {max_attempts} attempts. Please try rephrasing your question." + Style.RESET_ALL)
                return

            # Process the approved response
            elapsed_time = time.time() - start_time
            conversation.files_context.update_last_api_call_timestamp()
            stop_thinking_spinner()
            conversation.cache_metrics.update(approved_response, elapsed_time)

            # Add the approved response to the main conversation
            result = await process_claude_response(approved_response, conversation, client, config)
            
            if isinstance(result, list):  # Tool results
                _handle_tool_results(result, conversation)
            elif result:
                _handle_final_response(result)
                break
            else:
                logger.warning("Received empty response from Claude")
                print(COLOR_ERROR + "I apologize, but I couldn't generate a proper response. Could you please rephrase your question?" + Style.RESET_ALL)
                break

        except Exception as e:
            elapsed_time = time.time() - start_time
            stop_thinking_spinner()
            logger.error(f"Error generating response: {e}")
            error_message = f"Failed to generate response: {str(e)}"
            conversation.add_message("assistant", [{"type": "text", "text": error_message}])
            raise APIError(error_message) from e
        
    # Print cache performance report after each response
    print(COLOR_SYSTEM + conversation.cache_metrics.generate_report() + Style.RESET_ALL)

async def handle_max_tokens_exceeded(response: anthropic.types.Message) -> Tuple[str, str]:
    """
    Handle the case where the response was truncated due to reaching max tokens.

    Args:
        response (anthropic.types.Message): The truncated response from Claude.

    Returns:
        Tuple[str, str]: A tuple containing the truncation message and any partial content.
    """
    truncation_message = (
        "I apologize, but my response was truncated due to reaching the maximum token limit. "
        "Here's what I managed to generate before being cut off:\n\n"
    )
    
    partial_content = ""
    for content in response.content:
        if content.type == 'text':
            partial_content += content.text

    truncation_message += "```\n" + partial_content + "\n```" + "\n\n"
    truncation_message += (
        "To get a complete response, you could try:\n"
        "1. Breaking your question into smaller, more focused parts.\n"
        "2. Simplifying your query if possible.\n"
        "3. If you're working with code or long text, consider sharing only the most relevant portions.\n"
        "Please feel free to rephrase or split your question, and I'll do my best to provide a complete answer."
    )
    
    logger.warning("Response truncated due to max tokens")
    return truncation_message, partial_content

async def _get_claude_response(conversation: Conversation, client: anthropic.Anthropic, config: Config) -> anthropic.types.Message:
    """Get a response from the Claude API."""
    logger.debug("Sending request to Claude API")
    
    system_message = conversation.system_message.get_message_for_api(conversation.files_context)
    conversation_messages = conversation.get_messages_for_api()

    response = client.messages.create(
        model=config.model_name,
        max_tokens=config.max_tokens,
        system=system_message,
        messages=conversation_messages,
        tools=TOOLS,
        tool_choice=TOOL_CHOICE,
        extra_headers=config.anthropic_headers
    )
    logger.debug(f"Received response from Claude API: {json.dumps(response.model_dump(), indent=2)}")
    _log_api_usage(response.usage)
    return response

def _log_api_usage(usage: anthropic.types.Usage) -> None:
    """Log the API usage information."""
    logger.info(f"API usage - Input tokens: {usage.input_tokens}, "
                f"Output tokens: {usage.output_tokens}, "
                f"Cache creation tokens: {getattr(usage, 'cache_creation_input_tokens', 0)}, "
                f"Cache read tokens: {getattr(usage, 'cache_read_input_tokens', 0)}")

def _handle_tool_results(results: List[Dict[str, Any]], conversation: Conversation) -> None:
    """Handle tool results by updating FilesContext and adding results to the conversation."""
    logger.info("Tool was used, processing results")
    for tool_result in results:
        tool_name = tool_result.get("tool_name")
        result_content = tool_result.get("result", {})
        is_error = result_content.get("is_error", False)

        if not is_error:
            # Find all keys containing 'file' (case-insensitive)
            file_keys = [key for key in result_content.keys() if 'file' in key.lower()]
            
            # Prioritize 'file_path' if it exists, otherwise use the first found key
            if 'file_path' in file_keys:
                file_path = result_content['file_path']
            elif file_keys:
                file_path = result_content[file_keys[0]]
            else:
                file_path = None

            file_content = result_content.get("file_content")
            
            if file_path:
                # Convert to absolute path if it's not already
                if not os.path.isabs(file_path):
                    file_path = os.path.abspath(file_path)

                if file_content is None and os.path.exists(file_path):
                    # Read file content if not provided but file exists
                    try:
                        with open(file_path, 'r') as f:
                            file_content = f.read()
                    except Exception as e:
                        logger.error(f"Error reading file {file_path}: {str(e)}")
                        file_content = None

                if file_content:
                    # Update FilesContext with the file content
                    relative_path = os.path.relpath(file_path)
                    conversation.files_context.update_file_in_context(relative_path, file_content, tool_name)
                    logger.info(f"Updated FilesContext with content from {relative_path}")
                    
                    # Add a reference to the file content in the conversation
                    tool_results_message = {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_result["tool_use_id"],
                                "content": json.dumps({
                                    "file_path": relative_path,
                                    "message": f"File content has been updated in the context. Use this reference to access the content from tool: {tool_name}"
                                }),
                                "is_error": False
                            }
                        ]
                    }
                else:
                    # Handle case where file was created but content is not available
                    tool_results_message = {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_result["tool_use_id"],
                                "content": json.dumps({
                                    "file_path": relative_path,
                                    "message": f"File was created or referenced by {tool_name} but content is not available in the context. You may need to use the read_file tool to access its content."
                                }),
                                "is_error": False
                            }
                        ]
                    }
            else:
                # Handle non-file results
                tool_results_message = {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_result["tool_use_id"],
                            "content": json.dumps(result_content),
                            "is_error": False
                        }
                    ]
                }
        else:
            # Handle error results
            tool_results_message = {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_result["tool_use_id"],
                        "content": json.dumps({
                            "error": result_content.get("error", "Unknown error occurred")
                        }),
                        "is_error": True
                    }
                ]
            }

        conversation.add_message("user", tool_results_message["content"])
        logger.info(f"Added result of {tool_name} to conversation")
        
        if is_error:
            logger.error(f"Error in tool {tool_name}: {result_content.get('error', 'Unknown error')}")

def format_ai_output(content: str) -> str:
    """
    Format AI output with proper indentation, removing outer JSON structure and labels.
    
    Args:
        content (str): The content to be formatted.
    
    Returns:
        str: Formatted and indented string.
    """
    # Parse the content as JSON to handle potential nested structures
    parsed = json.loads(content)
    # Extract the actual content (either 'reasoning' or 'response')
    actual_content = list(parsed.values())[0]
    # Use json.dumps for consistent indentation if the content is a complex structure
    if isinstance(actual_content, (dict, list)):
        return json.dumps(actual_content, indent=2)
    else:
        # For simple strings, split into lines and indent
        lines = actual_content.split('\n')
        return '\n'.join('  ' + line if line.strip() else line for line in lines)

def extract_reasoning(response: str) -> Tuple[str, str]:
    """
    Extract reasoning from the response if present.

    Args:
        response (str): The full response string.

    Returns:
        Tuple[str, str]: A tuple containing the extracted reasoning and the remaining response.
    """
    reasoning = ""
    if "<reasoning>" in response and "</reasoning>" in response:
        start = response.index("<reasoning>") + len("<reasoning>")
        end = response.index("</reasoning>")
        reasoning = response[start:end].strip()
        response = response[:start-len("<reasoning>")] + response[end+len("</reasoning>"):]
    return reasoning, response

def format_reasoning(reasoning: str) -> str:
    lines = reasoning.split("\n")
    return "\n".join(f"   > {line}" for line in lines)

def format_markdown_content(reasoning: Optional[str], response: str) -> str:
    """
    Format the reasoning and response into markdown content.

    Args:
        reasoning (Optional[str]): The extracted reasoning, if any.
        response (str): The main response content.

    Returns:
        str: Formatted markdown content.
    """
    markdown_content = ""
    if reasoning:
        markdown_content += f"{REASONING_EMOJI} **{REASONING_TITLE}**\n"
        markdown_content += "> " + reasoning.replace("\n", "\n> ") + "\n\n"
    
    markdown_content += f"{RESPONSE_EMOJI} **{RESPONSE_TITLE}**\n\n"
    markdown_content += response
    return markdown_content

def print_assistant_response(response: str, console: Optional[Console] = None) -> None:
    """
    Print the assistant's response in a formatted panel.

    This function extracts reasoning (if present), formats the content into markdown,
    and displays it in a Rich panel.

    Args:
        response (str): The full response string from the assistant.
        console (Optional[Console]): A Rich Console instance. If None, a new one will be created.

    Raises:
        ValueError: If the response string is empty.
    """
    if not response.strip():
        raise ValueError("Response cannot be empty")

    try:
        reasoning, final_response = extract_reasoning(response)
        markdown_content = format_markdown_content(reasoning, final_response)

        panel = Panel(
            Markdown(markdown_content),
            title=PANEL_TITLE,
            expand=False,
            border_style="cyan",
            padding=(1, 1)
        )
        
        if console is None:
            console = Console()
        
        console.print(panel)
        console.print()  # Add a newline for separation
    except Exception as e:
        console.print(f"[bold red]Error displaying response: {str(e)}[/bold red]") 

def _handle_final_response(result: str) -> None:
    print_assistant_response(result)

async def process_user_input(conversation: Conversation, user_input: str, client: anthropic.Anthropic, config: Config, wise_counsel: WiseCounsel, initial_review: InitialReview) -> bool:
    """
    Process user input and generate a response.

    This function handles both command inputs (starting with '/') and regular user messages.
    For regular messages, it checks if the input mentions 'project study' and if so, 
    adds relevant information about the project_structure status to the user's message.

    Args:
        conversation (Conversation): The current conversation object.
        user_input (str): The user's input string.
        client (anthropic.Anthropic): The Anthropic client for API calls.
        config (Config): The configuration object.
        wise_counsel (WiseCounsel): The WiseCounsel instance for response review.
        initial_review (InitialReview): The InitialReview instance for initial assessment.

    Returns:
        bool: True if the conversation should continue, False if it should end.

    Raises:
        Exception: Any exception that occurs during processing is logged and printed.
    """
    if user_input.startswith('/'):
        result = handle_command(user_input, conversation)
        if result == "exit":
            return False
    else:
        if "project study" in user_input.lower():
            project_structure_file = "project_structure.json"
            if not os.path.exists(project_structure_file):
                user_input += "\n\n[NOTE: project_structure output is not available. Consider running project_structure before project_study.]"
            elif (time.time() - os.path.getmtime(project_structure_file)) > 3600:  # 1 hour
                user_input += "\n\n[NOTE: project_structure output may be outdated. Consider running project_structure again before project_study.]"
            
            user_input += "\n\nBefore proceeding with project_study, please confirm that project_structure has been run recently."

        conversation.add_message("user", [{"type": "text", "text": user_input}])
        
        try:
            await generate_response(conversation, client, config, wise_counsel, initial_review)
        except Exception as e:
            logger.error(f"Error processing user input: {e}")
            print_error_message(str(e))
        return True

async def conversation_loop(conversation: Conversation, client: anthropic.Anthropic, config: Config, wise_counsel: WiseCounsel, initial_review: InitialReview) -> None:
    """
    Main conversation loop.

    Args:
        conversation (Conversation): The current conversation object.
        client (anthropic.Anthropic): The Anthropic client.
        config (Config): The configuration object.
        wise_counsel (WiseCounsel): The WiseCounsel instance for response review.
        initial_review (InitialReview): The InitialReview instance for initial assessment.
    """
    os.system('cls' if os.name == 'nt' else 'clear')
    
    print_welcome_message()
    
    while True:
        user_input = get_user_input()
        should_continue = await process_user_input(conversation, user_input, client, config, wise_counsel, initial_review)
        if not should_continue:
            break

    if conversation.cache_metrics.total_requests > 0:
        visualize_metrics(conversation.cache_metrics)
    else:
        print("No metrics to visualize. No requests were made.")

def visualize_metrics(metrics: CacheMetrics) -> None:
    if metrics.total_requests == 0:
        print("No metrics to visualize. No requests were made.")
        return

    plt.figure(figsize=(12, 6))
    avg_response_time = metrics.total_time / metrics.total_requests
    plt.plot(range(1, metrics.total_requests + 1), [avg_response_time] * metrics.total_requests, label='Average Response Time')
    plt.title('Average Response Time per Request')
    plt.xlabel('Request Number')
    plt.ylabel('Response Time (s)')
    plt.legend()
    plt.savefig('response_times.png')
    plt.close()

    print(f"Metrics visualization saved as 'response_times.png'")
    print(f"Total requests: {metrics.total_requests}")
    print(f"Average response time: {avg_response_time:.2f} seconds")

def main() -> None:
    """Main function to run the Codai application."""
    try:
        config = Config.load()
        client = anthropic.Anthropic(api_key=config.api_key)
        conversation = Conversation()
        files_context = FilesContext()

        check_console_encoding()
        
        # Initialize WiseCounsel
        wise_counsel = WiseCounsel(client, config.__dict__)
        initial_review = InitialReview(client, config.__dict__)
        
        # Main conversation loop
        os.system('cls' if os.name == 'nt' else 'clear')
        print_welcome_message()
        
        while True:
            user_input = get_user_input()
            if user_input.startswith('/'):
                result = handle_command(user_input, conversation)
                if result == "exit":
                    break
                # Continue the loop for other commands
            else:
                should_continue = asyncio.run(process_user_input(conversation, user_input, client, config, wise_counsel, initial_review))
                if not should_continue:
                    break

        if conversation.cache_metrics.total_requests > 0:
            visualize_metrics(conversation.cache_metrics)
        else:
            print("No metrics to visualize. No requests were made.")
            
    except ConfigurationError as e:
        logger.error(f"Configuration error: {e}")
        print(COLOR_ERROR + f"Configuration error: {str(e)}" + Style.RESET_ALL)
    except FileReadError as e:
        logger.error(f"File read error: {e}")
        print(COLOR_ERROR + f"File read error: {str(e)}" + Style.RESET_ALL)
    except APIError as e:
        logger.error(f"API error: {e}")
        print(COLOR_ERROR + f"API error: {str(e)}" + Style.RESET_ALL)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        print(COLOR_ERROR + f"An unexpected error occurred: {str(e)}" + Style.RESET_ALL)
    finally:
        logger.info("Codai session ended.")
        print(COLOR_SYSTEM + "Codai session ended." + Style.RESET_ALL)

if __name__ == "__main__":
    main()             