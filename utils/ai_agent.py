from google import genai
from google.genai import types
import streamlit as st
import json
import base64
import requests

# 1. Gemini Client 설정
def init_gemini():
    try:
        api_key = st.secrets["google"]["api_key"]
        return genai.Client(api_key=api_key)
    except Exception as e:
        st.error(f"Gemini API 연결 실패: {e}")
        return None

client = init_gemini()
MODEL_ID = "gemini-3-flash-preview"

# 공통 설정: Thinking Level = High (Explicit)
# Gemini 3.0은 기본값이 High이지만, 명시적으로 설정함.
config_high_thinking = types.GenerateContentConfig(
    thinking_config=types.ThinkingConfig(thinking_level="high")
)

# ==========================================
# 🧠 기능 1: 가이드라인 정제 (Admin용)
# ==========================================
def refine_guideline_with_ai(category, raw_input):
    """
    관리자의 거친 표현을 세련된 스크립트로 변환
    """
    if not client: return "AI 클라이언트 오류"

    prompt = f"""
    관리자의 지시사항을 상담원이 즉시 사용할 수 있는 **'간결하고 명확한 가이드'**로 변환하세요.
    서론, 인사말, 매니저의 조언 같은 불필요한 미사여구는 모두 제거하고 핵심만 남기세요.

    [입력 정보]
    - 카테고리: {category}
    - 관리자 지시: "{raw_input}"

    [출력 형식]
    다음 두 가지만 간결하게 작성:
    1. 💡 **행동 지침**: 무엇을 해야 하는지 1~2문장으로 요약
    2. 🗣️ **표준 스크립트**: 실제 고객 응대 시 사용할 1~2개의 핵심 문장
    """
    
    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt,
            config=config_high_thinking
        )
        return response.text
    except Exception as e:
        return f"AI 변환 실패: {e}"

def generate_reference_usage_context(content, file_data=None, mime_type="application/pdf"):
    """
    참고자료의 '사용 상황(Context)'을 AI로 추출
    (텍스트 또는 파일 기반)
    """
    if not client: return "AI Client Error"

    prompt = f"""
    이 참고자료가 상담 중 **언제 쓰여야 하는지**를 **가장 짧고 명확한 한 문장**으로 정의하세요. (토큰 절약 목적)
    구체적인 상황을 키워드 위주로 간결하게 표현하세요. (20자 내외 권장)
    **주의: 글자 수(예: (19자))를 출력 결과에 포함하지 마세요.**

    [출력 예시]
    - 단순 변심 환불 방어 시 (7일 경과)
    - 제품 하자 주장 대응 (증빙 없을 때)
    - 해지 위약금 안내 필요 시
    
    [실제 출력]
    사용 시점:
    """
    
    contents = [prompt]
    if file_data:
        contents.append(types.Part.from_bytes(data=file_data, mime_type=mime_type))
    elif content:
        contents.append(f"[자료 본문]\n{content}")
    else:
        return "내용 없음"
    
    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=contents,
            config=config_high_thinking
        )
        return response.text.replace("사용 시점:", "").strip()
    except Exception as e:
        return f"분석 실패: {str(e)[:50]}..."

# ==========================================
# 🧠 기능 2: 상담 분석 & 코칭 (Consultant용)
# ==========================================

def analyze_topic_and_traits(script=None, audio_data=None, mime_type="audio/mp3", ref_metadata=[], categories=[]):
    """
    [1차 분석] 주제 분류, 고객 성향, 고객 정보(이름/전화번호) 추출 + RAG 추천
    Now capable of using dynamic categories with descriptions.
    """
    if not client: return {"topic": "general", "customer_traits": "unknown", "customer_info": {}, "summary": "AI Error"}

    # 카테고리 정보 포맷팅
    cat_text = ""
    if categories:
        cat_text = "[가능한 상담 유형 (Categories)]\n"
        for c in categories:
            # c가 dict면 description 사용, str이면 이름만 사용
            if isinstance(c, dict):
                desc = f": {c.get('description')}" if c.get('description') else ""
                cat_text += f"- {c['name']}{desc}\n"
            else:
                cat_text += f"- {c}\n"
    else:
        # Fallback
        cat_text = "환불(refund), 기술(tech), 문의(inquiry), 일반(general) 중 택1"

    # 참고자료 리스트 텍스트 화
    ref_list_txt = ""
    if ref_metadata:
        ref_list_txt = "[가용 참고자료 목록]\n"
        for r in ref_metadata:
            # ID, Title, Context만 전달 (토큰 효율화)
            ref_list_txt += f"- ID:{r['id']} | {r['title']} (상황: {r.get('summary')})\n"

    sys_instruction = f"""
    상담 내용을 분석해서 다음 5가지 정보를 JSON으로 추출하세요.
    
    1. top_3_topics: 아래 '가능한 상담 유형' 중 가장 적절한 순서대로 상위 1~3개를 리스트로 반환 (영문 코드명)
    {cat_text}
    
    2. customer_traits: 급함, 화남, 논리적 등 핵심 키워드
    3. customer_info: 대화 중 언급된 고객의 이름과 전화번호(또는 식별자). 없으면 null.
    4. summary: 상담 내용 한줄 요약
    5. recommended_ref_ids: 위 '가용 참고자료 목록' 중, 현재 상담에 도움이 될 자료의 ID 리스트 (없으면 [])
    
    오디오가 입력되었다면 내용을 듣고 분석하세요.
    
    {ref_list_txt}
    
    [출력 포맷 - JSON Only]
    {{
        "top_3_topics": ["topic_A", "topic_B"], 
        "customer_traits": "...",
        "customer_info": {{
            "name": "홍길동" or null,
            "phone": "010-XXXX-XXXX" or null
        }},
        "summary": "...",
        "recommended_ref_ids": [123, 456]
    }}
    """
    
    contents = [sys_instruction]
    
    # 멀티모달 입력 처리
    if audio_data:
        contents.append(types.Part.from_bytes(data=audio_data, mime_type=mime_type))
    elif script:
        contents.append(f"[상담 내용]\n{script}")
    else:
        return None

    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=contents,
            config=config_high_thinking
        )
        
        # Regex로 JSON 블록 추출
        import re
        match = re.search(r'\{.*\}', response.text, re.DOTALL)
        if match:
            json_str = match.group(0)
            return json.loads(json_str)
        else:
            return json.loads(response.text) # 시도

    except Exception as e:
        print(f"1차 분석 실패: {e}")
        return {
            "topic": "general", 
            "customer_traits": "알수없음", 
            "customer_info": {"name": None, "phone": None},
            "summary": "분석 실패",
            "recommended_ref_ids": []
        }

def generate_coaching_feedback(script=None, audio_data=None, history=[], guidelines=[], references=[], mime_type="audio/mp3"):
    """
    [2차 분석] Context-Aware 코칭 + (오디오인 경우) STT 추출
    """
    if not client: return None
    
    history_text = ""
    if history:
        for h in history[-3:]:
            history_text += f"- {h.get('date')}: {h.get('summary')} (성향: {h.get('extracted_traits')})\n"
    
    rule_text = ""
    for g in guidelines:
        rule_text += f"- {g['refined_content']}\n"
        
    ref_text = ""
    if references:
        ref_text = "[참고 문헌 (법률, 규정, 매뉴얼)]\n"
        for r in references:
             # 파일이 있으면(PDF) 프롬프트 텍스트에서는 제외 (토큰 절약 및 중복 방지)
             # 단, DOCX나 TXT는 파일 Part 지원이 안되므로 텍스트로 포함
             f_url = r.get('file_url')
             is_pdf = f_url and f_url.lower().endswith('.pdf')
             
             if not is_pdf:
                ref_text += f"==== {r['title']} ====\n{r['content']}\n================\n"
             else:
                ref_text += f"==== {r['title']} ====\n(첨부된 PDF 파일 참조)\n================\n"

    prompt_text = f"""
    당신은 AI 세일즈 슈퍼바이저입니다. 
    과거 이력, 필수 가이드라인, 그리고 **참고 문헌(Reference)**을 바탕으로 상담 내용을 평가하고 정밀 코칭하세요.
    
    [고객 프로필 (History)]
    {history_text}
    
    [필수 준수 가이드라인]
    {rule_text}
    
    {ref_text}
    
    ---------------------------------------------------
    [요청 사항]
    위 상담 내용을 바탕으로 상담원의 화법을 구체적으로 교정해주는 JSON을 작성하세요.
    특히, 제공된 **'참고 문헌'이 있다면 이를 적극 활용하여 팩트 체크(Fact Check)**를 수행해야 합니다.
    상담원이 잘못된 정보를 안내했다면, 참고 문헌의 조항을 인용하여 정확한 정보를 알려주세요.
    
    'feedback' 필드에는:
    1. 잘한 점
    2. 아쉬운 점 & 수정 제안 (Before & After) - **참고 문헌 인용 필수**
    3. 총평
    을 포함하여 Markdown 형식으로 작성하세요.
    
    [출력 포맷 - JSON Only]
    {{
        "score": 0~100 사이 정수,
        "metrics": {{
            "empathy": 0~100,
            "clarity": 0~100,
            "compliance": 0~100
        }},
        "feedback": "...",
        "type": "상담 유형",
        "transcript": "..."
    }}
    """
    
    contents = [prompt_text]
    
    # [NEW] PDF 파일 첨부 처리 (References)
    if references:
        for r in references:
            f_url = r.get('file_url')
            # 1. 파일이 있고 PDF인 경우 -> File Part 전송
            if f_url and f_url.lower().endswith('.pdf'):
                try:
                    # 파일 다운로드 (Public URL or Signed URL needed. Assuming Public based on settings)
                    rf = requests.get(f_url)
                    if rf.status_code == 200:
                        print(f"📎 PDF Reference Attached: {r['title']}")
                        contents.append(types.Part.from_bytes(data=rf.content, mime_type="application/pdf"))
                    else:
                        print(f"⚠️ PDF Download Failed ({rf.status_code}): {f_url}")
                        # 실패 시 텍스트로 폴백할지 여부 결정. 여기선 텍스트 content가 있다면 텍스트는 프롬프트에 이미 포함됨?
                        # 아니오, 위 로직에서 ref_text 생성 시 file_url 있으면 제외할지 판단 필요.
                        # 현재 로직: ref_text에 텍스트도 넣고, 파일도 넣으면 중복/토큰낭비 가능성.
                        # -> "파일이 있으면 텍스트는 빼자"
                except Exception as e:
                    print(f"Error downloading ref file: {e}")
    
    if audio_data:
        contents.append(types.Part.from_bytes(data=audio_data, mime_type=mime_type))
    elif script:
        contents.append(f"[금번 상담 내용]\n{script}")

    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=contents,
            config=config_high_thinking
        )
        
        import re
        match = re.search(r'\{.*\}', response.text, re.DOTALL)
        if match:
            json_str = match.group(0)
            return json.loads(json_str)
        else:
             # Fallback
            return json.loads(response.text.replace("```json", "").replace("```", "").strip())
            
    except Exception as e:
        return {"score": 0, "metrics": {}, "feedback": f"분석 오류: {e}", "type": "unknown", "transcript": ""}