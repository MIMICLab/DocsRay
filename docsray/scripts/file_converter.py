#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
docsray/scripts/file_converter.py
Convert various file formats to PDF for processing
"""

import os
import sys
from pathlib import Path
from typing import Optional, Tuple
import tempfile
import subprocess

# Office document conversion
try:
    import pypandoc
    HAS_PANDOC = True
except ImportError:
    HAS_PANDOC = False

# Image to PDF conversion
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# DOCX to PDF
try:
    from docx2pdf import convert as docx2pdf_convert
    HAS_DOCX2PDF = True
except ImportError:
    HAS_DOCX2PDF = False

# HTML to PDF
try:
    import pdfkit
    HAS_PDFKIT = True
except ImportError:
    HAS_PDFKIT = False

# Markdown to PDF
try:
    import markdown
    import weasyprint
    HAS_MARKDOWN = True
except ImportError:
    HAS_MARKDOWN = False

try:
    import pyhwp
    HAS_PYHWP = True
except ImportError:
    HAS_PYHWP = False

try:
    import hwp5
    HAS_HWP5 = True
except ImportError:
    HAS_HWP5 = False

try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

class FileConverter:
    """Convert various file formats to PDF"""
    
    SUPPORTED_FORMATS = {
        # Office documents
        '.docx': 'Microsoft Word',
        '.doc': 'Microsoft Word (Legacy)',
        '.xlsx': 'Microsoft Excel',
        '.xls': 'Microsoft Excel (Legacy)',
        '.pdf': 'PDF Document',
        '.pptx': 'Microsoft PowerPoint',
        '.ppt': 'Microsoft PowerPoint (Legacy)',
        '.odt': 'OpenDocument Text',
        '.ods': 'OpenDocument Spreadsheet',
        '.odp': 'OpenDocument Presentation',
        #'.hwp': 'Hangul Word Processor',
        #'.hwpx': 'Hangul Word Processor (OOXML)',


        # Text formats
        '.txt': 'Plain Text',
        '.md': 'Markdown',
        '.rst': 'reStructuredText',
        '.rtf': 'Rich Text Format',
        
        # Web formats
        '.html': 'HTML',
        '.htm': 'HTML',
        '.xml': 'XML',
        
        # Image formats
        '.jpg': 'JPEG Image',
        '.jpeg': 'JPEG Image',
        '.png': 'PNG Image',
        '.gif': 'GIF Image',
        '.bmp': 'Bitmap Image',
        '.tiff': 'TIFF Image',
        '.tif': 'TIFF Image',
        '.webp': 'WebP Image',
        
        # Other formats
        '.epub': 'EPUB Book',
        '.mobi': 'Kindle Book',
    }
    
    def __init__(self, output_dir: Optional[Path] = None):
        """
        Initialize converter with optional output directory
        
        Args:
            output_dir: Directory to save converted PDFs (default: temp directory)
        """
        self.output_dir = output_dir or Path(tempfile.gettempdir())
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def convert_to_pdf(self, input_path: str, output_path: Optional[str] = None) -> Tuple[bool, str]:
        """
        Convert file to PDF
        
        Args:
            input_path: Path to input file
            output_path: Optional output path (default: auto-generated)
            
        Returns:
            Tuple of (success: bool, output_path_or_error: str)
        """
        input_file = Path(input_path)
        
        # Check if file exists
        if not input_file.exists():
            return False, f"File not found: {input_path}"
        
        # Check if already PDF
        if input_file.suffix.lower() == '.pdf':
            return True, str(input_file)
        
        # Check if format is supported
        file_ext = input_file.suffix.lower()
        if file_ext not in self.SUPPORTED_FORMATS:
            return False, f"Unsupported format: {file_ext}"
        
        # Generate output path if not provided
        if output_path is None:
            output_path = self.output_dir / f"{input_file.stem}_converted.pdf"
        else:
            output_path = Path(output_path)
        
        # Select conversion method based on file type
        print(f"Converting {self.SUPPORTED_FORMATS[file_ext]} file to PDF...", file=sys.stderr)
        
        # Office documents
        if file_ext in ['.docx', '.doc']:
            return self._convert_docx_to_pdf(input_file, output_path)
        elif file_ext in ['.xlsx', '.xls']:
            return self._convert_excel_to_pdf(input_file, output_path)
        elif file_ext in ['.pptx', '.ppt']:
            return self._convert_ppt_to_pdf(input_file, output_path)
        #elif file_ext in ['.hwp', '.hwpx']:
        #    if HAS_HWP5:
        #        return self._convert_hwp_to_pdf_with_hwp5(input_file, output_path)
        #    else:
        #        return self._convert_hwp_to_pdf(input_file, output_path)
        elif file_ext in ['.odt', '.ods', '.odp']:
            if HAS_PANDOC:
                return self._convert_with_pandoc(input_file, output_path)
            else:
                return False, "OpenDocument formats require pandoc for conversion."
        elif file_ext in ['.pdf']:
            # If already PDF, just return the path
            return True, str(input_file)   
               
        # Text formats
        elif file_ext == '.txt':
            return self._convert_text_to_pdf(input_file, output_path)
        elif file_ext == '.md':
            return self._convert_markdown_to_pdf(input_file, output_path)
        elif file_ext in ['.html', '.htm']:
            return self._convert_html_to_pdf(input_file, output_path)
        
        # Image formats
        elif file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp']:
            return self._convert_image_to_pdf(input_file, output_path)
        
        # Try pandoc for other formats
        else:
            return self._convert_with_pandoc(input_file, output_path)
    
    def _convert_docx_to_pdf(self, input_file: Path, output_file: Path) -> Tuple[bool, str]:
        """Convert DOCX to PDF"""
        # Try multiple methods in order of preference
        
        # Method 1: LibreOffice (most reliable)
        if self._check_libreoffice():
            try:
                cmd = [
                    'libreoffice', '--headless', '--convert-to', 'pdf',
                    '--outdir', str(output_file.parent), str(input_file)
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    # LibreOffice names the output file automatically
                    expected_output = output_file.parent / f"{input_file.stem}.pdf"
                    if expected_output.exists() and expected_output != output_file:
                        expected_output.rename(output_file)
                    return True, str(output_file)
            except Exception as e:
                print(f"LibreOffice conversion failed: {e}", file=sys.stderr)
        
        # Method 2: docx2pdf (Windows/Mac)
        if HAS_DOCX2PDF:
            try:
                docx2pdf_convert(str(input_file), str(output_file))
                return True, str(output_file)
            except Exception as e:
                print(f"docx2pdf conversion failed: {e}", file=sys.stderr)
        
        # Method 3: pandoc
        if HAS_PANDOC:
            try:
                pypandoc.convert_file(str(input_file), 'pdf', outputfile=str(output_file))
                return True, str(output_file)
            except Exception as e:
                print(f"Pandoc conversion failed: {e}", file=sys.stderr)
        
        return False, "No suitable DOCX converter found. Install LibreOffice, docx2pdf, or pandoc."
    
    def _convert_excel_to_pdf(self, input_file: Path, output_file: Path) -> Tuple[bool, str]:
        """Convert Excel to PDF"""
        # Try LibreOffice
        if self._check_libreoffice():
            try:
                cmd = [
                    'libreoffice', '--headless', '--convert-to', 'pdf',
                    '--outdir', str(output_file.parent), str(input_file)
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    expected_output = output_file.parent / f"{input_file.stem}.pdf"
                    if expected_output.exists() and expected_output != output_file:
                        expected_output.rename(output_file)
                    return True, str(output_file)
            except Exception as e:
                print(f"LibreOffice conversion failed: {e}", file=sys.stderr)
        
        return False, "Excel conversion requires LibreOffice. Please install it first."
    
    def _convert_ppt_to_pdf(self, input_file: Path, output_file: Path) -> Tuple[bool, str]:
        """Convert PowerPoint to PDF"""
        # Try LibreOffice
        if self._check_libreoffice():
            try:
                cmd = [
                    'libreoffice', '--headless', '--convert-to', 'pdf',
                    '--outdir', str(output_file.parent), str(input_file)
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    expected_output = output_file.parent / f"{input_file.stem}.pdf"
                    if expected_output.exists() and expected_output != output_file:
                        expected_output.rename(output_file)
                    return True, str(output_file)
            except Exception as e:
                print(f"LibreOffice conversion failed: {e}", file=sys.stderr)
        
        return False, "PowerPoint conversion requires LibreOffice. Please install it first."
    def _convert_hwp_to_pdf(self, input_file: Path, output_file: Path) -> Tuple[bool, str]:
        """Convert HWP to PDF"""
        
        if HAS_PYHWP:
            try:
                hwp = pyhwp.HWP(str(input_file))
                
                text_content = ""
                for section in hwp.sections:
                    text_content += section.get_text() + "\n\n"
                
                html_content = f"""
                <html>
                <head>
                    <meta charset="utf-8">
                    <style>
                        body {{
                            font-family: 'Malgun Gothic', 'Nanum Gothic', sans-serif;
                            margin: 40px;
                            line-height: 1.6;
                        }}
                        p {{ margin-bottom: 10px; }}
                    </style>
                </head>
                <body>
                    <h1>{input_file.name}</h1>
                    {"".join(f"<p>{para}</p>" for para in text_content.split('\n') if para.strip())}
                </body>
                </html>
                """
                
     
                if HAS_MARKDOWN:
                    html_doc = weasyprint.HTML(string=html_content)
                    html_doc.write_pdf(str(output_file))
                    return True, str(output_file)
                    
            except Exception as e:
                print(f"pyhwp conversion failed: {e}", file=sys.stderr)
        
        if self._check_hancom():
            try:
                cmd = ['hwp', '--convert-to', 'pdf', '--outdir', str(output_file.parent), str(input_file)]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    return True, str(output_file)
            except Exception as e:
                print(f"Hancom Office conversion failed: {e}", file=sys.stderr)
        
        return False, "HWP conversion requires pyhwp or Hancom Office"

    def _check_hancom(self) -> bool:
        """Check if Hancom Office is available"""
        try:
            result = subprocess.run(['hwp', '--version'], capture_output=True)
            return result.returncode == 0
        except FileNotFoundError:
            return False
    
    def _convert_hwp_to_pdf_with_hwp5(self, input_file: Path, output_file: Path) -> Tuple[bool, str]:
        """Convert HWP to PDF using hwp5"""
        if not HAS_HWP5:
            return False, "hwp5 not installed"
        
        try:
            odf_path = output_file.with_suffix('.odt')
            
            cmd = ['hwp5odt', str(input_file), str(odf_path)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                if self._check_libreoffice():
                    cmd = [
                        'libreoffice', '--headless', '--convert-to', 'pdf',
                        '--outdir', str(output_file.parent), str(odf_path)
                    ]
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    
                    odf_path.unlink(missing_ok=True)
                    
                    if result.returncode == 0:
                        return True, str(output_file)
            
        except Exception as e:
            print(f"hwp5 conversion failed: {e}", file=sys.stderr)
        
        return False, "HWP conversion failed"

    def _convert_text_to_pdf(self, input_file: Path, output_file: Path) -> Tuple[bool, str]:
        """Convert plain text to PDF"""
        try:
            # Read text file
            with open(input_file, 'r', encoding='utf-8') as f:
                text = f.read()
            
            # First try: reportlab (most reliable for text)
            if HAS_REPORTLAB:
                try:
                    doc = SimpleDocTemplate(str(output_file), pagesize=A4)
                    styles = getSampleStyleSheet()
                    story = []
                    
                    # Title
                    title_style = ParagraphStyle(
                        'CustomTitle',
                        parent=styles['Heading1'],
                        fontSize=24,
                        spaceAfter=30
                    )
                    story.append(Paragraph(input_file.name, title_style))
                    story.append(Spacer(1, 0.2*inch))
                    
                    # Content
                    text_style = ParagraphStyle(
                        'CustomText',
                        parent=styles['Normal'],
                        fontSize=11,
                        leading=14
                    )
                    
                    # Split text into paragraphs
                    for paragraph in text.split('\n\n'):
                        if paragraph.strip():
                            # Escape special characters for reportlab
                            safe_text = paragraph.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                            story.append(Paragraph(safe_text, text_style))
                            story.append(Spacer(1, 0.1*inch))
                    
                    doc.build(story)
                    return True, str(output_file)
                    
                except Exception as e:
                    print(f"Reportlab conversion failed: {e}", file=sys.stderr)
            
            # Second try: Direct PDF creation using pure Python
            try:
                # Simple PDF creation without external dependencies
                pdf_content = self._create_simple_pdf(text, input_file.name)
                with open(output_file, 'wb') as f:
                    f.write(pdf_content)
                return True, str(output_file)
            except Exception as e:
                print(f"Simple PDF creation failed: {e}", file=sys.stderr)
            
            # Third try: Create HTML and convert
            html_content = f"""
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        margin: 40px;
                        line-height: 1.6;
                        white-space: pre-wrap;
                    }}
                    h1 {{
                        color: #333;
                        border-bottom: 2px solid #333;
                        padding-bottom: 10px;
                    }}
                    pre {{
                        background: #f4f4f4;
                        padding: 15px;
                        border-radius: 5px;
                        overflow-x: auto;
                    }}
                </style>
            </head>
            <body>
                <h1>{input_file.name}</h1>
                <pre>{text}</pre>
            </body>
            </html>
            """
            
            # Try various HTML to PDF converters
            converters_tried = []
            
            # Try weasyprint
            if HAS_MARKDOWN:
                try:
                    import weasyprint
                    html_doc = weasyprint.HTML(string=html_content)
                    html_doc.write_pdf(str(output_file))
                    return True, str(output_file)
                except Exception as e:
                    converters_tried.append("weasyprint")
            
            # Try pdfkit
            if HAS_PDFKIT:
                try:
                    import pdfkit
                    pdfkit.from_string(html_content, str(output_file))
                    return True, str(output_file)
                except Exception as e:
                    converters_tried.append("pdfkit")
            
            # Try pandoc
            if HAS_PANDOC:
                try:
                    temp_html = output_file.with_suffix('.html')
                    with open(temp_html, 'w', encoding='utf-8') as f:
                        f.write(html_content)
                    
                    pypandoc.convert_file(str(temp_html), 'pdf', outputfile=str(output_file))
                    temp_html.unlink()
                    return True, str(output_file)
                except Exception as e:
                    converters_tried.append("pandoc")
                    
        except Exception as e:
            print(f"Text to PDF conversion error: {e}", file=sys.stderr)
        
        # Provide helpful error message
        error_msg = "Text conversion failed. "
        if not HAS_REPORTLAB:
            error_msg += "Install reportlab for best results: pip install reportlab"
        elif converters_tried:
            error_msg += f"Tried: {', '.join(converters_tried)}. "
            error_msg += "Install one of: reportlab, weasyprint, pdfkit+wkhtmltopdf, or pandoc"
        else:
            error_msg += "No PDF converters available. Install: pip install reportlab"
        
        return False, error_msg

    def _create_simple_pdf(self, text: str, title: str) -> bytes:
        """Create a very simple PDF without external dependencies"""
        # This is a minimal PDF creator - for production use reportlab is recommended
        lines = text.split('\n')
        
        # Basic PDF structure
        pdf = b"%PDF-1.4\n"
        
        # Catalog and Pages
        pdf += b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        pdf += b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        
        # Page
        pdf += b"3 0 obj\n<< /Type /Page /Parent 2 0 R /Resources 4 0 R /MediaBox [0 0 612 792] /Contents 5 0 R >>\nendobj\n"
        
        # Resources
        pdf += b"4 0 obj\n<< /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >>\nendobj\n"
        
        # Content stream
        content = f"BT /F1 12 Tf 50 750 Td ({title}) Tj ET\n"
        y_pos = 720
        for line in lines[:50]:  # Limit to first 50 lines for simplicity
            if line.strip():
                # Escape special characters
                safe_line = line.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
                content += f"BT /F1 10 Tf 50 {y_pos} Td ({safe_line[:80]}) Tj ET\n"
                y_pos -= 15
                if y_pos < 50:
                    break
        
        content_bytes = content.encode('latin-1', errors='replace')
        pdf += f"5 0 obj\n<< /Length {len(content_bytes)} >>\nstream\n".encode()
        pdf += content_bytes
        pdf += b"\nendstream\nendobj\n"
        
        # xref table
        xref_pos = len(pdf)
        pdf += b"xref\n0 6\n"
        pdf += b"0000000000 65535 f \n"
        pdf += b"0000000009 00000 n \n"
        pdf += b"0000000058 00000 n \n"
        pdf += b"0000000115 00000 n \n"
        pdf += b"0000000229 00000 n \n"
        pdf += b"0000000328 00000 n \n"
        
        # Trailer
        pdf += b"trailer\n<< /Size 6 /Root 1 0 R >>\n"
        pdf += f"startxref\n{xref_pos}\n".encode()
        pdf += b"%%EOF"
        
        return pdf

    def _convert_markdown_to_pdf(self, input_file: Path, output_file: Path) -> Tuple[bool, str]:
        """Convert Markdown to PDF"""
        if HAS_PANDOC:
            try:
                pypandoc.convert_file(str(input_file), 'pdf', outputfile=str(output_file))
                return True, str(output_file)
            except Exception as e:
                print(f"Pandoc conversion failed: {e}", file=sys.stderr)
        
        if HAS_MARKDOWN:
            try:
                # Read markdown
                with open(input_file, 'r', encoding='utf-8') as f:
                    md_text = f.read()
                
                # Convert to HTML
                html_content = markdown.markdown(md_text, extensions=['extra', 'codehilite'])
                
                # Wrap in HTML document
                full_html = f"""
                <html>
                <head>
                    <meta charset="utf-8">
                    <style>
                        body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
                        code {{ background: #f4f4f4; padding: 2px 4px; }}
                        pre {{ background: #f4f4f4; padding: 10px; overflow-x: auto; }}
                        h1, h2, h3 {{ color: #333; }}
                    </style>
                </head>
                <body>
                    {html_content}
                </body>
                </html>
                """
                
                # Convert to PDF
                if HAS_MARKDOWN:
                    html_doc = weasyprint.HTML(string=full_html)
                    html_doc.write_pdf(str(output_file))
                    return True, str(output_file)
            except Exception as e:
                print(f"Markdown conversion failed: {e}", file=sys.stderr)
        
        return False, "Markdown conversion requires pandoc or markdown+weasyprint."
    
    def _convert_html_to_pdf(self, input_file: Path, output_file: Path) -> Tuple[bool, str]:
        """Convert HTML to PDF"""
        if HAS_PDFKIT:
            try:
                pdfkit.from_file(str(input_file), str(output_file))
                return True, str(output_file)
            except Exception as e:
                print(f"pdfkit conversion failed: {e}", file=sys.stderr)
        
        if HAS_MARKDOWN:
            try:
                html_doc = weasyprint.HTML(filename=str(input_file))
                html_doc.write_pdf(str(output_file))
                return True, str(output_file)
            except Exception as e:
                print(f"weasyprint conversion failed: {e}", file=sys.stderr)
        
        return False, "HTML conversion requires pdfkit or weasyprint."
    
    def _convert_image_to_pdf(self, input_file: Path, output_file: Path) -> Tuple[bool, str]:
        """Convert image to PDF"""
        if not HAS_PIL:
            return False, "Image conversion requires Pillow. Install with: pip install pillow"
        
        try:
            # Open image
            img = Image.open(input_file)
            
            # Convert to RGB if necessary
            if img.mode in ('RGBA', 'LA'):
                # Create white background
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'RGBA':
                    background.paste(img, mask=img.split()[-1])
                else:
                    background.paste(img)
                img = background
            elif img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')
            
            # Save as PDF
            img.save(str(output_file), 'PDF', resolution=100.0)
            return True, str(output_file)
            
        except Exception as e:
            return False, f"Image conversion failed: {e}"
    
    def _convert_with_pandoc(self, input_file: Path, output_file: Path) -> Tuple[bool, str]:
        """Try to convert using pandoc as fallback"""
        if not HAS_PANDOC:
            return False, "Pandoc not available for conversion"
        
        try:
            pypandoc.convert_file(str(input_file), 'pdf', outputfile=str(output_file))
            return True, str(output_file)
        except Exception as e:
            return False, f"Pandoc conversion failed: {e}"
    
    def _check_libreoffice(self) -> bool:
        """Check if LibreOffice is available"""
        try:
            result = subprocess.run(['libreoffice', '--version'], capture_output=True)
            return result.returncode == 0
        except FileNotFoundError:
            return False
    
    @classmethod
    def get_supported_formats(cls) -> dict:
        """Get dictionary of supported formats"""
        return cls.SUPPORTED_FORMATS.copy()
    
    @classmethod
    def is_supported(cls, file_path: str) -> bool:
        """Check if file format is supported"""
        ext = Path(file_path).suffix.lower()
        return ext in cls.SUPPORTED_FORMATS or ext == '.pdf'


def convert_file_to_pdf(input_path: str, output_dir: Optional[str] = None) -> Tuple[bool, str]:
    """
    Convenience function to convert a file to PDF
    
    Args:
        input_path: Path to input file
        output_dir: Optional output directory
        
    Returns:
        Tuple of (success: bool, output_path_or_error: str)
    """
    converter = FileConverter(Path(output_dir) if output_dir else None)
    return converter.convert_to_pdf(input_path)


if __name__ == "__main__":
    # Test conversion
    import argparse
    
    parser = argparse.ArgumentParser(description="Convert files to PDF")
    parser.add_argument("input_file", help="Input file path")
    parser.add_argument("-o", "--output", help="Output PDF path")
    parser.add_argument("-d", "--output-dir", help="Output directory")
    
    args = parser.parse_args()
    
    converter = FileConverter(Path(args.output_dir) if args.output_dir else None)
    success, result = converter.convert_to_pdf(args.input_file, args.output)
    
    if success:
        print(f"✅ Converted successfully: {result}")
    else:
        print(f"❌ Conversion failed: {result}")
        sys.exit(1)