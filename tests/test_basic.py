"""
Basic tests for DocsRay functionality
"""
import unittest
from pathlib import Path
import sys
import tempfile

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from docsray.utils.text_cleaning import basic_clean_text
from docsray.scripts.chunker import chunk_text, _tokenize, _detokenize


class TestTextCleaning(unittest.TestCase):
    """Test text cleaning utilities"""
    
    def test_basic_clean_text(self):
        """Test basic text cleaning functionality"""
        # Test tab and newline replacement
        text = "Hello\tworld\nHow are\tyou?"
        expected = "Hello world How are you?"
        self.assertEqual(basic_clean_text(text), expected)
        
        # Test multiple spaces
        text = "Hello    world   !"
        expected = "Hello world !"
        self.assertEqual(basic_clean_text(text), expected)
        
        # Test strip
        text = "  Hello world  "
        expected = "Hello world"
        self.assertEqual(basic_clean_text(text), expected)
        
        # Test empty string
        self.assertEqual(basic_clean_text(""), "")
        
        # Test string with only whitespace
        self.assertEqual(basic_clean_text("   \t\n   "), "")


class TestChunker(unittest.TestCase):
    """Test text chunking functionality"""
    
    def test_tokenize_detokenize(self):
        """Test tokenization round trip"""
        text = "Hello world, how are you today?"
        tokens = _tokenize(text)
        
        # Check that we get tokens
        self.assertIsInstance(tokens, list)
        self.assertGreater(len(tokens), 0)
        
        # Check round trip
        if hasattr(_tokenize, '__code__') and 'tiktoken' in str(_tokenize.__code__.co_names):
            # tiktoken version - should preserve exact text
            reconstructed = _detokenize(tokens)
            self.assertEqual(reconstructed, text)
        else:
            # Fallback whitespace version
            self.assertEqual(tokens, text.split())
    
    def test_chunk_text_basic(self):
        """Test basic text chunking"""
        text = " ".join(["word"] * 100)  # 100 words
        
        # Test with small chunks
        chunks = chunk_text(text, chunk_size=10, overlap=0)
        
        # Should have multiple chunks
        self.assertGreater(len(chunks), 1)
        
        # Each chunk should have content
        for chunk in chunks:
            self.assertIsInstance(chunk, str)
            self.assertGreater(len(chunk), 0)
    
    def test_chunk_text_overlap(self):
        """Test chunking with overlap"""
        # Create text with numbered words for easy verification
        words = [f"word{i}" for i in range(20)]
        text = " ".join(words)
        
        chunks = chunk_text(text, chunk_size=5, overlap=2)
        
        # Should have overlapping content
        self.assertGreater(len(chunks), 1)
        
        # Verify chunks have content
        for chunk in chunks:
            self.assertGreater(len(chunk.strip()), 0)
    
    def test_chunk_empty_text(self):
        """Test chunking empty text"""
        chunks = chunk_text("")
        self.assertEqual(chunks, [])
        
        chunks = chunk_text("   \t\n   ")
        self.assertEqual(chunks, [])


class TestFileConverter(unittest.TestCase):
    """Test file converter functionality"""
    
    def test_supported_formats(self):
        """Test getting supported formats"""
        from docsray.scripts.file_converter import FileConverter
        
        converter = FileConverter()
        formats = converter.get_supported_formats()
        
        # Check that we have some formats
        self.assertIsInstance(formats, dict)
        self.assertGreater(len(formats), 0)
        
        # Check some expected formats
        self.assertIn('.pdf', formats)
        self.assertIn('.docx', formats)
        self.assertIn('.txt', formats)
        self.assertIn('.png', formats)
    
    def test_is_supported(self):
        """Test format support checking"""
        from docsray.scripts.file_converter import FileConverter
        
        converter = FileConverter()
        
        # Test supported formats
        self.assertTrue(converter.is_supported("test.pdf"))
        self.assertTrue(converter.is_supported("test.docx"))
        self.assertTrue(converter.is_supported("test.txt"))
        self.assertTrue(converter.is_supported("TEST.PDF"))  # Case insensitive
        
        # Test unsupported format
        self.assertFalse(converter.is_supported("test.xyz"))
        self.assertFalse(converter.is_supported("test"))  # No extension


if __name__ == '__main__':
    unittest.main()