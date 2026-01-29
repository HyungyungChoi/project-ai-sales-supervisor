import pypdf
import docx
import io

def extract_text_from_file(uploaded_file):
    """
    Streamlit uploaded_file 객체(PDF or DOCX or TXT)에서 텍스트를 추출합니다.
    """
    file_type = uploaded_file.name.split('.')[-1].lower()
    text = ""
    
    try:
        if file_type == 'pdf':
            # PDF Reader
            pdf_reader = pypdf.PdfReader(uploaded_file)
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
                
        elif file_type == 'docx':
            # Docx Reader
            doc = docx.Document(uploaded_file)
            for para in doc.paragraphs:
                text += para.text + "\n"
                
        elif file_type == 'txt':
            # Text File
            text = uploaded_file.getvalue().decode("utf-8")
            
        else:
            return None, "지원하지 않는 파일 형식입니다."
            
        return text.strip(), None
        
    except Exception as e:
        return None, f"파일 처리 중 오류 발생: {str(e)}"
