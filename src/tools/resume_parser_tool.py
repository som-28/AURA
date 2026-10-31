"""Resume parser tool - extracts text from PDF/DOCX resumes."""
from typing import Tuple, List
import os


def _extract_from_pdf(file_path: str) -> str:
    """Extract text from PDF file with OCR fallback."""
    try:
        import PyPDF2
        with open(file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            
            text = text.strip()
            
            # Check if extraction worked
            if not text or len(text) < 10:
                # Try OCR as fallback
                return _extract_from_pdf_with_ocr(file_path)
            
            return text
    except Exception as e:
        return f"Error reading PDF: {str(e)}"


def _extract_from_pdf_with_ocr(file_path: str) -> str:
    """Extract text from scanned/image-based PDF using OCR."""
    try:
        from pdf2image import convert_from_path
        import pytesseract
        
        # Try to find Tesseract executable on Windows
        if os.name == 'nt':  # Windows
            possible_paths = [
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                r"C:\Users\{}\AppData\Local\Tesseract-OCR\tesseract.exe".format(os.getenv('USERNAME')),
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    pytesseract.pytesseract.tesseract_cmd = path
                    break
        
        # Convert PDF pages to images
        images = convert_from_path(file_path)
        
        text = ""
        for i, image in enumerate(images):
            # Perform OCR on each page
            page_text = pytesseract.image_to_string(image)
            text += page_text + "\n"
        
        text = text.strip()
        
        if not text or len(text) < 10:
            return "Error: Could not extract text from PDF even with OCR. Please try DOCX or TXT format."
        
        return text
        
    except ImportError:
        return "Error: OCR libraries not installed. Please run: pip install pytesseract pdf2image pillow"
    except Exception as e:
        return f"Error during OCR: {str(e)}. Try converting to DOCX or TXT format."


def _extract_from_docx(file_path: str) -> str:
    """Extract text from DOCX file."""
    try:
        from docx import Document
        doc = Document(file_path)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        return text.strip()
    except Exception as e:
        return f"Error reading DOCX: {e}"


def _extract_from_txt(file_path: str) -> str:
    """Extract text from TXT file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read().strip()
    except Exception as e:
        return f"Error reading TXT: {e}"


def run(args: dict, context: dict) -> Tuple[List[str], dict]:
    """Parse resume and extract text content.
    
    Args:
        args: {"file_path": str} - Path to resume file
        context: Execution context
    
    Returns:
        logs, {"resume_text": str, "file_name": str}
    """
    logs = []
    file_path = args.get("file_path", "")
    
    if not file_path or not os.path.exists(file_path):
        logs.append("Error: Resume file not found")
        return logs, {"resume_text": "", "error": "File not found"}
    
    file_name = os.path.basename(file_path)
    file_ext = os.path.splitext(file_path)[1].lower()
    
    logs.append(f"Parsing resume: {file_name}")
    
    # Extract text based on file type
    if file_ext == '.pdf':
        text = _extract_from_pdf(file_path)
    elif file_ext in ['.docx', '.doc']:
        text = _extract_from_docx(file_path)
    elif file_ext == '.txt':
        text = _extract_from_txt(file_path)
    else:
        logs.append(f"Unsupported file format: {file_ext}")
        return logs, {"resume_text": "", "error": f"Unsupported format: {file_ext}"}
    
    if text.startswith("Error"):
        logs.append(text)
        return logs, {"resume_text": "", "error": text}
    
    word_count = len(text.split())
    logs.append(f"Successfully parsed resume ({word_count} words)")
    
    return logs, {
        "resume_text": text,
        "file_name": file_name,
        "word_count": word_count
    }
