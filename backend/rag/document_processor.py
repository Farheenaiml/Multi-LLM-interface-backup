import logging
import io
from typing import List

from pypdf import PdfReader
from docx import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

class DocumentProcessor:
    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        """
        Initializes the document processor config.
        We use character length heuristically matching ~tokens. Langchain's Recursive splitter is great for this.
        """
        # Note: 500 characters usually != 500 tokens. 
        # Typically 1 token ~= 4 chars in English, so for ~500 tokens we might want ~2000 chars.
        # But we align with user request to keep chunks relatively small and overlapping.
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size * 4,  # Approx 500 tokens
            chunk_overlap=chunk_overlap * 4, # Approx 50 tokens
            length_function=len,
            separators=["\n\n", "\n", " ", ""]
        )

    async def ingest_file(self, filename: str, content: bytes) -> List[str]:
        """
        Extract text from file bytes based on filename extension, then chunk it.
        """
        ext = filename.split('.')[-1].lower()
        extracted_text = ""
        
        try:
            if ext == 'pdf':
                extracted_text = self._extract_pdf(content)
            elif ext == 'docx':
                extracted_text = self._extract_docx(content)
            elif ext == 'txt':
                extracted_text = content.decode('utf-8', errors='replace')
            else:
                raise ValueError(f"Unsupported file type: {ext}")
                
            if not extracted_text.strip():
                logger.warning(f"No text could be extracted from {filename}")
                return []
                
            # Split the extracted text into chunks
            chunks = self.text_splitter.split_text(extracted_text)
            logger.info(f"Extracted and split {filename} into {len(chunks)} chunks.")
            return chunks
            
        except Exception as e:
            logger.error(f"Error processing document {filename}: {e}")
            raise e

    def _extract_pdf(self, content: bytes) -> str:
        pdf_file = io.BytesIO(content)
        reader = PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text

    def _extract_docx(self, content: bytes) -> str:
        docx_file = io.BytesIO(content)
        doc = Document(docx_file)
        text = "\n".join([para.text for para in doc.paragraphs])
        return text
