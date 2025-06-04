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

import pypandoc
from PIL import Image
from docx2pdf import convert as docx2pdf_convert

import pdfkit

import markdown

from llama_index.readers.file import HWPReader

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from PIL import Image
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch    

from bs4 import BeautifulSoup


from typing import List, Tuple
from pathlib import Path
from docsray.config import CACHE_DIR
import pandas as pd

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
import os

def _save_text_images_to_pdf_korean(text: str, image_paths: List[str], output_file: Path) -> bool:
    """Save text and images to PDF with Korean font support"""
    try:          
        # Register Korean fonts
        # Try to find Korean fonts on the system
        korean_fonts = [
            # Windows
            "C:/Windows/Fonts/malgun.ttf",  # Malgun Gothic
            "C:/Windows/Fonts/gulim.ttc",   # Gulim
            "C:/Windows/Fonts/batang.ttc",  # Batang
            # macOS
            "/System/Library/Fonts/AppleSDGothicNeo.ttc",
            "/Library/Fonts/NanumGothic.ttf",
            # Linux
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
            "/usr/share/fonts/truetype/fonts-nanum/NanumGothic.ttf",
        ]
        
        font_registered = False
        font_name = "NanumGothic"
        
        for font_path in korean_fonts:
            if os.path.exists(font_path):
                try:
                    pdfmetrics.registerFont(TTFont(font_name, font_path))
                    font_registered = True
                    break
                except:
                    continue
        
        if not font_registered:
            # Fallback: download and use a free Korean font
            import urllib.request
            font_url = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf"
            font_path = output_file.parent / "NanumGothic.ttf"
            urllib.request.urlretrieve(font_url, font_path)
            pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
        
        # Create PDF
        c = canvas.Canvas(str(output_file), pagesize=A4)
        width, height = A4
        
        # Set font with Korean support
        c.setFont(font_name, 12)
        
        # Add text
        y = height - 50
        for line in text.split('\n'):
            if y < 50:  # New page if needed
                c.showPage()
                c.setFont(font_name, 12)
                y = height - 50
            
            # Handle long lines
            if len(line) > 80:
                words = line.split()
                current_line = ""
                for word in words:
                    if len(current_line + word) < 80:
                        current_line += word + " "
                    else:
                        c.drawString(50, y, current_line.strip())
                        y -= 20
                        current_line = word + " "
                if current_line:
                    c.drawString(50, y, current_line.strip())
                    y -= 20
            else:
                c.drawString(50, y, line)
                y -= 20
        
        # Add images
        for img_path in image_paths:
            if os.path.exists(img_path):
                try:
                    c.showPage()
                    img = ImageReader(img_path)
                    c.drawImage(img, 50, 50, width=width-100, height=height-100, preserveAspectRatio=True)
                except:
                    pass
        
        c.save()
        return True
        
    except Exception as e:
        print(f"PDF creation error: {e}")
        return False
            
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
        '.hwp': 'Hancom Word Processor',
        '.hwpx': 'Hancom Word Processor (OOXML)',

        # Text formats
        '.txt': 'Plain Text',
        
        # Image formats
        '.jpg': 'JPEG Image',
        '.jpeg': 'JPEG Image',
        '.png': 'PNG Image',
        '.gif': 'GIF Image',
        '.bmp': 'Bitmap Image',
        '.tiff': 'TIFF Image',
        '.tif': 'TIFF Image',
        '.webp': 'WebP Image',
    }
    
    def __init__(self, output_dir: Optional[Path] = None):
        """
        Initialize converter with optional output directory
        
        Args:
            output_dir: Directory to save converted PDFs (default: temp directory)
        """
        self.output_dir = output_dir or CACHE_DIR
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
        elif file_ext == '.hwp':
            return self._convert_hwp_to_pdf(input_file, output_path)
        elif file_ext == '.hwpx':
            return self._convert_hwpx_to_pdf(input_file, output_path)
        
        elif file_ext in ['.pdf']:
            # If already PDF, just return the path
            return True, str(input_file)

        # Text formats
        elif file_ext == '.txt':
            return self._convert_text_to_pdf(input_file, output_path)
        
        # Image formats
        elif file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp']:
            return self._convert_image_to_pdf(input_file, output_path)
        
        # Fallback: try pandoc for anything else
        else:
            return self._convert_with_pandoc(input_file, output_path)
        
    # ------------------------------------------------------------------
    # HWPX → PDF  (zip + XML)  — text + images via BeautifulSoup + ReportLab
    # ------------------------------------------------------------------
    def _convert_hwpx_to_pdf(self, input_file: Path, output_file: Path) -> Tuple[bool, str]:
        """Convert HWPX (Hangul OOXML) to PDF."""
        from zipfile import ZipFile
        texts, img_paths = [], []
        tmp_dir = output_file.with_suffix("")  # temp folder alongside output
        tmp_dir.mkdir(exist_ok=True)

        try:
            with ZipFile(input_file) as zf:
                # 1) Collect text + image ids
                for name in zf.namelist():
                    if name.startswith("Contents/") and name.endswith(".xml"):
                        # Read with proper encoding
                        raw_content = zf.read(name)
                        
                        # Try different encodings for Korean text
                        for encoding in ['utf-8', 'utf-8-sig', 'cp949', 'euc-kr']:
                            try:
                                content = raw_content.decode(encoding)
                                break
                            except UnicodeDecodeError:
                                continue
                        else:
                            # If all encodings fail, use utf-8 with error handling
                            content = raw_content.decode('utf-8', errors='replace')
                        
                        soup = BeautifulSoup(content, "xml")
                        
                        # HWPX uses different tag structure
                        # Look for text in various possible tags
                        text_tags = ['t', 'text', 'hp:t', 'hp:run', 'w:t']
                        for tag_name in text_tags:
                            for text_elem in soup.find_all(tag_name):
                                text = text_elem.get_text(strip=True)
                                if text:
                                    texts.append(text)
                        
                        # Also try to find paragraphs with different naming conventions
                        para_tags = ['p', 'para', 'hp:p', 'hp:para', 'w:p']
                        for tag_name in para_tags:
                            for para in soup.find_all(tag_name):
                                para_text = para.get_text(" ", strip=True)
                                if para_text and para_text not in texts:
                                    texts.append(para_text)
                        
                        # Find images with various possible tag/attribute names
                        img_tags = ['pic', 'hp:pic', 'image', 'hp:image']
                        img_attrs = ['binFile', 'hp:binFile', 'r:embed', 'href']
                        
                        for img_tag in img_tags:
                            for pic in soup.find_all(img_tag):
                                for attr in img_attrs:
                                    img_id = pic.get(attr)
                                    if img_id:
                                        img_paths.append(img_id)

                # Debug: Print what we found
                print(f"Found {len(texts)} text elements")
                print(f"Found {len(img_paths)} image references")
                
                # 2) Extract BinData images
                extracted_imgs = []
                for img_id in img_paths:
                    for possible_path in [f"BinData/{img_id}", f"Contents/BinData/{img_id}", img_id]:
                        try:
                            data = zf.read(possible_path)
                            # Detect image type
                            if data[:8] == b"\x89PNG\r\n\x1a\n":
                                ext = ".png"
                            elif data[:2] == b"\xff\xd8":
                                ext = ".jpg"
                            else:
                                ext = ".bin"  # unknown format
                            
                            out_path = tmp_dir / f"{input_file.stem}_{img_id}{ext}"
                            out_path.write_bytes(data)
                            extracted_imgs.append(str(out_path))
                            break
                        except KeyError:
                            continue

                # 3) Synthesize PDF with proper encoding
                combined_text = "\n".join(texts) if texts else "No text content found"
                
                # Ensure _save_text_images_to_pdf handles Korean text properly
                success = _save_text_images_to_pdf_korean(combined_text, extracted_imgs, output_file)
                if success:
                    return True, str(output_file)
                return False, "PDF synthesis failed"

        except Exception as e:
            return False, f"HWPX conversion error: {e}"
        finally:
            # Cleanup temp directory
            try:
                import shutil
                shutil.rmtree(tmp_dir)
            except:
                pass

    def _convert_hwp_to_pdf(self, input_file: Path, output_file: Path) -> Tuple[bool, str]:
        """Convert HWP to PDF"""
        try:
            reader = HWPReader()
            # llama_index HWPReader returns a list of Document objects
            documents = reader.load_data(file=str(input_file))
            
            if documents and len(documents) > 0:
                # Combine text from all documents
                full_text = ""
                all_images = []
                
                for doc in documents:
                    # llama_index Document objects have a 'text' attribute
                    full_text += doc.text + "\n\n"
                    
                    # Extract images from metadata
                    # Metadata structure may vary depending on HWPReader implementation
                    if hasattr(doc, 'metadata') and doc.metadata:
                        images = doc.metadata.get("images", [])
                        all_images.extend(images)
                
                # Save text and images to PDF with Korean font support
                if _save_text_images_to_pdf_korean(full_text.strip(), all_images, output_file):
                    return True, str(output_file)
                else:
                    return False, "Failed to save PDF"
            else:
                return False, "Unable to read HWP document"
                
        except ImportError:
            return False, "llama_index not installed"
        except Exception as e:
            error_msg = f"Error during HWP conversion: {str(e)}"
            print(f"[Error] {error_msg}", file=sys.stderr)
            return False, error_msg

       
    def _convert_docx_to_pdf(self, input_file: Path, output_file: Path) -> Tuple[bool, str]:
        """Convert DOCX to PDF"""
        try:
            pypandoc.convert_file(str(input_file), 'pdf', outputfile=str(output_file))
            return True, str(output_file)
        except Exception as e:
            print(f"Pandoc conversion failed: {e}", file=sys.stderr)
            return False, e

    def _convert_excel_to_pdf(self, input_file: Path, output_file: Path) -> Tuple[bool, str]:
        """Convert Excel to PDF using pypandoc"""
        try:
            # Convert Excel to PDF via pandoc
            pypandoc.convert_file(
                str(input_file), 
                'pdf', 
                outputfile=str(output_file),
                extra_args=['--pdf-engine=xelatex']  # xelatex handles Unicode better
            )
            return True, str(output_file)
            
        except ImportError:
            return False, "Please install pypandoc: pip install pypandoc"
        except Exception as e:
            # Fallback to pandas if pypandoc fails
            try:
                # Read Excel file
                excel_file = pd.ExcelFile(input_file)
                
                # Convert to HTML first
                html_content = "<html><head><meta charset='utf-8'></head><body>"
                
                for sheet_name in excel_file.sheet_names:
                    df = excel_file.parse(sheet_name)
                    html_content += f"<h2>Sheet: {sheet_name}</h2>"
                    html_content += df.to_html(index=False, escape=False)
                    html_content += "<br><br>"
                
                html_content += "</body></html>"
                
                # Convert HTML to PDF using pypandoc
                pypandoc.convert_text(
                    html_content,
                    'pdf',
                    format='html',
                    outputfile=str(output_file),
                    extra_args=['--pdf-engine=xelatex', '--variable=mainfont:NanumGothic']
                )
                return True, str(output_file)
                
            except Exception as e2:
                return False, f"Excel conversion error: {str(e)} / {str(e2)}"

    def _convert_excel_to_pdf(self, input_file: Path, output_file: Path) -> Tuple[bool, str]:
        """Convert Excel to PDF using openpyxl and reportlab"""
        try:
            import openpyxl
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import inch
            
            # Load Excel file
            wb = openpyxl.load_workbook(input_file, data_only=True)
            
            # Create PDF
            doc = SimpleDocTemplate(str(output_file), pagesize=landscape(A4))
            story = []
            styles = getSampleStyleSheet()
            
            # Process each sheet
            for sheet_name in wb.sheetnames:
                sheet = wb[sheet_name]
                
                # Add sheet title
                story.append(Paragraph(f"Sheet: {sheet_name}", styles['Heading1']))
                story.append(Spacer(1, 0.2*inch))
                
                # Extract data from sheet
                data = []
                max_row = min(sheet.max_row, 1000)  # Limit rows to prevent memory issues
                max_col = min(sheet.max_column, 20)  # Limit columns
                
                for row in sheet.iter_rows(min_row=1, max_row=max_row, max_col=max_col, values_only=True):
                    # Convert None to empty string and everything to string
                    row_data = [str(cell) if cell is not None else '' for cell in row]
                    if any(row_data):  # Skip completely empty rows
                        data.append(row_data)
                
                if data:
                    # Create table
                    try:
                        # Calculate column widths dynamically
                        col_widths = [1.5*inch] * len(data[0]) if data else []
                        
                        table = Table(data, colWidths=col_widths)
                        
                        # Add style to table
                        table_style = TableStyle([
                            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                            ('FONTSIZE', (0, 0), (-1, 0), 10),
                            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                            ('GRID', (0, 0), (-1, -1), 1, colors.black),
                        ])
                        
                        table.setStyle(table_style)
                        story.append(table)
                        story.append(Spacer(1, 0.5*inch))
                    except Exception as e:
                        # If table creation fails, add data as text
                        for row in data[:100]:  # Limit to first 100 rows
                            text = ' | '.join(row)
                            story.append(Paragraph(text, styles['Normal']))
                        story.append(Spacer(1, 0.2*inch))
            
            # Build PDF
            doc.build(story)
            return True, str(output_file)
            
        except ImportError:
            return False, "Please install openpyxl and reportlab: pip install openpyxl reportlab"
        except Exception as e:
            return False, f"Excel conversion error: {str(e)}"
    
    def _convert_ppt_to_pdf(self, input_file: Path, output_file: Path) -> Tuple[bool, str]:
        """Convert PowerPoint to PDF using python-pptx and reportlab"""
        try:
            from pptx import Presentation
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import A4, landscape
            from PIL import Image
            import io
            
            # Load PowerPoint file
            prs = Presentation(str(input_file))
            
            # Create PDF
            c = canvas.Canvas(str(output_file), pagesize=landscape(A4))
            width, height = landscape(A4)
            
            for slide_num, slide in enumerate(prs.slides):
                if slide_num > 0:
                    c.showPage()
                
                # Add slide number
                c.setFont("Helvetica-Bold", 16)
                c.drawString(50, height - 50, f"Slide {slide_num + 1}")
                
                y_position = height - 100
                
                # Extract text from slide
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text:
                        c.setFont("Helvetica", 12)
                        
                        # Handle text that might be too long
                        text = shape.text.strip()
                        lines = text.split('\n')
                        
                        for line in lines:
                            if y_position < 50:
                                break
                                
                            # Wrap long lines
                            if len(line) > 80:
                                words = line.split()
                                current_line = ""
                                for word in words:
                                    if len(current_line + word) < 80:
                                        current_line += word + " "
                                    else:
                                        c.drawString(50, y_position, current_line.strip())
                                        y_position -= 20
                                        current_line = word + " "
                                if current_line:
                                    c.drawString(50, y_position, current_line.strip())
                                    y_position -= 20
                            else:
                                c.drawString(50, y_position, line)
                                y_position -= 20
                        
                        y_position -= 10  # Extra space between shapes
                    
                    # Handle images (basic support)
                    if shape.shape_type == 13:  # Picture
                        try:
                            image = shape.image
                            image_bytes = image.blob
                            img = Image.open(io.BytesIO(image_bytes))
                            
                            # Save temporary image
                            temp_img = output_file.parent / f"temp_img_{slide_num}_{shape.shape_id}.png"
                            img.save(temp_img)
                            
                            # Add to PDF (simplified positioning)
                            if y_position > 200:
                                c.drawImage(str(temp_img), 50, y_position - 150, width=200, height=150)
                                y_position -= 160
                            
                            # Clean up
                            temp_img.unlink()
                        except:
                            pass
                
                # Handle tables
                for shape in slide.shapes:
                    if shape.has_table:
                        y_position -= 20
                        c.setFont("Helvetica", 10)
                        c.drawString(50, y_position, "[Table]")
                        y_position -= 15
                        
                        table = shape.table
                        for row in table.rows:
                            row_text = " | ".join([cell.text for cell in row.cells])
                            if len(row_text) > 80:
                                row_text = row_text[:77] + "..."
                            c.drawString(50, y_position, row_text)
                            y_position -= 15
                            if y_position < 50:
                                break
            
            c.save()
            return True, str(output_file)
            
        except ImportError:
            return False, "Please install python-pptx and pillow: pip install python-pptx pillow"
        except Exception as e:
            return False, f"PowerPoint conversion error: {str(e)}"

            
    def _convert_text_to_pdf(self, input_file: Path, output_file: Path) -> Tuple[bool, str]:
        """Convert plain text to PDF"""
        try:
            # Read text file
            with open(input_file, 'r', encoding='utf-8') as f:
                text = f.read()

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
            # Try pdfkit
            try:
                pdfkit.from_string(html_content, str(output_file))
                return True, str(output_file)
            except Exception as e:
                converters_tried.append("pdfkit")
            
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
        if converters_tried:
            error_msg += f"Tried: {', '.join(converters_tried)}. "
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
    
    def _convert_image_to_pdf(self, input_file: Path, output_file: Path) -> Tuple[bool, str]:
        """Convert image to PDF"""       
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
        try:
            pypandoc.convert_file(str(input_file), 'pdf', outputfile=str(output_file))
            return True, str(output_file)
        except Exception as e:
            return False, f"Pandoc conversion failed: {e}"

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