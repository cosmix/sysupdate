"""SHA256 checksum verification utilities for self-update."""

import hashlib
from pathlib import Path


def parse_sha256sums(content: str) -> dict[str, str]:
    """Parse SHA256SUMS.txt format into a mapping of filename to hash.

    Expected format: "<hash>  <filename>" (two spaces between hash and filename)

    Args:
        content: Content of SHA256SUMS.txt file

    Returns:
        Dictionary mapping filename to SHA256 hash

    Examples:
        >>> content = "abc123  file1.tar.gz\\ndef456  file2.tar.gz"
        >>> parse_sha256sums(content)
        {'file1.tar.gz': 'abc123', 'file2.tar.gz': 'def456'}
    """
    checksums: dict[str, str] = {}

    for line in content.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # SHA256SUMS format: "<hash>  <filename>" (two spaces)
        parts = line.split(None, 1)  # Split on whitespace, max 2 parts
        if len(parts) == 2:
            hash_value, filename = parts
            checksums[filename] = hash_value.lower()

    return checksums


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hash of a file.

    Args:
        file_path: Path to the file to hash

    Returns:
        Lowercase hexadecimal SHA256 hash string

    Raises:
        FileNotFoundError: If file does not exist
        PermissionError: If file cannot be read
    """
    sha256_hash = hashlib.sha256()

    with file_path.open("rb") as f:
        # Read file in chunks to handle large files efficiently
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)

    return sha256_hash.hexdigest().lower()


def verify_checksum(file_path: Path, expected_hash: str) -> bool:
    """Verify that a file's SHA256 checksum matches the expected hash.

    Args:
        file_path: Path to the file to verify
        expected_hash: Expected SHA256 hash (case-insensitive)

    Returns:
        True if checksum matches, False otherwise

    Raises:
        FileNotFoundError: If file does not exist
        PermissionError: If file cannot be read
    """
    actual_hash = compute_sha256(file_path)
    return actual_hash == expected_hash.lower()
