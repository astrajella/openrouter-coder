# tests/test_tools.py

import os
import sys
import pytest

# Add the backend directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.tools import read_file, write_file, list_files, create_directory, delete_file, rename_file

@pytest.fixture
def setup_teardown():
    """Setup and teardown for file system tests."""
    test_dir = "test_dir"
    test_file = os.path.join(test_dir, "test_file.txt")
    renamed_file = os.path.join(test_dir, "renamed_file.txt")

    # Teardown: Clean up created files and directories
    yield test_dir, test_file, renamed_file

    if os.path.exists(test_file):
        os.remove(test_file)
    if os.path.exists(renamed_file):
        os.remove(renamed_file)
    if os.path.exists(test_dir):
        os.rmdir(test_dir)

def test_create_directory(setup_teardown):
    test_dir, _, _ = setup_teardown
    result = create_directory(test_dir)
    assert os.path.isdir(test_dir)
    assert "created successfully" in result

def test_write_and_read_file(setup_teardown):
    test_dir, test_file, _ = setup_teardown
    create_directory(test_dir)

    content = "Hello, world!"
    write_result = write_file(test_file, content)
    assert "written successfully" in write_result

    read_result = read_file(test_file)
    assert read_result == content

def test_list_files(setup_teardown):
    test_dir, test_file, _ = setup_teardown
    create_directory(test_dir)
    write_file(test_file, "content")

    file_list = list_files(test_dir)
    assert "test_file.txt" in file_list

def test_rename_file(setup_teardown):
    test_dir, test_file, renamed_file = setup_teardown
    create_directory(test_dir)
    write_file(test_file, "content")

    rename_result = rename_file(test_file, renamed_file)
    assert "renamed to" in rename_result
    assert not os.path.exists(test_file)
    assert os.path.exists(renamed_file)

def test_delete_file(setup_teardown):
    test_dir, test_file, _ = setup_teardown
    create_directory(test_dir)
    write_file(test_file, "content")

    delete_result = delete_file(test_file)
    assert "deleted successfully" in delete_result
    assert not os.path.exists(test_file)
