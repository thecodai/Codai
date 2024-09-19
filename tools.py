import os
import sys
import re
import logging
import datetime
from typing import Dict, Any, List, Set, Tuple
from pathlib import Path
import fnmatch
import ast
import codecs
import json
import time

from code_edit_tool import code_edit_tool

logger = logging.getLogger(__name__)

def read_file_with_encoding(file_path: str) -> str:
    """
    Attempt to read a file using multiple encodings.
    
    Args:
        file_path (str): The path to the file to be read.
    
    Returns:
        str: The contents of the file.
    
    Raises:
        FileReadError: If the file cannot be read with any of the attempted encodings.
    """
    encodings = ['utf-8', 'utf-16', 'ascii', 'iso-8859-1', 'cp1252']
    
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as file:
                content = file.read()
            logger.info(f"Successfully read file {file_path} with {encoding} encoding.")
            return content
        except UnicodeDecodeError:
            logger.warning(f"Failed to read {file_path} with {encoding} encoding. Trying next encoding.")
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {str(e)}")
            raise FileReadError(f"Error reading file {file_path}: {str(e)}")
    
    error_msg = f"Unable to read file {file_path} with any of the attempted encodings."
    logger.error(error_msg)
    raise FileReadError(error_msg)

def _list_files(tool_input: Dict[str, str]) -> Dict[str, Any]:
    """List files and folders in the specified directory."""
    path = tool_input.get("path", ".")
    logger.info(f"Listing files in path: {path}")
    if not os.path.exists(path):
        error_msg = f"Directory not found: {path}"
        logger.error(error_msg)
        return {"error": error_msg, "is_error": True}
    
    items = os.listdir(path)
    files = [f for f in items if os.path.isfile(os.path.join(path, f))]
    folders = [f for f in items if os.path.isdir(os.path.join(path, f))]
    
    result = f"Contents of directory: {path}\n"
    result += "=" * (24 + len(path)) + "\n"
    
    if not files and not folders:
        result += "(Empty directory)\n"
    else:
        if folders:
            result += "\nFolders:\n"
            for folder in sorted(folders):
                result += f"  📁 {folder}\n"
        if files:
            result += "\nFiles:\n"
            for file in sorted(files):
                result += f"  📄 {file}\n"
    
    logger.info(f"list_files tool result: {result}")
    return {"result": result, "is_error": False}

def _read_file(tool_input: Dict[str, str]) -> Dict[str, Any]:
    """Read the contents of the specified file using the robust reading method."""
    file_path = tool_input.get("file_path")
    logger.info(f"Attempting to read file: {file_path}")
    
    if not os.path.exists(file_path):
        error_msg = f"File not found: {file_path}"
        logger.error(error_msg)
        return {"error": error_msg, "is_error": True}
    
    try:
        file_content = read_file_with_encoding(file_path)
        relative_path = os.path.relpath(file_path)
        result = {
            "file_path": relative_path,
            "file_content": file_content
        }
        logger.info(f"Successfully read file: {file_path}")
        return result
    except FileReadError as e:
        error_msg = str(e)
        logger.error(error_msg)
        return {"error": error_msg, "is_error": True}
    except Exception as e:
        error_msg = f"An unexpected error occurred while reading file {file_path}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"error": error_msg, "is_error": True}

def read_files_in_folder(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Read the contents of all files in the specified folder, with option to include subfolders."""
    folder_path = tool_input.get("folder_path", "")
    include_subfolders = tool_input.get("include_subfolders", False)
    root_dir = os.getcwd()  # Get the current working directory as root
    target_dir = os.path.join(root_dir, folder_path)
    
    logger.info(f"Attempting to read files in folder: {target_dir} (include subfolders: {include_subfolders})")
    
    if not os.path.isdir(target_dir):
        error_msg = f"Folder not found or is not a directory: {target_dir}"
        logger.error(error_msg)
        return {"error": error_msg, "is_error": True}
    
    results = {}
    if include_subfolders:
        for root, _, files in os.walk(target_dir):
            for file in files:
                file_path = os.path.join(root, file)
                _process_file(file_path, root_dir, results)
    else:
        for item in os.listdir(target_dir):
            file_path = os.path.join(target_dir, item)
            if os.path.isfile(file_path):
                _process_file(file_path, root_dir, results)
    
    return {"results": results}

def _process_file(file_path: str, root_dir: str, results: Dict[str, Any]) -> None:
    """Helper function to process a single file and add it to the results."""
    try:
        file_content = read_file_with_encoding(file_path)
        relative_path = os.path.relpath(file_path, root_dir)
        results[relative_path] = {
            "file_content": file_content,
            "is_error": False
        }
        logger.info(f"Successfully read file: {relative_path}")
    except Exception as e:
        error_msg = f"An error occurred while reading file {relative_path}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        results[relative_path] = {"error": error_msg, "is_error": True}
  
def _create_file(tool_input: Dict[str, str]) -> Dict[str, Any]:
    """Create a new file with the specified content."""
    file_path = tool_input.get("file_path")
    content = tool_input.get("content", "")
    logger.info(f"Attempting to create file: {file_path}")
    
    try:
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(content)
        logger.info(f"Successfully created file: {file_path}")
        return {"message": f"File created successfully: {file_path}", "is_error": False}
    except Exception as e:
        error_msg = f"An error occurred while creating file {file_path}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"error": error_msg, "is_error": True}

def _create_folder(tool_input: Dict[str, str]) -> Dict[str, Any]:
    """Create a new folder at the specified path, handling existing folders."""
    folder_path = tool_input.get("folder_path")
    logger.info(f"Attempting to create folder: {folder_path}")
    
    try:
        path = Path(folder_path)
        if path.exists() and path.is_dir():
            logger.info(f"Folder already exists: {folder_path}")
            return {
                "message": f"Folder already exists: {folder_path}",
                "is_error": False,
                "folder_status": "existing"
            }
        
        path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Successfully created folder: {folder_path}")
        return {
            "message": f"Folder created successfully: {folder_path}",
            "is_error": False,
            "folder_status": "created"
        }
    except Exception as e:
        error_msg = f"An error occurred while creating folder {folder_path}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "error": error_msg,
            "is_error": True,
            "folder_status": "error"
        }

def parse_gitignore(gitignore_path: str) -> Set[str]:
    """Parse .gitignore file and return a set of ignore patterns."""
    ignore_patterns = set()
    if os.path.exists(gitignore_path):
        with open(gitignore_path, 'r') as gitignore_file:
            for line in gitignore_file:
                line = line.strip()
                if line and not line.startswith('#'):
                    # Preserve the original pattern, including any trailing slash
                    ignore_patterns.add(line)
    return ignore_patterns

def should_ignore(path: str, root: str, ignore_patterns: Set[str]) -> bool:
    """Check if a path should be ignored based on .gitignore rules."""
    relative_path = os.path.relpath(path, root)
    for pattern in ignore_patterns:
        # Remove trailing slash if present
        pattern = pattern.rstrip('/')
        if fnmatch.fnmatch(relative_path, pattern) or \
           fnmatch.fnmatch(relative_path, f"{pattern}/*") or \
           fnmatch.fnmatch(os.path.basename(path), pattern):
            return True
    return False

def read_exclude_dirs_from_file(file_path: str) -> Set[str]:
    """
    Read directories to exclude from a text file.
    The file can contain directories separated by commas or each on a new line.
    
    Args:
        file_path (str): Path to the text file containing directories to exclude.
    
    Returns:
        Set[str]: Set of directories to exclude.
    """
    exclude_dirs = set()
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Split by both commas and newlines
        dirs = re.split(r'[,\n]', content)
        
        # Strip whitespace and add non-empty directories to the set
        exclude_dirs = {d.strip() for d in dirs if d.strip()}
        
    except Exception as e:
        logger.error(f"Error reading exclude directories file: {str(e)}")
        print(f"Error reading file: {str(e)}")
    
    return exclude_dirs

def project_structure(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a JSON file representation of the project directory hierarchy, respecting .gitignore rules.
    
    Args:
        tool_input (Dict[str, Any]): A dictionary containing:
            - folder_path (str): The relative path of the folder to analyze.
            - output_path (str, optional): The relative path for the output JSON file.
            - interactive (bool, optional): Whether to seek user approval. Defaults to True.
            - exclude_dirs (List[str], optional): List of directories to exclude from traversal.
            - user_interaction_callback (callable, optional): A function to handle user interactions when interactive is True.
            - include_ignored (bool, optional): Whether to include files and directories that would be ignored by .gitignore rules. Defaults to False.

    Returns:
        Dict[str, Any]: A dictionary containing the result of the operation.
    """
    folder_path = tool_input.get("folder_path", "")
    output_path = tool_input.get("output_path", "")
    interactive = tool_input.get("interactive", True)
    exclude_dirs = set(tool_input.get("exclude_dirs", []))
    user_interaction_callback = tool_input.get("user_interaction_callback")
    include_ignored = tool_input.get("include_ignored", False)
    
    root_dir = os.getcwd()  # Get the current working directory as root
    target_dir = os.path.join(root_dir, folder_path)
    
    logger.info(f"Creating project structure for: {target_dir}")
    
    if not os.path.isdir(target_dir):
        error_msg = f"Folder not found or is not a directory: {target_dir}"
        logger.error(error_msg)
        return {"error": error_msg, "is_error": True}
    
    # Parse root .gitignore
    root_gitignore_path = os.path.join(root_dir, '.gitignore')
    root_ignore_patterns = parse_gitignore(root_gitignore_path)
    
    # Get list of directories to traverse, respecting .gitignore if include_ignored is False
    dirs_to_traverse = get_dirs_respecting_gitignore(target_dir, root_dir, root_ignore_patterns, include_ignored)
    
    if interactive:
        gitignore_status = "ignored" if include_ignored else "respected"
        if user_interaction_callback:
            dirs_to_traverse = user_interaction_callback({
                "action": "approve_dirs",
                "dirs": dirs_to_traverse,
                "exclude_dirs": list(exclude_dirs),
                "gitignore_status": gitignore_status
            })
        else:
            logger.info("No user_interaction_callback provided. Using default console-based approval.")
            print(f"The following directories will be traversed (.gitignore rules are {gitignore_status}):")
            for d in dirs_to_traverse:
                print(f"- {d}")
            while True:
                user_input = input(f"Do you approve this list? (yes/no): ").lower().strip()
                if user_input == 'yes':
                    break
                elif user_input == 'no':
                    print("Please choose an option:")
                    print("1. Enter directories to exclude (comma-separated)")
                    print("2. Provide a path to a .txt file with directories to exclude")
                    option = input("Enter your choice (1 or 2): ").strip()
                    
                    if option == '1':
                        exclude_input = input("Enter directories to exclude (comma-separated): ").strip()
                        user_excludes = {d.strip() for d in exclude_input.split(',')} if exclude_input else set()
                    elif option == '2':
                        file_path = input("Enter the path to the .txt file: ").strip()
                        user_excludes = read_exclude_dirs_from_file(file_path)
                    else:
                        print("Invalid option. No directories will be excluded.")
                        user_excludes = set()
                    
                    dirs_to_traverse = [d for d in dirs_to_traverse if d not in user_excludes]
                    break
                else:
                    print("Invalid input. Please enter 'yes' or 'no'.")
    
    exclude_dirs.update(set(d for d in os.listdir(target_dir) if os.path.isdir(os.path.join(target_dir, d)) and d not in dirs_to_traverse))
    
    def build_structure(dir_path: str, ignore_patterns: Set[str]) -> Dict[str, Any]:
        structure = {"name": os.path.basename(dir_path), "type": "directory", "children": []}
        
        # Parse folder-specific .gitignore and combine with root ignore patterns
        local_gitignore_path = os.path.join(dir_path, '.gitignore')
        local_ignore_patterns = parse_gitignore(local_gitignore_path)
        combined_ignore_patterns = ignore_patterns.union(local_ignore_patterns)
        
        try:
            items = os.listdir(dir_path)
            for item in items:
                item_path = os.path.join(dir_path, item)
                rel_path = os.path.relpath(item_path, target_dir)
                
                if include_ignored or not should_ignore(rel_path, root_dir, combined_ignore_patterns):
                    if rel_path not in exclude_dirs:
                        if os.path.isdir(item_path):
                            child_structure = build_structure(item_path, combined_ignore_patterns)
                            structure["children"].append(child_structure)
                        else:
                            structure["children"].append({"name": item, "type": "file"})
        except Exception as e:
            logger.error(f"Error processing directory {dir_path}: {str(e)}")
            structure["error"] = str(e)
        
        return structure
    
    project_structure = build_structure(target_dir, root_ignore_patterns)
    
    # Add summary information
    project_structure["summary"] = {
        "total_files": sum(1 for item in project_structure["children"] if item["type"] == "file"),
        "total_directories": sum(1 for item in project_structure["children"] if item["type"] == "directory"),
        "traversed_directories": dirs_to_traverse,
        "excluded_directories": list(exclude_dirs)
    }
    
    # Determine the output file path
    if not output_path:
        output_path = os.path.join(target_dir, "project_structure.json")
    else:
        output_path = os.path.join(root_dir, output_path)
    
    # Ensure the directory for the output file exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Create the JSON file
    try:
        with open(output_path, 'w') as json_file:
            json.dump(project_structure, json_file, indent=2)
        
        logger.info(f"Project structure JSON file created: {output_path}")
        return {
            "json_file_path": output_path,
            "is_error": False,
            "summary": project_structure["summary"]
        }
    except Exception as e:
        error_msg = f"Error creating JSON file: {str(e)}"
        logger.error(error_msg)
        return {"error": error_msg, "is_error": True}
    
def get_dirs_respecting_gitignore(dir_path: str, root_dir: str, ignore_patterns: Set[str], include_ignored: bool) -> List[str]:
    dirs = []
    for item in os.listdir(dir_path):
        item_path = os.path.join(dir_path, item)
        if os.path.isdir(item_path):
            relative_path = os.path.relpath(item_path, root_dir)
            if include_ignored or not should_ignore(relative_path, root_dir, ignore_patterns):
                dirs.append(item)
    return dirs

def project_study(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    project_root = tool_input.get("project_root", ".")
    folder_path = tool_input.get("folder_path", "")
    output_file = tool_input.get("output_file", "project_study.json")
    include_ignored = tool_input.get("include_ignored", False)
    structure_file_path = tool_input.get("structure_file_path", "project_structure.json")
    interactive_mode = tool_input.get("interactive_mode", False)
    
    if interactive_mode and not structure_file_path:
        structure_file_path = input("Please enter the relative path to the project structure file: ").strip()
    
    # Construct absolute paths for file operations
    abs_project_root = os.path.abspath(project_root)
    abs_structure_file_path = os.path.join(abs_project_root, structure_file_path)
    
    if not os.path.exists(abs_structure_file_path):
        return {
            "status": "error",
            "error_code": "PROJECT_STRUCTURE_NOT_FOUND",
            "message": f"Project structure file not found at {structure_file_path}. Please ensure the file exists and the path is correct.",
            "data": {
                "files_analyzed": 0,
                "analysis_time": 0,
                "project_structure_used": False
            }
        }
    
    # Load project structure data
    with open(abs_structure_file_path, 'r') as f:
        project_structure_data = json.load(f)
    
    # Initialize project data
    project_data = {
        "files": {},
        "functions": [],
        "imports": [],
        "relations": [],
        "summary": {}
    }
    
    # Analyze files
    for file_info in project_structure_data.get("children", []):
        if file_info["type"] == "file":
            rel_file_path = os.path.join(folder_path, file_info["name"])
            abs_file_path = os.path.join(abs_project_root, rel_file_path)
            file_analysis = analyze_file(abs_file_path)
            project_data["files"][rel_file_path] = file_analysis
            project_data["functions"].extend(file_analysis["functions"])
            project_data["imports"].extend(file_analysis["imports"])
    
    # Generate relations between files
    project_data["relations"] = generate_relations(project_data["files"])
    
    # Generate summary
    project_data["summary"] = generate_summary(project_data)
    
    # Save the project data to a JSON file
    output_path = os.path.join(folder_path, output_file)
    abs_output_path = os.path.join(abs_project_root, output_path)
    with open(abs_output_path, 'w', encoding='utf-8') as f:
        json.dump(project_data, f, indent=2)
    
    return {
        "status": "success",
        "message": f"Project study completed successfully. Output saved to: {output_path}",
        "data": {
            "output_file": output_path,
            "files_analyzed": len(project_data["files"]),
            "project_structure_used": True,
            "summary": project_data["summary"]
        }
    }

def analyze_imports(content: str) -> List[Dict[str, Any]]:
    tree = ast.parse(content)
    imports = []
    
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                import_info = {
                    "name": alias.name,
                    "alias": alias.asname,
                    "type": "standard" if alias.name in sys.stdlib_module_names else "third-party",
                    "from_import": isinstance(node, ast.ImportFrom),
                    "module": node.module if isinstance(node, ast.ImportFrom) else None,
                    "line": node.lineno
                }
                
                # Check if it's a local import
                if import_info["type"] == "third-party":
                    if import_info["from_import"] and import_info["module"] and "." in import_info["module"]:
                        import_info["type"] = "local"
                    elif not import_info["from_import"] and "." in import_info["name"]:
                        import_info["type"] = "local"
                
                imports.append(import_info)
    
    return imports

class BaseAnalyzer:
    def analyze_imports(self, content: str) -> List[Dict[str, Any]]:
        return []

    def analyze_functions(self, content: str) -> List[Dict[str, Any]]:
        return []

    def analyze_file(self, file_path: str) -> Dict[str, Any]:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        return {
            "size_bytes": len(content),
            "line_count": len(content.splitlines()),
            "imports": self.analyze_imports(content),
            "functions": self.analyze_functions(content)
        }

class PythonAnalyzer(BaseAnalyzer):
    def analyze_imports(self, content: str) -> List[Dict[str, Any]]:
        import_pattern = r'^(?:from\s+(\S+)\s+)?import\s+(.+)$'
        imports = []
        for line_num, line in enumerate(content.splitlines(), 1):
            match = re.match(import_pattern, line.strip())
            if match:
                from_module, imported_items = match.groups()
                for item in re.split(r'\s*,\s*', imported_items):
                    name, _, alias = item.partition(' as ')
                    imports.append({
                        "name": name.strip(),
                        "alias": alias.strip() or None,
                        "from_module": from_module,
                        "line": line_num
                    })
        return imports

    def analyze_functions(self, content: str) -> List[Dict[str, Any]]:
        function_pattern = r'^def\s+(\w+)\s*\((.*?)\):'
        functions = []
        for line_num, line in enumerate(content.splitlines(), 1):
            match = re.match(function_pattern, line.strip())
            if match:
                name, params = match.groups()
                functions.append({
                    "name": name,
                    "parameters": [p.strip() for p in params.split(',') if p.strip()],
                    "line_number": line_num
                })
        return functions

class JavaScriptAnalyzer(BaseAnalyzer):
    def analyze_imports(self, content: str) -> List[Dict[str, Any]]:
        import_pattern = r'^(?:import|export)\s+(.+?)\s+from\s+[\'"](.+?)[\'"]'
        imports = []
        for line_num, line in enumerate(content.splitlines(), 1):
            match = re.match(import_pattern, line.strip())
            if match:
                imported_items, module = match.groups()
                imports.append({
                    "name": imported_items.strip('{}'),
                    "from_module": module,
                    "line": line_num
                })
        return imports

    def analyze_functions(self, content: str) -> List[Dict[str, Any]]:
        function_pattern = r'^(?:function\s+(\w+)|(?:let|const)\s+(\w+)\s*=\s*(?:function|\([^)]*\)\s*=>))'
        functions = []
        for line_num, line in enumerate(content.splitlines(), 1):
            match = re.match(function_pattern, line.strip())
            if match:
                name = match.group(1) or match.group(2)
                functions.append({
                    "name": name,
                    "line_number": line_num
                })
        return functions

class GenericAnalyzer(BaseAnalyzer):
    pass  # Uses default implementations from BaseAnalyzer

def get_analyzer(file_path: str) -> BaseAnalyzer:
    _, ext = os.path.splitext(file_path)
    if ext.lower() == '.py':
        return PythonAnalyzer()
    elif ext.lower() in ['.js', '.jsx', '.ts', '.tsx']:
        return JavaScriptAnalyzer()
    elif ext.lower() in ['.cs', '.aspx', '.cshtml', '.vbhtml']:
        return CSharpAnalyzer()
    else:
        return GenericAnalyzer()

def analyze_file(file_path: str) -> Dict[str, Any]:
    analyzer = get_analyzer(file_path)
    return analyzer.analyze_file(file_path)
class CSharpAnalyzer(BaseAnalyzer):
    def analyze_imports(self, content: str) -> List[Dict[str, Any]]:
        imports = []
        # C# using statements
        using_pattern = r'^using\s+([\w.]+)\s*;'
        # ASP.NET Import directives
        import_directive_pattern = r'<%@\s*Import\s+Namespace\s*=\s*"([\w.]+)"\s*%>'
        
        for line_num, line in enumerate(content.splitlines(), 1):
            match = re.match(using_pattern, line.strip()) or re.match(import_directive_pattern, line.strip())
            if match:
                imports.append({
                    "name": match.group(1),
                    "line": line_num
                })
        return imports

    def analyze_functions(self, content: str) -> List[Dict[str, Any]]:
        functions = []
        # C# method pattern
        method_pattern = r'(public|private|protected|internal|static)?\s*[\w<>[\]]+\s+(\w+)\s*\([^)]*\)\s*{'
        # ASP.NET code-behind method pattern
        codebehind_pattern = r'protected\s+void\s+(\w+)\s*\([^)]*\)\s*{'
        
        for line_num, line in enumerate(content.splitlines(), 1):
            match = re.search(method_pattern, line) or re.search(codebehind_pattern, line)
            if match:
                functions.append({
                    "name": match.group(2) if match.group(2) else match.group(1),
                    "line_number": line_num
                })
        return functions

def generate_relations(files: Dict[str, Any]) -> List[Dict[str, str]]:
    """Generate relations between files based on imports."""
    relations = []
    for file_name, file_data in files.items():
        for imp in file_data["imports"]:
            for other_file, other_data in files.items():
                if file_name != other_file and any(func["name"] in imp for func in other_data["functions"]):
                    relations.append({
                        "from": file_name,
                        "to": other_file,
                        "type": "import"
                    })
    return relations

def generate_summary(project_data: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a summary of the project analysis."""
    return {
        "total_files": len(project_data["files"]),
        "total_functions": len(project_data["functions"]),
        "total_imports": len(project_data["imports"]),
        "total_relations": len(project_data["relations"]),
        "file_types": count_file_types(project_data["files"]),
        "largest_files": get_largest_files(project_data["files"], 5),
        "most_complex_files": get_most_complex_files(project_data["files"], 5)
    }

def count_file_types(files: Dict[str, Any]) -> Dict[str, int]:
    """Count the number of files of each type."""
    file_types = {}
    for file_name in files:
        ext = os.path.splitext(file_name)[1].lower() or 'unknown'
        file_types[ext] = file_types.get(ext, 0) + 1
    return file_types

def get_largest_files(files: Dict[str, Any], n: int) -> List[Tuple[str, int]]:
    """Get the n largest files by size."""
    return sorted([(name, data["size_bytes"]) for name, data in files.items()], 
                  key=lambda x: x[1], reverse=True)[:n]

def get_most_complex_files(files: Dict[str, Any], n: int) -> List[Tuple[str, int]]:
    """Get the n most complex files based on the number of functions."""
    return sorted([(name, len(data["functions"])) for name, data in files.items()], 
                  key=lambda x: x[1], reverse=True)[:n]

def intelligent_edit(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update the content of a file, either by replacing the entire content or modifying a specific function or class.

    Args:
        tool_input (Dict[str, Any]): A dictionary containing:
            - file_path (str): The path of the file to edit.
            - new_content (str): The new content to be written to the file.
            - target (str, optional): The name of the function or class to update.
            - mode (str): The mode of editing ('replace', 'append', or 'prepend').

    Returns:
        Dict[str, Any]: A dictionary containing the result of the operation:
            - message (str): A success message if the operation was successful.
            - error (str): An error message if the operation failed.
            - is_error (bool): Indicates whether an error occurred.
    """
    file_path = tool_input.get("file_path")
    new_content = tool_input.get("new_content")
    target = tool_input.get("target")
    mode = tool_input.get("mode", "replace")

    try:
        # Read the original content of the file, handling BOM if present
        with codecs.open(file_path, 'r', encoding='utf-8-sig') as file:
            original_content = file.read()

        if target:
            # Update a specific target (function or class) within the file
            updated_content = update_target(original_content, new_content, target, mode)
        else:
            # Update the entire file content based on the specified mode
            if mode == "replace":
                updated_content = new_content
            elif mode == "append":
                updated_content = original_content + "\n" + new_content
            elif mode == "prepend":
                updated_content = new_content + "\n" + original_content
            else:
                return {"error": f"Invalid mode: {mode}", "is_error": True}

        # Write the updated content back to the file, preserving BOM if it was present
        with codecs.open(file_path, 'w', encoding='utf-8-sig') as file:
            file.write(updated_content)

        return {
            "message": f"File {file_path} updated successfully.",
            "is_error": False
        }
    except FileNotFoundError:
        return {"error": f"File not found: {file_path}", "is_error": True}
    except PermissionError:
        return {"error": f"Permission denied: {file_path}", "is_error": True}
    except Exception as e:
        return {"error": f"An error occurred: {str(e)}", "is_error": True}

def update_target(content: str, new_content: str, target: str, mode: str) -> str:
    """
    Update a specific function or class within the file content.

    Args:
        content (str): The original file content.
        new_content (str): The new content to be added or used for replacement.
        target (str): The name of the function or class to update.
        mode (str): The mode of editing ('replace', 'append', or 'prepend').

    Returns:
        str: The updated file content.

    Raises:
        ValueError: If the target is not found in the file.
    """
    tree = ast.parse(content)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == target:
            start_line = node.lineno - 1
            end_line = node.end_lineno
            lines = content.split('\n')
            if mode == "replace":
                lines[start_line:end_line] = new_content.split('\n')
            elif mode == "append":
                lines[end_line:end_line] = new_content.split('\n')
            elif mode == "prepend":
                lines[start_line:start_line] = new_content.split('\n')
            return '\n'.join(lines)
    
    raise ValueError(f"Target {target} not found in the file.")

def get_current_datetime(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get the current date and time.

    Args:
        tool_input (Dict[str, Any]): An empty dictionary as this tool doesn't require any input.

    Returns:
        Dict[str, Any]: A dictionary containing the current date and time information:
            - current_datetime (str): The current date and time in ISO format.
            - current_date (str): The current date in YYYY-MM-DD format.
            - current_time (str): The current time in HH:MM:SS format.
            - timezone (str): The name of the current timezone.
    """
    now = datetime.datetime.now()
    return {
        "current_datetime": now.isoformat(),
        "current_date": now.date().isoformat(),
        "current_time": now.time().isoformat(),
        "timezone": now.astimezone().tzname()
    }

def code_change_analysis_action_plan(tool_input):
    """
    Generate an action plan for code change analysis based on the provided input.

    Args:
    tool_input (dict): A dictionary containing the following keys:
        - user_request (str): The original user request for code changes.
        - project_folder (str, optional): The relative path to the project folder. Defaults to current directory ('.').
        - project_structure_file (str, optional): The name of the project structure JSON file. Defaults to "project_structure.json".
        - project_study_file (str, optional): The name of the project study JSON file. Defaults to "project_study.json".
        - additional_context (str, optional): Any additional context for the code change analysis. Defaults to an empty string.
        - interactive_mode (bool, optional): Whether to include interactive steps in the action plan. Defaults to True.

    Returns:
    dict: A dictionary containing:
        - message (str): A success message.
        - action_plan_file (str): The relative path to the saved action plan file.
        - project_folder (str): The relative path to the project folder.
        - is_error (bool): False if the operation was successful.
        - next_action (str): A suggestion for the next action to take.

    Raises:
    ValueError: If the specified project folder does not exist.
    """
    user_request = tool_input.get("user_request")
    project_folder = tool_input.get("project_folder", ".")
    project_structure_file = tool_input.get("project_structure_file", "project_structure.json")
    project_study_file = tool_input.get("project_study_file", "project_study.json")
    additional_context = tool_input.get("additional_context", "")
    interactive_mode = tool_input.get("interactive_mode", True)  # New parameter

    if not os.path.isdir(project_folder):
        raise ValueError(f"The specified project folder does not exist: {project_folder}")

    logger.info(f"Generating code change analysis action plan for project folder: {project_folder}")

    # Define the action plan as a data structure
    action_plan = {
        "project_folder": project_folder,  # Add project_folder to the action plan
        "original_request": user_request,
        "additional_context": additional_context,
        "preliminary_steps": [],
        "reports": [
            {
                "name": "Affected Files Report",
                "steps": [
                    "Analyze the project structure and identify all files that may be affected by the requested changes.",
                    "List these files along with their relative paths in the project.",
                    "Provide a brief explanation of why each file is considered affected."
                ]
            },
            {
                "name": "Implementation Strategy Report",
                "steps": [
                    "Outline a step-by-step plan for implementing the requested changes.",
                    "Break down the implementation into manageable tasks.",
                    "Identify any dependencies between tasks and suggest an order of execution."
                ]
            },
            {
                "name": "Risk Assessment Report",
                "steps": [
                    "Evaluate potential risks associated with the proposed changes.",
                    "Consider factors such as system stability, performance impacts, and potential side effects.",
                    "Suggest mitigation strategies for each identified risk."
                ]
            },
            {
                "name": "Impact Analysis Report",
                "steps": [
                    "Analyze how the proposed changes might affect other parts of the system.",
                    "Identify any components, modules, or services that may need to be updated as a result of these changes.",
                    "Assess the potential impact on system architecture and design patterns."
                ]
            },
            {
                "name": "Testing and Validation Plan",
                "steps": [
                    "Propose a comprehensive testing strategy for the changes.",
                    "Identify specific test cases that should be developed or updated.",
                    "Suggest integration and system-level tests to ensure overall system integrity."
                ]
            }
        ],
        "post_report_steps": []
    }

    if interactive_mode:
        action_plan["post_report_steps"] = [
            {
                "name": "Present Proposed Changes",
                "steps": [
                    "Summarize the findings from all reports.",
                    "Present a clear and concise overview of the proposed changes.",
                    "Highlight potential risks and mitigation strategies."
                ]
            },
            {
                "name": "User Approval",
                "steps": [
                    "Present the proposed changes to the user for review.",
                    "Address any questions or concerns raised by the user.",
                    "Obtain explicit approval from the user to proceed with the changes."
                ]
            },
            {
                "name": "Apply Changes",
                "steps": [
                    "Call the intelligent_edit tool to apply the approved changes.",
                    "Provide the tool with the necessary information from the reports and user approval.",
                    "Execute the changes in a controlled manner, following the implementation strategy."
                ]
            }
        ]
    else:
        action_plan["post_report_steps"] = [
            {
                "name": "Apply Changes",
                "steps": [
                    "Call the intelligent_edit tool to apply the changes based on the reports.",
                    "Execute the changes in a controlled manner, following the implementation strategy."
                ]
            }
        ]

    # Check if files exist and add preliminary steps if necessary
    if not os.path.exists(os.path.join(project_folder, project_structure_file)):
        action_plan["preliminary_steps"].append({
            "name": "Generate Project Structure File",
            "file": project_structure_file,
            "steps": [
                "Create a JSON file to represent the project structure",
                "Include information about directories, files, and their relationships",
                "Ensure the file is properly formatted and valid JSON"
            ]
        })
    
    if not os.path.exists(os.path.join(project_folder, project_study_file)):
        action_plan["preliminary_steps"].append({
            "name": "Generate Project Study File",
            "file": project_study_file,
            "steps": [
                "Create a JSON file to store project study information",
                "Include relevant project metadata, goals, and constraints",
                "Ensure the file is properly formatted and valid JSON"
            ]
        })
    
    # Save action plan to a file in JSON format
    action_plan_file = os.path.join(project_folder, "code_change_analysis_action_plan.json")
    with open(action_plan_file, "w") as f:
        json.dump(action_plan, f, indent=2)

    # Use relative paths in the return dictionary
    relative_action_plan_file = os.path.relpath(action_plan_file, start=os.getcwd())

    return {
        "message": f"Code change analysis action plan generated and saved to {relative_action_plan_file}. Next, call the code_change_analysis_planner to determine the next step in the analysis process.",
        "action_plan_file": relative_action_plan_file,
        "project_folder": project_folder,
        "is_error": False,
        "next_action": f"Call code_change_analysis_planner with the following input: {{'project_folder': '{project_folder}', 'action_plan_file': '{os.path.basename(action_plan_file)}'}}"
    }

def _get_all_files(structure: Dict[str, Any]) -> List[str]:
    """Recursively get all file names from the project structure."""
    files = []
    if structure["type"] == "file":
        return [structure["name"]]
    for child in structure.get("children", []):
        child_files = _get_all_files(child)
        files.extend(child_files)  # Add child files directly without joining paths
    return files

def code_change_analysis_planner(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Read the action plan and determine the next analysis to be conducted, including preliminary steps,
    reports, and post-report steps with review and progress update steps.

    Args:
        tool_input (Dict[str, Any]): A dictionary containing:
            - project_folder (str): Relative path to the project folder.
            - action_plan_file (str): Name of the action plan file.

    Returns:
        Dict[str, Any]: A dictionary containing:
            - message (str): Description of the next action.
            - next_step (str): Name of the next step to be executed.
            - step_type (str): Type of the next step (preliminary step, report, or post_report step).
            - action (str): Action to be taken (execute, generate, or review).
            - step_name (str): Name of the specific step.
            - progress_update_file (str): Relative path to the progress update file.
            - project_folder (str): Relative path to the project folder.
            - is_error (bool): False if the operation was successful.
    """
    project_folder = tool_input.get("project_folder", ".")
    action_plan_file = tool_input.get("action_plan_file", "code_change_analysis_action_plan.json")
    
    action_plan_path = os.path.join(project_folder, action_plan_file)
    progress_update_path = os.path.join(project_folder, "code_change_analysis_progress.json")
    
    if not os.path.exists(action_plan_path):
        return {"error": f"Action plan file not found: {action_plan_file}", "project_folder": project_folder, "is_error": True}
    
    with open(action_plan_path, 'r') as f:
        action_plan = json.load(f)
    
    # Extract and expand all steps with review and progress update
    all_steps = []
    
    # Preliminary steps
    for step in action_plan.get("preliminary_steps", []):
        all_steps.append({"name": f"Execute: {step['name']}", "type": "preliminary step", "action": "execute"})
        all_steps.append({"name": f"Review and Update Progress: {step['name']}", "type": "review", "action": "review"})
    
    # Reports
    for report in action_plan.get("reports", []):
        all_steps.append({"name": report["name"], "type": "report", "action": "generate"})
        all_steps.append({"name": f"Review and Update Progress: {report['name']}", "type": "review", "action": "review"})
    
    # Post-report steps
    for step in action_plan.get("post_report_steps", []):
        all_steps.append({"name": f"Execute: {step['name']}", "type": "post_report step", "action": "execute"})
        all_steps.append({"name": f"Review and Update Progress: {step['name']}", "type": "review", "action": "review"})
    
    # Check existing progress or initialize new progress
    if os.path.exists(progress_update_path):
        with open(progress_update_path, 'r') as f:
            progress = json.load(f)
    else:
        progress = {step["name"]: {"status": "Not Started"} for step in all_steps}
    
    # Determine next step to be executed
    next_step = next((step for step in all_steps if progress[step["name"]]["status"] != "Completed"), None)
    
    if next_step:
        progress[next_step["name"]]["status"] = "In Progress"
        step_type = next_step["type"]
        action = next_step["action"]
        step_name = next_step["name"].split(": ")[-1] if ": " in next_step["name"] else next_step["name"]
    else:
        return {
            "message": "All steps, reports, and post-report steps have been completed.",
            "project_folder": project_folder,
            "is_error": False
        }
    
    # Save updated progress
    with open(progress_update_path, 'w') as f:
        json.dump(progress, f, indent=2)
    
    # Use relative paths in the return dictionary
    relative_progress_update_path = os.path.relpath(progress_update_path, start=os.getcwd())
    
    return {
        "message": f"Next action: {action} {step_type} - {step_name}",
        "next_step": next_step["name"],
        "step_type": step_type,
        "action": action,
        "step_name": step_name,
        "progress_update_file": relative_progress_update_path,
        "project_folder": project_folder,
        "is_error": False
    }

def generate_code_change_analysis_report(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Provide instructions for generating the next code change analysis report based on the progress update file.

    Args:
        tool_input (Dict[str, Any]): A dictionary containing:
            - project_folder (str): Path to the project folder.
            - progress_update_file (str): Name of the progress update file.

    Returns:
        Dict[str, Any]: A dictionary containing the report generation instructions.
    """
    project_folder = tool_input.get("project_folder", ".")
    progress_update_file = tool_input.get("progress_update_file", "code_change_analysis_progress.json")
    
    progress_update_path = os.path.join(project_folder, progress_update_file)
    
    if not os.path.exists(progress_update_path):
        return {"error": f"Progress update file not found: {progress_update_path}", "is_error": True}
    
    with open(progress_update_path, 'r') as f:
        progress = json.load(f)
    
    next_report = next((report for report in progress if progress[report]["status"] == "In Progress"), None)
    
    if not next_report:
        return {"message": "No reports left to generate.", "is_error": False}
    
    report_instructions = f"""
    Please generate the following report: {next_report}

    This report should include:

    1. Detailed analysis based on the project structure and files
    2. Specific recommendations and findings
    3. Any relevant code snippets or file references

    Use the project structure and study files in the project folder for reference.
    Be thorough and provide actionable insights.
    """
    
    return {
        "message": f"Instructions for generating report: {next_report}",
        "report_name": next_report,
        "instructions": report_instructions,
        "is_error": False
    }

def save_code_change_analysis_report(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Save the AI-generated code change analysis report and update the progress file.

    Args:
        tool_input (Dict[str, Any]): A dictionary containing:
            - project_folder (str): Path to the project folder.
            - report_name (str): Name of the report.
            - report_content (str): The content of the generated report.
            - progress_update_file (str): Name of the progress update file.

    Returns:
        Dict[str, Any]: A dictionary containing the result of the save operation.
    """
    project_folder = tool_input.get("project_folder", ".")
    report_name = tool_input.get("report_name")
    report_content = tool_input.get("report_content")
    progress_update_file = tool_input.get("progress_update_file", "code_change_analysis_progress.json")
    
    if not all([report_name, report_content]):
        return {"error": "Missing required input: report_name or report_content", "is_error": True}
    
    # Save the report
    report_filename = f"{report_name.lower().replace(' ', '_')}.md"
    report_path = os.path.join(project_folder, "code_change_analysis", report_filename)
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    
    with open(report_path, 'w') as f:
        f.write(report_content)
    
    # Update progress
    progress_update_path = os.path.join(project_folder, progress_update_file)
    with open(progress_update_path, 'r') as f:
        progress = json.load(f)
    
    progress[report_name]["status"] = "Completed"
    
    with open(progress_update_path, 'w') as f:
        json.dump(progress, f, indent=2)
    
    return {
        "message": f"Generated report saved: {report_name}",
        "report_file": report_path,
        "is_error": False
    }

def review_and_update_progress(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Review the outcome of a step and update the progress file for execution, generation, and review steps.

    Args:
        tool_input (Dict[str, Any]): A dictionary containing:
            - project_folder (str): Path to the project folder.
            - step_name (str): Name of the step to review.
            - step_type (str): Type of the step (preliminary step, report, or post_report step).
            - action (str): The action that was performed (execute, generate, or review).
            - outcome (str): Description of the step's outcome.
            - status (str): The status of the step (Completed, Failed, In Progress).

    Returns:
        Dict[str, Any]: A dictionary containing the review result and updated progress information.

    Raises:
        ValueError: If required input parameters are missing or invalid.
        IOError: If there's an error reading from or writing to the progress file.
    """
    # Input validation
    required_fields = ["project_folder", "step_name", "step_type", "action", "outcome", "status"]
    if not all(field in tool_input for field in required_fields):
        raise ValueError("Missing required input parameters")

    project_folder = tool_input["project_folder"]
    step_name = tool_input["step_name"]
    step_type = tool_input["step_type"]
    action = tool_input["action"]
    outcome = tool_input["outcome"]
    status = tool_input["status"]

    # Validate input values
    if step_type not in ["preliminary step", "report", "post_report step"]:
        raise ValueError("Invalid step_type. Must be 'preliminary step', 'report', or 'post_report step'")

    if action not in ["execute", "generate", "review"]:
        raise ValueError("Invalid action. Must be 'execute', 'generate', or 'review'")

    if status not in ["Completed", "Failed", "In Progress"]:
        raise ValueError("Invalid status. Must be 'Completed', 'Failed', or 'In Progress'")

    progress_update_path = os.path.join(project_folder, "code_change_analysis_progress.json")
    lock_file = progress_update_path + ".lock"

    def acquire_lock(lock_file: str, timeout: int = 10) -> bool:
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                with open(lock_file, 'x'):  # Try to create the lock file
                    return True
            except FileExistsError:
                time.sleep(0.1)  # Wait a bit before trying again
        return False

    def release_lock(lock_file: str) -> None:
        try:
            os.remove(lock_file)
        except FileNotFoundError:
            pass  # If the file is already gone, that's fine

    try:
        # Acquire lock
        if not acquire_lock(lock_file):
            raise IOError("Unable to acquire lock for progress file")

        # Read existing progress
        try:
            with open(progress_update_path, 'r') as f:
                progress = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            progress = {}

        if action in ["execute", "generate"]:
            # Update progress for execution or generation steps
            action_step_name = f"Execute: {step_name}" if action == "execute" else step_name
            review_step_name = f"Review and Update Progress: {step_name}"

            progress[action_step_name] = {
                "status": status,
                "outcome": outcome
            }
            progress[review_step_name] = {
                "status": "Completed"
            }

        elif action == "review":
            # Update progress for review steps
            progress[step_name] = {
                "status": status,
                "outcome": outcome
            }

        # Write updated progress
        temp_file = progress_update_path + '.tmp'
        with open(temp_file, 'w') as f:
            json.dump(progress, f, indent=2)
        os.replace(temp_file, progress_update_path)  # Atomic operation

    except IOError as e:
        raise IOError(f"Error accessing progress file: {str(e)}")
    finally:
        release_lock(lock_file)

    # Prepare review result
    review_result = {
        "message": f"Progress updated for {step_name}",
        "step_name": step_name,
        "step_type": step_type,
        "action": action,
        "status": status,
        "outcome": outcome,
        "progress_update_file": progress_update_path,
        "is_error": False
    }

    return review_result

def execute_tool(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a tool and return the result.

    Args:
        tool_name (str): The name of the tool to execute.
        tool_input (Dict[str, Any]): The input parameters for the tool.

    Returns:
        Dict[str, Any]: The result of the tool execution.
    """
    logger.debug(f"Executing tool: {tool_name} with input: {tool_input}")
    try:
        if tool_name == "list_files":
            return _list_files(tool_input)
        elif tool_name == "read_file":
            return _read_file(tool_input)
        elif tool_name == "read_files_in_folder":
            return read_files_in_folder(tool_input)
        elif tool_name == "create_file":
            return _create_file(tool_input)
        elif tool_name == "create_folder":
            return _create_folder(tool_input)
        elif tool_name == "project_structure":
            return project_structure(tool_input)
        elif tool_name == "project_study":
            return project_study(tool_input)
        elif tool_name == "code_change_analysis_action_plan":
            return code_change_analysis_action_plan(tool_input)
        elif tool_name == "code_change_analysis_planner":
            return code_change_analysis_planner(tool_input)
        elif tool_name == "generate_code_change_analysis_report":
            return generate_code_change_analysis_report(tool_input)
        elif tool_name == "save_code_change_analysis_report":
            return save_code_change_analysis_report(tool_input)
        elif tool_name == "review_and_update_progress":
            return review_and_update_progress(tool_input)
        elif tool_name == "intelligent_edit":
            return intelligent_edit(tool_input)
        elif tool_name == "code_edit_tool":
            return code_edit_tool(tool_input)
        elif tool_name == "get_current_datetime":
            return get_current_datetime(tool_input)
        else:
            error_msg = f"Unknown tool: {tool_name}"
            logger.error(error_msg)
            return {"error": error_msg, "is_error": True}
    except Exception as e:
        error_msg = f"An error occurred while executing tool {tool_name}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"error": error_msg, "is_error": True}

# Define tools
TOOLS = [
    {
        "name": "list_files",
        "description": "List files and folders in a specified directory. Use this when asked about project structure or file listings.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The directory path to list files from. Use '.' for current directory."
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "read_file",
        "description": "Read the contents of a specified file. Use this when asked about file contents or to analyze code.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The path of the file to read."
                }
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "read_files_in_folder",
        "description": "Read the contents of all files in a specified folder, with option to include subfolders. Uses relative paths and root as default.",
        "input_schema": {
            "type": "object",
            "properties": {
                "folder_path": {
                    "type": "string",
                    "description": "The relative path of the folder containing the files to read. Use empty string or '.' for root directory."
                },
                "include_subfolders": {
                    "type": "boolean",
                    "description": "Whether to include files from subfolders (default: false)."
                }
            },
            "required": ["folder_path"]
        }
    },
    {
        "name": "create_file",
        "description": "Create a new file with specified content. Use this when asked to create a new file or save content to a file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The path where the new file should be created."
                },
                "content": {
                    "type": "string",
                    "description": "The content to be written to the new file."
                }
            },
            "required": ["file_path", "content"]
        }
    },
    {
        "name": "create_folder",
        "description": "Create a new folder at the specified path. If the folder already exists, it will be reported as such.",
        "input_schema": {
            "type": "object",
            "properties": {
                "folder_path": {
                    "type": "string",
                    "description": "The path where the new folder should be created."
                }
            },
            "required": ["folder_path"]
        }
    },
    {
        "name": "project_structure",
        "description": "Create a JSON file representation of the project directory hierarchy, respecting .gitignore rules. Supports interactive mode and custom directory exclusions. The JSON file is created either in the specified output path or in the project folder if no path is provided.",
        "input_schema": {
            "type": "object",
            "properties": {
                "folder_path": {
                    "type": "string",
                    "description": "The relative path of the folder to analyze. Use empty string or '.' for root directory."
                },
                "include_ignored": {
                    "type": "boolean",
                    "description": "Whether to include files and directories that would be ignored by .gitignore rules. Default is false."
                },
                "output_path": {
                    "type": "string",
                    "description": "The relative path where the JSON file should be created. If not provided, it will be created in the project folder."
                },
                "interactive": {
                    "type": "boolean",
                    "description": "Whether to run in interactive mode, allowing user approval of directories to traverse. Default is true."
                },
                "exclude_dirs": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "List of directories to exclude from the analysis."
                }
            },
            "required": ["folder_path"]
        }
    },
    {
        "name": "project_study",
        "description": "Analyze the project structure, read all files, and create a JSON file with comprehensive project information. Uses relative paths for all file and folder references.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_root": {
                    "type": "string",
                    "description": "The relative path to the project root folder. Default is '.' (current directory)."
                },
                "folder_path": {
                    "type": "string",
                    "description": "The relative path of the folder to analyze, from the project root. Use empty string or '.' for root directory."
                },
                "output_file": {
                    "type": "string",
                    "description": "The name of the output JSON file, relative to the analyzed folder. Default is 'project_study.json'."
                },
                "include_ignored": {
                    "type": "boolean",
                    "description": "Whether to include files and directories that would be ignored by .gitignore rules. Default is false."
                },
                "structure_file_path": {
                    "type": "string",
                    "description": "The relative path to the project_structure.json file from the project root. Default is 'project_structure.json'."
                },
                "interactive_mode": {
                    "type": "boolean",
                    "description": "Whether to run in interactive mode, allowing user input if required information is not provided. Default is false."
                }
            },
            "required": ["folder_path"]
        }
    },
    {
        "name": "intelligent_edit",
        "description": "Update the content of a file based on prior code change analysis. This tool must be used after code_change_analysis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The path of the file to edit."
                },
                "new_content": {
                    "type": "string",
                    "description": "The new content to be written to the file."
                },
                "target": {
                    "type": "string",
                    "description": "Optional. The name of the function or class to update. If not provided, the entire file content will be replaced."
                },
                "mode": {
                    "type": "string",
                    "enum": ["replace", "append", "prepend"],
                    "description": "The mode of editing. 'replace' will replace the target, 'append' will add to the end, 'prepend' will add to the beginning."
                },
                "analysis_result": {
                    "type": "object",
                    "description": "The result of prior code_change_analysis. This is required."
                }
            },
            "required": ["file_path", "new_content", "mode", "analysis_result"]
        }
    },
    {
        "name": "code_edit_tool",
        "description": "Edit multiple code files based on AI-generated instructions. The 'config' object should align with the settings in config.yaml. If not provided or partially provided, missing values will be automatically filled from config.yaml. Ensure that any config values passed here are compatible with those in config.yaml.",
        "input_schema": {
            "type": "object",
            "properties": {
                "files": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                            "instructions": {"type": "string"}
                        },
                        "required": ["path", "content", "instructions"]
                    }
                },
                "project_context": {"type": "string"},
                "config": {
                    "type": "object",
                    "properties": {
                        "model_name": {"type": "string"},
                        "max_tokens": {"type": "integer"},
                        "anthropic_headers": {"type": "object"},
                        "interactive_mode": {"type": "boolean"},
                        "api_key": {"type": "string"}
                    }
                }
            },
            "required": ["files", "project_context", "config"]
        }
    },
    {
        "name": "get_current_datetime",
        "description": "Get the current date and time. Use this when you need to know the current date, time, or timezone.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "code_change_analysis_action_plan",
        "description": """
        Generate an action plan for code change analysis, outlining 5 reports to be created:
        1. Affected Files Report
        2. Implementation Strategy Report
        3. Risk Assessment Report
        4. Impact Analysis Report
        5. Testing and Validation Plan
        The action plan also includes post-report steps for presenting changes, getting user approval, and applying changes.
        The action plan is saved as a JSON file in the project folder.
        """,
        "input_schema": {
            "type": "object",
            "properties": {
                "user_request": {
                    "type": "string",
                    "description": "The user's request for code changes."
                },
                "project_folder": {
                    "type": "string",
                    "description": "Path to the project folder. All operations and file paths will be relative to this folder."
                },
                "project_structure_file": {
                    "type": "string",
                    "description": "Name of the JSON file containing the current project structure, relative to the project folder."
                },
                "project_study_file": {
                    "type": "string",
                    "description": "Name of the JSON file containing the project study results, relative to the project folder."
                },
                "additional_context": {
                    "type": "string",
                    "description": "Any additional context or information relevant to the code change analysis."
                }
            },
            "required": ["user_request", "project_folder"]
        }
    },
    {
        "name": "code_change_analysis_planner",
        "description": """
        Read the code change analysis action plan and determine the next analysis to be conducted.
        This includes preliminary steps, reports, and post-report steps.
        Creates or updates a progress update file showing which steps are done and which remain.
        """,
        "input_schema": {
            "type": "object",
            "properties": {
                "project_folder": {
                    "type": "string",
                    "description": "Path to the project folder."
                },
                "action_plan_file": {
                    "type": "string",
                    "description": "Name of the action plan file."
                }
            },
            "required": ["project_folder"]
        }
    },
    {
        "name": "review_and_update_progress",
        "description": """
        Review the outcome of a step in the code change analysis process and update the progress file.
        This tool should be used after each step to ensure proper documentation and tracking of the analysis process.
        It now supports preliminary steps, reports, and post-report steps.
        """,
        "input_schema": {
            "type": "object",
            "properties": {
                "project_folder": {
                    "type": "string",
                    "description": "Path to the project folder."
                },
                "step_name": {
                    "type": "string",
                    "description": "Name of the step to review."
                },
                "step_type": {
                    "type": "string",
                    "enum": ["preliminary step", "report", "post_report step"],
                    "description": "Type of the step (preliminary step, report, or post_report step)."
                },
                "action": {
                    "type": "string",
                    "enum": ["execute", "generate", "review"],
                    "description": "The action that was performed."
                },
                "outcome": {
                    "type": "string",
                    "description": "Description of the step's outcome."
                },
                "status": {
                    "type": "string",
                    "enum": ["Completed", "Failed", "In Progress"],
                    "description": "The status of the step."
                }
            },
            "required": ["project_folder", "step_name", "step_type", "action", "outcome", "status"]
        }
    },    
    {
        "name": "generate_code_change_analysis_report",
        "description": """
        Provide instructions for generating the next code change analysis report based on the progress update file.
        Returns instructions for report generation without saving the report.
        """,
        "input_schema": {
            "type": "object",
            "properties": {
                "project_folder": {
                    "type": "string",
                    "description": "Path to the project folder."
                },
                "progress_update_file": {
                    "type": "string",
                    "description": "Name of the progress update file."
                }
            },
            "required": ["project_folder"]
        }
    },
    {
        "name": "save_code_change_analysis_report",
        "description": """
        Save the AI-generated code change analysis report and update the progress file.
        This tool should be used after the report content has been generated based on the instructions.
        """,
        "input_schema": {
            "type": "object",
            "properties": {
                "project_folder": {
                    "type": "string",
                    "description": "Path to the project folder."
                },
                "report_name": {
                    "type": "string",
                    "description": "Name of the report to be saved."
                },
                "report_content": {
                    "type": "string",
                    "description": "The content of the generated report."
                },
                "progress_update_file": {
                    "type": "string",
                    "description": "Name of the progress update file."
                }
            },
            "required": ["project_folder", "report_name", "report_content"]
        }
    }
]

class FileReadError(Exception):
    """Raised when there's an error reading a file"""
    pass

__all__ = ['execute_tool', 'TOOLS', 'FileReadError', '_list_files', '_read_file', 'read_files_in_folder', '_create_file', '_create_folder', 'project_structure', 'project_study']