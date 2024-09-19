from typing import Dict, List, Tuple, Optional
from datetime import datetime

class FilesContext:
    """
    Manages the context of files for the Codai application.
    
    This class keeps track of file contents, modifications, and provides
    methods to interact with and retrieve file information for API calls.
    It does not perform actual file operations but manages the context
    of files within the application.
    """

    def __init__(self):
        """Initialize the FileContext with empty dictionaries and no last API call time."""
        self.files: Dict[str, str] = {}
        self.last_modified: Dict[str, datetime] = {}
        self.modification_source: Dict[str, str] = {}
        self.last_api_call: Optional[datetime] = None

    def update_file_in_context(self, relative_path: str, file_content: str, source: str) -> None:
        """
        Add a new file or update an existing file in the context.

        Args:
            relative_path (str): The relative path of the file.
            file_content (str): The content of the file.
            source (str): The source of the modification (e.g., 'user', 'list_files', 'read_file').
        """
        self.files[relative_path] = file_content
        self.last_modified[relative_path] = datetime.now()
        self.modification_source[relative_path] = source

    def remove_file_from_context(self, relative_path: str) -> None:
        """
        Remove a file from the context.

        Args:
            relative_path (str): The relative path of the file to remove.

        Raises:
            KeyError: If the file does not exist in the context.
        """
        if relative_path not in self.files:
            raise KeyError(f"File '{relative_path}' not found in the context.")
        
        del self.files[relative_path]
        del self.last_modified[relative_path]
        del self.modification_source[relative_path]

    def get_all_file_paths(self) -> List[str]:
        """
        Return a list of all file paths in the context.

        Returns:
            List[str]: A list of relative paths of all files in the context.
        """
        return list(self.files.keys())

    def list_files_in_context(self) -> str:
        """
        Generate a formatted string listing all files in the context.

        Returns:
            str: A formatted string containing a list of all files in the context.
        """
        file_list = self.get_all_file_paths()
        if not file_list:
            return "No files in context."
        
        return "Files in context:\n" + "\n".join(f"- {file}" for file in sorted(file_list))

    def split_files_for_api_context(self) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
        """
        Split and retrieve files into existing and new/modified categories for API context.

        This method is crucial for optimizing API calls by separating files that have been
        modified since the last API call from those that haven't changed. It sorts the files
        based on their last modification time.

        Returns:
            Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]: A tuple containing two lists:
                1. Existing files: [(relative_path, file_content), ...]
                2. New/modified files: [(relative_path, file_content), ...]
                Both lists are sorted by last modification time (oldest first).
        """
        existing_files = []
        new_modified_files = []

        for relative_path, file_content in self.files.items():
            file_tuple = (relative_path, file_content)
            if self.last_api_call and self.last_modified[relative_path] > self.last_api_call:
                new_modified_files.append(file_tuple)
            else:
                existing_files.append(file_tuple)

        # Sort both lists by last modification time (oldest first)
        existing_files.sort(key=lambda x: self.last_modified[x[0]])
        new_modified_files.sort(key=lambda x: self.last_modified[x[0]])

        return existing_files, new_modified_files

    def update_last_api_call_timestamp(self) -> None:
        """
        Update the timestamp of the last API call.

        This method should be called immediately after each API call to ensure
        accurate tracking of file modifications between calls.
        """
        self.last_api_call = datetime.now()
