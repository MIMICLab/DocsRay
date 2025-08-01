"""
Multimedia processing utilities for audio and video files
"""

import os
import subprocess
import tempfile
import logging
from pathlib import Path
from typing import Tuple, List, Optional
import re
from faster_whisper import WhisperModel
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
import textwrap

logger = logging.getLogger(__name__)

class AudioProcessor:
    """Process audio files using faster-whisper"""
    
    def __init__(self, model_size: str = "base"):
        """
        Initialize audio processor with faster-whisper model
        
        Args:
            model_size: Model size (tiny, base, small, medium, large-v1, large-v2, large-v3)
        """
        self.model_size = model_size
        self.model = None
        
    def load_model(self):
        """Load faster-whisper model lazily"""
        if self.model is None:
            logger.info(f"Loading faster-whisper model: {self.model_size}")
            # Use CPU by default, but will use GPU if available
            self.model = WhisperModel(self.model_size, device="auto", compute_type="default")
            
    def transcribe_audio(self, audio_path: str) -> Tuple[str, str]:
        """
        Transcribe audio file to text
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Tuple of (transcribed_text, detected_language)
        """
        self.load_model()
        
        logger.info(f"Transcribing audio: {audio_path}")
        
        # Transcribe audio
        segments, info = self.model.transcribe(
            audio_path,
            beam_size=5,
            best_of=5,
            language=None,  # Auto-detect language
            task="transcribe",
            condition_on_previous_text=True,
        )
        
        # Collect all segments
        transcribed_text = " ".join([segment.text for segment in segments])
        detected_language = info.language
        
        # Clean transcribed text
        transcribed_text = self.clean_transcribed_text(transcribed_text)
        
        logger.info(f"Detected language: {detected_language}")
        logger.info(f"Transcription length: {len(transcribed_text)} characters")
        
        # Debug: Print transcribed text for audio files
        logger.info(f"[DEBUG] Transcribed text: {transcribed_text[:500]}...")  # First 500 chars
        
        return transcribed_text, detected_language
    
    @staticmethod
    def clean_transcribed_text(text: str) -> str:
        """
        Clean transcribed text by removing unnecessary characters
        
        Args:
            text: Raw transcribed text
            
        Returns:
            Cleaned text
        """
        if not text:
            return text
            
        # Define allowed punctuation marks
        allowed_punctuation = set('.,!?;:\'"-()[]{}…')
        
        # Remove special characters except allowed punctuation, alphanumeric, and spaces
        cleaned_chars = []
        for char in text:
            if char.isalnum() or char.isspace() or char in allowed_punctuation:
                cleaned_chars.append(char)
            elif ord(char) >= 0xAC00 and ord(char) <= 0xD7A3:  # Korean characters
                cleaned_chars.append(char)
        
        text = ''.join(cleaned_chars)
        
        # Remove multiple spaces
        text = re.sub(r'\s+', ' ', text)
        
        # Remove leading/trailing whitespace
        text = text.strip()
        
        # Remove repeated punctuation (e.g., "..." becomes ".")
        text = re.sub(r'([.!?])\1+', r'\1', text)
        
        # Fix spacing around punctuation
        text = re.sub(r'\s+([,.!?;:])', r'\1', text)
        text = re.sub(r'([,.!?;:])(?=[A-Za-z가-힣])', r'\1 ', text)
        
        # Keep repeated words as they may be meaningful (e.g., children repeating phrases)
        
        return text
    
    def save_transcription(self, text: str, output_path: str) -> str:
        """
        Save transcription to text file
        
        Args:
            text: Transcribed text
            output_path: Output file path
            
        Returns:
            Path to saved file
        """
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(text)
        
        logger.info(f"Saved transcription to: {output_path}")
        return output_path


class VideoProcessor:
    """Process video files - extract frames and audio"""
    
    @staticmethod
    def check_ffmpeg():
        """Check if ffmpeg is installed"""
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.error("ffmpeg not found. Please install ffmpeg to process video files.")
            logger.error("Run 'docsray setup' to install dependencies automatically")
            return False
    
    @staticmethod
    def extract_frames(video_path: str, output_dir: str, fps: float = 0.25) -> List[str]:
        """
        Extract frames from video at specified FPS
        
        Args:
            video_path: Path to video file
            output_dir: Directory to save frames
            fps: Frames per second to extract (default 0.25 fps, 1 frame every 4 seconds)
            
        Returns:
            List of extracted frame paths
        """
        if not VideoProcessor.check_ffmpeg():
            raise RuntimeError("ffmpeg is required for video processing")
        
        os.makedirs(output_dir, exist_ok=True)
        
        # Extract frames using ffmpeg with 4-second intervals
        output_pattern = os.path.join(output_dir, "frame_%04d.jpg")
        
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-vf', f'fps={fps}',
            '-q:v', '2',  # High quality JPEG
            output_pattern,
            '-y'  # Overwrite existing files
        ]
        
        logger.info(f"Extracting frames at {fps} fps (1 frame every 4 seconds) from: {video_path}")
        
        try:
            subprocess.run(cmd, capture_output=True, check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to extract frames: {e.stderr.decode()}")
            raise RuntimeError(f"Failed to extract frames: {e.stderr.decode()}")
        
        # Get list of extracted frames
        frame_files = sorted([
            os.path.join(output_dir, f) 
            for f in os.listdir(output_dir) 
            if f.startswith("frame_") and f.endswith(".jpg")
        ])
        
        logger.info(f"Extracted {len(frame_files)} frames")
        return frame_files
    
    @staticmethod
    def extract_audio(video_path: str, output_path: str) -> str:
        """
        Extract audio from video file
        
        Args:
            video_path: Path to video file
            output_path: Path for output audio file
            
        Returns:
            Path to extracted audio file
        """
        if not VideoProcessor.check_ffmpeg():
            raise RuntimeError("ffmpeg is required for video processing")
        
        # Extract audio as MP3
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-vn',  # No video
            '-acodec', 'mp3',
            '-ab', '192k',  # Audio bitrate
            output_path,
            '-y'  # Overwrite existing files
        ]
        
        logger.info(f"Extracting audio from: {video_path}")
        
        try:
            subprocess.run(cmd, capture_output=True, check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to extract audio: {e.stderr.decode()}")
            raise RuntimeError(f"Failed to extract audio: {e.stderr.decode()}")
        
        logger.info(f"Extracted audio to: {output_path}")
        return output_path


class MultimediaPDFCreator:
    """Create PDF from video frames and transcribed text"""
    
    @staticmethod
    def create_pdf_from_video_data(
        frame_paths: List[str],
        transcribed_text: str,
        output_path: str,
        title: str = "Video Content Analysis"
    ) -> str:
        """
        Create PDF combining video frames and transcribed text in 4x4 grid layout
        
        Args:
            frame_paths: List of paths to video frames
            transcribed_text: Transcribed audio text
            output_path: Path for output PDF
            title: PDF title
            
        Returns:
            Path to created PDF
        """
        # Create PDF document
        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=18,
        )
        
        # Container for the 'Flowable' objects
        story = []
        
        # Define styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor='black',
            spaceAfter=30,
            alignment=TA_LEFT
        )
        
        subtitle_style = ParagraphStyle(
            'CustomSubtitle',
            parent=styles['Heading2'],
            fontSize=18,
            textColor='black',
            spaceAfter=20,
            alignment=TA_LEFT
        )
        
        text_style = ParagraphStyle(
            'CustomText',
            parent=styles['Normal'],
            fontSize=12,
            leading=16,
            textColor='black',
            spaceAfter=12,
            alignment=TA_LEFT
        )
        
        # Add title
        story.append(Paragraph(title, title_style))
        story.append(Spacer(1, 12))
        
        # Add transcription section
        story.append(Paragraph("Audio Transcription", subtitle_style))
        
        # Split long text into paragraphs
        if transcribed_text:
            # Wrap text to reasonable line length
            wrapped_text = textwrap.fill(transcribed_text, width=80)
            for paragraph in wrapped_text.split('\n\n'):
                if paragraph.strip():
                    story.append(Paragraph(paragraph, text_style))
                    story.append(Spacer(1, 6))
        else:
            story.append(Paragraph("No audio transcription available.", text_style))
        
        story.append(PageBreak())
        
        # Add frames section
        story.append(Paragraph("Video Frames (1 frame every 4 seconds)", subtitle_style))
        story.append(Spacer(1, 12))
        
        # Create 4x4 grid layout (16 frames per page)
        frames_per_page = 16
        for page_start in range(0, len(frame_paths), frames_per_page):
            page_frames = frame_paths[page_start:page_start + frames_per_page]
            
            # Create a grid layout using reportlab table
            from reportlab.platypus import Table, TableStyle
            from reportlab.lib import colors
            
            grid_data = []
            grid_size = 4  # 4x4 grid
            frame_width = 1.3 * inch
            frame_height = 0.975 * inch  # 4:3 aspect ratio
            
            for row in range(grid_size):
                row_data = []
                for col in range(grid_size):
                    frame_idx = row * grid_size + col
                    if frame_idx < len(page_frames):
                        frame_path = page_frames[frame_idx]
                        global_frame_idx = page_start + frame_idx
                        
                        if os.path.exists(frame_path):
                            try:
                                # Create a cell with timestamp and image as a single flowable
                                timestamp = f"T: {global_frame_idx * 4}s"
                                # Create a mini table to contain both timestamp and image
                                from reportlab.platypus import Table as MiniTable
                                mini_data = [
                                    [Paragraph(timestamp, ParagraphStyle('Timestamp', fontSize=8, alignment=TA_LEFT))],
                                    [RLImage(frame_path, width=frame_width, height=frame_height)]
                                ]
                                mini_table = MiniTable(mini_data, colWidths=[frame_width])
                                mini_table.setStyle(TableStyle([
                                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                                    ('FONTSIZE', (0, 0), (-1, -1), 8),
                                ]))
                                row_data.append(mini_table)
                            except Exception as e:
                                logger.error(f"Failed to load frame {frame_path}: {e}")
                                row_data.append(Paragraph(f"[Frame {global_frame_idx+1} error]", ParagraphStyle('Error', fontSize=8)))
                        else:
                            row_data.append(Paragraph(f"[Frame {global_frame_idx+1} missing]", ParagraphStyle('Error', fontSize=8)))
                    else:
                        row_data.append('')  # Empty cell
                grid_data.append(row_data)
            
            if grid_data:
                # Create table with grid
                table = Table(grid_data, colWidths=[frame_width + 0.4*inch] * grid_size, 
                             rowHeights=[frame_height + 0.5*inch] * grid_size)
                table.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                    ('FONTSIZE', (0, 0), (-1, -1), 8),
                    ('LEFTPADDING', (0, 0), (-1, -1), 6),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ]))
                
                story.append(table)
                
                # Add page break if not the last page
                if page_start + frames_per_page < len(frame_paths):
                    story.append(PageBreak())
        
        # Build PDF
        try:
            doc.build(story)
            logger.info(f"Created PDF: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Failed to create PDF: {e}")
            raise RuntimeError(f"Failed to create PDF: {e}")


def process_audio_file(audio_path: str, output_dir: str) -> str:
    """
    Process audio file and convert to text file
    
    Args:
        audio_path: Path to audio file
        output_dir: Directory for output files
        
    Returns:
        Path to transcribed text file
    """
    processor = AudioProcessor()
    
    # Transcribe audio
    text, language = processor.transcribe_audio(audio_path)
    
    # Save transcription
    base_name = Path(audio_path).stem
    txt_path = os.path.join(output_dir, f"{base_name}_transcription.txt")
    
    # Add metadata to transcription
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(f"Audio Transcription\n")
        f.write(f"==================\n")
        f.write(f"Source: {Path(audio_path).name}\n")
        f.write(f"Language: {language}\n")
        f.write(f"==================\n\n")
        f.write(text)
    
    return txt_path


def process_video_file(video_path: str, output_dir: str) -> str:
    """
    Process video file and convert to PDF with frames and transcription
    
    Args:
        video_path: Path to video file
        output_dir: Directory for output files
        
    Returns:
        Path to created PDF file
    """
    # Create subdirectories
    frames_dir = os.path.join(output_dir, "frames")
    audio_dir = os.path.join(output_dir, "audio")
    os.makedirs(frames_dir, exist_ok=True)
    os.makedirs(audio_dir, exist_ok=True)
    
    # Extract frames at 4-second intervals
    frame_paths = VideoProcessor.extract_frames(video_path, frames_dir, fps=0.25)
    
    # Extract and transcribe audio
    audio_path = os.path.join(audio_dir, "extracted_audio.mp3")
    VideoProcessor.extract_audio(video_path, audio_path)
    
    # Transcribe audio
    processor = AudioProcessor()
    transcribed_text, _ = processor.transcribe_audio(audio_path)
    
    # Create PDF
    base_name = Path(video_path).stem
    pdf_path = os.path.join(output_dir, f"{base_name}_video_content.pdf")
    
    MultimediaPDFCreator.create_pdf_from_video_data(
        frame_paths=frame_paths,
        transcribed_text=transcribed_text,
        output_path=pdf_path,
        title=f"Video Analysis: {Path(video_path).name}"
    )
    
    return pdf_path