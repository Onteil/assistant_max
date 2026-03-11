"""
Test file type classification functionality.

Tests the classify_file_type function to ensure correct file type detection
based on file extensions.

Requirements: 15.6, 15.7, 15.8
"""

import pytest
from database.models import FileType
from services.validation_service import classify_file_type


class TestFileTypeClassification:
    """Test suite for file type classification."""
    
    def test_pdf_classification(self):
        """Test that PDF files are correctly classified."""
        assert classify_file_type("document.pdf") == FileType.PDF
        assert classify_file_type("REPORT.PDF") == FileType.PDF
        assert classify_file_type("file.Pdf") == FileType.PDF
    
    def test_image_classification(self):
        """Test that image files are correctly classified."""
        # Common image formats
        assert classify_file_type("photo.jpg") == FileType.IMAGE
        assert classify_file_type("image.jpeg") == FileType.IMAGE
        assert classify_file_type("picture.png") == FileType.IMAGE
        assert classify_file_type("animation.gif") == FileType.IMAGE
        assert classify_file_type("bitmap.bmp") == FileType.IMAGE
        assert classify_file_type("modern.webp") == FileType.IMAGE
        
        # Case insensitive
        assert classify_file_type("PHOTO.JPG") == FileType.IMAGE
        assert classify_file_type("Image.PNG") == FileType.IMAGE
    
    def test_document_classification(self):
        """Test that document files are correctly classified."""
        # Microsoft Office formats
        assert classify_file_type("report.doc") == FileType.DOCUMENT
        assert classify_file_type("report.docx") == FileType.DOCUMENT
        assert classify_file_type("spreadsheet.xls") == FileType.DOCUMENT
        assert classify_file_type("spreadsheet.xlsx") == FileType.DOCUMENT
        
        # Text formats
        assert classify_file_type("notes.txt") == FileType.DOCUMENT
        assert classify_file_type("formatted.rtf") == FileType.DOCUMENT
        
        # OpenDocument formats
        assert classify_file_type("document.odt") == FileType.DOCUMENT
        assert classify_file_type("spreadsheet.ods") == FileType.DOCUMENT
        
        # Case insensitive
        assert classify_file_type("REPORT.DOCX") == FileType.DOCUMENT
    
    def test_other_classification(self):
        """Test that unknown file types are classified as OTHER."""
        # Various other file types
        assert classify_file_type("archive.zip") == FileType.OTHER
        assert classify_file_type("video.mp4") == FileType.OTHER
        assert classify_file_type("audio.mp3") == FileType.OTHER
        assert classify_file_type("executable.exe") == FileType.OTHER
        assert classify_file_type("script.py") == FileType.OTHER
    
    def test_none_file_name(self):
        """Test that None file name returns OTHER."""
        assert classify_file_type(None) == FileType.OTHER
    
    def test_empty_file_name(self):
        """Test that empty file name returns OTHER."""
        assert classify_file_type("") == FileType.OTHER
    
    def test_no_extension(self):
        """Test that file names without extension return OTHER."""
        assert classify_file_type("README") == FileType.OTHER
        assert classify_file_type("Makefile") == FileType.OTHER
    
    def test_multiple_dots(self):
        """Test file names with multiple dots."""
        assert classify_file_type("my.document.pdf") == FileType.PDF
        assert classify_file_type("backup.2024.01.15.docx") == FileType.DOCUMENT
        assert classify_file_type("photo.final.v2.jpg") == FileType.IMAGE
